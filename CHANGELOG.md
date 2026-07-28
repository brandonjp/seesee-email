# Changelog

All notable changes to SeeSee will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

> The `-dev` labels below are the **post-0.20.0** series and are unrelated to the
> identically-numbered pre-release labels superseded by 0.20.0. `0.20.1-dev` and
> `0.20.2-dev` were reused by accident; the series moved to `0.21.0-dev` to stop
> the collision, which is also the correct bump for a default that changes
> behaviour and a raised dependency floor.

### Added
- `SEESEE_FORWARDED_ALLOW_IPS` — which client IPs may set `X-Forwarded-Proto` / `X-Forwarded-For`, passed through to uvicorn's `forwarded_allow_ips`. Needed because uvicorn's own default of `127.0.0.1` never matches a reverse proxy running in a separate container (Coolify, Compose, Kubernetes all connect from a private network address), so the forwarded scheme was being dropped. Defaults to the private ranges a containerized proxy connects from — see Security below (v0.20.2-dev, default narrowed in v0.21.0-dev)
- A startup `WARNING` when `SEESEE_BASE_URL` is an `http://` URL on a non-local host — the one configuration mistake that has no other visible symptom (v0.20.2-dev)

### Security
- **`SEESEE_FORWARDED_ALLOW_IPS` no longer defaults to `*`.** The default is now the set of private ranges a containerized reverse proxy actually connects from — `127.0.0.0/8,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7`. `*` trusts any client that can open a TCP connection to SeeSee's HTTP port, which on a directly-exposed instance means an attacker can forge `X-Forwarded-For` and dictate what the access log records as the source of every request they send — destroying the audit trail precisely when it would be needed. Nothing in SeeSee's own code reads the client IP, so the blast radius was log integrity rather than an auth or rate-limit bypass, but the private-range default costs nothing on a normal deployment and removes the exposure, so `*` was not worth keeping as a default. Behaviour on Coolify, Docker Compose, and Kubernetes is unchanged: every one of them puts the proxy on one of these ranges. **Set the variable explicitly if your proxy reaches SeeSee from a public address** — nothing in the list will match it, the forwarded scheme will be dropped, and cookies will stay `Secure` only via an `https://` `SEESEE_BASE_URL` (which the existing startup warning nags about). `*` is still accepted for anyone who wants the old behaviour. Two tests cover it: the forwarded-proto test now asserts all three directions (untrusted loopback default → insecure, private proxy under the new default → secure, arbitrary public client → insecure), and a second test parses each entry through uvicorn's own `_TrustedHosts` — a malformed entry there is not an error but a silent fallback to literal string matching that could never match a real address, which would narrow the trust to nothing and un-`Secure` cookies with no symptom (v0.21.0-dev)

### Changed
- **`uvicorn[standard]` floor raised from `>=0.30.0` to `>=0.31.0`.** CIDR notation in `forwarded_allow_ips` only works from 0.31; 0.30.x compares trusted hosts as plain strings, so the new private-range default would have matched nothing and silently reintroduced the insecure-cookie bug it exists to prevent (v0.21.0-dev)

### Fixed
- **`Secure` cookies no longer depend on `SEESEE_BASE_URL` being set.** The 0.20.0 fix derived the flag from `base_url` alone, and `base_url` defaults to `http://localhost:8080` — so an operator who deployed behind HTTPS without setting it got insecure cookies, with no error and no visible symptom to notice. `cookies_are_secure()` now takes the `Request` and returns true if *either* `base_url` is `https://` **or** the request itself arrived over HTTPS, which behind a TLS-terminating proxy means `X-Forwarded-Proto`. Making that work required trusting the proxy — see `SEESEE_FORWARDED_ALLOW_IPS` above; without it `request.url.scheme` stayed `http` behind Coolify and the request-scheme check would itself have been a silent no-op. `base_url` is kept as the first check so the flag stays correct if that trust is ever narrowed, and a startup warning covers the case where it is. Threading the request through also surfaced three handlers that never had one — `logout`, rotate-key, and delete-app — caught by `ruff` rather than at runtime (v0.20.2-dev)
- **The `# noqa: S608` comments marking reviewed f-string SQL suppressed nothing — they were decoration that read as enforcement.** `S608` (flake8-bandit's SQL-injection check) was never in `[tool.ruff.lint] select`, so all 20 of them were inert, and `RUF100` (unused-noqa) was not enabled either, so nothing would ever say so. The consequence had already happened silently: `ruff format` moved one of them off its diagnostic line in `seesee/mcp_server.py` while collapsing a call, and no check noticed. `S608` and `RUF100` are now selected as a pair — the first makes the suppressions real (new f-string SQL has to be acknowledged deliberately), the second fails the build if a `noqa` ever stops matching a real diagnostic, so they cannot rot back into decoration. Enabling `S608` flagged exactly one site, the misplaced comment, which is fixed; the other 19 were already correct. Reviewed all 20 while confirming this: every one interpolates a module-level column constant or a generated `?` placeholder string, never user input (v0.20.1-dev)

---

## [0.20.0] — 2026-07-27

First tagged release. Everything below accumulated under `[Unreleased]` across the
`0.8.0-dev`–`0.20.3-dev` development series and ships here as one version.

### Added
- MCP server at `/mcp` (streamable HTTP): nine provisioning + email-debugging tools, scope-filtered tool list, management-key auth, `SEESEE_MCP_ENABLED` toggle
- Management API keys: scoped (`emails:read`/`apps:read`/`apps:write`/`apps:delete`), labeled, expiring, individually revocable; key CRUD REST endpoints; Keys UI on Settings and app detail; safe two-step rotation
- Unified `api_keys` table (schema v4): multi-key-per-app, management keys (`ss_mgmt_`), scoped credentials, safe rotation over REST and SMTP, CLI bootstrap (`python -m seesee.keys`)
- CSRF tokens on all session-authenticated UI form POSTs (signed with the session secret, bound to the session user; `fetch()` callers send `X-CSRF-Token`)
- `GET /api/v1/emails` now also accepts an app-scoped Bearer API key (in addition to admin auth), hard-scoped to that app's own emails — any `app_id` filter passed by an app key is overridden by its own app ID, so an app can never read another app's emails. Fixes client apps (e.g. SplitGive) that call this endpoint with their `MAIL_SEESEE_API_KEY` to show recent emails in their own dashboards and got 401s because the route was admin-only. New `require_admin_or_app` dependency in `seesee/dependencies.py`; all other email routes remain admin-only
- `GET /api/v1/emails/{id}/preview` now also accepts the admin session cookie (in addition to HTTP Basic), fixing the email-detail page's preview iframe: the iframe request carried the session cookie but no Basic header, so `HTTPBasic` 401'd with a `WWW-Authenticate: Basic` challenge and the browser popped a native login prompt instead of rendering the preview. New `require_admin_or_session` dependency checks the session cookie first, then falls back to Basic, without triggering the browser's native auth prompt for cookie-bearing requests
- Documentation site (seesee.email) now shows the current SeeSee version in the footer on every page, read at build time from `pyproject.toml` via a custom Starlight `Footer` override — no manual updates needed
- Privacy-first, cookieless analytics on the docs site: Umami (self-hosted), OpenPanel (self-hosted), and Swetrix (self-hosted) page-view tracking, injected via Starlight's `head` config per the shared-ai-docs Analytics Playbook. Only public client IDs are embedded; no server-side secrets ship to the browser
- Version number is now visible across the UI: as a small tag beside the "email" label in the desktop sidebar brand, in the mobile top-bar header (where "email" now stays, instead of disappearing), and as a fuller `SeeSee.email • v… / <build timestamp>` footer block above the settings section of the nav
- Image build timestamp baked into the container at build time (CI passes `--build-arg BUILD_TIME`, exposed as `SEESEE_BUILD_TIME` → `settings.build_time`) and rendered in the display timezone; running from source shows "local dev" instead
- New `app_version` and `build_display` Jinja2 globals available to all templates
- Edit an app's storage mode and retention overrides after creation, via a new "Settings" card on the app detail page
- Inline app name editing on app detail page (pencil icon next to the name), backed by a new `POST /apps/{app_id}/rename` UI endpoint
- "Copy all as ENV vars" button on the app credentials alert (post-creation) and the SMTP Settings tab in app detail — copies the complete `.env` block: `MAIL_SEESEE_API_KEY`, the full SMTP connection (host/port/username/password/encryption), base URL, and app identity vars (`MAIL_SEESEE_APP_ID`, `MAIL_SEESEE_APP_URL`, `MAIL_SEESEE_LOG_URL`), grouped under section comments
- Expanded theme catalog — 11 new themes added (Phase 4), bringing the total to 21:
  - Developer: Monokai, Tomorrow Night, Rosé Pine, Catppuccin Mocha, Obsidian
  - Light: Paper, Aqua Classic, Blueprint (with subtle CSS grid background overlay)
  - Retro: Amber Terminal, VHS (with scanline texture), Mac OS 9 (with beveled borders), Rad (with neon glow effects)
  - Special CSS overrides scoped to `[data-theme]` for Blueprint (grid), VHS (scanlines), OS 9 (beveled borders), Rad (neon glow)
  - Theme picker reorganized into logical groups: Accent (4), Developer (8), Light (4), Retro (6)
  - All themes WCAG AA compliant for body text contrast
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
- Mobile UX, theme system foundation, and UI polish (Phase 2.1):
  - CSS custom properties theme system (`--color-accent`, `--color-paper`) with `data-theme` attribute on `<html>` — the mint palette becomes the default theme; future themes only need a new `[data-theme="name"]` CSS block
  - Tailwind config now uses CSS variable-based colors (`accent`, `paper`) instead of hardcoded hex values
  - Renamed all `mint` Tailwind classes to `accent` across all templates for theme-agnostic styling
  - Theme state stored in `localStorage('seesee-theme')` via Alpine.js
  - Active/tap feedback on all interactive elements (`active:` Tailwind classes alongside every `hover:` class) for touch device responsiveness
  - CSS active states for table rows, buttons, and links (scale transform, background color change)
  - Enlarged touch targets on icon-only buttons (`p-2 -m-2` padding pattern) for 44px minimum tap area
  - Copy-to-clipboard buttons on email addresses (From, To, CC, BCC, Reply-To) in email detail view
  - Copy-to-clipboard buttons on all code snippets (integration tabs in app detail, onboarding steps in dashboard), via a new `copyCodeBlock()` JS helper
  - Code copy buttons: always visible on touch devices, hover-to-reveal on pointer devices via `@media (hover: hover)`
  - Active filter count badge on filter toggle button in emails list (shows count when filters active but panel collapsed)
  - Responsive metadata labels in email detail (`w-24 sm:w-40` instead of fixed `w-40`)
  - `aria-label` attributes on all icon-only buttons (sidebar close, hamburger menu, toast dismiss, modal close, copy, rotate key, delete)
- Click-to-copy buttons on credential values — small clipboard icon next to API Key, SMTP Username, SMTP Password, and rotated key values; copies to clipboard on click with checkmark feedback and toast notification
- Data export per recipient — GDPR right of access (Phase 3.0):
  - `GET /api/v1/export?recipient=user@example.com` — export all emails associated with a recipient address (admin auth required)
  - Searches across `to_addresses`, `cc_addresses`, and `bcc_addresses` fields (case-insensitive)
  - Returns email metadata (subject, from, to, cc, bcc, status, provider, ingest_method, logged_at) and body content (body_html, body_text, body_preview)
  - JSON format by default with `ExportResponse` envelope (recipient, total, exported_at, emails)
  - CSV format via `format=csv` query parameter or `Accept: text/csv` header, with `Content-Disposition` attachment header
  - Input validation: requires valid email address (must contain `@`)
  - `ExportEmail` and `ExportResponse` Pydantic models
  - 15 new tests covering export by to/cc/bcc, cross-field matching, no results, auth required, missing/invalid recipient, case-insensitive matching, body content, metadata fields, CSV format (param and Accept header), CSV empty results, exported_at timestamp
- Search-and-delete / GDPR right to erasure (Phase 3.0):
  - `DELETE /api/v1/emails` — bulk delete emails matching search criteria (admin auth required)
  - Accepts same filter parameters as `GET /api/v1/emails`: `q`, `app_id`, `status`, `provider`, `date_from`, `date_to`
  - Returns `{"deleted": N, "message": "Deleted N emails"}` response
  - Safety: requires at least one filter parameter to prevent accidental full-database wipes (returns 422 if no filters)
  - FTS5 index automatically cleaned up via existing delete triggers
  - "Delete matching" button on emails search page when filters are active, with confirmation modal showing count
  - Toast notification on completion with deleted count
  - 11 new tests covering bulk delete by app, status, provider, FTS query, date range, combined filters, empty results, no-filter rejection, auth requirement, and FTS consistency after delete
- Timezone handling architecture — consistent UTC storage and configurable admin display:
  - `SEESEE_DISPLAY_TIMEZONE` env var — IANA timezone string (default: `UTC`) controlling how dates are shown in admin views; does not affect storage or API responses
  - `seesee/timezone.py` helper module — `utc_now_iso()`, `utc_iso()`, `utc_cutoff_iso()`, `format_for_display()`, `get_display_tz()`, `display_day_start_utc()` for consistent timestamp handling
  - `display_dt` Jinja2 filter — server-rendered timestamp fallback in admin templates using the configured display timezone
  - Client-side timezone display — JavaScript shows relative times with tooltips showing both local and UTC times via `Intl.DateTimeFormat`
  - 37 new tests covering timezone helpers, DST transitions, non-hour offset timezones (Asia/Kolkata, Pacific/Chatham), format consistency, and display formatting
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
- Persistence diagnostics — startup logging and admin debug endpoint for diagnosing volume/data loss issues:
  - `GET /api/v1/admin/debug/persistence` — returns database path, size, app/email counts, volume mount status, container hostname, and uptime (admin auth)
  - Startup diagnostics logged on every boot: database state (new vs existing), app/email counts, mount info, with `WARNING` when database appears freshly created
  - `PersistenceDiagnostics` Pydantic response model
  - 2 new tests covering the debug endpoint (happy path + auth requirement)
- App deletion — permanently remove an app and all its emails from both the REST API and admin UI:
  - `DELETE /api/v1/apps/{app_id}` — delete an app and all its emails (admin auth)
  - Delete button (trash icon) in Apps list Actions column with confirmation modal
  - "Delete App" button on app detail page alongside existing Rotate Key and Purge actions
  - Flash alert on Apps page confirming deletion with email count
  - 4 new tests covering app deletion (with emails, without emails, 404, auth required)
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
- Documentation and community files: screenshots (login, dashboard onboarding, settings, app creation modal, keyboard shortcuts) plus placeholders for the ones still missing; GitHub issue templates (bug report, feature request) with structured YAML forms; a pull request template with a testing checklist; `SECURITY.md` with a vulnerability disclosure process; and `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1)
- Docs coverage for previously undocumented API surface: bulk delete (`DELETE /api/v1/emails`), delete app (`DELETE /api/v1/apps/{app_id}`), and the per-app degradation fields (`retention_degrade_to_text_days`, `retention_degrade_to_preview_days`) on create/update app
- Coolify deployment troubleshooting docs — detailed "Data lost after redeploy" section with debug endpoint usage, Storages verification steps, startup log examples, and common volume pitfalls
- Provider Webhooks, GDPR Ready, 21 Themes, and Keyboard Shortcuts feature cards on the landing page; improved docs site CSS (screenshot styling, focus states, smooth scrolling, responsive images)

### Changed
- Unified API key and SMTP password — the API key is now the only credential (used for both API and SMTP auth). The SMTP authenticator validates against the API key directly, and key rotation updates SMTP credentials automatically
- The ENV var block is built server-side from a single source, so SMTP host/port/encryption can no longer drift between the two copy locations
- CI: bumped the remaining Node 20 actions to fully clear the deprecation — `docker/setup-qemu-action` v3→v4, `docker/setup-buildx-action` v3→v4, `docker/login-action` v3→v4, `docker/metadata-action` v5→v6, `docker/build-push-action` v5→v7 (pinned `provenance: false` so the published multi-arch image stays a clean 2-arch manifest), `actions/upload-pages-artifact` v4→v5, and `actions/setup-python` v5→v6. No Node 20 deprecation warnings remain in either workflow
- CI: bumped first-party GitHub Actions off the deprecated Node 20 runtime — `actions/checkout` v4→v5, `actions/setup-node` v4→v5 (and the docs build now uses Node 22), `actions/upload-pages-artifact` v3→v4, `actions/deploy-pages` v4→v5
- CI: the docs deploy workflow now also triggers on changes to its own workflow file and supports manual `workflow_dispatch` runs (useful for redeploying to pick up a version bump made outside `docs/`)
- Docs homepage hero button relabeled from the ambiguous "Get Started" to **"Read the Docs — Quick Start Guide"**, so it clearly reads as the way into the docs; the "View on GitHub" link is unchanged
- Settings card helper text now spells out the override semantics: blank (or 0) inherits the system default, and when both an override and a system default are set, the stricter (smaller) value wins
- Removed the `VOLUME ["/data"]` instruction from the Dockerfile — it creates anonymous volumes that interfere with named volume mounting in orchestrators like Coolify, causing silent data loss on redeploy. Named volumes in `docker-compose.yml` are unaffected
- Updated the Coolify deployment guide: the persistent storage section now clearly states the requirement to verify Coolify Storages configuration, with explicit field values for adding a mount
- `requires-python` relaxed from `>=3.12` to `>=3.11` (no 3.12-only features used)
- Sidebar navigation updated with Settings link and keyboard shortcut hint; dashboard "Emails by App" section and Apps list rows now link to app detail pages; email list table rows include `data-href` for keyboard navigation
- `BatchLogResponse.errors` field now uses structured `BatchLogError` objects (index + error) instead of plain strings
- `app.js` rewritten with toast manager, keyboard shortcuts, relative timestamp utilities, and flash-to-toast bridge
- Replaced the "SS" favicon text with "See" to avoid unintended abbreviation associations
- Internal development versions `0.8.0-dev` through `0.20.3-dev` are superseded by this release; the per-bump `Version bump: X → Y` entries that had accumulated under `[Unreleased]` are consolidated into this line

### Fixed
- **CI's formatting gate broke the build, and `ruff` is now pinned instead of floored.** The dev extra specified `ruff>=0.6.0`, so CI resolved to whatever was current — 0.16.0, which began formatting Python code blocks *inside Markdown files*. `ruff format --check .` therefore failed on six untouched docs files, and because the Docker `build` job declares `needs: test`, the image publish was skipped: a red build for a reason unrelated to any code change. Pinned to `ruff==0.16.0` and reformatted (Markdown code blocks only — no Python source changed), so local and CI agree byte-for-byte. This was the second time an unpinned formatter blocked the publish; the pin is the durable fix, and bumping it is now a deliberate act with reformatting in the same commit (v0.21.0-dev)
- **Session and flash cookies are now marked `Secure` on HTTPS deployments.** Both previously set `HttpOnly` + `SameSite=Lax` but not `Secure`, so they were transmitted in the clear over plain HTTP. This mattered most for the flash cookie, which briefly carries a **plaintext API key** on the redirect after minting one. The flag is derived from `SEESEE_BASE_URL` rather than a new setting — the two can never sensibly disagree, and hard-coding `Secure` would silently lock the admin out of any HTTP-only install (localhost, LAN) because the browser drops the cookie. No configuration change needed: an `https://` base URL gets secure cookies automatically (v0.20.2-dev)
- **Search crashed with a 500 on ordinary input — including any email address.** SQLite FTS5 treats the `MATCH` operand as a query *language*, not a literal string, so `user@example.com`, a stray `"`, or a lone `(` raised `sqlite3.OperationalError` straight out of the route. This hit `GET /api/v1/emails`, the `DELETE /api/v1/emails` bulk delete, the `/emails` UI search box, the UI bulk delete, and the new MCP `search_emails` tool. New `seesee/search.py` normalizes every query first: well-formed input (including advanced syntax like `subject:foo`, `foo AND bar`, `reset*`, `"exact phrase"`) is still passed to FTS5 verbatim, malformed input degrades to a quoted-term search, and input with no searchable term at all (`((((`, `***`) matches nothing rather than silently dropping the filter and returning every email. Pre-existing bug, project-wide; found during the 0.20.0 review (v0.20.1-dev)
- Minting an app key from the app-detail UI for a nonexistent app returned a 500 (`sqlite3.IntegrityError` from the foreign key) instead of a 404 — the REST route already checked, the UI handler did not (v0.20.1-dev)
- The MCP `create_app_key` tool surfaced a raw `FOREIGN KEY constraint failed` to the calling agent when given an unknown `app_id`; it now raises an actionable `No app with id …` error, matching the REST route (v0.20.1-dev)
- The MCP auth gate rejected a lowercase `bearer` scheme; per RFC 7235 the auth scheme is case-insensitive (v0.20.1-dev)
- The legacy-key fallback added for the 0.19.x→0.20.0 transition could not rescue the case its own docstring described. `_resolve_legacy_fallback` selected candidate apps *by* `key_prefix`, so an app row with a NULL prefix — exactly the row the v4 backfill records as `''`, and which `resolve_key`'s indexed lookup therefore cannot find — was unreachable, and that app's key would have stopped authenticating after the upgrade. It now also matches NULL/empty prefixes, and heals both the `api_keys` and `apps` rows to the real prefix on first use so the slow path runs at most once per app. Latent rather than live (every insert path has populated `apps.key_prefix` since Phase 1.0), but the transition safety net now covers what it claims to. Also added the first tests asserting a pre-0.20.0 key still authenticates over both REST and SMTP after the migration (v0.20.1-dev)
- `POST /logout` did not verify the CSRF token its own form had been shipping since the CSRF work landed. It is now checked when a session is present, and skipped when there is none — a forged logout against an already-unauthenticated visitor achieves nothing, and 403-ing would strand a user whose session expired behind a logout button that no longer worked (v0.20.1-dev)
- **CI (and therefore the Docker image publish) was blocked by a formatting failure.** `tests/test_email_detail.py` had been committed without running the formatter, so the `Format check` step (`ruff format --check .`) exited non-zero, failing the `test` job. Because the `build` job declares `needs: test`, the Docker image build/push was skipped entirely — a green-looking deploy that never rebuilt the image. Reformatted the file (a call that fits within the configured `line-length = 100` was collapsed to one line); `ruff format --check .` now passes clean (v0.19.16-dev)
- **Runtime version was stale in the app UI.** `seesee/__init__.py` (`__version__`, which drives the FastAPI docs, the `/health` payload, and the web UI sidebar/footer) was left at `0.19.12-dev` while `pyproject.toml` had advanced to `0.19.14-dev` — so the running app reported a two-bump-old version. Resynced both and added `tests/test_version_sync.py`, which asserts `seesee.__version__` equals the `pyproject.toml` version so this drift fails CI in the future (v0.19.15-dev)
- **SMTP ingest was completely broken since inception — no email was ever accepted over SMTP.** The server replied `235 Authentication successful` to *any* credentials (valid or bogus) but never actually authenticated the session, so every subsequent `MAIL FROM` was rejected with `530 5.7.0 Authentication required`. Root cause: `SmtpAuthenticator.__call__` was declared `async def`, but aiosmtpd (1.4.6) invokes the authenticator synchronously without awaiting it — the un-awaited coroutine object fell into aiosmtpd's legacy "truthy result = success" branch, so the DB lookup and bcrypt check never ran and `session.authenticated`/`session.app` were never set. The authenticator is now a plain synchronous callable using stdlib `sqlite3`. Added wire-level integration tests (`tests/test_smtp_integration.py`) that drive a real aiosmtpd `Controller` with a real `smtplib` client through `AUTH` → `MAIL` → `RCPT` → `DATA` — the previous unit tests manually awaited the authenticator and therefore masked the bug (v0.19.13-dev)
- OpenPanel analytics on the docs site now actually record page views. OpenPanel is self-hosted (`api.openpanel.bpf.fyi`, like Umami and Swetrix), but the init call omitted `apiUrl`, so `op1.js` posted events to OpenPanel cloud (`api.openpanel.dev`), which returned `401 "Invalid client id"` (the client only exists on the self-hosted instance). Added `apiUrl: 'https://api.openpanel.bpf.fyi'` per shared-ai-docs Analytics Playbook §7; Umami and Swetrix were unaffected
- Docs site favicon 404: Starlight auto-injects `<link rel="icon" href="/favicon.svg">`, but no `docs/public/favicon.svg` existed. Added one (the SeeSee "See" mark) so `/favicon.svg` resolves instead of returning 404
- CI test failures under Starlette 1.x that blocked Docker image publishing since March — all `TemplateResponse` calls now use the modern `TemplateResponse(request, name, context)` signature; the old `(name, {"request": ...})` form was removed in Starlette 1.0 and crashed every UI page render with `TypeError: unhashable type: 'dict'` (v0.19.5-dev)
- Retention overrides of `0` submitted via the settings UI are now stored as "system default" (NULL) — the retention engine already treated `0` and unset identically, but the read view displayed a literal `0`, implying it did something; legacy `0` values stored via the API also render as "System default" now
- `POST /api/v1/log` with no `Authorization` header now returns **401 Unauthorized** (was 403 Forbidden) — changed `HTTPBearer` to `auto_error=False` and added an explicit 401 raise in `get_current_app` when credentials are absent
- `get_current_app` credentials annotation now uses `HTTPAuthorizationCredentials | None` instead of `Optional[...]` — the project's ruff config enables `UP` rules and the `Optional[]` form failed `ruff check` (`UP045`), which the dev guide requires to pass before merge
- Consolidated the `VALID_BODY_STORAGE_MODES` constant into `seesee/helpers.py` — the app-create and app-settings UI handlers now validate against a single source instead of three duplicated inline copies that could silently drift apart
- App detail edit forms (Settings, rename) no longer briefly flash open before Alpine.js initializes — added the missing `[x-cloak]` CSS rule to `base.html`
- `MAIL_SEESEE_SMTP_ENCRYPTION` in the copied ENV block now emits `null` (no encryption) instead of `STARTTLS` — the SMTP ingest server (aiosmtpd) does not speak TLS; TLS is terminated by a reverse proxy, so a copied `STARTTLS` value would have caused client connection failures
- Theme picker not applying selected theme — `$root.getAttribute('data-theme')` returned null (Alpine's `$root` scopes to current component, not `<html>`); replaced with `localStorage` read and `$dispatch` event for cross-component communication
- Accent-background buttons (Add App, Search, Login, etc.) invisible on dark-accent themes (Win95, Obsidian, Indigo, Rose, VHS, Rad, etc.) — added `--color-accent-contrast` CSS variable per theme, replaced hardcoded `text-gray-900` with `text-accent-contrast` on all solid `bg-accent` elements
- iOS Safari auto-zoom on form focus — CSS rule enforces 16px minimum font-size on all input/select/textarea elements via `@media screen and (-webkit-min-device-pixel-ratio: 0)`
- Mobile touch targets below 44px — CSS `@media (pointer: coarse)` rule sets `min-height: 44px` on buttons and interactive elements; sidebar hamburger and close buttons increased from `p-1` to `p-2.5`
- Timestamp comparison bug — replaced all SQLite `datetime('now', ...)` calls with Python-computed UTC parameters; the format mismatch (SQLite's space separator vs Python's `T` separator) caused incorrect lexicographic comparisons in time-window queries (dashboard stats, retention cleanup)
- Standardized all timestamp storage to `YYYY-MM-DDTHH:MM:SS` format (no microseconds, no offset suffix) across API ingest, SMTP ingest, app creation, and retention cleanup for consistent cross-query comparisons
- Version numbers were out of sync across `pyproject.toml`, `seesee/__init__.py`, and the docs during the 0.18.x series — all realigned
- Docs corrections: the health endpoint response showed `"healthy"` instead of the actual `"ok"` status value and a stale `"0.6.0-dev"` version; the Contributing page was missing routes (`export.py`, `webhooks.py`, `admin.py`) from the project structure; and the Privacy page's "No CDN" claim contradicted the Tailwind/Alpine CDN loads
- Docs and compose gaps for `SEESEE_DISPLAY_TIMEZONE` — added to the docs-site configuration reference (UI table and example `.env` block) and to the `docker-compose.yml` environment section; marked search-and-delete complete in the `dev.md` Phase 3.0 checklist

### Removed
- SMTP relay feature — SeeSee no longer forwards emails to upstream SMTP servers. The SMTP ingest remains as a capture-only feature, consistent with SeeSee's core principle of being a log viewer, not a mail server. Removed the `aiosmtplib` dependency, all `SEESEE_SMTP_RELAY_*` configuration variables, and the `_relay_message()` function. SMTP ingest (capture-only) continues to work as before
- Separate SMTP password — replaced by the unified API key; the `generate_smtp_password()` utility and the `smtp_password` field on `AppCreateResponse` are gone

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
