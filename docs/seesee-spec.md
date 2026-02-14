# SeeSee — Lightweight Sent Email Log Viewer

**Project:** SeeSee  
**Website:** seesee.email  
**Tagline:** See what your apps sent.  
**Version:** 0.4.0-spec  
**Status:** Draft Specification  
**Date:** 2025-02-12  
**License:** MIT  
**Repository:** Public from day one

---

## Problem Statement

Developers who run multiple applications — each sending transactional email through various providers (Resend, SendGrid, Postmark, SES, SMTP, etc.) — have no lightweight, self-hosted way to answer the question: *"Did my app actually send that email, when, and what did it say?"*

The existing ecosystem offers either full mail delivery platforms (Postal, Cuttlefish) that are heavy and want to replace your email provider, or IMAP archivers (Mail-Archiver, Bichon, OpenArchiver) that pull from existing mailboxes — solving an entirely different problem. There is no simple "write-only log aggregator with search" for outbound application email.

**SeeSee fills this gap.** It's a single-container, self-hosted service that receives email log entries from your applications via REST API or SMTP, stores them with configurable retention, and provides a clean web UI to search and inspect them. Think Dozzle (Docker log viewer) but for outbound email.

---

## Core Principles

1. **Log-only, not a mail server.** SeeSee never sends email. Your apps continue using whatever email provider they already use. SeeSee just records what was sent.
2. **Minimal footprint.** Single Docker container. SQLite by default. No Redis, no RabbitMQ, no Postfix. Target idle RAM: <50MB.
3. **Universal ingest.** Two ways in: HTTP POST (any app, any language) or SMTP ingest (apps that already use SMTP can point at SeeSee and it captures the message).
4. **Configurable retention.** Keep the last N messages per app, or messages within a date range, or up to a storage size limit. Auto-prune on schedule.
5. **Multi-app awareness.** A single SeeSee instance serves multiple applications, each identified by an app key.
6. **Good UX matters.** The UI should feel polished and purposeful — fast search, clean layout, keyboard shortcuts. Worth a few extra kilobytes.

---

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  WordPress App  │    │  Python App     │    │  Node.js App    │
│  (sends via     │    │  (sends via     │    │  (sends via     │
│   Resend)       │    │   SES)          │    │   SendGrid)     │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
    POST /api/v1/log      SMTP :2525            POST /api/v1/log
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                │
                       ┌────────▼────────┐
                       │     SeeSee      │
                       │  ┌────────────┐ │
                       │  │  REST API   │ │  :8080
                       │  ├────────────┤ │
                       │  │ SMTP Ingest │ │  :2525
                       │  ├────────────┤ │
                       │  │  SQLite DB  │ │
                       │  ├────────────┤ │
                       │  │  Web UI     │ │
                       │  └────────────┘ │
                       └─────────────────┘
                        Single Container
```

### Ingest Methods

#### 1. REST API (Primary)
Your app sends an HTTP POST to SeeSee after sending an email. Works with any language, any provider. You control exactly what gets logged.

#### 2. SMTP Ingest (Secondary)
SeeSee listens on port 2525 as an SMTP server (via Python's `aiosmtpd`). Your app points its SMTP config at SeeSee. SeeSee captures the full email and logs it. SeeSee never forwards or delivers email — it is purely an observer. Apps should continue sending email through their normal provider separately.

**Docker networking:** The SMTP listener runs on a port inside the SeeSee container. For apps on the same Docker network, point SMTP at `seesee:2525`. For apps on isolated networks, expose the port on the host (`-p 2525:2525`) and connect via `host.docker.internal:2525` or the server's LAN IP. Same routing model as any cross-container service.

---

## Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.12+ | Broadly accessible to contributors, good ecosystem |
| Framework | FastAPI | Async, auto-generated OpenAPI docs, lightweight |
| SMTP | aiosmtpd | Lightweight, async, stdlib-adjacent, well-maintained |
| Database | SQLite (default) | Zero config, single file, FTS5 for search |
| Web UI | Jinja2 + Tailwind CSS (CDN) + Alpine.js (CDN) | No build step, polished UX, responsive |
| Container | Docker (single) | One image, one container, `docker run` and done |
| CI/CD | GitHub Actions → GHCR | Auto-build images on push/tag |
| Auth | API keys (ingest) + session auth (UI) | Simple, sufficient for self-hosted |

---

## Data Model

### `apps` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `name` | TEXT | Human-readable app name (e.g., "BookLink.fyi") |
| `slug` | TEXT | URL-safe identifier, auto-generated from name |
| `api_key` | TEXT | Hashed API key for ingest authentication |
| `smtp_username` | TEXT | SMTP auth username (auto-generated, matches app slug) |
| `smtp_password` | TEXT | Hashed SMTP password for ingest authentication |
| `body_storage_mode` | TEXT | "full", "text_only", or "preview" (default: "full") |
| `retention_max_count` | INTEGER | Max messages to keep (NULL = use global default) |
| `retention_max_age_days` | INTEGER | Max message age in days (NULL = use global default) |
| `created_at` | DATETIME | When the app was registered |
| `last_activity_at` | DATETIME | When the last email was logged |

### `emails` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `app_id` | TEXT | FK → apps.id |
| `to_addresses` | TEXT | JSON array of recipient addresses |
| `from_address` | TEXT | Sender address |
| `subject` | TEXT | Email subject line |
| `body_html` | TEXT | Full HTML body (NULL if body_storage_mode is not "full") |
| `body_text` | TEXT | Plain text body |
| `body_preview` | TEXT | First 500 chars of text (always populated) |
| `body_size_bytes` | INTEGER | Original body size for storage accounting |
| `status` | TEXT | "sent", "failed", "queued", "bounced", "delivered" |
| `provider` | TEXT | "resend", "sendgrid", "ses", "smtp", "postmark", etc. |
| `provider_message_id` | TEXT | The ID returned by the email provider |
| `error_message` | TEXT | Error details if status is "failed" |
| `metadata` | TEXT | JSON blob for arbitrary key-value data |
| `cc_addresses` | TEXT | JSON array (optional) |
| `bcc_addresses` | TEXT | JSON array (optional) |
| `reply_to` | TEXT | Reply-to address (optional) |
| `tags` | TEXT | JSON array of tags for filtering |
| `ingest_method` | TEXT | "api" or "smtp" — how this entry was captured |
| `logged_at` | DATETIME | When the email was sent (app-reported) |
| `created_at` | DATETIME | When the log entry was received by SeeSee |

### `emails_fts` Virtual Table (SQLite FTS5)

Full-text search index over: `subject`, `body_text`, `body_preview`, `to_addresses`, `from_address`, `error_message`

---

## API Specification

*See the Authentication section above for details on API keys and UI session auth.*

### Endpoints

#### `POST /api/v1/log` — Log an Email

The primary endpoint. Called by your application right after sending an email.

**Request:**
```json
{
  "to": ["user@example.com"],
  "from": "noreply@myapp.com",
  "subject": "Your password has been reset",
  "body_html": "<h1>Password Reset</h1><p>Your password was changed...</p>",
  "body_text": "Your password was changed...",
  "status": "sent",
  "provider": "resend",
  "provider_message_id": "msg_abc123",
  "metadata": {
    "user_id": "usr_456",
    "template": "password-reset"
  },
  "tags": ["transactional", "auth"],
  "cc": [],
  "bcc": [],
  "reply_to": "support@myapp.com",
  "logged_at": "2025-02-12T14:30:00Z"
}
```

**Required fields:** `to`, `from`, `subject`  
**Optional fields:** Everything else. Sensible defaults applied (status="sent", logged_at=now, etc.)

**Response (201):**
```json
{
  "id": "e1b2c3d4-...",
  "status": "logged",
  "created_at": "2025-02-12T14:30:01Z"
}
```

#### `POST /api/v1/log/batch` — Log Multiple Emails

For apps that batch-send or want to backfill. Max 100 per request.

**Response (201):**
```json
{
  "logged": 47,
  "errors": []
}
```

#### `GET /api/v1/emails` — Search Emails (UI + API)

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Full-text search query |
| `app_id` | string | Filter by application |
| `status` | string | Filter by status |
| `provider` | string | Filter by provider |
| `to` | string | Filter by recipient (partial match) |
| `from` | string | Filter by sender (partial match) |
| `tag` | string | Filter by tag |
| `after` | datetime | Messages logged after this time |
| `before` | datetime | Messages logged before this time |
| `page` | integer | Page number (default: 1) |
| `per_page` | integer | Results per page (default: 50, max: 200) |
| `sort` | string | Sort field: "logged_at", "created_at", "subject" |
| `order` | string | "desc" (default) or "asc" |

**Response (200):**
```json
{
  "emails": [ ... ],
  "total": 342,
  "page": 1,
  "per_page": 50,
  "pages": 7
}
```

#### `GET /api/v1/emails/{id}` — Get Email Detail

Returns full email record including HTML body (if stored).

#### `GET /api/v1/emails/{id}/preview` — Render HTML Preview

Returns the email's HTML body in a sandboxed format for iframe rendering.

#### `PATCH /api/v1/emails/{id}/status` — Update Email Status

For webhook-driven status updates (e.g., your provider reports a bounce).

```json
{
  "status": "bounced",
  "error_message": "550 User not found"
}
```

#### `GET /api/v1/apps` — List Apps
#### `POST /api/v1/apps` — Register App (returns API key + SMTP credentials)
#### `PATCH /api/v1/apps/{id}` — Update App Settings
#### `POST /api/v1/apps/{id}/rotate-key` — Regenerate API Key

#### `GET /api/v1/stats` — Dashboard Statistics

Returns counts by app, status, provider, and time period.

#### `GET /api/v1/health` — Health Check

Returns `200 OK` with basic status. Useful for monitoring and Coolify health checks.

---

## Body Storage Modes

Configurable per app. Controls how much of the email body is stored.

| Mode | HTML Stored | Text Stored | Preview Stored | Typical Size/Email |
|------|-------------|-------------|----------------|-------------------|
| `full` | ✅ Complete | ✅ Complete | ✅ Auto-generated | 10-100 KB |
| `text_only` | ❌ Stripped | ✅ Complete | ✅ Auto-generated | 1-5 KB |
| `preview` | ❌ Stripped | ❌ Stripped | ✅ First 500 chars | <1 KB |

- **Default:** `full` (most useful for debugging — you want to see exactly what was sent).
- **Preview** is always populated regardless of mode (for list view).
- The API accepts `body_html` and `body_text` regardless of mode; SeeSee applies the storage policy on write.

### Future: Graduated Degradation (v0.2+)

Per-app setting to automatically downgrade storage mode after a configurable number of days:

```toml
[retention.degradation]
full_to_text_after_days = 45      # Convert full HTML to text-only after 45 days
text_to_preview_after_days = 90   # Reduce to preview-only after 90 days
```

This runs as part of the nightly retention job. It preserves the metadata and searchability of old emails while reclaiming storage from HTML bodies that are no longer needed for debugging.

---

## Web UI

### Design Approach

- **Tailwind CSS** (loaded from CDN) for styling — utility-first, responsive, clean.
- **Alpine.js** (loaded from CDN) for interactivity — search-as-you-type, filter toggles, modal previews.
- **No build step.** No npm, no webpack, no node_modules. Just Jinja2 templates served by FastAPI.
- **Dark and light mode** via Tailwind's `dark:` classes, respecting system preference with manual toggle.
- **Keyboard shortcuts** for power users: `/` to focus search, `j`/`k` to navigate results, `Enter` to open detail, `Esc` to close.

### Pages

#### 1. Dashboard (`/`)
- Total emails logged (all time + last 24h / 7d / 30d)
- Breakdown by app (cards showing name, count, last activity)
- Status breakdown (sent / failed / bounced — with color indicators)
- Volume sparkline (emails per day over last 30 days)
- Quick links to recent failures/bounces

#### 2. Email List (`/emails`)
- **Search bar** (full-text, searches subject + body + addresses)
- **Filter chips** for app, status, provider, date range
- **Results table:** timestamp, app (color-coded badge), to, subject (truncated), status (icon), provider
- Click row → slide-out detail panel (or dedicated detail page)
- Pagination with page size selector
- "No results" state with helpful suggestions

#### 3. Email Detail (`/emails/{id}`)
- Header: subject, timestamp, status badge, provider badge, app badge
- Addresses: from, to, cc, bcc, reply-to
- **Tabbed content area:**
  - "Preview" tab — sandboxed iframe rendering the HTML body
  - "HTML Source" tab — syntax-highlighted raw HTML
  - "Text" tab — plain text version
  - "Metadata" tab — JSON metadata, tags, provider message ID, ingest method
- Status update history (if status was updated via API)

#### 4. Apps (`/apps`)
- List of registered apps with stats (total emails, last activity, storage mode)
- Add new app form (name → auto-generates slug, API key, SMTP credentials)
- Per-app settings: body storage mode, retention overrides
- Copy-to-clipboard for API key and SMTP credentials
- Integration code snippets (PHP, Python, JS, cURL) pre-filled with the app's credentials

#### 5. Settings (`/settings`)
- Global retention defaults (max count, max age)
- Storage usage display
- Admin password change
- SMTP ingest configuration
- Manual purge button with confirmation
- Export database / backup download

### UX Details

- **Toast notifications** for actions (app created, key regenerated, settings saved)
- **Confirmation dialogs** for destructive actions (purge, delete app)
- **Loading states** (skeleton screens, not spinners)
- **Empty states** with helpful onboarding copy ("No emails logged yet. Here's how to send your first log entry...")
- **Responsive** — usable on tablet, functional on phone, optimized for desktop
- **Relative timestamps** ("2 minutes ago") with full timestamp on hover

---

## Retention System

Retention is evaluated on a scheduled basis (configurable interval, default: every 60 minutes).

### Retention Rules (evaluated per-app, with fallback to global defaults)

| Rule | Description | Default |
|------|-------------|---------|
| `max_count` | Keep at most N emails per app | 1000 |
| `max_age_days` | Delete emails older than N days | 90 |
| `max_storage_mb` | Global storage cap (triggers oldest-first deletion) | 500 |

- Per-app settings override global defaults.
- When multiple rules apply, the most restrictive wins.
- Deletion is oldest-first within each app.
- A manual "purge" endpoint and UI button are also available.
- Retention runs are logged (count deleted, storage freed) for transparency.

---

## Configuration

All config via environment variables (12-factor style), with an optional `seesee.toml` file.

```toml
# seesee.toml (all values also settable via env vars prefixed SEESEE_)

[server]
host = "0.0.0.0"
port = 8080
base_url = "https://seesee.example.com"

[smtp_ingest]
enabled = true
port = 2525

[auth]
admin_username = "admin"
admin_password = ""  # Set via SEESEE_ADMIN_PASSWORD env var

[database]
path = "/data/seesee.db"

[retention]
default_max_count = 1000
default_max_age_days = 90
max_storage_mb = 500
cleanup_interval_minutes = 60

[ui]
theme = "system"  # "light", "dark", or "system"

[logging]
level = "info"
```

### Environment Variable Mapping

`SEESEE_ADMIN_PASSWORD`, `SEESEE_DB_PATH`, `SEESEE_PORT`, `SEESEE_SMTP_PORT`, `SEESEE_RETENTION_MAX_COUNT`, etc.

---

## Deployment

### Docker Run

```bash
docker run -d \
  --name seesee \
  -p 8080:8080 \
  -p 2525:2525 \
  -v seesee-data:/data \
  -e SEESEE_ADMIN_PASSWORD=changeme \
  ghcr.io/yourusername/seesee:latest
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  seesee:
    image: ghcr.io/yourusername/seesee:latest
    container_name: seesee
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "2525:2525"
    volumes:
      - seesee-data:/data
    environment:
      SEESEE_ADMIN_PASSWORD: "${SEESEE_ADMIN_PASSWORD:-changeme}"
      SEESEE_RETENTION_MAX_COUNT: "1000"
      SEESEE_RETENTION_MAX_AGE_DAYS: "90"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/v1/health"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  seesee-data:
```

### Coolify

One-click deploy using the Docker Compose template above. Coolify auto-detects the healthcheck. Environment variables are configured through the Coolify UI. The SQLite database persists in the named volume.

### GitHub Actions CI/CD

```yaml
# .github/workflows/build.yml
name: Build and Push Docker Image

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          push: ${{ github.event_name != 'pull_request' }}
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.sha }}
            ${{ startsWith(github.ref, 'refs/tags/v') && format('ghcr.io/{0}:{1}', github.repository, github.ref_name) || '' }}
```

This builds and pushes to GHCR on every push to `main` and on version tags. PRs build but don't push.

### Docs Site Deployment (GitHub Pages)

The `docs/` Starlight site auto-deploys to GitHub Pages on push to `main` via a second workflow (`.github/workflows/docs.yml`). Custom domain `seesee.email` is configured via a CNAME file in the Starlight public directory.

---

## SMTP Ingest Details

### How It Works

1. SeeSee runs an SMTP server on port 2525 (configurable) via `aiosmtpd`.
2. Apps configure their SMTP settings to point at SeeSee (host + port + credentials).
3. When an email arrives via SMTP, SeeSee:
   a. Authenticates the sender against app SMTP credentials.
   b. Parses the full MIME message (extracts to, from, subject, HTML body, text body).
   c. Logs the email to the database (same as a REST API call would).
   d. Returns success/failure to the sending app.

SeeSee is capture-only — it never forwards or delivers email. Apps should send email through their normal provider and use SeeSee's SMTP ingest purely for logging.

### SMTP Credentials

Each registered app gets auto-generated SMTP credentials:
- **Username:** App slug (e.g., `booklink-fyi`)
- **Password:** Auto-generated, shown once on creation (like an API key)

This lets SeeSee identify which app sent each email via SMTP, maintaining the multi-app separation.

---

## Integration Examples

### PHP (WordPress — Automatic Hook)

```php
// Drop into your theme's functions.php or a must-use plugin.
// Automatically logs every email sent by wp_mail().

add_action('wp_mail_succeeded', function($mail_data) {
    wp_remote_post(SEESEE_URL . '/api/v1/log', [
        'headers' => [
            'Authorization' => 'Bearer ' . SEESEE_API_KEY,
            'Content-Type'  => 'application/json',
        ],
        'body' => json_encode([
            'to'        => (array) $mail_data['to'],
            'from'      => $mail_data['headers']['From'] ?? get_option('admin_email'),
            'subject'   => $mail_data['subject'],
            'body_html' => $mail_data['message'],
            'body_text' => wp_strip_all_tags($mail_data['message']),
            'status'    => 'sent',
            'provider'  => 'wp_mail',
        ]),
        'blocking' => false,  // Non-blocking — don't slow down the app
    ]);
});

add_action('wp_mail_failed', function($error) {
    wp_remote_post(SEESEE_URL . '/api/v1/log', [
        'headers' => [
            'Authorization' => 'Bearer ' . SEESEE_API_KEY,
            'Content-Type'  => 'application/json',
        ],
        'body' => json_encode([
            'to'            => [],
            'from'          => get_option('admin_email'),
            'subject'       => 'Unknown',
            'status'        => 'failed',
            'error_message' => $error->get_error_message(),
            'provider'      => 'wp_mail',
        ]),
        'blocking' => false,
    ]);
});
```

### Python

```python
import httpx

SEESEE_URL = "https://seesee.example.com"
SEESEE_KEY = "ss_abc123def456"

def log_email(to, subject, body_text, provider="resend", status="sent", **kwargs):
    httpx.post(
        f"{SEESEE_URL}/api/v1/log",
        headers={"Authorization": f"Bearer {SEESEE_KEY}"},
        json={
            "to": to if isinstance(to, list) else [to],
            "from": kwargs.pop("from_addr", "noreply@example.com"),
            "subject": subject,
            "body_text": body_text,
            "status": status,
            "provider": provider,
            **kwargs,
        },
        timeout=5,
    )
```

### JavaScript / Node.js

```javascript
const SEESEE_URL = 'https://seesee.example.com';
const SEESEE_KEY = 'ss_abc123def456';

async function logEmail({ to, from, subject, bodyHtml, provider = 'sendgrid', status = 'sent', ...extra }) {
  await fetch(`${SEESEE_URL}/api/v1/log`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${SEESEE_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      to: Array.isArray(to) ? to : [to],
      from,
      subject,
      body_html: bodyHtml,
      status,
      provider,
      ...extra,
    }),
  });
}
```

### SMTP Configuration (Any App)

Point your app's SMTP settings at SeeSee:

```
SMTP Host: seesee.example.com (or host IP / Docker hostname)
SMTP Port: 2525
SMTP Username: your-app-slug
SMTP Password: (from app registration)
SMTP TLS: STARTTLS (if configured)
```

### cURL (Testing)

```bash
curl -X POST https://seesee.example.com/api/v1/log \
  -H "Authorization: Bearer ss_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["user@example.com"],
    "from": "app@example.com",
    "subject": "Test email",
    "body_text": "Hello from SeeSee!",
    "status": "sent",
    "provider": "smtp"
  }'
```

---

## MVP Scope (v0.1.0)

### In Scope

- [ ] REST API for logging emails (single + batch)
- [ ] SMTP ingest listener (capture-only)
- [ ] SQLite storage with FTS5 full-text search
- [ ] API key authentication per app (REST) + SMTP credentials per app
- [ ] Body storage modes (full / text_only / preview) configurable per app
- [ ] Web UI: dashboard, email list with search/filter, email detail with HTML preview
- [ ] App management: register, list, regenerate keys, per-app settings
- [ ] Configurable retention (max count, max age, global storage cap)
- [ ] Session-based admin auth with login page
- [ ] Docker single-container deployment
- [ ] GitHub Actions → GHCR image builds
- [ ] Docker Compose template (Coolify-compatible)
- [ ] Health check endpoint
- [ ] Auto-generated OpenAPI/Swagger docs at `/docs`
- [ ] Dark/light mode UI

### Out of Scope (Future Versions)

- [ ] Graduated body degradation (full → text → preview over time)
- [ ] Webhook receiver for provider status updates (Resend, SendGrid callbacks)
- [ ] Email resend/forward capability
- [ ] Multi-user auth with roles
- [ ] Postgres support as alternative to SQLite
- [ ] Prometheus metrics endpoint
- [ ] Email template tracking / diff comparison
- [ ] CSV/JSON export of search results
- [ ] Notification alerts (e.g., "App X hasn't sent email in 24 hours")
- [ ] WordPress plugin with settings page (code snippet in examples/ is sufficient for now)
- [ ] STARTTLS support for SMTP ingest
- [ ] Search-and-delete (find all emails for a specific address and purge them — supports GDPR right to erasure)
- [ ] Data export per recipient (supports GDPR right of access / data portability)

---

## Authentication

SeeSee has two completely separate auth systems for two different purposes.

### 1. API Authentication (Machine-to-Machine)

Your applications authenticate when logging emails via the REST API. This uses **bearer tokens** — one API key per registered app, prefixed `ss_`. No human ever interacts with this; it's just a header your app sends with each POST.

```
Authorization: Bearer ss_abc123def456
```

For SMTP ingest, apps authenticate with per-app SMTP username/password credentials (generated when the app is registered).

### 2. Web UI Authentication (Human)

The admin dashboard uses **session-based auth with a login page**. You open SeeSee in your browser, you see a login form, you type your username and password, you get a session cookie. That's it.

- Single admin user for v1 (username + password set via env var)
- Session cookie with configurable expiry (default: 7 days)
- Login page is the only publicly accessible page; everything else requires auth
- Same pattern as Dozzle, Uptime Kuma, Mailpit

### Cross-App Global Search

The core value of SeeSee is that **search spans all apps by default**. When you type a query in the search bar, it searches across every app's emails simultaneously. "Show me every email sent to user@example.com in the last week" returns results from your WordPress sites, your Python tools, your Node apps — everything in one view.

Each result shows which app sent it (color-coded badge), and you can narrow results to a specific app using the filter chips. But the default is global. This is what makes SeeSee more useful than per-app logging — it's the single pane of glass across your entire email-sending infrastructure.

---

## Project Structure

```
seesee/
├── .github/
│   └── workflows/
│       ├── build.yml           # Docker image → GHCR
│       └── docs.yml            # Docs site → GitHub Pages
├── Dockerfile
├── docker-compose.yml          # Coolify-compatible
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE                     # MIT
│
├── seesee/                     # Application code
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings / env var parsing (pydantic-settings)
│   ├── database.py             # SQLite setup, migrations, FTS5
│   ├── models.py               # Pydantic models (request/response)
│   ├── auth.py                 # API key + session auth
│   ├── retention.py            # Cleanup logic + scheduler
│   ├── smtp_server.py          # aiosmtpd ingest (capture-only)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── ingest.py           # POST /api/v1/log, /log/batch
│   │   ├── emails.py           # GET /api/v1/emails, /{id}, /preview
│   │   ├── apps.py             # App management endpoints
│   │   ├── stats.py            # Dashboard stats endpoint
│   │   └── ui.py               # HTML page routes (Jinja2)
│   ├── templates/
│   │   ├── base.html           # Layout with nav, dark mode, Tailwind
│   │   ├── login.html
│   │   ├── dashboard.html
│   │   ├── emails.html
│   │   ├── email_detail.html
│   │   ├── apps.html
│   │   ├── app_detail.html
│   │   └── settings.html
│   └── static/
│       ├── style.css           # Minimal custom styles beyond Tailwind
│       ├── app.js              # Alpine.js components + keyboard shortcuts
│       └── favicon.svg
│
├── docs/                       # Documentation + marketing site (Astro Starlight)
│   ├── astro.config.mjs
│   ├── package.json
│   └── src/
│       └── content/
│           └── docs/
│               ├── index.mdx           # Landing / marketing page
│               ├── getting-started.md  # Quick start guide
│               ├── configuration.md    # All config options
│               ├── api-reference.md    # REST API docs
│               ├── smtp-ingest.md      # SMTP ingest setup
│               ├── deployment/
│               │   ├── docker.md
│               │   └── coolify.md
│               ├── integrations/
│               │   ├── php.md
│               │   ├── python.md
│               │   ├── javascript.md
│               │   └── wordpress.md
│               └── contributing.md
│
├── examples/                   # Copy-paste integration snippets
│   ├── wordpress-hook.php
│   ├── python-example.py
│   ├── node-example.js
│   └── curl-example.sh
│
└── tests/
    ├── test_ingest.py
    ├── test_search.py
    ├── test_retention.py
    ├── test_smtp.py
    └── test_auth.py
```

### Documentation Site

The `docs/` directory contains an [Astro Starlight](https://starlight.astro.build/) site that serves as both the marketing homepage and full documentation. Starlight is chosen because:

- Docs are just markdown files — no special syntax, version-controlled with the code
- Built-in search, navigation, dark mode, mobile responsive
- Landing page support for marketing content
- Deploys to GitHub Pages via Actions (free, automatic on push to main)
- Accessible at `seesee.email` (custom domain pointed at GitHub Pages)

The documentation site is NOT required to run SeeSee — it's a separate static site that deploys independently. The SeeSee application itself has no dependency on Node.js or Astro.

---

## Privacy & Compliance Considerations

### The Reality

SeeSee logs copies of emails your applications already sent. This data already exists at your email provider (Resend, SendGrid, Postmark, SES all retain sent email logs and content), in recipient inboxes, and often in your application databases. SeeSee does not create new data exposure — it creates a self-hosted, controllable copy of data that already exists in places you have less control over.

Being self-hosted is a privacy advantage: the data never leaves your infrastructure, you control retention and deletion, and there is no third-party processor to account for.

That said, email content frequently contains personally identifiable information (PII) — names, email addresses, account details, and in some cases sensitive data like medical appointments or financial transactions. Organizations deploying SeeSee should treat it as a system that processes PII and apply appropriate controls.

### Built-In Privacy Features

SeeSee includes several features designed to support privacy-conscious deployments:

| Feature | Privacy Benefit |
|---------|----------------|
| **Per-app body storage modes** | Sensitive apps can use `preview` or `text_only` mode, avoiding storage of full HTML content |
| **Configurable retention** | Auto-delete emails after N days, satisfying storage limitation requirements |
| **Max count limits** | Cap stored emails per app, preventing unbounded data accumulation |
| **Global storage cap** | Hard ceiling on total data stored |
| **Self-hosted** | Data never leaves your server — no third-party data processor |
| **Single admin auth** | Access is restricted to authenticated administrators |

### Recommended Defaults for Sensitive Environments

For organizations in regulated sectors (healthcare, education, finance, EU data subjects), the documentation should recommend:

```toml
# Privacy-conservative defaults
[retention]
default_max_age_days = 30          # Shorter retention window
default_max_count = 500            # Lower cap per app

# For sensitive apps (set per-app in UI):
# body_storage_mode = "preview"    # Store only first 500 chars, no full content
```

### Documentation Guidance (for docs site)

The docs should include a "Privacy & Compliance" page covering:

1. **What SeeSee stores** — explicit list of all fields and data types
2. **Where data lives** — single SQLite file at a known path, easy to locate and delete
3. **How to delete data** — per-email, per-app, or full purge via UI and API
4. **GDPR considerations** — SeeSee as a data processor, retention as storage limitation, right to deletion via the purge/search-and-delete functionality
5. **Regulatory environments** — guidance for HIPAA (use preview mode, short retention), FERPA (same), and general best practices
6. **What SeeSee does NOT do** — it does not send emails, does not contact external services, does not phone home, does not collect analytics

### What This Is NOT

This is not a legal compliance framework. SeeSee is a tool. Organizations are responsible for their own compliance posture. But we can — and should — make it easy to deploy SeeSee in a privacy-respecting way by providing good defaults, clear documentation, and the right controls.

---

## Repository Strategy

**Start public.** There is no competitive advantage to hiding this — the research confirmed nobody else is building it. Going public from day one provides:

- Free GitHub Actions CI/CD (private repos have limited minutes)
- Free GHCR image hosting for public images
- Free GitHub Pages for the docs/marketing site
- Commit history that demonstrates active development
- Early feedback from the self-hosted community

A well-written README with a clear "⚠️ Early Development — Not yet production ready" badge is standard practice. People on GitHub understand that v0.1.0 is early software. The `awesome-selfhosted` community actively watches for new projects and early visibility leads to early contributors.

**Recommended workflow:**
1. Create public repo with README, LICENSE, and this spec
2. Build in the open — commit frequently, use issues for tracking
3. Tag `v0.1.0-alpha` when core functionality works
4. Submit to `awesome-selfhosted` at `v0.1.0` stable
5. Announce on Reddit r/selfhosted when docs site is live

---

## Success Metrics

For a v0.1.0 release, we'd consider this successful if:

1. `docker run` to first logged email takes under 3 minutes.
2. Search across 10,000 emails returns in under 200ms.
3. A developer can integrate their app (any language) in under 10 minutes.
4. The UI is genuinely pleasant to use — not just functional, but something you'd choose over grepping log files.
5. Idle resource usage is under 50MB RAM, near-zero CPU.