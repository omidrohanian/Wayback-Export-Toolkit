# Contributing

Thanks for contributing to Wayback Export Toolkit.

## Setup

```bash
python -m pip install -e .[dev]
```

## Run tests

```bash
pytest -q
```

## Local quality checks before push

```bash
python -m compileall -q src tests
pytest -q
```

## Commit style

- Keep commits focused (one logical change per commit).
- Add or update tests when behavior changes.
- Prefer clear, small PRs over large mixed changes.

## Project conventions

- Keep Python source in `src/wayback_export/`.
- Keep tests in `tests/` and mirror module names where practical.
- Preserve existing CLI flags and output shape unless intentionally versioning behavior.
