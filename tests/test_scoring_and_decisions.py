import copy

import pytest

from evaluation.artifacts import digest, load_json
from evaluation.contracts import Split
from evaluation.decisions import (
    baseline_metrics,
    holdout_decision,
    release_gates,
    select_candidate,
    train_decision,
)
from evaluation.scoring import assess, summarize


def test_synthetic_lifecycle_rejects_critical_regression(completed_demo):
    metrics = load_json(completed_demo / "TEST/metrics.json")
    selected = select_candidate(metrics)
    assert selected["candidate_id"] == "A1"
    assert not selected["gates"]["A2"]["critical"]
    assert load_json(completed_demo / "completed.json")["model_invoked"] is False
    assert "SYNTHETIC SOFTWARE REPLAY" in (completed_demo / "test_report.md").read_text()


def test_pending_human_review_is_not_acceptance(completed_demo, truths):
    row = load_json(next((completed_demo / "TEST/invocations").glob("A1-*.json")))
    check = assess(row, truths[row["question_id"]])
    assert check["deterministic_pass"] is True
    assert check["accepted"] is None
    with pytest.raises(ValueError, match="different"):
        assess(row, truths[row["question_id"]], {"record_sha256": "wrong"})


def test_human_disagreement_can_fail_numerically_correct_answer(completed_demo, truths):
    row = load_json(next((completed_demo / "TEST/invocations").glob("A1-*.json")))
    result = assess(
        row,
        truths[row["question_id"]],
        {
            "record_sha256": digest(row),
            "reviewer": "synthetic reviewer",
            "rubric_sha256": "0" * 64,
            "pass": False,
            "errors": ["UNSUPPORTED_CAUSAL_OR_POPULATION_CLAIM"],
        },
    )
    assert result["accepted"] is False
    assert result["deterministic_pass"] is True


def test_missing_cost_makes_selection_inconclusive(completed_demo):
    metrics = load_json(completed_demo / "TEST/metrics.json")
    metrics[0]["costs_complete"] = False
    assert select_candidate(metrics)["decision"] == "inconclusive"


def test_critical_failure_overrides_eleven_of_twelve(completed_demo):
    metric = copy.deepcopy(load_json(completed_demo / "TEST/metrics.json")[1])
    metric["accepted"] = 11
    metric["critical_accepted"] = 3
    assert release_gates(metric)["accuracy"] is True
    assert holdout_decision(metric)["decision"] == "rejected"


def test_baseline_robust_loss_blocks_even_if_total_increases(completed_demo):
    baseline, candidate, _ = load_json(completed_demo / "TEST/metrics.json")
    key = next(
        q for q, r in baseline["per_question"].items() if r["accepted"] == 2 and not r["critical"]
    )
    candidate["per_question"][key]["accepted"] = 1
    assert not release_gates(candidate, baseline)["no_baseline_robust_loss"]


def test_rejected_train_iteration_remains_in_ledger(completed_demo):
    train = load_json(completed_demo / "TRAIN/metrics.json")
    assert train_decision(train[0], train[1])["promoted"]
    result = train_decision(train[1], train[2])
    assert not result["promoted"]
    assert result["regressions"]


def test_missing_invocations_cannot_shrink_denominator(completed_demo, questions):
    records = [load_json(p) for p in (completed_demo / "TEST/invocations").glob("*.json")]
    checks = load_json(completed_demo / "TEST/assessments.json")
    removed = next(r for r in records if r["candidate_id"] == "A1")
    records.remove(removed)
    checks = [r for r in checks if r["invocation_id"] != removed["invocation_id"]]
    metrics = summarize(
        "A1",
        [q for q in questions if q.split == Split.TEST],
        records,
        checks,
        {r["invocation_id"]: "0.01" for r in records},
    )
    assert metrics["expected_invocations"] == 12
    assert metrics["attempted"] == 11
    assert metrics["complete"] is False
    assert holdout_decision(metrics)["decision"] == "inconclusive"


def test_duplicate_repetitions_are_rejected(completed_demo, questions):
    records = [load_json(p) for p in (completed_demo / "TEST/invocations").glob("A1-*.json")]
    checks = load_json(completed_demo / "TEST/assessments.json")
    records.append(records[0])
    with pytest.raises(ValueError, match="Duplicate"):
        summarize("A1", [q for q in questions if q.split == Split.TEST], records, checks, {})


def _relabel(metrics, mapping):
    relabelled = copy.deepcopy(metrics)
    for row in relabelled:
        row["candidate_id"] = mapping[row["candidate_id"]]
    return relabelled


def test_r1_recognizes_v0_as_the_sealed_baseline(completed_demo):
    """ADR-0004: the selection rule is unchanged apart from recognizing V0 as baseline."""
    metrics = load_json(completed_demo / "TEST/metrics.json")
    r1 = _relabel(metrics, {"A0": "V0", "A1": "V1", "A2": "V2"})
    r1.append({**copy.deepcopy(r1[0]), "candidate_id": "V3"})
    assert baseline_metrics(r1)["candidate_id"] == "V0"
    assert select_candidate(r1)["candidate_id"] == "V1"


def test_baseline_is_required_and_never_guessed(completed_demo):
    metrics = load_json(completed_demo / "TEST/metrics.json")
    with pytest.raises(ValueError, match="baseline"):
        baseline_metrics(_relabel(metrics, {"A0": "V1", "A1": "V2", "A2": "V3"}))
    partial = _relabel(metrics, {"A0": "V0", "A1": "V1", "A2": "V2"})
    with pytest.raises(ValueError, match="baseline"):
        baseline_metrics(partial)
