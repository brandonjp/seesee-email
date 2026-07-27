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
            response = JSONResponse({"detail": "Management API key required"}, status_code=401)
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
_EMAIL_SUMMARY_SELECT = ", ".join(f"e.{col.strip()}" for col in _EMAIL_SUMMARY_COLUMNS.split(","))


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

    Note: this function's name contains "_mcp_server" only as text — it does
    not read or write FastMCP's private `self._mcp_server` attribute anywhere
    in this module; ScopedFastMCP only overrides the public list_tools/call_tool.
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
