# Next Steps — SeeSee

**Version:** 0.15.0-dev
**Updated:** 2026-02-21

## Just Completed

- **Mobile UX, theme system foundation, and UI polish** — Phase 2.1:
  - CSS custom properties theme system (`--color-accent`, `--color-paper`) with `data-theme` attribute — current mint palette is the default; future themes just add a `[data-theme="name"]` CSS block
  - Tailwind config uses CSS variable-based colors; all `mint` classes renamed to `accent` across templates
  - Active/tap feedback on all interactive elements for touch devices
  - Enlarged touch targets on icon-only buttons (44px minimum)
  - Copy buttons on email addresses (From, To, CC, BCC, Reply-To) and all code snippets
  - Code copy buttons: always visible on touch, hover-to-reveal on desktop
  - Active filter count badge, responsive metadata labels, aria-labels on icon-only buttons
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

- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, search-and-delete, and data export per recipient from Phase 3.0
- 272 tests passing
- Full REST API, SMTP ingest, Web UI, retention, docs site
- CSS custom properties theme system ready for multiple themes
- Provider webhook receivers for Resend and SendGrid
- Graduated body degradation (full → text → preview over time)
- Timezone architecture: UTC storage, configurable display, format-consistent queries
- Search-and-delete: GDPR erasure via bulk delete with filters
- Data export per recipient: GDPR right of access via JSON/CSV export
- Docker multi-platform builds (amd64 + arm64)
- Documentation site deployed via GitHub Pages
- Persistence diagnostics for debugging deployment issues
