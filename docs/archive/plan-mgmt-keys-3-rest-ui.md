# Management Keys REST + Scopes + UI

Sub-plan 3 of 4 for the 0.20.0 management-keys + MCP feature. Adds `require_scope`, scope-maps the existing app routes, adds key CRUD endpoints with the kind/scope validity matrix, and the Keys UI (Settings + app detail). Design (source of truth — read §2, §4, §5, §7): `docs/superpowers/specs/2026-07-26-management-keys-mcp-design.md`.

⛔ **PREREQUISITE — `docs/plan-mgmt-keys-2-foundation.md` must be complete first** (same branch).

**Branch:** `feature/management-keys-mcp`

**Critical rule:** The entire existing test suite passes in every chunk. The ONLY pre-existing test file that may be modified is `tests/test_ui.py`, and only by ADDING tests for the new key forms — existing assertions and status codes unchanged. (`tests/test_api_keys.py` was created by sub-plan 2 and may be extended.) New REST tests go in the new file `tests/test_management_api.py`.

**Security invariant (design B1):** `require_scope` accepts a management-key Bearer token or HTTP Basic admin — it must NEVER read the session cookie. A cookie-authenticated state-changing API route is a CSRF hole the UI-form tokens do not cover.

**Testing:** `python -m pytest -x -q`. Lint: `ruff check . && ruff format --check .`

---

## Chunk 1: Gate + `require_scope` (`seesee/dependencies.py`, `seesee/routes/apps.py`, `tests/test_management_api.py`)

- [x] Step 1 (GATE): Run `test -f seesee/keys.py && grep -q "resolve_key" seesee/dependencies.py && echo GATE-OK`. If it does not print `GATE-OK`, **HALT** — sub-plan 2 has not run.
- [x] Step 2: Add to `seesee/dependencies.py`:

```python
def _verify_basic_admin(basic_credentials: HTTPBasicCredentials | None) -> str | None:
    """Constant-time Basic admin check. Returns username or None."""
    if basic_credentials is None or not settings.admin_password:
        return None
    username_correct = secrets.compare_digest(
        basic_credentials.username.lower().encode("utf-8"),
        settings.admin_username.lower().encode("utf-8"),
    )
    password_correct = secrets.compare_digest(
        basic_credentials.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )
    return basic_credentials.username if (username_correct and password_correct) else None


def require_scope(*required_scopes: str):
    """Dependency factory: management-key Bearer OR HTTP Basic admin.

    NEVER reads the session cookie — state-changing API routes must not be
    reachable with an ambient credential (design review B1). UI forms post to
    ui.py handlers (session + CSRF) which share service code with these routes.
    Basic admin implicitly holds all scopes. 401 = unresolvable credential;
    403 = resolved key missing a scope.
    """

    async def _dep(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
        basic_credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_scheme_optional)],
    ) -> keys.Principal:
        username = _verify_basic_admin(basic_credentials)
        if username is not None:
            return keys.Principal(
                key_id="admin", app_id=None, scopes=keys.ALL_SCOPES, label="admin"
            )
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            principal = await keys.resolve_key(credentials.credentials)
        except keys.KeyRevokedError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="API key revoked"
            ) from exc
        except keys.KeyExpiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired"
            ) from exc
        if principal is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        missing = [s for s in required_scopes if s not in principal.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {', '.join(missing)}",
            )
        return principal

    return _dep
```

- [x] Step 3: In `seesee/routes/apps.py`, change `list_apps`'s decorator from `dependencies=[Depends(require_admin)]` to `dependencies=[Depends(require_scope("apps:read"))]` (import `require_scope` from `seesee.dependencies`).
- [x] Step 4: Create `tests/test_management_api.py` with a module-level helper (mirroring `conftest.create_test_app` style):

```python
async def create_mgmt_key(scopes: list[str]) -> str:
    """Mint a management key directly and return its plaintext."""
    from seesee import keys

    _key_id, plaintext = await keys.create_key(
        label="test-mgmt", app_id=None, scopes=scopes, expires_at=None, created_by="test"
    )
    return plaintext
```

Tests:
  - `test_basic_admin_still_lists_apps` — `GET /api/v1/apps` with `admin_auth_header` → 200.
  - `test_mgmt_key_lists_apps` — key with `["apps:read"]`, `Authorization: Bearer <key>` → 200.
  - `test_missing_scope_403` — key with `["emails:read"]` → 403, detail contains `apps:read`.
  - `test_app_key_403_on_apps_read` — app key (create app, use its plaintext) → 403 (app keys can never hold `apps:*`).
  - `test_session_cookie_never_authenticates_api` — login via `POST /login` (session cookie now on the client), then `GET /api/v1/apps` with NO Authorization header → 401. **This is the B1 regression test.**
  - `test_no_credentials_401` — bare request → 401.
- [x] Step 5: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [x] Step 6: Commit: `git add seesee/dependencies.py seesee/routes/apps.py tests/test_management_api.py && git commit -m "feat(scopes): require_scope dependency (Bearer/Basic only, no cookies)"`

### ✅ Review Checkpoint — Chunk 1
- [ ] `require_scope`'s inner dependency takes NO `Request` parameter and never calls `_validate_session_cookie`: `grep -A8 "async def _dep" seesee/dependencies.py`
- [ ] `test_session_cookie_never_authenticates_api` exists and passes
- [ ] 403 detail names the missing scope
- [ ] `git diff HEAD~1 --name-only -- tests/` lists ONLY `tests/test_management_api.py`
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 2: Scope-map remaining app routes + `GET /apps/{id}` (`seesee/routes/apps.py`, `tests/test_management_api.py`)

- [x] Step 1: In `seesee/routes/apps.py`, replace `dependencies=[Depends(require_admin)]` route-by-route: `create_app` and `update_app` and `rotate_key` → `require_scope("apps:write")`; `purge_app_emails` and `delete_app` → `require_scope("apps:delete")`. Remove the now-unused `require_admin` import ONLY if no route in the file still uses it.
- [x] Step 2: In `create_app`, capture the minting principal for provenance: change the decorator-only dependency to a parameter `principal: Principal = Depends(require_scope("apps:write"))` (import `Principal` from `seesee.keys`), and in the `api_keys` INSERT added by sub-plan 2, replace the hardcoded `"admin"` `created_by` value with `principal.key_id` (Basic admin yields `"admin"`, a management key yields its key id). Do the same in `rotate_key`.
- [x] Step 3: Add `GET /api/v1/apps/{app_id}` (place it after `list_apps`; note FastAPI matches literal paths in registration order — `/apps/{app_id}` must not shadow anything since all other app routes have suffixes or different methods):

```python
@router.get(
    "/apps/{app_id}",
    response_model=AppResponse,
    dependencies=[Depends(require_scope("apps:read"))],
)
async def get_app(app_id: str) -> AppResponse:
    """Fetch a single app record. Requires apps:read."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, retention_degrade_to_text_days, "
        "retention_degrade_to_preview_days, created_at, last_activity_at "
        "FROM apps WHERE id = ?",
        (app_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return AppResponse(**dict(row))
```

- [x] Step 4: Extend `tests/test_management_api.py`:
  - `test_mgmt_key_creates_app` — key with `["apps:write"]` → `POST /api/v1/apps` 201, response contains a working `api_key` (Bearer-ingest one email with it); the created app's `api_keys` row has `created_by` equal to the management key's id (query the db).
  - `test_apps_write_cannot_delete` — same key → `DELETE /api/v1/apps/{id}` 403.
  - `test_apps_delete_can_delete` — key with `["apps:delete"]` → `DELETE` 200.
  - `test_get_single_app` — `GET /api/v1/apps/{id}` with `["apps:read"]` key → 200 with the app's fields; unknown id → 404.
- [x] Step 5: `python -m pytest -x -q` — full suite unmodified (`test_apps.py` proves Basic admin still works everywhere). `ruff check . && ruff format --check .`
- [x] Step 6: Commit: `git add seesee/routes/apps.py tests/test_management_api.py && git commit -m "feat(scopes): scope-map app routes; GET /api/v1/apps/{id}; created_by provenance"`

### ✅ Review Checkpoint — Chunk 2
- [ ] `grep -c "require_scope" seesee/routes/apps.py` ≥ 6 (list, create, update, rotate, purge, delete, get)
- [ ] `grep -n "require_admin" seesee/routes/apps.py` shows no remaining app-route usage
- [ ] DELETE routes require `apps:delete`, not `apps:write`
- [ ] `created_by` comes from the principal, not a hardcoded string
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 3: Key CRUD REST (`seesee/routes/apps.py`, `seesee/models.py`, `seesee/timezone.py`, `tests/test_management_api.py`)

- [x] Step 1: Add to `seesee/models.py` (following its existing pydantic model style):

```python
class KeyCreateRequest(BaseModel):
    """Mint a new key for an app."""

    label: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default=["emails:read", "emails:write"])
    expires_days: int | None = Field(default=None, ge=1, le=3650)


class KeyMetadata(BaseModel):
    """Key metadata — never includes hashes or plaintext."""

    id: str
    label: str
    key_prefix: str
    scopes: list[str]
    created_by: str
    created_at: str
    last_used_at: str | None
    expires_at: str | None
    revoked_at: str | None


class KeyCreateResponse(KeyMetadata):
    """Returned once at mint time — the only time plaintext is available."""

    api_key: str
```

- [x] Step 2: Add three routes to `seesee/routes/apps.py`:

```python
@router.get(
    "/apps/{app_id}/keys",
    response_model=list[KeyMetadata],
    dependencies=[Depends(require_scope("apps:read"))],
)
async def list_app_keys(app_id: str) -> list[KeyMetadata]:
    """List key metadata for an app. Requires apps:read."""
    db = await get_db()
    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return [KeyMetadata(**k) for k in await keys.list_keys(app_id)]


@router.post(
    "/apps/{app_id}/keys",
    response_model=KeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_app_key(
    app_id: str,
    request: KeyCreateRequest,
    principal: Principal = Depends(require_scope("apps:write")),
) -> KeyCreateResponse:
    """Mint an additional key for an app (safe rotation: mint, deploy, revoke old)."""
    db = await get_db()
    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    expires_at = None
    if request.expires_days is not None:
        expires_at = iso_in_days(request.expires_days)
    try:
        key_id, plaintext = await keys.create_key(
            label=request.label,
            app_id=app_id,
            scopes=request.scopes,
            expires_at=expires_at,
            created_by=principal.key_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    metadata = [k for k in await keys.list_keys(app_id) if k["id"] == key_id][0]
    return KeyCreateResponse(**metadata, api_key=plaintext)


@router.delete(
    "/apps/{app_id}/keys/{key_id}",
    dependencies=[Depends(require_scope("apps:write"))],
)
async def revoke_app_key(app_id: str, key_id: str) -> dict:
    """Revoke one of an app's keys.

    404 unless the key exists AND belongs to this app — revocation by bare
    key_id would let apps:write revoke management keys (lockout/DoS). There
    is deliberately no REST route that revokes a management key.
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT id FROM api_keys WHERE id = ? AND app_id = ?", (key_id, app_id)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await keys.revoke_key(key_id)
    return {"message": "Key revoked"}
```

Add a tiny helper `iso_in_days(days: int) -> str` to `seesee/timezone.py` (UTC now + N days in `%Y-%m-%dT%H:%M:%S`), implemented with `datetime.now(tz=timezone.utc) + timedelta(days=days)`; import it in `apps.py`. Import `keys`, `Principal`, and the new models.

- [x] Step 3: Extend `tests/test_management_api.py`:
  - `test_mint_and_use_app_key` — POST keys → 201 with `api_key` plaintext + metadata; new key ingests an email.
  - `test_two_step_rotation` — mint new key, verify BOTH keys work simultaneously (overlap window), revoke the old key id via DELETE, old 401s, new still works.
  - `test_cross_app_revoke_404` — two apps; revoking app A's key via app B's path → 404, key still active.
  - `test_mgmt_key_not_revocable_via_rest` — DELETE `/apps/{id}/keys/{mgmt_key_id}` → 404 (management keys have `app_id NULL`, can never match).
  - `test_matrix_422` — POST keys with `scopes=["apps:write"]` → 422 naming the scope.
  - `test_key_metadata_never_leaks` — GET keys response has no `key_hash`/`api_key` fields; `expires_days` round-trips to a future `expires_at`.
- [x] Step 4: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [x] Step 5: Commit: `git add seesee/routes/apps.py seesee/models.py seesee/timezone.py tests/test_management_api.py && git commit -m "feat(keys): app-key CRUD endpoints with validity matrix + belongs-to-app revoke"`

### ✅ Review Checkpoint — Chunk 3
- [ ] `revoke_app_key` matches `id = ? AND app_id = ?` in SQL (belongs-to-app enforced)
- [ ] Mint failures from `ValueError` surface as 422 with the message
- [ ] `KeyCreateResponse` is the ONLY response model containing plaintext
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 4: Settings UI — management keys (`seesee/routes/ui.py`, `seesee/templates/settings.html`, `tests/test_ui.py`)

- [x] Step 1: In `seesee/routes/ui.py` `settings_page`, add to the template context: `mgmt_keys=await keys.list_keys(None)` and the flash (existing `_pop_flash` already flows through). Import `keys` and `iso_in_days`.
- [x] Step 2: Add two session+CSRF handlers to `ui.py`:

```python
@router.post("/settings/keys")
async def create_mgmt_key_ui(
    request: Request,
    user: str = Depends(require_session),
    _csrf: None = Depends(require_csrf),
    label: str = Form(...),
    scopes: list[str] = Form([]),
    expires: str = Form("90"),
) -> RedirectResponse:
    """Mint a management key from the Settings page. Plaintext flashed once."""
    expires_at = None if expires == "never" else iso_in_days(int(expires))
    response = RedirectResponse(url="/settings", status_code=303)
    try:
        _key_id, plaintext = await keys.create_key(
            label=label,
            app_id=None,
            scopes=scopes,
            expires_at=expires_at,
            created_by="admin",
        )
    except ValueError as exc:
        _set_flash(response, {"key_error": str(exc)})
        return response
    _set_flash(response, {"new_mgmt_key": plaintext, "new_mgmt_key_label": label})
    return response


@router.post("/settings/keys/{key_id}/revoke")
async def revoke_mgmt_key_ui(
    key_id: str,
    request: Request,
    user: str = Depends(require_session),
    _csrf: None = Depends(require_csrf),
) -> RedirectResponse:
    """Revoke a management key. Only management keys — app keys are revoked
    from their app's detail page."""
    db = await get_db()
    cursor = await db.execute("SELECT id FROM api_keys WHERE id = ? AND app_id IS NULL", (key_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await keys.revoke_key(key_id)
    return RedirectResponse(url="/settings", status_code=303)
```

(`expires` select values: `"30"`, `"90"`, `"365"`, `"never"`. Guard `int(expires)` with a try/except ValueError → 422 HTTPException.)

- [x] Step 3: In `seesee/templates/settings.html`, add an "API Keys" card (match the page's existing card markup/classes; include the CSRF hidden input in both forms):
  - Flash display: if `flash.new_mgmt_key`, show the plaintext in a copyable `<code>` block with the standing warning "Shown once — store it now." If `flash.key_error`, show the error.
  - Table over `mgmt_keys`: label, `key_prefix` rendered as `ss_mgmt_{{ key.key_prefix }}…`, scopes (badges), created_by, last_used_at, expires_at, and a revoke button (its own small form POSTing to `/settings/keys/{{ key.id }}/revoke`) for rows where `revoked_at` is none. Revoked rows render muted with a "revoked" badge.
  - Create form POSTing to `/settings/keys`: label text input (required); four checkboxes — `emails:read` (checked), `apps:read` (checked), `apps:write` (unchecked, helper text: **"Can mint app keys — transitively grants access to all email in this instance"**), `apps:delete` (unchecked, helper text: **"Destructive: can delete apps and purge all their email"** styled as a warning); expiry `<select name="expires">` with options 30 / **90 (selected)** / 365 / never.
- [x] Step 4: Add tests to `tests/test_ui.py` (ADD only — do not touch existing tests; reuse the `csrf_form` helper):
  - `test_settings_shows_keys_section` — logged-in GET `/settings` contains `API Keys`.
  - `test_create_mgmt_key_ui_flow` — POST `/settings/keys` with `csrf_form({"label": "agent", "scopes": ["emails:read", "apps:read"], "expires": "90"})` → 303; following GET `/settings` shows an `ss_mgmt_` plaintext once (flash), and the table lists the label.
  - `test_create_mgmt_key_invalid_scope_shows_error` — scopes `["emails:write"]` → flash error rendered, no key created.
  - `test_revoke_mgmt_key_ui` — create, then POST revoke → 303; row shows revoked.
  - `test_revoke_app_key_via_settings_404` — an app's key id POSTed to `/settings/keys/{id}/revoke` → 404.
- [x] Step 5: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [x] Step 6: Commit: `git add seesee/routes/ui.py seesee/templates/settings.html tests/test_ui.py && git commit -m "feat(keys): management-keys UI on Settings (90-day default, scope warnings)"`

### ✅ Review Checkpoint — Chunk 4
- [ ] The expiry select defaults to 90 days (`selected` on the 90 option)
- [ ] `apps:delete` and `apps:write` render UNCHECKED with their warning texts present in the template
- [ ] Both new forms contain the `csrf_token` hidden input
- [ ] `/settings/keys/{id}/revoke` SQL filters `app_id IS NULL`
- [ ] `git diff HEAD~1 -- tests/test_ui.py` shows only ADDED test functions
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 5: App detail keys UI (`seesee/routes/ui.py`, `seesee/templates/app_detail.html`, `tests/test_ui.py`)

- [x] Step 1: In `ui.py` `app_detail`, add `app_keys=await keys.list_keys(app_id)` to the template context.
- [x] Step 2: Add two handlers mirroring Chunk 4's shape: `POST /apps/{app_id}/keys` (`create_app_key_ui`: label + scope checkboxes limited to `emails:read`/`emails:write`, no expiry select — app keys default to no expiry; flash `{"new_app_key": plaintext}`; redirect to `/apps/{app_id}`) and `POST /apps/{app_id}/keys/{key_id}/revoke` (`revoke_app_key_ui`: 404 unless `SELECT id FROM api_keys WHERE id = ? AND app_id = ?` matches; redirect back). Both: `require_session` + `require_csrf`, `created_by="admin"`, ValueError → flash error.
- [x] Step 3: In `app_detail.html`:
  - Add an "API Keys" card above the existing danger-zone/rotate area: table over `app_keys` (label, `ss_{{ key.key_prefix }}…`, scopes, created_by, last used, revoke button forms) + a mint form (label input; `emails:read`/`emails:write` checkboxes, both checked by default). Include CSRF hidden inputs. Flash display for `new_app_key` plaintext (copyable, shown once).
  - Relabel the existing rotate button text to `Rotate key (immediately invalidates the current key)` and add helper text pointing at the keys table: `Prefer minting a second key, deploying it, then revoking the old one — zero-downtime rotation.`
- [x] Step 4: Add tests to `tests/test_ui.py`:
  - `test_app_detail_shows_keys_table` — app detail GET lists the default key's prefix.
  - `test_mint_app_key_ui_flow` — POST mint → 303 → flash shows `ss_` plaintext; table gains a row.
  - `test_revoke_app_key_ui` — revoke the minted key → row shows revoked; SMTP/REST rejection is covered by sub-plan 2 tests.
  - `test_cross_app_revoke_ui_404` — key id from another app → 404.
- [ ] Step 5: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [ ] Step 6: Commit: `git add seesee/routes/ui.py seesee/templates/app_detail.html tests/test_ui.py && git commit -m "feat(keys): per-app keys UI with mint/revoke; rotate relabeled as destructive"`

### ✅ Review Checkpoint — Chunk 5
- [ ] App-key mint form offers ONLY `emails:read`/`emails:write` checkboxes
- [ ] Revoke handler SQL matches both `id` and `app_id`
- [ ] Rotate button text now includes "immediately invalidates"
- [ ] `git diff HEAD~2 -- tests/test_ui.py` shows only ADDED test functions
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 6: Version + docs (`pyproject.toml`, `seesee/__init__.py`, `CHANGELOG.md`, `README.md`)

- [x] Step 1: Bump to `0.19.19-dev` in `pyproject.toml` and `seesee/__init__.py`.
- [x] Step 2: `CHANGELOG.md` `[Unreleased]` → `### Added`: `- Management API keys: scoped (emails:read/apps:read/apps:write/apps:delete), labeled, expiring, individually revocable; key CRUD REST endpoints; Keys UI on Settings and app detail; safe two-step rotation`
- [x] Step 3: In `README.md`, add a short "Management API keys" subsection under the existing API/usage docs: what they are (`ss_mgmt_` Bearer credentials for automation/agents), the CLI bootstrap one-liner, the two-step rotation flow, and the sentence: `A key with apps:write can mint app keys and therefore transitively read all email in the instance — scope keys per agent and prefer read-only keys for debugging.`
- [x] Step 4: `python -m pytest -x -q`.
- [x] Step 5: Commit: `git add pyproject.toml seesee/__init__.py CHANGELOG.md README.md && git commit -m "chore: bump 0.19.19-dev; changelog + README for management keys"`

### ✅ Review Checkpoint — Chunk 6
- [ ] Versions match: `python -m pytest tests/test_version_sync.py -q`
- [ ] README contains the `apps:write` transitivity warning verbatim
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean
