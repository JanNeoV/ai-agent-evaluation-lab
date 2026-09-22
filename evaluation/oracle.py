"""Frozen relational oracle and benchmark admission checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from evaluation.artifacts import load_json, verify_files
from evaluation.comparators import rows_equal
from evaluation.contracts import GroundTruth, Question, validate, validate_splits

TABLES = {
    "event": [
        ("race_id", "VARCHAR"),
        ("display_name", "VARCHAR"),
        ("identity_basis", "VARCHAR"),
        ("source_identity_ref", "VARCHAR"),
    ],
    "event_year": [
        ("race_id", "VARCHAR"),
        ("event_year", "INTEGER"),
        ("state_code", "VARCHAR"),
        ("scheduled", "BOOLEAN"),
        ("held", "BOOLEAN"),
        ("abnormal_termination", "BOOLEAN"),
        ("status_flags", "JSON"),
        ("identity_review_state", "VARCHAR"),
    ],
    "coverage": [
        ("state_code", "VARCHAR"),
        ("event_year", "INTEGER"),
        ("calendar_coverage", "VARCHAR"),
        ("held_verification_coverage", "VARCHAR"),
        ("exit_coverage", "VARCHAR"),
        ("participant_coverage", "VARCHAR"),
        ("price_coverage", "VARCHAR"),
        ("coverage_note", "VARCHAR"),
    ],
    "source": [
        ("source_id", "VARCHAR"),
        ("citation", "VARCHAR"),
        ("source_kind", "VARCHAR"),
        ("publication_date", "VARCHAR"),
        ("public_locator", "VARCHAR"),
        ("source_fingerprint", "VARCHAR"),
        ("redistribution_disposition", "VARCHAR"),
    ],
    "observation_source": [
        ("evidence_id", "VARCHAR"),
        ("race_id", "VARCHAR"),
        ("event_year", "INTEGER"),
        ("field_name", "VARCHAR"),
        ("source_id", "VARCHAR"),
        ("relation", "VARCHAR"),
        ("source_locator", "VARCHAR"),
        ("review_ref", "VARCHAR"),
    ],
}


def database(data: dict[str, list[dict[str, Any]]]) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    for table, columns in TABLES.items():
        connection.execute(
            f"CREATE TABLE {table} ("
            + ", ".join(f'"{name}" {kind}' for name, kind in columns)
            + ")"
        )
        rows = data.get(table, [])
        if rows:
            connection.executemany(
                f"INSERT INTO {table} VALUES (" + ", ".join("?" for _ in columns) + ")",
                [
                    [
                        json.dumps(row[name], ensure_ascii=False) if kind == "JSON" else row[name]
                        for name, kind in columns
                    ]
                    for row in rows
                ],
            )
    # No network or external-file access during oracle execution.
    connection.execute("SET enable_external_access=false")
    return connection


def query(connection: duckdb.DuckDBPyConnection, sql: str) -> tuple[list[str], list[list[Any]]]:
    statements = connection.extract_statements(sql)
    if len(statements) != 1 or str(statements[0].type) != "StatementType.SELECT":
        raise ValueError("Oracle SQL must be one read-only SELECT")
    result = connection.execute(sql)
    columns = [str(c[0]) for c in result.description]
    rows = [list(row) for row in result.fetchall()]
    return columns, rows


def validate_data(data: dict[str, list[dict[str, Any]]]) -> None:
    if set(data) != set(TABLES):
        raise ValueError("Dataset must contain the five canonical tables")
    keys = {
        "event": ("race_id",),
        "event_year": ("race_id", "event_year"),
        "coverage": ("state_code", "event_year"),
        "source": ("source_id",),
        "observation_source": ("evidence_id",),
    }
    for table, columns in TABLES.items():
        observed: set[tuple[Any, ...]] = set()
        for row in data[table]:
            if set(row) != {name for name, _ in columns}:
                raise ValueError(f"Unexpected columns in {table}")
            key = tuple(row[col] for col in keys[table])
            if None in key or key in observed:
                raise ValueError(f"Missing or duplicate key in {table}")
            observed.add(key)
    events = {row["race_id"] for row in data["event"]}
    sources = {row["source_id"] for row in data["source"]}
    event_years = {(row["race_id"], row["event_year"]) for row in data["event_year"]}
    for row in data["event_year"]:
        if row["race_id"] not in events:
            raise ValueError("Unknown race identity")
        for field in ["scheduled", "held", "abnormal_termination"]:
            if row[field] is not None and type(row[field]) is not bool:
                raise ValueError("Unknown Boolean cannot be zero, empty string or text")
        if row["held"] is True and not any(
            e["race_id"] == row["race_id"]
            and e["event_year"] == row["event_year"]
            and e["field_name"] == "held"
            and e["relation"] == "supports"
            for e in data["observation_source"]
        ):
            raise ValueError("Held assertion has no supporting evidence")
    for row in data["observation_source"]:
        if (row["race_id"], row["event_year"]) not in event_years or row[
            "source_id"
        ] not in sources:
            raise ValueError("Orphan provenance relationship")


def verify_release(root: Path, *, allow_synthetic: bool = False) -> dict[str, Any]:
    manifest = load_json(root / "manifest.json")
    validate("benchmark_release", manifest)
    if manifest["schema_version"] == "r1.aggregate.v1":
        from evaluation.r1 import verify_r1_release

        return verify_r1_release(root)
    if not {"data.json", "questions.json", "ground_truth.json"}.issubset(manifest["files"]):
        raise ValueError("Manifest must hash data, questions and ground truth")
    synthetic = manifest["classification"] == "synthetic_fixture"
    if synthetic and not allow_synthetic:
        raise ValueError("Synthetic fixture cannot be admitted as a real benchmark")
    if not synthetic and (
        manifest["publication_disposition"] != "approved"
        or not manifest["review_ref"]
        or not manifest["source_snapshot_refs"]
    ):
        raise ValueError("Real benchmark has no approved export evidence")
    verify_files(root, manifest["files"])
    data = load_json(root / "data.json")
    validate_data(data)
    questions = [Question.from_dict(row) for row in load_json(root / "questions.json")]
    validate_splits(questions)
    if not synthetic and any(q.origin == "synthetic_fixture" for q in questions):
        raise ValueError("Fixture questions in a real benchmark")
    truths = [GroundTruth.from_dict(row) for row in load_json(root / "ground_truth.json")]
    if {q.question_id for q in questions} != {t.question_id for t in truths} or len(truths) != len(
        questions
    ):
        raise ValueError("Ground truth coverage mismatch")
    connection = database(data)
    try:
        for truth in truths:
            if truth.reviewer == "unreviewed":
                raise ValueError("Ground truth requires review")
            if truth.oracle_sql:
                columns, rows = query(connection, truth.oracle_sql)
                if columns != truth.expected["columns"] or not rows_equal(
                    rows, truth.expected["rows"], columns, truth.tolerances, truth.ordered
                ):
                    raise ValueError(f"Oracle mismatch: {truth.question_id}")
    finally:
        connection.close()
    return {
        "release_id": manifest["release_id"],
        "classification": manifest["classification"],
        "questions": len(questions),
        "event_years": len(data["event_year"]),
        "integrity": "PASS",
    }
