"""Benchmark R1 aggregate loader, deterministic oracle, and sealed-release checks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeAlias, cast

import duckdb
from cryptography.fernet import Fernet

from evaluation.artifacts import canonical, digest, file_hash, load_json, verify_files
from evaluation.comparators import rows_equal
from evaluation.contracts import GroundTruth, Question, Split, validate, validate_splits
from evaluation.p2_core_export import (
    DECIMAL_COLUMNS,
    INTEGER_COLUMNS,
    OUTPUT_COLUMNS,
    STRING_COLUMNS,
    parse_export,
    sha256_bytes,
)
from evaluation.sealing import seal_payload

R1_SCHEMA_VERSION = "r1.aggregate.v1"
R1_RELEASE_ID = "R1-001"
R1_TABLE = "p2_core_edition"
SOURCE_CSV_SHA256 = "8aef522a581db33fcab973d4d95700803800957e5d57c01ebf4ff1a1c34ffa00"
SOURCE_MANIFEST_SHA256 = "8231e23568236f2922f87bc59a1a2eb91ba8f03f296c9fc64a9dafd525bebe9f"
SOURCE_EVIDENCE_ID = "SOURCE-MANIFEST-R1-001"
PROHIBITED_CLAIMS = (
    "national_representativeness",
    "bavaria_wide_representativeness",
    "causal_effect",
    "causal_pandemic_effect",
    "participant_level_reconstruction",
    "external_replication_pooling",
)
REQUIRED_CAVEATS = (
    "p2_core_four_series_40_editions_only",
    "not_nationally_representative",
    "non_causal_descriptive_only",
)
GROUP_FIELDS = (
    "intent_id",
    "leakage_group_id",
    "translation_group_id",
    "paraphrase_group_id",
    "entity_substitution_group_id",
)

Cell: TypeAlias = str | int | float | Decimal | None
TypedRow: TypeAlias = dict[str, Cell]


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, Any], value)


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _source_schema() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for column in OUTPUT_COLUMNS:
        if column in STRING_COLUMNS:
            kind = "string"
        elif column in INTEGER_COLUMNS:
            kind = "integer"
        else:
            kind = "decimal"
        result.append({"name": column, "type": kind, "nullable": column in DECIMAL_COLUMNS})
    return result


def load_aggregate(csv_path: Path, source_manifest_path: Path) -> list[TypedRow]:
    """Load the approved CSV without mapping it onto the legacy event tables."""
    if file_hash(csv_path) != SOURCE_CSV_SHA256:
        raise ValueError("R1 aggregate does not match the TASK-0002 approved CSV hash")
    if file_hash(source_manifest_path) != SOURCE_MANIFEST_SHA256:
        raise ValueError("R1 source manifest does not match the TASK-0002 approved manifest hash")
    manifest = _require_object(load_json(source_manifest_path), "source manifest")
    return parse_aggregate(csv_path.read_bytes(), manifest)


def parse_aggregate(content: bytes, manifest: dict[str, Any]) -> list[TypedRow]:
    """Parse a schema-conforming aggregate; production admission adds frozen hash checks."""
    export = _require_object(manifest.get("export"), "source manifest export")
    expected = {
        "sha256": sha256_bytes(content),
        "row_count": 40,
        "column_count": 30,
        "series_count": 4,
        "schema": _source_schema(),
    }
    if any(export.get(key) != value for key, value in expected.items()):
        raise ValueError("R1 aggregate does not reconcile to the TASK-0002 manifest")
    scope = _require_object(manifest.get("scope"), "source manifest scope")
    excluded = (
        "external_replication_included",
        "participant_or_finisher_rows_included",
        "names_or_personal_data_included",
        "row_identifiers_included",
        "source_locators_or_raw_documents_included",
    )
    if any(scope.get(field) is not False for field in excluded):
        raise ValueError("R1 source manifest weakens the aggregate-only boundary")
    if manifest.get("unknown_value_policy") is None:
        raise ValueError("R1 source manifest has no unknown-value policy")

    raw_rows = parse_export(content)
    rows: list[TypedRow] = []
    for raw in raw_rows:
        row: TypedRow = {}
        for column in OUTPUT_COLUMNS:
            value = raw[column]
            if column in STRING_COLUMNS:
                row[column] = value
            elif column in INTEGER_COLUMNS:
                row[column] = int(value)
            else:
                row[column] = None if value == "" else Decimal(value)
        validate("r1_aggregate_row", row)
        _validate_null_semantics(row)
        rows.append(row)
    return rows


def _validate_null_semantics(row: Mapping[str, Cell]) -> None:
    age_difference = int(cast(int, row["age_year_difference_count"]))
    for column in ("mean_age_year_difference", "median_age_year_difference"):
        if (row[column] is None) != (age_difference == 0):
            raise ValueError(f"{column} must be null exactly when its denominator is zero")
    mapped = int(cast(int, row["age_band_mappable"]))
    for column in ("share_under_30_mapped", "share_30_49_mapped", "share_50_plus_mapped"):
        if (row[column] is None) != (mapped == 0):
            raise ValueError(f"{column} must preserve zero-denominator null semantics")
    recorded = int(cast(int, row["sex_recorded"]))
    if (row["female_share_known"] is None) != (recorded == 0):
        raise ValueError("female_share_known must preserve zero-denominator null semantics")


def aggregate_database(rows: list[TypedRow]) -> duckdb.DuckDBPyConnection:
    columns = []
    for name in OUTPUT_COLUMNS:
        if name in STRING_COLUMNS:
            kind = "VARCHAR"
        elif name in INTEGER_COLUMNS:
            kind = "INTEGER"
        else:
            kind = "DECIMAL(18,9)"
        columns.append((name, kind))
    connection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE {R1_TABLE} (" + ", ".join(f'"{name}" {kind}' for name, kind in columns) + ")"
    )
    connection.executemany(
        f"INSERT INTO {R1_TABLE} VALUES (" + ", ".join("?" for _ in columns) + ")",
        [[row[name] for name, _ in columns] for row in rows],
    )
    connection.execute("SET enable_external_access=false")
    return connection


def query_aggregate(
    connection: duckdb.DuckDBPyConnection, sql: str
) -> tuple[list[str], list[list[Any]]]:
    statements = connection.extract_statements(sql)
    if len(statements) != 1 or str(statements[0].type) != "StatementType.SELECT":
        raise ValueError("R1 oracle SQL must be one read-only SELECT")
    result = connection.execute(sql)
    columns = [str(column[0]) for column in result.description]
    rows = [
        [float(value) if isinstance(value, Decimal) else value for value in row]
        for row in result.fetchall()
    ]
    return columns, rows


def _validate_grouping(questions: list[Question] | None, split_manifest: dict[str, Any]) -> None:
    assignments = [
        _require_object(row, "split assignment")
        for row in _require_list(split_manifest.get("assignments"), "split assignments")
    ]
    if len(assignments) != 24:
        raise ValueError("R1 split manifest must contain exactly 24 assignments")
    question_by_id = (
        {question.question_id: question for question in questions} if questions is not None else {}
    )
    if questions is not None and {row.get("question_id") for row in assignments} != set(
        question_by_id
    ):
        raise ValueError("R1 split assignments do not cover the canonical questions")
    groups: dict[str, dict[str, Split]] = {field: {} for field in GROUP_FIELDS}
    for row in assignments:
        validate("split_assignment", row)
        split = Split(str(row["split"]))
        question = question_by_id.get(str(row["question_id"]))
        if question is not None and row["split"] != question.split.value:
            raise ValueError("R1 question and split manifest disagree")
        expected_hash = digest(
            {key: value for key, value in row.items() if key != "assignment_sha256"}
        )
        if row["assignment_sha256"] != expected_hash:
            raise ValueError("R1 split assignment hash mismatch")
        values = {
            "intent_id": row["intent_id"],
            "leakage_group_id": row["leakage_group_id"],
            "translation_group_id": row["translation_group_id"],
            "paraphrase_group_id": row["paraphrase_group_id"],
            "entity_substitution_group_id": row["entity_substitution_group_id"],
        }
        for field, group_id in values.items():
            registry = groups[field]
            if group_id in registry and registry[group_id] != split:
                raise ValueError(f"{field} crosses splits")
            registry[group_id] = split
        if question is not None and (
            row["intent_id"] != question.intent_id
            or row["leakage_group_id"] != question.leakage_group_id
        ):
            raise ValueError("R1 question grouping metadata disagrees with the split manifest")


def _has_restricted_claim_wording(text: str) -> bool:
    lowered = text.casefold()
    markers = (
        "ganz deutschland",
        "bundesweit",
        "national",
        "bayernweit",
        "repräsentativ",
        "bevölkerung",
        "kausal",
        "verursacht",
        "bewirkt",
        "pandemie",
        "einzelne finisher",
        "einzelne teilnehm",
    )
    return any(marker in lowered for marker in markers)


def _validate_questions_and_truths(
    questions: list[Question],
    truths: list[GroundTruth],
    split_manifest: dict[str, Any],
    reviewer: str,
) -> None:
    validate_splits(questions)
    _validate_grouping(questions, split_manifest)
    truth_by_id = {truth.question_id: truth for truth in truths}
    if len(truth_by_id) != 24 or set(truth_by_id) != {
        question.question_id for question in questions
    }:
        raise ValueError("R1 ground truth coverage mismatch")
    for question in questions:
        truth = truth_by_id[question.question_id]
        if truth.reviewer != reviewer or reviewer.strip().casefold() == "unreviewed":
            raise ValueError("R1 ground truth requires the named reviewer")
        if not set(PROHIBITED_CLAIMS).issubset(truth.prohibited_claims):
            raise ValueError("R1 ground truth omits a prohibited-claim boundary")
        if not set(REQUIRED_CAVEATS).issubset(truth.expected["caveats"]):
            raise ValueError("R1 ground truth omits a scope caveat")
        restricted = _has_restricted_claim_wording(question.text)
        if restricted and (truth.oracle_sql is not None or truth.expected["status"] != "abstain"):
            raise ValueError(
                "Unsupported national, causal, or participant-level wording must abstain"
            )


def _split_manifest(items: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    assignments: list[dict[str, Any]] = []
    for item in items:
        question = _require_object(item.get("question"), "question")
        row = {
            "benchmark_id": R1_RELEASE_ID,
            "question_id": question["question_id"],
            "split": question["split"],
            "grouping_version": spec["grouping_version"],
            "seed": spec["split_seed"],
            "frozen_at": spec["frozen_at"],
            "intent_id": question["intent_id"],
            "leakage_group_id": question["leakage_group_id"],
            "translation_group_id": item["translation_group_id"],
            "paraphrase_group_id": item["paraphrase_group_id"],
            "entity_substitution_group_id": item["entity_substitution_group_id"],
        }
        row["assignment_sha256"] = digest(row)
        assignments.append(row)
    return {
        "benchmark_id": R1_RELEASE_ID,
        "grouping_version": spec["grouping_version"],
        "seed": spec["split_seed"],
        "frozen_at": spec["frozen_at"],
        "assignments": assignments,
    }


def build_plain_payloads(
    rows: list[TypedRow], authoring_spec: dict[str, Any]
) -> tuple[dict[Split, dict[str, Any]], dict[str, Any]]:
    if authoring_spec.get("release_id") != R1_RELEASE_ID:
        raise ValueError("Authoring specification has the wrong release ID")
    reviewer = authoring_spec.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer.casefold() == "unreviewed":
        raise ValueError("Authoring specification requires a named reviewer")
    items = [
        _require_object(item, "authoring item")
        for item in _require_list(authoring_spec.get("items"), "authoring items")
    ]
    if len(items) != 24:
        raise ValueError("R1 requires exactly 24 authoring items")
    questions = [
        Question.from_dict(_require_object(item.get("question"), "question")) for item in items
    ]
    split_manifest = _split_manifest(items, authoring_spec)
    truths: list[GroundTruth] = []
    connection = aggregate_database(rows)
    try:
        for item, question in zip(items, questions, strict=True):
            status = item.get("status")
            oracle_sql = item.get("oracle_sql")
            if status == "answered":
                if not isinstance(oracle_sql, str) or not oracle_sql:
                    raise ValueError("Answered R1 item requires oracle SQL")
                columns, result_rows = query_aggregate(connection, oracle_sql)
            elif status == "abstain":
                if oracle_sql is not None:
                    raise ValueError("R1 abstention may not carry oracle SQL")
                columns, result_rows = [], []
            else:
                raise ValueError("R1 item status must be answered or abstain")
            units = _require_object(item.get("units"), "answer units")
            if set(units) - set(columns):
                raise ValueError("R1 units name a column absent from the oracle result")
            extra_caveats = item.get("extra_caveats", [])
            if not isinstance(extra_caveats, list) or not all(
                isinstance(value, str) and value for value in extra_caveats
            ):
                raise ValueError("R1 extra caveats must be strings")
            truth_data = {
                "question_id": question.question_id,
                "expected": {
                    "status": status,
                    "columns": columns,
                    "rows": result_rows,
                    "units": units,
                    "caveats": list(dict.fromkeys([*REQUIRED_CAVEATS, *extra_caveats])),
                    "evidence_ids": [SOURCE_EVIDENCE_ID],
                    "explanation_de": item["explanation_de"],
                },
                "oracle_sql": oracle_sql,
                "ordered": bool(item.get("ordered", False)),
                "tolerances": _require_object(item.get("tolerances", {}), "tolerances"),
                "evidence_alternatives": [[SOURCE_EVIDENCE_ID]],
                "prohibited_claims": list(PROHIBITED_CLAIMS),
                "reviewer": reviewer,
            }
            truths.append(GroundTruth.from_dict(truth_data))
    finally:
        connection.close()
    _validate_questions_and_truths(questions, truths, split_manifest, reviewer)
    payloads: dict[Split, dict[str, Any]] = {}
    truth_data_by_id = {
        truth.question_id: {
            "question_id": truth.question_id,
            "expected": truth.expected,
            "oracle_sql": truth.oracle_sql,
            "ordered": truth.ordered,
            "tolerances": truth.tolerances,
            "evidence_alternatives": [list(group) for group in truth.evidence_alternatives],
            "prohibited_claims": list(truth.prohibited_claims),
            "reviewer": truth.reviewer,
        }
        for truth in truths
    }
    raw_question_by_id = {
        question.question_id: _require_object(item["question"], "question")
        for item, question in zip(items, questions, strict=True)
    }
    for split in Split:
        selected = [question for question in questions if question.split == split]
        payloads[split] = {
            "release_id": R1_RELEASE_ID,
            "split": split.value,
            "questions": [raw_question_by_id[question.question_id] for question in selected],
            "ground_truth": [truth_data_by_id[question.question_id] for question in selected],
        }
    return payloads, split_manifest


def _json_bytes(value: Any) -> bytes:
    return canonical(value) + b"\n"


def _write_bytes_once_or_same(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite changed frozen artifact: {path}")
        return
    path.write_bytes(content)


def _decrypt_payload(path: Path, key_path: Path) -> dict[str, Any]:
    value = json.loads(Fernet(key_path.read_bytes().strip()).decrypt(path.read_bytes()))
    return _require_object(value, "decrypted payload")


def _policy(frozen_at: str) -> dict[str, Any]:
    return {
        "version": "benchmark-r1-policy-v1",
        "frozen_at": frozen_at,
        "question_counts": {"TRAIN": 12, "TEST": 6, "HOLDOUT": 6},
        "category_allocation": {"TRAIN": 2, "TEST": 1, "HOLDOUT": 1},
        "critical_counts": {"TRAIN": 4, "TEST": 2, "HOLDOUT": 2},
        "repetitions": 2,
        "automatic_retries": 0,
        "candidate_ids": ["V0", "V1", "V2", "V3"],
        "test_selection": "existing deterministic decision boundary; one selected candidate",
        "holdout_gate": "selected TEST candidate only",
        "cost_ceiling_usd": "10.00",
        "uncertainty_reserve_usd": "2.00",
        "claim_boundaries": list(PROHIBITED_CLAIMS),
    }


def _rubric(reviewer: str) -> dict[str, Any]:
    return {
        "version": "benchmark-r1-narrative-rubric-v1",
        "reviewer": reviewer,
        "checks": [
            "prose agrees with every value, unit, filter, and denominator",
            "answer stays within the four-series, 40-edition P2 CORE subset",
            "nulls and calendar gaps are not converted to zero or imputed observations",
            "answer makes no national, Bavaria-wide, population, or causal generalization",
            "answer makes no participant-level reconstruction or external-replication inference",
            "abstentions state the unavailable scope without fabricating a result",
        ],
        "prohibited_claims": list(PROHIBITED_CLAIMS),
        "decision_rule": "Any material contradiction or prohibited claim fails narrative review.",
    }


def build_release(
    *,
    source_root: Path,
    release_root: Path,
    authoring_spec_path: Path,
    key_root: Path,
    developer_root: Path,
    train_output: Path,
    lab_root: Path,
) -> dict[str, Any]:
    if authoring_spec_path.resolve().is_relative_to(developer_root.resolve()):
        raise ValueError("Hidden authoring plaintext must be outside the developer checkout")
    if key_root.resolve().is_relative_to(developer_root.resolve()):
        raise ValueError("Evaluator keys must be outside the developer checkout")
    source_csv = source_root / "p2_core_edition_aggregate.csv"
    source_manifest = source_root / "source_manifest.json"
    rows = load_aggregate(source_csv, source_manifest)
    authoring_spec = _require_object(load_json(authoring_spec_path), "authoring specification")
    payloads, split_manifest = build_plain_payloads(rows, authoring_spec)
    second_payloads, second_split_manifest = build_plain_payloads(rows, authoring_spec)
    if _json_bytes(payloads) != _json_bytes(second_payloads) or _json_bytes(
        split_manifest
    ) != _json_bytes(second_split_manifest):
        raise ValueError("Two isolated R1 oracle builds were not byte-identical")

    release_root.mkdir(parents=True, exist_ok=True)
    stable_files: dict[str, bytes] = {
        "p2_core_edition_aggregate.csv": source_csv.read_bytes(),
        "source_manifest.json": source_manifest.read_bytes(),
        "train_payload.json": _json_bytes(payloads[Split.TRAIN]),
        "split_manifest.json": _json_bytes(split_manifest),
        "semantic_spec.json": (lab_root / "semantics/r1_aggregate_v1.json").read_bytes(),
        "rubric.json": _json_bytes(_rubric(str(authoring_spec["reviewer"]))),
        "policy.json": _json_bytes(_policy(str(authoring_spec["frozen_at"]))),
    }
    source_links = {
        "source_evidence_id": SOURCE_EVIDENCE_ID,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "aggregate_sha256": SOURCE_CSV_SHA256,
        "approval_ref": "docs/approvals/P2-CORE-R1-APPROVAL-001.md",
        "task_ref": "tasks/TASK-0002.md",
        "public_redistribution_authorized": False,
    }
    stable_files["source_links.json"] = _json_bytes(source_links)
    for relative, content in stable_files.items():
        _write_bytes_once_or_same(release_root / relative, content)
    _write_bytes_once_or_same(train_output, stable_files["train_payload.json"])

    sealed: dict[str, str] = {}
    for split, filename in (
        (Split.TEST, "test_payload.enc"),
        (Split.HOLDOUT, "holdout_payload.enc"),
    ):
        target = release_root / filename
        key_path = key_root / f"{split.value.casefold()}.key"
        if target.exists():
            if _json_bytes(_decrypt_payload(target, key_path)) != _json_bytes(payloads[split]):
                raise ValueError(
                    f"Existing {split.value} ciphertext decrypts to different plaintext"
                )
            sealed[split.value] = file_hash(target)
        else:
            sealed[split.value] = seal_payload(payloads[split], target, key_path, developer_root)

    protocol = {
        "release_id": R1_RELEASE_ID,
        "schema_version": R1_SCHEMA_VERSION,
        "classification": "prospective_procedurally_sealed",
        "frozen_at": authoring_spec["frozen_at"],
        "policy_sha256": file_hash(release_root / "policy.json"),
        "dependency_lock_sha256": file_hash(lab_root / "requirements.lock"),
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "aggregate_sha256": SOURCE_CSV_SHA256,
        "split_manifest_sha256": file_hash(release_root / "split_manifest.json"),
        "train_payload_sha256": file_hash(release_root / "train_payload.json"),
        "semantic_spec_sha256": file_hash(release_root / "semantic_spec.json"),
        "rubric_sha256": file_hash(release_root / "rubric.json"),
        "sealed_payloads": sealed,
    }
    _write_bytes_once_or_same(release_root / "protocol_freeze.json", _json_bytes(protocol))

    file_names = sorted(
        [*stable_files, "test_payload.enc", "holdout_payload.enc", "protocol_freeze.json"]
    )
    files = {name: file_hash(release_root / name) for name in file_names}
    manifest = {
        "release_id": R1_RELEASE_ID,
        "schema_version": R1_SCHEMA_VERSION,
        "classification": "real_benchmark",
        "publication_disposition": "blocked",
        "files": files,
        "selection_rule_sha256": protocol["policy_sha256"],
        "source_snapshot_refs": [
            f"source_manifest.json#sha256={SOURCE_MANIFEST_SHA256}",
            f"p2_core_edition_aggregate.csv#sha256={SOURCE_CSV_SHA256}",
        ],
        "frozen_at": authoring_spec["frozen_at"],
        "review_ref": str(authoring_spec["review_ref"]),
    }
    _write_bytes_once_or_same(release_root / "manifest.json", _json_bytes(manifest))
    return verify_r1_release(
        release_root, key_root=key_root, lab_root=lab_root, developer_root=developer_root
    )


def _payload_objects(payload: dict[str, Any]) -> tuple[list[Question], list[GroundTruth]]:
    questions = [
        Question.from_dict(_require_object(row, "question"))
        for row in _require_list(payload.get("questions"), "payload questions")
    ]
    truths = [
        GroundTruth.from_dict(_require_object(row, "ground truth"))
        for row in _require_list(payload.get("ground_truth"), "payload ground truth")
    ]
    return questions, truths


def verify_r1_release(
    release_root: Path,
    *,
    key_root: Path | None = None,
    lab_root: Path | None = None,
    developer_root: Path | None = None,
) -> dict[str, Any]:
    manifest = _require_object(load_json(release_root / "manifest.json"), "release manifest")
    validate("benchmark_release", manifest)
    expected_identity = {
        "release_id": R1_RELEASE_ID,
        "schema_version": R1_SCHEMA_VERSION,
        "classification": "real_benchmark",
        "publication_disposition": "blocked",
    }
    if any(manifest.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("R1 release identity or publication boundary changed")
    files = _require_object(manifest.get("files"), "release files")
    verify_files(release_root, cast(dict[str, str], files))
    required_files = {
        "p2_core_edition_aggregate.csv",
        "source_manifest.json",
        "train_payload.json",
        "test_payload.enc",
        "holdout_payload.enc",
        "split_manifest.json",
        "semantic_spec.json",
        "rubric.json",
        "policy.json",
        "source_links.json",
        "protocol_freeze.json",
    }
    if set(files) != required_files:
        raise ValueError("R1 release file inventory changed")
    rows = load_aggregate(
        release_root / "p2_core_edition_aggregate.csv", release_root / "source_manifest.json"
    )
    semantic = _require_object(load_json(release_root / "semantic_spec.json"), "semantic spec")
    validate("semantic_spec", semantic)
    if semantic.get("version") != R1_SCHEMA_VERSION:
        raise ValueError("R1 semantic specification version mismatch")
    rubric = _require_object(load_json(release_root / "rubric.json"), "rubric")
    reviewer = rubric.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer.casefold() == "unreviewed":
        raise ValueError("R1 narrative rubric requires a named reviewer")
    if not set(PROHIBITED_CLAIMS).issubset(
        _require_list(rubric.get("prohibited_claims"), "claims")
    ):
        raise ValueError("R1 narrative rubric omits prohibited claims")
    if rubric != _rubric(reviewer):
        raise ValueError("R1 narrative rubric differs from the frozen review contract")
    policy = _require_object(load_json(release_root / "policy.json"), "policy")
    if policy != _policy(str(manifest["frozen_at"])):
        raise ValueError("R1 selection/cost policy differs from the frozen contract")
    source_links = _require_object(load_json(release_root / "source_links.json"), "source links")
    expected_source_links = {
        "source_evidence_id": SOURCE_EVIDENCE_ID,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "aggregate_sha256": SOURCE_CSV_SHA256,
        "approval_ref": "docs/approvals/P2-CORE-R1-APPROVAL-001.md",
        "task_ref": "tasks/TASK-0002.md",
        "public_redistribution_authorized": False,
    }
    if source_links != expected_source_links:
        raise ValueError("R1 source links or redistribution boundary changed")
    split_manifest = _require_object(
        load_json(release_root / "split_manifest.json"), "split manifest"
    )
    train_payload = _require_object(load_json(release_root / "train_payload.json"), "TRAIN payload")
    train_questions, train_truths = _payload_objects(train_payload)
    if len(train_questions) != 12 or any(
        question.split != Split.TRAIN for question in train_questions
    ):
        raise ValueError("Developer-visible R1 payload must contain exactly 12 TRAIN questions")

    protocol = _require_object(load_json(release_root / "protocol_freeze.json"), "protocol")
    protocol_identity = {
        "release_id": R1_RELEASE_ID,
        "schema_version": R1_SCHEMA_VERSION,
        "classification": "prospective_procedurally_sealed",
        "frozen_at": manifest["frozen_at"],
    }
    if any(protocol.get(key) != value for key, value in protocol_identity.items()):
        raise ValueError("R1 frozen protocol identity mismatch")
    checks = {
        "policy_sha256": file_hash(release_root / "policy.json"),
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "aggregate_sha256": SOURCE_CSV_SHA256,
        "split_manifest_sha256": file_hash(release_root / "split_manifest.json"),
        "train_payload_sha256": file_hash(release_root / "train_payload.json"),
        "semantic_spec_sha256": file_hash(release_root / "semantic_spec.json"),
        "rubric_sha256": file_hash(release_root / "rubric.json"),
    }
    if any(protocol.get(key) != value for key, value in checks.items()):
        raise ValueError("R1 frozen protocol hash mismatch")
    if manifest["selection_rule_sha256"] != protocol["policy_sha256"]:
        raise ValueError("R1 selection policy hash mismatch")
    sealed = _require_object(protocol.get("sealed_payloads"), "sealed payload hashes")
    expected_sealed = {
        "TEST": file_hash(release_root / "test_payload.enc"),
        "HOLDOUT": file_hash(release_root / "holdout_payload.enc"),
    }
    if sealed != expected_sealed:
        raise ValueError("R1 ciphertext hash mismatch")
    if lab_root is not None and protocol.get("dependency_lock_sha256") != file_hash(
        lab_root / "requirements.lock"
    ):
        raise ValueError("R1 dependency-lock hash mismatch")
    if (
        lab_root is not None
        and (release_root / "semantic_spec.json").read_bytes()
        != (lab_root / "semantics/r1_aggregate_v1.json").read_bytes()
    ):
        raise ValueError("R1 release semantic specification differs from its versioned contract")

    if key_root is None:
        _validate_grouping(None, split_manifest)
        return {
            "release_id": R1_RELEASE_ID,
            "classification": "real_benchmark",
            "questions": 24,
            "train_questions": 12,
            "editions": len(rows),
            "hidden_validation": "sealed",
            "integrity": "PASS",
        }
    if developer_root is not None and key_root.resolve().is_relative_to(developer_root.resolve()):
        raise ValueError("Evaluator keys must remain outside the developer checkout")
    payloads = {Split.TRAIN: train_payload}
    for split, filename in (
        (Split.TEST, "test_payload.enc"),
        (Split.HOLDOUT, "holdout_payload.enc"),
    ):
        payloads[split] = _decrypt_payload(
            release_root / filename, key_root / f"{split.value.casefold()}.key"
        )
    questions: list[Question] = []
    truths: list[GroundTruth] = []
    for split, payload in payloads.items():
        if payload.get("release_id") != R1_RELEASE_ID or payload.get("split") != split.value:
            raise ValueError("R1 payload identity mismatch")
        split_questions, split_truths = _payload_objects(payload)
        questions.extend(split_questions)
        truths.extend(split_truths)
    _validate_questions_and_truths(questions, truths, split_manifest, reviewer)
    connection = aggregate_database(rows)
    try:
        for truth in truths:
            if truth.oracle_sql is None:
                continue
            columns, result_rows = query_aggregate(connection, truth.oracle_sql)
            if columns != truth.expected["columns"] or not rows_equal(
                result_rows,
                truth.expected["rows"],
                columns,
                truth.tolerances,
                truth.ordered,
            ):
                raise ValueError(f"R1 oracle mismatch: {truth.question_id}")
    finally:
        connection.close()
    counts = {
        split.value: sum(question.split == split for question in questions) for split in Split
    }
    return {
        "release_id": R1_RELEASE_ID,
        "classification": "real_benchmark",
        "questions": len(questions),
        "splits": counts,
        "editions": len(rows),
        "series": len({row["series_id"] for row in rows}),
        "source_csv_sha256": SOURCE_CSV_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "oracle_reproducibility": "byte-identical",
        "hidden_validation": "decrypted-in-evaluator-custody",
        "integrity": "PASS",
    }
