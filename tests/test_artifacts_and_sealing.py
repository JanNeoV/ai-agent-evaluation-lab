from dataclasses import replace

import pytest

from evaluation.artifacts import Ledger, digest, file_hash, load_json, verify_files, write_once
from evaluation.contracts import Split, validate_splits
from evaluation.runner import schedule
from evaluation.sealing import Campaign, open_payload, seal_payload


def campaign(tmp_path):
    result = Campaign(tmp_path / "campaign")
    result.initialize({"repetitions": 2, "automatic_retries": 0})
    return result


def test_immutable_artifacts_and_path_escape(tmp_path):
    write_once(tmp_path / "f.json", {"x": 1})
    with pytest.raises(FileExistsError):
        write_once(tmp_path / "f.json", {"x": 2})
    with pytest.raises(ValueError):
        verify_files(tmp_path, {"../outside": "0" * 64})


def test_ledger_detects_content_mutation(tmp_path):
    ledger = Ledger(tmp_path / "events.jsonl")
    ledger.append("submit", {"id": "one"})
    ledger.append("finish", {"id": "one"})
    assert len(ledger.read()) == 2
    ledger.path.write_text(ledger.path.read_text().replace('"one"', '"two"'))
    with pytest.raises(ValueError, match="integrity"):
        ledger.read()


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"x":1,"x":2}')
    with pytest.raises(ValueError, match="Duplicate"):
        load_json(path)


def test_no_hidden_access_during_train(tmp_path):
    c = campaign(tmp_path)
    for split in [Split.TEST, Split.HOLDOUT]:
        for purpose in ["execute", "review"]:
            with pytest.raises(PermissionError):
                c.authorize(split, purpose)


def test_candidates_and_schedule_are_sealed(tmp_path, questions):
    c = campaign(tmp_path)
    qs = [q for q in questions if q.split == Split.TEST]
    c.seal({"A0": {}, "A1": {}}, schedule(qs, ["A0", "A1"], 9))
    c.authorize(Split.TEST, "execute")
    with pytest.raises(PermissionError):
        c.authorize(Split.TEST, "review")
    with pytest.raises(ValueError):
        c.seal({"A0": {}, "A1": {}}, [])
    (c.root / "candidate_bundle.json").write_text('{"A0":{},"A1":{"changed":true}}')
    with pytest.raises(ValueError, match="mutated"):
        c.verify_seal()


def test_r1_four_candidates_can_be_sealed(tmp_path, questions):
    # ADR-0004: Benchmark R1 seals exactly V0-V3, without a mandatory A0/2-3 baseline shape.
    c = campaign(tmp_path)
    qs = [q for q in questions if q.split == Split.TEST]
    c.seal(
        {"V0": {}, "V1": {}, "V2": {}, "V3": {}},
        schedule(qs, ["V0", "V1", "V2", "V3"], 9),
    )
    c.authorize(Split.TEST, "execute")


def test_partial_v_candidates_still_rejected(tmp_path, questions):
    c = campaign(tmp_path)
    qs = [q for q in questions if q.split == Split.TEST]
    with pytest.raises(ValueError, match="V0-V3"):
        c.seal({"V0": {}, "V1": {}, "V2": {}}, schedule(qs, ["V0", "V1", "V2"], 9))


def test_holdout_requires_selected_candidate(tmp_path, questions):
    c = campaign(tmp_path)
    c.seal(
        {"A0": {}, "A1": {}},
        schedule([q for q in questions if q.split == Split.TEST], ["A0", "A1"], 9),
    )
    c.transition("SEALED", "TEST_RUNNING")
    c.transition("TEST_RUNNING", "TEST_COMPLETE")
    c.transition("TEST_COMPLETE", "TEST_REVEALED")
    c.select({"candidate_id": None, "decision": "rejected"})
    with pytest.raises(PermissionError):
        c.authorize(Split.HOLDOUT, "execute")
    with pytest.raises(ValueError):
        c.select({"candidate_id": "A1", "decision": "accepted"})


def test_ciphertext_integrity_and_external_key(tmp_path, questions):
    developer = tmp_path / "developer"
    developer.mkdir()
    c = campaign(developer)
    path = developer / "test.enc"
    with pytest.raises(ValueError, match="outside"):
        seal_payload({"secret": "expected answer"}, path, developer / "key", developer)
    key = tmp_path / "custodian" / "key"
    hash_value = seal_payload({"secret": "expected answer"}, path, key, developer)
    assert b"expected answer" not in path.read_bytes()
    c.seal(
        {"A0": {}, "A1": {}},
        schedule([q for q in questions if q.split == Split.TEST], ["A0", "A1"], 9),
    )
    assert open_payload(path, key, c, Split.TEST, "execute", "evaluator", hash_value)["secret"]
    with pytest.raises(ValueError, match="integrity"):
        open_payload(path, key, c, Split.TEST, "execute", "evaluator", "0" * 64)
    assert file_hash(path) == hash_value
    assert any(e["kind"] == "disclosure" for e in c.ledger.read())


def test_paraphrase_and_translation_group_cannot_cross_split(questions):
    validate_splits(questions)
    changed = list(questions)
    changed[2] = replace(changed[2], leakage_group_id=changed[0].leakage_group_id)
    with pytest.raises(ValueError, match="crosses"):
        validate_splits(changed)
    changed = list(questions)
    changed[2] = replace(changed[2], intent_id=changed[0].intent_id, language="en")
    with pytest.raises(ValueError, match="crosses"):
        validate_splits(changed)


def test_protocol_mutation_detected(tmp_path):
    c = campaign(tmp_path)
    (c.root / "protocol.json").write_text('{"repetitions":3}')
    with pytest.raises(ValueError, match="mutated"):
        c.state()


def test_hash_is_canonical():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_unfilled_real_protocol_is_not_frozen(tmp_path):
    c = Campaign(tmp_path / "campaign")
    with pytest.raises(ValueError, match="template"):
        c.initialize({"template_only": True, "repetitions": 2, "automatic_retries": 0})
    with pytest.raises(ValueError, match="Real protocol"):
        c.initialize(
            {
                "classification": "prospective_procedurally_sealed",
                "repetitions": 2,
                "automatic_retries": 0,
            }
        )
