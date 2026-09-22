"""Assess saved evidence. Human narrative review is mandatory for acceptance."""

from __future__ import annotations

import math
import random
from collections import Counter
from decimal import Decimal
from statistics import median
from typing import Any

from evaluation.artifacts import digest
from evaluation.comparators import compare
from evaluation.contracts import GroundTruth, Question
from evaluation.costs import cost_per_accepted, money


def assess(
    record: dict[str, Any], truth: GroundTruth, review: dict[str, Any] | None = None
) -> dict[str, Any]:
    comparison = compare(record["response_text"], truth)
    errors = list(comparison.errors)
    executed = record["status"] == "completed"
    if not executed:
        errors.append(record.get("error_code") or "PLATFORM_ERROR")
    if review is not None:
        if review.get("record_sha256") != digest(record):
            raise ValueError("Review refers to different execution evidence")
        if not review.get("reviewer") or not review.get("rubric_sha256"):
            raise ValueError("Review must identify reviewer and rubric")
        if type(review.get("pass")) is not bool:
            raise ValueError("Review must explicitly pass or fail")
        if not review["pass"]:
            errors.extend(review.get("errors") or ["UNSUPPORTED_CLAIM"])
    deterministic_pass = executed and comparison.deterministic_pass
    # An automatic failure needs no human review to count as a failure.
    accepted = False if not deterministic_pass else (bool(review["pass"]) if review else None)
    return {
        "invocation_id": record["invocation_id"],
        "candidate_id": record["candidate_id"],
        "question_id": record["question_id"],
        "repetition": record["repetition"],
        "deterministic_pass": deterministic_pass,
        "accepted": accepted,
        "errors": sorted(set(errors)),
        "record_sha256": digest(record),
        "review_sha256": digest(review) if review else None,
        "comparator_version": "1.0.0",
    }


def nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(percentile * len(values)) - 1)]


def cluster_interval(
    rates: list[float], seed: int = 20260919, draws: int = 2000
) -> list[float] | None:
    if not rates:
        return None
    rng = random.Random(seed)
    samples = sorted(sum(rng.choice(rates) for _ in rates) / len(rates) for _ in range(draws))
    return [samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]]


def summarize(
    candidate: str,
    questions: list[Question],
    records: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    runtime_costs: dict[str, str | None],
) -> dict[str, Any]:
    expected = {(q.question_id, r) for q in questions for r in range(2)}
    invocations = [row for row in records if row["candidate_id"] == candidate]
    checks = [row for row in assessments if row["candidate_id"] == candidate]
    ids = [row["invocation_id"] for row in invocations]
    check_ids = [row["invocation_id"] for row in checks]
    if len(set(ids)) != len(ids) or len(set(check_ids)) != len(check_ids):
        raise ValueError("Duplicate execution/assessment in score input")
    if any(i not in ids for i in check_ids):
        raise ValueError("Assessment without invocation")
    by_id = {row["invocation_id"]: row for row in invocations}
    for check in checks:
        if check["record_sha256"] != digest(by_id[check["invocation_id"]]):
            raise ValueError("Assessment evidence hash mismatch")
    observed = {(row["question_id"], row["repetition"]) for row in invocations}
    if len(observed) != len(invocations) or not observed.issubset(expected):
        raise ValueError("Duplicate or unplanned invocation")
    complete = observed == expected and set(ids) == set(check_ids)
    complete = complete and all(row["accepted"] is not None for row in checks)
    by_question: dict[str, Any] = {}
    for q in questions:
        rows = sorted(
            (row for row in checks if row["question_id"] == q.question_id),
            key=lambda row: row["repetition"],
        )
        by_question[q.question_id] = {
            "accepted": sum(r["accepted"] is True for r in rows),
            "expected": 2,
            "repetitions": [r["accepted"] for r in rows],
            "critical": q.critical,
            "category": q.category,
            "difficulty": q.difficulty,
            "leakage_group_id": q.leakage_group_id,
        }
    accepted = sum(row["accepted"] is True for row in checks)
    latencies = [row["latency_ms"] for row in invocations]
    costs_complete = (
        all(
            identifier in runtime_costs and runtime_costs[identifier] is not None
            for identifier in ids
        )
        and observed == expected
    )
    total = Decimal(0)
    for identifier in ids:
        amount = runtime_costs.get(identifier)
        if amount is not None:
            total += money(amount)
    cpa = cost_per_accepted(total, accepted) if costs_complete else None
    groups: dict[str, list[float]] = {}
    for value in by_question.values():
        groups.setdefault(value["leakage_group_id"], []).append(value["accepted"] / 2)
    group_rates = [sum(v) / len(v) for v in groups.values()]
    breakdown: dict[str, dict[str, dict[str, int]]] = {}
    for field in ["category", "difficulty"]:
        breakdown[field] = {}
        for value in by_question.values():
            part = breakdown[field].setdefault(value[field], {"accepted": 0, "expected": 0})
            part["accepted"] += value["accepted"]
            part["expected"] += 2
    return {
        "candidate_id": candidate,
        "complete": complete,
        "costs_complete": costs_complete,
        "expected_invocations": len(expected),
        "attempted": len(invocations),
        "accepted": accepted,
        "acceptance_rate": accepted / len(expected) if expected else None,
        "robust_successes": sum(v["accepted"] == 2 for v in by_question.values()),
        "critical_accepted": sum(v["accepted"] for v in by_question.values() if v["critical"]),
        "critical_expected": sum(q.critical for q in questions) * 2,
        "per_question": by_question,
        "breakdown": breakdown,
        "latency_ms": {
            "median": median(latencies) if latencies else None,
            "p95": nearest_rank(latencies, 0.95),
            "maximum": max(latencies, default=None),
        },
        "timeout_count": sum(r["status"] == "timeout" for r in invocations),
        "runtime_cost_usd": str(total) if costs_complete else None,
        "runtime_cost_per_accepted_usd": str(cpa) if cpa is not None else None,
        "errors": dict(Counter(e for row in checks for e in row["errors"])),
        "exploratory_cluster_interval": cluster_interval(group_rates) if complete else None,
        "interval_warning": (
            "Descriptive cluster bootstrap; six questions cannot establish reliability"
        ),
    }
