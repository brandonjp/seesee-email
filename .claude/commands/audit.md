# SeeSee Project Audit & Documentation Cleanup

**Run a comprehensive audit and cleanup of the SeeSee project's documentation and structure.**

---

## Project Context

**SeeSee** is a lightweight, self-hosted sent email log aggregator. It receives email log entries from multiple applications via REST API or SMTP, stores them with configurable retention in SQLite, and provides a web UI to search and inspect them.

- **Website:** seesee.email
- **Tagline:** See what your apps sent.
- **License:** MIT (SPDX: MIT)
- **Language:** Python 3.12+
- **Framework:** FastAPI + aiosmtpd
- **Database:** SQLite with FTS5
- **UI:** Jinja2 + Tailwind CSS (CDN) + Alpine.js (CDN)
- **Deployment:** Single Docker container → GHCR
- **Docs Site:** Astro Starlight → GitHub Pages (seesee.email)
- **Versioning:** Semantic Versioning (MAJOR.MINOR.PATCH)

---

## Phase 1: Project Structure Verification

### Expected File Structure

Verify all expected files exist and are properly configured:

```
seesee/
├── .github/
│   └── workflows/
│       ├── build.yml           # Docker image → GHCR
│       └── docs.yml            # Docs site → GitHub Pages
├── .claude/
│   └── commands/
│       ├── dev.md              # Development workflow guide
│       ├── setup-dev-guide.md  # Dev guide generator prompt
│       └── audit.md            # This file
├── Dockerfile
├── docker-compose.yml          # Coolify-compatible
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE                     # MIT — do NOT ingest or reproduce full text
├── CONTRIBUTING.md
│
├── seesee/                     # Application code
│   ├── __init__.py             # Contains __version__
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # pydantic-settings, env var parsing
│   ├── database.py             # SQLite setup, migrations, FTS5
│   ├── models.py               # Pydantic request/response models
│   ├── auth.py                 # API key + session auth
│   ├── retention.py            # Cleanup logic + scheduler
│   ├── smtp_server.py          # aiosmtpd ingest (capture-only)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── ingest.py           # POST /api/v1/log, /log/batch
│   │   ├── emails.py           # GET /api/v1/emails, /{id}, /preview
│   │   ├── apps.py             # App management endpoints
│   │   ├── stats.py            # Dashboard stats endpoint
│   │   └── ui.py               # HTML page routes (Jinja2)
│   ├── templates/              # Jinja2 HTML templates
│   └── static/                 # CSS, JS, favicon
│
├── docs/                       # Astro Starlight site
│   ├── astro.config.mjs
│   ├── package.json
│   └── src/content/docs/       # Markdown documentation pages
│
├── examples/                   # Integration snippets
│   ├── wordpress-hook.php
│   ├── python-example.py
│   ├── node-example.js
│   └── curl-example.sh
│
└── tests/
    ├── test_ingest.py
    ├── test_search.py
    ├── test_retention.py
    ├── test_smtp.py
    └── test_auth.py
```

**Flag any missing files or directories.**

---

## Phase 2: Version Consistency

### Version Locations (ALL must match)

Check these locations for version consistency:

| Location | Format | Example |
|----------|--------|---------|
| `seesee/__init__.py` | `__version__ = "X.X.X"` | Canonical source |
| `pyproject.toml` | `version = "X.X.X"` | Package version |
| `CHANGELOG.md` | `## [X.X.X]` heading | Latest release |
| `docker-compose.yml` | Image tag reference | If version-pinned |
| `docs/` config or frontmatter | If version is displayed | Docs site |
| `README.md` | Badge or text reference | If version mentioned |

**Canonical version source:** `seesee/__init__.py`

**If versions are inconsistent:** Update all locations to match `__init__.py`.

---

## Phase 3: Documentation Audit

### Root-Level Files

| File | Required | Check |
|------|----------|-------|
| `README.md` | ✅ | Has: project description, quick start (docker run), badges, link to docs site, link to dev guide |
| `CHANGELOG.md` | ✅ | Keep a Changelog format, Unreleased section exists, entries in reverse chronological order |
| `LICENSE` | ✅ | MIT license file exists — do NOT read or reproduce contents |
| `CONTRIBUTING.md` | ✅ | Has: how to contribute, dev setup, PR process, code standards |
| `SPEC.md` | Optional | Project specification (may be in docs/ instead) |

### README.md Required Sections

- [ ] Project name + tagline + logo/badge
- [ ] "Early Development" status badge
- [ ] One-paragraph description
- [ ] Quick start with `docker run` command
- [ ] Docker Compose example
- [ ] Screenshot (when UI exists)
- [ ] Link to full docs at seesee.email
- [ ] Link to API docs at `/docs` (Swagger)
- [ ] "How it works" brief explanation
- [ ] Integration examples (or link to examples/)
- [ ] Contributing link
- [ ] License: "MIT" with link to LICENSE file — no full text

### CHANGELOG.md Checks

- [ ] Follows [Keep a Changelog](https://keepachangelog.com/) format
- [ ] Has `[Unreleased]` section
- [ ] All versions have dates
- [ ] Categories used: Added, Changed, Fixed, Removed, Security
- [ ] Entries are meaningful (not just "updated stuff")

### Documentation Site (docs/)

Verify these pages exist or are planned:

| Page | Path | Status |
|------|------|--------|
| Landing/marketing | `index.mdx` | Required |
| Getting Started | `getting-started.md` | Required |
| Configuration | `configuration.md` | Required |
| REST API Reference | `api-reference.md` | Required |
| SMTP Ingest | `smtp-ingest.md` | Required |
| Docker Deployment | `deployment/docker.md` | Required |
| Coolify Deployment | `deployment/coolify.md` | Required |
| PHP Integration | `integrations/php.md` | Required |
| Python Integration | `integrations/python.md` | Required |
| JavaScript Integration | `integrations/javascript.md` | Required |
| WordPress Integration | `integrations/wordpress.md` | Required |
| Privacy & Compliance | `privacy.md` | Required |
| Contributing | `contributing.md` | Required |

---

## Phase 4: Configuration Files Audit

### Files to Check

| File | Verify |
|------|--------|
| `.gitignore` | Covers: `__pycache__`, `.env`, `*.db`, `*.sqlite`, `.venv`, `node_modules` (docs/), `.DS_Store`, `dist/`, `*.egg-info` |
| `.env.example` | Documents all `SEESEE_*` env vars with descriptions and defaults |
| `pyproject.toml` | Complete: name, version, description, authors, license, dependencies, dev dependencies, scripts |
| `Dockerfile` | Multi-stage build, non-root user, health check, minimal image size |
| `docker-compose.yml` | Health check, named volume, env var references, restart policy |
| `.github/workflows/build.yml` | Builds on push to main + tags, pushes to GHCR, multi-arch if feasible |
| `.github/workflows/docs.yml` | Builds Starlight, deploys to GitHub Pages on push to main |

### Environment Variables

Verify `.env.example` documents all of these:

```bash
# Server
SEESEE_PORT=8080
SEESEE_BASE_URL=http://localhost:8080

# Auth
SEESEE_ADMIN_USERNAME=admin
SEESEE_ADMIN_PASSWORD=           # Required, no default

# Database
SEESEE_DB_PATH=/data/seesee.db

# SMTP Ingest
SEESEE_SMTP_ENABLED=true
SEESEE_SMTP_PORT=2525
# Retention
SEESEE_RETENTION_MAX_COUNT=1000
SEESEE_RETENTION_MAX_AGE_DAYS=90
SEESEE_RETENTION_MAX_STORAGE_MB=500
SEESEE_RETENTION_CLEANUP_INTERVAL_MINUTES=60

# UI
SEESEE_THEME=system

# Logging
SEESEE_LOG_LEVEL=info
```

---

## Phase 5: SeeSee-Specific Checks

### API Consistency

- [ ] All REST endpoints follow `/api/v1/` prefix
- [ ] API key prefix is `ss_` for all generated keys
- [ ] OpenAPI/Swagger auto-docs are accessible at `/docs`
- [ ] Health endpoint at `/api/v1/health` returns 200

### Database

- [ ] SQLite FTS5 index covers: subject, body_text, body_preview, to_addresses, from_address, error_message
- [ ] Migrations are handled gracefully (schema versioning or auto-migration on startup)
- [ ] WAL mode is enabled for concurrent read/write

### Auth

- [ ] REST API: Bearer token auth with `ss_` prefixed keys
- [ ] SMTP: Per-app username/password credentials
- [ ] Web UI: Session-based auth with login page
- [ ] API keys are stored hashed, never in plaintext
- [ ] Admin password is never logged or exposed

### Retention

- [ ] Cleanup job runs on configured interval
- [ ] Per-app settings override global defaults
- [ ] Most restrictive rule wins when multiple apply
- [ ] Deletion is oldest-first within each app
- [ ] Cleanup actions are logged

### Body Storage

- [ ] Three modes work: `full`, `text_only`, `preview`
- [ ] `body_preview` is always populated regardless of mode
- [ ] Mode is configurable per app
- [ ] API accepts all body fields regardless of mode (storage policy applied on write)

---

## Phase 6: Cleanup

### Remove Clutter

- [ ] No `__pycache__` directories committed
- [ ] No `.env` files committed (only `.env.example`)
- [ ] No `.db` / `.sqlite` files committed
- [ ] No IDE-specific files (`.idea/`, `.vscode/` — unless shared settings)
- [ ] No `node_modules` committed (docs/ has its own .gitignore)

### Verify No Sensitive Data

- [ ] No API keys or passwords in any committed file
- [ ] No real email addresses in test fixtures (use @example.com)
- [ ] No production URLs in committed config
- [ ] Docker Compose uses env var references, not hardcoded values

---

## Output Requirements

### Summary Report

```
PROJECT: SeeSee — Sent Email Log Viewer
VERSION: [current version]
STATUS: [assessment]

FILES AUDITED: [count]
FILES MODIFIED: [count]
FILES CREATED: [count]
ISSUES FOUND: [critical/warnings/suggestions counts]

CRITICAL:
- [any blocking issues]

WARNINGS:
- [should fix]

SUGGESTIONS:
- [nice to have]

CHANGES MADE:
- [file]: [what changed]

NEXT STEPS:
1. [prioritized actions]
```

### Commit

- Stage all changes
- Commit: `chore: project documentation audit and cleanup`
- Must be on a feature branch (e.g., `chore/project-audit`), not main

---

## Audit Checklist

- [ ] Project structure matches expected layout
- [ ] Version numbers consistent across all locations
- [ ] README is comprehensive with quick start
- [ ] CHANGELOG follows Keep a Changelog format
- [ ] Documentation site pages exist or are tracked
- [ ] .env.example documents all SEESEE_* variables
- [ ] .gitignore is comprehensive
- [ ] Docker files have health checks
- [ ] GitHub Actions workflows exist and are correct
- [ ] No sensitive data in committed files
- [ ] API follows /api/v1/ convention
- [ ] Auth is properly configured (API keys, SMTP creds, UI sessions)
- [ ] Dev guide exists at .claude/commands/dev.md
- [ ] Changes committed in feature branch
