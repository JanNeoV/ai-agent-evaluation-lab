"""Generate reports solely from saved assessments; no cloud calls."""

from __future__ import annotations

from typing import Any


def report(
    title: str, metrics: list[dict[str, Any]], decision: dict[str, Any], synthetic: bool
) -> str:
    lines = [f"# {title}", ""]
    if synthetic:
        lines.extend(
            [
                "**SYNTHETIC SOFTWARE REPLAY — no AI model was invoked.**",
                "Outcomes, costs and latencies are test inputs, not measured agent performance.",
                "",
            ]
        )
    lines.extend(
        [
            "| Candidate | Accepted | Robust questions | Critical | p95 ms | "
            "Runtime USD | USD/accepted |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for m in metrics:
        lines.append(
            f"| {m['candidate_id']} | {m['accepted']}/{m['expected_invocations']} | "
            f"{m['robust_successes']} | {m['critical_accepted']}/{m['critical_expected']} | "
            f"{m['latency_ms']['p95']} | {m['runtime_cost_usd']} | "
            f"{m['runtime_cost_per_accepted_usd']} |"
        )
    lines.extend(
        [
            "",
            f"Decision: **{decision['decision']}**; candidate: {decision.get('candidate_id')}",
            "",
            decision["reason"],
            "",
            "## Per-question repetitions",
            "",
        ]
    )
    for m in metrics:
        lines.extend(
            [
                f"### {m['candidate_id']}",
                "",
                "| Question | Repetitions | Critical | Category |",
                "|---|---|---|---|",
            ]
        )
        for q, row in sorted(m["per_question"].items()):
            lines.append(f"| {q} | {row['repetitions']} | {row['critical']} | {row['category']} |")
        lines.extend(
            [
                "",
                "Exploratory cluster interval: " + str(m["exploratory_cluster_interval"]),
                m["interval_warning"],
                "",
            ]
        )
    lines.extend(
        [
            "No independent blinding, national-population accuracy or causal intervention effect "
            "is established by this report.",
            "",
        ]
    )
    return "\n".join(lines)
