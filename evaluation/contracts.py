"""Canonical contracts: platform APIs never receive grading data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import jsonschema

from evaluation.artifacts import load_json

FORMAT_CHECKER = jsonschema.FormatChecker()


def zoned_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    return "T" in value and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None


FORMAT_CHECKER.checks("date-time", raises=(ValueError, TypeError))(zoned_timestamp)


class Split(StrEnum):
    TRAIN = "TRAIN"
    TEST = "TEST"
    HOLDOUT = "HOLDOUT"


@dataclass(frozen=True)
class Question:
    question_id: str
    intent_id: str
    leakage_group_id: str
    language: str
    text: str
    category: str
    difficulty: str
    critical: bool
    split: Split
    origin: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Question:
        validate("question", data)
        return cls(**{**data, "split": Split(data["split"])})


@dataclass(frozen=True)
class GroundTruth:
    question_id: str
    expected: dict[str, Any]
    oracle_sql: str | None
    ordered: bool = False
    tolerances: dict[str, str] = field(default_factory=dict)
    evidence_alternatives: tuple[tuple[str, ...], ...] = ()
    prohibited_claims: tuple[str, ...] = ()
    reviewer: str = "unreviewed"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroundTruth:
        validate("ground_truth", data)
        return cls(
            **{
                **data,
                "evidence_alternatives": tuple(
                    tuple(x) for x in data.get("evidence_alternatives", [])
                ),
                "prohibited_claims": tuple(data.get("prohibited_claims", [])),
            }
        )


@dataclass(frozen=True)
class InvocationRequest:
    invocation_id: str
    candidate_id: str
    deployment_ref: str
    question_text: str
    repetition: int
    deadline_seconds: int = 120


@dataclass(frozen=True)
class InvocationResult:
    status: str
    response_text: str | None
    latency_ms: int
    request_id: str | None
    raw: dict[str, Any]
    error_code: str | None = None


@dataclass(frozen=True)
class UsageRecord:
    scope_id: str
    component: str
    usd: Decimal | None
    credits: Decimal | None
    state: str
    attribution: str
    rate_card_hash: str | None


class PlatformAdapter(Protocol):
    def probe(self) -> dict[str, Any]: ...
    def deploy(self, bundle: dict[str, Any]) -> dict[str, Any]: ...
    def verify(self, deployment: dict[str, Any]) -> dict[str, Any]: ...
    def estimate(self, batch: dict[str, Any]) -> dict[str, Any]: ...
    def invoke(self, request: InvocationRequest) -> InvocationResult: ...
    def collect_usage(self, batch: dict[str, Any]) -> list[UsageRecord]: ...
    def export_trace(self, invocation: dict[str, Any]) -> dict[str, Any]: ...


def validate(name: str, value: Any) -> None:
    schema = load_json(Path(__file__).parent / "schemas" / f"{name}.json")
    jsonschema.Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(value)


def validate_splits(questions: list[Question], *, require_v1: bool = True) -> None:
    ids: set[str] = set()
    groups: dict[str, Split] = {}
    intents: dict[str, Split] = {}
    categories: dict[str, dict[Split, int]] = {}
    for q in questions:
        if q.question_id in ids:
            raise ValueError("Duplicate question ID")
        ids.add(q.question_id)
        for key, registry in [(q.leakage_group_id, groups), (q.intent_id, intents)]:
            if key in registry and registry[key] != q.split:
                raise ValueError("Leakage group or intent crosses splits")
            registry[key] = q.split
        counts = categories.setdefault(q.category, dict.fromkeys(Split, 0))
        counts[q.split] += 1
        if require_v1 and q.language != "de":
            raise ValueError("V1 scores canonical German only")
    if require_v1:
        if len(questions) != 24 or len(categories) != 6:
            raise ValueError("V1 requires 24 questions in six categories")
        if any(
            counts != {Split.TRAIN: 2, Split.TEST: 1, Split.HOLDOUT: 1}
            for counts in categories.values()
        ):
            raise ValueError("Invalid category split allocation")
        critical = {s: sum(q.critical for q in questions if q.split == s) for s in Split}
        if critical != {Split.TRAIN: 4, Split.TEST: 2, Split.HOLDOUT: 2}:
            raise ValueError("Invalid critical-question allocation")
