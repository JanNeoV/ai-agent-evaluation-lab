"""Exactly accounted, single-concurrency invocation batches without quality retries."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evaluation.artifacts import (
    Ledger,
    digest,
    exclusive_lock,
    file_hash,
    load_json,
    utc_now,
    write_once,
)
from evaluation.contracts import InvocationRequest, PlatformAdapter, Question, Split, validate
from evaluation.costs import Budget
from evaluation.sealing import Campaign


def schedule(questions: list[Question], candidates: list[str], seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    blocks = [(q.question_id, repetition) for q in questions for repetition in range(2)]
    rng.shuffle(blocks)
    rows: list[dict[str, Any]] = []
    for question_id, repetition in blocks:
        order = sorted(candidates)
        rng.shuffle(order)
        for candidate in order:
            rows.append(
                {
                    "invocation_id": f"{candidate}-{question_id}-R{repetition}",
                    "candidate_id": candidate,
                    "question_id": question_id,
                    "repetition": repetition,
                }
            )
    validate_schedule(rows)
    return rows


def validate_schedule(rows: list[dict[str, Any]]) -> None:
    ids: set[str] = set()
    combinations: set[tuple[str, str, int]] = set()
    for row in rows:
        identifier = row["invocation_id"]
        if not identifier or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in identifier
        ):
            raise ValueError("Unsafe invocation ID")
        combo = (row["candidate_id"], row["question_id"], row["repetition"])
        if identifier in ids or combo in combinations or row["repetition"] not in {0, 1}:
            raise ValueError("Duplicate invocation or invalid repetition")
        ids.add(identifier)
        combinations.add(combo)
    for candidate, question, _ in combinations:
        if not all((candidate, question, repetition) in combinations for repetition in range(2)):
            raise ValueError("Unbalanced repetitions")


def run_batch(
    root: Path,
    adapter: PlatformAdapter,
    questions: list[Question],
    deployments: dict[str, dict[str, Any]],
    plan: list[dict[str, Any]],
    budget: Budget,
    batch_id: str,
    campaign: Campaign | None = None,
    synthetic: bool = False,
) -> list[dict[str, Any]]:
    validate_schedule(plan)
    if not questions or len({q.split for q in questions}) != 1:
        raise ValueError("One nonempty split per batch")
    split = questions[0].split
    if not synthetic and campaign is None:
        raise ValueError("Real invocations require a campaign")
    if synthetic and any(q.origin != "synthetic_fixture" for q in questions):
        raise ValueError("Synthetic mode cannot run real questions")
    if campaign:
        campaign.authorize(split, "execute")
        if split == Split.TEST:
            sealed = campaign.verify_seal()
            if deployments != sealed or plan != load_json(campaign.root / "test_schedule.json"):
                raise ValueError("TEST differs from sealed candidates/schedule")
        if split == Split.HOLDOUT:
            selected = campaign.selected_candidate()
            sealed = campaign.verify_seal()
            if deployments != {selected: sealed[selected]}:
                raise ValueError("HOLDOUT must use the one selected sealed candidate")
            if len(questions) != 6 or len(plan) != 12:
                raise ValueError("HOLDOUT requires all six questions and both repetitions")
    question_map = {q.question_id: q for q in questions}
    if len(question_map) != len(questions):
        raise ValueError("Duplicate questions")
    expected = {(c, q, r) for c in deployments for q in question_map for r in range(2)}
    if {(p["candidate_id"], p["question_id"], p["repetition"]) for p in plan} != expected:
        raise ValueError("Schedule does not account for every question/candidate/repetition")
    balances = budget.balances()
    if batch_id not in balances["pending"]:
        raise ValueError("Batch has no outstanding budget reservation")
    reservation = next(
        e["payload"]
        for e in budget.ledger.read()
        if e["kind"] == "reserve" and e["payload"]["batch_id"] == batch_id
    )
    if reservation["invocation_count"] != len(plan):
        raise ValueError("Budget reservation covers a different number of invocations")
    if not synthetic and datetime.now(UTC) - datetime.fromisoformat(
        reservation["observed_at"]
    ) > timedelta(minutes=15):
        raise ValueError("Batch preflight is stale")
    for deployment in deployments.values():
        if not adapter.verify(deployment).get("verified"):
            raise ValueError("Deployment verification failed")
    root.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(root / ".run.lock"):
        plan_path = root / "schedule.json"
        if not plan_path.exists():
            write_once(plan_path, plan)
            write_once(
                root / "batch.json",
                {
                    "batch_id": batch_id,
                    "synthetic": synthetic,
                    "split": split.value,
                    "deployments_sha256": digest(deployments),
                    "questions_sha256": digest([q.__dict__ for q in questions]),
                },
            )
        elif load_json(plan_path) != plan or load_json(root / "batch.json") != {
            "batch_id": batch_id,
            "synthetic": synthetic,
            "split": split.value,
            "deployments_sha256": digest(deployments),
            "questions_sha256": digest([q.__dict__ for q in questions]),
        }:
            raise ValueError("Cannot resume a changed batch")
        events = Ledger(root / "events.jsonl")
        submitted = {
            e["payload"]["invocation_id"] for e in events.read() if e["kind"] == "submitted"
        }
        if campaign and split in {Split.TEST, Split.HOLDOUT}:
            initial = "SEALED" if split == Split.TEST else "RC_SELECTED"
            if campaign.state() == initial:
                campaign.transition(initial, f"{split.value}_RUNNING", batch_id=batch_id)
        results: list[dict[str, Any]] = []
        for row in plan:
            identifier = row["invocation_id"]
            output_path = root / "invocations" / f"{identifier}.json"
            if output_path.exists():
                saved = load_json(output_path)
                completed = next(
                    (
                        event
                        for event in events.read()
                        if event["kind"] == "completed"
                        and event["payload"]["invocation_id"] == identifier
                    ),
                    None,
                )
                if identifier not in submitted or completed is None:
                    raise ValueError("Uncommitted response artifact: reconcile before resuming")
                if digest(saved) != completed["payload"]["record_sha256"]:
                    raise ValueError("Saved invocation integrity failure")
                if file_hash(root / "raw" / f"{identifier}.json") != saved["raw_sha256"]:
                    raise ValueError("Raw response integrity failure")
                results.append(saved)
                continue
            if identifier in submitted:
                raise ValueError("Ambiguous prior submission: reconcile without automatic retry")
            # Never call the adapter before a durable submission record exists.
            started = utc_now()
            events.append("submitted", {"invocation_id": identifier, "started_at": started})
            request = InvocationRequest(
                identifier,
                row["candidate_id"],
                deployments[row["candidate_id"]]["deployment_ref"],
                question_map[row["question_id"]].text,
                row["repetition"],
            )
            result = adapter.invoke(request)
            raw_hash = write_once(root / "raw" / f"{identifier}.json", result.raw)
            record = {
                **row,
                "status": result.status,
                "response_text": result.response_text,
                "latency_ms": result.latency_ms,
                "request_id": result.request_id,
                "raw_sha256": raw_hash,
                "started_at": started,
                "completed_at": utc_now(),
                "error_code": result.error_code,
            }
            validate("invocation", record)
            write_once(output_path, record)
            events.append(
                "completed", {"invocation_id": identifier, "record_sha256": digest(record)}
            )
            results.append(record)
        if campaign and split in {Split.TEST, Split.HOLDOUT}:
            campaign.transition(
                f"{split.value}_RUNNING", f"{split.value}_COMPLETE", results_sha256=digest(results)
            )
        return results
