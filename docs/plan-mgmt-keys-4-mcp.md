# MCP Server at /mcp

Sub-plan 4 of 4 for the 0.20.0 management-keys + MCP feature. Mounts a scope-aware MCP server into the FastAPI app. The SDK surface below was **verified end-to-end against `mcp==1.26.0`** (design §6 "Verified SDK surface" — read it before implementing; do not improvise different mounting mechanics).

⛔ **PREREQUISITE — `docs/plan-mgmt-keys-3-rest-ui.md` must be complete first** (same branch).

**Branch:** `feature/management-keys-mcp`

**Critical rule:** The entire existing test suite passes in every chunk; NO existing test file may be modified in this plan. New tests go in `tests/test_mcp.py`.

**Security invariants (design §6, normative):** (1) auth runs in pure-ASGI middleware BEFORE any SDK code parses the body; (2) any principal with `app_id IS NOT NULL` is rejected 401 regardless of scopes; (3) the principal is resolved per request, never cached; (4) `delete_app`/`purge_emails` do not exist as tools; (5) one `TOOL_SCOPES` dict drives both `tools/list` filtering and dispatch.

**Testing:** `python -m pytest -x -q`. Lint: `ruff check . && ruff format --check .`

---

## Chunk 1: Gate + MCP module with email tools (`pyproject.toml`, `seesee/config.py`, `seesee/mcp_server.py`)

- [ ] Step 1 (GATE): Run `grep -q "def require_scope" seesee/dependencies.py && test -f seesee/keys.py && echo GATE-OK`. If it does not print `GATE-OK`, **HALT** — sub-plan 3 has not run.
- [ ] Step 2: In `pyproject.toml` `dependencies`, add `"mcp>=1.26,<2",` after the `itsdangerous` line. Run `pip install -e ".[dev]"` (or `pip install "mcp>=1.26,<2"`) so the SDK is importable.
- [ ] Step 3: In `seesee/config.py`, add under the `# SMTP Ingest` block:

```python
    # MCP server (mounted at /mcp; Bearer ss_mgmt_ keys only)
    mcp_enabled: bool = True
```

- [ ] Step 4: Create `seesee/mcp_server.py`:

```python
"""MCP server — provisioning and email debugging over the Model Context Protocol.

Mounted at /mcp (streamable HTTP, stateless, JSON responses). Auth is the same
Bearer ss_mgmt_ credential resolved by seesee.keys — MCP is a new transport over
existing authorization, not a new authorization system.

Verified against mcp==1.26.0; see the design spec's "Verified SDK surface"
section before changing any mounting mechanics.
"""

import contextvars
import json

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool
from starlette.responses import JSONResponse

from seesee import keys
from seesee.config import settings
from seesee.database import get_db

# Single source of truth: drives BOTH tools/list filtering and dispatch checks.
# A test asserts every registered tool has exactly one entry here.
TOOL_SCOPES: dict[str, str] = {
    "search_emails": "emails:read",
    "get_email": "emails:read",
    "list_recent_failures": "emails:read",
    "list_apps": "apps:read",
    "get_app": "apps:read",
    "get_integration_env": "apps:read",
    "create_app": "apps:write",
    "create_app_key": "apps:write",
    "revoke_app_key": "apps:write",
}

_current_principal: contextvars.ContextVar[keys.Principal | None] = contextvars.ContextVar(
    "seesee_mcp_principal", default=None
)


class ScopedFastMCP(FastMCP):
    """FastMCP with per-request scope filtering and dispatch-time checks.

    Overrides the PUBLIC list_tools/call_tool methods — FastMCP registers
    exactly these as its protocol handlers (verified in _setup_handlers).
    """

    async def list_tools(self) -> list[Tool]:
        principal = _current_principal.get()
        tools = await super().list_tools()
        if principal is None:
            return []
        return [t for t in tools if TOOL_SCOPES[t.name] in principal.scopes]

    async def call_tool(self, name, arguments):
        principal = _current_principal.get()
        required = TOOL_SCOPES.get(name)
        if principal is None or required is None or required not in principal.scopes:
            raise PermissionError(
                f"Tool {name!r} requires scope {required!r}, which this key does not hold"
            )
        return await super().call_tool(name, arguments)


class MCPAuthMiddleware:
    """Pure-ASGI gate in front of the SDK: no unauthenticated bytes reach
    JSON-RPC parsing. Resolves the Bearer per request (revocation applies on
    the next request), rejects app-bound principals regardless of scopes, and
    stashes the Principal in a contextvar for the tool layer."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if not settings.mcp_enabled:
            response = JSONResponse({"detail": "MCP is disabled"}, status_code=404)
            return await response(scope, receive, send)
        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        principal = None
        detail = "Invalid or missing API key"
        if token:
            try:
                principal = await keys.resolve_key(token)
            except keys.KeyRevokedError:
                detail = "API key revoked"
            except keys.KeyExpiredError:
                detail = "API key expired"
        if principal is None:
            response = JSONResponse({"detail": detail}, status_code=401)
            return await response(scope, receive, send)
        if principal.app_id is not None:
            # App keys are hard-bound to one app; MCP tools are instance-wide.
            # Kind comes from the ROW (app_id), never the token's text.
            response = JSONResponse(
                {"detail": "Management API key required"}, status_code=401
            )
            return await response(scope, receive, send)
        var_token = _current_principal.set(principal)
        try:
            return await self.app(scope, receive, send)
        finally:
            _current_principal.reset(var_token)


_EMAIL_SUMMARY_COLUMNS = (
    "id, app_id, to_addresses, from_address, subject, body_preview, "
    "status, provider, ingest_method, logged_at"
)


# emails_fts duplicates several emails column names (subject, to_addresses, ...),
# so every selected column must be e.-prefixed when the FTS join is present.
_EMAIL_SUMMARY_SELECT = ", ".join(
    f"e.{col.strip()}" for col in _EMAIL_SUMMARY_COLUMNS.split(",")
)


async def search_emails(
    query: str = "", app_id: str = "", status: str = "", limit: int = 20
) -> str:
    """Search logged emails (FTS5 over subject/body/addresses). All filters
    optional. Mirror the join/condition shape of routes/emails.py:list_emails —
    the FTS table is joined UNALIASED because `emails_fts MATCH ?` names the
    table."""
    limit = max(1, min(int(limit), 100))
    conditions, params = [], []
    joins = ""
    if query:
        joins = "JOIN emails_fts ON emails_fts.rowid = e.rowid"
        conditions.append("emails_fts MATCH ?")
        params.append(query)
    if app_id:
        conditions.append("e.app_id = ?")
        params.append(app_id)
    if status:
        conditions.append("e.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    db = await get_db()
    cursor = await db.execute(
        f"SELECT {_EMAIL_SUMMARY_SELECT} "  # noqa: S608
        f"FROM emails e {joins} {where} ORDER BY e.logged_at DESC LIMIT ?",
        (*params, limit),
    )
    rows = await cursor.fetchall()
    return json.dumps([dict(r) for r in rows], default=str)


async def get_email(email_id: str) -> str:
    """Fetch one email in full. Body content honors the app's body_storage_mode
    and any degradation already applied — this tool never bypasses them."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
    row = await cursor.fetchone()
    if row is None:
        raise ValueError(f"No email with id {email_id!r}")
    return json.dumps(dict(row), default=str)


async def list_recent_failures(limit: int = 20) -> str:
    """Recent emails with status='failed', newest first, with error messages."""
    limit = max(1, min(int(limit), 100))
    db = await get_db()
    cursor = await db.execute(
        f"SELECT {_EMAIL_SUMMARY_COLUMNS}, error_message FROM emails "  # noqa: S608
        "WHERE status = 'failed' ORDER BY logged_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return json.dumps([dict(r) for r in rows], default=str)


def create_mcp_server() -> ScopedFastMCP:
    """Build a fresh server instance.

    A factory (not only a module singleton) because the SDK's
    session_manager.run() is once-per-instance — main.py builds one at import;
    each test builds its own.
    """
    server = ScopedFastMCP(
        "seesee",
        instructions=(
            "SeeSee sent-email log. Provision apps and debug email delivery. "
            "Destructive operations (delete app, purge emails) are deliberately "
            "not exposed over MCP."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
    )
    server.tool()(search_emails)
    server.tool()(get_email)
    server.tool()(list_recent_failures)
    return server


def build_mcp_asgi_app(server: ScopedFastMCP):
    """Wrap the SDK's Starlette app in the auth gate. Mount result at /mcp."""
    return MCPAuthMiddleware(server.streamable_http_app())
```

- [ ] Step 5: `python -c "from seesee.mcp_server import create_mcp_server, build_mcp_asgi_app, TOOL_SCOPES"`; then `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [ ] Step 6: Commit: `git add pyproject.toml seesee/config.py seesee/mcp_server.py && git commit -m "feat(mcp): scoped MCP server module with email debugging tools"`

### ✅ Review Checkpoint — Chunk 1
- [ ] `pyproject.toml` pins `mcp>=1.26,<2`
- [ ] `ScopedFastMCP` overrides only PUBLIC methods (`list_tools`, `call_tool`) — `grep -n "_mcp_server" seesee/mcp_server.py` finds nothing
- [ ] `MCPAuthMiddleware` rejects `principal.app_id is not None` with 401 BEFORE the wrapped app is called
- [ ] `FastMCP(...)` is constructed with `stateless_http=True, json_response=True, streamable_http_path="/"` and NO `transport_security` argument
- [ ] No stubs; the three email tools run real queries
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 2: Mount + lifespan + wire tests (`seesee/main.py`, `tests/test_mcp.py`)

- [ ] Step 1: In `seesee/main.py`, build and mount the server (module level, after the route registrations):

```python
from seesee.mcp_server import build_mcp_asgi_app, create_mcp_server

mcp_server = create_mcp_server()
app.mount("/mcp", build_mcp_asgi_app(mcp_server))
```

(Mount unconditionally; `MCPAuthMiddleware` returns 404 at request time when `settings.mcp_enabled` is false — this keeps the toggle runtime-testable.)

- [ ] Step 2: Replace the `lifespan` function in `main.py` with exactly this (the `mcp_server` global is defined later in the module; the lifespan body only runs at startup, after the module has fully loaded):

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    await init_db()
    if settings.smtp_enabled:
        await start_smtp_server()
    await start_retention_scheduler()
    async with mcp_server.session_manager.run():
        yield
    await stop_retention_scheduler()
    if settings.smtp_enabled:
        await stop_smtp_server()
    await close_db()
```

- [ ] Step 3: Add a pure-ASGI trailing-slash rewrite so `POST /mcp` (no slash) works — Starlette's Mount 307-redirects it otherwise, and MCP clients can't be assumed to follow redirects on POST. In `main.py` after the mount:

```python
class _MCPPathRewrite:
    """Serve POST /mcp without a trailing-slash 307 (mounted app lives at /mcp/)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
        await self.app(scope, receive, send)


app.add_middleware(_MCPPathRewrite)
```

- [ ] Step 4: Create `tests/test_mcp.py`. Module-level helpers:

```python
"""MCP server tests. Each test builds a FRESH server instance because the
SDK's session_manager.run() is once-per-instance."""

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from seesee import keys
from seesee.mcp_server import TOOL_SCOPES, build_mcp_asgi_app, create_mcp_server

INIT_PARAMS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "0"},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


async def mint_mgmt_key(scopes: list[str]) -> str:
    _key_id, plaintext = await keys.create_key(
        label="mcp-test", app_id=None, scopes=scopes, expires_at=None, created_by="test"
    )
    return plaintext


def rpc_body(method: str, params: dict | None = None, id_: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "method": method, "id": id_}
    if params is not None:
        body["params"] = params
    return body


class MCPHarness:
    """A fresh mounted MCP app + running session manager per test."""

    def __init__(self):
        self.server = create_mcp_server()
        self.app = FastAPI()
        self.app.mount("/mcp", build_mcp_asgi_app(self.server))

    async def __aenter__(self):
        self._sm = self.server.session_manager.run()
        await self._sm.__aenter__()
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://test"
        )
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        await self._sm.__aexit__(*exc)

    async def rpc(self, token: str, method: str, params: dict | None = None, id_: int = 1):
        return await self.client.post(
            "/mcp/",
            headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
            json=rpc_body(method, params, id_),
        )
```

Tests (each uses `async with MCPHarness() as h:` after minting keys via the standard db fixtures):
  - `test_tool_scopes_covers_all_registered_tools` — `server = create_mcp_server()`; `names = {t.name for t in await FastMCP.list_tools(server)}` (call the PARENT class method to bypass filtering; `from mcp.server.fastmcp import FastMCP`); assert `names == set(TOOL_SCOPES)`.
  - `test_missing_auth_401` — POST `/mcp/` with no Authorization → 401 before any JSON-RPC processing (body can be garbage bytes — send `content=b"junk"`; still 401).
  - `test_app_key_rejected` — create an app via REST; its plaintext Bearer → 401 `"Management API key required"` even though it holds `emails:read`.
  - `test_revoked_key_rejected_next_request` — mint key, one successful `initialize` (200), revoke via `keys.revoke_key`, second request → 401 `"API key revoked"` (per-request resolution).
  - `test_tools_list_filtered_by_scope` — key with `["emails:read"]` → `tools/list` names == the three email tools; key with all four management scopes → all nine names.
  - `test_call_allowed_and_blocked` — `emails:read` key: `tools/call search_emails` → 200 result; `tools/call create_app` → result has `isError: true` mentioning the scope.
  - `test_no_destructive_tools` — full-scope key (`["emails:read","apps:read","apps:write","apps:delete"]`): `delete_app` and `purge_emails` absent from `tools/list` AND `"delete_app" not in TOOL_SCOPES`.
  - `test_mcp_disabled_404` — `monkeypatch.setattr(settings, "mcp_enabled", False)` → any `/mcp/` request 404s.
  - `test_main_app_mount_both_slash_forms` — ONE test against the real `seesee.main.app` (the only test allowed to run ITS session manager: `from seesee.main import app as main_app, mcp_server`; `async with mcp_server.session_manager.run():`): `POST /mcp` and `POST /mcp/` with a valid key both return 200 for `initialize`. Mark this test to run once; if the session manager was already started by a previous run in the same process, skip with `pytest.skip("main app session manager already consumed")` guarded by a module-level flag.
- [ ] Step 5: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [ ] Step 6: Commit: `git add seesee/main.py tests/test_mcp.py && git commit -m "feat(mcp): mount /mcp with lifespan session manager and no-redirect path rewrite"`

### ✅ Review Checkpoint — Chunk 2
- [ ] `main.py` runs `mcp_server.session_manager.run()` inside `lifespan`
- [ ] `_MCPPathRewrite` registered via `app.add_middleware`
- [ ] `test_missing_auth_401` sends garbage bytes and still gets 401 (auth precedes SDK parsing)
- [ ] `test_revoked_key_rejected_next_request` passes (per-request resolution)
- [ ] `git diff HEAD~1 --name-only -- tests/` lists ONLY `tests/test_mcp.py`
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 3: App service extraction (`seesee/app_service.py`, `seesee/routes/apps.py`)

The MCP `create_app` tool must not duplicate the REST route's logic — extract it once.

- [ ] Step 1: Create `seesee/app_service.py` containing `async def create_app_record(*, name, body_storage_mode="full", retention_max_count=None, retention_max_age_days=None, retention_degrade_to_text_days=None, retention_degrade_to_preview_days=None, created_by="admin") -> dict`. Move the ENTIRE body of `routes/apps.py:create_app` into it verbatim — the `VALID_BODY_STORAGE_MODES` check (raise `ValueError` instead of `HTTPException`), slug collision loop, credential generation, the `apps` INSERT, and the `api_keys` dual-write INSERT (using the `created_by` parameter) — returning a plain dict with every field `AppCreateResponse` needs plus `api_key` (plaintext) and `smtp_username`.
- [ ] Step 2: Rewrite `routes/apps.py:create_app` to: call `create_app_record(**request.model_dump(), created_by=principal.key_id)`, catch `ValueError` → 422 with the message, and build `AppCreateResponse(**record)`. Behavior (status codes, response shape, dual-write) must be byte-identical — `tests/test_apps.py` and `tests/test_management_api.py` prove it.
- [ ] Step 3: `python -m pytest -x -q` — full suite unmodified. `ruff check . && ruff format --check .`
- [ ] Step 4: Commit: `git add seesee/app_service.py seesee/routes/apps.py && git commit -m "refactor: extract create_app_record service for REST + MCP reuse"`

### ✅ Review Checkpoint — Chunk 3
- [ ] `routes/apps.py:create_app` contains no SQL — it delegates to the service
- [ ] `create_app_record` raises `ValueError` (not HTTPException) on a bad storage mode
- [ ] The `api_keys` dual-write INSERT lives in the service with `created_by` parameterized
- [ ] No test files changed in this chunk: `git diff HEAD~1 --name-only -- tests/` is empty
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 4: App tools (`seesee/mcp_server.py`, `tests/test_mcp.py`)

- [ ] Step 1: Add the six app tools to `seesee/mcp_server.py` and register them in `create_mcp_server()` (six more `server.tool()(...)` lines). Imports: `from seesee.app_service import create_app_record`, `from seesee.routes.ui import API_KEY_PLACEHOLDER, _build_env_vars`, `from seesee.timezone import iso_in_days`.

```python
async def create_app(name: str, body_storage_mode: str = "full") -> str:
    """Register a new app. Returns the record, the plaintext API key (shown
    ONCE — store it now), and a ready-to-paste .env block."""
    principal = _current_principal.get()
    record = await create_app_record(
        name=name, body_storage_mode=body_storage_mode, created_by=principal.key_id
    )
    env_block = _build_env_vars(
        record["id"], record["slug"], record["api_key"], settings.base_url, settings.smtp_port
    )
    return json.dumps({**record, "env_vars": env_block})


async def create_app_key(
    app_id: str, label: str, scopes: list[str] | None = None, expires_days: int | None = None
) -> str:
    """Mint an additional key for an app (safe rotation: mint, deploy, then
    revoke_app_key the old id). Plaintext is returned once."""
    principal = _current_principal.get()
    expires_at = iso_in_days(expires_days) if expires_days else None
    key_id, plaintext = await keys.create_key(
        label=label,
        app_id=app_id,
        scopes=scopes or ["emails:read", "emails:write"],
        expires_at=expires_at,
        created_by=principal.key_id,
    )
    return json.dumps({"key_id": key_id, "api_key": plaintext})


async def revoke_app_key(app_id: str, key_id: str) -> str:
    """Revoke one of an app's keys. Errors unless the key belongs to that app
    (management keys can never be revoked over MCP)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id FROM api_keys WHERE id = ? AND app_id = ?", (key_id, app_id)
    )
    if await cursor.fetchone() is None:
        raise ValueError("Key not found for that app")
    await keys.revoke_key(key_id)
    return json.dumps({"revoked": key_id})


_APP_COLUMNS = (
    "id, name, slug, body_storage_mode, retention_max_count, retention_max_age_days, "
    "retention_degrade_to_text_days, retention_degrade_to_preview_days, created_at, "
    "last_activity_at"
)


async def list_apps() -> str:
    """List registered apps (no credentials)."""
    db = await get_db()
    cursor = await db.execute(
        f"SELECT {_APP_COLUMNS} FROM apps ORDER BY created_at DESC"  # noqa: S608
    )
    rows = await cursor.fetchall()
    return json.dumps([dict(r) for r in rows], default=str)


async def get_app(app_id: str) -> str:
    """One app record plus its key METADATA (never hashes or plaintext)."""
    db = await get_db()
    cursor = await db.execute(
        f"SELECT {_APP_COLUMNS} FROM apps WHERE id = ?", (app_id,)  # noqa: S608
    )
    row = await cursor.fetchone()
    if row is None:
        raise ValueError(f"No app with id {app_id!r}")
    return json.dumps(
        {**dict(row), "keys": await keys.list_keys(app_id)}, default=str
    )


async def get_integration_env(app_id: str) -> str:
    """The .env integration block with the key REDACTED to a placeholder —
    plaintext keys are unrecoverable after mint; use create_app_key for a new
    one. Passing the placeholder as api_key redacts BOTH occurrences
    (MAIL_SEESEE_API_KEY and MAIL_SEESEE_SMTP_PASSWORD)."""
    db = await get_db()
    cursor = await db.execute("SELECT id, slug FROM apps WHERE id = ?", (app_id,))
    row = await cursor.fetchone()
    if row is None:
        raise ValueError(f"No app with id {app_id!r}")
    return _build_env_vars(
        row["id"], row["slug"], API_KEY_PLACEHOLDER, settings.base_url, settings.smtp_port
    )
```

- [ ] Step 2: Extend `tests/test_mcp.py`:
  - `test_create_app_roundtrip` — `apps:write` key → `tools/call create_app {"name": "Via MCP"}` → 200; parse the tool result JSON; the returned `api_key` plaintext successfully Bearer-ingests an email via REST; `env_vars` contains `MAIL_SEESEE_API_KEY=ss_`.
  - `test_create_and_revoke_app_key_tools` — mint via `create_app_key`, key works; `revoke_app_key` with mismatched app_id → `isError`; correct app_id → revoked, key 401s.
  - `test_get_integration_env_redacts_both` — result contains `API_KEY_PLACEHOLDER` exactly twice and NO `ss_`-prefixed 40+-char token (`import re; assert not re.search(r"ss_[A-Za-z0-9_-]{20,}", text)` — the placeholder itself is `ss_YOUR_API_KEY`, adjust the regex to exclude it: assert every `ss_` occurrence in the text is the placeholder).
  - `test_get_app_returns_key_metadata_only` — response includes `keys` list with `key_prefix` but no `key_hash`.
- [ ] Step 3: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [ ] Step 4: Commit: `git add seesee/mcp_server.py tests/test_mcp.py && git commit -m "feat(mcp): provisioning tools (create_app, keys, integration env)"`

### ✅ Review Checkpoint — Chunk 4
- [ ] All nine tools registered; `test_tool_scopes_covers_all_registered_tools` still passes
- [ ] `get_integration_env` passes the PLACEHOLDER into `_build_env_vars` (both occurrences redacted)
- [ ] `revoke_app_key` SQL matches `id = ? AND app_id = ?`
- [ ] No `delete_app`/`purge_emails` anywhere in `mcp_server.py`: `grep -n "delete_app\|purge" seesee/mcp_server.py` only hits the docstring/instructions text
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 5: Docs + version 0.20.0-dev (`docs/src/content/docs/guides/mcp-server.md`, `docs/astro.config.mjs`, `README.md`, `CHANGELOG.md`, `pyproject.toml`, `seesee/__init__.py`)

- [ ] Step 1: Create `docs/src/content/docs/guides/mcp-server.md` (Starlight frontmatter like the other guides: `title: MCP Server`, `description: Let agents provision apps and debug email over the Model Context Protocol`). Sections:
  - **What it is** — `/mcp` endpoint, streamable HTTP, authenticated by `ss_mgmt_` management keys minted on Settings → API Keys or via `python -m seesee.keys create`.
  - **Connect Claude Code** — the one-liner: `claude mcp add --transport http seesee https://seesee.example.com/mcp --header "Authorization: Bearer ss_mgmt_..."`.
  - **Tools and scopes** — the nine tools grouped by required scope (`emails:read`: search_emails, get_email, list_recent_failures; `apps:read`: list_apps, get_app, get_integration_env; `apps:write`: create_app, create_app_key, revoke_app_key). Note destructive operations are deliberately absent.
  - **Security notes** — verbatim points: `/mcp` is internet-facing by default (`SEESEE_MCP_ENABLED=false` disables it); granting `emails:read` grants the agent access to email contents (bodies can contain reset links and PII); email content is untrusted input to your agent — **use a read-only key (emails:read + apps:read) for debugging agents and a separate apps:write key for provisioning agents**; `apps:write` transitively grants access to all email; keys default to 90-day expiry in the UI.
- [ ] Step 2: In `docs/astro.config.mjs`, add `{ label: "MCP Server", slug: "guides/mcp-server" },` after the Integrations entry in the Guides sidebar group.
- [ ] Step 3: `README.md` — add an "MCP server" bullet/paragraph near the management-keys section added by sub-plan 3: endpoint, the `claude mcp add` one-liner, pointer to the docs page.
- [ ] Step 4: `CHANGELOG.md` `[Unreleased]` → `### Added`: `- MCP server at /mcp (streamable HTTP): nine provisioning + email-debugging tools, scope-filtered tool list, management-key auth, SEESEE_MCP_ENABLED toggle`
- [ ] Step 5: Bump version to `0.20.0-dev` in `pyproject.toml` and `seesee/__init__.py`. (The human cuts the final `0.20.0` release + CHANGELOG consolidation manually — do NOT create a release section.)
- [ ] Step 6: `python -m pytest -x -q`.
- [ ] Step 7: Commit: `git add docs/src docs/astro.config.mjs README.md CHANGELOG.md pyproject.toml seesee/__init__.py && git commit -m "docs(mcp): docs-site guide + README; bump 0.20.0-dev"`

### ✅ Review Checkpoint — Chunk 5
- [ ] `grep -n "mcp-server" docs/astro.config.mjs` shows the sidebar entry
- [ ] The docs page contains the split-credential recommendation (read-only key for debugging agents)
- [ ] Versions match at `0.20.0-dev`: `python -m pytest tests/test_version_sync.py -q`
- [ ] No release section was added to CHANGELOG (still under `[Unreleased]`)
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean
