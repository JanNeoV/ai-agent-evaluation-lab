import copy
import shutil
from decimal import Decimal

import pytest

from evaluation.artifacts import load_json
from evaluation.integrity import verify_batch
from evaluation.iterations import validate_intervention
from evaluation.reconciliation import reconcile_runtime


def test_cost_reconciliation_includes_idle_without_double_counting():
    records = [
        {"invocation_id": "a", "request_id": "r1", "latency_ms": 1000},
        {"invocation_id": "b", "request_id": "r2", "latency_ms": 3000},
    ]
    usage = [
        {"request_id": "r1", "component": "agent_token_credits", "usd": "0.02"},
        {"request_id": "r2", "component": "agent_token_credits", "usd": "0.03"},
    ]
    costs = reconcile_runtime(
        records,
        usage,
        "0.04",
        warehouse_attribution_review="fixture-review",
        rate_card_hash="0" * 64,
    )
    assert Decimal(costs["a"]["usd"]) == Decimal("0.03")
    assert sum(Decimal(row["usd"]) for row in costs.values()) == Decimal("0.09")
    usage.append(usage[0])
    with pytest.raises(ValueError, match="Duplicate"):
        reconcile_runtime(
            records, usage, "0.04", warehouse_attribution_review="review", rate_card_hash="0" * 64
        )


def test_unmatched_usage_and_extra_tool_cost_fail_closed():
    records = [{"invocation_id": "a", "request_id": "r", "latency_ms": 1000}]
    for usage in [
        [{"request_id": "r", "component": "analyst", "usd": "0.01"}],
        [{"request_id": "other", "component": "agent_token_credits", "usd": "0.01"}],
    ]:
        with pytest.raises(ValueError):
            reconcile_runtime(
                records,
                usage,
                "0.01",
                warehouse_attribution_review="review",
                rate_card_hash="0" * 64,
            )
    costs = reconcile_runtime(
        records, [], "0.01", warehouse_attribution_review="review", rate_card_hash="0" * 64
    )
    assert costs["a"]["usd"] is None
    assert costs["a"]["state"] == "unknown"


def test_all_submissions_and_raw_evidence_verify(completed_demo):
    assert verify_batch(completed_demo / "TEST") == {
        "planned": 36,
        "submitted": 36,
        "completed": 36,
        "unsubmitted": [],
        "ambiguous": [],
        "complete": True,
    }


def test_raw_response_tampering_is_detected(tmp_path, completed_demo):
    target = tmp_path / "copy"
    shutil.copytree(completed_demo / "TEST", target)
    raw = next((target / "raw").glob("*.json"))
    raw.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="Raw evidence"):
        verify_batch(target)


def test_intervention_boundaries_do_not_allow_silent_model_change():
    parent = {
        "candidate_id": "A0",
        "parent_id": None,
        "intervention": "cold_start",
        "instructions": {"response": "JSON"},
        "tools": [{"name": "sql", "description": "base"}],
        "semantic_sha256": "0" * 64,
        "model_bindings": [{"model": "same"}],
        "limits": {"seconds": 60, "tokens": 4096},
        "output_contract_sha256": "0" * 64,
    }
    candidate = copy.deepcopy(parent)
    candidate.update(
        candidate_id="A1", parent_id="A0", intervention="semantics", semantic_sha256="1" * 64
    )
    assert validate_intervention(parent, candidate) == ["semantic_sha256"]
    candidate["model_bindings"] = [{"model": "changed"}]
    with pytest.raises(ValueError, match="boundary"):
        validate_intervention(parent, candidate)


def test_configuration_stage_changes_exactly_one_factor():
    parent = {
        "candidate_id": "A2",
        "parent_id": "A1",
        "intervention": "instructions",
        "instructions": {},
        "tools": [],
        "semantic_sha256": "0" * 64,
        "model_bindings": [],
        "limits": {"seconds": 60, "tokens": 4096},
        "output_contract_sha256": "0" * 64,
    }
    candidate = copy.deepcopy(parent)
    candidate.update(candidate_id="A3", parent_id="A2", intervention="config")
    candidate["limits"] = {"seconds": 90, "tokens": 8192}
    with pytest.raises(ValueError, match="one factor"):
        validate_intervention(parent, candidate)


def test_saved_fixture_data_not_modified_by_demo(fixture_root, completed_demo):
    manifest = load_json(fixture_root / "manifest.json")
    from evaluation.artifacts import verify_files

    verify_files(fixture_root, manifest["files"])


def test_full_report_replays_from_saved_evidence(completed_demo, fixture_root, tmp_path):
    from evaluation.replay import replay_demo

    result = replay_demo(completed_demo, fixture_root, tmp_path / "report.md")
    assert result["report_identical"] is True
    assert result["model_invoked"] is False
    assert (tmp_path / "report.md").read_bytes() == (completed_demo / "test_report.md").read_bytes()


def test_monitoring_uses_twelve_scripted_calls(completed_demo):
    assert (
        sum(
            verify_batch(path)["completed"]
            for path in (completed_demo / "monitoring").glob("MONITOR-*")
        )
        == 12
    )
    incident = load_json(completed_demo / "monitoring" / "synthetic_incident.json")
    assert incident[0]["reason"] == "deployment_changed"
