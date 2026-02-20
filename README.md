# SeeSee

**See what your apps sent.** Lightweight, self-hosted sent email log aggregator with search UI.

[![Early Development](https://img.shields.io/badge/status-early%20development-orange)](https://github.com/brandonjp/seesee-email)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)

---

SeeSee receives email log entries from your applications via REST API or SMTP, stores them with configurable retention in SQLite, and provides a clean web UI to search and inspect them. Think Dozzle (Docker log viewer) but for outbound email.

**One instance, all your apps.** Search across every application's sent emails in one view.

## Quick Start

```bash
docker run -d \
  --name seesee \
  -p 8080:8080 \
  -p 2525:2525 \
  -v seesee-data:/data \
  -e SEESEE_ADMIN_PASSWORD=changeme \
  ghcr.io/brandonjp/seesee-email:latest
```

Open `http://localhost:8080` and log in with `admin` / `changeme`.

### Docker Compose

```yaml
services:
  seesee:
    image: ghcr.io/brandonjp/seesee-email:latest
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "2525:2525"
    volumes:
      - seesee-data:/data
    environment:
      SEESEE_ADMIN_PASSWORD: "${SEESEE_ADMIN_PASSWORD:-changeme}"

volumes:
  seesee-data:
```

## How It Works

1. Your apps send email through their normal provider (Resend, SendGrid, SES, SMTP, etc.)
2. After sending, they log the email to SeeSee via a simple HTTP POST or SMTP ingest
3. SeeSee stores the metadata and body in SQLite with full-text search
4. You search and inspect sent emails through the web UI

```
Your App → sends email via provider → logs to SeeSee → search & inspect in browser
```

## Log an Email

```bash
curl -X POST http://localhost:8080/api/v1/log \
  -H "Authorization: Bearer ss_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["user@example.com"],
    "from": "app@example.com",
    "subject": "Welcome!",
    "body_text": "Thanks for signing up.",
    "status": "sent",
    "provider": "resend"
  }'
```

See [examples/](examples/) for PHP/WordPress, Python, Node.js, and cURL integration snippets.

## Features

- **REST API** — `POST /api/v1/log` from any language
- **SMTP Ingest** — Point your app's SMTP at SeeSee on port 2525
- **Full-Text Search** — SQLite FTS5 across subject, body, addresses
- **Multi-App** — One instance serves all your applications
- **Web UI** — Dashboard, email list, detail view with HTML preview
- **Configurable Retention** — Max count, max age, storage cap per app
- **Body Storage Modes** — Full, text-only, or preview-only per app
- **Dark/Light Mode** — System preference with manual toggle
- **Single Container** — Docker, no external dependencies

## Documentation

Full documentation at **[seesee.email](https://seesee.email)** — getting started, API reference, deployment guides, integrations, and more.

Auto-generated OpenAPI docs also available at `/docs` on your running instance.

## Timezone Handling

- **Storage:** All dates stored in UTC. Do not change this.
- **Admin display:** Controlled by `SEESEE_DISPLAY_TIMEZONE` env var (default: `UTC`). IANA timezone string (e.g. `America/Chicago`). Used in admin views via `seesee.timezone` helpers and the `display_dt` Jinja2 filter.
- **User display:** Dates are displayed in the browser's local timezone via client-side JavaScript (`Intl.DateTimeFormat`). Tooltips show both local and UTC times.
- **API responses:** Always UTC ISO 8601.

## Tech Stack

Python 3.12+ / FastAPI / SQLite FTS5 / Jinja2 + Tailwind CSS + Alpine.js / Docker

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

[MIT](LICENSE)
