# Changelog

All notable changes to SeeSee will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

## [0.1.0] - Unreleased

Initial release. See ROADMAP.md for planned features.
