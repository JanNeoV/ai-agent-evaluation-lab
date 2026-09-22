"""Re-grade saved responses and rebuild metrics without a model or platform connection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.artifacts import digest, load_json, verify_files
from evaluation.contracts import GroundTruth, Question, Split
from evaluation.decisions import select_candidate
from evaluation.integrity import verify_batch
from evaluation.oracle import verify_release
from evaluation.reporting import report
from evaluation.scoring import assess, summarize


def replay_demo(evidence: Path, fixture: Path, report_output: Path) -> dict[str, Any]:
    complete = load_json(evidence / "completed.json")
    if complete.get("classification") != "synthetic_fixture" or complete.get("model_invoked"):
        raise ValueError("This replay command accepts completed synthetic packages only")
    verify_files(evidence, complete["artifact_hashes"])
    verify_release(fixture, allow_synthetic=True)
    if (
        digest(load_json(fixture / "manifest.json"))
        != load_json(evidence / "campaign" / "protocol.json")["benchmark_manifest"]
    ):
        raise ValueError("Replay benchmark is different from the frozen input")
    questions = [Question.from_dict(row) for row in load_json(fixture / "questions.json")]
    truths = {
        row["question_id"]: GroundTruth.from_dict(row)
        for row in load_json(fixture / "ground_truth.json")
    }
    checksums: dict[str, Any] = {}
    test_metrics = []
    for split in Split:
        root = evidence / split.value
        accounting = verify_batch(root)
        if not accounting["complete"]:
            raise ValueError("Cannot replay incomplete primary experiment")
        records = [load_json(path) for path in sorted((root / "invocations").glob("*.json"))]
        reviews = load_json(root / "reviews.json")
        checks = [
            assess(row, truths[row["question_id"]], reviews.get(row["invocation_id"]))
            for row in records
        ]
        saved_checks = load_json(root / "assessments.json")
        if sorted(checks, key=lambda x: x["invocation_id"]) != sorted(
            saved_checks, key=lambda x: x["invocation_id"]
        ):
            raise ValueError("Recomputed assessments differ from the frozen evidence")
        metrics = [
            summarize(
                candidate,
                [q for q in questions if q.split == split],
                records,
                checks,
                load_json(root / "runtime_costs.json"),
            )
            for candidate in sorted({r["candidate_id"] for r in records})
        ]
        if metrics != load_json(root / "metrics.json"):
            raise ValueError("Recomputed metrics differ from saved metrics")
        checksums[split.value] = accounting
        if split == Split.TEST:
            test_metrics = metrics
    decision = select_candidate(test_metrics)
    saved_decision = load_json(evidence / "TEST/decision.json")
    if {k: v for k, v in decision.items() if k != "recorded_at"} != {
        k: v for k, v in saved_decision.items() if k != "recorded_at"
    }:
        raise ValueError("Recomputed decision differs")
    text = report("Synthetic lifecycle replay", test_metrics, saved_decision, True)
    if text != (evidence / "test_report.md").read_text(encoding="utf-8"):
        raise ValueError("Report does not reproduce")
    report_output.parent.mkdir(parents=True, exist_ok=True)
    with report_output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return {
        "recomputed": checksums,
        "report_identical": True,
        "model_invoked": False,
        "output": str(report_output),
    }
