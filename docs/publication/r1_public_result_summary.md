# R1-001 public result summary

Derived from immutable R1-001 campaign evidence. This summary contains no hidden
question text, ground truth values, or evaluator keys.

## Campaign overview

| Property | Value |
|---|---|
| Campaign ID | R1-001 |
| Model | `claude-haiku-4-5` (Snowflake Cortex Agents) |
| Questions | 24 total: 12 TRAIN / 6 TEST / 6 HOLDOUT |
| Repetitions | 2 per question per candidate |
| Candidates | 4 (V0, V1, V2, V3) |
| Scoring | Deterministic value comparison + human narrative review |
| Hard ceiling | USD 40.00 (amendment chain: 10 → 20 → 30 → 40) |

## TRAIN results (development evidence)

Each candidate had 12 TRAIN questions × 2 repetitions = 24 invocations.

| Candidate | Intervention | Accepted | Critical accepted | Robust successes | Promoted |
|---|---|---|---|---|---|
| V0 | cold start | 0/24 | 0/8 | 0/12 | no |
| V1 | semantic representation | 0/24 | 0/8 | 0/12 | no |
| V2 | instruction and tool description | 1/24 | 0/8 | 0/12 | no |
| V3 | cumulative | 6/24 | 4/8 | 3/12 | no |

V2's single acceptance: R1-Q09 (1 of 2 repetitions passed).
V3's six acceptances: R1-Q09 (2/2), R1-Q21 (2/2), R1-Q22 (2/2).

No candidate was promoted on TRAIN. All four failed the `costs_complete` and `cost`
operational gates (per-invocation cost attribution is permanently unknown).

## TEST results (independent evidence)

6 hidden questions × 4 candidates × 2 repetitions = 48 invocations.

| Metric | Value |
|---|---|
| Planned invocations | 48 |
| Submitted | 48 |
| Completed | 48 |
| Failed | 0 |
| Retries | 0 |
| Discarded | 0 |

| Candidate | TEST accepted (of 24) | TEST critical accepted |
|---|---|---|
| V0 | 0/24 | 0/4 |
| V1 | 0/24 | 0/4 |
| V2 | 0/24 | 0/4 |
| V3 | 0/24 | 0/4 |

**TEST decision: INCONCLUSIVE — no candidate selected.**

All four candidates failed the frozen deterministic comparator on every TEST
invocation. A replayed gate diagnostic confirms no candidate could have passed
the accuracy or critical gates under any cost evidence.

### TEST latency

| Candidate | p50 (ms) | p95 (ms) | max (ms) |
|---|---|---|---|
| V0 | 30,266 | 54,422 | 54,422 |
| V1 | 16,477 | 20,703 | 20,703 |
| V2 | 26,750 | 60,719 | 60,719 |
| V3 | 17,735 | 39,922 | 39,922 |

### TEST cost

| Component | USD |
|---|---|
| Cortex agent inference (actual billed) | 1.8775 |
| LAB_XS warehouse (actual billed) | 1.5895 |
| **TEST batch total** | **3.4670** |
| Pre-execution quote | 9.5774 |

## HOLDOUT (unused)

| Metric | Value |
|---|---|
| Invocations authorized | 12 (if a candidate had been selected) |
| Invocations executed | 0 |
| HOLDOUT key accessed | no |
| HOLDOUT ciphertext fetched | no |
| HOLDOUT ciphertext decrypted | no |
| Disclosure events | 0 |
| Reason | TEST selected no candidate; state is `TEST_REVEALED`, not `RC_SELECTED` |

HOLDOUT questions remain hidden and uncontaminated for potential future use.

## Campaign cost

| Component | Category | USD |
|---|---|---|
| Setup and smoke — warehouse | actual billed | 0.3976 |
| Setup and smoke — agent inference | allocated | 0.3575 |
| TRAIN — warehouse | actual billed | 12.3670 |
| TRAIN — agent inference | allocated | 3.8137 |
| TEST — warehouse | actual billed | 2.3650 |
| TEST — agent inference | actual billed | 1.8776 |
| HOLDOUT | actual billed | 0.0000 |
| Post-settlement residual | unresolved | 0.7756 |
| **Frozen-basis total** | | **21.1784** |

| Budget metric | Value |
|---|---|
| Hard ceiling | USD 40.00 |
| Reserve | USD 2.00 |
| Headroom remaining | USD 16.82 |
| Within ceiling | yes |
| Cost per accepted answer (TEST) | undefined (zero accepted) |

Total trial spend (including coding-agent tooling outside the frozen basis):
at least USD 194.41. The USD 158.06 coding-agent component is disclosed separately
and is not part of the experimental cost basis.

## Evidence classification

| Category | Content | Status |
|---|---|---|
| Development evidence | TRAIN invocations, assessments, iterative candidate changes | Complete, immutable |
| Independent TEST evidence | 48 sealed invocations, deterministic comparison, batch cost | Complete, immutable |
| Unused HOLDOUT evidence | 6 hidden questions, encrypted payloads, evaluator key | Intact, never accessed |

## Reproducibility

Three independent offline replays reproduced the machine-readable manifest and the
Markdown report byte-for-byte without invoking any cloud service.

The synthetic fixture lifecycle (120 + 12 invocations) can be reproduced entirely
offline using the public repository. The real R1-001 campaign requires the private
dataset and Snowflake account configuration which are not distributed.
