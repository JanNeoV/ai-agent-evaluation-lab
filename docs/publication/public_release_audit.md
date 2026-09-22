# Public repository audit

Audit date: 2026-09-22

Scope: files selected for the fresh public repository. Frozen experiment evidence and canonical results were not rewritten.

## Release contents

The public tree contains the evaluation engine, schemas, offline synthetic fixture, Snowflake adapter/SQL renderer, implementation tests, and public methodology/results documentation. The original research data, sealed TASK-0019 inputs, evaluator keys, raw cloud responses, account configuration, and local run artifacts are not part of the tracked release.

Task records, the generated task history, the detailed Snowflake retry diary, and unpublished article drafts are local development material. Their useful methodology and canonical result information are represented in the public documentation; local copies remain available in the maintainer checkout and are excluded from Git. Historical baseline manifests are retained as historical integrity records.

## File classification

| Class | Repository material | Disposition |
|---|---|---|
| A — Public implementation | `evaluation/`, `platforms/`, `evaluation/schemas/`, `tests/`, `data/synthetic/`, `pyproject.toml`, and the schema/fixture generators | Retained as the runnable reference implementation. |
| B — Reproducibility evidence | `baselines/`, public synthetic release files, the TASK-0019 fact sheet and generated figures, and the R1 public result summary | Retained; the fact sheet is authoritative for TASK-0019 claims. |
| C — Useful documentation | `docs/quickstart.md`, `methodology.md`, `reproduction.md`, `architecture.md`, `results.md`, protocol/custody notes, and deployment guidance | Retained, with a direct reader path from overview to run instructions. |
| D — Internal development material | `tasks/`, `docs/task_history.md`, `AGENTS.md`, the task-history generator, R1/custody automation, detailed Snowflake retry diary, and unpublished article drafts | Kept in the maintainer checkout but removed from public Git tracking and ignored. |
| E — Generated or local material | `local/`, `private/`, virtual environments, Python/test caches, package metadata, and `.cortex/` plans | Ignored. Frozen local evidence was preserved byte-for-byte during cleanup. |
| F — Potentially sensitive material | Credentials, evaluator keys, private data, hidden question/truth, raw traces, account identifiers, personal paths, and personal identity disclosures | No credentials, live account identifiers, personal paths, or personal identity disclosures are included. Private evidence remains outside the public repository. |

## Privacy and configuration

- No credentials, tokens, or private keys are intended to be tracked. The Snowflake profile example contains placeholders only; the public CLI does not load `.env` files.
- Historical records use redaction markers where account or user fields are necessary to interpret the record; these markers are not live identifiers.
- Citation metadata points to the public repository at `https://github.com/JanNeoV/agent-evaluation-lab`.
- The public repository starts with fresh Git history, so disclosures from the internal repository's history are not inherited.
- Task diaries and task history are excluded from the public repository.

The audit found no actual Snowflake account locator or credential in the public tree.

## Evidence boundary

The [article fact sheet](article_fact_sheet.md) is the authoritative source for TASK-0019 results. The canonical strict and structural measures remain distinct. The public figures can be regenerated from that fact sheet, but hidden question text, truth, and raw responses are not distributed. No experiment was rerun for this cleanup.

## Local validation

Validation results for this cleanup are recorded in the final change summary and may be repeated using the commands in [local validation](../validation.md). CI runs offline checks only and does not invoke Snowflake or Cortex.

## Release metadata

- The software is released under the MIT License.
- No `SECURITY.md` is provided because a verified private vulnerability-reporting channel has not been configured.
