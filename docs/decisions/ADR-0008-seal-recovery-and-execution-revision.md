# ADR-0008: Recover the TASK-0015 campaign seal and bind a clean R1 execution revision

Status: accepted for Campaign R1 before any TEST plaintext access.

## Context

The TASK-0015 campaign seal was produced in a Snowflake Workspace session and written to
`local/benchmark-r1/R1-001/campaign/`. `local/` is listed in `.gitignore`, so the four sealed
artifacts were never committed and were absent from the canonical local checkout at the start of
R1-001 execution. The original execution record noted this as a
blocking condition and stopped before TEST decryption with 0/48 TEST calls, 0 retries, no TEST
response, no assessment, no decision, and HOLDOUT unopened.

Two further preconditions were open:

1. `LAB_RUNTIME` lacked `USAGE` on `AGENT_LAB.AGENTS.BENCHMARK_AGENT_R1_RECOVERED`.
2. ADR-0004 requires extending code "from the baseline labels/count to four R1 candidates"; the
   sealing path was extended in TASK-0015 round 3, but two execution-path call sites were not:
   candidate deployment verification and TEST baseline identification.

## Decision

### 1. The original seal is recovered, not re-created

The four TASK-0015 artifacts were recovered byte-for-byte from the Snowflake Workspace
`USER$REDACTED_USER.PUBLIC."agent-evaluation-lab"` (`versions/live/local/benchmark-r1/R1-001/campaign/`)
and materialised at the expected evaluator path. All four hashes reproduce the TASK-0015 record
exactly:

| Artifact | SHA-256 |
|---|---|
| `protocol.json` | `f8a4306b837ea1a9b23dd30c5aa6eaeeaa19fbb6e5fd8cd374ff0e4f7388dbbd` |
| `events.jsonl` | `8c83c598c721b828cda591c39e885d2210ca252c5019b31b7f21a421ccd03966` |
| `candidate_bundle.json` | `2b83db2739000db0a4f19e3852d1d63d37e5e37958e540ffb60260dfc7d49488` |
| `test_schedule.json` | `7f8d182a3539c42c7c7959c13acb95011be15e7ddf480a4bdd0735785025c8d6` |

Because the exact originals exist, **no prospective recovery reseal is performed and no reseal is
authorized**. The historical TASK-0015 record is not rewritten; the recovery is appended to it.
`protocol.json` — including its frozen `git_commit`
`d27c3ee58bcd2ea513f79b69862a56cc26331833` — is preserved unmodified.

### 2. Execution provenance is normalised, not re-sealed

The diff between the sealed commit `d27c3ee` and the repository state at recovery is confined to
local task-history records and two empty pytest cache marker directories. No execution-critical
module differed. Documentation and task-record changes do not invalidate execution provenance.

The two extensions in section 3 below *are* execution-critical. They are therefore committed, and
the resulting clean revision is recorded as the **execution revision** in an append-only recovery
artifact (`local/benchmark-r1/R1-001/release/seal_recovery_record.json`). The sealed
`protocol.json.git_commit` remains `d27c3ee…` and is not rewritten: the seal binds the campaign
definition, and the recovery record binds the revision that executed it. Both are reported.

### 3. Two ADR-0004-mandated extensions are implemented before TEST access

Neither changes a frozen gate, threshold, comparator, schedule, candidate, or selection rule. Both
fail closed. Both are derived exclusively from sealed and public artifacts, with no TEST plaintext,
question, ground truth, or result consulted.

**(a) Sealed-candidate verification (`platforms/snowflake/adapter.py`).** `run_batch` requires
`adapter.verify(deployment).get("verified")` for every sealed candidate. The frozen `A0`-`A2`
bundle shape carries `fingerprint_sha256` and `tables` and is verified by a full dependency probe.
The R1 seal carries neither; it pins each candidate component-by-component
(`spec_canonical_hash`, `instructions_hash`, `tools_hash`, `tool_resources_hash`, `semantic_view`,
`model`) plus the execution role. `verify()` now dispatches to `verify_sealed_specification()` for
the R1 shape, which recomputes every sealed component against the live committed agent version and
returns `verified=False` if any one diverges. The baseline path is unchanged and still takes
precedence when `fingerprint_sha256` is present. TASK-0015's acceptance criterion — "every
deployment fingerprint still matches the value captured before sealing" — is thereby enforced
against the fingerprints that were actually sealed, rather than skipped.

**(b) Baseline identification (`evaluation/decisions.py`).** ADR-0004 already states that "the TEST
selection rule and one-candidate HOLDOUT gate remain unchanged apart from recognizing `V0` as the
baseline identifier". `select_candidate()` hard-coded `A0`. A new `baseline_metrics()` returns `A0`
when present, otherwise `V0` **only** when the candidate set is exactly `{V0, V1, V2, V3}`, and
raises otherwise. The lexicographic tie-break order, eligibility gates, thresholds, and
`POLICY` hash are untouched; `policy_sha256` in every decision is unchanged.

### 4. Formatting-only cleanup

`platforms/snowflake/deployment.py` failed `ruff format --check` at the pinned `ruff==0.16.6`
before any change in this round. It is reformatted with no semantic change so that the required
validation passes on the execution revision.

## Alternatives

**Perform a prospective recovery reseal.** Rejected: the exact original bytes were recoverable and
verified, so a reseal would replace a genuine prospective seal with a weaker reconstruction.

**Treat the missing R1 code paths as a hard stop.** Rejected: ADR-0004 pre-registered both
extensions before any TEST access. Declining to implement them would not preserve frozen semantics;
it would leave a pre-registered rule unimplemented and force either a fabricated verification or an
abandoned campaign.

**Inject `fingerprint_sha256` into the candidate bundle.** Rejected and impossible: `run_batch`
requires the deployments argument to equal the sealed bundle exactly, and mutating a sealed artifact
is forbidden.

**Bypass verification for R1.** Rejected: that would weaken a fail-closed gate.

## Consequences

- `tests/test_snowflake_adapter.py` and `tests/test_scoring_and_decisions.py` gain ten tests
  covering component-wise verification failure, execution-role enforcement, swapped semantic views,
  baseline-path precedence, V0 recognition, and refusal to guess a baseline.
- TEST cost completeness still depends on per-invocation `request_id` attribution. If Cortex does
  not return an attributable request identifier, `costs_complete` is `false` and the frozen rule
  yields `INCONCLUSIVE`. Unknown remains unknown; no cost is estimated into a gate.
- Human narrative review remains mandatory for acceptance. A deterministically passing answer with
  no human review scores `accepted = null`, which makes the candidate incomplete and the TEST
  decision `INCONCLUSIVE` rather than a selection.
- The USD 30 hard ceiling (ADR-0003 → ADR-0006 → ADR-0007) and the USD 2 reserve are unchanged. No
  ceiling increase is authorized by this record.
