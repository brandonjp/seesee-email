# Next Steps — SeeSee

**Version:** 0.17.0-dev
**Updated:** 2026-02-22

## Just Completed

- **Theme selector UI + expanded theme catalog** (Phase 3.0):
  - 10 color themes: Mint (default), Indigo, Rose, Amber, Nord, Gruvbox, Dracula, Solarized Light, Terminal, Windows 95
  - Swatch grid picker on Settings page with live preview, active indicator, and localStorage persistence
  - Win95 theme includes flat corners and beveled borders via scoped CSS overrides
  - Full palette specs for each theme noted in CSS comments for future expansion beyond `--color-accent` / `--color-paper`
  - 272 tests passing

## Highest Priority Next Task

- **CSV/JSON search export** — add export buttons to the email search page that download filtered results as CSV or JSON files.

## Other Candidates (from ROADMAP Phase 3.0)

- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Current State

- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, search-and-delete, data export per recipient, admin UX audit, and theme selector UI from Phase 3.0
- 272 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- 10-theme color system with swatch picker on Settings page
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Timezone architecture: UTC storage, configurable display, format-consistent queries
- Search-and-delete: GDPR erasure via bulk delete with filters
- Data export per recipient: GDPR right of access via JSON/CSV export
- Admin UX audit: iOS zoom fix, sortable columns, touch targets, copy buttons, loading states, tooltips
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
