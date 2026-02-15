---
title: Contributing
description: Development setup, code style, testing, and git workflow for SeeSee contributors.
---

SeeSee is open source and welcomes contributions. This guide covers how to set up a development environment and the project's coding standards.

## Development setup

### Prerequisites

- Python 3.12+
- pip
- Git

### Clone and install

```bash
git clone https://github.com/brandonjp/seesee-email.git
cd seesee-email
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run the development server

```bash
# Starts both HTTP (8080) and SMTP (2525) servers
python -m seesee

# With debug logging
SEESEE_ADMIN_PASSWORD=dev SEESEE_LOG_LEVEL=debug python -m seesee
```

### Run tests

```bash
pytest                       # Full test suite
pytest -x                    # Stop on first failure
pytest tests/test_ingest.py  # Specific test file
pytest -k "test_search"      # Tests matching pattern
```

### Lint and format

```bash
ruff check .                 # Check for lint errors
ruff format .                # Auto-format code
ruff format --check .        # Check formatting without changing
```

### Build Docker image locally

```bash
docker build -t seesee:dev .
docker run -p 8080:8080 -p 2525:2525 -e SEESEE_ADMIN_PASSWORD=dev seesee:dev
```

### Build docs site locally

The docs site is independent from the Python app — it uses Node.js, not the Python venv.

```bash
cd docs
npm install
npm run dev    # Dev server at localhost:4321
npm run build  # Production build to docs/dist
```

## Project structure

```
seesee-email/
├── seesee/                  # Python application package
│   ├── __init__.py          # Version number (__version__)
│   ├── __main__.py          # Entry point (python -m seesee)
│   ├── main.py              # FastAPI app, lifespan, route registration
│   ├── config.py            # Settings with SEESEE_* env var mapping
│   ├── database.py          # SQLite + FTS5 schema, queries, migrations
│   ├── models.py            # Pydantic request/response models
│   ├── auth.py              # API key hashing, session management
│   ├── retention.py         # Cleanup scheduler, retention enforcement
│   ├── smtp_server.py       # aiosmtpd handler, MIME parsing
│   ├── routes/
│   │   ├── ingest.py        # POST /api/v1/log, /api/v1/log/batch
│   │   ├── emails.py        # GET /api/v1/emails, /{id}, /{id}/preview
│   │   ├── apps.py          # App CRUD + key rotation
│   │   ├── stats.py         # GET /api/v1/stats
│   │   └── ui.py            # Web UI page routes
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS, JS, favicon
├── docs/                    # Astro Starlight docs site
├── examples/                # Integration snippets (PHP, Python, JS, cURL)
├── tests/                   # pytest test suite
├── Dockerfile               # Multi-stage production build
├── docker-compose.yml       # Coolify-compatible deployment
├── pyproject.toml           # Package config and dependencies
└── .github/workflows/       # CI/CD (Docker → GHCR, docs → GitHub Pages)
```

## Code style

- **Formatter:** Ruff (line length 100)
- **Linter:** Ruff (PEP 8 enforcement)
- **Type hints:** Required on all function signatures
- **Imports:** Sorted by Ruff (isort-compatible)
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants
- **Docstrings:** Google format for public functions and classes
- **Comments:** Explain "why", not "what"

## Testing

SeeSee uses pytest with pytest-asyncio for async test support.

**Priority areas to test:**
- Ingest endpoints — validation, auth, storage modes
- Search and filter queries — FTS5 behavior, pagination
- Retention logic — count limits, age limits, per-app overrides
- Auth — API key verification, session management
- SMTP parsing — MIME extraction

**Test patterns:**
- API tests use httpx `AsyncClient` with FastAPI's `TestClient`
- Database tests use temporary SQLite (in-memory or `tmp_path`)
- SMTP tests use mock fixtures

## Git workflow

- **Feature branches required** — never commit directly to `main`
- **Branch naming:** `feature/`, `fix/`, `refactor/`, `docs/`, `chore/`, or `phase-X.X/`
- **Commit format:** Conventional commits:
  - `feat:` — new feature
  - `fix:` — bug fix
  - `docs:` — documentation
  - `chore:` — maintenance
  - `refactor:` — code restructuring
  - `test:` — test additions

### Before merging to main

- [ ] `pytest` passes
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] Version bumped if code changed
- [ ] CHANGELOG.md updated
- [ ] Documentation updated if behavior changed

## Version management

SeeSee uses Semantic Versioning (MAJOR.MINOR.PATCH):

- **Patch:** Bug fixes, minor improvements
- **Minor:** New features, new endpoints, new UI pages
- **Major:** Breaking API changes, breaking config changes

The canonical version source is `seesee/__init__.py`. Also update `pyproject.toml` and `CHANGELOG.md` when bumping.

## Roadmap

See [`ROADMAP.md`](https://github.com/brandonjp/seesee-email/blob/main/ROADMAP.md) in the repository for the current development phases and planned features.
