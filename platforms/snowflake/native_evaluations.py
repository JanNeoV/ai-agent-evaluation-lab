"""TRAIN-only native diagnostics, deliberately outside primary acceptance scores."""

from __future__ import annotations

import json
import re
from typing import Any

from evaluation.contracts import GroundTruth, Question, Split
from platforms.snowflake.adapter import split_reference
from platforms.snowflake.deployment import literal, qualified


def native_rows(questions: list[Question], truths: dict[str, GroundTruth]) -> list[dict[str, Any]]:
    if len(questions) > 3 or any(q.split != Split.TRAIN for q in questions):
        raise ValueError("V1 native diagnostics allow at most three TRAIN questions")
    return [
        {
            "question_id": q.question_id,
            "input_query": q.text,
            "ground_truth": {
                "ground_truth_output": "Expected typed result and caveats: "
                + json.dumps(truths[q.question_id].expected, ensure_ascii=False)
                + ". Compare numeric values, scope, nulls and evidence. "
                "Do not reward unsupported claims."
            },
        }
        for q in questions
    ]


def dataset_sql(table: str, dataset: str, rows: list[dict[str, Any]]) -> list[str]:
    qualified(table)
    qualified(dataset)
    statements = [
        f"CREATE TABLE {table} (QUESTION_ID VARCHAR, INPUT_QUERY VARCHAR, GROUND_TRUTH VARIANT);"
    ]
    for row in rows:
        statements.append(
            f"INSERT INTO {table} SELECT {literal(row['question_id'])}, "
            f"{literal(row['input_query'])}, PARSE_JSON("
            + literal(json.dumps(row["ground_truth"], ensure_ascii=False))
            + ");"
        )
    statements.append(
        "CALL SYSTEM$CREATE_EVALUATION_DATASET('Cortex Agent', "
        + literal(table)
        + ", "
        + literal(dataset)
        + ", OBJECT_CONSTRUCT('query_text', 'INPUT_QUERY', "
        "'expected_tools', 'GROUND_TRUTH'));"
    )
    return statements


def evaluation_config(deployment_ref: str, dataset: str, metric_version: str) -> dict[str, Any]:
    name, version = split_reference(deployment_ref)
    qualified(dataset)
    if not re.fullmatch(r"v[1-9][0-9]*_[0-9]+", metric_version):
        raise ValueError("Pin an exact supported native metric major_minor; auto is forbidden")
    # JSON is valid YAML; no dataset block, so repeats cannot recreate the dataset.
    return {
        "evaluation": {
            "agent_params": {
                "agent_name": name,
                "agent_type": "CORTEX AGENT",
                "agent_version": version,
            },
            "source_metadata": {"type": "dataset", "dataset_name": dataset},
        },
        "metrics": [{"name": "answer_correctness", "version": metric_version}],
    }


def execution_sql(operation: str, run_name: str, stage_path: str) -> str:
    if operation not in {"START", "STATUS", "CANCEL"}:
        raise ValueError("Only start/status/cancel are supported; evidence deletion is prohibited")
    if not re.fullmatch(r"@[A-Z0-9_.]+/[A-Za-z0-9_./-]+", stage_path):
        raise ValueError("Expected named stage configuration path")
    return (
        f"CALL EXECUTE_AI_EVALUATION('{operation}', OBJECT_CONSTRUCT('run_name', "
        + literal(run_name)
        + "), "
        + literal(stage_path)
        + ");"
    )
