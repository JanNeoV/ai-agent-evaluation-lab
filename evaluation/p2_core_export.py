"""Public aggregate contract helpers for the historical R1 dataset shape."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from decimal import Decimal

SERIES = (
    "erlangen_middle",
    "erlangen_short",
    "ingolstadt_middle",
    "ingolstadt_olympic",
)

SOURCE_COLUMNS = (
    "layer",
    "source_family",
    "series_id",
    "event",
    "festival_id",
    "state",
    "distance",
    "event_year",
    "era",
    "eligible_finishers",
    "sex_recorded",
    "sex_missing",
    "sex_completeness",
    "female_count",
    "male_count",
    "other_sex_count",
    "female_share_known",
    "age_recorded",
    "age_missing",
    "age_completeness",
    "age_year_difference_count",
    "mean_age_year_difference",
    "median_age_year_difference",
    "age_band_mappable",
    "age_band_unmapped",
    "age_band_mapping_completeness",
    "age_under_30_count",
    "age_30_49_count",
    "age_50_plus_count",
    "share_under_30_mapped",
    "share_30_49_mapped",
    "share_50_plus_mapped",
    "source_file_count",
    "source_files",
)

OUTPUT_COLUMNS = tuple(
    column
    for column in SOURCE_COLUMNS
    if column not in {"layer", "source_family", "source_file_count", "source_files"}
)

STRING_COLUMNS = {"series_id", "event", "festival_id", "state", "distance", "era"}
INTEGER_COLUMNS = {
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
}
DECIMAL_COLUMNS = set(OUTPUT_COLUMNS) - STRING_COLUMNS - INTEGER_COLUMNS
PROPORTION_COLUMNS = {
    "sex_completeness",
    "female_share_known",
    "age_completeness",
    "age_band_mapping_completeness",
    "share_under_30_mapped",
    "share_30_49_mapped",
    "share_50_plus_mapped",
}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _as_int(row: dict[str, str], column: str) -> int:
    value = row[column]
    if not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise ValueError(f"{column} is not a canonical non-negative integer: {value!r}")
    return int(value)


def _as_decimal(row: dict[str, str], column: str) -> Decimal | None:
    value = row[column]
    if value == "":
        return None
    try:
        return Decimal(value)
    except Exception as exc:
        raise ValueError(f"{column} is not a decimal: {value!r}") from exc


def _close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.0000000005")


def validate_rows(rows: list[dict[str, str]]) -> None:
    if len(rows) != 40:
        raise ValueError(f"Expected 40 CORE editions, found {len(rows)}")
    if any(tuple(row) != OUTPUT_COLUMNS for row in rows):
        raise ValueError("Export row schema or column order changed")
    by_series = {series: 0 for series in SERIES}
    keys: set[tuple[str, str]] = set()

    for row in rows:
        if any(row[column] == "" for column in STRING_COLUMNS):
            raise ValueError("Edition identity fields may not be empty")
        if row["series_id"] not in by_series:
            raise ValueError(f"Unexpected CORE series: {row['series_id']}")
        by_series[row["series_id"]] += 1
        key = (row["series_id"], row["event_year"])
        if key in keys:
            raise ValueError(f"Duplicate edition: {key}")
        keys.add(key)

        values = {column: _as_int(row, column) for column in INTEGER_COLUMNS}
        decimals = {column: _as_decimal(row, column) for column in DECIMAL_COLUMNS}
        if values["eligible_finishers"] == 0:
            raise ValueError("An observed edition must contain eligible finishers")
        if values["sex_recorded"] + values["sex_missing"] != values["eligible_finishers"]:
            raise ValueError(f"Sex denominator does not reconcile for {key}")
        if (
            values["female_count"] + values["male_count"] + values["other_sex_count"]
            != values["sex_recorded"]
        ):
            raise ValueError(f"Sex counts do not reconcile for {key}")
        if values["age_recorded"] + values["age_missing"] != values["eligible_finishers"]:
            raise ValueError(f"Age denominator does not reconcile for {key}")
        if (
            values["age_band_mappable"] + values["age_band_unmapped"]
            != values["eligible_finishers"]
        ):
            raise ValueError(f"Age-band denominator does not reconcile for {key}")
        if (
            values["age_under_30_count"] + values["age_30_49_count"] + values["age_50_plus_count"]
            != values["age_band_mappable"]
        ):
            raise ValueError(f"Age-band counts do not reconcile for {key}")
        for column in PROPORTION_COLUMNS:
            value = decimals[column]
            if value is not None and not Decimal(0) <= value <= Decimal(1):
                raise ValueError(f"{column} is outside [0, 1] for {key}")

        ratios = {
            "sex_completeness": Decimal(values["sex_recorded"])
            / Decimal(values["eligible_finishers"]),
            "age_completeness": Decimal(values["age_recorded"])
            / Decimal(values["eligible_finishers"]),
            "age_band_mapping_completeness": Decimal(values["age_band_mappable"])
            / Decimal(values["eligible_finishers"]),
        }
        if values["sex_recorded"]:
            ratios["female_share_known"] = Decimal(values["female_count"]) / Decimal(
                values["sex_recorded"]
            )
        if values["age_band_mappable"]:
            ratios.update(
                {
                    "share_under_30_mapped": Decimal(values["age_under_30_count"])
                    / Decimal(values["age_band_mappable"]),
                    "share_30_49_mapped": Decimal(values["age_30_49_count"])
                    / Decimal(values["age_band_mappable"]),
                    "share_50_plus_mapped": Decimal(values["age_50_plus_count"])
                    / Decimal(values["age_band_mappable"]),
                }
            )
        for column, expected in ratios.items():
            actual = decimals[column]
            if actual is None or not _close(actual, expected):
                raise ValueError(f"{column} does not reconcile for {key}")

    if by_series != {series: 10 for series in SERIES}:
        raise ValueError(f"Expected ten editions per approved CORE series, found {by_series}")
    if sum(_as_int(row, "eligible_finishers") for row in rows) != 13853:
        raise ValueError("CORE eligible-finisher total does not reconcile to 13,853")


def render_csv(rows: list[dict[str, str]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


def parse_export(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
        raise ValueError("Export schema does not match the frozen aggregate schema")
    rows = [dict(row) for row in reader]
    validate_rows(rows)
    return rows
