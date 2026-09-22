# ADR-0002: Freeze candidates before TEST and certify one RC on HOLDOUT

Status: accepted for implementation; authorizing task TASK-0001.

Use 24 German questions, 12/6/6 allocation, two repetitions and A0/A1/A2. TRAIN drives
development. Commit all candidate/dependency hashes before TEST. Select an RC using
the fixed multidimensional gates, then run exactly one HOLDOUT campaign. The solo
workflow is procedurally sealed, with logged custody and encryption, not independently
blinded. English translations are documentation, not extra observations.

Alternative: sequential TEST gates. Rejected because repeated feedback permits test
optimization. A sequential design would need to call TEST development validation and
use a separate unseen assessment. Alternative: optimize one scalar correctness score.
Rejected because critical failure, cost and latency must remain individually visible.

Consequences: a failed gate is a valid result. Small denominators support only pilot
descriptions. Pending review/cost data defers decisions without allowing extra calls.
Migration: exposed TEST/HOLDOUT becomes regression material; a new experiment needs
fresh hidden groups. Changes to thresholds, oracle or rubric create new versions,
never retroactive improvements to the primary result.
