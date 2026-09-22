# Quick start

This guide runs the local software fixture. It makes no Snowflake connection and invokes no AI model.

## Requirements

- Python 3.11 or later; Python 3.12 is the validated release environment.
- Git, if cloning the repository.

`requirements.lock` records one Windows/Python 3.12 environment snapshot. For other operating systems or Python versions, install from the project metadata instead.

## Install and run the demo

From the repository root:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e .
python -m evaluation.cli doctor
python -m evaluation.cli verify-release data/synthetic/SYNTHETIC-001 --allow-synthetic
python -m evaluation.cli demo --output artifacts/demo-001
python -m evaluation.cli replay-demo --evidence artifacts/demo-001 --output artifacts/demo-report.md
```

Generated files go under `artifacts/`. Maintainer-only frozen material under `local/` is not included in the public repository. Use a fresh output directory for each demo because evidence output is write-once. The demo produces clearly labeled synthetic responses, costs, and latencies; it is a plumbing example, not a model-quality result.

## Development checks

Install the development tools and run the offline checks:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q --basetemp=pytest-cache-files-public
python -m ruff check .
python -m ruff format --check .
python -m mypy evaluation platforms
python scripts/build_schemas.py --check
```

The pytest base directory above is ignored scratch space and remains separate from frozen evidence under `local/`. Choose a fresh directory name if you have already used it. The project has an optional `snowflake` extra for the Snowflake connector and a `visuals` extra for regenerating the publication SVGs; neither is needed for the demo.

Continue with the [methodology overview](methodology.md).
