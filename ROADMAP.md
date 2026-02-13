# SeeSee Development Roadmap

**Version:** 0.5.0-dev
**Status Legend:** ✅ Complete | 🚧 In Progress | 📋 Planned | 🔮 Future

---

## Phase 0 — Project Setup ✅

- [x] Project specification (`seesee-spec.md`)
- [x] Development workflow guide (`.claude/commands/dev.md`)
- [x] Project audit checklist (`.claude/commands/audit.md`)
- [x] Repository scaffolding (pyproject.toml, Dockerfile, CI/CD, tests)
- [x] Python package structure with module stubs
- [x] Database schema with FTS5
- [x] Pydantic models for all API types
- [x] Auth utilities (API key generation, bcrypt hashing)
- [x] Integration examples (PHP, Python, Node.js, cURL)

---

## Phase 1.0 — Core API + Storage ✅

**Goal:** Working REST API that can log and retrieve emails.

- [x] SQLite database initialization on first run
- [x] `POST /api/v1/log` — log a single email
- [x] API key authentication middleware
- [x] `POST /api/v1/apps` — register app (returns API key + SMTP credentials)
- [x] `GET /api/v1/apps` — list registered apps
- [x] `PATCH /api/v1/apps/{id}` — update app settings
- [x] `POST /api/v1/apps/{id}/rotate-key` — regenerate API key
- [x] Body storage mode enforcement (full / text_only / preview)
- [x] `GET /api/v1/emails` — list/search emails with pagination
- [x] `GET /api/v1/emails/{id}` — get email detail
- [x] `GET /api/v1/emails/{id}/preview` — sandboxed HTML preview
- [x] `GET /api/v1/stats` — dashboard statistics
- [x] `GET /api/v1/health` — health check with database status
- [x] FTS5 full-text search integration (sync triggers)
- [x] Error response consistency (`{"error": "...", "detail": "..."}`)

---

## Phase 1.1 — Web UI 🚧

**Goal:** Admin dashboard for searching and viewing logged emails.

- [x] Login page with session-based auth (itsdangerous signed cookies)
- [x] Base layout (sidebar nav, dark mode toggle, brand styling)
- [x] Dashboard page (stats cards, status breakdown, per-app counts, empty state)
- [x] Email list page (search bar, filter dropdowns, results table, pagination)
- [x] Email detail page (header, addresses, tabbed content: preview/HTML/text/metadata)
- [x] App management page (list, add modal, credentials display, key rotation)
- [x] Dark/light mode with system preference + manual toggle
- [x] Confirmation dialogs for destructive actions (key rotation)
- [x] Empty states with onboarding copy
- [x] Responsive design (desktop-optimized, tablet-usable)
- [ ] App detail page (stats, integration snippets pre-filled with credentials)
- [ ] Settings page (retention config, storage usage, manual purge)
- [ ] Keyboard shortcuts (`/` search, `j`/`k` navigate, `Enter` open, `Esc` close)
- [ ] Toast notifications for actions

---

## Phase 1.2 — SMTP Ingest ✅

**Goal:** Accept emails via SMTP for apps that already use SMTP.

- [x] aiosmtpd listener on configurable port (default 2525)
- [x] SMTP AUTH with per-app username/password credentials
- [x] MIME message parsing (extract to, from, subject, HTML body, text body)
- [x] Log parsed email to database (same as REST API path)
- [x] Optional upstream relay (forward to real SMTP server for delivery)
- [x] Capture-only mode (no relay) for apps that send via provider API separately

---

## Phase 1.3 — Retention + Deployment 📋

**Goal:** Automated cleanup and production-ready container.

- [ ] Retention scheduler (runs on configurable interval, default 60 min)
- [ ] `max_count` enforcement — keep at most N emails per app
- [ ] `max_age_days` enforcement — delete emails older than N days
- [ ] `max_storage_mb` enforcement — global storage cap, oldest-first deletion
- [ ] Per-app retention overrides (most restrictive rule wins)
- [ ] Cleanup logging (count deleted, storage freed)
- [ ] Manual purge via API and UI
- [ ] Dockerfile finalized (multi-stage, non-root, health check)
- [ ] Docker Compose verified with Coolify
- [ ] GitHub Actions: build + push to GHCR on tag
- [ ] `.env.example` with all variables documented

---

## Phase 2.0 — Documentation Site 📋

**Goal:** Public docs site at seesee.email via Astro Starlight.

- [ ] Astro Starlight setup in `docs/`
- [ ] Landing/marketing page
- [ ] Getting started guide
- [ ] Configuration reference (all SEESEE_* variables)
- [ ] REST API reference
- [ ] SMTP ingest guide
- [ ] Docker deployment guide
- [ ] Coolify deployment guide
- [ ] Integration guides: PHP, Python, JavaScript, WordPress
- [ ] Privacy & compliance page
- [ ] Contributing page
- [ ] GitHub Actions: docs build + deploy to GitHub Pages

---

## Phase 2.1 — Polish 📋

**Goal:** Quality-of-life improvements for daily use.

- [ ] `POST /api/v1/log/batch` — batch ingest (max 100 per request)
- [ ] `PATCH /api/v1/emails/{id}/status` — status update endpoint
- [ ] Loading states (skeleton screens)
- [ ] Relative timestamps ("2 minutes ago") with full timestamp on hover
- [ ] Integration snippets in app detail (pre-filled with app's credentials)
- [ ] Volume sparkline on dashboard (emails per day, last 30 days)
- [ ] Empty state onboarding ("No emails logged yet. Here's how...")

---

## Phase 3.0 — Future 🔮

**Goal:** Advanced features based on user feedback.

- [ ] Graduated body degradation (full → text → preview over time)
- [ ] Provider webhook receivers (Resend, SendGrid status callbacks)
- [ ] Search-and-delete (GDPR right to erasure)
- [ ] Data export per recipient (GDPR right of access)
- [ ] CSV/JSON search export
- [ ] Prometheus metrics endpoint
- [ ] Multi-user auth with roles
- [ ] WordPress plugin with settings page
- [ ] Postgres support as alternative to SQLite
- [ ] STARTTLS support for SMTP ingest
- [ ] Notification alerts ("App X hasn't sent email in 24 hours")
