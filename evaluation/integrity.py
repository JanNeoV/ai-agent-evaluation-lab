"""Recompute evidence hashes and accounting without invoking any agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.artifacts import Ledger, digest, file_hash, load_json
from evaluation.contracts import validate


def verify_batch(root: Path) -> dict[str, Any]:
    plan = load_json(root / "schedule.json")
    planned_ids = {row["invocation_id"] for row in plan}
    if len(planned_ids) != len(plan):
        raise ValueError("Duplicate planned invocation")
    events = Ledger(root / "events.jsonl").read()
    submitted = [e["payload"]["invocation_id"] for e in events if e["kind"] == "submitted"]
    completed = {
        e["payload"]["invocation_id"]: e["payload"]["record_sha256"]
        for e in events
        if e["kind"] == "completed"
    }
    if len(submitted) != len(set(submitted)) or not set(submitted).issubset(planned_ids):
        raise ValueError("Invalid submission accounting")
    files = list((root / "invocations").glob("*.json"))
    observed: set[str] = set()
    for path in files:
        record = load_json(path)
        validate("invocation", record)
        identifier = record["invocation_id"]
        if identifier in observed or identifier not in planned_ids or identifier != path.stem:
            raise ValueError("Unexpected response file")
        observed.add(identifier)
        if identifier not in submitted or completed.get(identifier) != digest(record):
            raise ValueError("Invocation hash or completion event mismatch")
        if file_hash(root / "raw" / f"{identifier}.json") != record["raw_sha256"]:
            raise ValueError("Raw evidence hash mismatch")
    if set(completed) != observed:
        raise ValueError("Missing completed invocation artifact")
    return {
        "planned": len(planned_ids),
        "submitted": len(submitted),
        "completed": len(observed),
        "unsubmitted": sorted(planned_ids - set(submitted)),
        "ambiguous": sorted(set(submitted) - observed),
        "complete": observed == planned_ids,
    }
