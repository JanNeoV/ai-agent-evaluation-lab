"""Conservative batch admission and append-only reconciliation in USD equivalents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from evaluation.artifacts import Ledger, exclusive_lock


def money(value: str | Decimal) -> Decimal:
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("Cost must be a finite nonnegative decimal")
    return result


@dataclass(frozen=True)
class Quote:
    batch_id: str
    invocation_count: int
    per_invocation_usd: Decimal
    warehouse_usd: Decimal
    judge_usd: Decimal
    multiplier: Decimal
    rate_card_hash: str

    def total(self) -> Decimal:
        for value in [self.per_invocation_usd, self.warehouse_usd, self.judge_usd, self.multiplier]:
            money(value)
        if self.invocation_count < 0 or self.multiplier < 1:
            raise ValueError("Invalid batch estimate")
        return (
            self.per_invocation_usd * self.invocation_count + self.warehouse_usd + self.judge_usd
        ) * self.multiplier


class Budget:
    def __init__(
        self, path: Path, ceiling: Decimal = Decimal("10.00"), reserve: Decimal = Decimal("2.00")
    ):
        self.ledger = Ledger(path)
        self.ceiling = money(ceiling)
        self.reserve = money(reserve)
        # USD 10 -> 20 -> 30 -> 40 ceiling amendment chain: ADR-0003, ADR-0006, ADR-0007, ADR-0009.
        # USD 40 is a hard safety ceiling, not a spend target; raise only with a new decision
        # record.
        if self.ceiling > Decimal("40") or self.reserve < Decimal("2"):
            raise ValueError("Benchmark R1 budget cannot exceed USD 40 or reduce USD 2 reserve")

    def balances(self) -> dict[str, Any]:
        pending: dict[str, Decimal] = {}
        settled: dict[str, Decimal] = {}
        for event in self.ledger.read():
            row = event["payload"]
            if event["kind"] == "reserve":
                pending[row["batch_id"]] = money(row["usd"])
            elif event["kind"] == "settle":
                pending.pop(row["batch_id"], None)
                settled[row["batch_id"]] = money(row["usd"])
        return {
            "pending": pending,
            "settled": settled,
            "committed": sum(pending.values(), Decimal(0)) + sum(settled.values(), Decimal(0)),
        }

    def admit(
        self,
        quote: Quote,
        trial_remaining: Decimal,
        observed_at: datetime,
        expires_at: datetime,
        future_required: Decimal = Decimal(0),
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        if observed_at.tzinfo is None or expires_at.tzinfo is None:
            raise ValueError("Budget timestamps must be timezone-aware")
        if observed_at > now or now - observed_at > timedelta(minutes=15):
            raise ValueError("Trial balance snapshot is stale or future-dated")
        if expires_at <= now:
            raise ValueError("Trial has expired")
        amount = quote.total()
        with exclusive_lock(self.ledger.path.with_suffix(".budget.lock")):
            balance = self.balances()
            if quote.batch_id in balance["pending"] or quote.batch_id in balance["settled"]:
                raise ValueError("Batch already reserved; use its existing reservation")
            required = amount + money(future_required) + self.reserve
            if balance["committed"] + required > self.ceiling:
                raise ValueError("Budget ceiling would be exceeded")
            if sum(balance["pending"].values(), Decimal(0)) + required > money(trial_remaining):
                raise ValueError("Insufficient trial balance")
            payload = {
                "batch_id": quote.batch_id,
                "usd": str(amount),
                "invocation_count": quote.invocation_count,
                "rate_card_hash": quote.rate_card_hash,
                "trial_remaining_usd": str(trial_remaining),
                "observed_at": observed_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "future_required_usd": str(future_required),
            }
            self.ledger.append("reserve", payload)
            return payload

    def settle(self, batch_id: str, actual: Decimal, evidence_hash: str) -> None:
        with exclusive_lock(self.ledger.path.with_suffix(".budget.lock")):
            balance = self.balances()
            if batch_id not in balance["pending"]:
                raise ValueError("No outstanding reservation")
            self.ledger.append(
                "settle",
                {
                    "batch_id": batch_id,
                    "usd": str(money(actual)),
                    "evidence_hash": evidence_hash,
                    "over_estimate": actual > balance["pending"][batch_id],
                },
            )


def cost_per_accepted(total: Decimal, accepted: int) -> Decimal | None:
    return money(total) / accepted if accepted > 0 else None
