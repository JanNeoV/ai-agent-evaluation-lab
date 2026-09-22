# Contributing

Contributions to the evaluation code, synthetic fixtures, and documentation are welcome.

## Before opening a change

- Keep frozen releases, schedules, raw responses, assessments, and canonical results immutable. Corrections to published prose must retain the evidence boundary and cite `docs/publication/article_fact_sheet.md` for TASK-0019 claims.
- Do not add private research data, hidden questions or truth, raw cloud traces, account identifiers, credentials, or user-specific local paths.
- Keep test fixtures clearly labeled synthetic. Never present fixture outcomes as observed model performance.
- Do not add a Cortex invocation to tests or CI. Any live campaign needs its own authorization, budget, and prospective protocol.

## Local checks

Install the development extra and run the repository checks from the root:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy evaluation platforms
python scripts/build_schemas.py --check
```

Document any check that could not be run and distinguish mock or offline checks from live Snowflake validation.
