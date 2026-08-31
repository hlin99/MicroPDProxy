# Contributing to xPyD-proxy

## Development Setup

```bash
git clone https://github.com/xPyD-hub/xPyD-proxy
cd xPyD-proxy
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/unit/ -q
```

## Code Style

- Python 3.10+
- Ruff: `ruff check .`
- Pre-commit: `pre-commit run --all-files`
- All PRs must pass CI (pre-commit + lint + tests + security scans + integration
  trigger)

## Security Scanning

CI runs CodeQL, `pip-audit` (dependency vulnerabilities) and Bandit (static
analysis) on every pull request, plus a weekly scheduled run. Reproduce the
Bandit gate locally with:

```bash
pip install bandit
bandit --configfile pyproject.toml --recursive xpyd
```

Bandit skips are configured under `[tool.bandit]` in `pyproject.toml` and each
one carries a justification comment. Add a new skip only with a comment
explaining why the finding does not apply.


## Bot Development

See [bot/](bot/) for automated development policies.
