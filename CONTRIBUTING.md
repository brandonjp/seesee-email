# Contributing to SeeSee

SeeSee is early-stage software — contributions are welcome!

## Development Setup

```bash
git clone https://github.com/brandonjp/seesee-email.git
cd seesee-email
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                       # Run all tests
pytest -x                    # Stop on first failure
pytest tests/test_ingest.py  # Run specific test file
pytest -k "test_search"      # Run tests matching pattern
```

## Code Style

- **Linting:** Ruff (`ruff check .`)
- **Formatting:** Ruff formatter (`ruff format .`)
- **Line length:** 100
- **Type hints:** Required on all function signatures
- **Docstrings:** Google format for public functions/classes

```bash
ruff check .          # Lint
ruff format .         # Format
ruff format --check . # Check format without changing
```

## Git Workflow

1. Create a feature branch from `main`:
   - `feature/`, `fix/`, `refactor/`, `docs/`, `chore/`, or `phase-X.X/`
2. Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
3. Before submitting a PR:
   - `pytest` passes
   - `ruff check .` passes
   - `ruff format --check .` passes
   - Update `CHANGELOG.md` if behavior changed

## Where to Find Work

- **ROADMAP.md** — Development phases and current focus
- **GitHub Issues** — Bug reports and feature requests
- **TODO comments** in source code — Implementation stubs

## Project Structure

See `.claude/commands/dev.md` for the full project structure and development guide.
