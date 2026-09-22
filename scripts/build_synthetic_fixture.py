"""Create public software fixtures. These are invented, not German research facts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.artifacts import digest, file_hash  # noqa: E402
from evaluation.oracle import database, query  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "SYNTHETIC-001"


def build() -> None:
    if (ROOT / "manifest.json").exists():
        raise SystemExit("Fixture release already frozen; make a new release instead")
    ROOT.mkdir(parents=True, exist_ok=True)
    data: dict[str, list[dict[str, Any]]] = {
        table: [] for table in ["event", "event_year", "coverage", "source", "observation_source"]
    }
    for n, name in enumerate(
        ["Fiktiver See", "Fiktiver Wald", "Fiktive Stadt", "Fiktiver Berg"], 1
    ):
        data["event"].append(
            {
                "race_id": f"SYN-{n}",
                "display_name": name,
                "identity_basis": "synthetic_fixture",
                "source_identity_ref": f"FIX-{n}",
            }
        )
    # Missing event-year and explicit nulls are deliberately different cases.
    observations = [
        (1, 2021, True, True),
        (1, 2022, True, None),
        (1, 2023, True, True),
        (2, 2021, True, False),
        (2, 2022, True, True),
        (2, 2023, True, True),
        (3, 2021, True, None),
        (3, 2023, True, True),
        (4, 2021, None, None),
        (4, 2022, True, False),
        (4, 2023, True, True),
    ]
    for n, year, scheduled, held in observations:
        data["event_year"].append(
            {
                "race_id": f"SYN-{n}",
                "event_year": year,
                "state_code": "DE-BW" if n <= 2 else "DE-SH",
                "scheduled": scheduled,
                "held": held,
                "abnormal_termination": True if n == 4 and year == 2023 else None,
                "status_flags": ["held"]
                if held
                else ["cancelled_temporarily"]
                if held is False
                else ["scheduled_unknown"]
                if scheduled
                else ["unknown"],
                "identity_review_state": "synthetic_fixture",
            }
        )
        for field, value in [("scheduled", scheduled), ("held", held)]:
            if value is None:
                continue
            source_id = f"SRC-{n}-{year}-{field}"
            data["source"].append(
                {
                    "source_id": source_id,
                    "citation": "Invented software fixture",
                    "source_kind": "synthetic_result" if field == "held" else "synthetic_calendar",
                    "publication_date": f"{year}-12-31",
                    "public_locator": None,
                    "source_fingerprint": digest(source_id),
                    "redistribution_disposition": "synthetic_only",
                }
            )
            data["observation_source"].append(
                {
                    "evidence_id": f"E-{n}-{year}-{field}",
                    "race_id": f"SYN-{n}",
                    "event_year": year,
                    "field_name": field,
                    "source_id": source_id,
                    "relation": "supports",
                    "source_locator": "fixture",
                    "review_ref": "SYNTHETIC-NOT-HUMAN-RESEARCH-REVIEW",
                }
            )
    for state in ["DE-BW", "DE-SH"]:
        for year in [2021, 2022, 2023]:
            data["coverage"].append(
                {
                    "state_code": state,
                    "event_year": year,
                    "calendar_coverage": "partial",
                    "held_verification_coverage": "partial",
                    "exit_coverage": "unknown",
                    "participant_coverage": "unknown",
                    "price_coverage": "unknown",
                    "coverage_note": "Synthetic software fixture only",
                }
            )
    specs = [
        (
            "lookup",
            "Wie heißt SYN-1 im synthetischen Datensatz?",
            "SELECT display_name FROM event WHERE race_id='SYN-1'",
        ),
        (
            "lookup",
            "Welche Jahre sind für SYN-3 erfasst?",
            "SELECT event_year FROM event_year WHERE race_id='SYN-3' ORDER BY event_year",
        ),
        (
            "lookup",
            "Welche Zustände sind für SYN-2 im Jahr 2021 erfasst?",
            "SELECT scheduled, held FROM event_year WHERE race_id='SYN-2' AND event_year=2021",
        ),
        (
            "lookup",
            "Welche Veranstaltung wurde 2023 begonnen und abnormal beendet?",
            "SELECT race_id FROM event_year WHERE event_year=2023 AND abnormal_termination IS TRUE",
        ),
        (
            "aggregation",
            "Wie viele Ereignisjahre enthält die gesamte synthetische Tabelle?",
            "SELECT COUNT(*) AS observation_count FROM event_year",
        ),
        (
            "aggregation",
            "Wie viele verschiedene Identitäten enthält jede Landesgruppe?",
            "SELECT state_code, COUNT(DISTINCT race_id) AS identities FROM event_year GROUP BY state_code",
        ),
        (
            "aggregation",
            "Wie viele gelistete Beobachtungen enthält jedes Jahr?",
            "SELECT event_year, COUNT(*) AS listed_count FROM event_year WHERE scheduled IS TRUE GROUP BY event_year",
        ),
        (
            "aggregation",
            "Welche Landesgruppen haben insgesamt mehr als fünf Ereignisjahre?",
            "SELECT state_code, COUNT(*) AS observation_count FROM event_year GROUP BY state_code HAVING COUNT(*)>5",
        ),
        (
            "temporal",
            "Wie ändert sich die Zahl erfasster Beobachtungen von 2021 zu 2022?",
            "SELECT SUM(CASE WHEN event_year=2022 THEN 1 ELSE 0 END)-SUM(CASE WHEN event_year=2021 THEN 1 ELSE 0 END) AS difference FROM event_year",
        ),
        (
            "temporal",
            "In welchen Jahren ist SYN-1 nachweislich durchgeführt?",
            "SELECT event_year FROM event_year WHERE race_id='SYN-1' AND held IS TRUE",
        ),
        (
            "temporal",
            "Welche Identitäten sind 2021 und 2023 im Datensatz enthalten?",
            "SELECT a.race_id FROM event_year a JOIN event_year b ON a.race_id=b.race_id WHERE a.event_year=2021 AND b.event_year=2023",
        ),
        (
            "temporal",
            "Welches früheste und späteste erfasste Jahr hat jede Identität?",
            "SELECT race_id, MIN(event_year) AS first_year, MAX(event_year) AS last_year FROM event_year GROUP BY race_id",
        ),
        (
            "ranking_ratio",
            "Welche Identitäten haben die meisten erfassten Jahre, inklusive Gleichstand?",
            "WITH c AS (SELECT race_id, COUNT(*) AS n FROM event_year GROUP BY race_id) SELECT race_id,n FROM c WHERE n=(SELECT MAX(n) FROM c)",
        ),
        (
            "ranking_ratio",
            "Wie hoch ist 2021 der Anteil verifiziert durchgeführter an allen erfassten Beobachtungen?",
            "SELECT CAST(SUM(CASE WHEN held IS TRUE THEN 1 ELSE 0 END) AS DOUBLE)/COUNT(*) AS share FROM event_year WHERE event_year=2021",
        ),
        (
            "ranking_ratio",
            "Sortiere die Landesgruppen nach Zahl erfasster Ereignisjahre absteigend, bei Gleichstand nach Code.",
            "SELECT state_code,COUNT(*) AS n FROM event_year GROUP BY state_code ORDER BY n DESC,state_code",
        ),
        (
            "ranking_ratio",
            "Wie hoch ist der Anteil gelisteter Beobachtungen mit bekanntem Durchführungsstatus?",
            "SELECT CAST(SUM(CASE WHEN held IS NOT NULL THEN 1 ELSE 0 END) AS DOUBLE)/COUNT(*) AS share FROM event_year WHERE scheduled IS TRUE",
        ),
        (
            "missingness",
            "Wie viele Beobachtungen haben unbekannten Durchführungsstatus?",
            "SELECT COUNT(*) AS unknown_count FROM event_year WHERE held IS NULL",
        ),
        (
            "missingness",
            "Wie viele sind explizit als nicht durchgeführt erfasst?",
            "SELECT COUNT(*) AS verified_false_count FROM event_year WHERE held IS FALSE",
        ),
        (
            "missingness",
            "Ist die Durchführung von SYN-1 im Jahr 2022 bekannt? Gib den gespeicherten Wert aus.",
            "SELECT held FROM event_year WHERE race_id='SYN-1' AND event_year=2022",
        ),
        (
            "missingness",
            "Belegt die fehlende Zeile für SYN-3 2022 eine dauerhafte Einstellung?",
            None,
        ),
        (
            "scope_provenance",
            "Welche Evidenz stützt die Durchführung von SYN-1 2021?",
            "SELECT evidence_id FROM observation_source WHERE race_id='SYN-1' AND event_year=2021 AND field_name='held'",
        ),
        ("scope_provenance", "Wie viele Triathlons fanden 2023 in ganz Deutschland statt?", None),
        (
            "scope_provenance",
            "Beweist dieser Datensatz eine kausale Wirkung einer bundesweiten Regeländerung?",
            None,
        ),
        (
            "scope_provenance",
            "Welche Kalender- und Durchführungsabdeckung ist für DE-SH 2022 dokumentiert?",
            "SELECT calendar_coverage,held_verification_coverage FROM coverage WHERE state_code='DE-SH' AND event_year=2022",
        ),
    ]
    questions = []
    truths = []
    connection = database(data)
    for i, (category, text, sql) in enumerate(specs):
        qid = f"SYN-Q{i + 1:02}"
        questions.append(
            {
                "question_id": qid,
                "intent_id": f"FIX-INTENT-{i + 1:02}",
                "leakage_group_id": f"FIX-GROUP-{i + 1:02}",
                "language": "de",
                "text": text,
                "category": category,
                "difficulty": "easy" if i % 4 == 0 else "medium",
                "critical": category in {"missingness", "scope_provenance"},
                "split": ["TRAIN", "TRAIN", "TEST", "HOLDOUT"][i % 4],
                "origin": "synthetic_fixture",
            }
        )
        columns, rows = query(connection, sql) if sql else ([], [])
        expected = {
            "status": "answered" if sql else "abstain",
            "columns": columns,
            "rows": rows,
            "units": {},
            "caveats": ["synthetic_fixture_only", "benchmark_subset_only"],
            "evidence_ids": ["E-1-2021-held"] if i == 20 else [],
            "explanation_de": "Synthetische Testantwort; keine Aussage über reale Veranstaltungen.",
        }
        truths.append(
            {
                "question_id": qid,
                "expected": expected,
                "oracle_sql": sql,
                "ordered": i == 14,
                "tolerances": {"share": "0.000001"} if "share" in columns else {},
                "evidence_alternatives": [["E-1-2021-held"]] if i == 20 else [],
                "prohibited_claims": ["national_representativeness", "causal_effect"],
                "reviewer": "synthetic_fixture_programmatic_crosscheck",
            }
        )
    connection.close()
    # Independent direct calculations for representative count/ratio/null semantics.
    assert truths[4]["expected"]["rows"] == [[len(data["event_year"])]]
    assert truths[16]["expected"]["rows"] == [[sum(r["held"] is None for r in data["event_year"])]]
    assert truths[17]["expected"]["rows"] == [[sum(r["held"] is False for r in data["event_year"])]]
    assert truths[13]["expected"]["rows"] == [[1 / 4]]
    files = {"data.json": data, "questions.json": questions, "ground_truth.json": truths}
    for name, value in files.items():
        (ROOT / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    manifest = {
        "release_id": "SYNTHETIC-001",
        "schema_version": "1.0",
        "classification": "synthetic_fixture",
        "publication_disposition": "synthetic_only",
        "files": {name: file_hash(ROOT / name) for name in files},
        "selection_rule_sha256": digest("invented fixed software fixture v1"),
        "source_snapshot_refs": [],
        "frozen_at": "2026-09-19T00:00:00Z",
        "review_ref": None,
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("SYNTHETIC fixture created: 24 questions, 11 invented event-years")


if __name__ == "__main__":
    build()
