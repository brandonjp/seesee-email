# Next Steps — SeeSee

**Version:** 0.16.0-dev
**Updated:** 2026-02-21

## Just Completed

- **Admin UX audit — 12 fixes across 7 files** (Phase 3.0):
  - Critical: iOS Safari auto-zoom fix (16px min on inputs), clickable sort column headers with indicators
  - Moderate: 44px touch targets on coarse-pointer devices, copy buttons on metadata/SMTP settings, title tooltips on truncated cells, loading states on login + app creation
  - Minor: `type="search"` on search input, required field asterisk, email ID display + copy, "View emails" link on app detail, copy buttons on body tabs
  - 272 tests passing

## Highest Priority Next Task

- **Theme selector UI** on settings page — dropdown that sets `data-theme` and persists to `localStorage`. The CSS variable infrastructure is already in place; just needs the UI component and a few theme color palettes defined in `style.css`.

## Other Candidates (from ROADMAP Phase 3.0)

- CSV/JSON search export
- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Current State

- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, search-and-delete, data export per recipient, and admin UX audit from Phase 3.0
- 272 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- CSS custom properties theme system ready for multiple themes
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Timezone architecture: UTC storage, configurable display, format-consistent queries
- Search-and-delete: GDPR erasure via bulk delete with filters
- Data export per recipient: GDPR right of access via JSON/CSV export
- Admin UX audit: iOS zoom fix, sortable columns, touch targets, copy buttons, loading states, tooltips
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
