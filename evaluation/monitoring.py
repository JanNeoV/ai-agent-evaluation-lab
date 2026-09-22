"""Bounded replay alerts, never automatic agent modification."""

from __future__ import annotations

from typing import Any


def incidents(
    metrics: dict[str, Any],
    expected_fingerprint: str,
    actual_fingerprint: str,
    budget_admitted: bool,
) -> list[dict[str, str]]:
    reasons = []
    if metrics["critical_accepted"] < metrics["critical_expected"]:
        reasons.append("critical_answer_failure")
    if expected_fingerprint != actual_fingerprint:
        reasons.append("deployment_changed")
    if metrics["expected_invocations"] - metrics["accepted"] >= 2:
        reasons.append("two_or_more_unsuccessful_requests")
    if metrics["latency_ms"]["p95"] is not None and metrics["latency_ms"]["p95"] > 90000:
        reasons.append("latency_gate_exceeded")
    if not budget_admitted or not metrics["costs_complete"]:
        reasons.append("budget_or_accounting_failure")
    return [
        {"reason": reason, "action": "suspend_or_route_to_previous_approved_release"}
        for reason in reasons
    ]
