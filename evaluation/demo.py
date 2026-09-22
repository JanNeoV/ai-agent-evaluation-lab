"""Full local lifecycle using visibly synthetic response fixtures, never an AI agent."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from evaluation.artifacts import digest, file_hash, load_json, write_once
from evaluation.contracts import (
    GroundTruth,
    InvocationRequest,
    InvocationResult,
    Question,
    Split,
    UsageRecord,
)
from evaluation.costs import Budget, Quote
from evaluation.decisions import holdout_decision, select_candidate, train_decision
from evaluation.monitoring import incidents
from evaluation.oracle import verify_release
from evaluation.reporting import report
from evaluation.runner import run_batch, schedule
from evaluation.scoring import assess, summarize
from evaluation.sealing import Campaign


class SyntheticReplay:
    def __init__(self, questions: list[Question], truths: dict[str, GroundTruth]):
        if any(q.origin != "synthetic_fixture" for q in questions):
            raise ValueError("Replay adapter accepts labeled synthetic fixtures only")
        self.questions = {q.text: q for q in questions}
        self.truths = truths

    def probe(self) -> dict[str, Any]:
        return {"synthetic": True, "model_invoked": False}

    def deploy(self, bundle: dict[str, Any]) -> dict[str, Any]:
        return {"synthetic": True, "bundle_sha256": digest(bundle)}

    def verify(self, deployment: dict[str, Any]) -> dict[str, Any]:
        return {"verified": deployment.get("deployment_ref", "").startswith("synthetic:")}

    def estimate(self, batch: dict[str, Any]) -> dict[str, Any]:
        return {"synthetic": True, "usd": str(Decimal("0.01") * batch["invocation_count"])}

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        q = self.questions[request.question_text]
        answer = copy.deepcopy(self.truths[q.question_id].expected)
        # Deliberate software test inputs, not purported model behavior.
        if request.candidate_id == "A0" and q.category in {"aggregation", "ranking_ratio"}:
            answer["rows"] = []
        if request.candidate_id == "A2" and q.category == "missingness" and request.repetition == 1:
            answer["status"] = "clarification_needed"
        raw = {"synthetic_fixture": True, "model_invoked": False, "answer": answer}
        return InvocationResult(
            "completed",
            json.dumps(answer, ensure_ascii=False),
            1000,
            f"SYNTHETIC-{request.invocation_id}",
            raw,
        )

    def collect_usage(self, batch: dict[str, Any]) -> list[UsageRecord]:
        return [
            UsageRecord(
                batch["batch_id"],
                "synthetic_not_billed",
                Decimal("0"),
                Decimal("0"),
                "final",
                "software_fixture",
                None,
            )
        ]

    def export_trace(self, invocation: dict[str, Any]) -> dict[str, Any]:
        return {"synthetic": True, "invocation_id": invocation["invocation_id"]}


def run_demo(fixture: Path, output: Path) -> dict[str, Any]:
    integrity = verify_release(fixture, allow_synthetic=True)
    if integrity["classification"] != "synthetic_fixture":
        raise ValueError("Demo must never consume real data")
    if output.exists():
        raise ValueError("Use a fresh output directory; completed demo evidence is immutable")
    questions = [Question.from_dict(row) for row in load_json(fixture / "questions.json")]
    truths = {
        row["question_id"]: GroundTruth.from_dict(row)
        for row in load_json(fixture / "ground_truth.json")
    }
    adapter = SyntheticReplay(questions, truths)
    budget = Budget(output / "usage" / "budget.jsonl")
    campaign = Campaign(output / "campaign")
    campaign.initialize(
        {
            "classification": "synthetic_fixture",
            "repetitions": 2,
            "automatic_retries": 0,
            "benchmark_manifest": digest(load_json(fixture / "manifest.json")),
        }
    )
    deployments = {
        name: {"deployment_ref": f"synthetic:{name}", "parent": parent}
        for name, parent in [("A0", None), ("A1", "A0"), ("A2", "A1")]
    }
    rubric_hash = digest("synthetic reviewer stub, never human validation")

    def batch(
        split: Split, refs: dict[str, dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        selected = [q for q in questions if q.split == split]
        plan = schedule(selected, list(refs), 20260919)
        now = datetime.now(UTC)
        quote = Quote(
            split.value,
            len(plan),
            Decimal("0.01"),
            Decimal(0),
            Decimal(0),
            Decimal("1.25"),
            digest("synthetic rates; not billed"),
        )
        budget.admit(quote, Decimal(10), now, now + timedelta(days=1))
        rows = run_batch(
            output / split.value,
            adapter,
            selected,
            refs,
            plan,
            budget,
            split.value,
            campaign if split != Split.TRAIN else None,
            synthetic=True,
        )
        if split == Split.TEST:
            campaign.transition("TEST_COMPLETE", "TEST_REVEALED")
        if split != Split.TRAIN:
            campaign.authorize(split, "review")
        reviews = {
            row["invocation_id"]: {
                "record_sha256": digest(row),
                "reviewer": "synthetic_fixture_stub",
                "rubric_sha256": rubric_hash,
                "pass": True,
            }
            for row in rows
        }
        assessments = [
            assess(row, truths[row["question_id"]], reviews[row["invocation_id"]]) for row in rows
        ]
        costs: dict[str, str | None] = {row["invocation_id"]: "0.01" for row in rows}
        metrics = [summarize(name, selected, rows, assessments, costs) for name in refs]
        write_once(output / split.value / "assessments.json", assessments)
        write_once(output / split.value / "metrics.json", metrics)
        write_once(output / split.value / "reviews.json", reviews)
        write_once(output / split.value / "runtime_costs.json", costs)
        budget.settle(split.value, Decimal("0.01") * len(rows), digest(costs))
        return metrics, rows

    train, _ = batch(Split.TRAIN, deployments)
    write_once(
        output / "TRAIN" / "promotion.json",
        [train_decision(train[0], train[1]), train_decision(train[1], train[2])],
    )
    test_questions = [q for q in questions if q.split == Split.TEST]
    campaign.seal(deployments, schedule(test_questions, list(deployments), 20260919))
    test, _ = batch(Split.TEST, deployments)
    selected = select_candidate(test)
    campaign.select(selected)
    write_once(output / "TEST" / "decision.json", selected)
    (output / "test_report.md").write_text(
        report("Synthetic lifecycle replay", test, selected, True), encoding="utf-8", newline="\n"
    )
    final: dict[str, Any] = {"decision": "rejected", "candidate_id": None}
    if selected["candidate_id"]:
        rc = selected["candidate_id"]
        holdout, _ = batch(Split.HOLDOUT, {rc: deployments[rc]})
        final = holdout_decision(holdout[0])
        write_once(output / "HOLDOUT" / "decision.json", final)
        campaign.transition("HOLDOUT_COMPLETE", "CLOSED", decision_sha256=digest(final))
        monitoring_questions = [q for q in questions if q.split == Split.TRAIN][::2]
        for batch_index in range(2):
            batch_id = f"MONITOR-{batch_index}"
            monitor_questions = monitoring_questions[batch_index * 3 : (batch_index + 1) * 3]
            monitor_plan = schedule(monitor_questions, [rc], 20260919 + batch_index)
            now = datetime.now(UTC)
            budget.admit(
                Quote(
                    batch_id,
                    6,
                    Decimal("0.01"),
                    Decimal(0),
                    Decimal(0),
                    Decimal("1.25"),
                    digest("synthetic rates; not billed"),
                ),
                Decimal(10),
                now,
                now + timedelta(days=1),
            )
            monitor_rows = run_batch(
                output / "monitoring" / batch_id,
                adapter,
                monitor_questions,
                {rc: deployments[rc]},
                monitor_plan,
                budget,
                batch_id,
                synthetic=True,
            )
            monitor_reviews = {
                row["invocation_id"]: {
                    "record_sha256": digest(row),
                    "reviewer": "synthetic_fixture_stub",
                    "rubric_sha256": rubric_hash,
                    "pass": True,
                }
                for row in monitor_rows
            }
            monitor_checks = [
                assess(row, truths[row["question_id"]], monitor_reviews[row["invocation_id"]])
                for row in monitor_rows
            ]
            monitor_costs: dict[str, str | None] = {
                row["invocation_id"]: "0.01" for row in monitor_rows
            }
            monitor_metric = summarize(
                rc, monitor_questions, monitor_rows, monitor_checks, monitor_costs
            )
            write_once(output / "monitoring" / batch_id / "metrics.json", monitor_metric)
            write_once(output / "monitoring" / batch_id / "assessments.json", monitor_checks)
            write_once(output / "monitoring" / batch_id / "reviews.json", monitor_reviews)
            write_once(output / "monitoring" / batch_id / "runtime_costs.json", monitor_costs)
            budget.settle(batch_id, Decimal("0.06"), digest(monitor_costs))
            write_once(
                output / "monitoring" / batch_id / "incidents.json",
                incidents(monitor_metric, "approved_fixture", "approved_fixture", True),
            )
        write_once(
            output / "monitoring" / "synthetic_incident.json",
            incidents(monitor_metric, "approved_fixture", "changed_fixture", True),
        )
    complete = {
        "classification": "synthetic_fixture",
        "model_invoked": False,
        "cash_spend": "0",
        "trial_credits_consumed": "0",
        "integrity": integrity,
        "planned_primary_invocations": 120,
        "planned_monitoring_invocations": 12,
        "test_candidate": selected["candidate_id"],
        "fixture_release_decision": final["decision"],
        "state": campaign.state(),
        "artifact_hashes": {
            path.relative_to(output).as_posix(): file_hash(path)
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
    }
    write_once(output / "completed.json", complete)
    return complete
