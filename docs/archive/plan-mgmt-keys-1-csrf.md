# CSRF Tokens on Session-Authenticated UI Form POSTs

Sub-plan 1 of 4 for the 0.20.0 management-keys + MCP feature. Adds signed CSRF tokens to every session-authenticated UI form POST, so the key-management forms added in sub-plan 3 are born protected. Design: `docs/superpowers/specs/2026-07-26-management-keys-mcp-design.md` §8.

**Branch:** `feature/management-keys-mcp`

**Critical rule:** The entire existing test suite must pass in every chunk. The ONLY existing test file that may be modified in this plan is `tests/test_ui.py`, and only by adding CSRF-token plumbing through the `csrf_form()` helper — existing assertions and expected status codes must not change.

**Testing:** `python -m pytest -x -q` (from the repo root). Lint before committing: `ruff check . && ruff format --check .`

**Project context:** FastAPI + Jinja2 + SQLite. Session auth is a signed cookie (`itsdangerous`, see `seesee/auth.py`). The session cookie is already `SameSite=Lax`; CSRF tokens are defense in depth. `/login` is credential-authenticated (no session yet) and `/logout` is a harmless no-op target — neither gets CSRF validation.

---

## Chunk 1: CSRF module + Jinja global (`seesee/csrf.py`, `seesee/main.py`, `tests/test_csrf.py`)

Create the token helpers and dependency; register a template-callable token generator.

- [x] Step 1: Create `seesee/csrf.py`:

```python
"""Signed CSRF tokens for session-authenticated UI form POSTs.

Tokens are signed with the session secret and bound to the session username.
Bearer-authenticated REST and MCP routes never use ambient credentials and
therefore never require CSRF tokens.
"""

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from seesee.config import settings
from seesee.dependencies import _get_secret_key, _validate_session_cookie

CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
_CSRF_SALT = "seesee-csrf"


def make_csrf_token(username: str, secret_key: str) -> str:
    """Create a signed CSRF token bound to the given session username."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_CSRF_SALT)
    return serializer.dumps({"u": username})


def validate_csrf_token(token: str, username: str, secret_key: str, max_age_seconds: int) -> bool:
    """Return True if the token is validly signed and bound to this username."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_CSRF_SALT)
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("u") == username


def csrf_token_for(request: Request) -> str:
    """Template helper: return a CSRF token for the current session, or ''.

    Registered as a Jinja global so templates can embed tokens without every
    GET handler passing one through its context.
    """
    username = _validate_session_cookie(request)
    if username is None:
        return ""
    return make_csrf_token(username, _get_secret_key())


async def require_csrf(request: Request) -> None:
    """FastAPI dependency: reject session POSTs lacking a valid CSRF token.

    Reads the token from the X-CSRF-Token header (fetch() callers) or the
    csrf_token form field (regular form posts). Starlette caches form parsing,
    so reading the form here does not conflict with Form(...) parameters.
    """
    username = _validate_session_cookie(request)
    if username is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    token = request.headers.get(CSRF_HEADER_NAME)
    if not token:
        form = await request.form()
        value = form.get(CSRF_FIELD_NAME, "")
        token = value if isinstance(value, str) else ""
    max_age = settings.session_max_age_days * 86400
    if not token or not validate_csrf_token(token, username, _get_secret_key(), max_age):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid"
        )
```

- [x] Step 2: In `seesee/main.py`, inside the `if _templates_dir.is_dir():` block (right after the `templates.env.globals["build_display"] = ...` assignment), add:

```python
    from seesee.csrf import csrf_token_for

    templates.env.globals["csrf_token_for"] = csrf_token_for
```

- [x] Step 3: Create `tests/test_csrf.py` with unit tests for the token round-trip (endpoint tests come in Chunk 4):

```python
"""CSRF token tests — unit round-trip now; endpoint enforcement tests below."""

from seesee.csrf import make_csrf_token, validate_csrf_token


def test_csrf_round_trip():
    token = make_csrf_token("admin", "sekrit")
    assert validate_csrf_token(token, "admin", "sekrit", 3600)


def test_csrf_wrong_username_rejected():
    token = make_csrf_token("admin", "sekrit")
    assert not validate_csrf_token(token, "other", "sekrit", 3600)


def test_csrf_wrong_secret_rejected():
    token = make_csrf_token("admin", "sekrit")
    assert not validate_csrf_token(token, "admin", "different", 3600)


def test_csrf_garbage_rejected():
    assert not validate_csrf_token("not-a-token", "admin", "sekrit", 3600)
```

- [x] Step 4: Run `python -m pytest -x -q` — full suite passes (no behavior change yet).
- [x] Step 5: Run `ruff check . && ruff format --check .` — clean.
- [x] Step 6: Commit: `git add seesee/csrf.py seesee/main.py tests/test_csrf.py && git commit -m "feat(csrf): signed CSRF token module and template helper"`

### ✅ Review Checkpoint — Chunk 1
- [ ] `python -c "from seesee.csrf import make_csrf_token, validate_csrf_token, csrf_token_for, require_csrf"` succeeds
- [ ] `grep -n "csrf_token_for" seesee/main.py` shows the Jinja global registration
- [ ] `require_csrf` checks the header first, then the form field; rejects with 403 in both failure paths
- [ ] No stubs, TODOs, or placeholder code
- [ ] No changes outside `seesee/csrf.py`, `seesee/main.py`, `tests/test_csrf.py`
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean (runner-owned plan/state files excepted)

---

## Chunk 2: Hidden token fields, part A (`seesee/templates/base.html`, `seesee/templates/apps.html`, `seesee/templates/app_detail.html`)

Embed tokens in forms. Inert until Chunk 4 enforces validation, so tests stay green.

- [x] Step 1: In `base.html`, add inside `<head>` (near the other meta tags): `<meta name="csrf-token" content="{{ csrf_token_for(request) }}">`
- [x] Step 2: In `base.html`, inside the logout form (`<form method="post" action="/logout">`, ~line 100), add as its first child: `<input type="hidden" name="csrf_token" value="{{ csrf_token_for(request) }}">` (logout is not validated, but the uniform field keeps templates consistent).
- [x] Step 3: In `apps.html`, add the same hidden input as the first child of all three POST forms: the create form (`action="/apps"`, ~line 103), the rotate-confirm form (`:action="'/apps/' + confirmRotate + '/rotate-key'"`, ~line 143), and the delete-confirm form (`:action="'/apps/' + confirmDelete + '/delete'"`, ~line 160).
- [x] Step 4: In `app_detail.html`, add the same hidden input as the first child of all five POST forms: rename (~line 49), settings (~line 312), rotate-key (~line 397), purge (~line 414), delete (~line 431).
- [x] Step 5: Run `python -m pytest -x -q` — full suite passes.
- [x] Step 6: Commit: `git add seesee/templates && git commit -m "feat(csrf): embed CSRF tokens in base, apps, and app_detail forms"`

### ✅ Review Checkpoint — Chunk 2
- [ ] `grep -c "csrf_token" seesee/templates/apps.html` returns 3; `grep -c "csrf_token" seesee/templates/app_detail.html` returns 5
- [ ] `grep -n "csrf-token" seesee/templates/base.html` shows the meta tag; `grep -c "csrf_token_for" seesee/templates/base.html` returns 2 (meta + logout)
- [ ] Every added input uses exactly `name="csrf_token"` and `value="{{ csrf_token_for(request) }}"`
- [ ] No changes outside the three named templates
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 3: Hidden token fields, part B (`seesee/templates/emails.html`, `seesee/templates/email_detail.html`, `seesee/templates/settings.html`)

- [x] Step 1: In `emails.html`, add the hidden input as the first child of the bulk-delete form (`action="/emails/bulk-delete"`, ~line 79).
- [x] Step 2: In `email_detail.html`, add the hidden input as the first child of the delete form (`action="/emails/{{ email.id }}/delete"`, ~line 64).
- [x] Step 3: In `settings.html`, the cleanup button (~line 136) POSTs via `fetch('/settings/cleanup', { method: 'POST' })`. Change the fetch options to send the token from the meta tag as a header:

```
fetch('/settings/cleanup', { method: 'POST', headers: { 'X-CSRF-Token': document.querySelector('meta[name=csrf-token]').content } })
```

- [x] Step 4: Run `python -m pytest -x -q` — full suite passes.
- [x] Step 5: Commit: `git add seesee/templates && git commit -m "feat(csrf): embed CSRF tokens in emails, email_detail, settings"`

### ✅ Review Checkpoint — Chunk 3
- [ ] `grep -c "csrf_token" seesee/templates/emails.html` returns 1; same for `email_detail.html`
- [ ] `grep -n "X-CSRF-Token" seesee/templates/settings.html` shows the fetch header sourced from the meta tag
- [ ] No changes outside the three named templates
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 4: Enforce validation (`seesee/routes/ui.py`, `tests/test_csrf.py`, `tests/test_ui.py`)

Turn validation on for all nine session-authenticated POST handlers, and plumb tokens through the UI tests.

- [x] Step 1: In `seesee/routes/ui.py`, add to the imports: `from seesee.csrf import require_csrf`.
- [x] Step 2: Add the parameter `_csrf: None = Depends(require_csrf),` immediately after the `user: str = Depends(require_session),` parameter in exactly these nine handlers: `create_app_ui`, `rotate_key_ui`, `rename_app_ui`, `update_app_settings_ui`, `purge_app_emails_ui`, `delete_app_ui`, `bulk_delete_emails_ui`, `delete_email_ui`, `run_cleanup_ui`. Do NOT touch `login_submit` or `logout`.
- [x] Step 3: In `tests/test_ui.py`, add near the top (after existing imports):

```python
from seesee.csrf import CSRF_FIELD_NAME, make_csrf_token


def csrf_form(data: dict | None = None) -> dict:
    """Merge a valid CSRF token into form data for session-authenticated POSTs."""
    token = make_csrf_token("admin", "testpassword")
    return {**(data or {}), CSRF_FIELD_NAME: token}
```

- [x] Step 4: In `tests/test_ui.py`, for every `client.post(...)` to a session-authenticated UI route (all POSTs except `/login` and `/logout`), wrap the existing `data=` argument: `data={...}` becomes `data=csrf_form({...})`, and calls with no `data=` argument gain `data=csrf_form()`. Change nothing else — no assertion, status code, or fixture changes.
- [x] Step 5: Append endpoint tests to `tests/test_csrf.py`:

```python
import pytest
from httpx import AsyncClient

from seesee.csrf import CSRF_FIELD_NAME
from tests.conftest import create_test_app


async def _login(client: AsyncClient) -> None:
    response = await client.post("/login", data={"username": "admin", "password": "testpassword"})
    assert response.status_code == 303


@pytest.mark.anyio
async def test_session_post_without_token_rejected(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    await _login(client)
    response = await client.post(f"/apps/{app_data['id']}/rename", data={"name": "Renamed"})
    assert response.status_code == 403


@pytest.mark.anyio
async def test_session_post_with_token_accepted(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    await _login(client)
    token = make_csrf_token("admin", "testpassword")
    response = await client.post(
        f"/apps/{app_data['id']}/rename",
        data={"name": "Renamed", CSRF_FIELD_NAME: token},
    )
    assert response.status_code == 303


@pytest.mark.anyio
async def test_header_token_accepted(client):
    await _login(client)
    token = make_csrf_token("admin", "testpassword")
    response = await client.post("/settings/cleanup", headers={"X-CSRF-Token": token})
    assert response.status_code == 303


@pytest.mark.anyio
async def test_bearer_rest_unaffected(client, admin_auth_header):
    response = await client.post(
        "/api/v1/apps", json={"name": "No CSRF Needed"}, headers=admin_auth_header
    )
    assert response.status_code == 201
```

(Adjust the `pytest.mark.anyio` marker to match whatever marker/asyncio mode the existing test files use — copy the pattern from `tests/test_ui.py` exactly.)

- [x] Step 6: Run `python -m pytest -x -q` — full suite passes.
- [x] Step 7: Run `git diff tests/test_ui.py` and confirm the diff contains ONLY the helper block and `csrf_form(` wrappings — no assertion or status-code changes.
- [x] Step 8: Commit: `git add seesee/routes/ui.py tests/test_csrf.py tests/test_ui.py && git commit -m "feat(csrf): enforce CSRF validation on session POST handlers"`

### ✅ Review Checkpoint — Chunk 4
- [ ] `grep -c "Depends(require_csrf)" seesee/routes/ui.py` returns 9
- [ ] `grep -n "require_csrf" seesee/routes/ui.py` shows NO usage on `login_submit` or `logout`
- [ ] `git diff HEAD~1 -- tests/test_ui.py` shows only token plumbing (helper + `csrf_form(` wraps); every `assert` line in the diff context is unchanged
- [ ] Session POST without token → 403 (run `python -m pytest tests/test_csrf.py -q`)
- [ ] No changes outside `seesee/routes/ui.py`, `tests/test_csrf.py`, `tests/test_ui.py`
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 5: Version + docs (`pyproject.toml`, `seesee/__init__.py`, `CHANGELOG.md`, `ROADMAP.md`)

- [x] Step 1: Bump version to `0.19.17-dev` in BOTH `pyproject.toml` (`version = "0.19.17-dev"`) and `seesee/__init__.py` (`__version__ = "0.19.17-dev"`). (`tests/test_version_sync.py` enforces they match.)
- [x] Step 2: In `CHANGELOG.md` under `## [Unreleased]`, add under `### Added` (create the subheading under `[Unreleased]` only if not present): `- CSRF tokens on all session-authenticated UI form POSTs (signed with the session secret, bound to the session user; fetch() callers send X-CSRF-Token)`
- [x] Step 3: In `ROADMAP.md`, find the CSRF line (~line 154, listed as a Phase 3.0 known gap) and mark it complete with a `✅` and the text `(shipped in 0.20.0 cycle — CSRF tokens on all session POST handlers)`.
- [x] Step 4: Run `python -m pytest -x -q` — full suite passes (including `test_version_sync.py`).
- [x] Step 5: Commit: `git add pyproject.toml seesee/__init__.py CHANGELOG.md ROADMAP.md && git commit -m "chore: bump to 0.19.17-dev; changelog + roadmap for CSRF"`

### ✅ Review Checkpoint — Chunk 5
- [ ] `grep version pyproject.toml | head -1` and `grep __version__ seesee/__init__.py` both show `0.19.17-dev`
- [ ] `grep -n "CSRF" CHANGELOG.md` shows the new entry under `[Unreleased]`
- [ ] `grep -n "CSRF" ROADMAP.md` shows the item marked complete
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean
