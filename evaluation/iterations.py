"""Validate intervention boundaries before sealing a prospective candidate."""

from __future__ import annotations

import copy
from typing import Any

from evaluation.contracts import validate


def validate_intervention(parent: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    validate("agent_spec", parent)
    validate("agent_spec", candidate)
    if candidate["parent_id"] != parent["candidate_id"]:
        raise ValueError("Candidate parent does not match compared configuration")
    intervention = candidate["intervention"]
    metadata = {"candidate_id", "parent_id", "intervention"}
    changed = sorted(key for key in parent if key not in metadata and parent[key] != candidate[key])
    allowed = {
        "semantics": {"semantic_sha256"},
        "instructions": {"instructions", "tools"},
        "cumulative": {"semantic_sha256", "instructions", "tools"},
        "model": {"model_bindings"},
        "config": {"limits"},
    }
    if (
        not changed
        or intervention not in allowed
        or not set(changed).issubset(allowed[intervention])
    ):
        raise ValueError("Change is empty or crosses the declared intervention boundary")
    if intervention in ("instructions", "cumulative") and "tools" in changed:

        def without_descriptions(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
            result = copy.deepcopy(tools)
            for tool in result:
                tool.pop("description", None)
            return result

        if without_descriptions(parent["tools"]) != without_descriptions(candidate["tools"]):
            raise ValueError("Instruction intervention cannot change tool capabilities")
    if intervention == "config":
        keys = set(parent["limits"]) | set(candidate["limits"])
        if sum(parent["limits"].get(k) != candidate["limits"].get(k) for k in keys) != 1:
            raise ValueError("Configuration stage changes exactly one factor")
    return changed
