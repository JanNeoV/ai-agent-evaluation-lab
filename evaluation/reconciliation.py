"""Explicit cost attribution without summing agent and tool charges twice."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from evaluation.costs import money


def reconcile_runtime(
    records: list[dict[str, Any]],
    token_usage: list[dict[str, Any]],
    warehouse_usd: str,
    *,
    warehouse_attribution_review: str,
    rate_card_hash: str,
) -> dict[str, dict[str, Any]]:
    """Allocate the complete reviewed warehouse amount by invocation wall time.

    token_usage contains only the agent's aggregate token USD, not extra Analyst or
    SQL charges. Include all warehouse idle/resume costs in the reviewed batch total.
    Missing/ambiguous request attribution leaves per-invocation totals unknown.
    """
    if not warehouse_attribution_review or not rate_card_hash:
        raise ValueError("Reviewed warehouse allocation and rate-card evidence are required")
    if len({r["invocation_id"] for r in records}) != len(records):
        raise ValueError("Duplicate invocation")
    request_ids = [r["request_id"] for r in records if r["request_id"] is not None]
    if len(set(request_ids)) != len(request_ids):
        raise ValueError("One billing request cannot be attributed twice")
    usage: dict[str, Decimal | None] = {}
    for row in token_usage:
        if row["request_id"] in usage:
            raise ValueError("Duplicate agent billing request; possible double counting")
        if row["component"] != "agent_token_credits":
            raise ValueError("Do not add separately reported Analyst or SQL cost here")
        usage[row["request_id"]] = money(row["usd"]) if row["usd"] is not None else None
    if set(usage) - set(request_ids):
        raise ValueError("Unattributed usage remains: reconcile before finalizing batch")
    total_warehouse = money(warehouse_usd)
    denominator = sum(max(1, r["latency_ms"]) for r in records)
    output: dict[str, dict[str, Any]] = {}
    allocated = Decimal(0)
    for index, record in enumerate(records):
        share = (
            total_warehouse - allocated
            if index == len(records) - 1
            else total_warehouse * Decimal(max(1, record["latency_ms"])) / Decimal(denominator)
        )
        allocated += share
        token_cost = usage.get(record["request_id"])
        output[record["invocation_id"]] = {
            "usd": str(token_cost + share) if token_cost is not None else None,
            "state": "final" if token_cost is not None else "unknown",
            "token_usd": str(token_cost) if token_cost is not None else None,
            "allocated_warehouse_usd": str(share),
            "allocation": "batch_wall_time_share",
            "warehouse_attribution_review": warehouse_attribution_review,
            "rate_card_sha256": rate_card_hash,
        }
    if not records and total_warehouse != 0:
        raise ValueError("Warehouse cost has no invocations to allocate to")
    return output
