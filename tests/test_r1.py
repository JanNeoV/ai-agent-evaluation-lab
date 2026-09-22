from __future__ import annotations

import copy
from decimal import Decimal

import duckdb
import pytest

from evaluation.p2_core_export import (
    DECIMAL_COLUMNS,
    INTEGER_COLUMNS,
    OUTPUT_COLUMNS,
    SERIES,
    STRING_COLUMNS,
    render_csv,
    sha256_bytes,
)
from evaluation.r1 import (
    R1_RELEASE_ID,
    aggregate_database,
    build_plain_payloads,
    load_aggregate,
    parse_aggregate,
    query_aggregate,
)


def synthetic_csv_and_manifest():
    """Labeled synthetic aggregate with the production contract, never observed P2 values."""
    rows = []
    for series_index, series in enumerate(SERIES):
        for edition_index in range(10):
            eligible = 359 if (series_index, edition_index) == (3, 9) else 346
            values = {
                "series_id": series,
                "event": f"Synthetic Event {series_index}",
                "festival_id": f"SYNTHETIC_{series_index}",
                "state": "Synthetic State",
                "distance": "synthetic_distance",
                "event_year": str(2000 + edition_index),
                "era": "synthetic_era",
                "eligible_finishers": str(eligible),
                "sex_recorded": str(eligible),
                "sex_missing": "0",
                "sex_completeness": "1.000000000",
                "female_count": "0",
                "male_count": str(eligible),
                "other_sex_count": "0",
                "female_share_known": "0.000000000",
                "age_recorded": str(eligible),
                "age_missing": "0",
                "age_completeness": "1.000000000",
                "age_year_difference_count": "0",
                "mean_age_year_difference": "",
                "median_age_year_difference": "",
                "age_band_mappable": str(eligible),
                "age_band_unmapped": "0",
                "age_band_mapping_completeness": "1.000000000",
                "age_under_30_count": "0",
                "age_30_49_count": str(eligible),
                "age_50_plus_count": "0",
                "share_under_30_mapped": "0.000000000",
                "share_30_49_mapped": "1.000000000",
                "share_50_plus_mapped": "0.000000000",
            }
            rows.append({column: values[column] for column in OUTPUT_COLUMNS})
    content = render_csv(rows)
    schema = []
    for column in OUTPUT_COLUMNS:
        kind = (
            "string"
            if column in STRING_COLUMNS
            else "integer"
            if column in INTEGER_COLUMNS
            else "decimal"
        )
        schema.append({"name": column, "type": kind, "nullable": column in DECIMAL_COLUMNS})
    manifest = {
        "export": {
            "sha256": sha256_bytes(content),
            "row_count": 40,
            "column_count": 30,
            "series_count": 4,
            "schema": schema,
        },
        "scope": {
            "external_replication_included": False,
            "participant_or_finisher_rows_included": False,
            "names_or_personal_data_included": False,
            "row_identifiers_included": False,
            "source_locators_or_raw_documents_included": False,
        },
        "unknown_value_policy": "Synthetic unknowns remain null.",
    }
    return content, manifest


def synthetic_authoring():
    categories = [
        "lookup",
        "aggregation",
        "temporal",
        "ranking_ratio",
        "missingness",
        "scope_provenance",
    ]
    splits = ["TRAIN", "TRAIN", "TEST", "HOLDOUT"]
    items = []
    number = 0
    for category in categories:
        for split in splits:
            number += 1
            suffix = f"{number:02}"
            items.append(
                {
                    "question": {
                        "question_id": f"SYN-R1-Q{suffix}",
                        "intent_id": f"SYN-R1-I{suffix}",
                        "leakage_group_id": f"SYN-R1-L{suffix}",
                        "language": "de",
                        "text": f"Synthetische Vertragsfrage {suffix}?",
                        "category": category,
                        "difficulty": "easy",
                        "critical": category in {"missingness", "scope_provenance"},
                        "split": split,
                        "origin": "synthetic_fixture",
                    },
                    "translation_group_id": f"SYN-R1-T{suffix}",
                    "paraphrase_group_id": f"SYN-R1-P{suffix}",
                    "entity_substitution_group_id": f"SYN-R1-E{suffix}",
                    "status": "answered",
                    "oracle_sql": "SELECT COUNT(*) AS edition_count FROM p2_core_edition",
                    "units": {"edition_count": "Ausgaben"},
                    "ordered": False,
                    "tolerances": {},
                    "explanation_de": "Synthetische Vertragsantwort.",
                }
            )
    return {
        "release_id": R1_RELEASE_ID,
        "reviewer": "synthetic_programmatic_reviewer",
        "review_ref": "synthetic-only",
        "frozen_at": "2026-09-19T00:00:00+00:00",
        "grouping_version": "synthetic-r1-grouping",
        "split_seed": 1,
        "items": items,
    }


def test_r1_aggregate_is_typed_and_does_not_use_legacy_tables():
    content, manifest = synthetic_csv_and_manifest()
    rows = parse_aggregate(content, manifest)
    assert len(rows) == 40
    assert rows[0]["eligible_finishers"] == 346
    assert rows[0]["mean_age_year_difference"] is None
    assert rows[0]["sex_completeness"] == Decimal("1.000000000")
    connection = aggregate_database(rows)
    try:
        columns, result = query_aggregate(
            connection,
            "SELECT COUNT(*) AS editions, SUM(eligible_finishers) AS finishers "
            "FROM p2_core_edition",
        )
        assert columns == ["editions", "finishers"]
        assert result == [[40, 13853]]
        with pytest.raises(duckdb.CatalogException):
            connection.execute("SELECT * FROM event_year")
    finally:
        connection.close()


def test_r1_null_is_not_reinterpreted_as_zero():
    content, manifest = synthetic_csv_and_manifest()
    altered = content.replace(b",0,,,346,", b",0,0.000000000,,346,", 1)
    manifest["export"]["sha256"] = sha256_bytes(altered)
    with pytest.raises(ValueError, match="must be null"):
        parse_aggregate(altered, manifest)


def test_r1_production_loader_rejects_unapproved_hashes(tmp_path):
    content, manifest = synthetic_csv_and_manifest()
    csv_path = tmp_path / "aggregate.csv"
    manifest_path = tmp_path / "source_manifest.json"
    csv_path.write_bytes(content)
    import json

    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="approved CSV hash"):
        load_aggregate(csv_path, manifest_path)


def test_r1_oracle_payloads_are_byte_deterministic():
    content, manifest = synthetic_csv_and_manifest()
    rows = parse_aggregate(content, manifest)
    authoring = synthetic_authoring()
    first = build_plain_payloads(rows, authoring)
    second = build_plain_payloads(rows, copy.deepcopy(authoring))
    assert first == second
    payloads, split_manifest = first
    assert {split.value: len(payload["questions"]) for split, payload in payloads.items()} == {
        "TRAIN": 12,
        "TEST": 6,
        "HOLDOUT": 6,
    }
    assert len(split_manifest["assignments"]) == 24


@pytest.mark.parametrize("failure", ["leakage", "scope", "reviewer", "count"])
def test_r1_authoring_fail_closed(failure):
    content, manifest = synthetic_csv_and_manifest()
    rows = parse_aggregate(content, manifest)
    authoring = synthetic_authoring()
    if failure == "leakage":
        authoring["items"][2]["question"]["leakage_group_id"] = authoring["items"][0]["question"][
            "leakage_group_id"
        ]
    elif failure == "scope":
        authoring["items"][0]["question"]["text"] = "Wie viele gibt es in ganz Deutschland?"
    elif failure == "reviewer":
        authoring["reviewer"] = "unreviewed"
    else:
        authoring["items"].pop()
    with pytest.raises(ValueError):
        build_plain_payloads(rows, authoring)
