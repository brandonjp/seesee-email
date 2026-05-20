# Edit App Settings — Design

**Date:** 2026-05-19
**Status:** Approved
**Topic:** Let users edit an app's storage mode and retention overrides after creation, from the app detail page.

## Problem

When adding an app, users pick a `body_storage_mode` (full / text only / preview). After creation there is no way to change it from the UI — only the app name is editable (inline edit). The four per-app retention override fields have no UI at all. Users who change their mind must call the REST API directly or recreate the app.

## Scope

In scope:
- Edit `body_storage_mode` from the app detail page.
- Edit the four retention override fields from the app detail page:
  `retention_max_count`, `retention_max_age_days`,
  `retention_degrade_to_text_days`, `retention_degrade_to_preview_days`.

Out of scope:
- Editing from the apps list page (detail page only, for now).
- Schema changes — all columns already exist on the `apps` table.
- REST API changes — `PATCH /api/v1/apps/{id}` already supports every field.
- Editing immutable fields (`slug`, credentials, timestamps).

## Background — current state

- **DB:** the `apps` table already has all five columns (`seesee/database.py`).
- **API:** `PATCH /api/v1/apps/{app_id}` (`seesee/routes/apps.py:139`) already updates
  all five fields, validates `body_storage_mode`, and supports clearing retention
  overrides to `NULL`. Fully tested in `tests/test_app_update.py`.
- **UI:** `app_detail.html` has an inline edit for the app name backed by
  `POST /apps/{app_id}/rename` (`seesee/routes/ui.py:651`). No UI for storage mode
  or retention.
- **Detail GET gap:** `app_detail` (`seesee/routes/ui.py:589`) only SELECTs
  `retention_max_count` and `retention_max_age_days` — it does **not** fetch
  `retention_degrade_to_text_days` or `retention_degrade_to_preview_days`. The query
  must be extended so the template can show all four.
- **Global defaults** (`seesee/config.py:30-37`): `retention_max_count = 1000`,
  `retention_max_age_days = 90`, `retention_degrade_to_text_days = 0`,
  `retention_degrade_to_preview_days = 0`. A per-app field set to `NULL` falls back
  to the matching global default. For the two degrade fields, `0` means "disabled".

## Design

### 1. Backend — `seesee/routes/ui.py`

**Extend `app_detail` GET handler:**
- Add `retention_degrade_to_text_days` and `retention_degrade_to_preview_days` to
  the `SELECT` so all four retention values reach the template.
- Add a `retention_defaults` dict to the template context, sourced from
  `config.py`, with keys `max_count`, `max_age_days`, `degrade_to_text_days`,
  `degrade_to_preview_days`. Used to render placeholder hints.

**New handler `POST /apps/{app_id}/settings`:**
- Modeled on the existing `rename_app_ui` handler (direct SQL, redirect response,
  `require_session` dependency).
- Form fields:
  - `body_storage_mode: str = Form(...)` — required.
  - `retention_max_count`, `retention_max_age_days`,
    `retention_degrade_to_text_days`, `retention_degrade_to_preview_days` —
    each `str = Form("")`, may be empty.
- Logic:
  1. Verify the app exists; if not, redirect to `/apps` (303).
  2. Validate `body_storage_mode` against `VALID_BODY_STORAGE_MODES`. If invalid,
     redirect back to `/apps/{app_id}` without writing (silent — see Error handling).
  3. For each retention field: strip whitespace; empty string → `NULL`; otherwise
     parse as `int`. If parsing fails or the value is negative, redirect back to
     `/apps/{app_id}` without writing.
  4. `UPDATE apps SET body_storage_mode = ?, retention_max_count = ?,
     retention_max_age_days = ?, retention_degrade_to_text_days = ?,
     retention_degrade_to_preview_days = ? WHERE id = ?`, then `commit()`.
  5. Redirect to `/apps/{app_id}` (303).

### 2. Frontend — `seesee/templates/app_detail.html`

Add a **"Settings" card** immediately above the existing "Actions" card. It uses an
Alpine.js `editingSettings` boolean (added to the page-level `x-data`).

**Read mode (default, `!editingSettings`):**
- Card titled "Settings" with an "Edit" pencil button (same icon/style as the name
  edit button).
- Shows current values as a labelled list:
  - Storage mode — humanized (`full` → "Full", `text_only` → "Text only",
    `preview` → "Preview only").
  - Each retention field — the stored value, or "System default" when `NULL`.

**Edit mode (`editingSettings`):**
- Inline `<form action="/apps/{{ app.id }}/settings" method="post">` with
  Save / Cancel buttons; `Escape` cancels (matches the name-edit pattern).
- `body_storage_mode` — `<select>` with the three options
  ("Full", "Text only", "Preview only"), current value preselected.
- Four retention fields — `<input type="number" min="0" step="1">`, prefilled with
  the stored value, or left empty when `NULL`. Empty inputs show a greyed
  placeholder built from `retention_defaults`:
  - count / age: `Default: 1000`, `Default: 90`.
  - degrade fields: `Default: off` when the global default is `0`, otherwise
    `Default: N`.
- Helper text:
  - Under the storage-mode select: "Applies to future emails only — won't change
    emails already stored."
  - Under the retention group: "Leave blank to use the system default."

**Retention field labels (plain language):**
- `retention_max_count` → "Max emails kept"
- `retention_max_age_days` → "Max age (days)"
- `retention_degrade_to_text_days` → "Strip HTML to text after (days)"
- `retention_degrade_to_preview_days` → "Reduce to preview after (days)"

The existing storage-mode badge in the page header stays as a read-only
at-a-glance indicator; the editable copy lives in the Settings card.

### 3. Error handling

A normal user effectively cannot submit invalid input: the `<select>` only emits
the three valid modes, and `type="number" min="0"` constrains the retention inputs.
Server-side validation is kept purely as a defense-in-depth safety net — on invalid
input the handler redirects back to the detail page without writing and without a
flash message. A user-facing flash error is intentionally deferred; HTML5
constraints are sufficient for the supported UI.

### 4. Testing — `tests/test_ui.py`

New tests against the `POST /apps/{app_id}/settings` handler:
- Updates `body_storage_mode` and retention values; the detail page reflects them.
- Clearing a retention override: submitting an empty field sets the column to `NULL`.
- Invalid `body_storage_mode` is rejected — no DB change.
- A negative / non-numeric retention value is rejected — no DB change.
- The detail page renders all four retention values (guards the extended `SELECT`).

## Files touched

| File | Change |
|------|--------|
| `seesee/routes/ui.py` | Extend `app_detail` SELECT + context; add `POST /apps/{app_id}/settings` |
| `seesee/templates/app_detail.html` | Add "Settings" card with view/edit toggle |
| `tests/test_ui.py` | Add tests for the settings handler and detail rendering |
| `pyproject.toml`, `seesee/__init__.py` | Version bump (new feature → `0.19.0-dev`) |
| `CHANGELOG.md` | New entry |
| `NEXT.md` | Move feature to "Just Completed"; update version header |

No database migration. No REST API change.

## Risks / notes

- **Storage mode is forward-only.** Switching `full → preview` does not strip HTML
  from already-stored emails, and switching back does not recover HTML that was
  never captured. Surfaced to the user via the helper note under the select.
- **Per-CLAUDE.md:** version bump, CHANGELOG entry, and `NEXT.md` update are
  required deliverables, not optional follow-ups.
