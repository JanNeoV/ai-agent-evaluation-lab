"""Deterministic SQL generation. Never overwrite a sealed semantic view or agent."""

from __future__ import annotations

import json
import re
from typing import Any

from evaluation.artifacts import digest
from evaluation.oracle import TABLES, validate_data


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
        raise ValueError("Use uppercase unquoted SQL identifiers")
    return value


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def qualified(value: str) -> str:
    parts = value.split(".")
    if len(parts) != 3:
        raise ValueError("Expected database.schema.object")
    return ".".join(identifier(part) for part in parts)


ANSWER_INSTRUCTION = (
    "Antworte auf Deutsch und ausschließlich als JSON-Objekt mit status "
    "(answered, abstain oder clarification_needed), columns (Liste), rows (Liste von Listen), "
    "units (Objekt), caveats (Liste von Codes), evidence_ids (Liste) und explanation_de (Text). "
    "Unbekannte Werte sind JSON null, nie 0 oder false. Verwende benchmark_subset_only als "
    "Geltungsbereich. Erfinde keine Werte. Keine Aussagen über die gesamte deutsche Population."
)


def agent_spec(
    model: str, semantic_view: str, iteration: str, warehouse: str = "LAB_XS"
) -> dict[str, Any]:
    if iteration not in {"A0", "A1", "A2"} or not re.fullmatch(r"[a-zA-Z0-9_.-]+", model):
        raise ValueError("Invalid iteration or explicit model name")
    qualified(semantic_view)
    warehouse = identifier(warehouse)
    response = ANSWER_INSTRUCTION
    planning = "Nutze das analytische Werkzeug für Fragen zu den bereitgestellten Tabellen."
    description = "Liest den eingefrorenen Ereignisjahresdatensatz."
    if iteration == "A2":
        planning += (
            " Prüfe Grain, Filter, NULL-Werte und Nenner vor der Antwort. "
            "Kalendereinträge belegen nur Planung; ohne positive Evidenz ist held unbekannt. "
            "Eine fehlende Zeile belegt keine Einstellung. Frage nach, wenn eine notwendige "
            "Definition fehlt, und lehne unbelegte nationale oder kausale Schlüsse ab."
        )
        response += (
            " Nenne erforderliche Einschränkungen und Evidenz-IDs. "
            "Die Erklärung darf den Tabellenwerten nicht widersprechen."
        )
        description += " Enthält Ereignisjahre, Identitäten, Abdeckung und normalisierte Evidenz."
    return {
        "models": {"orchestration": model},
        "orchestration": {
            "tool_not_accessible": "reject",
            "budget": {"seconds": 60, "tokens": 4096},
        },
        "instructions": {"response": response, "orchestration": planning},
        "tools": [
            {
                "tool_spec": {
                    "type": "cortex_analyst_text_to_sql",
                    "name": "benchmark_analyst",
                    "description": description,
                }
            }
        ],
        "tool_resources": {
            "benchmark_analyst": {
                "semantic_view": semantic_view,
                "execution_environment": {
                    "type": "warehouse",
                    "warehouse": warehouse,
                },
            }
        },
    }


def semantic_sql(database: str, table_schema: str, improved: bool) -> tuple[str, str]:
    db, schema = identifier(database), identifier(table_schema)
    table = f"{db}.{schema}"
    comment = (
        "Frozen benchmark subset; event grain is race_id, event_year. "
        "scheduled does not imply held; NULL is unknown. No causal/population inference."
    )
    definition = f"""TABLES (
  e AS {table}.EVENT PRIMARY KEY (RACE_ID),
  ey AS {table}.EVENT_YEAR PRIMARY KEY (RACE_ID, EVENT_YEAR),
  c AS {table}.COVERAGE PRIMARY KEY (STATE_CODE, EVENT_YEAR),
  s AS {table}.SOURCE PRIMARY KEY (SOURCE_ID),
  os AS {table}.OBSERVATION_SOURCE PRIMARY KEY (EVIDENCE_ID)
)
RELATIONSHIPS (
  ey_to_event AS ey (RACE_ID) REFERENCES e (RACE_ID),
  ey_to_coverage AS ey (STATE_CODE, EVENT_YEAR) REFERENCES c (STATE_CODE, EVENT_YEAR),
  evidence_to_observation AS os (RACE_ID, EVENT_YEAR) REFERENCES ey (RACE_ID, EVENT_YEAR),
  evidence_to_source AS os (SOURCE_ID) REFERENCES s (SOURCE_ID)
)
DIMENSIONS (
  e.race_id AS e.RACE_ID,
  e.display_name AS e.DISPLAY_NAME,
  ey.event_year AS ey.EVENT_YEAR,
  ey.state_code AS ey.STATE_CODE,
  ey.scheduled AS ey.SCHEDULED,
  ey.held AS ey.HELD,
  ey.abnormal_termination AS ey.ABNORMAL_TERMINATION,
  c.calendar_coverage AS c.CALENDAR_COVERAGE,
  c.held_verification_coverage AS c.HELD_VERIFICATION_COVERAGE,
  os.evidence_id AS os.EVIDENCE_ID,
  os.field_name AS os.FIELD_NAME,
  os.relation AS os.RELATION,
  s.source_id AS s.SOURCE_ID,
  s.citation AS s.CITATION
)"""
    if improved:
        definition += """
METRICS (
  ey.observation_count AS COUNT(*),
  ey.known_held_count AS SUM(CASE WHEN ey.HELD IS TRUE THEN 1 ELSE 0 END),
  ey.unknown_held_count AS SUM(CASE WHEN ey.HELD IS NULL THEN 1 ELSE 0 END)
)"""
    definition += "\nCOMMENT = " + literal(comment)
    if improved:
        definition += "\nAI_SQL_GENERATION " + literal(
            "Count event-years before joining evidence, which is one-to-many. "
            "Treat scheduled and held separately. Preserve unknowns. "
            "Missing rows do not establish historical nonexistence. "
            "Quote the scope of every denominator. No evidence of national representativeness."
        )
    name = "SV_" + digest(definition)[:12].upper()
    return f"{db}.SEMANTICS.{name}", f"CREATE SEMANTIC VIEW {db}.SEMANTICS.{name}\n{definition};"


def table_sql(database: str, schema: str, data: dict[str, list[dict[str, Any]]]) -> list[str]:
    validate_data(data)
    prefix = f"{identifier(database)}.{identifier(schema)}"
    statements = []
    for table, columns in TABLES.items():
        types = {"JSON": "VARIANT", "INTEGER": "NUMBER(10,0)"}
        definitions = ", ".join(f"{name.upper()} {types.get(kind, kind)}" for name, kind in columns)
        statements.append(f"CREATE TABLE {prefix}.{table.upper()} ({definitions});")
        for row in data[table]:
            values = []
            for name, kind in columns:
                value = row[name]
                if value is None:
                    values.append("NULL")
                elif kind == "JSON":
                    values.append(
                        "PARSE_JSON(" + literal(json.dumps(value, ensure_ascii=False)) + ")"
                    )
                elif isinstance(value, bool):
                    values.append("TRUE" if value else "FALSE")
                elif isinstance(value, int):
                    values.append(str(value))
                else:
                    values.append(literal(str(value)))
            statements.append(
                f"INSERT INTO {prefix}.{table.upper()} SELECT " + ", ".join(values) + ";"
            )
    return statements


def render_bundle(
    database: str,
    table_schema: str,
    data: dict[str, list[dict[str, Any]]],
    model: str,
    a2_parent: str = "A1",
    warehouse: str = "LAB_XS",
) -> dict[str, Any]:
    if a2_parent not in {"A0", "A1"}:
        raise ValueError("A2 must use the last TRAIN-promoted A0 or A1")
    db = identifier(database)
    baseline_view, baseline_sql = semantic_sql(db, table_schema, False)
    improved_view, improved_sql = semantic_sql(db, table_schema, True)
    candidates = {}
    for iteration in ["A0", "A1", "A2"]:
        baseline = iteration == "A0" or (iteration == "A2" and a2_parent == "A0")
        view = baseline_view if baseline else improved_view
        spec = agent_spec(model, view, iteration, warehouse)
        parent = None if iteration == "A0" else "A0" if iteration == "A1" else a2_parent
        candidates[iteration] = {
            "spec": spec,
            "semantic_view": view,
            "spec_sha256": digest(spec),
            "parent": parent,
        }
    return {
        "database": db,
        "table_schema": identifier(table_schema),
        "tables": table_sql(db, table_schema, data),
        "semantic_views": [baseline_sql, improved_sql],
        "candidates": candidates,
    }


def create_agent_sql(name: str, spec: dict[str, Any]) -> str:
    # Single-quoted JSON is also a valid YAML specification, without $$ injection.
    return (
        f"CREATE AGENT {qualified(name)} FROM SPECIFICATION "
        + literal(json.dumps(spec, ensure_ascii=False))
        + ";"
    )


def import_version_sql(name: str, stage_folder: str) -> str:
    if not re.fullmatch(r"@[A-Z0-9_.]+/[A-Za-z0-9_/-]+", stage_folder):
        raise ValueError("Use a validated named stage folder")
    return f"ALTER AGENT {qualified(name)} ADD VERSION FROM {stage_folder};"


# --- R1 aggregate renderer (TASK-0007) ---


R1_TABLE = "P2_CORE_EDITION"
R1_STRING_COLUMNS = frozenset({"series_id", "event", "festival_id", "state", "distance", "era"})
R1_INTEGER_COLUMNS = frozenset(
    {
        "event_year",
        "eligible_finishers",
        "sex_recorded",
        "sex_missing",
        "female_count",
        "male_count",
        "other_sex_count",
        "age_recorded",
        "age_missing",
        "age_year_difference_count",
        "age_band_mappable",
        "age_band_unmapped",
        "age_under_30_count",
        "age_30_49_count",
        "age_50_plus_count",
    }
)
R1_COLUMN_ORDER = (
    "series_id",
    "event",
    "festival_id",
    "state",
    "distance",
    "event_year",
    "era",
    "eligible_finishers",
    "sex_recorded",
    "sex_missing",
    "sex_completeness",
    "female_count",
    "male_count",
    "other_sex_count",
    "female_share_known",
    "age_recorded",
    "age_missing",
    "age_completeness",
    "age_year_difference_count",
    "mean_age_year_difference",
    "median_age_year_difference",
    "age_band_mappable",
    "age_band_unmapped",
    "age_band_mapping_completeness",
    "age_under_30_count",
    "age_30_49_count",
    "age_50_plus_count",
    "share_under_30_mapped",
    "share_30_49_mapped",
    "share_50_plus_mapped",
)


def r1_table_ddl(database: str, schema: str) -> str:
    prefix = f"{identifier(database)}.{identifier(schema)}"
    cols = []
    for col in R1_COLUMN_ORDER:
        upper = col.upper()
        if col in R1_STRING_COLUMNS:
            cols.append(f"{upper} VARCHAR NOT NULL")
        elif col in R1_INTEGER_COLUMNS:
            cols.append(f"{upper} NUMBER(10,0) NOT NULL")
        else:
            cols.append(f"{upper} DECIMAL(18,9)")
    return f"CREATE TABLE {prefix}.{R1_TABLE} (\n  " + ",\n  ".join(cols) + "\n);"


def r1_insert_sql(database: str, schema: str, rows: list[dict[str, Any]]) -> list[str]:
    prefix = f"{identifier(database)}.{identifier(schema)}"
    statements = []
    for row in rows:
        values = []
        for col in R1_COLUMN_ORDER:
            value = row[col]
            if value is None or value == "":
                values.append("NULL")
            elif col in R1_STRING_COLUMNS:
                values.append(literal(str(value)))
            elif col in R1_INTEGER_COLUMNS:
                values.append(str(int(value)))
            else:
                values.append(str(value))
        statements.append(f"INSERT INTO {prefix}.{R1_TABLE} SELECT " + ", ".join(values) + ";")
    return statements


def r1_semantic_sql(database: str, schema: str) -> tuple[str, str]:
    db, sch = identifier(database), identifier(schema)
    table_ref = f"{db}.{sch}.{R1_TABLE}"
    comment = (
        "Frozen R1 P2 CORE aggregate; edition grain is series_id, event_year. "
        "Four series, 40 editions. NULL is unknown, not zero. "
        "No causal, national, or population inference."
    )
    definition = f"""TABLES (
  p AS {table_ref} PRIMARY KEY (SERIES_ID, EVENT_YEAR)
)
DIMENSIONS (
  p.series_id AS p.SERIES_ID,
  p.event AS p.EVENT,
  p.festival_id AS p.FESTIVAL_ID,
  p.state AS p.STATE,
  p.distance AS p.DISTANCE,
  p.event_year AS p.EVENT_YEAR,
  p.era AS p.ERA
)
COMMENT = {literal(comment)}"""
    name = "SV_" + digest(definition)[:12].upper()
    full_name = f"{db}.SEMANTICS.{name}"
    return full_name, f"CREATE SEMANTIC VIEW {full_name}\n{definition};"


def r1_agent_spec(
    model: str,
    semantic_view: str,
    candidate_id: str,
    warehouse: str = "LAB_XS",
) -> dict[str, Any]:
    if candidate_id not in {"V0", "V1", "V2", "V3"}:
        raise ValueError("R1 candidate must be V0-V3")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", model):
        raise ValueError("Invalid model name")
    qualified(semantic_view)
    warehouse = identifier(warehouse)
    response = ANSWER_INSTRUCTION
    planning = "Nutze das analytische Werkzeug für Fragen zu den bereitgestellten Tabellen."
    description = "Liest den eingefrorenen P2 CORE Ausgabendatensatz."
    return {
        "models": {"orchestration": model},
        "orchestration": {
            "tool_not_accessible": "reject",
            "budget": {"seconds": 60, "tokens": 4096},
        },
        "instructions": {"response": response, "orchestration": planning},
        "tools": [
            {
                "tool_spec": {
                    "type": "cortex_analyst_text_to_sql",
                    "name": "benchmark_analyst",
                    "description": description,
                }
            }
        ],
        "tool_resources": {
            "benchmark_analyst": {
                "semantic_view": semantic_view,
                "execution_environment": {
                    "type": "warehouse",
                    "warehouse": warehouse,
                },
            }
        },
    }
