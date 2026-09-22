# ADR-0005: Permit cumulative V3 combining V1 semantics and V2 instructions

Status: accepted for Campaign R1 TRAIN development; prospective amendment before TEST access.

## Context

ADR-0004 defined four candidates (V0–V3) with single-factor intervention boundaries:

- V0: cold-start baseline (dimensions only, no measures).
- V1: semantic representation only (added 23 measures to the semantic view).
- V2: instructions and existing-tool-description only, parented to the last TRAIN-promoted candidate.
- V3: one additional instruction/tool-description refinement, again parented to the last
  TRAIN-promoted candidate.

All three TRAIN evaluations are now complete:

| Candidate | Accepted | Robust | Critical | Dominant Errors |
|---|---|---|---|---|
| V0 | 0/24 | 0/12 | 0/8 | FORMAT_INVALID (19) |
| V1 | 0/24 | 0/12 | 0/8 | MISSING_CAVEAT (16), UNSUPPORTED_PROVENANCE (16), WRONG_VALUE (13) |
| V2 | 1/24 | 0/12 | 0/8 | WRONG_VALUE (18), WRONG_UNITS (18), UNNECESSARY_ABSTENTION (13) |

No candidate was promoted. V0 remains the default parent for all successors.

The completed TRAIN evidence demonstrates that V1 and V2 address complementary, non-overlapping
failure modes:

- **V1** made measures accessible: FORMAT_INVALID dropped 19→8, UNNECESSARY_ABSTENTION dropped 1→0.
  The agent could find and return data, but failed on answer-contract metadata (caveats, evidence
  IDs, units).
- **V2** fixed contract compliance: FORMAT_INVALID dropped 19→1, UNSUPPORTED_PROVENANCE dropped
  5→0, FAILED_TO_ABSTAIN dropped 1→0. But without measures in its dimensions-only semantic view,
  the agent abstained on 13/24 answerable questions.

The single-factor parentage design forces V3 to inherit V0's dimensions-only view, making it
structurally unable to answer measure-dependent questions regardless of instruction quality.
The `validate_intervention()` function enforces that an `instructions` intervention can only touch
`{instructions, tools}`, not `semantic_sha256`. No existing intervention type permits both
semantic and instruction changes.

This is not a quality-retry or TEST-feedback situation. It is a structural limitation of the
original experimental design that was only discoverable through completed TRAIN execution.

## Evidence basis

This amendment is derived exclusively from TRAIN evidence:

- `v0/v0_scored.json`, `v0/v0_assessment.json` (V0: 0/24, FORMAT_INVALID dominant)
- `v1/v1_scored.json`, `v1/v1_assessment.json` (V1: 0/24, metadata errors dominant)
- `v2/v2_scored.json`, `v2/v2_assessment.json` (V2: 1/24, abstention errors dominant)
- `v1/v0_v1_intervention_analysis.md` (V0→V1 error shift)
- `v2/TASK-0007-V2-HANDOFF.md` (V0→V1→V2 cross-version error taxonomy, Section 3 diagnostic)

TEST and HOLDOUT payloads remain sealed. Their ciphertext hashes are unchanged:

- TEST: `d02f3bb629ee76765637d66d4171825592d98ab3c6023a6368296bbc9a1cc5aa`
- HOLDOUT: `349bcb8d668bbd7e269c39b4c618bc8f854b6cedc16c6205301064479a590999`

No TEST or HOLDOUT plaintext, question, ground truth, or result has been accessed, viewed, or used
to inform this amendment.

## Decision

The R1 protocol is amended as follows:

1. **V3 intervention type is changed** from `instructions` to `cumulative`. The `cumulative`
   intervention permits changes to `{semantic_sha256, instructions, tools}` — combining semantic
   representation with instruction/tool-description refinement.

2. **V3 parent is V1** for semantic representation and **V2** for instructions/tool-descriptions.
   Formally, V3 declares `parent_id: "V1"` with an additional `instruction_source: "V2"` field.
   Both V1 and V2 are complete, scored, and their evidence is frozen.

3. **V3 may additionally include** at most one targeted refinement derived from recorded TRAIN
   error classes (e.g., fixing MISSING_CAVEAT on abstention questions, correcting unit labels).

4. **The tool capability constraint still applies**: V3 may change tool descriptions but not tool
   types, names, or functional behavior. Only `description` fields in tool specs may differ.

5. **All other controls remain fixed**:
   - Model: `claude-haiku-4-5`
   - Underlying data: `AGENT_LAB.BENCHMARK_R1.P2_CORE_EDITION` (40 rows, 30 columns)
   - TRAIN questions and ground truth: unchanged
   - Scoring comparator, rubric, schemas, acceptance logic: unchanged
   - Repetitions: 2 per question (24 TRAIN invocations)
   - Cost ceiling: USD 10.00 with USD 2.00 reserve
   - No retries, no discarded failures, no quality re-runs
   - Execution protocol: sequential, concurrency 1
   - Permissions: LAB_RUNTIME role, LAB_XS warehouse

6. **After V3 TRAIN evaluation**, development freezes completely. No further candidates, no
   instruction tuning, no semantic view changes. The campaign proceeds to TEST sealing with
   V0, V1, V2, and V3 as the four sealed candidates.

7. **The original protocol freeze (`protocol_freeze.json`) is not rewritten.** This amendment is
   recorded as a separate versioned artifact (`protocol_amendment_v2.json`) with its own hash,
   timestamp, and reference to the original freeze.

## Preserved evidence

All existing V0, V1, and V2 evidence is unchanged:

- V0: `v0_scored.json`, `v0_assessment.json`, deployment, schedule, batch SQL, results table
- V1: `v1_scored.json`, `v1_assessment.json`, deployment, schedule, batch SQL, results table,
  intervention analysis, V1 handoff
- V2: `v2_scored.json`, `v2_assessment.json`, deployment, schedule, batch SQL, agent spec,
  budget admission, results table, V2 handoff

No file, Snowflake object, or assessment from V0, V1, or V2 is modified.

## Alternatives

**Keep the single-factor design.** V3 would inherit V0's dimensions-only view and be structurally
limited to ~6–10/24 maximum (the V2 handoff ceiling estimate). This preserves experimental purity
but guarantees no candidate can pass the TEST gate (≥10/12 robust = ≥20/24). The campaign would
complete with four uniformly failing candidates and no actionable development outcome.

**Add a fifth candidate (V4).** This would exceed the four candidates declared in ADR-0004 and
the frozen policy, and would require additional budget. Rejected as more disruptive than amending
V3's intervention type.

**Declare V3 as a semantic-only intervention parented to V2.** This would lose V2's instruction
improvements because V3 would not inherit V2's instructions through semantic parentage. Rejected
because it recreates the same single-factor limitation.

## Consequences

- `evaluation/iterations.py` must add `cumulative` to the allowed intervention map with
  `{semantic_sha256, instructions, tools}`.
- V3 deployment must reference V1's semantic view (`SV_V1_MEASURES`) and V2's instructions
  (with targeted refinements).
- The `protocol_amendment_v2.json` artifact carries its own SHA-256 hash and is referenced
  alongside the original `protocol_freeze.json` in all subsequent sealing operations.
- The number of candidates (4), questions (24 TRAIN), repetitions (2), and gates are unchanged.
- After V3 TRAIN, the campaign has exactly 96 completed TRAIN invocations (4 × 24), matching
  the original ADR-0004 plan.
