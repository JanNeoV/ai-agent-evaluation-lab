from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from evaluation.costs import Budget, Quote, cost_per_accepted, money


def quote(name, amount="1", count=1):
    return Quote(name, count, Decimal(amount), Decimal(0), Decimal(0), Decimal(1), "0" * 64)


def admit(budget, q, **kwargs):
    now = datetime.now(UTC)
    return budget.admit(
        q,
        kwargs.get("remaining", Decimal(10)),
        now,
        now + timedelta(days=1),
        kwargs.get("future", Decimal(0)),
    )


def test_pending_reservations_block_overspend(tmp_path):
    budget = Budget(tmp_path / "budget.jsonl")
    admit(budget, quote("first", "6"))
    with pytest.raises(ValueError, match="ceiling"):
        admit(budget, quote("second", "3"))
    assert budget.balances()["committed"] == Decimal(6)


def test_future_hidden_campaign_budget_is_reserved_in_admission(tmp_path):
    with pytest.raises(ValueError):
        admit(Budget(tmp_path / "budget.jsonl"), quote("train", "5"), future=Decimal(4))


def test_trial_balance_and_expiry_are_independent_limits(tmp_path):
    budget = Budget(tmp_path / "budget.jsonl")
    with pytest.raises(ValueError, match="trial balance"):
        admit(budget, quote("first", "1"), remaining=Decimal("2.50"))
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="expired"):
        budget.admit(quote("x"), Decimal(10), now, now - timedelta(seconds=1))
    with pytest.raises(ValueError, match="stale"):
        budget.admit(quote("x"), Decimal(10), now - timedelta(minutes=16), now + timedelta(days=1))


def test_reconciliation_replaces_reservation_not_adds_it(tmp_path):
    budget = Budget(tmp_path / "budget.jsonl")
    admit(budget, quote("first", "3"))
    budget.settle("first", Decimal("2"), "0" * 64)
    assert budget.balances()["committed"] == 2
    with pytest.raises(ValueError):
        budget.settle("first", Decimal("1"), "0" * 64)
    with pytest.raises(ValueError):
        admit(budget, quote("first"))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1"])
def test_nonfinite_or_negative_cost_rejected(value):
    with pytest.raises(ValueError):
        money(value)


def test_no_accepted_answers_has_no_fictitious_free_cost():
    assert cost_per_accepted(Decimal(1), 0) is None


def test_cannot_raise_trial_cap_or_remove_reserve(tmp_path):
    with pytest.raises(ValueError):
        Budget(tmp_path / "b", ceiling=Decimal(41))
    with pytest.raises(ValueError):
        Budget(tmp_path / "b", reserve=Decimal(0))


def test_amended_ceiling_up_to_forty_is_accepted(tmp_path):
    # ADR-0003 -> ADR-0006 -> ADR-0007 -> ADR-0009: USD 10 -> 20 -> 30 -> 40 hard safety ceiling.
    for ceiling in [30, 40]:
        Budget(tmp_path / f"b{ceiling}", ceiling=Decimal(ceiling))
