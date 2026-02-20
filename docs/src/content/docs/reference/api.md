---
title: REST API Reference
description: Complete documentation of all SeeSee REST API endpoints.
---

SeeSee provides a REST API under `/api/v1/`. All requests and responses use JSON.

FastAPI auto-generates interactive OpenAPI documentation at `/docs` on your running instance.

## Authentication

SeeSee uses two authentication methods:

| Context | Method | Header |
|---------|--------|--------|
| Per-app endpoints (logging emails) | Bearer token | `Authorization: Bearer ss_...` |
| Admin endpoints (managing apps, querying emails) | HTTP Basic Auth | `Authorization: Basic base64(user:pass)` |

API keys are prefixed with `ss_` and are generated when you create an app. They are shown once — store them securely.

## Error responses

All errors follow a consistent format:

```json
{
  "error": "Short error description",
  "detail": "More detailed explanation (optional)"
}
```

Common HTTP status codes:

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad request (validation error) |
| `401` | Unauthorized (missing or invalid credentials) |
| `404` | Not found |
| `422` | Unprocessable entity (invalid request body) |
| `500` | Internal server error |

---

## Health

### `GET /api/v1/health`

Returns service status and database health. No authentication required.

```bash
curl http://localhost:8080/api/v1/health
```

```json
{
  "status": "healthy",
  "version": "0.6.0-dev",
  "database": "ok"
}
```

---

## Apps

All app endpoints require admin Basic Auth.

### Create app

#### `POST /api/v1/apps`

Create a new app and receive its API key and SMTP credentials.

```bash
curl -X POST http://localhost:8080/api/v1/apps \
  -u admin:your-password \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Website",
    "body_storage_mode": "full"
  }'
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Display name for the app |
| `body_storage_mode` | string | no | `full` | How to store email bodies: `full`, `text_only`, or `preview` |
| `retention_max_count` | int | no | — | Per-app email count limit (overrides global) |
| `retention_max_age_days` | int | no | — | Per-app max age in days (overrides global) |

**Response (201):**

```json
{
  "id": 1,
  "name": "My Website",
  "slug": "my-website",
  "body_storage_mode": "full",
  "retention_max_count": null,
  "retention_max_age_days": null,
  "last_activity_at": null,
  "created_at": "2025-01-15T10:30:00Z",
  "api_key": "ss_abc123...",
  "smtp_username": "my-website",
  "smtp_password": "xyz789..."
}
```

:::caution
The `api_key` and `smtp_password` are only returned on creation. Store them securely — they cannot be retrieved later.
:::

### List apps

#### `GET /api/v1/apps`

```bash
curl http://localhost:8080/api/v1/apps \
  -u admin:your-password
```

**Response (200):**

```json
[
  {
    "id": 1,
    "name": "My Website",
    "slug": "my-website",
    "body_storage_mode": "full",
    "retention_max_count": null,
    "retention_max_age_days": null,
    "last_activity_at": "2025-01-15T12:00:00Z",
    "created_at": "2025-01-15T10:30:00Z"
  }
]
```

### Update app

#### `PATCH /api/v1/apps/{app_id}`

Update app settings. All fields are optional.

```bash
curl -X PATCH http://localhost:8080/api/v1/apps/1 \
  -u admin:your-password \
  -H "Content-Type: application/json" \
  -d '{
    "body_storage_mode": "text_only",
    "retention_max_count": 500
  }'
```

**Request body:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Update display name |
| `body_storage_mode` | string | `full`, `text_only`, or `preview` |
| `retention_max_count` | int | Per-app email count limit |
| `retention_max_age_days` | int | Per-app max age in days |

### Rotate API key

#### `POST /api/v1/apps/{app_id}/rotate-key`

Regenerate the app's API key. The old key stops working immediately.

```bash
curl -X POST http://localhost:8080/api/v1/apps/1/rotate-key \
  -u admin:your-password
```

**Response (200):**

```json
{
  "api_key": "ss_new_key_here...",
  "message": "API key rotated successfully"
}
```

---

## Email Logging

### Log a single email

#### `POST /api/v1/log`

Requires app Bearer token authentication.

```bash
curl -X POST http://localhost:8080/api/v1/log \
  -H "Authorization: Bearer ss_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["user@example.com"],
    "from": "app@example.com",
    "subject": "Welcome!",
    "body_html": "<h1>Welcome</h1><p>Thanks for signing up.</p>",
    "body_text": "Welcome! Thanks for signing up.",
    "status": "sent",
    "provider": "resend"
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `to` | string[] | yes | Recipient email addresses |
| `from` | string | yes | Sender email address |
| `subject` | string | yes | Email subject line |
| `body_html` | string | no | HTML body content |
| `body_text` | string | no | Plain text body content |
| `status` | string | no | Email status (e.g., `sent`, `failed`, `queued`, `bounced`) |
| `provider` | string | no | Sending provider (e.g., `resend`, `sendgrid`, `ses`, `smtp`) |
| `provider_message_id` | string | no | Provider's message ID for tracking |
| `error_message` | string | no | Error details if delivery failed |
| `metadata` | object | no | Arbitrary key-value metadata |
| `cc` | string[] | no | CC recipients |
| `bcc` | string[] | no | BCC recipients |
| `reply_to` | string | no | Reply-to address |
| `tags` | string[] | no | Tags for categorization |
| `logged_at` | string | no | ISO 8601 timestamp (defaults to now) |

**Response (201):**

```json
{
  "id": 42,
  "status": "sent",
  "created_at": "2025-01-15T12:00:00Z"
}
```

### Log a batch of emails

#### `POST /api/v1/log/batch`

Log up to 100 emails in a single request. Same auth and fields as the single endpoint.

```bash
curl -X POST http://localhost:8080/api/v1/log/batch \
  -H "Authorization: Bearer ss_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "emails": [
      {
        "to": ["user1@example.com"],
        "from": "app@example.com",
        "subject": "Welcome user 1",
        "body_text": "Hello user 1",
        "status": "sent"
      },
      {
        "to": ["user2@example.com"],
        "from": "app@example.com",
        "subject": "Welcome user 2",
        "body_text": "Hello user 2",
        "status": "sent"
      }
    ]
  }'
```

**Response (201):**

```json
{
  "logged": 2,
  "errors": []
}
```

---

## Email Management

### Update email status

#### `PATCH /api/v1/emails/{email_id}/status`

Update an email's status after initial logging. Requires admin Basic Auth.

Use case: provider webhooks update delivery status (e.g., `sent` → `delivered` or `bounced`).

```bash
curl -X PATCH http://localhost:8080/api/v1/emails/42/status \
  -u admin:your-password \
  -H "Content-Type: application/json" \
  -d '{"status": "delivered"}'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | yes | New status value |

**Response (200):** Full email detail object with updated status.

### Delete a single email

#### `DELETE /api/v1/emails/{email_id}`

Permanently delete a single email. Requires admin Basic Auth.

```bash
curl -X DELETE http://localhost:8080/api/v1/emails/42 \
  -u admin:your-password
```

**Response (200):**

```json
{
  "message": "Email deleted"
}
```

### Purge all emails for an app

#### `DELETE /api/v1/apps/{app_id}/emails`

Delete all emails for a specific app. Requires admin Basic Auth.

```bash
curl -X DELETE http://localhost:8080/api/v1/apps/1/emails \
  -u admin:your-password
```

**Response (200):**

```json
{
  "message": "Deleted 42 emails"
}
```

---

## Email Queries

All query endpoints require admin Basic Auth.

### List and search emails

#### `GET /api/v1/emails`

```bash
curl "http://localhost:8080/api/v1/emails?q=welcome&status=sent&per_page=10" \
  -u admin:your-password
```

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | — | Full-text search query (searches subject, body, addresses, errors) |
| `app_id` | int | — | Filter by app ID |
| `status` | string | — | Filter by status |
| `provider` | string | — | Filter by provider |
| `date_from` | string | — | Filter emails logged after this ISO date |
| `date_to` | string | — | Filter emails logged before this ISO date |
| `sort` | string | `logged_at` | Sort field: `logged_at`, `created_at`, `subject` |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `page` | int | `1` | Page number |
| `per_page` | int | `20` | Results per page (1–100) |

**Response (200):**

```json
{
  "emails": [
    {
      "id": 42,
      "app_id": 1,
      "to_addresses": "[\"user@example.com\"]",
      "from_address": "app@example.com",
      "subject": "Welcome!",
      "body_preview": "Thanks for signing up...",
      "status": "sent",
      "provider": "resend",
      "ingest_method": "api",
      "logged_at": "2025-01-15T12:00:00Z",
      "created_at": "2025-01-15T12:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 20,
  "pages": 1
}
```

:::tip
Full-text search uses SQLite FTS5. Use `*` for prefix matching: `pass*` matches "password", "passport", etc.
:::

### Get email detail

#### `GET /api/v1/emails/{email_id}`

```bash
curl http://localhost:8080/api/v1/emails/42 \
  -u admin:your-password
```

**Response (200):**

Returns the full email detail including `body_html`, `body_text`, `body_size_bytes`, `metadata`, `cc_addresses`, `bcc_addresses`, `reply_to`, `tags`, `provider_message_id`, and `error_message`.

### Preview email HTML

#### `GET /api/v1/emails/{email_id}/preview`

Returns rendered HTML content with security headers (CSP) suitable for iframe embedding. For plain-text emails, the text is wrapped in `<pre>` tags with HTML escaping.

```bash
curl http://localhost:8080/api/v1/emails/42/preview \
  -u admin:your-password
```

---

## Stats

### Dashboard statistics

#### `GET /api/v1/stats`

Requires admin Basic Auth.

```bash
curl http://localhost:8080/api/v1/stats \
  -u admin:your-password
```

**Response (200):**

```json
{
  "total_emails": 1234,
  "emails_24h": 45,
  "emails_7d": 312,
  "emails_30d": 890,
  "total_apps": 5,
  "by_status": {
    "sent": 1100,
    "failed": 50,
    "queued": 84
  },
  "by_app": [
    { "id": 1, "name": "My Website", "count": 500 },
    { "id": 2, "name": "Newsletter", "count": 734 }
  ]
}
```

---

## Admin

### Trigger retention cleanup

#### `POST /api/v1/admin/cleanup`

Trigger an immediate retention cleanup cycle. This runs the same cleanup that the background scheduler runs on the configured interval. Requires admin Basic Auth.

```bash
curl -X POST http://localhost:8080/api/v1/admin/cleanup \
  -u admin:your-password
```

**Response (200):**

```json
{
  "message": "Cleanup completed"
}
```

### Persistence diagnostics

#### `GET /api/v1/admin/debug/persistence`

Return diagnostic information about database persistence and volume mounting. Useful for debugging data loss after container redeploys, especially on platforms like Coolify. Requires admin Basic Auth.

```bash
curl http://localhost:8080/api/v1/admin/debug/persistence \
  -u admin:your-password
```

**Response (200):**

```json
{
  "db_path": "/data/seesee.db",
  "db_size_bytes": 245760,
  "db_modified_at": "2026-02-20T10:30:00+00:00",
  "app_count": 3,
  "email_count": 1234,
  "schema_version": "1",
  "oldest_app_created_at": "2026-01-15T10:30:00",
  "uptime_seconds": 3661.42,
  "hostname": "abc123def456",
  "volume_mounted": true,
  "mount_info": "device=overlay mount=/data fstype=overlay"
}
```

| Field | Description |
|-------|-------------|
| `db_path` | Resolved path to the SQLite database file |
| `db_size_bytes` | Database file size in bytes |
| `db_modified_at` | Last modification time (ISO 8601) |
| `app_count` | Number of registered apps |
| `email_count` | Total number of stored emails |
| `schema_version` | Database schema version |
| `oldest_app_created_at` | Creation time of the oldest app |
| `uptime_seconds` | Seconds since application startup |
| `hostname` | Container hostname (container ID in Docker) |
| `volume_mounted` | Whether `/data` is a separate mount point |
| `mount_info` | Filesystem device and type for the data directory |
