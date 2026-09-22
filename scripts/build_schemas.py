"""Deterministically generate public JSON Schemas; --check is read-only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
S = {"type": "string", "minLength": 1}
B = {"type": "boolean"}
NONNEGATIVE_INTEGER = {"type": "integer", "minimum": 0}
OBJ = {"type": "object"}
STAMP = {"type": "string", "format": "date-time"}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
MONEY = {"type": "string", "pattern": r"^\d+(\.\d+)?$"}

R1_STRING_COLUMNS = (
    "series_id",
    "event",
    "festival_id",
    "state",
    "distance",
    "era",
)
R1_INTEGER_COLUMNS = (
    "event_year",
    "eligible_finishers",
    "sex_recorded",
    "sex_missing",
    "female_count",
    "male_count",
    "other_sex_count",
    "age_recorded",
    "age_missing",
    "age_year_difference_count",
    "age_band_mappable",
    "age_band_unmapped",
    "age_under_30_count",
    "age_30_49_count",
    "age_50_plus_count",
)
R1_DECIMAL_COLUMNS = (
    "sex_completeness",
    "female_share_known",
    "age_completeness",
    "mean_age_year_difference",
    "median_age_year_difference",
    "age_band_mapping_completeness",
    "share_under_30_mapped",
    "share_30_49_mapped",
    "share_50_plus_mapped",
)


def enum(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def obj(properties: dict[str, Any], optional: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": [key for key in properties if key not in optional],
        "additionalProperties": False,
    }


def schemas() -> dict[str, dict[str, Any]]:
    answer = obj(
        {
            "status": enum("answered", "abstain", "clarification_needed"),
            "columns": {**array(S), "uniqueItems": True},
            "rows": array(array({"type": ["string", "integer", "number", "boolean", "null"]})),
            "units": {"type": "object", "additionalProperties": S},
            "caveats": {**array(S), "uniqueItems": True},
            "evidence_ids": {**array(S), "uniqueItems": True},
            "explanation_de": {"type": "string"},
        }
    )
    question = obj(
        {
            "question_id": S,
            "intent_id": S,
            "leakage_group_id": S,
            "language": enum("de", "en"),
            "text": S,
            "category": enum(
                "lookup",
                "aggregation",
                "temporal",
                "ranking_ratio",
                "missingness",
                "scope_provenance",
            ),
            "difficulty": enum("easy", "medium", "hard"),
            "critical": B,
            "split": enum("TRAIN", "TEST", "HOLDOUT"),
            "origin": enum(
                "stakeholder", "authored", "synthetic_fixture", "synthetic_augmentation"
            ),
        }
    )
    truth = obj(
        {
            "question_id": S,
            "expected": answer,
            "oracle_sql": nullable(S),
            "ordered": B,
            "tolerances": {"type": "object", "additionalProperties": MONEY},
            "evidence_alternatives": array(array(S)),
            "prohibited_claims": array(S),
            "reviewer": S,
        },
        ("ordered", "tolerances", "evidence_alternatives", "prohibited_claims", "reviewer"),
    )
    r1_aggregate_row = obj(
        {
            **{name: S for name in R1_STRING_COLUMNS},
            **{name: NONNEGATIVE_INTEGER for name in R1_INTEGER_COLUMNS},
            **{name: nullable({"type": "number"}) for name in R1_DECIMAL_COLUMNS},
        }
    )
    return {
        "answer": answer,
        "question": question,
        "ground_truth": truth,
        "question_translation": obj(
            {
                "question_id": S,
                "language": S,
                "text": S,
                "purpose": {"const": "documentation"},
                "scored": {"const": False},
            }
        ),
        "benchmark_release": obj(
            {
                "release_id": S,
                "schema_version": S,
                "classification": enum("synthetic_fixture", "real_benchmark"),
                "publication_disposition": enum("synthetic_only", "approved", "blocked"),
                "files": {"type": "object", "minProperties": 1, "additionalProperties": HASH},
                "selection_rule_sha256": HASH,
                "source_snapshot_refs": array(S),
                "frozen_at": STAMP,
                "review_ref": nullable(S),
            }
        ),
        "split_assignment": obj(
            {
                "benchmark_id": S,
                "question_id": S,
                "split": enum("TRAIN", "TEST", "HOLDOUT"),
                "grouping_version": S,
                "seed": NONNEGATIVE_INTEGER,
                "assignment_sha256": HASH,
                "frozen_at": STAMP,
                "intent_id": S,
                "leakage_group_id": S,
                "translation_group_id": S,
                "paraphrase_group_id": S,
                "entity_substitution_group_id": S,
            },
            (
                "translation_group_id",
                "paraphrase_group_id",
                "entity_substitution_group_id",
                "intent_id",
                "leakage_group_id",
            ),
        ),
        "r1_aggregate_row": r1_aggregate_row,
        "semantic_spec": obj(
            {
                "version": S,
                "entities": array(OBJ),
                "relationships": array(OBJ),
                "dimensions": array(OBJ),
                "measures": array(OBJ),
                "null_policy": S,
                "descriptions": OBJ,
                "synonyms": OBJ,
                "train_examples": array(OBJ),
            }
        ),
        "model_binding": obj(
            {
                "component": S,
                "provider": S,
                "requested_model": S,
                "reported_model": nullable(S),
                "reported_revision": nullable(S),
                "routing_policy": S,
                "parameters": OBJ,
                "region": S,
                "pinning_level": enum("revision", "named_model", "managed_unknown"),
            }
        ),
        "agent_spec": obj(
            {
                "candidate_id": S,
                "parent_id": nullable(S),
                "intervention": enum("cold_start", "semantics", "instructions", "model", "config"),
                "instructions": OBJ,
                "tools": array(OBJ),
                "semantic_sha256": HASH,
                "model_bindings": array(OBJ),
                "limits": OBJ,
                "output_contract_sha256": HASH,
            }
        ),
        "evaluation_spec": obj(
            {
                "version": S,
                "comparator_version": S,
                "rubric_sha256": HASH,
                "native_judge": nullable(OBJ),
                "repetitions": {"const": 2},
                "schedule_seed": NONNEGATIVE_INTEGER,
                "missing_output_policy": {"const": "unsuccessful"},
                "thresholds": OBJ,
            }
        ),
        "experiment_manifest": obj(
            {
                "experiment_id": S,
                "schema_version": S,
                "classification": enum("synthetic_fixture", "prospective_procedurally_sealed"),
                "frozen_at": STAMP,
                "git_commit": S,
                "dependency_lock_sha256": HASH,
                "benchmark_sha256": HASH,
                "evaluation_sha256": HASH,
                "candidates": {
                    "type": "object",
                    "minProperties": 2,
                    "maxProperties": 3,
                    "additionalProperties": HASH,
                },
                "schedule_sha256": HASH,
                "environment": OBJ,
                "budget": OBJ,
            }
        ),
        "invocation": obj(
            {
                "invocation_id": S,
                "candidate_id": S,
                "question_id": S,
                "repetition": {"type": "integer", "minimum": 0, "maximum": 1},
                "status": enum("completed", "timeout", "error", "ambiguous"),
                "response_text": nullable({"type": "string"}),
                "latency_ms": NONNEGATIVE_INTEGER,
                "request_id": nullable(S),
                "raw_sha256": HASH,
                "started_at": STAMP,
                "completed_at": STAMP,
                "error_code": nullable(S),
            }
        ),
        "assessment": obj(
            {
                "invocation_id": S,
                "metric": S,
                "value": nullable(B),
                "assessor_type": enum(
                    "deterministic", "human", "native_judge", "synthetic_fixture"
                ),
                "evaluator_version": S,
                "evidence_refs": array(S),
                "status": enum("pending", "final", "superseded"),
                "recorded_at": STAMP,
            }
        ),
        "usage_record": obj(
            {
                "scope_id": S,
                "component": S,
                "usd": nullable(MONEY),
                "credits": nullable(MONEY),
                "state": enum("estimated", "final", "unknown"),
                "attribution": S,
                "rate_card_hash": nullable(HASH),
            }
        ),
        "error_record": obj(
            {
                "invocation_id": S,
                "codes": array(S),
                "severity": enum("warning", "failure", "critical"),
                "stage": S,
                "evidence_refs": array(S),
                "reviewer": nullable(S),
            }
        ),
        "release_decision": obj(
            {
                "candidate_id": nullable(S),
                "predecessor": nullable(S),
                "policy_sha256": HASH,
                "metrics_sha256": HASH,
                "gates": OBJ,
                "decision": enum("accepted", "rejected", "inconclusive"),
                "reason": S,
                "recorded_at": STAMP,
            }
        ),
        "disclosure_event": obj(
            {
                "actor": S,
                "role": S,
                "artifact_sha256": HASH,
                "purpose": S,
                "at": STAMP,
                "reveal_stage": S,
                "authorization_basis": S,
            }
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "evaluation" / "schemas"
    if not args.check:
        target.mkdir(parents=True, exist_ok=True)
    for name, body in schemas().items():
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:agent-lab:1:{name}",
            **body,
        }
        text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
        path = target / f"{name}.json"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit(f"Schema drift: {name}")
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Schemas: {len(schemas())} PASS")


if __name__ == "__main__":
    main()
