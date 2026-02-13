# Changelog

All notable changes to SeeSee will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Core API endpoints (Phase 1.0 — Core API + Storage):
  - `POST /api/v1/apps` — register app (returns API key + SMTP credentials, shown once)
  - `GET /api/v1/apps` — list registered apps (admin auth required)
  - `PATCH /api/v1/apps/{id}` — update app settings (name, body_storage_mode, retention)
  - `POST /api/v1/apps/{id}/rotate-key` — regenerate API key (old key immediately invalidated)
  - `POST /api/v1/log` — log a single email (API key auth, body storage mode enforcement)
  - `GET /api/v1/emails` — list/search emails with FTS5 full-text search, filters (app, status, provider, date range), sorting, and pagination
  - `GET /api/v1/emails/{id}` — full email detail with all fields
  - `GET /api/v1/emails/{id}/preview` — sandboxed HTML preview with Content-Security-Policy headers
  - `GET /api/v1/stats` — dashboard statistics (totals, time windows, breakdowns by status and app)
- API key authentication dependency with O(1) prefix-based lookup
- Admin HTTP Basic Auth for management endpoints
- Body storage mode enforcement (full / text_only / preview) per app
- Body preview generation (first 500 chars, auto-strips HTML when no text provided)
- FTS5 sync triggers for automatic full-text search indexing on email insert/update/delete
- Slug generation utility for app names (unicode-safe, collision-resistant)
- Enhanced health check endpoint with database status probe
- Consistent error response format (`{"error": "...", "detail": "..."}`)
- Pydantic models for app update (`AppUpdateRequest`) and key rotation (`KeyRotateResponse`)
- Comprehensive test suite: 69 tests covering auth, apps, app update, key rotation, ingest, email list/search, email detail, email preview, stats, health, FTS, and storage modes

### Changed
- Registered all Phase 1.0 routers (ingest, apps, emails, stats) in main app
- Static files mount now checks for directory existence before mounting
- Removed deprecated license classifier from pyproject.toml
- Version bump: 0.2.0-dev → 0.3.0-dev

## [0.1.0] - 2026-02-12

### Added
- Project structure and scaffolding
- Development workflow guides (`.claude/commands/dev.md`)
- Project specification (`seesee-spec.md`)
- Dockerfile with multi-stage build, non-root user, health check
- Docker Compose template (Coolify-compatible)
- GitHub Actions workflows (build + docs)
- pyproject.toml with full package config
- Integration examples (PHP/WordPress, Python, Node.js, cURL)
- Test scaffolding with pytest + pytest-asyncio
- SeeSee Python package scaffolding:
  - FastAPI app with health check endpoint
  - pydantic-settings config with SEESEE_* env vars
  - SQLite database schema with FTS5 full-text search
  - Pydantic models for all API request/response types
  - Auth utilities (API key generation, bcrypt hashing)
  - Route stubs for ingest, emails, apps, stats, UI
  - Jinja2 template stubs with Tailwind + Alpine.js base layout
