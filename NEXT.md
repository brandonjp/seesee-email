# Next Steps — SeeSee

**Version:** 0.12.0-dev
**Updated:** 2026-02-20

## Just Completed

- **Timezone handling architecture** — Consistent UTC storage with configurable admin display:
  - `SEESEE_DISPLAY_TIMEZONE` env var (IANA timezone string, default: `UTC`) controls admin view date formatting
  - `seesee/timezone.py` helper module with `utc_now_iso()`, `utc_iso()`, `utc_cutoff_iso()`, `format_for_display()`, etc.
  - Fixed critical timestamp comparison bug: replaced all SQLite `datetime('now', ...)` with Python-computed UTC parameters (format mismatch caused incorrect time-window queries)
  - Standardized all timestamp storage to `YYYY-MM-DDTHH:MM:SS` (no microseconds, no offset)
  - Client-side JS shows relative times with local + UTC tooltips
  - `display_dt` Jinja2 filter for server-rendered fallbacks
  - 37 new tests, 246 total passing

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

- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, and timezone handling from Phase 3.0
- 246 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Timezone architecture: UTC storage, configurable display, format-consistent queries
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
