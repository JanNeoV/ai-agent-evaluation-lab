import copy

import duckdb
import pytest

from evaluation.artifacts import load_json
from evaluation.oracle import database, query, validate_data, verify_release


def test_all_frozen_oracles_reproduce(fixture_root):
    result = verify_release(fixture_root, allow_synthetic=True)
    assert result["questions"] == 24
    assert result["classification"] == "synthetic_fixture"
    with pytest.raises(ValueError, match="Synthetic"):
        verify_release(fixture_root)


def test_calendar_alone_does_not_support_held(fixture_root):
    data = load_json(fixture_root / "data.json")
    data["observation_source"] = [
        e for e in data["observation_source"] if e["field_name"] != "held"
    ]
    with pytest.raises(ValueError, match="Held assertion"):
        validate_data(data)


def test_identity_and_provenance_keys_are_validated(fixture_root):
    original = load_json(fixture_root / "data.json")
    data = copy.deepcopy(original)
    data["event_year"].append(data["event_year"][0])
    with pytest.raises(ValueError, match="duplicate"):
        validate_data(data)
    data = copy.deepcopy(original)
    data["observation_source"][0]["source_id"] = "not-present"
    with pytest.raises(ValueError, match="Orphan"):
        validate_data(data)


def test_only_readonly_oracle_sql(fixture_root):
    connection = database(load_json(fixture_root / "data.json"))
    try:
        with pytest.raises(ValueError):
            query(connection, "DELETE FROM event_year")
        with pytest.raises(ValueError):
            query(connection, "SELECT 1; SELECT 2")
        with pytest.raises(duckdb.PermissionException):
            query(connection, "SELECT * FROM read_csv_auto('C:/private.csv')")
    finally:
        connection.close()
