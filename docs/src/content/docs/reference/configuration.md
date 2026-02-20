---
title: Configuration Reference
description: All SeeSee environment variables with defaults, types, and descriptions.
---

SeeSee is configured entirely through environment variables. All variables use the `SEESEE_` prefix.

Copy `.env.example` from the repository as a starting template.

## Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_PORT` | int | `8080` | HTTP server port |
| `SEESEE_BASE_URL` | string | `http://localhost:8080` | Public base URL of the service |

## Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_ADMIN_USERNAME` | string | `admin` | Admin username for Web UI and API basic auth |
| `SEESEE_ADMIN_PASSWORD` | string | *(required)* | Admin password — **must be set**, no default |

:::caution
`SEESEE_ADMIN_PASSWORD` has no default value. SeeSee will not start without it. Choose a strong password for production deployments.
:::

## Database

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_DB_PATH` | string | `/data/seesee.db` | Path to the SQLite database file |

The database directory must be writable. In Docker, mount a volume at `/data` for persistence.

## SMTP Ingest

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_SMTP_ENABLED` | bool | `true` | Enable the built-in SMTP server |
| `SEESEE_SMTP_PORT` | int | `2525` | SMTP server listen port |

## Retention

Retention rules control automatic cleanup. The most restrictive rule wins.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_RETENTION_MAX_COUNT` | int | `1000` | Maximum emails to keep per app. Oldest are deleted first |
| `SEESEE_RETENTION_MAX_AGE_DAYS` | int | `90` | Delete emails older than this many days |
| `SEESEE_RETENTION_MAX_STORAGE_MB` | int | `500` | Global storage cap in MB. Oldest emails deleted first when exceeded |
| `SEESEE_RETENTION_CLEANUP_INTERVAL_MINUTES` | int | `60` | How often the retention scheduler runs (in minutes) |
| `SEESEE_RETENTION_DEGRADE_TO_TEXT_DAYS` | int | `0` | Strip HTML body after N days, keeping text + preview. `0` = never degrade |
| `SEESEE_RETENTION_DEGRADE_TO_PREVIEW_DAYS` | int | `0` | Strip text body after N days, keeping preview only. `0` = never degrade |

Apps can override `max_count`, `max_age_days`, `degrade_to_text_days`, and `degrade_to_preview_days` with per-app values set during app creation or update. For retention limits, the effective value is the **minimum** of the per-app and global value. For degradation thresholds, a per-app override can enable degradation even if the global setting is disabled.

## Session

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_SECRET_KEY` | string | *(falls back to admin password)* | Secret key for signing session cookies. Set a unique value in production |
| `SEESEE_SESSION_MAX_AGE_DAYS` | int | `7` | Session cookie expiry in days |

:::tip
Set `SEESEE_SECRET_KEY` to a unique random string in production. If not set, it falls back to `SEESEE_ADMIN_PASSWORD`, which means changing your password will invalidate all sessions.
:::

## UI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_THEME` | string | `system` | Default theme: `light`, `dark`, or `system` (follows OS preference) |
| `SEESEE_DISPLAY_TIMEZONE` | string | `UTC` | IANA timezone string for admin date display (e.g. `America/Chicago`, `Europe/London`). Controls how dates appear in admin views only — does **not** affect storage (always UTC) or API responses (always UTC ISO 8601) |

## Webhook Secrets

Optional secrets for verifying webhook payloads from email providers. If not set, signature verification is skipped (a warning is logged).

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_WEBHOOK_SECRET_RESEND` | string | *(empty)* | Svix signing secret from the Resend dashboard (starts with `whsec_`) |
| `SEESEE_WEBHOOK_SECRET_SENDGRID` | string | *(empty)* | Shared secret for SendGrid webhook token verification |

:::tip
For production deployments, always configure webhook secrets to prevent unauthorized status updates. See the [Webhooks API reference](/reference/api/#webhooks) for setup instructions.
:::

## Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SEESEE_LOG_LEVEL` | string | `info` | Log level: `debug`, `info`, `warning`, `error`, `critical` |

## Example `.env` file

```bash
# Required
SEESEE_ADMIN_PASSWORD=change-me-to-something-secure

# Server
SEESEE_PORT=8080
SEESEE_BASE_URL=https://seesee.example.com

# Database (default is fine for Docker)
SEESEE_DB_PATH=/data/seesee.db

# SMTP
SEESEE_SMTP_ENABLED=true
SEESEE_SMTP_PORT=2525

# Retention
SEESEE_RETENTION_MAX_COUNT=1000
SEESEE_RETENTION_MAX_AGE_DAYS=90
SEESEE_RETENTION_MAX_STORAGE_MB=500
SEESEE_RETENTION_DEGRADE_TO_TEXT_DAYS=0
SEESEE_RETENTION_DEGRADE_TO_PREVIEW_DAYS=0

# UI
SEESEE_DISPLAY_TIMEZONE=UTC  # e.g. "America/Chicago", "Europe/London"

# Session
SEESEE_SECRET_KEY=your-random-secret-key
SEESEE_SESSION_MAX_AGE_DAYS=7

# Webhook secrets (optional)
SEESEE_WEBHOOK_SECRET_RESEND=whsec_your_resend_signing_secret
SEESEE_WEBHOOK_SECRET_SENDGRID=your-sendgrid-shared-secret

# Logging
SEESEE_LOG_LEVEL=info
```
