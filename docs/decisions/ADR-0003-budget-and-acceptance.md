# ADR-0003: Deterministic truth plus review, conservative trial budget

Status: accepted for implementation; authorizing task TASK-0001.

Primary acceptance requires typed result equality and reviewed narrative correctness.
Native LLM judges are versioned secondary diagnostics, TRAIN-only in v1. Every failed
submission counts; no quality retries. Use decimal costs, explicit unknown attribution,
request-level agent token charges and a reviewed allocation of whole warehouse cost.

Alternative: native judge alone. Rejected because judge agreement is not deterministic
truth and native rubrics change. Alternative: count only successful-query/token cost.
Rejected because failed attempts, idle/resume compute and evaluation overhead matter.

Admission target: at most USD 10 equivalent with USD 2 reserve, fresh trial balance
and expiry check, outstanding reservations and future hidden-campaign funding. No
paid conversion. Delayed billing prevents claiming a perfectly atomic spend cap.

Migration: bind new rate cards/judge versions prospectively. Preserve estimated and
final cost events; never replace unknown usage with zero. Real deployment validation
is deferred until the user configures Snowflake access; local tests make no cloud claims.
