# Methodology

## Core question

An agent that improves on development questions may have learned those examples rather than a pattern that generalizes. The evaluation process therefore separates questions used to develop an agent from questions held back to assess its frozen configuration.

## Evidence stages

- **TRAIN** is visible during development. It supports changes to semantic representations and instructions.
- **REGRESSION / DEV-VALIDATION** checks whether those changes still work on previously opened development material.
- **TEST** is sealed before development and opened only after configurations are frozen.
- **HOLDOUT** remains sealed until the confirmatory stage and receives no development feedback.

For TASK-0019, the design used 12 TRAIN questions, 6 regression questions, 10 fresh TEST questions, and 6 HOLDOUT questions. TEST stopped further development. The work was procedurally sealed in a solo workflow, not independently blinded.

## Two quality measures

The canonical deterministic scorer checks the complete response contract: exact columns, values, units, caveats, and evidence IDs. Structural response quality separately records whether the response is valid JSON matching the answer schema. A structurally valid response can still fail deterministic acceptance.

Use deterministic ground truth where the task supports it. Unknown values remain unknown; a missing result must not be treated as a zero or a false value. Human review and cost attribution are separate records and do not overwrite deterministic assessments.

## Evidence boundaries

Only the canonical TASK-0019 results in the [article fact sheet](publication/article_fact_sheet.md) support the public result claims. Small question counts support descriptive observations only; they do not establish statistical significance, model rankings, universal transfer, or production readiness. Cloud model names do not guarantee immutable backend behavior.

The original task data, sealed question material, keys, raw cloud traces, and account configuration are not part of this public checkout. The historical result can be cited, but its cloud responses cannot be replayed from the published files.

## Further detail

- [Prospective protocol](methodology/protocol.md) describes separation, freeze points, scoring, and decision boundaries.
- [Review and custody](methodology/review_and_custody.md) describes evaluator/developer boundaries and artifact handling.
- [Architecture](architecture.md) describes the implementation components.
- [Reproduction guide](reproduction.md) distinguishes the runnable offline path from a new Snowflake campaign.
- [Canonical results](results.md) summarize the published finding.
