# ADR-0001: Separate frozen benchmark from scientific research

Status: accepted for implementation; authorizing task TASK-0001.

The user chose a standalone repository. The source research repository has an
empirical freeze and no approved real-data redistribution disposition. The lab reads
only an approved export and never writes back. Until that export exists, all data
and performance-like outputs are labeled synthetic software fixtures.

Alternative: continue the scientific pipeline or treat an existing calendar panel
as complete ground truth. Rejected: it changes scope and bypasses evidence/release
stages. Synthetic fixtures allow software progress but provide no AI quality evidence.

Migration: introduce a new real BenchmarkRelease with reviewed source references,
rights disposition, selection-rule hash and independent oracle checks. Never relabel
SYNTHETIC-001 as real. Existing research IDs and claims stay unchanged.
