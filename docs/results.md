# Results

The authoritative public result source is the [TASK-0019 article fact sheet](publication/article_fact_sheet.md). The figures here use only its canonical `compare()` rescoring.

## Structural response quality

This measure is valid analytical JSON matching the answer schema.

| Split | H0 cold Haiku | H1 improved Haiku | S0 cold Sonnet | S1 improved Sonnet |
|---|---:|---:|---:|---:|
| TEST (10 questions) | 10% | 50% | 0% | 60% |
| HOLDOUT (6 questions) | 33% | 100% | 0% | 83% |

The configuration improvement raised structural response quality for both model families in these small samples. The [structural-quality visual](publication/visual_b_structural_quality.svg) shows the per-configuration rates.

## Cost context

The experiment's reported total was $36.10 across agent execution, orchestration, and warehouse use. The observed Haiku development workload cost about $2.52 in agent credits. An estimate of about $7.56 for the same workload on Sonnet is counterfactual and covers agent credits only; it is not an observed saving.

## Strict deterministic acceptance

Strict acceptance requires exact columns, values, units, caveats, and evidence IDs.

| Split | H0 cold Haiku | H1 improved Haiku | S0 cold Sonnet | S1 improved Sonnet |
|---|---:|---:|---:|---:|
| TEST (10 questions) | 0/10 | 0/10 | 0/10 | 0/10 |
| HOLDOUT (6 questions) | 0/6 | 1/6 | 0/6 | 1/6 |

Structural validity did not establish full contract compliance. Column naming, unit labels, and caveat codes were among the reported failure classes.

## Interpretation limits

This is a small public proof of concept. The workflow was procedurally sealed in a solo setting, not independently blinded. The samples are not statistically powered, and results do not establish a general model ranking, domain transfer, or production readiness. The reported cost comparison is a counterfactual estimate for agent credits, not realized savings.

The underlying evaluation inputs and frozen responses are not distributed. The exact historical cloud run therefore cannot be reproduced from this repository; see the [reproduction guide](reproduction.md) for the reproducible scope and requirements for an independent run.
