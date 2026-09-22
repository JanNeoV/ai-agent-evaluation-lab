# Local validation

The project has an offline validation path. It uses synthetic fixtures and does not require Snowflake credentials or Cortex access.

## Commands

Run from the repository root in an environment installed with the development extra:

```bash
python -m pip check
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy evaluation platforms
python scripts/build_schemas.py --check
python -m evaluation.cli doctor
python -m evaluation.cli verify-release data/synthetic/SYNTHETIC-001 --allow-synthetic
```

For a clean synthetic lifecycle and report replay, use fresh output paths:

```bash
python -m evaluation.cli demo --output artifacts/demo-validation
python -m evaluation.cli replay-demo --evidence artifacts/demo-validation --output artifacts/demo-validation-report.md
```

The SQL renderer can also be checked without a server:

```bash
python -m evaluation.cli render-snowflake --release data/synthetic/SYNTHETIC-001 --output artifacts/sql-validation --model claude-haiku-4-5 --allow-synthetic
```

Rendering only creates local files. It does not verify live Snowflake compatibility.

## Validation boundary

Unit tests use synthetic fixtures and mock transports. They do not prove current account privileges, model availability, live SQL parity, request-level cost attribution, or cloud behavior. Any Cortex Agent, warehouse execution, or model invocation is a paid external operation and is outside the local validation path.

`requirements.lock` captures one Windows/Python 3.12 environment. The supported dependency ranges and optional extras are declared in `pyproject.toml` for cross-platform installation.
