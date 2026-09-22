import json

import pytest

from evaluation.artifacts import digest, load_json
from evaluation.contracts import InvocationRequest, Split
from platforms.snowflake.adapter import SnowflakeAdapter, split_reference
from platforms.snowflake.deployment import create_agent_sql, render_bundle
from platforms.snowflake.native_evaluations import dataset_sql, evaluation_config, native_rows


class Transport:
    def __init__(self, response=None, exception=None):
        self.response = response
        self.exception = exception
        self.calls = []

    def query(self, sql, parameters=()):
        self.calls.append((sql, parameters))
        if self.exception:
            raise self.exception
        return [{"response": self.response}]


class FingerprintTransport:
    def __init__(self):
        self.calls = []

    def query(self, sql, parameters=()):
        self.calls.append((sql, parameters))
        if sql.startswith("SHOW VERSIONS"):
            return [
                {
                    "name": "VERSION$1",
                    "spec_file_path": "snow://agent/versions/version$1/",
                    "is_default": "true",
                    "comment": None,
                    "agent_spec": json.dumps({"models": {"orchestration": "model"}}),
                }
            ]
        if sql.startswith("LIST "):
            return [{"name": "/versions/version$1/agent_spec.yaml", "size": 10, "md5": "abc"}]
        if "GET_DDL('SEMANTIC_VIEW'" in sql:
            raise RuntimeError("GET_DDL is unsupported")
        if sql.startswith("DESCRIBE SEMANTIC VIEW"):
            return [{"property": "COMMENT", "property_value": "synthetic"}]
        if sql.startswith("SELECT * FROM"):
            return [{"id": 1}]
        if sql.startswith("SELECT CURRENT_ROLE"):
            return [{"role": "LAB_RUNTIME"}]
        if sql.startswith("SHOW GRANTS"):
            return [{"created_on": "now", "privilege": "SELECT", "name": "TABLE"}]
        raise AssertionError(f"Unexpected SQL: {sql}")


def request():
    return InvocationRequest(
        "A1-Q1-R0",
        "A1",
        "AGENT_LAB.AGENTS.BENCHMARK_AGENT!VERSION$2",
        "Wie viele Ereignisjahre?",
        0,
    )


@pytest.mark.parametrize("version", ["LIVE", "LAST", "FIRST", "DEFAULT", "production", "VERSION$0"])
def test_mutable_aliases_forbidden_for_evaluation(version):
    with pytest.raises(ValueError):
        split_reference(f"DB.SCHEMA.AGENT!{version}")


def test_invocation_uses_named_version_and_fresh_history():
    transport = Transport(
        {"content": [{"type": "text", "text": "{}"}], "metadata": {"run_id": "r1"}}
    )
    result = SnowflakeAdapter(transport).invoke(request())
    sql, params = transport.calls[0]
    assert "DATA_AGENT_RUN(%s, %s)" in sql
    assert params[0].endswith("!VERSION$2")
    payload = json.loads(params[1])
    assert set(payload) == {"messages"}
    assert len(payload["messages"]) == 1
    assert result.request_id == "r1"


def test_timeout_has_no_retry_or_secret_in_error():
    transport = Transport(exception=TimeoutError("secret password"))
    result = SnowflakeAdapter(transport).invoke(request())
    assert result.status == "timeout"
    assert len(transport.calls) == 1
    assert "secret" not in str(result)


def test_server_error_cannot_be_scored_as_completed():
    transport = Transport({"status": "error", "error": {"code": "bad"}, "content": []})
    assert SnowflakeAdapter(transport).invoke(request()).status == "error"


def test_provider_error_envelope_cannot_be_scored_as_completed():
    transport = Transport(
        {"code": "399504", "message": "Access denied for trial accounts.", "request_id": "r1"}
    )
    result = SnowflakeAdapter(transport).invoke(request())
    assert result.status == "error"
    assert result.error_code == "399504"


def test_dependency_fingerprint_must_match():
    adapter = SnowflakeAdapter(Transport(), lambda _: {"data": "changed"})
    deployment = {
        "deployment_ref": request().deployment_ref,
        "fingerprint_sha256": digest({"data": "original"}),
    }
    assert adapter.verify(deployment)["verified"] is False


def test_fingerprint_records_model_and_describe_fallback():
    transport = FingerprintTransport()
    deployment = {
        "deployment_ref": "AGENT_LAB.AGENTS.BENCHMARK_AGENT!VERSION$1",
        "semantic_view": "AGENT_LAB.SEMANTICS.SV_BASELINE",
        "tables": ["AGENT_LAB.BENCHMARK_R1.EVENT"],
    }
    observed = SnowflakeAdapter(transport).capture_fingerprint(deployment)
    assert observed["agent_version"]["requested"] == "VERSION$1"
    assert observed["requested_model"] == "model"
    assert observed["semantic_definition"]["source"] == "DESCRIBE SEMANTIC VIEW"
    assert observed["native_files"][0]["md5"] == "abc"


SEALED_SPEC = {
    "models": {"orchestration": "claude-haiku-4-5"},
    "instructions": {"response": "JSON", "orchestration": "tool"},
    "tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "benchmark_analyst"}}],
    "tool_resources": {"benchmark_analyst": {"semantic_view": "AGENT_LAB.SEMANTICS.SV_X"}},
}


class SealedSpecTransport:
    def __init__(self, spec=None, role="LAB_RUNTIME"):
        self.spec = SEALED_SPEC if spec is None else spec
        self.role = role

    def query(self, sql, parameters=()):
        if sql.startswith("SHOW VERSIONS"):
            return [{"name": "VERSION$2", "agent_spec": json.dumps(self.spec)}]
        if sql.startswith("LIST "):
            return [{"name": "/versions/version$2/spec.yaml", "size": 10, "md5": "abc"}]
        if sql.startswith("SELECT CURRENT_ROLE"):
            return [{"role": self.role}]
        raise AssertionError(f"Unexpected SQL: {sql}")


def sealed_candidate():
    return {
        "candidate_id": "V0",
        "deployment_ref": "AGENT_LAB.AGENTS.BENCHMARK_AGENT_R1_RECOVERED!VERSION$2",
        "spec_canonical_hash": digest(SEALED_SPEC),
        "instructions_hash": digest(SEALED_SPEC["instructions"]),
        "tools_hash": digest(SEALED_SPEC["tools"]),
        "tool_resources_hash": digest(SEALED_SPEC["tool_resources"]),
        "semantic_view": "AGENT_LAB.SEMANTICS.SV_X",
        "model": "claude-haiku-4-5",
        "permissions": {"role": "LAB_RUNTIME", "warehouse": "LAB_XS"},
    }


def test_sealed_r1_candidate_verifies_every_component():
    result = SnowflakeAdapter(SealedSpecTransport()).verify(sealed_candidate())
    assert result["verified"] is True
    assert result["verification"] == "sealed_specification_components"
    assert all(result["checks"].values())


@pytest.mark.parametrize(
    "field", ["spec_canonical_hash", "instructions_hash", "tools_hash", "tool_resources_hash"]
)
def test_sealed_r1_candidate_fails_closed_on_any_changed_hash(field):
    deployment = {**sealed_candidate(), field: "0" * 64}
    result = SnowflakeAdapter(SealedSpecTransport()).verify(deployment)
    assert result["verified"] is False
    assert result["checks"][field] is False


def test_sealed_r1_candidate_requires_the_sealed_execution_role():
    adapter = SnowflakeAdapter(SealedSpecTransport(role="ACCOUNTADMIN"))
    assert adapter.verify(sealed_candidate())["verified"] is False


def test_sealed_r1_candidate_rejects_a_swapped_semantic_view():
    spec = json.loads(json.dumps(SEALED_SPEC))
    spec["tool_resources"]["benchmark_analyst"]["semantic_view"] = "AGENT_LAB.SEMANTICS.SV_OTHER"
    result = SnowflakeAdapter(SealedSpecTransport(spec)).verify(sealed_candidate())
    assert result["verified"] is False


def test_baseline_bundle_still_uses_the_dependency_fingerprint():
    adapter = SnowflakeAdapter(Transport(), lambda _: {"data": "changed"})
    deployment = {
        "deployment_ref": request().deployment_ref,
        "fingerprint_sha256": digest({"data": "original"}),
        "spec_canonical_hash": digest(SEALED_SPEC),
    }
    assert adapter.verify(deployment)["verified"] is False
    assert "checks" not in adapter.verify(deployment)


def test_generated_sql_does_not_replace_frozen_objects(fixture_root):
    bundle = render_bundle(
        "AGENT_LAB", "BENCHMARK_R1", load_json(fixture_root / "data.json"), "explicit-test-model"
    )
    all_sql = "\n".join(bundle["tables"] + bundle["semantic_views"])
    assert "OR REPLACE" not in all_sql
    assert "NULL" in all_sql
    assert (
        bundle["candidates"]["A0"]["semantic_view"] != bundle["candidates"]["A1"]["semantic_view"]
    )
    assert (
        bundle["candidates"]["A0"]["spec"]["instructions"]
        == bundle["candidates"]["A1"]["spec"]["instructions"]
    )
    assert (
        bundle["candidates"]["A1"]["spec"]["models"] == bundle["candidates"]["A2"]["spec"]["models"]
    )
    assert bundle["candidates"]["A0"]["spec"]["tool_resources"]["benchmark_analyst"][
        "execution_environment"
    ] == {"type": "warehouse", "warehouse": "LAB_XS"}
    assert "CREATE AGENT" in create_agent_sql(
        "AGENT_LAB.AGENTS.BENCHMARK_AGENT", bundle["candidates"]["A0"]["spec"]
    )


def test_sql_identifier_injection_rejected(fixture_root):
    with pytest.raises(ValueError):
        render_bundle("DB;DROP DATABASE X", "S", load_json(fixture_root / "data.json"), "model")

    with pytest.raises(ValueError):
        render_bundle(
            "DB",
            "S",
            load_json(fixture_root / "data.json"),
            "model",
            warehouse="LAB_XS;DROP WAREHOUSE X",
        )


def test_native_dataset_is_train_only_and_uses_correct_mapping(questions, truths):
    train = [q for q in questions if q.split == Split.TRAIN][:3]
    rows = native_rows(train, truths)
    statements = dataset_sql("AGENT_LAB.EVAL_NATIVE.INPUTS", "AGENT_LAB.EVAL_NATIVE.DS", rows)
    assert "'expected_tools', 'GROUND_TRUTH'" in statements[-1]
    assert "PARSE_JSON(" in statements[1]
    with pytest.raises(ValueError):
        native_rows([q for q in questions if q.split == Split.TEST][:1], truths)


def test_native_judge_exact_version_and_no_dataset_recreation():
    config = evaluation_config(request().deployment_ref, "AGENT_LAB.EVAL_NATIVE.DS", "v3_0")
    assert "dataset" not in config
    assert config["metrics"][0]["version"] == "v3_0"
    with pytest.raises(ValueError):
        evaluation_config(request().deployment_ref, "AGENT_LAB.EVAL_NATIVE.DS", "auto")
