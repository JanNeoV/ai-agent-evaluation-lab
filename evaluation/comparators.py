"""Typed result comparison, with explicit unknowns, bags, ties and tolerances."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import jsonschema

from evaluation.contracts import GroundTruth, validate


@dataclass(frozen=True)
class Comparison:
    deterministic_pass: bool
    errors: tuple[str, ...]


def parse_answer(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[8:-4]
    elif text.startswith("```\n") and text.endswith("\n```"):
        text = text[4:-4]

    def reject(value: str) -> None:
        raise ValueError(f"Nonfinite value {value}")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate answer key")
            result[key] = value
        return result

    answer: dict[str, Any] = json.loads(text, parse_constant=reject, object_pairs_hook=pairs)
    try:
        validate("answer", answer)
    except jsonschema.ValidationError as exc:
        raise ValueError("Answer does not satisfy the frozen output contract") from exc
    if len(set(answer["columns"])) != len(answer["columns"]):
        raise ValueError("Duplicate answer column")
    if any(len(row) != len(answer["columns"]) for row in answer["rows"]):
        raise ValueError("Row width does not match columns")
    return answer


def cell_equal(actual: Any, expected: Any, tolerance: str | None) -> bool:
    if actual is None or expected is None:
        return actual is None and expected is None
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if tolerance is not None:
        # String identifiers must never become approximate numbers.
        if not isinstance(actual, (float, int)) or not isinstance(expected, (float, int)):
            return False
        try:
            bound = Decimal(tolerance)
            if not bound.is_finite() or bound < 0:
                raise ValueError("Invalid tolerance")
            return abs(Decimal(str(actual)) - Decimal(str(expected))) <= bound
        except InvalidOperation:
            return False
    if type(actual) is not type(expected):
        return False
    return bool(actual == expected)


def rows_equal(
    actual: list[list[Any]],
    expected: list[list[Any]],
    columns: list[str],
    tolerances: dict[str, str],
    ordered: bool,
) -> bool:
    if len(actual) != len(expected):
        return False

    def matches(left: list[Any], right: list[Any]) -> bool:
        return len(left) == len(right) == len(columns) and all(
            cell_equal(a, b, tolerances.get(col))
            for col, a, b in zip(columns, left, right, strict=True)
        )

    if ordered:
        return all(matches(a, b) for a, b in zip(actual, expected, strict=True))
    # Bipartite matching rather than greedy matching: overlapping tolerance bands
    # can make a greedy bag comparator reject an otherwise valid permutation.
    owners: dict[int, int] = {}

    def assign(i: int, visited: set[int]) -> bool:
        for j, row in enumerate(expected):
            if j in visited or not matches(actual[i], row):
                continue
            visited.add(j)
            if j not in owners or assign(owners[j], visited):
                owners[j] = i
                return True
        return False

    return all(assign(i, set()) for i in range(len(actual)))


def compare(text: str | None, truth: GroundTruth) -> Comparison:
    if text is None:
        return Comparison(False, ("FORMAT_INVALID",))
    try:
        answer = parse_answer(text)
    except (ValueError, TypeError, jsonschema.ValidationError):
        return Comparison(False, ("FORMAT_INVALID",))
    expected = truth.expected
    errors: list[str] = []
    if answer["status"] != expected["status"]:
        errors.append(
            "FAILED_TO_ABSTAIN" if expected["status"] != "answered" else "UNNECESSARY_ABSTENTION"
        )
    if answer["columns"] != expected["columns"] or not rows_equal(
        answer["rows"], expected["rows"], expected["columns"], truth.tolerances, truth.ordered
    ):
        errors.append("WRONG_VALUE")
    if answer["units"] != expected["units"]:
        errors.append("WRONG_UNITS")
    if not set(expected["caveats"]).issubset(answer["caveats"]):
        errors.append("MISSING_CAVEAT")
    if truth.evidence_alternatives and not any(
        set(group).issubset(answer["evidence_ids"]) for group in truth.evidence_alternatives
    ):
        errors.append("UNSUPPORTED_PROVENANCE")
    # Explanation, extra caveats and extra evidence need the human review rubric.
    return Comparison(not errors, tuple(errors))
