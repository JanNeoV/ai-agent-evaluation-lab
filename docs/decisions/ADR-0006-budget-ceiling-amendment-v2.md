# ADR-0006: Prospective USD 10 to USD 20 budget ceiling amendment for Benchmark R1

Status: accepted for Campaign R1; authorized in-session by the account owner before any TEST/HOLDOUT
disclosure; recorded before TASK-0015 sealing was attempted.

## Context

The fresh TASK-0015 budget preflight found the account's
the account resource monitor exhausted (4.62/5.00 credits, 90% suspend-immediate threshold
exceeded), suspending all warehouses including `LAB_XS`. The account owner explicitly authorized
raising its `CREDIT_QUOTA` from 5 to 10 credits, and separately, prospectively
authorized raising the Benchmark R1 internal USD accounting ceiling (ADR-0003, `policy.json`) from
USD 10 to USD 20 if a fresh preflight showed USD 10 to be insufficient — subject to: TEST/HOLDOUT
remaining sealed and undisclosed at amendment time, preserving the historical USD 10 record, keeping
the USD 2 reserve unchanged, treating USD 20 as a new hard ceiling not to be raised again without new
authorization, not enabling paid/on-demand billing, and not touching unrelated quotas.

The resource monitor was increased to 10 credits and verified (`SHOW RESOURCE MONITORS`); `LAB_XS`
resumed successfully. A fresh, actual-cost reconciliation was then run against
`SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` for the V0-V3 TRAIN window, replacing the
original flat USD 0.50-per-batch warehouse estimate (`v0..v3/budget_admission.json`) with measured
consumption. See `local/benchmark-r1/R1-001/release/budget_amendment_v1.json` for full figures and
methodology.

## Decision

1. The Benchmark R1 internal accounting ceiling is amended from **USD 10.00 to USD 20.00**. The
   USD 2.00 uncertainty reserve is unchanged. USD 20.00 is a new hard ceiling; it will not be
   increased again without new, explicit authorization.
2. `local/benchmark-r1/R1-001/release/policy.json` is **not rewritten**. Its frozen `cost_ceiling_usd:
   "10.00"` remains the historical record of the original ADR-0003 admission target. This amendment is
   a separate, hashed, versioned artifact — `release/budget_amendment_v1.json` — referencing the
   original policy file's hash, following the same non-destructive amendment pattern ADR-0005 used for
   `protocol_amendment_v2.json` over `protocol_freeze.json`.
3. The amendment is bound to TEST/HOLDOUT still being sealed and undisclosed at the time it was made;
   this was verified (`budget_amendment_v1.json.preconditions_verified`) before this ADR was written.
4. If a future TASK-0015 sealing attempt proceeds while this amendment is in force, the campaign seal
   event must explicitly include `budget_amendment_v1.json`'s hash and the resulting effective USD 20
   ceiling, cryptographically binding the amended budget policy into the sealed campaign before any
   TEST disclosure. No seal has occurred yet under this ADR (see Consequences).

## Evidence basis

Reconciliation distinguishes explicitly between an **actual** and a **bounded/estimated** cost
component, per the account owner's instruction not to label a partly-estimated figure as fully actual:

- **Actual**: LAB_XS warehouse credits measured via `WAREHOUSE_METERING_HISTORY` for the TRAIN window
  = 2.658931936 credits, converted at an approximate, non-contractual USD 3.00/credit (the only
  in-repo reference rate, reproduced from `v0/budget_admission.json`'s own
  `estimated_trial_remaining_usd`/credits ratio; this trial account exposes no rate-sheet/
  usage-in-currency view). Actual warehouse ≈ **USD 7.98**.
- **Bounded, not actual**: per-invocation agent-inference cost stays at the USD 0.03/call conservative
  cap for all 96 TRAIN invocations (**USD 2.88**), because `reconcile_runtime()` requires a
  `request_id` per invocation that the frozen `v0..v3_scored.json` records do not carry — a permanent
  gap (AGENTS.md: "unknown values stay unknown"), not backfilled or defaulted to zero.
- TRAIN total (conservative, mixed actual+bounded, no forward-quote multiplier applied since this
  spend already occurred): **USD 10.86** — already exceeding the original USD 10 ceiling by itself,
  before the USD 2 reserve or any TEST/HOLDOUT cost.
- Projected TEST (48) + HOLDOUT (12) = 60 calls, using the *empirically observed* per-call warehouse
  credit rate from TRAIN (0.0277 credits/call, not the original flat guess that TRAIN evidence just
  showed to be roughly 4x too low): warehouse ≈ USD 4.99, bounded inference USD 1.80, at the existing
  1.25x forward-quote safety multiplier = **USD 8.49**.
- **Total required: USD 21.35** (10.86 + 2.00 + 8.49).

## Consequences

- Under the original USD 10 ceiling: insufficient by USD 11.35.
- **Under the amended USD 20 ceiling: still insufficient, by USD 1.35.** This amendment therefore
  raises the ceiling as authorized but does **not** clear TASK-0015's budget-admission acceptance
  criterion. `Campaign.seal()` was not called. TEST/HOLDOUT remain sealed and undisclosed. TASK-0015
  remains `blocked`, not `done`.
- Per the account owner's explicit instruction, no further ceiling increase is authorized. The exact
  reported blocker (USD 1.35 shortfall against USD 20, driven primarily by realized warehouse
  consumption running ~4x the original flat per-batch estimate) is the basis for any future
  authorization decision.
- The credit-rate approximation (USD 3.00/credit) is a real source of uncertainty: at a materially
  lower unverified rate the amended ceiling could pass. This ADR deliberately does not substitute a
  lower, unverified rate to make the preflight pass — a conservative budget gate must not understate
  cost, and AGENTS.md prohibits tuning a control to force a desired outcome.
- `evaluation/costs.py::Budget.__init__` still hard-codes `ceiling <= Decimal("10")`. That code
  invariant was intentionally left unchanged here, since even the amended USD 20 ceiling does not admit
  the campaign — updating the code to accept a USD 20 ceiling is deferred to when/if additional
  funding evidence is provided, to avoid an unused code change ahead of need.

## Alternatives

**Do not amend the ceiling; report the USD 10 shortfall only.** Rejected: the account owner explicitly
pre-authorized the prospective USD 20 amendment specifically to test whether it would be sufficient;
skipping it would not answer that question.

**Use a lower, more favorable credit-to-USD conversion to make USD 20 pass.** Rejected: no authoritative
rate is available on this trial account, and choosing a lower unverified rate to reach a passing result
would be exactly the kind of gate-tuning AGENTS.md prohibits.

**Silently overwrite `policy.json`'s `cost_ceiling_usd`.** Rejected: this is a real methodological
change, it requires a decision record, and the historical USD 10 figure must be preserved, not erased.
