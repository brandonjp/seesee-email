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
  "status": "ok",
  "version": "0.18.0",
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
| `retention_degrade_to_text_days` | int | no | — | Strip HTML after N days, 0 = never (overrides global) |
| `retention_degrade_to_preview_days` | int | no | — | Strip text after N days, 0 = never (overrides global) |

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
  "smtp_username": "my-website"
}
```

:::caution
The `api_key` is only returned on creation. Store it securely — it cannot be retrieved later. Your API key is also your SMTP password.
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
| `retention_degrade_to_text_days` | int | Strip HTML after N days (0 = never) |
| `retention_degrade_to_preview_days` | int | Strip text after N days (0 = never) |

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

### Delete app

#### `DELETE /api/v1/apps/{app_id}`

Permanently delete an app and all its emails. Requires admin Basic Auth.

```bash
curl -X DELETE http://localhost:8080/api/v1/apps/1 \
  -u admin:your-password
```

**Response (200):**

```json
{
  "message": "App deleted"
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

### Bulk delete emails

#### `DELETE /api/v1/emails`

Delete all emails matching search criteria. At least one filter is required to prevent accidental deletion of all data. Requires admin Basic Auth.

```bash
curl -X DELETE "http://localhost:8080/api/v1/emails?app_id=1&status=bounced" \
  -u admin:your-password
```

**Query parameters:** Same filters as `GET /api/v1/emails` — `q`, `app_id`, `status`, `provider`, `date_from`, `date_to`.

**Response (200):**

```json
{
  "deleted": 15,
  "message": "Deleted 15 emails"
}
```

:::caution
This permanently deletes all matching emails. Use the query parameters carefully — at least one filter must be provided.
:::

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

## Webhooks

Webhook endpoints receive delivery status callbacks from email providers and automatically update the matching email's status in SeeSee. No admin auth is required — these endpoints authenticate via provider-specific signature/token verification.

### Receive webhook

#### `POST /api/v1/webhooks/{provider}`

Supported providers: `resend`, `sendgrid`. Unknown providers return `404`.

Events are matched to stored emails using the `provider` and `provider_message_id` fields that were set when the email was originally logged.

#### Resend setup

1. In your Resend dashboard, go to **Webhooks** and add a new endpoint:
   - **URL:** `https://your-seesee-domain/api/v1/webhooks/resend`
   - **Events:** Select the events you want (e.g., `email.delivered`, `email.bounced`, `email.complained`)
2. Copy the **Signing secret** (starts with `whsec_`) and set it as `SEESEE_WEBHOOK_SECRET_RESEND`

Resend uses Svix HMAC-SHA256 signatures via `svix-id`, `svix-timestamp`, and `svix-signature` headers.

**Event mapping:**

| Resend Event | SeeSee Status |
|-------------|---------------|
| `email.sent` | `sent` |
| `email.delivered` | `delivered` |
| `email.delivery_delayed` | `delayed` |
| `email.bounced` | `bounced` |
| `email.complained` | `complained` |

**Example Resend payload:**

```json
{
  "type": "email.delivered",
  "created_at": "2026-01-01T00:00:00.000Z",
  "data": {
    "email_id": "d1234567-abcd-1234-efgh-123456789012",
    "from": "sender@example.com",
    "to": ["user@example.com"],
    "subject": "Welcome"
  }
}
```

#### SendGrid setup

1. In your SendGrid dashboard, go to **Settings > Mail Settings > Event Webhook**
2. Set the **HTTP Post URL** to: `https://your-seesee-domain/api/v1/webhooks/sendgrid?verification_token=YOUR_SECRET`
3. Set the same secret value as `SEESEE_WEBHOOK_SECRET_SENDGRID` in your SeeSee environment
4. Select the events you want (e.g., `delivered`, `bounce`, `spamreport`)

**Event mapping:**

| SendGrid Event | SeeSee Status |
|---------------|---------------|
| `processed` | `sent` |
| `delivered` | `delivered` |
| `bounce` | `bounced` |
| `dropped` | `dropped` |
| `deferred` | `deferred` |
| `spamreport` | `complained` |

**Example SendGrid payload:**

```json
[
  {
    "email": "user@example.com",
    "timestamp": 1234567890,
    "event": "delivered",
    "sg_message_id": "abc123.filter0001.16648.5515E0B88.0"
  }
]
```

#### Webhook response

All successfully parsed webhooks return `200`:

```json
{
  "processed": 1,
  "matched": 1,
  "events": [
    {
      "provider_message_id": "d1234567-abcd-1234-efgh-123456789012",
      "event_type": "email.delivered",
      "new_status": "delivered",
      "email_id": "uuid-of-matched-email",
      "matched": true
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `processed` | Number of events parsed from the payload |
| `matched` | Number of events that matched a stored email |
| `events[].matched` | Whether this specific event matched a stored email |
| `events[].email_id` | The SeeSee email ID (null if not matched) |

:::note
Unmatched events (where `provider_message_id` doesn't match any stored email) still return `200`. This is standard webhook practice — it prevents providers from retrying events for emails not tracked in SeeSee.
:::

---

## Data Export (GDPR)

### Export recipient data

#### `GET /api/v1/export`

Export all emails associated with a specific recipient email address. Supports GDPR Article 15 (right of access) — when a user requests their data, the admin can export everything SeeSee has logged for that address.

Searches across `to_addresses`, `cc_addresses`, and `bcc_addresses` fields (case-insensitive). Requires admin Basic Auth.

```bash
curl "http://localhost:8080/api/v1/export?recipient=user@example.com" \
  -u admin:your-password
```

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `recipient` | string | yes | Email address to export data for |
| `format` | string | no | Response format: `json` (default) or `csv` |

You can also request CSV format via the `Accept: text/csv` header instead of the `format` parameter.

**JSON response (200):**

```json
{
  "recipient": "user@example.com",
  "total": 2,
  "exported_at": "2026-02-20T12:00:00Z",
  "emails": [
    {
      "id": "abc-123",
      "app_id": "def-456",
      "to_addresses": ["user@example.com"],
      "from_address": "app@example.com",
      "subject": "Welcome!",
      "body_preview": "Thanks for signing up...",
      "body_html": "<h1>Welcome</h1><p>Thanks for signing up.</p>",
      "body_text": "Welcome! Thanks for signing up.",
      "status": "sent",
      "provider": "resend",
      "ingest_method": "api",
      "logged_at": "2026-02-20T10:00:00",
      "cc_addresses": null,
      "bcc_addresses": null
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `recipient` | The email address that was searched |
| `total` | Number of matching emails found |
| `exported_at` | Timestamp when the export was generated |
| `emails` | Array of email records with metadata and body content |

**CSV response:**

```bash
curl "http://localhost:8080/api/v1/export?recipient=user@example.com&format=csv" \
  -u admin:your-password \
  -o export.csv
```

Returns a CSV file with columns: `id`, `app_id`, `to_addresses`, `from_address`, `subject`, `body_preview`, `body_html`, `body_text`, `status`, `provider`, `ingest_method`, `logged_at`, `cc_addresses`, `bcc_addresses`.

:::tip
The CSV format is useful for importing into spreadsheets or data processing tools when responding to GDPR data access requests.
:::

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
