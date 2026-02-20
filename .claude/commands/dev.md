# /dev - SeeSee Development Workflow

> See what your apps sent. Lightweight self-hosted email log viewer.

---

## Quick Start

**Prerequisites:** Python 3.12+, pip

**Install dependencies:**
```bash
git clone https://github.com/brandonjp/seesee-email.git
cd seesee-email
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**Run development server:**
```bash
# Starts both HTTP (8080) and SMTP (2525) servers
python -m seesee
# Or with environment overrides:
SEESEE_ADMIN_PASSWORD=dev SEESEE_LOG_LEVEL=debug python -m seesee
```

**Run tests:**
```bash
pytest
pytest -x                    # Stop on first failure
pytest tests/test_ingest.py  # Run specific test file
pytest -k "test_search"      # Run tests matching pattern
```

**Lint/format:**
```bash
ruff check .                 # Linting
ruff format .                # Formatting
```

**Build Docker image locally:**
```bash
docker build -t seesee:dev .
docker run -p 8080:8080 -p 2525:2525 -e SEESEE_ADMIN_PASSWORD=dev seesee:dev
```

**Build docs site locally:**
```bash
cd docs
npm install
npm run dev                  # Dev server at localhost:4321
```

---

## Project Overview

**Type:** Self-hosted web application (API + SMTP + Web UI)
**Stack:** Python 3.12+ / FastAPI / SQLite FTS5 / Jinja2 + Tailwind + Alpine.js
**Version:** 0.12.0-dev (Semantic Versioning)
**Package Manager:** pip with pyproject.toml
**Deployment:** Docker single container → GHCR, Coolify-compatible

### Project Structure
```
seesee-email/
├── seesee/                  # Python application package
│   ├── __init__.py          # __version__ (canonical version source)
│   ├── __main__.py          # Entry point for python -m seesee
│   ├── main.py              # FastAPI app, startup/shutdown, mount SMTP
│   ├── config.py            # SeeSeeSettings (pydantic-settings)
│   ├── database.py          # SQLite connection, schema, FTS5, migrations
│   ├── models.py            # Pydantic models for API request/response
│   ├── auth.py              # API key hashing/verification, session management
│   ├── retention.py         # Cleanup scheduler, per-app + global rules
│   ├── timezone.py          # Timezone helpers (UTC storage, display formatting)
│   ├── smtp_server.py       # aiosmtpd handler, MIME parsing
│   ├── routes/
│   │   ├── ingest.py        # POST /api/v1/log, /api/v1/log/batch
│   │   ├── emails.py        # GET /api/v1/emails, /{id}, /{id}/preview
│   │   ├── apps.py          # CRUD for app registration + key management
│   │   ├── stats.py         # GET /api/v1/stats (dashboard data)
│   │   ├── admin.py         # Admin endpoints (cleanup, persistence diagnostics)
│   │   └── ui.py            # Jinja2 HTML page routes (/, /emails, /apps, etc.)
│   ├── templates/           # Jinja2 HTML (Tailwind + Alpine.js, no build step)
│   └── static/              # CSS, JS, favicon
├── docs/                    # Astro Starlight docs site (independent)
├── examples/                # Integration code snippets (PHP, Python, JS, cURL)
├── tests/                   # pytest test suite
├── Dockerfile               # Multi-stage, non-root, health check
├── docker-compose.yml       # Coolify-compatible with health check
├── pyproject.toml           # Package config, dependencies, scripts
└── .github/workflows/       # Docker build → GHCR, docs → GitHub Pages
```

### Key Configuration Files

| File | Purpose |
|------|---------|
| `seesee/__init__.py` | Canonical version source (`__version__`) |
| `seesee/config.py` | All settings with env var mapping (`SEESEE_*` prefix) |
| `pyproject.toml` | Package metadata, dependencies, dev tools config |
| `.env.example` | Documented env vars with defaults |
| `Dockerfile` | Production container build |
| `docker-compose.yml` | One-command deployment (Coolify-compatible) |

---

## Development Phases & Roadmap

See `ROADMAP.md` for detailed phase breakdown.

**Phase Status Legend:**
- ✅ Complete | 🚧 In Progress | 📋 Planned | 🔮 Future

### Current Focus: Phase 3.0 — Future features

All phases 0 through 2.1 are complete. See `ROADMAP.md` for the full breakdown.

#### Completed Phases
- ✅ Phase 0 — Project Setup
- ✅ Phase 1.0 — Core API + Storage
- ✅ Phase 1.1 — Web UI
- ✅ Phase 1.2 — SMTP Ingest
- ✅ Phase 1.3 — Retention + Deployment
- ✅ Phase 2.0 — Documentation Site
- ✅ Phase 2.1 — Polish

#### Phase 3.0 — Future 🔮
- ✅ Graduated body degradation (full → text → preview over time)
- ✅ Provider webhook receivers (Resend, SendGrid status callbacks)
- ✅ Timezone handling (UTC storage, SEESEE_DISPLAY_TIMEZONE, format-consistent queries)
- Search-and-delete (GDPR right to erasure)
- Data export per recipient
- CSV/JSON search export
- Prometheus metrics
- Multi-user auth with roles
- WordPress plugin
- Postgres support

---

## What to Work On

**Priority Order:**
1. Current phase items (see Roadmap)
2. Bugs / broken functionality
3. Test coverage for critical paths
4. Documentation gaps

---

## Development Standards

### Code Quality

- **Style:** PEP 8, enforced by Ruff
- **Formatting:** Ruff formatter (line length 100)
- **Type hints:** Required on all function signatures
- **Imports:** Sorted by Ruff (isort-compatible)
- **Docstrings:** Google format for public functions/classes
- **Comments:** Explain "why", not "what"
- **Naming:** snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants

### Database

- **SQLite with WAL mode** for concurrent reads
- **FTS5** for full-text search (subject, body_text, body_preview, to_addresses, from_address, error_message)
- **Schema migrations** handled on startup (version-tracked in a metadata table)
- **aiosqlite** for async access — never block the event loop with synchronous SQLite calls
- **Parameterized queries only** — never string-format SQL values

### API Design

- All endpoints under `/api/v1/` prefix
- JSON request/response bodies
- Pydantic models for validation
- Consistent error response format: `{"error": "message", "detail": "..."}`
- API keys prefixed with `ss_`
- OpenAPI docs auto-generated at `/docs`

### UI Design

- **Server-rendered** with Jinja2 — this is NOT an SPA
- **Tailwind CSS from CDN** — no build step, no PostCSS
- **Alpine.js from CDN** — for interactivity (search, filters, modals, toggles)
- **No npm/node required** to run SeeSee — only for the docs site
- **Dark mode:** Tailwind `dark:` classes, system preference with manual toggle
- **Keyboard shortcuts:** `/` = search, `j`/`k` = navigate, `Enter` = open, `Esc` = close
- **Brand color:** Phosphor mint `#32F5C0` — used for primary actions, active states, brand identity
- **Light mode warm background:** `#F6F1E6` (paper tone, not clinical white)

### Auth Implementation

| Layer | Method | Storage |
|-------|--------|---------|
| REST API | Bearer token (`Authorization: Bearer ss_xxx`) | API key hash in `apps` table |
| SMTP Ingest | SMTP AUTH (username + password) | Credentials hash in `apps` table |
| Web UI | Session cookie (login form) | Server-side session, admin user from env var |

- API keys and SMTP passwords: hash with bcrypt or argon2, store only the hash
- Session: secure cookie, configurable expiry (default 7 days)
- Admin credentials: set via `SEESEE_ADMIN_USERNAME` + `SEESEE_ADMIN_PASSWORD` env vars

### Version Management

- **Strategy:** Semantic Versioning (MAJOR.MINOR.PATCH)
- **Canonical source:** `seesee/__init__.py` → `__version__`
- **Also update:** `pyproject.toml`, `CHANGELOG.md`
- **Bump when:** Any code change that affects functionality
- **Patch:** Bug fixes, minor improvements
- **Minor:** New features, new endpoints, new UI pages
- **Major:** Breaking API changes, breaking config changes

### Testing Strategy

- **Framework:** pytest + pytest-asyncio
- **API tests:** httpx AsyncClient with FastAPI TestClient
- **Database tests:** Use temporary SQLite in-memory or tmp_path
- **SMTP tests:** Mock aiosmtpd or use test fixtures

**Priority areas to test:**
- Ingest endpoints (POST /api/v1/log) — validation, auth, storage modes
- Search/filter queries — FTS5 behavior, pagination, combined filters
- Retention logic — count limits, age limits, per-app overrides
- Auth — API key verification, session management, invalid credentials
- SMTP parsing — MIME message extraction

**Don't bother testing:**
- Jinja2 template rendering details
- Tailwind CSS classes
- SQLite engine internals
- FastAPI framework behavior

### Git Workflow

- **Feature branches required** — never commit directly to main
- **Branch naming:** `feature/`, `fix/`, `refactor/`, `docs/`, `chore/`, or `phase-X.X/`
- **Commit format:** Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`)
- **Before merging to main:**
  - `pytest` passes
  - `ruff check .` passes
  - `ruff format --check .` passes
  - Version bumped if code changed
  - CHANGELOG.md updated
  - Documentation updated if behavior changed
- **After merge:** Delete feature branch (local + remote)

---

## Key Files Quick Reference

| Path | Purpose | When to Modify |
|------|---------|----------------|
| `seesee/__init__.py` | Version number | Every release |
| `seesee/config.py` | All settings/env vars | Adding new config options |
| `seesee/database.py` | Schema + queries | Changing data model |
| `seesee/models.py` | API contracts | Changing API request/response shapes |
| `seesee/routes/ingest.py` | Core logging endpoint | Changing how emails are logged |
| `seesee/routes/ui.py` | All HTML page routes | Adding/changing UI pages |
| `seesee/templates/` | HTML templates | Any UI change |
| `seesee/retention.py` | Cleanup logic | Changing retention behavior |
| `seesee/timezone.py` | UTC helpers + display formatting | Adding time-related features |
| `seesee/smtp_server.py` | SMTP capture (ingest) | Changing SMTP behavior |
| `.env.example` | Config documentation | Adding new env vars |
| `docker-compose.yml` | Deployment template | Changing ports, volumes, health checks |
| `ROADMAP.md` | Development phases | Completing or planning phases |
| `CHANGELOG.md` | Release history | Every meaningful change |

---

## Common Tasks

### Adding a New API Endpoint

1. Add Pydantic models to `models.py`
2. Add route function to appropriate `routes/` file
3. Register route in `main.py` if new router
4. Write tests in `tests/`
5. Update OpenAPI description/tags
6. Add to CHANGELOG

### Adding a New UI Page

1. Add route in `routes/ui.py`
2. Create template in `templates/`
3. Add navigation link in `templates/base.html`
4. Style with Tailwind classes (CDN, no build)
5. Add Alpine.js interactivity if needed
6. Test both dark and light mode

### Adding a New Config Option

1. Add field to `SeeSeeSettings` in `config.py` with default + description
2. Add to `.env.example` with comment
3. Use in application code via `settings.new_option`
4. Document in docs site configuration page
5. Add to CHANGELOG

### Adding a Database Schema Change

1. Update schema in `database.py`
2. Add migration logic (check schema version, alter table)
3. Update Pydantic models if API-facing
4. Update FTS5 index if search fields changed
5. Write test with fresh + migrated database
6. Add to CHANGELOG

---

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Check what's using port 8080 or 2525
lsof -i :8080
lsof -i :2525
```

**SQLite locked:**
- Ensure WAL mode is enabled in `database.py`
- Check for long-running transactions
- Only one write connection at a time

**SMTP connection refused from another container:**
- Expose port: `-p 2525:2525`
- Use host IP or `host.docker.internal`, not `localhost`
- Verify SMTP credentials match registered app

**FTS5 search not returning expected results:**
- FTS5 tokenizes on word boundaries — partial words won't match
- Use `*` suffix for prefix matching: `pass*` matches "password"
- Check that the column is included in the FTS5 index

---

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [aiosmtpd Documentation](https://aiosmtpd.readthedocs.io/)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [Alpine.js](https://alpinejs.dev/)
- [Astro Starlight](https://starlight.astro.build/)
- [Keep a Changelog](https://keepachangelog.com/)
