# Next Steps — SeeSee

**Version:** 0.20.2-dev
**Updated:** 2026-07-27

## Just Completed

- **`Secure` cookies no longer depend on `SEESEE_BASE_URL` being set** (v0.20.2-dev). Closes the gap found reviewing the 0.20.0 cookie fix: the flag came from `base_url` alone, which defaults to `http://localhost:8080`, so deploying behind HTTPS without setting it produced insecure cookies with no error and no symptom. `cookies_are_secure()` now takes the `Request` and is true if *either* `base_url` is `https://` **or** the request arrived over HTTPS.
  - **The request-scheme half needed a second fix to work at all.** `uvicorn.run()` never set `forwarded_allow_ips`, so it used uvicorn's default of `127.0.0.1` — which never matches a reverse proxy in a separate container. Behind Coolify, `X-Forwarded-Proto` was being dropped and `request.url.scheme` stayed `http`, meaning the request-scheme check would itself have been a silent no-op in exactly the deployment it was written for. New `SEESEE_FORWARDED_ALLOW_IPS` (default `*`) plus `proxy_headers=True`; the trust tradeoff is documented in `seesee/config.py` and the docs-site config reference.
  - Verified rather than assumed: `test_forwarded_proto_is_trusted_from_a_containerized_proxy` drives uvicorn's own `ProxyHeadersMiddleware` from a non-loopback client address and asserts **both** directions — cookie insecure with `127.0.0.1`, secure with `*`. A test in `test_version_sync.py` asserts the `uvicorn.run()` kwargs stay wired, since nothing else exercises them.
  - `base_url` is kept as the first check so the flag stays correct if that trust is ever narrowed, and a startup `WARNING` fires when `base_url` is `http://` on a non-local host — the one config mistake with no other visible symptom.
  - Threading the request through surfaced three handlers that never had one (`logout`, rotate-key, delete-app), caught by `ruff` rather than at runtime. 429 tests passing (+6).

- **`S608` + `RUF100` enabled — the `# noqa: S608` comments now actually enforce something** (v0.20.1-dev). They never had: `S608` was not in `select`, so all 20 were inert, and `RUF100` was not enabled either, so nothing would ever report that. The failure had already happened quietly — `ruff format` moved one off its diagnostic line in `seesee/mcp_server.py` while collapsing a call. Both rules are now selected as a pair: `S608` makes the suppressions real, `RUF100` fails the build if a `noqa` ever stops matching a real diagnostic, so this cannot silently rot again. Enabling `S608` flagged exactly one site (the misplaced comment, now fixed); the other 19 were already correct. Confirmed the corrected placement survives `ruff format` — a trailing comment on the f-string line pins the multi-line form. Audited all 20 while doing it: every one interpolates a module-level column constant, a generated `?` placeholder string, or literal `WHERE`/`SET` fragments; every user-supplied value is bound as a `?` parameter. No injection vector found.

- **🎉 0.20.0 released — the project's first tagged version** (2026-07-27). `CHANGELOG.md`'s `[Unreleased]` block, which had accumulated every batch since `0.8.0-dev` with repeated `### Added`/`### Fixed`/`### Removed` headings and a stray `### Previously` group, was consolidated into one Added/Changed/Fixed/Removed/Security set and cut into `## [0.20.0] — 2026-07-27`. Verified item-by-item that nothing was lost: the only deletions were the fourteen `Version bump: X → Y` lines (collapsed into a single line) and three stale `N total tests passing` counts. `pyproject.toml` and `seesee/__init__.py` set to `0.20.0`; tagged `v0.20.0`. The build workflow already triggers on `tags: ['v*']` and carries `type=semver` metadata patterns, so the tag published `ghcr.io/brandonjp/seesee-email:0.20.0` and `:0.20` alongside `latest` — CI run `30311559466` completed **success**.

- **Review of the two post-merge commits** (2026-07-27) — both verified sound; 423 tests, `ruff check` and `ruff format --check` clean at `ruff 0.16.0`. Details:
  - `769d18c` (Secure cookies): coverage is complete — both `set_cookie` sites and all four `delete_cookie` sites carry the flag, and all three `_pop_flash` readers delete the cookie. The 60-second `_FLASH_MAX_AGE` bounds the plaintext-key exposure window. One gap logged under Known Issues (the `SEESEE_BASE_URL` default makes the fix a silent no-op if unset).
  - `07463bb` (ruff pin): the pin genuinely governs CI — `build.yml` runs `pip install -e ".[dev]"` and then bare `ruff` commands, so the dev extra is the resolved version. No dependabot or pre-commit config exists to silently un-pin it. All six markdown diffs are pure line-joining inside fenced code blocks; no prose or content was lost.

- **`ruff` pinned to `==0.16.0`** (v0.20.3-dev) — CI installed an unpinned `ruff>=0.6.0`, resolved to 0.16.0, which started formatting Python code blocks inside Markdown. `ruff format --check .` failed on six untouched docs files and, because the Docker `build` job declares `needs: test`, the image publish was skipped. Second time an unpinned formatter has blocked the publish, so the version is now pinned rather than floored; bump it deliberately and reformat in the same commit. Only Markdown code blocks were reformatted — no Python source changed.

- **Session and flash cookies marked `Secure` on HTTPS deployments** (v0.20.2-dev) — both previously travelled in the clear over plain HTTP, and the flash cookie briefly carries a **plaintext API key** on the redirect after minting one. `cookies_are_secure()` derives the flag from `SEESEE_BASE_URL` rather than adding a setting: an `https://` base URL gets secure cookies automatically, while HTTP-only installs keep working (a hard-coded `Secure` would lock the admin out silently, since the browser just drops the cookie). No config change needed on deploy.

- **Full branch code review before the 0.20.0 release** (v0.20.1-dev) — reviewed all 40 files touched by `feature/management-keys-mcp`. Findings and fixes:
  - **Search 500'd on any email address** (and on a stray `"`, `(`, or `-`). FTS5's `MATCH` operand is a query language, not a literal, so `sqlite3.OperationalError` escaped the route. Affected five call sites: REST list, REST bulk delete, UI search box, UI bulk delete, and the new MCP `search_emails`. New `seesee/search.py` normalizes queries; well-formed advanced syntax is unchanged, malformed input degrades to a term search, and a no-term query matches nothing instead of dropping the filter (which would have returned *every* email — and, in bulk delete, deleted them). **Pre-existing and project-wide, not introduced by this branch.**
  - UI app-key mint against an unknown app 500'd on the FK constraint; now 404, matching the REST route
  - MCP `create_app_key` leaked `FOREIGN KEY constraint failed` to the agent; now an actionable error
  - MCP auth gate rejected a lowercase `bearer` scheme (RFC 7235: case-insensitive)
  - `POST /logout` never verified the CSRF token its form was already sending; now checked when a session exists, skipped when there is none
  - The 0.20.0 legacy-auth safety net could not rescue the one case it documented. `_resolve_legacy_fallback` looked up candidate apps *by* `key_prefix`, so an app row whose prefix was NULL — precisely the row the backfill stores as `''` and that `resolve_key`'s indexed lookup misses — was unfindable, and its key would have stopped authenticating. Found by a new post-upgrade test. It now also matches NULL/empty prefixes and heals both rows to the real prefix on first use. **Latent, not live:** `apps.key_prefix` has been populated by every insert path since Phase 1.0, so no real deployment should contain a NULL — but the safety net now actually covers what it claims to
  - 45 new regression tests (`tests/test_search_sanitization.py` plus additions to `test_migration_v4.py`, `test_mcp.py`, `test_csrf.py`, `test_ui.py`), including the first tests that assert a pre-0.20.0 key still authenticates over **both** REST and SMTP after the upgrade
  - Verified clean: `require_scope` correctly refuses app-bound keys on management routes; all state-changing REST routes use Basic/Bearer only (no ambient cookie), so the CSRF surface really is limited to the UI handlers; the schema v4 migration is idempotent and correctly skipped on fresh databases

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

### CSV/JSON Search Export

Add export buttons to the email search page that download the current filtered results as CSV or JSON files.

Worth knowing before starting: `seesee/routes/export.py` already implements CSV and JSON serialization for the per-recipient GDPR export (`GET /api/v1/export`), including the `Content-Disposition` attachment header and the `format=csv` / `Accept: text/csv` negotiation. This task is mostly about reusing that machinery against the `/emails` search filters (`q`, `app_id`, `status`, `provider`, `date_from`, `date_to`) rather than writing new serializers. Route the search query through `seesee/search.py` like every other FTS5 call site.

### Follow-up from the 0.20.0 release review

Nothing outstanding — both findings are fixed (`S608`/`RUF100` in v0.20.1-dev, request-scheme cookies in v0.20.2-dev). `0.20.2-dev` is unreleased; fold it into the next tag.

### Deferred

Design spec for the shipped 0.20.0 behavior (source of truth): `docs/superpowers/specs/2026-07-26-management-keys-mcp-design.md`.

Deliberately skipped at the 0.20.0 cut: the pre-upgrade smoke test against a real database. There are no existing installs to migrate (single-user, redeployable from scratch), and `tests/test_migration_v4.py` covers the v4 backfill including proof that a pre-upgrade key still authenticates over both REST and SMTP.

## Other Candidates (from ROADMAP Phase 3.0)

- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Known Issues

- **Per-app degradation cannot be disabled when a global default is set.** (Also on ROADMAP Phase 3.0 — needs a human design decision.) `_effective_degrade_days` (`seesee/retention.py:162`) treats a per-app value of `0` (or `NULL`) as "inherit global". So if `settings.retention_degrade_to_text_days` is non-zero, there is no way to turn degradation off for a single app — `0`/blank falls back to the global. As of v0.19.4-dev the Settings UI stores `0` as NULL and shows "System default", so it at least no longer *implies* that `0` disables anything — but an explicit "disabled" state (sentinel value, separate column, or checkbox) still needs to be designed before per-app opt-out can work as a user would expect.
- **Legacy key columns must be deleted in 0.21.0.** `_resolve_legacy_fallback` in `seesee/keys.py`, the matching fallback branch at the end of `resolve_smtp_password`, and the legacy `apps.api_key` / `apps.smtp_password` columns exist only to survive a 0.19.x↔0.20.0 deploy overlap. They are commented "delete in 0.21.0" in three places. Once 0.20.0 has been running long enough that no 0.19.x container can come back, remove all three plus the `revoke_key` tombstone write, and drop the columns in a schema v5 migration. Until then a revoked *primary* app key stays revoked only because `revoke_key` tombstones those columns — do not remove that write in isolation.
- **App-detail key minting has no expiry control.** `create_app_key_ui` (`seesee/routes/ui.py`) always passes `expires_at=None`, so keys minted from an app's page never expire, while the Settings page defaults management keys to 90 days. Defensible (app keys are long-lived deploy credentials) but inconsistent and undocumented in the UI. Either add the same expiry `<select>` to the app-detail form or add a line of helper text saying app keys do not expire.
- **`last_used_at` costs a write transaction on every authenticated request.** `keys._record_use` runs an `UPDATE … WHERE last_used_at < cutoff` and commits on every successful key resolution. The 60-second debounce is in the `WHERE` clause, so the *row* is written at most once a minute, but the transaction and commit happen every request — a SQLite writer-lock acquisition per API call. Fine at current volume; revisit if ingest throughput ever becomes a concern (in-process debounce cache, or skip the commit when `rowcount == 0`).
- **Plaintext keys are interpolated into a JS string literal in templates.** `copyToClipboard('{{ flash.new_app_key }}', this)` in `app_detail.html` and `settings.html` (and the older `created_credentials` block) put a value inside a JS string inside an HTML attribute, where Jinja's HTML autoescaping does not protect the JS context. Safe today because the interpolated value is always a generated URL-safe base64 key (`[A-Za-z0-9_-]`), but the pattern breaks the moment anything user-supplied — a key *label*, say — is copied the same way. Prefer `|tojson` (already used for the ENV-vars block) if this pattern spreads.
## Resolved (previously listed here)

- ~~**CHANGELOG `[Unreleased]` needs a one-time consolidation.**~~ Done at the 0.20.0 cut (2026-07-27): the accumulated batches, repeated subheadings, and the stray `### Previously` group were merged into one Added/Changed/Fixed/Removed/Security set under `## [0.20.0]`, and `[Unreleased]` is now empty. Keep it that way — append to the existing heading for a bump rather than prepending a new block.

- ~~**Session and flash cookies not marked `Secure`.**~~ Fixed in v0.20.2-dev: `cookies_are_secure()` (`seesee/routes/ui.py`) derives the flag from `SEESEE_BASE_URL`, so an `https://` deployment gets secure cookies automatically while HTTP-only installs keep working. Covered by tests in `tests/test_ui.py`, including one asserting the plaintext-key-carrying flash cookie is `Secure` over HTTPS.
- ~~**No CSRF protection on UI form POSTs.**~~ Shipped in the 0.20.0 cycle: signed CSRF tokens bound to the session user on every session-authenticated POST handler (`seesee/csrf.py`), with `X-CSRF-Token` for `fetch()` callers. The 0.20.0 review closed the last gap (`POST /logout`).
- ~~**Retention value of `0` displays literally.**~~ Fixed in v0.19.4-dev: the settings UI stores `0` as NULL, and the read view treats `0` (e.g. legacy API-stored values) as "System default".

## Current State

- 429 tests passing (0 failures); `ruff check` and `ruff format --check` clean (ruff pinned at 0.16.0; `S608` + `RUF100` enforced)
- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, search-and-delete, data export per recipient, admin UX audit, theme selector UI, expanded theme catalog, complete copy-all-as-ENV-vars on app credentials, and the 0.20.0 management-keys + MCP work
- Full REST API, SMTP ingest, Web UI, retention, docs site, MCP server at `/mcp`
- Scoped management API keys (`ss_mgmt_`) with expiry and revocation; multiple keys per app for zero-downtime rotation; CLI bootstrap via `python -m seesee.keys`
- CSRF protection on all session-authenticated UI form POSTs
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
