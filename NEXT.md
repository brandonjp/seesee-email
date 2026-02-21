# Next Steps — SeeSee

**Version:** 0.14.0-dev
**Updated:** 2026-02-21

## Just Completed

- **Data export per recipient (GDPR right of access)** — Phase 3.0 feature:
  - `GET /api/v1/export?recipient=user@example.com` — export all emails where recipient appears in to, cc, or bcc (admin auth required)
  - JSON response with metadata envelope (recipient, total, exported_at) and full email records
  - CSV format supported via `format=csv` query parameter or `Accept: text/csv` header
  - Case-insensitive matching across to_addresses, cc_addresses, bcc_addresses
  - Includes email metadata and body content (whatever storage mode allows)
  - Input validation (requires valid email address)
  - 15 new tests, 272 total tests passing

## Highest Priority Next Task

Pick from remaining Phase 3.0 candidates based on user feedback.

## Other Candidates (from ROADMAP Phase 3.0)

- CSV/JSON search export
- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Current State

- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, search-and-delete, and data export per recipient from Phase 3.0
- 272 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Timezone architecture: UTC storage, configurable display, format-consistent queries
- Search-and-delete: GDPR erasure via bulk delete with filters
- Data export per recipient: GDPR right of access via JSON/CSV export
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
