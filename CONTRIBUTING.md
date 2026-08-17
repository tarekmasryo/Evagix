# Contributing to Evagix

Thank you for helping improve Evagix. Contributions should preserve its local-first, deterministic, and conservative behavior.

## Development setup

```bash
python -m pip install -e ".[dev]"
```

Optional local hooks:

```bash
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Required checks

Run these before opening a pull request:

```bash
python -m compileall -q evagix tests scripts
python -m ruff check .
python -m ruff format --check .
python -m mypy evagix
python -m pytest --cov=evagix --cov-branch --cov-report=term-missing --cov-fail-under=80
python -m evagix check .
python -m evagix doctor . --strict --fail-under 80
```

## Design and safety principles

- Prefer static repository evidence over guesses.
- Do not add network or model API calls to the default path.
- Do not execute project commands during scans.
- Preserve public CLI behavior, exit codes, schemas, and generated-file ownership rules.
- Keep changes focused and add regression tests for behavior changes.
- Treat scoring, command safety, path traversal, redaction, and generated-context integrity as high-risk areas.

Documentation, tests, focused evidence detection, and small validation improvements are welcome. Broad architecture changes, new dependencies, scoring-policy changes, and compatibility breaks require explicit design discussion before implementation.
