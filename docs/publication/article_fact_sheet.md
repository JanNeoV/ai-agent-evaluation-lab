# Article Fact Sheet — TASK-0019

Authoritative source for the Medium article and all public-facing claims.
Use only the numbers and claims documented here.

## Problem

Analytical AI agents are easy to improve on development questions but the
improvement often does not survive independent evaluation. This project asks
whether inexpensive Haiku-guided development produces durable improvements
that transfer to a stronger model on genuinely unseen questions.

## Method

**Design:** 2×2 factorial — (cold-start, improved) × (claude-haiku-4-5, claude-sonnet-4-6)

**Question roles:**

| Role | Count | Usage |
|------|-------|-------|
| TRAIN | 12 | Active Haiku development |
| REGRESSION / DEV-VALIDATION | 6 | Previously opened R1 TEST; used to detect overfitting |
| Fresh sealed TEST | 10 | Curated and procedurally sealed before development |
| HOLDOUT | 6 | Sealed until final confirmatory stage |

**Workflow:** Procedurally sealed in a solo workflow, not independently blinded.

- TRAIN was used for active development.
- Previously opened R1 TEST questions were reclassified as REGRESSION evidence.
- A fresh TEST set was curated and procedurally sealed before development.
- HOLDOUT remained sealed until the final confirmatory stage.
- Once TEST was opened, development stopped permanently.
- No agent was modified after TEST or HOLDOUT.

**Agent configurations:**

| Config | Model | Semantic View | Instructions |
|--------|-------|---------------|-------------|
| H0 | claude-haiku-4-5 | Dimensions-only | Minimal (JSON schema only) |
| H1 | claude-haiku-4-5 | Dimensions + 23 metrics | Rich analytical guidance |
| S0 | claude-sonnet-4-6 | Dimensions-only | Minimal (JSON schema only) |
| S1 | claude-sonnet-4-6 | Dimensions + 23 metrics | Rich analytical guidance |

H0/S0 differ only by model. H1/S1 differ only by model.
The H0→H1 intervention equals the S0→S1 intervention.

**Cold-start → improved delta:** enriched semantic view, detailed orchestration
instructions (scope limits, caveat codes, abstention rules), expanded tool
description. All other spec fields (model position, budget, tool type) identical.

**Development:** Up to 20 Haiku checkpoints allowed; stopped after 2 because
further iteration was not justified. Interventions:

1. Enriched semantic view + domain-specific instructions
2. Added representativeness/generalizability abstain rule

Early stopping reason: remaining failures were data-integrity mismatches,
not agent errors. Further changes would have been question-specific.

**Scoring:** `evaluation.comparators.compare()` v1.0.0 — the same canonical
scorer used throughout the project. Requires exact column names, row values,
unit labels, caveat codes, and evidence IDs.

## Final Canonical Findings

### Strict deterministic acceptance

| | Cold Start | Improved |
|--|-----------|----------|
| **TEST** | H0: 0/10, S0: 0/10 | H1: 0/10, S1: 0/10 |
| **HOLDOUT** | H0: 0/6, S0: 0/6 | H1: 1/6, S1: 1/6 |

Under the strict canonical scorer, TEST shows no differentiation. HOLDOUT
shows a modest effect: the only passing question (R1-Q12) uses database column
names directly, bypassing the aliasing mismatch that dominates TEST failures.

### Structural response quality (valid JSON answer schema)

| | Cold Start | Improved |
|--|-----------|----------|
| **TEST** | H0: 10%, S0: 0% | H1: 50%, S1: 60% |
| **HOLDOUT** | H0: 33%, S0: 0% | H1: 100%, S1: 83% |

The strongest replicated improvement is structural: improved configs produce
valid analytical JSON instead of conversational prose. This transfers across
models and question sets.

### Gap between structural and strict

Many structurally valid responses fail strict scoring on:
- Column naming (agent chooses aliases like "differenz" vs expected "difference")
- Unit labels (agent omits units or uses different labels)
- Caveat codes (missing specific required codes like `participant_level_linkage_not_available`)

These are genuine contract-compliance failures, not merely evaluator fragility.
An agent that returns correct data under the wrong column name has not fully
satisfied the analytical output contract. However, the failures are systematic
and addressable — they represent a clear next improvement target, not a
fundamental capability limitation.

## Comparisons (structural quality)

| Comparison | TEST | HOLDOUT | Interpretation |
|-----------|------|---------|---------------|
| H1 − H0 | +40pp | +67pp | Improvement under Haiku |
| S1 − S0 | +60pp | +83pp | Transfer to Sonnet |
| S0 − H0 | −10pp | −33pp | Stronger model adds nothing at cold start |
| S1 − H1 | +10pp | −17pp | Sonnet adds little after improvement |
| H1 vs S0 | 50% vs 0% | 100% vs 0% | Improved Haiku >> cold-start Sonnet |

## Development Trajectory

| Checkpoint | Intervention | TRAIN | REGRESSION |
|-----------|-------------|-------|------------|
| 0 (H0 baseline) | Cold start | 0% | 0% |
| 1 | Enriched SV + instructions | 100% (5/5 subset) | 50% (3/6) |
| 2 (frozen) | + representativeness abstain rule | 100% (5/5 subset) | 67% (4/6) |

Development consumed ~1.26 agent credits (~17 Haiku calls). Early stopping
after 2 of 20 allowed checkpoints.

## Cost

| Component | Credits | USD |
|-----------|---------|-----|
| Cortex Agents | +2.608 | $5.22 |
| CoCo CLI (orchestration) | +12.028 | $24.06 |
| Warehouse compute | +1.654 | $6.83 |
| **Total** | **+16.29** | **$36.10** |

Starting balance: $146.43. Estimated ending balance: $110.33.

Note: CoCo CLI credits (orchestration overhead from the Opus-based experiment
coordinator) dominate total cost. Agent execution itself was $5.22 for all 64
primary invocations across both models.

## Counterfactual Development-Cost Estimate

**What would the observed Haiku development workload have cost with Sonnet?**

| | Haiku (observed) | Sonnet (counterfactual) |
|--|-----------------|----------------------|
| Development calls | 17 | 17 |
| Agent credits | ~1.26 | ~3.78 |
| Agent cost | ~$2.52 | ~$7.56 |

Estimated avoided agent credits: ~2.52. Estimated avoided agent cost: ~$5.04.
Cost ratio: ~3×.

**Limitation:** Counterfactual estimate, not realized savings. The development
trajectory might have differed if Sonnet had been used. The estimate only
answers the cost of executing the same observed workload with the stronger
model. Covers agent credits only, not warehouse or orchestration overhead.

## Claims That Are Supported

1. A weak cold-start analytical agent can be improved through inexpensive
   iterative development using Haiku.

2. The same frozen agent-level improvements also improved structural response
   quality when the agent was executed with Sonnet.

3. This pattern appeared on both fresh TEST and untouched HOLDOUT questions.

4. Simply switching the cold-start agent to a stronger model did not produce
   the same improvement.

5. Improved Haiku substantially outperformed cold-start Sonnet on structural
   response quality in this small PoC.

6. Strict end-to-end deterministic acceptance remained difficult, demonstrating
   that improving an agent is not the same as making it production-ready.

7. Development stopped after only 2 of 20 allowed iterations, demonstrating
   cost-aware early stopping.

## Claims That Must NOT Be Made

- This establishes general model superiority or inferiority.
- These results generalize to other analytical domains or agent architectures.
- The cross-model transfer is universal or guaranteed.
- Statistical significance was achieved (sample sizes are 6–10 questions).
- Independent blinding was established (this was procedurally sealed, solo workflow).
- The strict-scoring failures are purely evaluator problems (many are genuine
  contract-compliance gaps).
- Structural quality equals production readiness.
- The counterfactual cost estimate represents realized savings.

## Superseded Numbers (do not use as canonical)

The following were produced by an ad-hoc evaluator before consistent rescoring
was applied. They are preserved in audit evidence but must not appear as
canonical results:

- TEST H1: 5/10 (50%) — ad-hoc scorer
- TEST S1: 7/10 (70%) — ad-hoc scorer
- TEST S0: 1/10 (10%) — ad-hoc scorer

These are superseded by the canonical `compare()` results above.
