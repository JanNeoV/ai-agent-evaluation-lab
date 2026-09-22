import jsonschema
import pytest

from evaluation.contracts import FORMAT_CHECKER


@pytest.mark.parametrize("value", ["not-a-date", "2026-09-19T08:30:00", "2026-09-19"])
def test_manifest_timestamps_require_a_valid_timezone(value):
    with pytest.raises(jsonschema.exceptions.FormatError):
        FORMAT_CHECKER.check(value, "date-time")


@pytest.mark.parametrize("value", ["2026-09-19T08:30:00Z", "2026-09-19T10:30:00+02:00"])
def test_manifest_timestamps_accept_explicit_zones(value):
    FORMAT_CHECKER.check(value, "date-time")
