# Next Steps — SeeSee

**Version:** 0.9.0-dev
**Updated:** 2026-02-20

## Just Completed

- **App deletion** — `DELETE /api/v1/apps/{app_id}` API endpoint + admin UI with trash icon on apps list and "Delete App" button on app detail page, both with confirmation modals. Flash alerts confirm deletion. 4 new tests added.

## Highest Priority Next Task

**Provider webhook receivers** (Phase 3.0) — Add webhook endpoints for email delivery status callbacks from providers like Resend and SendGrid. When a provider reports a delivery, bounce, or complaint, automatically update the email's status in SeeSee.

## Other Candidates (from ROADMAP Phase 3.0)

- Graduated body degradation (full → text → preview over time)
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

- All phases 0 through 2.1 complete
- 158 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
