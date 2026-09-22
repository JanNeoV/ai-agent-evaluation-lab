"""Encrypted evaluator artifacts and an explicit delayed-reveal state machine."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from evaluation.artifacts import (
    Ledger,
    canonical,
    digest,
    exclusive_lock,
    file_hash,
    load_json,
    utc_now,
    write_once,
)
from evaluation.contracts import Split


class Campaign:
    def __init__(self, root: Path):
        self.root = root
        self.ledger = Ledger(root / "events.jsonl")

    def initialize(self, protocol: dict[str, Any]) -> None:
        if protocol.get("template_only"):
            raise ValueError("Fill and review protocol template before freezing")
        if protocol.get("repetitions") != 2 or protocol.get("automatic_retries") != 0:
            raise ValueError("V1 requires two repetitions and no automatic retries")
        if protocol.get("classification") == "prospective_procedurally_sealed":
            for name in [
                "benchmark_manifest",
                "train_questions_sha256",
                "dependency_lock_sha256",
                "evaluation_spec_sha256",
            ]:
                if not re.fullmatch(r"[a-f0-9]{64}", str(protocol.get(name, ""))):
                    raise ValueError(f"Real protocol requires a frozen {name}")
            if not re.fullmatch(r"[a-f0-9]{40,64}", str(protocol.get("git_commit", ""))):
                raise ValueError("Real protocol requires a committed code revision")
            for split in ["TEST", "HOLDOUT"]:
                if not re.fullmatch(
                    r"[a-f0-9]{64}", protocol.get("sealed_payloads", {}).get(split, "")
                ):
                    raise ValueError("Real protocol requires sealed TEST/HOLDOUT hashes")
        write_once(self.root / "protocol.json", protocol)
        self.ledger.append("initialize", {"protocol_sha256": digest(protocol), "state": "TRAIN"})

    def state(self) -> str:
        events = self.ledger.read()
        if not events:
            raise ValueError("Campaign not initialized")
        if (
            digest(load_json(self.root / "protocol.json"))
            != events[0]["payload"]["protocol_sha256"]
        ):
            raise ValueError("Protocol mutated")
        return str(next(e["payload"]["state"] for e in reversed(events) if "state" in e["payload"]))

    def transition(self, expected: str, state: str, **metadata: Any) -> None:
        allowed = {
            "SEALED": "TEST_RUNNING",
            "TEST_RUNNING": "TEST_COMPLETE",
            "TEST_COMPLETE": "TEST_REVEALED",
            "RC_SELECTED": "HOLDOUT_RUNNING",
            "HOLDOUT_RUNNING": "HOLDOUT_COMPLETE",
            "HOLDOUT_COMPLETE": "CLOSED",
        }
        if allowed.get(expected) != state:
            raise ValueError("Transition requires a dedicated sealing/selection method")
        with exclusive_lock(self.root / ".campaign.lock"):
            if self.state() != expected:
                raise ValueError(f"Expected {expected}; campaign is {self.state()}")
            self.ledger.append("transition", {"state": state, **metadata})

    def seal(self, candidates: dict[str, dict[str, Any]], schedule: list[dict[str, Any]]) -> None:
        with exclusive_lock(self.root / ".campaign.lock"):
            if self.state() != "TRAIN":
                raise ValueError("Candidates can be sealed only before TEST")
            r1_four_candidates = set(candidates) == {"V0", "V1", "V2", "V3"}
            baseline_two_or_three = 2 <= len(candidates) <= 3 and "A0" in candidates
            if not (r1_four_candidates or baseline_two_or_three):
                # ADR-0004: Benchmark R1 seals exactly V0-V3; the frozen synthetic baseline
                # (A0 plus one or two candidates) remains supported unchanged.
                raise ValueError("Sealing requires A0 and one or two candidates, or exactly V0-V3")
            if {r["candidate_id"] for r in schedule} != set(candidates):
                raise ValueError("TEST schedule must cover every candidate")
            from evaluation.runner import validate_schedule

            validate_schedule(schedule)
            counts = {key: sum(r["candidate_id"] == key for r in schedule) for key in candidates}
            if set(counts.values()) != {12}:
                raise ValueError("Each TEST candidate requires six questions repeated twice")
            hashes = {key: digest(value) for key, value in candidates.items()}
            write_once(self.root / "candidate_bundle.json", candidates)
            write_once(self.root / "test_schedule.json", schedule)
            self.ledger.append(
                "seal",
                {"state": "SEALED", "candidates": hashes, "schedule_sha256": digest(schedule)},
            )

    def verify_seal(self) -> dict[str, dict[str, Any]]:
        self.state()
        event = next((e for e in self.ledger.read() if e["kind"] == "seal"), None)
        if event is None:
            raise ValueError("Candidates have not been sealed")
        candidates: dict[str, dict[str, Any]] = load_json(self.root / "candidate_bundle.json")
        if {k: digest(v) for k, v in candidates.items()} != event["payload"]["candidates"]:
            raise ValueError("Candidate bundle mutated")
        if (
            digest(load_json(self.root / "test_schedule.json"))
            != event["payload"]["schedule_sha256"]
        ):
            raise ValueError("Sealed schedule mutated")
        return candidates

    def select(self, decision: dict[str, Any]) -> None:
        with exclusive_lock(self.root / ".campaign.lock"):
            if self.state() != "TEST_REVEALED":
                raise ValueError("Selection requires completed, revealed TEST")
            candidates = self.verify_seal()
            candidate = decision.get("candidate_id")
            if candidate is not None and candidate not in candidates:
                raise ValueError("Selected candidate was not sealed")
            if decision.get("decision") not in {"accepted", "rejected", "inconclusive"}:
                raise ValueError("Invalid decision")
            if decision["decision"] == "inconclusive":
                self.ledger.append(
                    "decision_deferred",
                    {"decision_sha256": digest(decision), "reason": decision.get("reason")},
                )
                return
            if (decision["decision"] == "accepted") != (candidate is not None):
                raise ValueError("Only an accepted TEST decision selects an RC")
            write_once(self.root / "test_decision.json", decision)
            self.ledger.append(
                "selection",
                {
                    "state": "RC_SELECTED" if candidate else "CLOSED",
                    "decision_sha256": digest(decision),
                    "candidate_id": candidate,
                },
            )

    def selected_candidate(self) -> str:
        events = [e for e in self.ledger.read() if e["kind"] == "selection"]
        if not events or events[-1]["payload"]["candidate_id"] is None:
            raise ValueError("No selected release candidate")
        if (
            digest(load_json(self.root / "test_decision.json"))
            != events[-1]["payload"]["decision_sha256"]
        ):
            raise ValueError("Selection decision mutated")
        return str(events[-1]["payload"]["candidate_id"])

    def authorize(self, split: Split, purpose: str) -> None:
        state = self.state()
        if split == Split.TRAIN:
            return
        allowed = {
            (Split.TEST, "execute"): {"SEALED", "TEST_RUNNING"},
            (Split.TEST, "review"): {
                "TEST_COMPLETE",
                "TEST_REVEALED",
                "RC_SELECTED",
                "HOLDOUT_RUNNING",
                "HOLDOUT_COMPLETE",
                "CLOSED",
            },
            (Split.HOLDOUT, "execute"): {"RC_SELECTED", "HOLDOUT_RUNNING"},
            (Split.HOLDOUT, "review"): {"HOLDOUT_COMPLETE", "CLOSED"},
        }
        if state not in allowed.get((split, purpose), set()):
            raise PermissionError(f"{split} {purpose} forbidden in {state}")
        self.verify_seal()
        if split == Split.HOLDOUT:
            self.selected_candidate()
        if purpose == "review":
            required = "test_complete" if split == Split.TEST else "holdout_complete"
            if not any(
                e["kind"] == "transition" and e["payload"].get("state", "").lower() == required
                for e in self.ledger.read()
            ):
                raise PermissionError("No completed campaign for this split")


def seal_payload(
    payload: dict[str, Any], target: Path, key_file: Path, developer_root: Path
) -> str:
    if key_file.resolve().is_relative_to(developer_root.resolve()):
        raise ValueError("Evaluator key must be outside the developer checkout")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        with key_file.open("xb") as handle:
            handle.write(Fernet.generate_key())
        key_file.chmod(0o600)
    encrypted = Fernet(key_file.read_bytes().strip()).encrypt(canonical(payload))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(encrypted)
    return file_hash(target)


def open_payload(
    path: Path,
    key_file: Path,
    campaign: Campaign,
    split: Split,
    purpose: str,
    actor: str,
    expected_hash: str,
) -> dict[str, Any]:
    import json

    campaign.authorize(split, purpose)
    if file_hash(path) != expected_hash:
        raise ValueError("Encrypted package integrity failure")
    campaign.ledger.append(
        "disclosure",
        {
            "actor": actor,
            "role": "LAB_EVALUATOR",
            "artifact_sha256": expected_hash,
            "purpose": purpose,
            "split": split.value,
            "at": utc_now(),
            "state_at_access": campaign.state(),
        },
    )
    payload: dict[str, Any] = json.loads(
        Fernet(key_file.read_bytes().strip()).decrypt(path.read_bytes())
    )
    return payload
