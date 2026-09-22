# TASK-0014 baseline validation report

## Baseline identity

- Baseline: `local-harness-v0.1.0`
- Annotated tag object: `e9cbbcb346b587386c7357163c8688c769a701f5`
- Tagged source commit: `38ce059533fc35a3a9c8d5d9dafda2cd4d815c33`
- Tagged source tree: `da6e639670232cc59f6e9b41d1ca7640b5f7845d`
- Tagged source files: 102; Git trees including root: 26
- The tag was created once after the reviewed source tree passed the pre-freeze checks. It is not
  advanced or reused for R1 work.

The manifest and this report are post-tag audit sidecars. Their scope is the immutable tagged
source tree above; they are added by the TASK-0014 closing commit so the manifest can record the
already-real commit/tree without a self-referential Git commit hash. This sidecar distinction is
intentional and is part of the working-tree review.

## Pre-existing Snowflake limitation

Before this baseline freeze, an authentication-only Snowflake preflight had already succeeded.
The observed facts were: Snowflake CLI 3.27.0; connection profile name redacted; current account
REDACTED_ACCOUNT; current user REDACTED_USER; current role ACCOUNTADMIN. The preflight created no database,
schema, warehouse, role, table, stage or agent; uploaded no data; invoked no Cortex/model; and
ran no Benchmark R1. No trial credits were consumed.

This is a documented pre-existing limitation to the original wording that the baseline precedes
all live Snowflake contact. The baseline still represents the complete pre-R1 implementation state,
but this report and the repository do not claim that Snowflake has never been contacted. TASK-0014
performed no further Snowflake command.

## Acceptance results

| Criterion | Result | Evidence |
|---|---|---|
| No credential, evaluator key, hidden real question, private trace, or real P2 artifact | PASS | Tagged tree scan: 102 tracked files; no forbidden credential/private-artifact names or literal secret assignments; only labeled synthetic release material is tracked. |
| Dependency installation/check, tests, lint/format, typing, schemas, release, replay, task history, links, diff | PASS | Exact command results are recorded below. |
| Replay reproduces report and evidence hashes offline | PASS | 312 evidence hashes verified; 313 evidence files including `completed.json`; report and replay report are byte-identical. |
| Manifest records every tagged file/tree hash and a real revision | PASS | `baselines/local-harness-v0.1.0.json` records 102 file hashes, 26 Git tree hashes, commit `38ce059533fc35a3a9c8d5d9dafda2cd4d815c33`, and tree `da6e639670232cc59f6e9b41d1ca7640b5f7845d`. |
| Working-tree review separates baseline from local/private evidence | PASS | `local/`, `private/`, and generated reports are ignored and absent from the tagged tree; sidecars are explicitly post-tag audit metadata. |

## Exact validation environment

| Component | Version/value |
|---|---|
| OS | Microsoft Windows NT 10.0.26200.0 |
| PowerShell | 5.1.26100.9444 |
| Python | 3.12.10 in `.venv` |
| pip | 26.2 |
| Git | 2.51.0.windows.1 |
| pytest | 8.4.2 |
| Ruff | 0.16.6 |
| mypy | 2.3.1 |
| cryptography | 46.0.3 |
| duckdb | 1.5.0 |
| jsonschema | 4.25.1 |

Dependency installation used `requirements.lock`, followed by editable installation with
`--no-deps`; the lock file is hashed in the baseline manifest.

## Exact commands and results

All commands were run from the repository root with the repository `.venv`
interpreter. Commands that write demo/replay evidence wrote only to ignored `local/` paths.

| Command | Result |
|---|---|
| `.venv\Scripts\python -m pip install -r requirements.lock` | PASS; locked packages already satisfied |
| `.venv\Scripts\python -m pip install --no-deps -e .` | PASS; editable package installed |
| `.venv\Scripts\python -m pip check` | PASS; no broken requirements |
| `.venv\Scripts\python -m pytest -q --basetemp=local/pytest-task0014` | PASS; 85 passed in 6.43 seconds |
| `.venv\Scripts\python -m ruff check .` | PASS |
| `.venv\Scripts\python -m ruff format --check .` | PASS; 72 files already formatted |
| `.venv\Scripts\python -m mypy evaluation platforms` | PASS; 23 source files |
| `.venv\Scripts\python scripts/build_schemas.py --check` | PASS; 17 schemas |
| `.venv\Scripts\python -m evaluation.cli verify-release data/synthetic/SYNTHETIC-001 --allow-synthetic` | PASS; 24 questions and 11 event-year rows |
| `.venv\Scripts\python -m evaluation.cli doctor` | PASS; local-only check reported no connection attempt and no optional connector |
| `.venv\Scripts\python -m evaluation.cli demo --fixture data/synthetic/SYNTHETIC-001 --output local/baseline-v0.1.0-demo` | PASS; 120 primary and 12 monitoring synthetic invocations; no model invoked |
| `.venv\Scripts\python -m evaluation.cli replay-demo --evidence local/baseline-v0.1.0-demo --fixture data/synthetic/SYNTHETIC-001 --output local/baseline-v0.1.0-replayed-report.md` | PASS; 72 TRAIN, 36 TEST, 12 HOLDOUT; report identical |
| `.venv\Scripts\python scripts/update_task_history.py check` | PASS |
| PowerShell local Markdown-link check over `git ls-files '*.md'` | PASS; 30 Markdown files |
| `git diff --check` and staged diff check | PASS; no whitespace errors |

The Markdown-link check resolved every non-external Markdown target relative to its source file.
The diff check emitted only expected CRLF-to-LF conversion notices for files governed by
`.gitattributes`; it reported no whitespace errors.

After the sidecars and baseline links were added, the closing rerun also passed: 85 pytest tests
in 6.57 seconds, Ruff check, Ruff format check (73 supported files including this report), strict
mypy over 23 source files, all 17 schemas, synthetic release verification, replay, task-history,
Markdown-link and manifest/tag binding checks. The replay still reported 72 TRAIN, 36 TEST and 12
HOLDOUT records with a byte-identical report.

## Hash summary

- Dependency lock SHA-256: `35ce95b7d450158190ef07081f2a1a4493d8324aff561a4d149cbc0ce0ed8549`
- Generated schema tree Git SHA-1: `593c4de16e94c2998194368c7605c6dcb2830794`; schema index SHA-256: `4dc4f72efd6489637cb20843848ec081a7d778b6d9a669e5f9f01bf9d1ab81f4`
- Synthetic release index SHA-256: `6de6ffeec97726787b0f5e697457456e64fab463a0b2e5ae993ceb1f1fdb28d1`; canonical manifest digest: `3708390908e05a1c6ddcd0f3580485b557aeed15bfe929489a1b9bf787393df9`
- Documentation index SHA-256: `a00caefb554299f42fe541774e0e9715c10f0849d4c56bc2e94354dfac9a9e9a`
- Demo completed artifact SHA-256: `970d73ef24efa11d8637c0d4446d8807be4f26f7c577f9cca97757125c449a3d`
- Demo evidence-index digest: `dc6e22c225d0c98f14dba6f9ca92d79d7ec2db03450dff5c8e8f636902ef4dba`
- Demo `test_report.md` SHA-256: `26c6d7f6cf6dc611755a5fb6694a4ee8ff3622806f22492d583777847fba8872
- Replayed report SHA-256: `26c6d7f6cf6dc611755a5fb6694a4ee8ff3622806f22492d583777847fba8872`
- Byte-identical report result: `true`

The full per-file and per-tree inventory, including Git blob IDs and SHA-256 values, is in
`baselines/local-harness-v0.1.0.json`.

## Working-tree and claim limits

The tagged source tree contains implementation, documentation, task records, generated schemas,
tests and the labeled synthetic release. It contains no credentials, evaluator keys, hidden
real questions, private traces or real P2 data. Ignored `local/` outputs are local/private
validation evidence and are not baseline content. No R1 compatibility changes, P2 import,
TASK-0002, TASK-0006, or cloud/model execution was performed.

Synthetic responses, costs, latencies and replay results are software-fixture evidence only; they
do not establish cloud compatibility or empirical agent performance.
