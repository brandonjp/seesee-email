# Next Steps — SeeSee

**Version:** 0.12.0-dev
**Updated:** 2026-02-20

## Just Completed

- **Graduated body degradation** (Phase 3.0) — Automatic email body storage degradation over time to save disk space:
  - `full` → `text_only`: strip HTML body after configurable days (`SEESEE_RETENTION_DEGRADE_TO_TEXT_DAYS`)
  - `text_only` → `preview`: strip text body after configurable days (`SEESEE_RETENTION_DEGRADE_TO_PREVIEW_DAYS`)
  - Per-app overrides supported (same pattern as retention overrides)
  - Runs as part of the existing retention scheduler cycle
  - Opt-in: disabled by default (0 = never degrade)
  - Preserves/generates body_text and body_preview during degradation
  - Updates body_size_bytes and FTS5 index automatically
  - `body_degraded_at` audit timestamp for tracking when degradation occurred
  - Database schema migrations v1 → v3
  - 26 new tests, 209 total passing

## Highest Priority Next Task

Pick from remaining Phase 3.0 candidates based on user feedback.

## Other Candidates (from ROADMAP Phase 3.0)

- Search-and-delete (GDPR right to erasure)
- Data export per recipient (GDPR right of access)
- CSV/JSON search export
- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Current State

- All phases 0 through 2.1 complete, plus provider webhook receivers and graduated body degradation from Phase 3.0
- 209 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
