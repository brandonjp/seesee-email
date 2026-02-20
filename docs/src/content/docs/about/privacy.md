---
title: Privacy & Compliance
description: What SeeSee stores, retention policies, and GDPR considerations.
---

SeeSee is self-hosted — your email data stays on your server. This page explains what data is stored, how to control it, and what to consider for privacy compliance.

## What SeeSee stores

SeeSee logs **metadata and content of sent emails**. For each email:

| Data | Stored | Notes |
|------|--------|-------|
| Recipient addresses (to, cc, bcc) | Yes | Stored as JSON arrays |
| Sender address | Yes | |
| Subject line | Yes | Indexed for full-text search |
| Email body (HTML and/or text) | Configurable | Depends on body storage mode |
| Body preview (first 500 chars) | Yes | Always generated |
| Email status | Yes | sent, failed, queued, bounced, etc. |
| Provider name | Yes | e.g., resend, sendgrid, smtp |
| Provider message ID | Yes | For cross-referencing with provider |
| Error messages | Yes | For failed deliveries |
| Custom metadata | Yes | Arbitrary key-value pairs |
| Tags | Yes | User-defined categorization |
| Timestamps | Yes | When logged and when created |
| Ingest method | Yes | `api` or `smtp` |

## What SeeSee does NOT store

- **Attachments** — MIME attachments are not stored (SMTP ingest skips them)
- **Original raw email** — only parsed fields are stored
- **Recipient inbox data** — SeeSee is log-only, it doesn't access inboxes
- **Tracking data** — no open tracking, click tracking, or analytics
- **User accounts** — there's one admin account, no multi-user data

## Body storage modes

Each app can be configured with a body storage mode that controls how much email content is retained:

| Mode | What's stored | Typical size | Use case |
|------|---------------|-------------|----------|
| `full` | Complete HTML + text body | 10–100 KB/email | Full audit trail, debug HTML rendering |
| `text_only` | Text body only, no HTML | 1–5 KB/email | Reduced storage, text content sufficient |
| `preview` | First 500 characters only | <1 KB/email | Minimal storage, just enough to identify emails |

Set the mode per app:

```bash
# On creation
curl -X POST http://localhost:8080/api/v1/apps \
  -u admin:password \
  -H "Content-Type: application/json" \
  -d '{"name": "Sensitive App", "body_storage_mode": "preview"}'

# Update existing app
curl -X PATCH http://localhost:8080/api/v1/apps/1 \
  -u admin:password \
  -H "Content-Type: application/json" \
  -d '{"body_storage_mode": "text_only"}'
```

## Retention policies

SeeSee automatically deletes old data based on configurable retention rules:

| Rule | Variable | Default | Scope |
|------|----------|---------|-------|
| **Max count** | `SEESEE_RETENTION_MAX_COUNT` | 1000 per app | Per-app |
| **Max age** | `SEESEE_RETENTION_MAX_AGE_DAYS` | 90 days | Per-app |
| **Storage cap** | `SEESEE_RETENTION_MAX_STORAGE_MB` | 500 MB | Global |

- The **most restrictive rule wins** — if an email exceeds any limit, it's deleted
- Deletion is **oldest-first**
- The cleanup scheduler runs every 60 minutes by default (configurable via `SEESEE_RETENTION_CLEANUP_INTERVAL_MINUTES`)
- Per-app overrides can set stricter limits than the global defaults

## Data location

All data is stored locally on your server:

- **Database:** Single SQLite file at the configured `SEESEE_DB_PATH` (default `/data/seesee.db`)
- **No cloud services** — SeeSee makes no outbound connections
- **No telemetry** — no usage data is sent anywhere
- **No CDN** — the Web UI uses bundled assets (Tailwind CSS and Alpine.js from CDN are loaded client-side)

## GDPR considerations

Since SeeSee is self-hosted, **you are the data controller**. Here's how SeeSee supports GDPR compliance:

### Storage limitation (Article 5(1)(e))

- Configurable retention policies automatically delete old data
- Per-app storage modes let you minimize data for sensitive applications
- Set aggressive retention for apps that process personal data

### Data minimization (Article 5(1)(c))

- Use `text_only` or `preview` body storage modes to reduce stored data
- Only log the fields you need — all fields except `to`, `from`, and `subject` are optional

### Right to erasure (Article 17)

- `DELETE /api/v1/emails` — bulk delete emails matching search criteria (by app, status, provider, date range, or full-text query)
- `DELETE /api/v1/emails/{id}` — delete individual emails
- Automatic retention policies continuously delete old data

### Right of access / Data portability (Articles 15 & 20)

- `GET /api/v1/export?recipient=user@example.com` — export all emails associated with a recipient address
- Searches across to, cc, and bcc fields (case-insensitive)
- Supports JSON and CSV output formats
- Includes email metadata and body content

### Security (Article 32)

- Admin credentials required for all access
- API keys are hashed with bcrypt (plaintext never stored)
- Session cookies are cryptographically signed
- Database is a local file — standard filesystem security applies
- Docker image runs as non-root user

## Recommendations for production

1. **Set appropriate retention** — don't keep emails longer than necessary
2. **Use `text_only` or `preview`** for apps handling sensitive content
3. **Secure access** — use a strong admin password and HTTPS (via reverse proxy)
4. **Back up the database** — and secure backups with the same care as the live data
5. **Document your use** — if required by your privacy policy, note that sent email logs are retained
6. **Network isolation** — run SeeSee on an internal network if possible; SMTP port 2525 should not be publicly exposed without authentication
