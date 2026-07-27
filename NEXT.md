# Next Steps — SeeSee

**Version:** 0.19.16-dev
**Updated:** 2026-07-27

## Just Completed

- **Release-prep review** (v0.19.15-dev):
  - Fixed a runtime version drift: `seesee/__init__.py` was stuck at `0.19.12-dev` while `pyproject.toml` had moved to `0.19.14-dev`, so the app UI, `/health`, and FastAPI docs all showed a stale version. Resynced both to `0.19.15-dev`
  - Added `tests/test_version_sync.py` — asserts `seesee.__version__` matches the `pyproject.toml` version so this recurring drift now fails CI
  - Merged a duplicate `### Changed` heading under CHANGELOG `[Unreleased]`
  - Follow-up noted below: the CHANGELOG `[Unreleased]` block has accumulated several un-released batches and needs a one-time consolidation + cut into a versioned release section

- **App-scoped Bearer keys on `GET /api/v1/emails` + preview 401 fix** (v0.19.14-dev):
  - The email-list route was admin-only, so client apps (e.g. SplitGive) calling it with their app API key always 401'd. New `require_admin_or_app` dependency: admin auth still sees everything; an app Bearer key is hard-scoped to its own `app_id` regardless of any `app_id` filter passed
  - The email-detail preview iframe authenticated via session cookie but hit a Basic-only dependency, triggering the browser's native auth prompt. New `require_admin_or_session` checks the cookie first, then falls back to Basic without early-erroring on a missing Basic header

- **SMTP AUTH fixed — SMTP ingest worked for the first time** (v0.19.13-dev):
  - `SmtpAuthenticator.__call__` was `async def`, but aiosmtpd 1.4.6 invokes the authenticator synchronously without awaiting it — the un-awaited coroutine was treated as a successful login, so the credential check never ran and every `MAIL FROM` was then rejected with `530`. Net effect: zero emails ever ingested via SMTP. Rewrote the authenticator as a plain sync callable using stdlib `sqlite3`
  - Added wire-level integration tests (`tests/test_smtp_integration.py`) driving a real `Controller` + `smtplib` client through `AUTH → MAIL → RCPT → DATA`, plus a guard test asserting the authenticator is not a coroutine function

- **Docs site + CI + version-display polish** (v0.19.5-dev → v0.19.12-dev):
  - Migrated `TemplateResponse` calls to the Starlette 1.x signature — this had been crashing every UI page render and blocking Docker image publishing since March
  - App version now surfaced across the UI (sidebar tag, mobile header, build-time footer block with image build timestamp)
  - Docs site: version in footer (read from `pyproject.toml` at build time), single clearer hero CTA, privacy-first self-hosted analytics (Umami/OpenPanel/Swetrix), favicon
  - CI: moved all GitHub Actions and Docker actions off the deprecated Node 20 runtime; added `workflow_dispatch` + self-path trigger to docs deploy

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

### Management API Keys + MCP Server (0.20.0) — READY TO LAUNCH (Ralph plans written)

Design spec: `docs/superpowers/specs/2026-07-26-management-keys-mcp-design.md` (branch `feature/management-keys-mcp`). Read the spec first — it is the source of truth; this is a pointer, not a summary.

Gives agents/automation a scoped, revocable credential for managing an instance, and exposes provisioning + email debugging over MCP. Unified `api_keys` table (schema v4) covering both app and management keys, five-scope vocabulary, multi-key-per-app (fixes today's destructive rotate), `/mcp` server, key management UI, CSRF on session POSTs.

**Status (2026-07-27):** All required review edits applied to the design spec — B1 (`require_scope` never reads session cookies), B2 (legacy-column dual-write/tombstone policy, §1a), B3 (kind/scope validity matrix + belongs-to-app revoke), B4 (MCP rejects app-bound principals normatively, per-request resolution), B5 (sync/async resolver split for SMTP), N1 (regression bar restated: whole suite + frozen files + per-spec test-change budgets), N2 (`SCHEMA_SQL` gains `api_keys`; single INSERT…SELECT backfill). Adopted recommendations: CSRF hoisted to its own spec run first, `created_by` provenance column, 90-day UI expiry default, lazy legacy fallback (N3), `TOOL_SCOPES` single source of truth (N5), guarded `last_used_at` UPDATE (N6), pre-SDK auth middleware + both-occurrence redaction (N8).

Both launch hazards are resolved:
- `tests/test_smtp_integration.py` verified stable in isolation: 3 consecutive clean runs (~1.4s each) on 2026-07-27.
- The `mcp` SDK surface was verified against installed `mcp==1.26.0` by a running end-to-end experiment (mount, lifespan, stateless auth, contextvar propagation, scope-filtered `tools/list`, trailing-slash behavior, once-per-instance `session_manager.run()`). The verified facts are prescriptive in design §6 and baked into Ralph sub-plan 4.

Four sequential Ralph sub-plans, one shared branch (`feature/management-keys-mcp`), one runner invocation — queued in `~/.ralph-queue/queue-2026-07-27.sh`:

1. `docs/plan-mgmt-keys-1-csrf.md` — CSRF tokens on all session POST handlers (lands first so key forms are born protected).
2. `docs/plan-mgmt-keys-2-foundation.md` — schema v4, `seesee/keys.py`, migration + backfill, REST/SMTP auth rewire, dual-write policy, CLI bootstrap.
3. `docs/plan-mgmt-keys-3-rest-ui.md` — `require_scope`, scope-mapped app routes, key CRUD endpoints, Keys UI (Settings + app detail).
4. `docs/plan-mgmt-keys-4-mcp.md` — `/mcp` mount per the verified SDK surface, auth middleware, the nine tools, docs-site page, bump to 0.20.0-dev.

After all four complete: cut the `0.20.0` release manually — that's when the CHANGELOG `[Unreleased]` one-time consolidation (see Known Issues) happens, deliberately, not inside a loop.

### CSV/JSON Search Export

Add export buttons to the email search page that download the current filtered results as CSV or JSON files. (Deprioritized below the 0.20.0 work above.)

## Other Candidates (from ROADMAP Phase 3.0)

- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Known Issues

- **Per-app degradation cannot be disabled when a global default is set.** (Also on ROADMAP Phase 3.0 — needs a human design decision.) `_effective_degrade_days` (`seesee/retention.py:162`) treats a per-app value of `0` (or `NULL`) as "inherit global". So if `settings.retention_degrade_to_text_days` is non-zero, there is no way to turn degradation off for a single app — `0`/blank falls back to the global. As of v0.19.4-dev the Settings UI stores `0` as NULL and shows "System default", so it at least no longer *implies* that `0` disables anything — but an explicit "disabled" state (sentinel value, separate column, or checkbox) still needs to be designed before per-app opt-out can work as a user would expect.
- **No CSRF protection on UI form POSTs.** (Also on ROADMAP Phase 3.0.) `/apps/{id}/settings`, `/rename`, `/purge`, and key rotation are session-cookie-authenticated POSTs with no CSRF token. Pre-existing and project-wide — the new settings endpoint follows the existing pattern. Acceptable for a single-admin self-hosted tool, but must be addressed before multi-user auth lands. **Severity rises with the 0.20.0 management-keys work:** once a key-creation form exists, a forged POST mints a durable attacker-known credential that survives a password change and is invisible until someone reads the key list. CSRF is therefore in scope for 0.20.0 (Ralph spec 2), not deferred.
- **CHANGELOG `[Unreleased]` needs a one-time consolidation.** The `[Unreleased]` section has accumulated several separately-prepended batches, leaving repeated `### Added`/`### Fixed`/`### Removed` subheadings and a stray `### Previously` group (all pre-dating the recent work). Before the next tagged release, consolidate `[Unreleased]` into a single Added/Changed/Fixed/Removed set and cut it into a versioned section. Low risk but should be a deliberate, careful edit — not folded into an unrelated change.

## Resolved (previously listed here)

- ~~**Retention value of `0` displays literally.**~~ Fixed in v0.19.4-dev: the settings UI stores `0` as NULL, and the read view treats `0` (e.g. legacy API-stored values) as "System default".

## Current State

- 295 tests passing (0 failures)
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
