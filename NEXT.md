# Next Steps — SeeSee

**Version:** 0.19.0-dev
**Updated:** 2026-05-19

## Just Completed

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

- `tests/test_ingest.py::test_log_email_no_auth` expects HTTP 401 but FastAPI's `HTTPBasic` returns 403 for a missing `Authorization` header — pre-existing, unrelated to recent work

## Current State

- 275 tests passing (1 pre-existing unrelated failure — see Known Issues)
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
