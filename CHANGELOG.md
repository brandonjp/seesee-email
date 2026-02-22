# Changelog

All notable changes to SeeSee will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Theme selector UI on settings page with 10 color themes (Phase 3.0):
  - Theme picker grid with two-tone color swatches, active checkmark indicator, and instant live preview
  - 4 accent themes: Mint (default), Indigo, Rose, Amber
  - 3 developer themes: Nord, Gruvbox, Dracula
  - 1 light theme: Solarized Light
  - 2 retro themes: Terminal (green phosphor CRT), Windows 95 (teal/silver/navy with flat corners and beveled borders)
  - Each theme defines `--color-accent` and `--color-paper` CSS custom properties; full palette specs noted in comments for future expansion
  - Win95 theme includes scoped overrides: `border-radius: 0 !important` and outset borders on cards/buttons
  - Hooks into existing Alpine.js theme state and `localStorage('seesee-theme')` persistence
  - Responsive grid (3 columns mobile, 5 columns desktop) with 44px+ touch targets

### Changed
- Version bump: 0.16.0-dev → 0.17.0-dev

### Added
- Admin UX audit fixes (12 issues across 7 files):
  - Clickable sort column headers on email list — Subject and Date columns are links that toggle sort direction, with chevron indicators on the active sort column; sort state preserved across pagination
  - Copy-to-clipboard buttons on email metadata tab (Provider, Provider Message ID)
  - Copy-to-clipboard buttons on SMTP settings in app detail (Host, Port, Username, Encryption)
  - Copy-to-clipboard buttons on HTML Source and Plain Text body tabs in email detail
  - Email ID display with copy button in email detail header
  - "View emails" link on app detail Total Emails stat card (links to `/emails?app_id=...`)
  - Loading/spinner states on login form and app creation form (disables button, shows spinner)
  - Required field asterisk (`*`) on App Name field in creation modal
  - `title` tooltips on truncated table cells (Subject, From, To in emails; Name, Slug, Storage in apps)
  - Search input changed to `type="search"` for native clear button and search keyboard action

### Fixed
- iOS Safari auto-zoom on form focus — CSS rule enforces 16px minimum font-size on all input/select/textarea elements via `@media screen and (-webkit-min-device-pixel-ratio: 0)`
- Mobile touch targets below 44px — CSS `@media (pointer: coarse)` rule sets `min-height: 44px` on buttons and interactive elements; sidebar hamburger and close buttons increased from `p-1` to `p-2.5`

### Changed
- Version bump: 0.15.0-dev → 0.16.0-dev

### Added
- Mobile UX, theme system foundation, and UI polish (Phase 2.1):
  - CSS custom properties theme system (`--color-accent`, `--color-paper`) with `data-theme` attribute on `<html>` — current mint palette becomes the default theme; future themes only need a new `[data-theme="name"]` CSS block
  - Tailwind config now uses CSS variable-based colors (`accent`, `paper`) instead of hardcoded hex values
  - Renamed all `mint` Tailwind classes to `accent` across all templates for theme-agnostic styling
  - Theme state stored in `localStorage('seesee-theme')` via Alpine.js, ready for future settings page selector
  - Active/tap feedback on all interactive elements (`active:` Tailwind classes alongside every `hover:` class) for touch device responsiveness
  - CSS active states for table rows, buttons, and links (scale transform, background color change)
  - Enlarged touch targets on icon-only buttons (`p-2 -m-2` padding pattern) for 44px minimum tap area
  - Copy-to-clipboard buttons on email addresses (From, To, CC, BCC, Reply-To) in email detail view
  - Copy-to-clipboard buttons on all code snippets (integration tabs in app detail, onboarding steps in dashboard)
  - `copyCodeBlock()` JS helper for code block copy buttons
  - Code copy buttons: always visible on touch devices, hover-to-reveal on pointer devices via `@media (hover: hover)`
  - Active filter count badge on filter toggle button in emails list (shows count when filters active but panel collapsed)
  - Responsive metadata labels in email detail (`w-24 sm:w-40` instead of fixed `w-40`)
  - `aria-label` attributes on all icon-only buttons (sidebar close, hamburger menu, toast dismiss, modal close, copy, rotate key, delete)

### Changed
- Version bump: 0.14.0-dev → 0.15.0-dev

### Added
- Data export per recipient — GDPR right of access (Phase 3.0):
  - `GET /api/v1/export?recipient=user@example.com` — export all emails associated with a recipient address (admin auth required)
  - Searches across `to_addresses`, `cc_addresses`, and `bcc_addresses` fields (case-insensitive)
  - Returns email metadata (subject, from, to, cc, bcc, status, provider, ingest_method, logged_at) and body content (body_html, body_text, body_preview)
  - JSON format by default with `ExportResponse` envelope (recipient, total, exported_at, emails)
  - CSV format via `format=csv` query parameter or `Accept: text/csv` header, with `Content-Disposition` attachment header
  - Input validation: requires valid email address (must contain `@`)
  - `ExportEmail` and `ExportResponse` Pydantic models
  - 15 new tests covering: export by to/cc/bcc, cross-field matching, no results, auth required, missing/invalid recipient, case-insensitive matching, body content, metadata fields, CSV format (param and Accept header), CSV empty results, exported_at timestamp
  - 272 total tests passing

### Changed
- Version bump: 0.13.1-dev → 0.14.0-dev

### Fixed
- Added `SEESEE_DISPLAY_TIMEZONE` to docs site configuration reference (was missing from the UI table and example `.env` block)
- Added `SEESEE_DISPLAY_TIMEZONE` to `docker-compose.yml` environment section
- Marked search-and-delete as completed in dev.md Phase 3.0 checklist

### Changed
- Version bump: 0.13.0-dev → 0.13.1-dev

### Added
- Search-and-delete / GDPR right to erasure (Phase 3.0):
  - `DELETE /api/v1/emails` — bulk delete emails matching search criteria (admin auth required)
  - Accepts same filter parameters as `GET /api/v1/emails`: `q`, `app_id`, `status`, `provider`, `date_from`, `date_to`
  - Returns `{"deleted": N, "message": "Deleted N emails"}` response
  - Safety: requires at least one filter parameter to prevent accidental full-database wipes (returns 422 if no filters)
  - FTS5 index automatically cleaned up via existing delete triggers
  - "Delete matching" button on emails search page when filters are active, with confirmation modal showing count
  - Toast notification on completion with deleted count
  - 11 new tests covering bulk delete by app, status, provider, FTS query, date range, combined filters, empty results, no-filter rejection, auth requirement, and FTS consistency after delete
  - 257 total tests passing

### Changed
- Version bump: 0.12.0-dev → 0.13.0-dev

### Added
- Timezone handling architecture — consistent UTC storage and configurable admin display:
  - `SEESEE_DISPLAY_TIMEZONE` env var — IANA timezone string (default: `UTC`) controlling how dates are shown in admin views; does not affect storage or API responses
  - `seesee/timezone.py` helper module — `utc_now_iso()`, `utc_iso()`, `utc_cutoff_iso()`, `format_for_display()`, `get_display_tz()`, `display_day_start_utc()` for consistent timestamp handling
  - `display_dt` Jinja2 filter — server-rendered timestamp fallback in admin templates using the configured display timezone
  - Client-side timezone display — JavaScript shows relative times with tooltips showing both local and UTC times via `Intl.DateTimeFormat`
  - 37 new tests covering timezone helpers, DST transitions, non-hour offset timezones (Asia/Kolkata, Pacific/Chatham), format consistency, and display formatting

### Fixed
- Timestamp comparison bug — replaced all SQLite `datetime('now', ...)` calls with Python-computed UTC parameters; the format mismatch (SQLite's space separator vs Python's `T` separator) caused incorrect lexicographic comparisons in time-window queries (dashboard stats, retention cleanup)
- Standardized all timestamp storage to `YYYY-MM-DDTHH:MM:SS` format (no microseconds, no offset suffix) across API ingest, SMTP ingest, app creation, and retention cleanup for consistent cross-query comparisons

### Added
- Graduated body degradation (Phase 3.0) — automatically degrade email body storage over time to save disk space:
  - `full` → `text_only`: strip HTML body after a configurable number of days, preserving text and preview
  - `text_only` → `preview`: strip text body after a configurable number of days, keeping only the preview (first 500 chars)
  - `SEESEE_RETENTION_DEGRADE_TO_TEXT_DAYS` — global threshold for HTML stripping (0 = never, default)
  - `SEESEE_RETENTION_DEGRADE_TO_PREVIEW_DAYS` — global threshold for text stripping (0 = never, default)
  - Per-app overrides via `retention_degrade_to_text_days` and `retention_degrade_to_preview_days` fields on app create/update
  - Runs as part of the existing retention scheduler cycle — no additional scheduler needed
  - Preserves body_text (generated from HTML if missing) during text degradation
  - Preserves body_preview (generated from text/HTML if missing) during preview degradation
  - Updates `body_size_bytes` to reflect actual stored content after degradation
  - FTS5 search index automatically updated via existing triggers
  - Opt-in and non-destructive: disabled by default (0 = never degrade)
  - `body_degraded_at` audit timestamp on emails — records when degradation occurred
  - Database schema migrations (v1 → v2 → v3) add per-app override columns and audit timestamp
  - 26 new tests covering degradation logic, thresholds, per-app overrides, FTS consistency, and body_size accuracy

### Changed
- Version bump: 0.11.0-dev → 0.12.0-dev

### Added
- Click-to-copy buttons on credential values — small clipboard icon next to API Key, SMTP Username, SMTP Password, and rotated key values; copies to clipboard on click with checkmark feedback and toast notification
- Provider webhook receivers — automatically update email delivery status from provider callbacks:
  - `POST /api/v1/webhooks/resend` — receive Resend delivery status webhooks (sent, delivered, bounced, complained, delayed)
  - `POST /api/v1/webhooks/sendgrid` — receive SendGrid event webhooks (delivered, bounced, dropped, deferred, complained)
  - Resend signature verification via Svix HMAC-SHA256 (`SEESEE_WEBHOOK_SECRET_RESEND`)
  - SendGrid token-based verification via URL query parameter (`SEESEE_WEBHOOK_SECRET_SENDGRID`)
  - Automatic email matching by `provider` + `provider_message_id`, with SendGrid `.filter` suffix fallback
  - Webhook secrets optional — skips verification with a logged warning if not configured
  - `WebhookResponse` and `WebhookEventResult` Pydantic response models
  - Database index on `provider_message_id` for efficient webhook event matching
  - 23 new tests covering signature verification, event parsing, status updates, unknown providers, invalid signatures, edge cases
  - 183 total tests passing

### Changed
- Version bump: 0.10.0-dev → 0.11.0-dev

### Added
- Persistence diagnostics — startup logging and admin debug endpoint for diagnosing volume/data loss issues:
  - `GET /api/v1/admin/debug/persistence` — returns database path, size, app/email counts, volume mount status, container hostname, and uptime (admin auth)
  - Startup diagnostics logged on every boot: database state (new vs existing), app/email counts, mount info, with `WARNING` when database appears freshly created
  - `PersistenceDiagnostics` Pydantic response model
  - 2 new tests covering the debug endpoint (happy path + auth requirement)
- Coolify deployment troubleshooting docs — detailed "Data lost after redeploy" section with debug endpoint usage, Storages verification steps, startup log examples, and common volume pitfalls

### Changed
- Removed `VOLUME ["/data"]` instruction from Dockerfile — it creates anonymous volumes that interfere with named volume mounting in orchestrators like Coolify, causing silent data loss on redeploy. Named volumes in docker-compose.yml are unaffected.
- Updated Coolify deployment guide: persistent storage section now clearly states the requirement to verify Coolify Storages configuration, with explicit field values for adding a mount
- Version bump: 0.9.0-dev → 0.10.0-dev

### Added
- App deletion — permanently remove an app and all its emails from both the REST API and admin UI:
  - `DELETE /api/v1/apps/{app_id}` — delete an app and all its emails (admin auth)
  - Delete button (trash icon) in Apps list Actions column with confirmation modal
  - "Delete App" button on app detail page alongside existing Rotate Key and Purge actions
  - Flash alert on Apps page confirming deletion with email count
  - 4 new tests covering app deletion (with emails, without emails, 404, auth required)

### Removed
- SMTP relay feature — SeeSee no longer forwards emails to upstream SMTP servers. The SMTP ingest remains as a capture-only feature, consistent with SeeSee's core principle of being a log viewer, not a mail server. Removed `aiosmtplib` dependency, all `SEESEE_SMTP_RELAY_*` configuration variables, and the `_relay_message()` function. SMTP ingest (capture-only) continues to work as before.

### Added
- Web UI Polish (Phase 1.1 completion + Phase 2.1):
  - App detail page (`GET /apps/{id}`) with email stats, status breakdown, integration snippets (REST, Python, Node.js, PHP, SMTP), rotate key and purge buttons
  - Settings page (`GET /settings`) displaying retention configuration and storage usage, with manual cleanup trigger
  - `POST /api/v1/log/batch` — batch email ingest (max 100 per request), validates each individually, returns logged count and per-item errors
  - `PATCH /api/v1/emails/{id}/status` — update email delivery status after initial logging (admin auth)
  - `DELETE /api/v1/emails/{id}` — delete a single email (admin auth)
  - `DELETE /api/v1/apps/{app_id}/emails` — purge all emails for an app (admin auth)
  - `POST /api/v1/admin/cleanup` — trigger immediate retention cleanup cycle (admin auth)
  - Keyboard shortcuts: `/` focus search, `j`/`k` navigate email list, `Enter` open, `Esc` close/blur, `?` shortcut help modal
  - Toast notification system (Alpine.js) — success (mint) and error (red) variants, auto-dismiss after 4s, wired to app creation, key rotation, cleanup, and delete actions
  - Relative timestamps ("just now", "2 minutes ago", "yesterday") with full ISO on hover, auto-updating every 30s
  - Volume sparkline on dashboard — bar chart of emails per day for last 30 days (inline HTML, no charting library)
  - Enhanced empty state onboarding on dashboard — step-by-step guide with copy-pasteable curl commands
  - Delete button on email detail page with confirmation dialog
  - Purge all button on app detail page with confirmation dialog
  - Settings nav link in sidebar
  - App list rows now link to app detail pages
  - 19 new tests covering batch ingest, status update, email delete, app purge, and admin cleanup
  - Updated REST API reference docs with new endpoints (batch, status, delete, purge, admin cleanup)
- `seesee/routes/admin.py` — new admin router for cleanup and future admin-only endpoints
- `BatchLogRequest`, `BatchLogError`, `StatusUpdateRequest`, `CleanupResponse` Pydantic models

### Changed
- `requires-python` relaxed from `>=3.12` to `>=3.11` (no 3.12-only features used)
- Sidebar navigation updated with Settings link and keyboard shortcut hint
- Dashboard "Emails by App" section now links to app detail pages
- Email list table rows include `data-href` for keyboard navigation
- Apps list table rows are clickable links to app detail pages
- `BatchLogResponse.errors` field now uses structured `BatchLogError` objects (index + error) instead of plain strings
- `app.js` rewritten with toast manager, keyboard shortcuts, relative timestamp utilities, and flash-to-toast bridge
- Version bump: 0.7.0-dev → 0.8.0-dev → 0.9.0-dev

### Security
- App credentials (API key, SMTP username/password) and rotated keys are no longer exposed in URL query parameters; they are now passed via signed, httponly flash cookies that are consumed on the next page load and immediately deleted — prevents leakage via browser history, server logs, and Referer headers

---

## [0.7.0-dev] — 2026-02-14

### Added
- Astro Starlight documentation site (Phase 2.0):
  - Initialized Astro Starlight project in `docs/` with brand color customization (phosphor mint `#32F5C0`)
  - Landing page with architecture diagram, feature highlights, and docker quick start
  - Getting started guide (docker run/compose, create app, log first email, verify)
  - Configuration reference documenting all 19 `SEESEE_*` environment variables grouped by category
  - REST API reference with all endpoints, request/response schemas, and curl examples
  - SMTP ingest guide with setup instructions, Python/PHP/Node.js client examples
  - Docker deployment guide with compose, volumes, health checks, and reverse proxy examples (nginx, Caddy, Traefik)
  - Coolify deployment guide with step-by-step setup, domain/SSL, and persistent storage
  - Integration guides for PHP/WordPress (wp_mail hook), Python, Node.js, and cURL
  - Privacy & compliance page covering body storage modes, retention, and GDPR considerations
  - Contributing page with development setup, code style, testing, and git workflow
  - Sidebar navigation organized into Getting Started, Guides, Reference, and About sections
  - Pagefind-powered full-text search across all documentation pages
  - Verified compatibility with existing `.github/workflows/docs.yml` GitHub Pages deployment

### Changed
- Version bump: 0.6.0-dev → 0.7.0-dev

---

## [0.6.0-dev] — 2026-02-13

### Added
- Retention scheduler and deployment finalization (Phase 1.3):
  - Async background cleanup scheduler using `asyncio.create_task`, runs on configurable interval (default 60 min via `SEESEE_RETENTION_CLEANUP_INTERVAL_MINUTES`)
  - Per-app `max_count` enforcement — keep at most N emails per app, delete oldest by `logged_at`
  - Per-app `max_age_days` enforcement — delete emails older than N days
  - Global `max_storage_mb` enforcement — oldest-first deletion across all apps until under cap
  - Most-restrictive-wins logic — `min(app_override, global)` when per-app override is set
  - Batch deletion (500 at a time) to avoid long-running database locks
  - INFO-level cleanup logging with counts and approximate storage freed
  - Start/stop wired into FastAPI lifespan in `main.py`
  - 23 new tests covering max_count, max_age, storage cap, per-app overrides, most-restrictive-wins, empty database, and FTS5 consistency after retention deletes
- GitHub Actions multi-platform Docker builds (linux/amd64 + linux/arm64) with QEMU, buildx, GHA build cache, and `docker/metadata-action` for tag management

### Changed
- `docker-compose.yml`: added missing retention env vars (`SEESEE_RETENTION_MAX_STORAGE_MB`, `SEESEE_RETENTION_CLEANUP_INTERVAL_MINUTES`, `SEESEE_SMTP_ENABLED`) with variable substitution defaults
- `.env.example`: added descriptive inline comments for retention variables
- Version bump: 0.5.0-dev → 0.6.0-dev

---

## [0.5.0-dev] — 2026-02-13

### Added
- SMTP ingest server (Phase 1.2):
  - `aiosmtpd` listener on configurable port (default 2525), controlled by `SEESEE_SMTP_ENABLED`
  - SMTP AUTH (LOGIN/PLAIN) — authenticates against per-app `smtp_username` + `smtp_password` (bcrypt hashed in `apps` table)
  - MIME message parsing via Python `email` stdlib — extracts subject, from, to, cc, reply-to, text/plain body, text/html body; handles multipart/alternative and multipart/mixed; skips attachments
  - Parsed emails inserted into `emails` table with `ingest_method = 'smtp'`
  - App `body_storage_mode` (full / text_only / preview) enforced on SMTP path, same as REST API
  - Capture-only SMTP ingest (emails are logged but never forwarded)
  - Graceful start/stop wired into FastAPI lifespan in `main.py`
  - 27 new tests covering AUTH, MIME parsing, DB insertion, body storage modes, and capture-only behavior
- `seesee/helpers.py` — shared body storage helpers (`apply_body_storage_mode`, `strip_html_tags`) used by both REST and SMTP ingest paths

### Changed
- Refactored `_apply_body_storage_mode` out of `routes/ingest.py` into `seesee/helpers.py` for reuse
- Version bump: 0.4.0-dev → 0.5.0-dev

---

## [0.4.0-dev] — 2026-02-12

### Added
- Web UI — admin dashboard (Phase 1.1):
  - Session-based authentication via `itsdangerous` signed cookies with configurable expiry
  - `GET /login`, `POST /login` — login page with form validation
  - `POST /logout` — clears session cookie and redirects
  - `require_session` dependency for UI routes — redirects to `/login` if unauthenticated
  - Base layout template with sidebar navigation, dark/light mode toggle (system preference + manual override via Alpine.js, stored in localStorage)
  - Brand styling: phosphor mint `#32F5C0` primary, warm paper `#F6F1E6` background
  - Dashboard page (`GET /`) — stats cards (total, 24h, 7d, 30d), status breakdown, per-app counts, empty state with onboarding
  - Email list page (`GET /emails`) — full-text search, filter dropdowns (app, status, provider), results table, pagination controls
  - Email detail page (`GET /emails/{id}`) — header with status badge, address block, tabbed content (Preview iframe, HTML Source, Plain Text, Metadata)
  - App management page (`GET /apps`) — app list with email counts, "Add App" modal form, credential display after creation, key rotation with confirmation dialog
  - Server-side app creation (`POST /apps`) and key rotation (`POST /apps/{id}/rotate-key`) via session-authenticated UI routes
  - Responsive sidebar (collapsible on mobile, fixed on desktop)
  - All interactivity via Alpine.js CDN (`x-data`, `x-show`, `x-on`, tabs, modals, toggles)
  - All styling via Tailwind CSS CDN (no build step, no npm required)
  - 20 new tests covering login/logout/session expiry, redirect behavior, page rendering, search, empty states, app CRUD
- `SEESEE_SECRET_KEY` config option for signing session cookies (falls back to `SEESEE_ADMIN_PASSWORD`)
- `SEESEE_SESSION_MAX_AGE_DAYS` config option (default: 7 days)

### Changed
- Registered UI router (`ui.router`) in main app
- Static/template paths now use package-relative `__file__` resolution (fixes pytest working directory issues)
- Version bump: 0.3.0-dev → 0.4.0-dev

---

## [0.3.0-dev] — 2026-02-12

### Added
- Core API endpoints (Phase 1.0 — Core API + Storage):
  - `POST /api/v1/apps` — register app (returns API key + SMTP credentials, shown once)
  - `GET /api/v1/apps` — list registered apps (admin auth required)
  - `PATCH /api/v1/apps/{id}` — update app settings (name, body_storage_mode, retention)
  - `POST /api/v1/apps/{id}/rotate-key` — regenerate API key (old key immediately invalidated)
  - `POST /api/v1/log` — log a single email (API key auth, body storage mode enforcement)
  - `GET /api/v1/emails` — list/search emails with FTS5 full-text search, filters (app, status, provider, date range), sorting, and pagination
  - `GET /api/v1/emails/{id}` — full email detail with all fields
  - `GET /api/v1/emails/{id}/preview` — sandboxed HTML preview with Content-Security-Policy headers
  - `GET /api/v1/stats` — dashboard statistics (totals, time windows, breakdowns by status and app)
- API key authentication dependency with O(1) prefix-based lookup
- Admin HTTP Basic Auth for management endpoints
- Body storage mode enforcement (full / text_only / preview) per app
- Body preview generation (first 500 chars, auto-strips HTML when no text provided)
- FTS5 sync triggers for automatic full-text search indexing on email insert/update/delete
- Slug generation utility for app names (unicode-safe, collision-resistant)
- Enhanced health check endpoint with database status probe
- Consistent error response format (`{"error": "...", "detail": "..."}`)
- Pydantic models for app update (`AppUpdateRequest`) and key rotation (`KeyRotateResponse`)
- Comprehensive test suite: 69 tests covering auth, apps, app update, key rotation, ingest, email list/search, email detail, email preview, stats, health, FTS, and storage modes

### Changed
- Registered all Phase 1.0 routers (ingest, apps, emails, stats) in main app
- Static files mount now checks for directory existence before mounting
- Removed deprecated license classifier from pyproject.toml
- Version bump: 0.2.0-dev → 0.3.0-dev

## [0.1.0] - 2026-02-12

### Added
- Project structure and scaffolding
- Development workflow guides (`.claude/commands/dev.md`)
- Project specification (`seesee-spec.md`)
- Dockerfile with multi-stage build, non-root user, health check
- Docker Compose template (Coolify-compatible)
- GitHub Actions workflows (build + docs)
- pyproject.toml with full package config
- Integration examples (PHP/WordPress, Python, Node.js, cURL)
- Test scaffolding with pytest + pytest-asyncio
- SeeSee Python package scaffolding:
  - FastAPI app with health check endpoint
  - pydantic-settings config with SEESEE_* env vars
  - SQLite database schema with FTS5 full-text search
  - Pydantic models for all API request/response types
  - Auth utilities (API key generation, bcrypt hashing)
  - Route stubs for ingest, emails, apps, stats, UI
  - Jinja2 template stubs with Tailwind + Alpine.js base layout
