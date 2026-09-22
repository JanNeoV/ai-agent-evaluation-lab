"""Canonical serialization, immutable files and an auditable event ledger."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON value: {value}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_constant,
        object_pairs_hook=unique_pairs,
    )


def write_once(path: Path, value: Any) -> str:
    payload = canonical(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create: existing frozen artifacts cannot be silently replaced.
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return file_hash(path)


def contained(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes package root")
    return target


def verify_files(root: Path, hashes: Mapping[str, str]) -> None:
    for relative, expected in hashes.items():
        if file_hash(contained(root, relative)) != expected:
            raise ValueError(f"Artifact integrity failure: {relative}")


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(fd)
        path.unlink()


class Ledger:
    """Hash-chained events; use external seal hashes to detect full-tail truncation."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        previous = "0" * 64
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            checksum = item.pop("sha256")
            if item["previous"] != previous or digest(item) != checksum:
                raise ValueError("Ledger integrity failure")
            if item["sequence"] != len(events):
                raise ValueError("Ledger sequence failure")
            item["sha256"] = checksum
            events.append(item)
            previous = checksum
        return events

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(self.path.with_suffix(".lock")):
            events = self.read()
            item = {
                "sequence": len(events),
                "previous": events[-1]["sha256"] if events else "0" * 64,
                "at": utc_now(),
                "kind": kind,
                "payload": payload,
            }
            item["sha256"] = digest(item)
            with self.path.open("ab") as handle:
                handle.write(canonical(item) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        return item
