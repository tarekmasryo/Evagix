# Fixture: Basic Python repository

This fixture demonstrates the smallest useful Evagix workflow for a Python package.

Expected detected shape:

- Python project from `pyproject.toml`
- pytest test command
- Ruff lint command
- local package installation command

Try it:

```bash
evagix scan tests/fixtures/basic-python
evagix compile tests/fixtures/basic-python
evagix doctor tests/fixtures/basic-python
evagix diff tests/fixtures/basic-python
```
