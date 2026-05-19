# Next Steps — SeeSee

**Version:** 0.18.0-dev
**Updated:** 2026-02-23

## Just Completed

- **"Copy all as ENV vars" button** on app credentials:
  - Post-creation alert in `/apps` — copies real values (API key, SMTP password, username, URL)
  - SMTP Settings tab in `/apps/{id}` — copies with `ss_YOUR_API_KEY` placeholder (credentials not re-shown after creation)
  - Format: `MAIL_SEESEE_API_KEY`, `MAIL_SEESEE_SMTP_PASSWORD`, `MAIL_SEESEE_SMTP_USERNAME`, `MAIL_SEESEE_URL`
  - Also passes `base_url` to the apps list template context (was missing)

- **Expanded theme catalog** (Phase 4):
  - 21 total themes (up from 10): 4 accent, 8 developer, 4 light, 6 retro
  - New developer themes: Monokai, Tomorrow Night, Rosé Pine, Catppuccin Mocha, Obsidian
  - New light themes: Paper, Aqua Classic, Blueprint (with CSS grid overlay)
  - New retro themes: Amber Terminal, VHS (scanlines), Mac OS 9 (beveled borders), Rad (neon glow)
  - Scoped CSS overrides for Blueprint, VHS, OS 9, and Rad — zero bleed between themes
  - Theme picker reorganized: Accent → Developer → Light → Retro
  - 272 tests passing

## Highest Priority Next Task

### Fix & Expand "Copy ENV Vars" — Two Locations, Both Incomplete

**Context:** There are two places in the UI that offer an ENV vars clipboard copy. Both are broken/incomplete. This is a high-friction UX problem for developers integrating SeeSee into other apps.

---

#### Location 1 — Post-creation alert in `/apps` (new app just added)

When you add a new app, a success alert fires and copies real credentials to the clipboard. **It currently copies only 4 vars:**

```
MAIL_SEESEE_API_KEY=ss_abc123...
MAIL_SEESEE_SMTP_PASSWORD=ss_abc123...
MAIL_SEESEE_SMTP_USERNAME=knack-cards
MAIL_SEESEE_URL=https://seesee.bpf.fyi
```

**Problem:** Missing SMTP host/port/encryption and missing app identity vars.

---

#### Location 2 — "Copy all as ENV vars" button on SMTP Settings tab in `/apps/{id}`

The SMTP Settings tab visually displays:
- Host: `seesee.bpf.fyi`
- Port: `2525`
- Username: `knack-cards`
- Password: `ss_YOUR_API_KEY` (placeholder — real key not re-shown after creation, that's fine)
- Encryption: `STARTTLS`

**Problem 1:** The "Copy all as ENV vars" button at the bottom of that tab only copies the same 4 vars (with placeholder for the key), so the host, port, and encryption shown right there on screen never make it to the clipboard. A user sees 5 fields, copies 4 vars, and is still missing the SMTP connection details.

**Problem 2:** Neither copy location includes the app's UUID or any URL vars that reference the specific app, which developers need to link back to SeeSee from their own app dashboards.

---

#### Goal — What the full ENV var block should look like

Both copy locations should produce the complete set below. Location 1 uses real values; Location 2 uses the `ss_YOUR_API_KEY` placeholder where credentials aren't re-shown.

```
# SeeSee API
MAIL_SEESEE_API_KEY=ss_abc123...

# SMTP connection
MAIL_SEESEE_SMTP_HOST=seesee.bpf.fyi
MAIL_SEESEE_SMTP_PORT=2525
MAIL_SEESEE_SMTP_USERNAME=knack-cards
MAIL_SEESEE_SMTP_PASSWORD=ss_abc123...
MAIL_SEESEE_SMTP_ENCRYPTION=STARTTLS

# Base URL
MAIL_SEESEE_URL=https://seesee.bpf.fyi

# App identity (for linking into external dashboards / building log URLs)
MAIL_SEESEE_APP_ID=4076a278-dd4b-4fa4-b894-8f4c26875418
MAIL_SEESEE_APP_URL=https://seesee.bpf.fyi/apps/4076a278-dd4b-4fa4-b894-8f4c26875418
MAIL_SEESEE_LOG_URL=https://seesee.bpf.fyi/emails?app_id=4076a278-dd4b-4fa4-b894-8f4c26875418
```

The exact var names above are a suggestion — use whatever is most consistent with the existing naming convention. The important thing is that developers get everything in one copy: API key, full SMTP connection details, and the app identity vars so they can build log links without extra lookups.

**Design principle:** It's always easier for a developer to delete lines they don't need than to hunt down values they're missing.

---

#### Scope summary

1. Find the JS/template code that builds the clipboard string for the post-creation alert (Location 1) and add the missing vars.
2. Find the JS/template code behind the "Copy all as ENV vars" button on the SMTP Settings tab (Location 2) and add the missing vars (using placeholder for key/password since they're not re-shown).
3. Add `MAIL_SEESEE_APP_ID`, `MAIL_SEESEE_APP_URL`, and `MAIL_SEESEE_LOG_URL` to both locations.
4. Confirm the SMTP host, port, and encryption values are either hardcoded constants or pulled from server config — they should not be hardcoded differently in two places.
5. Update tests that assert on the clipboard string format.

---

- **CSV/JSON search export** — add export buttons to the email search page that download filtered results as CSV or JSON files.

## Other Candidates (from ROADMAP Phase 3.0)

- Prometheus metrics endpoint
- Multi-user auth with roles
- WordPress plugin with settings page
- Postgres support as alternative to SQLite
- STARTTLS support for SMTP ingest
- Notification alerts ("App X hasn't sent email in 24 hours")

## Current State

- All phases 0 through 2.1 complete, plus provider webhook receivers, graduated body degradation, timezone handling, search-and-delete, data export per recipient, admin UX audit, theme selector UI, expanded theme catalog, and copy-all-as-ENV-vars on app credentials
- 272 tests passing
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
