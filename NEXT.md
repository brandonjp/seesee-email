# Next Steps — SeeSee

**Version:** 0.13.0-dev
**Updated:** 2026-02-20

## Just Completed

- **Search-and-delete / GDPR right to erasure** — Bulk delete emails matching search criteria:
  - `DELETE /api/v1/emails` endpoint with same filter parameters as list (q, app_id, status, provider, date_from, date_to)
  - Safety: requires at least one filter parameter (422 if no filters provided)
  - FTS5 index automatically cleaned up via existing delete triggers
  - "Delete matching" button on emails search page with confirmation modal and count
  - Toast notification on completion
  - 11 new tests, 257 total passing

## Highest Priority Next Task

Pick from remaining Phase 3.0 candidates based on user feedback.

## Other Candidates (from ROADMAP Phase 3.0)

- Data export per recipient (GDPR right of access)
- CSV/JSON search export
- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Current State

- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, and search-and-delete from Phase 3.0
- 257 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Timezone architecture: UTC storage, configurable display, format-consistent queries
- Search-and-delete: GDPR erasure via bulk delete with filters
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
