import copy
import json

import pytest

from evaluation.comparators import cell_equal, compare, parse_answer, rows_equal
from evaluation.contracts import GroundTruth


@pytest.mark.parametrize(
    "actual,expected",
    [(0, None), (False, None), (False, 0), (True, 1), ("1", 1), (1.0, 1), ([], None)],
)
def test_unknowns_and_types_are_not_coerced(actual, expected):
    assert not cell_equal(actual, expected, None)


def test_bag_comparison_retains_multiplicity():
    assert rows_equal([[1], [1], [2]], [[2], [1], [1]], ["n"], {}, False)
    assert not rows_equal([[1], [2], [2]], [[2], [1], [1]], ["n"], {}, False)
    assert not rows_equal([[1], [2]], [[2], [1]], ["n"], {}, True)


def test_tolerance_bands_use_matching_not_greedy():
    assert rows_equal([[1.0], [0.0]], [[0.0], [2.0]], ["n"], {"n": "1"}, False)
    assert not cell_equal("1", 1, "0.1")


@pytest.mark.parametrize(
    "text",
    [
        '{"status":NaN}',
        '{"status":"a","status":"b"}',
        'preface {"status":"answered"}',
        "null",
        "[]",
    ],
)
def test_parser_rejects_ambiguous_contracts(text):
    with pytest.raises(ValueError):
        parse_answer(text)


def test_null_is_not_zero_in_complete_answer(truths):
    truth = truths["SYN-Q19"]
    answer = copy.deepcopy(truth.expected)
    assert compare(json.dumps(answer), truth).deterministic_pass
    answer["rows"] = [[0]]
    assert compare(json.dumps(answer), truth).errors == ("WRONG_VALUE",)


def test_caveat_evidence_and_units_fail_independently(truths):
    truth = truths["SYN-Q21"]
    answer = copy.deepcopy(truth.expected)
    answer["caveats"] = []
    answer["evidence_ids"] = []
    answer["units"] = {"evidence_id": "EUR"}
    assert set(compare(json.dumps(answer), truth).errors) == {
        "MISSING_CAVEAT",
        "UNSUPPORTED_PROVENANCE",
        "WRONG_UNITS",
    }


def test_format_failure_is_not_repaired(truths):
    assert compare("answer: 42", truths["SYN-Q01"]).errors == ("FORMAT_INVALID",)


def test_alternative_evidence_support_is_accepted(truths):
    base = truths["SYN-Q21"]
    truth = GroundTruth(
        base.question_id,
        base.expected,
        base.oracle_sql,
        evidence_alternatives=(("E-1-2021-held",), ("other",)),
    )
    answer = copy.deepcopy(base.expected)
    answer["evidence_ids"] = ["other"]
    assert compare(json.dumps(answer), truth).deterministic_pass


def test_row_width_and_duplicate_columns_rejected(truths):
    answer = copy.deepcopy(truths["SYN-Q01"].expected)
    answer["columns"] = ["x", "x"]
    with pytest.raises(ValueError):
        parse_answer(json.dumps(answer))
