from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from evaluation.artifacts import Ledger, load_json
from evaluation.contracts import Split
from evaluation.costs import Budget, Quote
from evaluation.demo import SyntheticReplay
from evaluation.runner import run_batch, schedule


def prepare(tmp_path, questions, truths):
    questions = [q for q in questions if q.split == Split.TRAIN][:2]
    adapter = SyntheticReplay(questions, truths)
    refs = {"A1": {"deployment_ref": "synthetic:A1"}}
    plan = schedule(questions, ["A1"], 7)
    budget = Budget(tmp_path / "budget.jsonl")
    now = datetime.now(UTC)
    budget.admit(
        Quote("B", len(plan), Decimal("0.01"), Decimal(0), Decimal(0), Decimal(1), "0" * 64),
        Decimal(10),
        now,
        now + timedelta(days=1),
    )
    return questions, adapter, refs, plan, budget


def test_runner_never_passes_ground_truth_to_adapter(tmp_path, questions, truths):
    qs, adapter, refs, plan, budget = prepare(tmp_path, questions, truths)
    original = adapter.invoke
    seen = []

    def invoke(request):
        seen.append(request)
        assert not hasattr(request, "ground_truth")
        assert not hasattr(request, "split")
        return original(request)

    adapter.invoke = invoke
    records = run_batch(tmp_path / "batch", adapter, qs, refs, plan, budget, "B", synthetic=True)
    assert len(records) == len(seen) == 4
    # Resume never re-invokes completed submissions.
    assert (
        run_batch(tmp_path / "batch", adapter, qs, refs, plan, budget, "B", synthetic=True)
        == records
    )
    assert len(seen) == 4


def test_ambiguous_submission_is_not_retried(tmp_path, questions, truths):
    qs, adapter, refs, plan, budget = prepare(tmp_path, questions, truths)

    def crash(request):
        raise RuntimeError("Simulated process failure after request may have been sent")

    adapter.invoke = crash
    with pytest.raises(RuntimeError):
        run_batch(tmp_path / "batch", adapter, qs, refs, plan, budget, "B", synthetic=True)
    with pytest.raises(ValueError, match="Ambiguous"):
        run_batch(tmp_path / "batch", adapter, qs, refs, plan, budget, "B", synthetic=True)
    assert (
        sum(e["kind"] == "submitted" for e in Ledger(tmp_path / "batch/events.jsonl").read()) == 1
    )


def test_real_batch_requires_campaign_before_any_invocation(tmp_path, questions, truths):
    qs, adapter, refs, plan, budget = prepare(tmp_path, questions, truths)
    with pytest.raises(ValueError, match="campaign"):
        run_batch(tmp_path / "batch", adapter, qs, refs, plan, budget, "B")


def test_unbalanced_schedule_and_wrong_budget_are_rejected(tmp_path, questions, truths):
    qs, adapter, refs, plan, budget = prepare(tmp_path, questions, truths)
    with pytest.raises(ValueError, match="Unbalanced"):
        run_batch(tmp_path / "batch", adapter, qs, refs, plan[:-1], budget, "B", synthetic=True)
    with pytest.raises(ValueError, match="reservation"):
        run_batch(tmp_path / "batch", adapter, qs, refs, plan, budget, "OTHER", synthetic=True)


def test_saved_output_matches_preassigned_schedule(completed_demo):
    plan = load_json(completed_demo / "TEST/schedule.json")
    actual = [load_json(p) for p in (completed_demo / "TEST/invocations").glob("*.json")]
    assert {r["invocation_id"] for r in plan} == {r["invocation_id"] for r in actual}
    assert len(plan) == 36
