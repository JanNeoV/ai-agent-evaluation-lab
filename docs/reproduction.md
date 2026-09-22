# Reproduction guide

This guide separates the runnable local reference workflow from a new Snowflake campaign. It does not start any cloud work.

## What this repository can reproduce

The local synthetic lifecycle, schema checks, strict scorer behavior, and publication SVGs can be rerun from this checkout. Synthetic responses, timings, and costs are software fixtures, not evidence of AI-agent performance.

The exact TASK-0019 cloud experiment cannot be recreated from the public files. The source dataset, question and ground-truth releases, frozen agent specifications, raw responses, and account-specific execution evidence are not distributed. The [article fact sheet](publication/article_fact_sheet.md) is the authoritative record of its canonical results. It supports citation and interpretation, but it does not make the underlying responses available for rescoring.

The historical 2-by-2 result used four configurations and 64 primary responses across fresh TEST and HOLDOUT questions. The general campaign runner in this repository schedules two repetitions per candidate and question; it is a reference lifecycle, not a turnkey TASK-0019 replay tool. A new 2-by-2 campaign requires its own approved data, frozen protocol, and matching invocation schedule.

## 1. Run the public offline reproduction

**Cost:** no Snowflake connection, Cortex calls, or cloud credits.

```bash
python -m pip install -e ".[dev,visuals]"
python -m evaluation.cli doctor
python -m evaluation.cli verify-release data/synthetic/SYNTHETIC-001 --allow-synthetic
python -m evaluation.cli demo --output artifacts/demo-reproduction
python -m evaluation.cli replay-demo --evidence artifacts/demo-reproduction --output artifacts/demo-report.md
python scripts/build_schemas.py --check
python docs/publication/gen_visuals.py
```

Choose fresh output paths under `artifacts/`, keeping generated outputs separate from frozen evidence in `local/`. The demo writes `completed.json`, a synthetic campaign ledger, schedules, invocations, usage records, and a replayable report under its output directory. The replay command verifies and re-grades those synthetic records. The result plots read the canonical tables in the article fact sheet; the lifecycle figure uses the documented stage counts. The command rewrites the three SVGs in `docs/publication/`.

## 2. Prerequisites for a new Snowflake run

- Python 3.11 or later. Python 3.12 is the validated release version.
- A Snowflake account with Cortex Agents, Cortex Analyst, and access to the specific requested models in the account's region or enabled cross-region scope.
- A cleared dataset and permission to use it for evaluation. Do not use the private TASK-0019 data or any data without an explicit reuse basis.
- A deployment administrator who can create the required database, schemas, roles, warehouse, semantic views, and agent, and grant access to the runtime role.
- A separate runtime identity with only the data and agent privileges needed for the run.
- A current cost estimate, account/model availability check, and a budget approved by the account owner.

Snowflake feature and model availability can vary by account, region, and date. Confirm the current model list and cross-region settings before choosing a model. The experiment's historical model identifiers were `claude-haiku-4-5` and `claude-sonnet-4-6`; their availability today is not guaranteed.

For Cortex Agents, Snowflake documents `SNOWFLAKE.CORTEX_AGENT_USER` as the agent-specific database role (or the broader `SNOWFLAKE.CORTEX_USER`). Agent callers also need `USAGE` on the agent, its database and schema, and their default warehouse, plus access to each tool's data. Permissions are evaluated using the user's default role. Cortex Analyst has a narrower `SNOWFLAKE.CORTEX_ANALYST_USER` role or can use the broader Cortex role; roles also need access to the semantic view and underlying tables. Creation requires `CREATE AGENT` and `CREATE SEMANTIC VIEW` on the relevant schemas. See Snowflake's current [Cortex Agent access guide](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-setup) and [Cortex Analyst access guide](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst).

The checked-in bootstrap SQL grants the narrower `CORTEX_AGENT_USER` and `CORTEX_ANALYST_USER` database roles to the runtime role. If an account does not expose those roles, an administrator must choose a supported configuration; `CORTEX_USER` is broader. Do not grant evaluator secrets or hidden truth to the agent role.

## 3. Install and configure credentials

For a cross-platform installation, use `pyproject.toml`:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev,snowflake,visuals]"
```

`requirements.lock` is an exact Windows/Python 3.12 snapshot, not a cross-platform lock. The `snowflake` extra installs the optional connector; `visuals` installs Matplotlib and NumPy for the SVG generator.

The public CLI reads no `.env` file. The Snowflake adapter reads a named connector profile selected with `--profile`. Store `connections.toml` in the connector's user-level configuration location, not in this repository. `SNOWFLAKE_HOME` may select a user-level connector configuration directory. Prefer browser SSO or approved key-pair authentication; keep private keys outside the checkout and restrict their filesystem permissions. Never put passwords, tokens, private keys, or real account details in a committed file or command history.

`examples/snowflake-connections.toml.example` is a placeholder profile. Copy it to your user-level connector configuration, replace the account and user placeholders locally, and confirm the configured default role and warehouse meet the Snowflake requirements. The connector documentation describes [connection profiles and their locations](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect).

## 4. Prepare data and Snowflake objects

Start with the public synthetic release to inspect the flow:

```bash
python -m evaluation.cli verify-release data/synthetic/SYNTHETIC-001 --allow-synthetic
python -m evaluation.cli render-snowflake --release data/synthetic/SYNTHETIC-001 --output artifacts/snowflake-sql --model claude-haiku-4-5 --allow-synthetic
```

These commands validate files and render SQL locally. They do not connect to Snowflake. Rendering produces table/data SQL, semantic views, example A0–A2 agent definitions, version commands, grants, and a bundle hash. It does not implement the TASK-0019 H0/H1/S0/S1 prompt pair or deploy anything.

For your own authorized data, create a release with `data.json`, `questions.json`, `ground_truth.json`, and `manifest.json`, then validate it before use. The synthetic files show the artifact shapes. Do not copy the original evaluation inputs. Adapt the SQL/data loading to your chosen release and account.

Review `platforms/snowflake/sql/001_bootstrap.sql` and generated SQL before execution. The bootstrap creates roles, a database, schemas, and an initially suspended warehouse. Run object creation with an administrator, apply only reviewed grants, and create one named agent version per frozen configuration. The semantic view must represent the same definitions used by the deterministic oracle. Set an adequate auto-suspend window for the agent's planning and tool calls. Keep the runtime role separate from the role that can read evaluator material.

**Cost boundary:** local validation and SQL rendering are free of Cortex usage. Creating or loading cloud objects can incur storage or warehouse charges. Resuming a warehouse, executing queries, calling an agent, and using downstream tools can incur Snowflake and Cortex charges. Cortex Agents bills for orchestration and tool use; actual cost depends on the account, model, token usage, warehouse, and current rate card. Estimate and record those charges before running.

## 5. Create the evaluation dataset and protocol

The local evaluator consumes versioned JSON question and ground-truth artifacts; it does not require Snowflake's separate native Agent Evaluations dataset service. Design question intent, answer contract, deterministic oracle, scoring rules, leakage groups, and split assignment before any agent run. Check that the oracle and candidate tool have the same allowed data but that ground truth and review criteria are never sent in an invocation request.

For a prospective independent study:

1. Prepare TRAIN, regression, fresh TEST, and HOLDOUT releases. Keep TEST/HOLDOUT plaintext and keys in evaluator custody, outside the developer checkout.
2. Hash the data, semantic definitions, question/answer contract, rubric, model settings, and dependency environment. Record the hashes in a completed copy of `examples/protocol.template.json`.
3. Initialize an empty campaign with `python -m evaluation.cli init-campaign --protocol path/to/protocol.json --output path/to/campaign`.
4. Seal hidden payloads with `python -m evaluation.cli seal-payload --input path/to/hidden-payload.json --output path/to/evaluator-custody/test.enc --key-file path/to/evaluator-custody/test.key --developer-root path/to/developer-checkout`. Keep the key and hidden plaintext out of the developer checkout and out of Git.
5. Create model/configuration versions and record their explicit Snowflake version references and fingerprints. Build a complete deployment bundle and invocation schedule, then bind both to the campaign with `python -m evaluation.cli seal-candidates --campaign path/to/campaign --deployments path/to/deployments.json --schedule path/to/schedule.json`. Only the approved TRAIN role may see TRAIN feedback.

The protocol and batch JSON files in `examples/` are templates containing placeholders. They are not runnable campaign inputs until completed, reviewed, and matched to the frozen artifacts. Never reuse example budget numbers as a live quote.

## 6. Develop, freeze, and execute

Develop only on TRAIN and the declared regression material. Change one factor at a time, preserve rejected configurations, record their parent relationships, and use a cost ceiling with an uncertainty reserve. If comparing model and configuration effects, prepare both cold-start and improved variants for both models before TEST. Keep the model identifier, semantic view, instructions, tool descriptions, permissions, and runtime settings explicit.

Freeze all candidate specifications and the complete invocation schedule before revealing TEST. Hash the bundle and schedule and verify the sealing record. Once TEST starts, do not change any candidate or schedule. After TEST scoring, select according to a rule written before reveal. The historical TASK-0019 design evaluated each of its four frozen configurations on every HOLDOUT question; the earlier R1 protocol and the generic runner instead use a selected candidate for HOLDOUT. Keep all raw responses and error outcomes in the denominator. The local campaign runner uses two repetitions per question/configuration; alter the schedule and matching analysis only in a new, reviewed study design.

**Costed cloud operation:** after budget preflight and review, `python -m evaluation.cli run-snowflake --config path/to/batch.json --profile your_profile_name` submits the configured invocations. It can incur Cortex and warehouse costs. The CLI requires a real campaign, a filled batch config, a current balance/expiry observation, and a reservation. Do not run this command merely to validate the repository. Account-specific R1 campaign launchers and custody utilities are maintainer-only and are excluded from the public checkout. They are not shortcuts for TASK-0019 reproduction.

## 7. Verify, score, reconcile, and extract results

After a batch, verify saved evidence locally with `python -m evaluation.cli verify-run path/to/batch`. This makes no cloud call. Score using `python -m evaluation.cli score --config path/to/score-config.json --output path/to/scores.json`; scoring reads the saved invocation records, ground truth, optional reviews, and final cost records. Apply a previously frozen gate with `python -m evaluation.cli decide --campaign path/to/campaign --scores path/to/scores.json --split TEST --output path/to/decision.json`. The TEST/decide step is local.

For structural validity, parse each response with `json.loads` and validate the object with `evaluation.contracts.validate("answer", parsed)`. Count schema-valid responses over all scheduled responses, including invalid or failed outcomes in the denominator. For strict deterministic acceptance, use `evaluation.comparators.compare(response_text, truth)`. Preserve both outcomes; do not treat schema validity as a deterministic pass. Extract question-level counts, failures, configuration identifiers, and cost/latency summaries from the saved output files. Keep unknown or unreconciled costs unknown. Never replace a saved response or canonical scorer assessment with a different evaluator.

For `score`, the JSON config identifies the campaign, split, batch directory, and payload; TEST/HOLDOUT also name the external key file. Optional `reviews` and `costs` fields point to finalized JSON files. For example, replace each value with the approved paths in the evaluator workspace:

```json
{
  "campaign": "path/to/campaign",
  "split": "TEST",
  "batch": "path/to/batch",
  "payload": "path/to/test.enc",
  "key_file": "path/to/external-evaluator-custody/test.key",
  "reviews": "path/to/reviews.json",
  "costs": "path/to/final-costs.json"
}
```

The score command writes `assessments` plus per-candidate `metrics`. Cost reconciliation is a separate local step using `python -m evaluation.cli reconcile-costs --input path/to/usage-export.json --output path/to/final-costs.json`. Its input object contains `records`, `token_usage`, `warehouse_usd`, `review_ref`, and `rate_card_sha256`; missing provider attribution remains unknown. `decide` writes a decision from those frozen scores and the predeclared gate.

The TASK-0019 raw response and question files are not public, and its fact sheet does not contain the row-level data. Therefore the published percentages cannot be independently rescored from this clone. The visual generator reproduces the published figures from the fact sheet; it does not reconstruct the hidden responses.

## 8. Regenerate visuals and clean up

Install the visual dependencies and regenerate the figures from the authoritative fact sheet:

```bash
python -m pip install -e ".[visuals]"
python docs/publication/gen_visuals.py
```

The expected files are `visual_a_lifecycle.svg`, `visual_b_structural_quality.svg`, and `visual_c_strict_vs_structural.svg` in `docs/publication/`. Font selection can vary by operating system; the values and labels are sourced from the fact sheet.

After a cloud campaign, export and reconcile provider usage, confirm the final evidence hashes and decisions, then remove only the Snowflake roles, warehouse, database, and objects you created, following your organization's retention policy. Cleanup may require an administrator. Preserve the campaign artifacts required for audit; do not delete frozen evidence to make a run appear complete.

## Expected outputs and limits

The offline workflow produces a verified synthetic release, a replayable demo evidence directory, a Markdown report, schema verification output, and the three SVG figures. It does not reproduce real AI-agent performance.

A new Snowflake run should produce named agent versions and fingerprints, frozen schedule/protocol files, raw invocation records, deterministic assessments, cost reconciliation, and a decision record. Account feature availability, exact model routing, output wording, latency, and billing attribution can vary. Repeating a live call cannot guarantee the same response or cost, even when a model name is unchanged.
