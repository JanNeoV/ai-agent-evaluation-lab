# Review and procedural custody

## Before execution

1. An author/evaluator prepares the approved real dataset and 24 questions in a
   separate custody directory, outside the developer checkout and coding-agent context.
2. Validate all dataset hashes, source release evidence, identities, provenance and
   expected SQL results. Review each ground truth; use an independent calculation
   or manual verification. Verify Snowflake/local SQL result parity later.
3. Review paraphrase/intent grouping before assignment. Software cannot discover all
   semantic duplicates; `validate_splits` enforces declared groups, not semantic truth.
4. Export TRAIN to the developer workspace. Package TEST and HOLDOUT independently
   as objects with `questions` and `ground_truth` arrays. Seal each with a Fernet key
   outside the developer checkout. Record ciphertext hashes in the protocol.
5. Restrict the custody folder/key with operating-system permissions. Windows chmod
   does not establish a strong ACL boundary; use a separate OS user/custodian for
   stronger separation. Never upload keys, tokens or hidden plaintext to a coding agent.
6. Freeze the protocol before TRAIN. Seal every candidate and the complete TEST
   schedule after TRAIN, before hidden execution. Publish only hash commitments.

The solo author may remember hidden questions and can assume their own privileged
roles. Access logs and delayed reveal document procedural controls; they do not
justify independent-blinding claims. A second custodian can take ownership of the
same encrypted artifacts, OS directory and evaluator credentials later.

## Review rubric

For each deterministic pass, review the explanation, extra caveats and evidence:

- Does the prose agree with every numerical/tabular value, unit, filter and denominator?
- Does it limit the answer to the frozen benchmark subset?
- Does it preserve unknowns, scheduled/held distinctions and identity ambiguity?
- Does it avoid unsupported national, survival or causal claims?
- Are required sources genuinely supportive, with no invented or contradictory extra evidence?
- For abstention/clarification, does it avoid a fabricated result and name the limitation?

Fail on any material contradiction or unsupported assertion. The review file maps
invocation ID to `record_sha256`, `reviewer`, `rubric_sha256`, Boolean `pass`, and
optional error codes. A draft with no explicit Boolean never counts as accepted.
Reviewers do not rewrite the response. Corrections use a new review file and a
superseding assessment event; retain the old file and rationale.

Hide configuration labels during human narrative review where practical. This is
not independent assessment when the same person authored the benchmark/configuration.

## Delayed reveal

The primary controller reads encrypted payloads under evaluator custody, but invokes
the analytical agent with LAB_RUNTIME credentials. Runtime cannot read truth tables.
Native Snowflake diagnostics are restricted to exposed TRAIN questions because
native evaluation role behavior must be validated before considering hidden data.

`score` refuses hidden review before the relevant batch is complete. `decide` records
the selected RC only after the frozen TEST rule. HOLDOUT cannot execute without that
selection, and a closed campaign cannot start another HOLDOUT attempt.

Archive results before trial expiry. After public release, retain the same benchmark
for replication/regression only. New generalization claims require new hidden groups.
