# ADR-0007: Pre-execution USD 20 to USD 30 hard safety ceiling for Benchmark R1

Status: accepted for Campaign R1; authorized in-session by the account owner immediately before TEST
execution; recorded before any TEST/HOLDOUT disclosure.

## Context

ADR-0006 raised the Benchmark R1 accounting ceiling from USD 10 to USD 20, but the conservative
preflight at that time still showed a USD 1.35 shortfall. Before actually executing TEST, a fresh,
pre-execution reconciliation was run, this time including a component ADR-0006 did not: real LAB_XS
warehouse credits consumed by this session's own reconciliation/administrative work (monitor checks,
`WAREHOUSE_METERING_HISTORY`/`QUERY_HISTORY` lookups, resume) after V3 TRAIN completed — 0.085477778
credits, ≈ USD 0.26. Combined with the unchanged TRAIN and TEST/HOLDOUT projections from ADR-0006, the
full conservative campaign projection is **USD 21.61**, which still exceeds USD 20.

The account owner explicitly pre-authorized one further amendment, to a **hard USD 30 safety
ceiling** — described explicitly as a ceiling, not an expected-spend target — conditioned on: TEST/
HOLDOUT remaining sealed and undisclosed at amendment time, preserving the full USD 10 → USD 20 → USD
30 amendment history and all prior evidence unchanged, no alteration of TEST/HOLDOUT scope/cases/
sealing/ground truth/methodology to fit the budget, executing TEST first, a cost-only reconciliation
after TEST before HOLDOUT, proceeding to HOLDOUT only if the conservative projected total (including
the USD 2 reserve) stays ≤ USD 30, and no ceiling increase above USD 30 without new authorization.

## Decision

1. The Benchmark R1 internal accounting ceiling is amended from **USD 20.00 to USD 30.00**. The USD
   2.00 uncertainty reserve is unchanged. USD 30.00 is a new hard ceiling — a safety bound, not a
   target — and will not be increased again without new, explicit authorization.
2. `release/policy.json` (USD 10, historical) and `release/budget_amendment_v1.json` (USD 10→20,
   historical) are **not modified**. This decision is recorded as a new, separate, hashed artifact,
   `release/budget_amendment_v2.json`, which references both prior artifacts by file hash, preserving
   the complete USD 10 → USD 20 → USD 30 chain.
3. TEST/HOLDOUT scope, case counts (48/12), sealing mechanics, ground truth, and evaluation
   methodology are explicitly unchanged by this amendment — it is a budget-ceiling change only.
4. Execution order is fixed by this amendment: TEST executes first; a cost-only reconciliation runs
   after TEST and before any HOLDOUT execution; HOLDOUT proceeds only if the conservative projected
   total campaign cost (actual to date + bounded remaining + USD 2 reserve) is ≤ USD 30.00; if
   projected to exceed USD 30.00 after TEST, the campaign stops and reports the blocker rather than
   seeking a further increase.

## Evidence basis

Reconciled figures (USD), full chain, actual vs. bounded/estimated kept distinct as in ADR-0006:

| Component | Basis | USD |
|---|---|---|
| TRAIN warehouse | Actual, `WAREHOUSE_METERING_HISTORY` (2.658931936 credits @ ~$3.00/credit, approximate/non-contractual) | 7.98 |
| TRAIN agent-inference (96 calls) | Bounded/estimated cap, not actual (no `request_id` in frozen records) | 2.88 |
| Session/administrative overhead to date | Actual, `WAREHOUSE_METERING_HISTORY` post-TRAIN (0.085477778 credits) | 0.26 |
| Uncertainty reserve | Fixed, unchanged | 2.00 |
| TEST+HOLDOUT (60 calls) warehouse | Projected from TRAIN's empirically observed per-call rate, not the original flat guess | 4.99 |
| TEST+HOLDOUT (60 calls) bounded inference | Bounded/estimated cap | 1.80 |
| TEST+HOLDOUT quote (1.25x forward-quote multiplier) | (4.99+1.80)×1.25 | 8.49 |
| **Total conservative campaign projection** | | **21.61** |

Under USD 20: insufficient by USD 1.61. Under USD 30: **sufficient, USD 8.39 headroom.**

## Alternatives

**Raise the ceiling directly to cover only the exact shortfall (e.g., USD 22).** Rejected: the account
owner explicitly requested a round, hard USD 30 safety ceiling with headroom for the reconciliation's
inherent approximation (non-contractual credit rate, bounded inference), not a tightly fitted number.

**Reduce TEST/HOLDOUT scope or repetitions to fit under USD 20.** Rejected outright per explicit
instruction: budget pressure must never alter sealed scope, cases, ground truth, or methodology.

**Skip the session-overhead line item.** Rejected: it is real, already-incurred, measured cost on the
campaign's designated warehouse; omitting it would understate a conservative preflight, which AGENTS.md
and ADR-0003 both prohibit.

## Consequences

- TEST (TASK-0008) may proceed once TASK-0015 sealing completes, subject to a real, independent
  blocker unrelated to budget: no encrypted TEST/HOLDOUT payload or evaluator key exists anywhere in
  this developer checkout or session filesystem (by design — evaluator custody keys must live outside
  the developer checkout, per AGENTS.md and ADR-0002). This ADR does not and cannot resolve that
  blocker; it only clears the budget gate.
- After TEST, a cost-only reconciliation (this same methodology: actual warehouse + bounded remaining
  inference + USD 2 reserve) must be recomputed before HOLDOUT is authorized to proceed.
- `evaluation/costs.py::Budget.__init__`'s hard-coded `ceiling <= Decimal("10")` invariant must be
  updated to recognize ceilings authorized by ADR-0006/ADR-0007 before `Budget` can be instantiated
  with the amended ceiling in code; this is implemented alongside this ADR since sealing now needs it.
