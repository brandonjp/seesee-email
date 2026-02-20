# Next Steps — SeeSee

**Version:** 0.10.0-dev
**Updated:** 2026-02-20

## Just Completed

- **Persistence diagnostics & Coolify volume fix** — Diagnosed and fixed why apps/emails were lost on every Coolify redeploy:
  - Removed `VOLUME ["/data"]` from Dockerfile (creates anonymous volumes that mask volume mounting failures)
  - Added startup persistence diagnostics logging (database state, app/email counts, mount info, WARNING on fresh DB)
  - Added `GET /api/v1/admin/debug/persistence` endpoint (volume mount status, database stats, container hostname, uptime)
  - Rewrote Coolify deployment docs with explicit Storages setup instructions and detailed troubleshooting for data loss
  - Added API reference docs for the new endpoint
  - 2 new tests, 160 total passing

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
- 160 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
