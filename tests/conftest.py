from pathlib import Path

import pytest

from evaluation.artifacts import load_json
from evaluation.contracts import GroundTruth, Question

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_root():
    return ROOT / "data/synthetic/SYNTHETIC-001"


@pytest.fixture
def questions(fixture_root):
    return [Question.from_dict(row) for row in load_json(fixture_root / "questions.json")]


@pytest.fixture
def truths(fixture_root):
    return {
        row["question_id"]: GroundTruth.from_dict(row)
        for row in load_json(fixture_root / "ground_truth.json")
    }


@pytest.fixture(scope="session")
def completed_demo(tmp_path_factory):
    from evaluation.demo import run_demo

    output = tmp_path_factory.mktemp("replay") / "evidence"
    run_demo(ROOT / "data/synthetic/SYNTHETIC-001", output)
    return output
