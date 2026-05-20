# Edit App Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users edit an app's `body_storage_mode` and four retention override fields from the app detail page.

**Architecture:** A new `POST /apps/{app_id}/settings` UI route updates the five existing `apps` columns via direct SQL (mirroring the existing `rename_app_ui` handler). The app detail page gains a "Settings" card with an Alpine.js view/edit toggle. No schema migration and no REST API changes — the `apps` table and `PATCH /api/v1/apps/{id}` already support every field.

**Tech Stack:** FastAPI, aiosqlite, Jinja2 templates, Alpine.js, Tailwind CSS, pytest.

---

## Background — facts the implementer needs

- **Spec:** `docs/superpowers/specs/2026-05-19-edit-app-settings-design.md`.
- **`apps` table** already has all five columns (`seesee/database.py`): `body_storage_mode`,
  `retention_max_count`, `retention_max_age_days`, `retention_degrade_to_text_days`,
  `retention_degrade_to_preview_days`.
- **Global retention defaults** live on the `settings` singleton (`seesee/config.py`):
  `settings.retention_max_count` (1000), `settings.retention_max_age_days` (90),
  `settings.retention_degrade_to_text_days` (0), `settings.retention_degrade_to_preview_days` (0).
  A per-app field of `NULL` falls back to the matching global default; `0` on a degrade
  field means "disabled".
- **Valid storage modes:** the set `{"full", "text_only", "preview"}` — `create_app_ui`
  (`seesee/routes/ui.py:488`) defines this inline; reuse the same inline set.
- **Existing pattern to mirror:** `rename_app_ui` (`seesee/routes/ui.py:651-671`) — a UI
  POST handler that does direct SQL and returns a 303 `RedirectResponse`.
- **`seesee/routes/ui.py` imports already present:** `Form`, `Depends`, `RedirectResponse`,
  `get_db`, `require_session`, `settings`. No new imports are needed.
- **The detail GET handler `app_detail` (`seesee/routes/ui.py:579-648`)** currently SELECTs
  only `retention_max_count` and `retention_max_age_days` — the two degrade columns are
  missing and must be added.
- **Test conventions (`tests/test_ui.py`):** create apps with
  `await client.post("/api/v1/apps", json={"name": ...}, headers=admin_auth_header)`;
  get a session cookie with the module helper `_get_session_cookie()`; pass it as
  `cookies={SESSION_COOKIE_NAME: token}`. `GET /api/v1/apps` returns a JSON list of apps
  including all four retention fields — use it to verify writes.

---

## Task 1: Add the settings-update UI handler

**Files:**
- Modify: `seesee/routes/ui.py` (add a new route after `rename_app_ui`, which ends at line 671)
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write the failing tests**

Add these four tests to `tests/test_ui.py` (append after `test_apps_rotate_key`, before the
`# Integration ENV vars` section comment at line 364):

```python
async def test_apps_update_settings(client: AsyncClient, admin_auth_header: dict) -> None:
    """POST /apps/{id}/settings updates storage mode and retention values."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Settings App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    resp = await client.post(
        f"/apps/{app_id}/settings",
        data={
            "body_storage_mode": "preview",
            "retention_max_count": "250",
            "retention_max_age_days": "30",
            "retention_degrade_to_text_days": "",
            "retention_degrade_to_preview_days": "",
        },
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/apps/{app_id}"

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["body_storage_mode"] == "preview"
    assert updated["retention_max_count"] == 250
    assert updated["retention_max_age_days"] == 30


async def test_apps_update_settings_clears_retention(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """Submitting empty retention fields clears the overrides to null."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Clear App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    # First set overrides
    await client.post(
        f"/apps/{app_id}/settings",
        data={
            "body_storage_mode": "full",
            "retention_max_count": "500",
            "retention_max_age_days": "45",
            "retention_degrade_to_text_days": "",
            "retention_degrade_to_preview_days": "",
        },
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    # Then clear them
    resp = await client.post(
        f"/apps/{app_id}/settings",
        data={
            "body_storage_mode": "full",
            "retention_max_count": "",
            "retention_max_age_days": "",
            "retention_degrade_to_text_days": "",
            "retention_degrade_to_preview_days": "",
        },
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["retention_max_count"] is None
    assert updated["retention_max_age_days"] is None


async def test_apps_update_settings_rejects_invalid_mode(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """An invalid body_storage_mode is rejected — no DB change."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Bad Mode App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    resp = await client.post(
        f"/apps/{app_id}/settings",
        data={
            "body_storage_mode": "bogus",
            "retention_max_count": "",
            "retention_max_age_days": "",
            "retention_degrade_to_text_days": "",
            "retention_degrade_to_preview_days": "",
        },
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["body_storage_mode"] == "full"  # unchanged from creation default


async def test_apps_update_settings_rejects_negative_retention(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """A negative retention value is rejected — prior value is left intact."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Neg App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    # Set a known value first
    await client.post(
        f"/apps/{app_id}/settings",
        data={
            "body_storage_mode": "full",
            "retention_max_count": "100",
            "retention_max_age_days": "",
            "retention_degrade_to_text_days": "",
            "retention_degrade_to_preview_days": "",
        },
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    # Negative value must be rejected
    resp = await client.post(
        f"/apps/{app_id}/settings",
        data={
            "body_storage_mode": "full",
            "retention_max_count": "-5",
            "retention_max_age_days": "",
            "retention_degrade_to_text_days": "",
            "retention_degrade_to_preview_days": "",
        },
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["retention_max_count"] == 100  # unchanged


```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_ui.py::test_apps_update_settings tests/test_ui.py::test_apps_update_settings_clears_retention tests/test_ui.py::test_apps_update_settings_rejects_invalid_mode tests/test_ui.py::test_apps_update_settings_rejects_negative_retention -v`
Expected: all four FAIL with HTTP 404/405 (the `/apps/{id}/settings` route does not exist yet).

- [ ] **Step 3: Implement the handler**

In `seesee/routes/ui.py`, insert this handler immediately after `rename_app_ui` (after its
closing `return` at line 671, before the `@router.post("/apps/{app_id}/purge")` decorator):

```python
@router.post("/apps/{app_id}/settings")
async def update_app_settings_ui(
    app_id: str,
    user: str = Depends(require_session),
    body_storage_mode: str = Form(...),
    retention_max_count: str = Form(""),
    retention_max_age_days: str = Form(""),
    retention_degrade_to_text_days: str = Form(""),
    retention_degrade_to_preview_days: str = Form(""),
) -> RedirectResponse:
    """Update an app's storage mode and retention overrides via the web UI."""
    db = await get_db()

    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        return RedirectResponse(url="/apps", status_code=303)

    # The <select> only emits valid modes; reject anything else as a
    # defense-in-depth safety net (no write).
    valid_modes = {"full", "text_only", "preview"}
    if body_storage_mode not in valid_modes:
        return RedirectResponse(url=f"/apps/{app_id}", status_code=303)

    # Empty string clears the override (NULL); otherwise a non-negative integer.
    # type="number" min="0" guards this client-side.
    retention: dict[str, int | None] = {}
    for field, raw in (
        ("retention_max_count", retention_max_count),
        ("retention_max_age_days", retention_max_age_days),
        ("retention_degrade_to_text_days", retention_degrade_to_text_days),
        ("retention_degrade_to_preview_days", retention_degrade_to_preview_days),
    ):
        stripped = raw.strip()
        if stripped == "":
            retention[field] = None
            continue
        try:
            parsed = int(stripped)
        except ValueError:
            return RedirectResponse(url=f"/apps/{app_id}", status_code=303)
        if parsed < 0:
            return RedirectResponse(url=f"/apps/{app_id}", status_code=303)
        retention[field] = parsed

    await db.execute(
        "UPDATE apps SET body_storage_mode = ?, retention_max_count = ?, "
        "retention_max_age_days = ?, retention_degrade_to_text_days = ?, "
        "retention_degrade_to_preview_days = ? WHERE id = ?",
        (
            body_storage_mode,
            retention["retention_max_count"],
            retention["retention_max_age_days"],
            retention["retention_degrade_to_text_days"],
            retention["retention_degrade_to_preview_days"],
            app_id,
        ),
    )
    await db.commit()

    return RedirectResponse(url=f"/apps/{app_id}", status_code=303)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_ui.py::test_apps_update_settings tests/test_ui.py::test_apps_update_settings_clears_retention tests/test_ui.py::test_apps_update_settings_rejects_invalid_mode tests/test_ui.py::test_apps_update_settings_rejects_negative_retention -v`
Expected: all four PASS.

- [ ] **Step 5: Commit**

```bash
git add seesee/routes/ui.py tests/test_ui.py
git commit -m "feat: add settings-update UI handler for storage mode and retention

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Extend the detail GET handler and add the Settings card

**Files:**
- Modify: `seesee/routes/ui.py` — `app_detail` handler (SELECT at lines 589-593; context dict at lines 626-645)
- Modify: `seesee/templates/app_detail.html` — insert a card before the "Actions" card (line 274)
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_ui.py` directly after the four tests from Task 1:

```python
async def test_app_detail_settings_card(client: AsyncClient, admin_auth_header: dict) -> None:
    """Detail page renders the Settings card; set retention values round-trip."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Card App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    await client.post(
        f"/apps/{app_id}/settings",
        data={
            "body_storage_mode": "preview",
            "retention_max_count": "111",
            "retention_max_age_days": "22",
            "retention_degrade_to_text_days": "7",
            "retention_degrade_to_preview_days": "14",
        },
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )

    resp = await client.get(f"/apps/{app_id}", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert f'action="/apps/{app_id}/settings"' in resp.text
    assert 'name="body_storage_mode"' in resp.text
    assert 'name="retention_max_count"' in resp.text
    assert 'name="retention_degrade_to_preview_days"' in resp.text
    # The degrade-field values prove the detail SELECT fetches all four columns.
    assert 'value="7"' in resp.text
    assert 'value="14"' in resp.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_ui.py::test_app_detail_settings_card -v`
Expected: FAIL — `action="/apps/{id}/settings"` is not in the page yet.

- [ ] **Step 3: Extend the `app_detail` SELECT**

In `seesee/routes/ui.py`, in the `app_detail` handler, replace the SELECT at lines 589-593:

```python
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, created_at, last_activity_at FROM apps WHERE id = ?",
        (app_id,),
    )
```

with:

```python
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, retention_degrade_to_text_days, "
        "retention_degrade_to_preview_days, created_at, last_activity_at "
        "FROM apps WHERE id = ?",
        (app_id,),
    )
```

- [ ] **Step 4: Add `retention_defaults` to the template context**

In the same handler, in the `TemplateResponse` context dict (lines 628-644), add this key
immediately after the `"rotated_key": rotated_key,` line:

```python
            "retention_defaults": {
                "max_count": settings.retention_max_count,
                "max_age_days": settings.retention_max_age_days,
                "degrade_to_text_days": settings.retention_degrade_to_text_days,
                "degrade_to_preview_days": settings.retention_degrade_to_preview_days,
            },
```

- [ ] **Step 5: Add the Settings card to the template**

In `seesee/templates/app_detail.html`, insert the following block immediately before the
`<!-- Actions -->` comment at line 274 (it becomes a sibling card inside the page's
`space-y-4` container):

```html
    <!-- Settings -->
    <div class="rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-5"
         x-data="{ editingSettings: false }">
        <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Settings</h2>
            <button x-show="!editingSettings" @click="editingSettings = true"
                    class="inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:text-accent/80 active:text-accent/70 transition-colors"
                    aria-label="Edit settings" title="Edit settings">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
                Edit
            </button>
        </div>

        <!-- Read mode -->
        <dl x-show="!editingSettings" class="grid gap-3 text-sm sm:grid-cols-2">
            <div>
                <dt class="text-gray-500 dark:text-gray-400">Storage mode</dt>
                <dd class="mt-0.5 font-medium capitalize">{{ app.body_storage_mode | replace('_', ' ') }}</dd>
            </div>
            <div>
                <dt class="text-gray-500 dark:text-gray-400">Max emails kept</dt>
                <dd class="mt-0.5 font-medium">{% if app.retention_max_count is not none %}{{ app.retention_max_count }}{% else %}<span class="text-gray-400 dark:text-gray-500">System default</span>{% endif %}</dd>
            </div>
            <div>
                <dt class="text-gray-500 dark:text-gray-400">Max age (days)</dt>
                <dd class="mt-0.5 font-medium">{% if app.retention_max_age_days is not none %}{{ app.retention_max_age_days }}{% else %}<span class="text-gray-400 dark:text-gray-500">System default</span>{% endif %}</dd>
            </div>
            <div>
                <dt class="text-gray-500 dark:text-gray-400">Strip HTML to text after (days)</dt>
                <dd class="mt-0.5 font-medium">{% if app.retention_degrade_to_text_days is not none %}{{ app.retention_degrade_to_text_days }}{% else %}<span class="text-gray-400 dark:text-gray-500">System default</span>{% endif %}</dd>
            </div>
            <div>
                <dt class="text-gray-500 dark:text-gray-400">Reduce to preview after (days)</dt>
                <dd class="mt-0.5 font-medium">{% if app.retention_degrade_to_preview_days is not none %}{{ app.retention_degrade_to_preview_days }}{% else %}<span class="text-gray-400 dark:text-gray-500">System default</span>{% endif %}</dd>
            </div>
        </dl>

        <!-- Edit mode -->
        <form x-show="editingSettings" x-cloak action="/apps/{{ app.id }}/settings" method="post"
              class="space-y-4" @keydown.escape="editingSettings = false">
            <div>
                <label class="block text-sm font-medium mb-1">Storage mode</label>
                <select name="body_storage_mode"
                        class="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent">
                    <option value="full" {% if app.body_storage_mode == 'full' %}selected{% endif %}>Full (HTML + Text)</option>
                    <option value="text_only" {% if app.body_storage_mode == 'text_only' %}selected{% endif %}>Text Only</option>
                    <option value="preview" {% if app.body_storage_mode == 'preview' %}selected{% endif %}>Preview Only</option>
                </select>
                <p class="mt-1 text-xs text-gray-400 dark:text-gray-500">Applies to future emails only — won't change emails already stored.</p>
            </div>

            <div class="grid gap-3 sm:grid-cols-2">
                <div>
                    <label class="block text-sm font-medium mb-1">Max emails kept</label>
                    <input type="number" min="0" step="1" name="retention_max_count"
                           value="{{ app.retention_max_count if app.retention_max_count is not none else '' }}"
                           placeholder="Default: {{ retention_defaults.max_count }}"
                           class="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent">
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">Max age (days)</label>
                    <input type="number" min="0" step="1" name="retention_max_age_days"
                           value="{{ app.retention_max_age_days if app.retention_max_age_days is not none else '' }}"
                           placeholder="Default: {{ retention_defaults.max_age_days }}"
                           class="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent">
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">Strip HTML to text after (days)</label>
                    <input type="number" min="0" step="1" name="retention_degrade_to_text_days"
                           value="{{ app.retention_degrade_to_text_days if app.retention_degrade_to_text_days is not none else '' }}"
                           placeholder="Default: {{ 'off' if retention_defaults.degrade_to_text_days == 0 else retention_defaults.degrade_to_text_days }}"
                           class="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent">
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">Reduce to preview after (days)</label>
                    <input type="number" min="0" step="1" name="retention_degrade_to_preview_days"
                           value="{{ app.retention_degrade_to_preview_days if app.retention_degrade_to_preview_days is not none else '' }}"
                           placeholder="Default: {{ 'off' if retention_defaults.degrade_to_preview_days == 0 else retention_defaults.degrade_to_preview_days }}"
                           class="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent">
                </div>
            </div>
            <p class="text-xs text-gray-400 dark:text-gray-500">Leave a field blank to use the system default.</p>

            <div class="flex gap-3 justify-end">
                <button type="button" @click="editingSettings = false"
                        class="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm hover:bg-gray-50 active:bg-gray-100 dark:hover:bg-gray-700 dark:active:bg-gray-700 transition-colors">Cancel</button>
                <button type="submit"
                        class="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-contrast hover:bg-accent/90 active:bg-accent/80 transition-colors">Save Settings</button>
            </div>
        </form>
    </div>

```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_ui.py::test_app_detail_settings_card -v`
Expected: PASS.

- [ ] **Step 7: Manual browser check**

Start the app: `python -m seesee` (or follow the project's dev-run skill). Log in, open an
app detail page, and confirm:
- The "Settings" card appears above "Actions" and shows current values (retention fields
  show "System default" when unset).
- Clicking "Edit" reveals the form; empty retention inputs show `Default: N` / `Default: off`
  placeholders; the storage-mode select is preselected to the current mode.
- Saving redirects back to the detail page with the new values shown in read mode.
- "Cancel" and the `Escape` key both close the form without saving.

- [ ] **Step 8: Commit**

```bash
git add seesee/routes/ui.py seesee/templates/app_detail.html tests/test_ui.py
git commit -m "feat: add Settings card to app detail page

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Version bump, changelog, and NEXT.md

**Files:**
- Modify: `pyproject.toml:7`
- Modify: `seesee/__init__.py:3`
- Modify: `CHANGELOG.md`
- Modify: `NEXT.md`

- [ ] **Step 1: Bump the version constants**

In `pyproject.toml` line 7, change `version = "0.18.4-dev"` to `version = "0.19.0-dev"`.

In `seesee/__init__.py` line 3, change `__version__ = "0.18.4-dev"` to
`__version__ = "0.19.0-dev"`.

- [ ] **Step 2: Update CHANGELOG.md**

In `CHANGELOG.md`, under the `## [Unreleased]` heading, add a new `### Added` section
immediately above the existing `### Changed` section:

```markdown
### Added
- Edit an app's storage mode and retention overrides after creation, via a new "Settings" card on the app detail page
```

Then, as the first bullet under `### Changed`, add:

```markdown
- Version bump: 0.18.4-dev → 0.19.0-dev
```

- [ ] **Step 3: Update NEXT.md**

In `NEXT.md`:
- Change the header line `**Version:** 0.18.4-dev` to `**Version:** 0.19.0-dev`.
- Add this bullet at the top of the `## Just Completed` list:

```markdown
- **Edit app settings from the detail page** (v0.19.0-dev):
  - New "Settings" card on `/apps/{id}` with a view/edit toggle for `body_storage_mode` and the four retention overrides
  - New `POST /apps/{app_id}/settings` UI handler; empty retention fields clear the override to the system default
  - Detail GET now fetches all four retention columns; edit form shows global defaults as placeholder hints
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest`
Expected: all tests pass except the one pre-existing unrelated failure noted in `NEXT.md`
(`tests/test_ingest.py::test_log_email_no_auth`). The new tests from Tasks 1-2 pass.

- [ ] **Step 5: Lint and format**

Run: `ruff check seesee tests && ruff format --check seesee tests`
If `ruff format --check` reports files needing formatting, run `ruff format seesee tests`
and re-run the tests from Step 4.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml seesee/__init__.py CHANGELOG.md NEXT.md
git commit -m "chore: bump version to 0.19.0-dev for edit-app-settings

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Completion

After Task 3, the feature branch `feat/edit-app-settings` is ready. Use the
`superpowers:finishing-a-development-branch` skill to choose between opening a PR or
merging. Pushing to the remote and opening a PR are shared actions — confirm with the user
before doing either.

## Self-review notes (for the planner — not an implementation step)

- **Spec coverage:** storage-mode edit (Tasks 1-2), all four retention fields (Tasks 1-2),
  detail-page-only (Task 2), extended GET SELECT (Task 2 Step 3), `retention_defaults`
  placeholders (Task 2 Steps 4-5), forward-only helper note (Task 2 Step 5), silent
  server-side validation (Task 1 Step 3), tests (Tasks 1-2), version/CHANGELOG/NEXT.md
  (Task 3) — all covered.
- **Type consistency:** form fields are `str` throughout the handler; the retention dict
  holds `int | None`; template uses `is not none` consistently; field names match between
  the handler, the template `name="..."` attributes, and the tests.
- **No placeholders:** every code and command step contains complete content.
