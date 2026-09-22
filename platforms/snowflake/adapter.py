"""SQL transport for Cortex Agents, with explicit versions and no retries."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from evaluation.artifacts import digest
from evaluation.contracts import InvocationRequest, InvocationResult, UsageRecord
from platforms.snowflake.deployment import identifier, qualified


class SQLTransport(Protocol):
    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]: ...


class ConnectorTransport:
    def __init__(self, connection: Any):
        self.connection = connection

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, parameters or None)
            names = [str(col[0]).lower() for col in cursor.description or []]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        finally:
            cursor.close()


def connect(profile: str, role: str = "LAB_RUNTIME") -> ConnectorTransport:
    # Credentials are resolved by Snowflake's local profile, never CLI arguments/logs.
    import snowflake.connector

    connection = snowflake.connector.connect(
        connection_name=profile,
        role=identifier(role),
        session_parameters={
            "STATEMENT_TIMEOUT_IN_SECONDS": 120,
            "QUERY_TAG": "agent-evaluation-lab",
        },
        network_timeout=120,
        login_timeout=30,
    )
    result = ConnectorTransport(connection)
    result.query("USE SECONDARY ROLES NONE")
    return result


def split_reference(value: str) -> tuple[str, str]:
    parts = value.split("!")
    if len(parts) != 2 or not re.fullmatch(r"VERSION\$[1-9][0-9]*", parts[1]):
        raise ValueError("Evaluation requires an explicit committed VERSION$N")
    return qualified(parts[0]), parts[1]


class SnowflakeAdapter:
    def __init__(
        self,
        transport: SQLTransport,
        deployment_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.transport = transport
        self.deployment_probe = deployment_probe or self.capture_fingerprint

    def probe(self) -> dict[str, Any]:
        rows = self.transport.query(
            "SELECT CURRENT_ACCOUNT() AS account, CURRENT_REGION() AS region, "
            "CURRENT_ROLE() AS role, CURRENT_VERSION() AS platform_version"
        )
        return {
            "platform": "snowflake",
            "connection": rows,
            "availability": "Requires separately budgeted capability smoke test",
        }

    def deploy(self, bundle: dict[str, Any]) -> dict[str, Any]:
        # This method expects a deployment-role transport, not the evaluation runner's runtime role.
        if not bundle.get("budget_preflight_ref"):
            raise ValueError("Deployment requires a recorded budget preflight")
        completed = []
        for statement in bundle["statements"]:
            completed.append(self.transport.query(statement))
        return {"bundle_sha256": digest(bundle), "results": completed}

    def capture_fingerprint(self, deployment: dict[str, Any]) -> dict[str, Any]:
        name, version = split_reference(deployment["deployment_ref"])
        semantic = qualified(deployment["semantic_view"])
        versions = self.transport.query(f"SHOW VERSIONS IN AGENT {name}")
        matching_versions = [row for row in versions if str(row.get("name")) == version]
        if not matching_versions:
            raise ValueError("Committed agent version missing")
        version_metadata = matching_versions[0]
        files = self.transport.query(f"LIST 'snow://agent/{name}/versions/{version}/'")
        if not files or any(not row.get("md5") for row in files):
            raise ValueError("Cannot verify native version files; do not assume integrity")
        try:
            semantic_definition = {
                "source": "GET_DDL",
                "rows": self.transport.query(
                    "SELECT GET_DDL('SEMANTIC_VIEW', %s) AS ddl", (semantic,)
                ),
            }
        except Exception:
            # GET_DDL is not implemented for semantic views on every account edition.
            # DESCRIBE exposes the normalized definition without elevating LAB_RUNTIME.
            semantic_definition = {
                "source": "DESCRIBE SEMANTIC VIEW",
                "rows": self.transport.query(f"DESCRIBE SEMANTIC VIEW {semantic}"),
            }
        data: dict[str, Any] = {}
        for table in deployment["tables"]:
            table_name = qualified(table)
            # Canonical sorting is local so SQL collation cannot change the digest.
            rows = self.transport.query(f"SELECT * FROM {table_name}")
            data[table_name] = sorted(
                rows, key=lambda row: json.dumps(row, sort_keys=True, default=str)
            )
        role = self.transport.query("SELECT CURRENT_ROLE() AS role")[0]["role"]
        if role != "LAB_RUNTIME":
            raise ValueError("Invoke with the dedicated LAB_RUNTIME role")
        grants = self.transport.query("SHOW GRANTS TO ROLE LAB_RUNTIME")
        stable_grants = [{k: v for k, v in row.items() if k != "created_on"} for row in grants]
        agent_spec = version_metadata.get("agent_spec")
        if isinstance(agent_spec, str):
            try:
                agent_spec = json.loads(agent_spec)
            except json.JSONDecodeError:
                agent_spec = {"raw": agent_spec}
        requested_model = (
            agent_spec.get("models", {}).get("orchestration")
            if isinstance(agent_spec, dict)
            else None
        )
        return {
            "agent_version": {
                "requested": version,
                "observed": {
                    key: version_metadata.get(key)
                    for key in ["name", "spec_file_path", "is_default", "comment"]
                },
            },
            "requested_model": requested_model,
            "agent_spec": agent_spec,
            "native_files": sorted(
                [{k: row.get(k) for k in ["name", "size", "md5"]} for row in files],
                key=lambda row: str(row["name"]),
            ),
            "semantic_definition": semantic_definition,
            "tables": data,
            "grants": sorted(
                stable_grants, key=lambda row: json.dumps(row, sort_keys=True, default=str)
            ),
            "role": role,
        }

    def verify_sealed_specification(self, deployment: dict[str, Any]) -> dict[str, Any]:
        """Verify a Benchmark R1 sealed candidate against its committed agent version.

        ADR-0004 requires extending verification from the frozen ``A0``-``A2`` bundle shape
        (a single ``fingerprint_sha256`` over a full dependency probe) to the four R1
        candidates, whose seal instead pins the committed specification component-by-component
        (``spec_canonical_hash``, ``instructions_hash``, ``tools_hash``,
        ``tool_resources_hash``, ``semantic_view``, ``model``) plus the execution role. Every
        sealed component must match the live committed version; anything missing, extra, or
        divergent fails closed.
        """
        name, version = split_reference(deployment["deployment_ref"])
        versions = self.transport.query(f"SHOW VERSIONS IN AGENT {name}")
        matching = [row for row in versions if str(row.get("name")) == version]
        if not matching:
            raise ValueError("Committed agent version missing")
        raw_spec = matching[0].get("agent_spec")
        spec = json.loads(raw_spec) if isinstance(raw_spec, str) else raw_spec
        if not isinstance(spec, dict):
            raise ValueError("Cannot read the committed agent specification")
        files = self.transport.query(f"LIST 'snow://agent/{name}/versions/{version}/'")
        if not files or any(not row.get("md5") for row in files):
            raise ValueError("Cannot verify native version files; do not assume integrity")
        role = self.transport.query("SELECT CURRENT_ROLE() AS role")[0]["role"]
        resources = spec.get("tool_resources", {})
        semantic_views = sorted(
            {
                str(value["semantic_view"])
                for value in resources.values()
                if isinstance(value, dict) and value.get("semantic_view")
            }
        )
        checks = {
            "spec_canonical_hash": digest(spec) == deployment["spec_canonical_hash"],
            "instructions_hash": digest(spec.get("instructions"))
            == deployment["instructions_hash"],
            "tools_hash": digest(spec.get("tools")) == deployment["tools_hash"],
            "tool_resources_hash": digest(resources) == deployment["tool_resources_hash"],
            "semantic_view": semantic_views == [deployment["semantic_view"]],
            "model": spec.get("models", {}).get("orchestration") == deployment["model"],
            "role": role == deployment.get("permissions", {}).get("role"),
        }
        return {
            "verified": all(checks.values()),
            "fingerprint_sha256": digest(spec),
            "checks": checks,
            "verification": "sealed_specification_components",
        }

    def verify(self, deployment: dict[str, Any]) -> dict[str, Any]:
        split_reference(deployment["deployment_ref"])
        if "fingerprint_sha256" not in deployment and "spec_canonical_hash" in deployment:
            return self.verify_sealed_specification(deployment)
        observed = self.deployment_probe(deployment)
        # Normalize Decimal/date values in SQL metadata deterministically.
        normalized = json.loads(json.dumps(observed, sort_keys=True, default=str))
        fingerprint = digest(normalized)
        return {
            "verified": fingerprint == deployment.get("fingerprint_sha256"),
            "fingerprint_sha256": fingerprint,
        }

    def estimate(self, batch: dict[str, Any]) -> dict[str, Any]:
        from evaluation.costs import Quote

        quote = Quote(
            batch["batch_id"],
            batch["invocation_count"],
            Decimal(batch["per_invocation_upper_usd"]),
            Decimal(batch["warehouse_usd"]),
            Decimal(batch["judge_usd"]),
            Decimal(batch["uncertainty_multiplier"]),
            batch["rate_card_sha256"],
        )
        return {
            "usd": str(quote.total()),
            "state": "estimated",
            "rate_card_sha256": quote.rate_card_hash,
        }

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        split_reference(request.deployment_ref)
        payload = {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": request.question_text}]}
            ]
        }
        started = time.monotonic_ns()
        try:
            rows = self.transport.query(
                "SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(%s, %s) AS response",
                (request.deployment_ref, json.dumps(payload, ensure_ascii=False)),
            )
            raw = rows[0]["response"]
            if isinstance(raw, str):
                raw = json.loads(raw)
            if not isinstance(raw, dict):
                raise ValueError("Unexpected Cortex response shape")
            elapsed = int((time.monotonic_ns() - started) / 1_000_000)
            text = "".join(
                block.get("text", "")
                for block in raw.get("content", [])
                if block.get("type") == "text"
            )
            request_id = raw.get("request_id") or raw.get("metadata", {}).get("run_id")
            status = raw.get("status", "completed")
            provider_code = raw.get("code") or raw.get("error_code")
            provider_error = raw.get("error") or (
                provider_code is not None
                and str(provider_code).upper() not in {"0", "200", "SUCCESS"}
            )
            if status in {"timed_out", "cancelled", "error"} or provider_error:
                timed_out = status == "timed_out"
                return InvocationResult(
                    "timeout" if timed_out else "error",
                    text or None,
                    elapsed,
                    request_id,
                    raw,
                    "TIMEOUT" if timed_out else str(provider_code or "PLATFORM_ERROR"),
                )
            return InvocationResult("completed", text or None, elapsed, request_id, raw)
        except Exception as exc:
            # Do not persist exception text: connector messages may expose credentials or SQL.
            elapsed = int((time.monotonic_ns() - started) / 1_000_000)
            timeout = isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower()
            return InvocationResult(
                "timeout" if timeout else "ambiguous",
                None,
                elapsed,
                None,
                {"exception_type": type(exc).__name__, "response_unavailable": True},
                "TIMEOUT" if timeout else "PLATFORM_ERROR",
            )

    def collect_usage(self, batch: dict[str, Any]) -> list[UsageRecord]:
        # Request-level token credits include component charges. Do not add Analyst totals again.
        rows = self.transport.query(
            "SELECT REQUEST_ID, TOKEN_CREDITS, METADATA FROM "
            "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY "
            "WHERE START_TIME >= %s AND START_TIME < %s AND AGENT_NAME = %s",
            (batch["started_at"], batch["completed_at"], batch["agent_name"]),
        )
        rate = Decimal(batch["usd_per_credit"]) if batch.get("usd_per_credit") else None
        records = []
        for row in rows:
            credits = (
                Decimal(str(row["token_credits"])) if row.get("token_credits") is not None else None
            )
            records.append(
                UsageRecord(
                    str(row["request_id"]),
                    "agent_token_credits",
                    credits * rate if credits is not None and rate is not None else None,
                    credits,
                    "final" if credits is not None else "unknown",
                    "provider_request_id",
                    batch.get("rate_card_sha256"),
                )
            )
        return records

    def export_trace(self, invocation: dict[str, Any]) -> dict[str, Any]:
        name, _ = split_reference(invocation["deployment_ref"])
        db, schema, agent = name.split(".")
        rows = self.transport.query(
            "SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(%s,%s,%s,%s)) "
            "WHERE TIMESTAMP >= %s AND TIMESTAMP <= %s",
            (
                db,
                schema,
                agent,
                "CORTEX AGENT",
                invocation["started_at"],
                invocation["completed_at"],
            ),
        )
        return {
            "request_id": invocation.get("request_id"),
            "events": rows,
            "attribution": "time_window_candidates; retain until exact trace join is reviewed",
        }
