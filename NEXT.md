# Next Steps — SeeSee

**Version:** 0.11.0-dev
**Updated:** 2026-02-20

## Just Completed

- **Click-to-copy buttons on credential values** — Small clipboard icon next to API Key, SMTP Username, SMTP Password, and rotated key values in the Apps page. Uses native Clipboard API with checkmark feedback and existing toast notifications.
- **Provider webhook receivers** (Phase 3.0) — Automatic email delivery status updates from provider callbacks:
  - `POST /api/v1/webhooks/resend` — Resend delivery status webhooks (sent, delivered, bounced, complained, delayed)
  - `POST /api/v1/webhooks/sendgrid` — SendGrid event webhooks (delivered, bounced, dropped, deferred, complained)
  - Resend: Svix HMAC-SHA256 signature verification (`SEESEE_WEBHOOK_SECRET_RESEND`)
  - SendGrid: token-based verification via URL query parameter (`SEESEE_WEBHOOK_SECRET_SENDGRID`)
  - Matches webhook events to stored emails by `provider` + `provider_message_id`
  - Secrets optional — skips verification with a logged warning if not configured
  - Database index on `provider_message_id` for efficient lookups
  - 23 new tests, 183 total passing

## Highest Priority Next Task

Pick from remaining Phase 3.0 candidates based on user feedback.

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

- All phases 0 through 2.1 complete, plus provider webhook receivers from Phase 3.0
- 183 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- Provider webhook receivers for Resend and SendGrid
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
