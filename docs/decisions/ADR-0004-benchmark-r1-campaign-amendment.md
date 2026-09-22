# ADR-0004: Use an aggregate P2 CORE contract and four candidates for Benchmark R1

Status: accepted for Campaign R1 planning; authorizing task TASK-0013.

## Context

The implemented local baseline models event identity, event-year status, coverage, and evidence
links and supports three initial candidates (`A0`-`A2`). The requested first real campaign instead
uses an approved edition-level aggregate export of the accepted P2 CORE demographic study and
requires a deliberately minimal `V0` followed by `V1`-`V3`, all sealed before TEST. The existing
physical data contract and three-candidate seal cannot execute that request unchanged.

These are blocking inconsistencies, not reasons to replace the portable architecture. Question,
truth, invocation, assessment, cost, custody, decision, and adapter boundaries remain suitable.

## Decision

Benchmark R1 will add one versioned aggregate release contract for exactly the four P2 CORE series
and 40 accepted edition summaries. It will not import finisher-level rows, external replication,
raw documents, or source locators. The export must carry a human approval for internal evaluation
use, exact upstream/output hashes, use restrictions, and the existing P2 claim limits. Public
redistribution remains a separate decision.

Campaign R1 will use four candidates:

- `V0`: a valid cold-start Cortex Agent with the fixed model, one aggregate analytical tool, the
  common answer contract, and only essential scope/safety instructions.
- `V1`: semantic representation and measure-description changes only.
- `V2`: instruction and existing-tool-description changes only, based on TRAIN and parented to the
  last TRAIN-promoted candidate.
- `V3`: one additional instruction/existing-tool-description refinement based only on recorded
  TRAIN error classes, again parented to the last TRAIN-promoted candidate.

All four versions remain candidates and are sealed for the one prospective TEST comparison.
Promotion decisions determine parentage; they do not erase rejected versions. The model binding,
data, questions, truth, permissions, limits, rubric, output contract, and gates stay fixed.

The R1 primary call schedule is 96 TRAIN, 48 TEST, and 12 HOLDOUT calls: 156 total. The minimal
trial smoke adds exactly one planned Cortex invocation. Native evaluations, monitoring calls,
publication, expanded experiments, and Databricks execution are excluded from R1. The existing
USD 10 equivalent ceiling and USD 2 uncertainty reserve remain unchanged; insufficient funding
stops the campaign before the next batch rather than reducing candidates or repetitions.

## Alternatives

Keeping `A0`-`A2` would preserve current code unchanged but would omit the explicitly requested
third TRAIN-developed version. Treating `V3` as an alias for the TEST-selected candidate would not
be a fourth sealed candidate. Importing P2 finisher rows would add rights, privacy, cost, and
semantic risk without helping the aggregate analytical benchmark. Rebuilding the framework around
P2 would duplicate working lifecycle, custody, scoring, and accounting controls.

## Consequences

TASK-0003 must add the smallest aggregate R1 schema/oracle extension. TASK-0007 and TASK-0015 must
extend rendering, intervention validation, and sealing from the baseline labels/count to four R1
candidates while retaining backward compatibility with the frozen synthetic baseline. The TEST
selection rule and one-candidate HOLDOUT gate remain unchanged apart from recognizing `V0` as the
baseline identifier.

Results describe one small, procedurally sealed pilot over selected P2 CORE edition aggregates.
They cannot establish national accuracy, causal effects, independent blinding, model superiority,
production readiness, or Databricks portability.

## Migration

TASK-0014 first freezes the current `A0`-`A2` local harness. R1 changes then use new versioned
artifacts and do not rewrite `SYNTHETIC-001` or its replay evidence. Later campaigns may retain the
four-candidate contract or adopt a new prospective ADR; exposed R1 TEST/HOLDOUT questions become
regression material and cannot support a second unseen claim.
