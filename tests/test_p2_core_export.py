from __future__ import annotations

from evaluation.p2_core_export import (
    OUTPUT_COLUMNS,
    SERIES,
    parse_export,
    render_csv,
    validate_rows,
)


def _synthetic_rows() -> list[dict[str, str]]:
    """Labeled synthetic fixture with the production shape, never observed P2 values."""
    rows: list[dict[str, str]] = []
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
    return rows


def test_synthetic_aggregate_contract_round_trips_byte_exactly() -> None:
    rows = _synthetic_rows()
    validate_rows(rows)
    content = render_csv(rows)
    assert parse_export(content) == rows
    header = content.splitlines()[0].decode("utf-8").split(",")
    assert header == list(OUTPUT_COLUMNS)
    assert "source_files" not in header
    assert "source_file_count" not in header
    assert "layer" not in header


def test_synthetic_aggregate_contract_rejects_reconciliation_change() -> None:
    rows = _synthetic_rows()
    rows[0]["sex_missing"] = "1"
    try:
        validate_rows(rows)
    except ValueError as exc:
        assert "Sex denominator does not reconcile" in str(exc)
    else:
        raise AssertionError("Invalid synthetic aggregate unexpectedly passed")
