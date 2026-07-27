# SeeSee Development Roadmap

**Version:** 0.19.15-dev
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

## Phase 1.1 — Web UI ✅

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
- [x] App detail page (stats, integration snippets pre-filled with credentials)
- [x] Settings page (retention config, storage usage, manual cleanup)
- [x] Keyboard shortcuts (`/` search, `j`/`k` navigate, `Enter` open, `Esc` close, `?` help)
- [x] Toast notifications for actions (app created, key rotated, cleanup, delete)

---

## Phase 1.2 — SMTP Ingest ✅

**Goal:** Accept emails via SMTP for apps that already use SMTP.

- [x] aiosmtpd listener on configurable port (default 2525)
- [x] SMTP AUTH with per-app username/password credentials
- [x] MIME message parsing (extract to, from, subject, HTML body, text body)
- [x] Log parsed email to database (same as REST API path)
- [x] Capture-only SMTP ingest (emails are logged but never forwarded)

---

## Phase 1.3 — Retention + Deployment ✅

**Goal:** Automated cleanup and production-ready container.

- [x] Retention scheduler (runs on configurable interval, default 60 min)
- [x] `max_count` enforcement — keep at most N emails per app
- [x] `max_age_days` enforcement — delete emails older than N days
- [x] `max_storage_mb` enforcement — global storage cap, oldest-first deletion
- [x] Per-app retention overrides (most restrictive rule wins)
- [x] Cleanup logging (count deleted, storage freed)
- [x] Manual purge via API and UI
- [x] Dockerfile finalized (multi-stage, non-root, health check)
- [x] Docker Compose verified with Coolify
- [x] GitHub Actions: build + push to GHCR on tag (multi-platform: amd64 + arm64)
- [x] `.env.example` with all variables documented

---

## Phase 2.0 — Documentation Site ✅

**Goal:** Public docs site at seesee.email via Astro Starlight.

- [x] Astro Starlight setup in `docs/` with brand color customization
- [x] Landing/marketing page with architecture diagram and feature highlights
- [x] Getting started guide (Docker quick start, app creation, first email)
- [x] Configuration reference (all SEESEE_* variables grouped by category)
- [x] REST API reference (all endpoints with curl examples)
- [x] SMTP ingest guide (setup, client examples, troubleshooting)
- [x] Docker deployment guide (compose, volumes, health checks, reverse proxies)
- [x] Coolify deployment guide (step-by-step with SSL and storage)
- [x] Integration guides: PHP/WordPress, Python, JavaScript, cURL
- [x] Privacy & compliance page (storage modes, retention, GDPR)
- [x] Contributing page (dev setup, code style, testing, git workflow)
- [x] GitHub Actions: docs build + deploy to GitHub Pages (verified compatible)

---

## Phase 2.1 — Polish ✅

**Goal:** Quality-of-life improvements for daily use.

- [x] `POST /api/v1/log/batch` — batch ingest (max 100 per request)
- [x] `PATCH /api/v1/emails/{id}/status` — status update endpoint
- [x] `DELETE /api/v1/emails/{id}` — delete single email
- [x] `DELETE /api/v1/apps/{app_id}/emails` — purge all emails for an app
- [x] `POST /api/v1/admin/cleanup` — manual retention cleanup trigger
- [x] Relative timestamps ("2 minutes ago") with full timestamp on hover
- [x] Integration snippets in app detail (pre-filled with app's credentials)
- [x] Volume sparkline on dashboard (emails per day, last 30 days)
- [x] Empty state onboarding ("No emails logged yet. Here's how...")
- [x] Keyboard shortcuts (`/` search, `j`/`k` navigate, `Enter` open, `Esc` close, `?` help modal)
- [x] Toast notifications for actions (success and error variants, auto-dismiss)
- [x] `DELETE /api/v1/apps/{app_id}` — delete app and all its emails
- [x] App deletion UI with confirmation modal (apps list + app detail page)
- [x] Mobile UX polish (active/tap states, enlarged touch targets, responsive metadata labels)
- [x] CSS custom properties theme system (`--color-accent`, `--color-paper`) with `data-theme` attribute
- [x] Copy buttons on email addresses and code snippets
- [x] Active filter count badge on filter toggle button
- [x] `aria-label` attributes on all icon-only buttons

---

## Phase 3.0 — Future 🔮

**Goal:** Advanced features based on user feedback.

- [x] Graduated body degradation (full → text → preview over time)
- [x] Provider webhook receivers (Resend, SendGrid status callbacks)
- [x] Timezone handling (UTC storage, SEESEE_DISPLAY_TIMEZONE, format-consistent queries)
- [x] Search-and-delete (GDPR right to erasure)
- [x] Data export per recipient (GDPR right of access)
- [x] Admin UX audit — iOS input zoom fix, sortable columns, touch targets, copy buttons, form loading states, tooltips
- [x] Theme selector UI on settings page — 10 themes (4 accent, 3 developer, 1 light, 2 retro) with swatch grid picker
- [x] Expanded theme catalog — 21 themes (4 accent, 8 developer, 4 light, 6 retro) with scoped CSS overrides for Blueprint, VHS, OS 9, Rad
- [x] Edit app settings from the detail page — storage mode + the four retention overrides ("Settings" card)
- [ ] **Management API keys + MCP server (0.20.0)** — scoped, revocable machine credentials (`ss_mgmt_`) and an MCP server at `/mcp` for provisioning + email debugging. Unified `api_keys` table (schema v4) also fixes today's destructive key rotation by allowing multiple keys per app. Spec: `docs/superpowers/specs/2026-07-26-management-keys-mcp-design.md`
- [ ] CSV/JSON search export
- [ ] Per-app "disable degradation" override — needs a design decision: the retention engine treats a per-app `0`/NULL as "inherit global", so an app cannot opt out of a globally enabled degradation schedule (see NEXT.md Known Issues)
- [x] ✅ CSRF protection for session-authenticated UI form POSTs (settings, rename, purge, key rotation) — acceptable for single-admin self-hosted use today; required before multi-user auth lands (shipped in 0.20.0 cycle — CSRF tokens on all session POST handlers)
- [ ] Prometheus metrics endpoint
- [ ] Multi-user auth with roles
- [ ] WordPress plugin with settings page
- [ ] Postgres support as alternative to SQLite
- [ ] STARTTLS support for SMTP ingest
- [ ] Notification alerts ("App X hasn't sent email in 24 hours")
