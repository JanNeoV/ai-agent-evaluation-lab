# ADR-0009: Prospective budget ceiling amendment v4, USD 30 to USD 40

Status: accepted for Campaign R1 before any TEST execution or TEST plaintext access.

## Context

TASK-0008's second round passed every non-budget gate — seal integrity (the original TASK-0015
artifacts were recovered byte-for-byte, so no reseal was needed), execution provenance, TEST
ciphertext hash, all four candidate mappings and fingerprints verified live, `LAB_RUNTIME`
permissions, warehouse availability, resource-monitor headroom, and the 48-row schedule replay — and
then failed the budget gate.

The failure was caused by better evidence, not by scope change.
`SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY` became available and is authoritative: its
per-service USD reconciles exactly to the trial free-usage-balance movement
(386.02 → 205.59 = 180.43 on 2026-09-20). It establishes real billed rates of **USD 4.6511 per
warehouse credit** and **USD 1.9971 per Cortex agent credit**. Every prior round used an approximate,
non-contractual USD 3.00 per credit because no rate card was available, which understated warehouse
cost by roughly 55 percent. Re-running the frozen `budget_amendment_v2.json` reconciliation
methodology — unchanged — against the corrected rates gives **USD 30.9043 required against the
USD 30.00 hard ceiling**, short by USD 0.9043.

`release/test_preflight_cost_reconciliation_v1.json` (sha256
`715478664cc69937eeccb2c06f8dfb232f0b61d06116251cf87a6b6e929a72d1`) records that preflight, including
the unresolved LAB_XS warehouse attribution question: applying the observed rate to LAB_XS credits
gives USD 12.7628 and a total of USD 30.9043, while pro-rating billed warehouse USD by LAB_XS's
35.72 percent share of all warehouse credits gives USD 11.4768 and a total of USD 29.6182. Both
readings fall inside the USD 2.00 uncertainty reserve band around the old ceiling.

## Decision

The account owner authorized, prospectively and explicitly, one further amendment raising the
Benchmark R1 hard ceiling from **USD 30.00 to USD 40.00**, before any TEST execution or TEST
plaintext access.

1. **Ceiling.** USD 40.00 becomes the hard safety ceiling for Campaign R1. It is explicitly **not a
   spend target**. It must not be raised again without new explicit authorization.
2. **Reserve.** The USD 2.00 uncertainty reserve is unchanged.
3. **Chain preserved.** The full history USD 10 → USD 20 → USD 30 → USD 40 is preserved. No prior
   policy, ADR, budget artifact, or reconciliation is rewritten or deleted:
   `release/policy.json` (sha256 `9ce58b4d…15a6ea`) still records the original USD 10.00;
   `budget_amendment_v1.json` (sha256 `cd534c5a…0fd1bf9`) still records USD 10 → 20;
   `budget_amendment_v2.json` (sha256 `03ef8a1c…8cb67989`) still records USD 20 → 30. Each is
   referenced by file hash from the new artifact.
4. **Methodology unchanged.** The frozen cost-attribution methodology in
   `budget_amendment_v2.json.reconciliation_methodology` is **not** altered. In particular the
   per-call warehouse rate stays at the frozen `0.02769720766` credits per call and is **not**
   re-derived on a marginal basis to fit any ceiling. Only the USD-per-credit rates are corrected,
   because authoritative billed rates now exist where previously only an approximation did.
5. **Cost categories stay distinct.** Actual/billed, bounded, estimated, and allocated components are
   recorded separately and never merged. Where a component was previously bounded and is now actual,
   the actual replaces the bound only when the actual is the higher, conservative figure — as with
   TRAIN agent inference, where the actual USD 4.1713 supersedes the USD 2.88 bound.
6. **Admissibility.** The current conservative projection of USD 30.9043 is admissible under
   USD 40.00, with USD 9.0957 of headroom.
7. **Scope unchanged.** TEST remains exactly 48 calls, HOLDOUT exactly 12 for exactly one selected
   candidate, two repetitions, concurrency one, no retries, no discarded failures. Candidates V0-V3,
   the sealed schedule, the comparator, the rubric, the oracle, the gates, the thresholds, the
   tie-break order, and `POLICY`/`policy_sha256` are untouched. No V4 exists.
8. **Attribution question stays open.** This amendment does not resolve the LAB_XS attribution
   question in the campaign's favour. It makes the campaign fundable under either reading, so the
   ambiguity no longer decides execution and remains recorded as unresolved for final reporting.

## Alternatives

**Resolve the attribution question instead.** Accepting the pro-rata reading would have given
USD 29.6182 and fitted the old ceiling. Rejected as the primary route: choosing the cost
interpretation that makes a campaign affordable, at the moment it becomes affordability-decisive, is
motivated reasoning even when the interpretation is defensible. Raising the ceiling with explicit
authorization is honest; reinterpreting evidence to fit a ceiling is not.

**Stop the campaign.** Rejected by the account owner, who holds the budget authority and has
authorized the amendment prospectively.

**Reduce candidates, repetitions, or the 48-call denominator.** Forbidden by ADR-0004: insufficient
funding stops the campaign rather than reducing scope.

## Consequences

- `evaluation/costs.py::Budget.__init__` raises its hard cap from USD 30 to USD 40 and still refuses
  anything above it or a reserve below USD 2.00. `tests/test_budget.py` is updated so the
  "cannot raise cap" probe sits at USD 41 and USD 40 is accepted.
- Warehouse and agent USD-per-credit rates are now derived from
  `ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY` rather than the earlier approximation, and the source
  is recorded with each figure. The rate remains non-contractual.
- Coding-agent tooling spend (`SNOWFLAKE_COCO_SNOWSIGHT`, `SNOWFLAKE_COCO_CLI`) and non-`LAB_XS`
  Snowsight worksheet compute remain outside the frozen R1 admission basis and continue to be
  disclosed separately. Total trial spend is far above the R1 evaluation ceiling and must be reported
  as such; it is neither folded into nor removed from the gate.
- If actual or conservatively projected campaign cost on the frozen basis would exceed USD 40.00, the
  campaign stops again rather than seeking a further increase.
