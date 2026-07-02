# Next Steps — SeeSee

**Version:** 0.19.4-dev
**Updated:** 2026-07-01

## Just Completed

- **Pre-release review polish for edit-app-settings** (v0.19.4-dev):
  - Retention overrides of `0` submitted via the Settings card are now stored as NULL — the retention engine already treated `0` and unset identically, but the read view showed a literal `0`; legacy API-stored `0` values also render as "System default" now (resolves the "retention value of 0 displays literally" known issue)
  - Settings card helper text now explains override semantics: blank (or 0) inherits the system default, and when both an override and a system default are set, the stricter (smaller) value wins (`_effective_limit` clamps with `min(app, global)`, so an override can never *extend* retention past the global cap)
  - Consolidated the stacked per-bump CHANGELOG headings under `[Unreleased]` into one Added/Fixed/Changed set for the 0.19.x work
  - Added the two open follow-ups (per-app degradation disable, CSRF) to ROADMAP Phase 3.0 so they're visible outside this file

- **Review fix: ruff `UP045` on `get_current_app`** (v0.19.3-dev):
  - The 401 fix annotated `credentials` as `Optional[HTTPAuthorizationCredentials]`; the project's ruff config enables `UP` rules so this failed `ruff check` — switched to `HTTPAuthorizationCredentials | None`

- **Return 401 (not 403) when the `Authorization` header is missing** (v0.19.2-dev):
  - `HTTPBearer` set to `auto_error=False`; `get_current_app` raises an explicit 401 with `WWW-Authenticate: Bearer` when credentials are absent

- **Code review fixes for edit-app-settings** (v0.19.1-dev):
  - Consolidated `VALID_BODY_STORAGE_MODES` into `seesee/helpers.py` — was duplicated inline in three places (`apps.py` constant, `create_app_ui`, `update_app_settings_ui`); all now import the single source
  - Added the missing `[x-cloak]` CSS rule to `base.html` so the Settings/rename edit forms no longer flash open on page load

- **Edit app settings from the detail page** (v0.19.0-dev):
  - New "Settings" card on `/apps/{id}` with a view/edit toggle for `body_storage_mode` and the four retention overrides
  - New `POST /apps/{app_id}/settings` UI handler; empty retention fields clear the override to the system default
  - Detail GET now fetches all four retention columns; edit form shows global defaults as placeholder hints

- **"Copy ENV Vars" — complete block, both locations** (v0.18.4-dev):
  - Both copy locations now emit the full var block: API key, full SMTP connection (host/port/username/password/encryption), base URL, and app identity vars (`MAIL_SEESEE_APP_ID`, `MAIL_SEESEE_APP_URL`, `MAIL_SEESEE_LOG_URL`)
  - Section comments group the block (`# SeeSee API`, `# SMTP connection`, `# Base URL`, `# App identity`)
  - Location 1 (post-creation alert in `/apps`) uses real values; Location 2 (SMTP Settings tab in `/apps/{id}`) uses the `ss_YOUR_API_KEY` placeholder
  - Block is built server-side in `_build_env_vars()` — single source of truth for SMTP host/port/encryption, no drift between the two locations
  - Clipboard string rendered via Jinja `|tojson` for safe JS embedding; 3 new tests
  - Review fix: `MAIL_SEESEE_SMTP_ENCRYPTION` emits `null` (not `STARTTLS`) — aiosmtpd has no TLS; aligns with PR #36 which corrected the SMTP Settings tab to show "none"
  - Review fix: realigned version numbers across `pyproject.toml`, `seesee/__init__.py`, and docs (were drifted to 0.18.1/0.18.2-dev)

- **Expanded theme catalog** (Phase 4):
  - 21 total themes (up from 10): 4 accent, 8 developer, 4 light, 6 retro
  - New developer themes: Monokai, Tomorrow Night, Rosé Pine, Catppuccin Mocha, Obsidian
  - New light themes: Paper, Aqua Classic, Blueprint (with CSS grid overlay)
  - New retro themes: Amber Terminal, VHS (scanlines), Mac OS 9 (beveled borders), Rad (neon glow)
  - Scoped CSS overrides for Blueprint, VHS, OS 9, and Rad — zero bleed between themes
  - Theme picker reorganized: Accent → Developer → Light → Retro

## Highest Priority Next Task

### CSV/JSON Search Export

Add export buttons to the email search page that download the current filtered results as CSV or JSON files.

## Other Candidates (from ROADMAP Phase 3.0)

- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Known Issues

- **Per-app degradation cannot be disabled when a global default is set.** (Also on ROADMAP Phase 3.0 — needs a human design decision.) `_effective_degrade_days` (`seesee/retention.py:162`) treats a per-app value of `0` (or `NULL`) as "inherit global". So if `settings.retention_degrade_to_text_days` is non-zero, there is no way to turn degradation off for a single app — `0`/blank falls back to the global. As of v0.19.4-dev the Settings UI stores `0` as NULL and shows "System default", so it at least no longer *implies* that `0` disables anything — but an explicit "disabled" state (sentinel value, separate column, or checkbox) still needs to be designed before per-app opt-out can work as a user would expect.
- **No CSRF protection on UI form POSTs.** (Also on ROADMAP Phase 3.0.) `/apps/{id}/settings`, `/rename`, `/purge`, and key rotation are session-cookie-authenticated POSTs with no CSRF token. Pre-existing and project-wide — the new settings endpoint follows the existing pattern. Acceptable for a single-admin self-hosted tool, but must be addressed before multi-user auth lands.

## Resolved (previously listed here)

- ~~**Retention value of `0` displays literally.**~~ Fixed in v0.19.4-dev: the settings UI stores `0` as NULL, and the read view treats `0` (e.g. legacy API-stored values) as "System default".

## Current State

- 282 tests passing (0 failures)
- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, search-and-delete, data export per recipient, admin UX audit, theme selector UI, expanded theme catalog, and complete copy-all-as-ENV-vars on app credentials
- Full REST API, SMTP ingest, Web UI, retention, docs site
- 21-theme color system with swatch picker on Settings page (4 accent, 8 developer, 4 light, 6 retro)
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Timezone architecture: UTC storage, configurable display, format-consistent queries
- Search-and-delete: GDPR erasure via bulk delete with filters
- Data export per recipient: GDPR right of access via JSON/CSV export
- Admin UX audit: iOS zoom fix, sortable columns, touch targets, copy buttons, loading states, tooltips
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
