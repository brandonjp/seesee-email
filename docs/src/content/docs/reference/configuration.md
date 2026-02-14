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

Apps can override `max_count` and `max_age_days` with per-app values set during app creation or update. The effective limit is the **minimum** of the per-app and global value.

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

# Session
SEESEE_SECRET_KEY=your-random-secret-key
SEESEE_SESSION_MAX_AGE_DAYS=7

# Logging
SEESEE_LOG_LEVEL=info
```
