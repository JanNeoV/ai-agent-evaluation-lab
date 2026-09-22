"""Predeclared vector gates and deterministic candidate selection."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from evaluation.artifacts import digest, utc_now

POLICY = {
    "version": "1.0.0",
    "min_accepted": 10,
    "expected_invocations": 12,
    "critical_expected": 4,
    "max_p95_ms": 90000,
    "max_cost_per_accepted_usd": "0.10",
    "train_cost_improvement": "0.15",
    "train_max_noncritical_robust_losses": 1,
}


def regressions(parent: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    if set(parent["per_question"]) != set(candidate["per_question"]):
        raise ValueError("Cannot compare different question sets")
    return [
        q
        for q, row in parent["per_question"].items()
        if candidate["per_question"][q]["accepted"] < row["accepted"]
    ]


def operational_gates(metrics: dict[str, Any]) -> dict[str, bool]:
    latency = metrics["latency_ms"]["p95"]
    cost = metrics["runtime_cost_per_accepted_usd"]
    return {
        "complete": bool(metrics["complete"]),
        "costs_complete": bool(metrics["costs_complete"]),
        "latency": latency is not None and latency <= POLICY["max_p95_ms"],
        "cost": cost is not None
        and Decimal(cost) <= Decimal(str(POLICY["max_cost_per_accepted_usd"])),
    }


def train_decision(parent: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    losses = regressions(parent, candidate)
    critical_loss = any(parent["per_question"][q]["critical"] for q in losses)
    robust_losses = sum(
        parent["per_question"][q]["accepted"] == 2 and not parent["per_question"][q]["critical"]
        for q in losses
    )
    gates = operational_gates(candidate)
    gates.update(
        {
            "no_critical_regression": not critical_loss,
            "bounded_robust_losses": robust_losses <= 1,
            "no_aggregate_regression": candidate["accepted"] >= parent["accepted"],
        }
    )
    quality_improvement = candidate["robust_successes"] > parent["robust_successes"]
    previous_cost = parent["runtime_cost_per_accepted_usd"]
    new_cost = candidate["runtime_cost_per_accepted_usd"]
    cost_improvement = (
        previous_cost is not None
        and new_cost is not None
        and Decimal(previous_cost) > 0
        and Decimal(new_cost) <= Decimal(previous_cost) * Decimal("0.85")
        and candidate["robust_successes"] >= parent["robust_successes"]
    )
    gates["material_improvement"] = quality_improvement or cost_improvement
    return {
        "promoted": all(gates.values()),
        "gates": gates,
        "regressions": losses,
        "policy_sha256": digest(POLICY),
    }


def release_gates(
    metrics: dict[str, Any], baseline: dict[str, Any] | None = None
) -> dict[str, bool]:
    gates = operational_gates(metrics)
    gates.update(
        {
            "full_denominator": metrics["expected_invocations"] == 12,
            "accuracy": metrics["accepted"] >= 10,
            "critical": metrics["critical_expected"] == 4 and metrics["critical_accepted"] == 4,
        }
    )
    if baseline is not None:
        losses = regressions(baseline, metrics)
        gates["no_baseline_critical_regression"] = not any(
            baseline["per_question"][q]["critical"] for q in losses
        )
        gates["no_baseline_robust_loss"] = not any(
            baseline["per_question"][q]["accepted"] == 2 for q in losses
        )
    return gates


def baseline_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the sealed baseline candidate for a TEST comparison.

    ADR-0004: the TEST selection rule and the one-candidate HOLDOUT gate are unchanged
    "apart from recognizing `V0` as the baseline identifier". `A0` remains the baseline for
    the frozen synthetic campaign; Benchmark R1 seals exactly {V0, V1, V2, V3} with the
    cold-start candidate `V0` as its baseline. No other candidate set has a baseline.
    """
    identifiers = {m["candidate_id"] for m in metrics}
    for baseline in ["A0", "V0"]:
        if baseline in identifiers:
            if baseline == "V0" and identifiers != {"V0", "V1", "V2", "V3"}:
                break
            return next(m for m in metrics if m["candidate_id"] == baseline)
    raise ValueError("TEST selection requires the sealed A0 or R1 V0 baseline")


def select_candidate(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if len({m["candidate_id"] for m in metrics}) != len(metrics):
        raise ValueError("Duplicate candidate metrics")
    baseline = baseline_metrics(metrics)
    if any(not m["complete"] or not m["costs_complete"] for m in metrics):
        return decision(None, "inconclusive", {}, metrics, "Incomplete evidence; no selection")
    gates = {m["candidate_id"]: release_gates(m, baseline) for m in metrics}
    eligible = [m for m in metrics if all(gates[m["candidate_id"]].values())]
    if not eligible:
        return decision(None, "rejected", gates, metrics, "No candidate passed TEST gates")
    chosen = min(
        eligible,
        key=lambda m: (
            -m["robust_successes"],
            -m["accepted"],
            Decimal(m["runtime_cost_per_accepted_usd"]),
            m["latency_ms"]["median"],
            m["candidate_id"],
        ),
    )
    return decision(
        chosen["candidate_id"],
        "accepted",
        gates,
        metrics,
        "Selected by frozen lexicographic rule; requires HOLDOUT",
    )


def holdout_decision(metrics: dict[str, Any]) -> dict[str, Any]:
    gates = release_gates(metrics)
    status = "accepted" if all(gates.values()) else "rejected"
    if not metrics["complete"] or not metrics["costs_complete"]:
        status = "inconclusive"
    return decision(
        metrics["candidate_id"],
        status,
        gates,
        metrics,
        "One-candidate HOLDOUT; no alternative candidate may be tried",
    )


def decision(
    candidate: str | None, status: str, gates: dict[str, Any], metrics: Any, reason: str
) -> dict[str, Any]:
    return {
        "candidate_id": candidate,
        "predecessor": None,
        "policy_sha256": digest(POLICY),
        "metrics_sha256": digest(metrics),
        "gates": gates,
        "decision": status,
        "reason": reason,
        "recorded_at": utc_now(),
    }
