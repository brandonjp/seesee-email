"""MCP server tests. Each test builds a FRESH server instance because the
SDK's session_manager.run() is once-per-instance."""

import json
import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mcp.server.fastmcp import FastMCP

from seesee import keys
from seesee.config import settings
from seesee.mcp_server import TOOL_SCOPES, build_mcp_asgi_app, create_mcp_server
from seesee.routes.ui import API_KEY_PLACEHOLDER

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
            transport=ASGITransport(app=self.app), base_url="http://localhost:8000"
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


async def test_tool_scopes_covers_all_registered_tools():
    server = create_mcp_server()
    names = {t.name for t in await FastMCP.list_tools(server)}
    # TOOL_SCOPES (Chunk 1) declares scopes for tools registered across later
    # chunks too; every REGISTERED tool must have exactly one entry here.
    assert names.issubset(set(TOOL_SCOPES))


async def test_missing_auth_401():
    async with MCPHarness() as h:
        response = await h.client.post("/mcp/", headers=MCP_HEADERS, content=b"junk")
        assert response.status_code == 401


async def test_app_key_rejected(client, admin_auth_header):
    from tests.conftest import create_test_app

    app_data = await create_test_app(client, admin_auth_header)
    async with MCPHarness() as h:
        response = await h.rpc(app_data["api_key"], "initialize", INIT_PARAMS)
        assert response.status_code == 401
        assert response.json()["detail"] == "Management API key required"


async def test_revoked_key_rejected_next_request():
    key_id, plaintext = await keys.create_key(
        label="revoke-test",
        app_id=None,
        scopes=["emails:read"],
        expires_at=None,
        created_by="test",
    )
    async with MCPHarness() as h:
        response = await h.rpc(plaintext, "initialize", INIT_PARAMS)
        assert response.status_code == 200

        await keys.revoke_key(key_id)

        response = await h.rpc(plaintext, "initialize", INIT_PARAMS, id_=2)
        assert response.status_code == 401
        assert response.json()["detail"] == "API key revoked"


async def test_tools_list_filtered_by_scope():
    read_token = await mint_mgmt_key(["emails:read"])
    full_token = await mint_mgmt_key(["emails:read", "apps:read", "apps:write", "apps:delete"])

    async with MCPHarness() as h:
        await h.rpc(read_token, "initialize", INIT_PARAMS)
        response = await h.rpc(read_token, "tools/list", {}, id_=2)
        names = {t["name"] for t in response.json()["result"]["tools"]}
        assert names == {"search_emails", "get_email", "list_recent_failures"}

    async with MCPHarness() as h:
        registered_names = {t.name for t in await FastMCP.list_tools(h.server)}
        await h.rpc(full_token, "initialize", INIT_PARAMS)
        response = await h.rpc(full_token, "tools/list", {}, id_=2)
        names = {t["name"] for t in response.json()["result"]["tools"]}
        assert names == registered_names


async def test_call_allowed_and_blocked():
    token = await mint_mgmt_key(["emails:read"])
    async with MCPHarness() as h:
        await h.rpc(token, "initialize", INIT_PARAMS)

        response = await h.rpc(
            token,
            "tools/call",
            {"name": "search_emails", "arguments": {}},
            id_=2,
        )
        result = response.json()["result"]
        assert response.status_code == 200
        assert not result.get("isError")

        response = await h.rpc(
            token,
            "tools/call",
            {"name": "create_app", "arguments": {"name": "nope"}},
            id_=3,
        )
        result = response.json()["result"]
        assert result["isError"] is True
        assert "scope" in json.dumps(result).lower()


async def test_no_destructive_tools():
    token = await mint_mgmt_key(["emails:read", "apps:read", "apps:write", "apps:delete"])
    async with MCPHarness() as h:
        await h.rpc(token, "initialize", INIT_PARAMS)
        response = await h.rpc(token, "tools/list", {}, id_=2)
        names = {t["name"] for t in response.json()["result"]["tools"]}
        assert "delete_app" not in names
        assert "purge_emails" not in names
    assert "delete_app" not in TOOL_SCOPES
    assert "purge_emails" not in TOOL_SCOPES


async def test_mcp_disabled_404(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", False)
    async with MCPHarness() as h:
        response = await h.client.post("/mcp/", headers=MCP_HEADERS, content=b"junk")
        assert response.status_code == 404


async def test_create_app_roundtrip():
    from seesee.main import app as main_app

    token = await mint_mgmt_key(["apps:write"])
    async with MCPHarness() as h:
        await h.rpc(token, "initialize", INIT_PARAMS)
        response = await h.rpc(
            token,
            "tools/call",
            {"name": "create_app", "arguments": {"name": "Via MCP"}},
            id_=2,
        )
        result = response.json()["result"]
        assert response.status_code == 200
        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert "MAIL_SEESEE_API_KEY=ss_" in data["env_vars"]

    async with AsyncClient(
        transport=ASGITransport(app=main_app), base_url="http://localhost:8000"
    ) as rest_client:
        response = await rest_client.post(
            "/api/v1/log",
            json={"to": ["a@example.com"], "from": "b@example.com", "subject": "hi"},
            headers={"Authorization": f"Bearer {data['api_key']}"},
        )
        assert response.status_code == 201


async def test_create_and_revoke_app_key_tools():
    from seesee.app_service import create_app_record
    from seesee.main import app as main_app

    record = await create_app_record(name="Key App", created_by="test")
    app_id = record["id"]
    token = await mint_mgmt_key(["apps:write"])

    async with MCPHarness() as h:
        await h.rpc(token, "initialize", INIT_PARAMS)
        response = await h.rpc(
            token,
            "tools/call",
            {"name": "create_app_key", "arguments": {"app_id": app_id, "label": "extra"}},
            id_=2,
        )
        result = response.json()["result"]
        assert not result.get("isError")
        key_data = json.loads(result["content"][0]["text"])

        response = await h.rpc(
            token,
            "tools/call",
            {
                "name": "revoke_app_key",
                "arguments": {"app_id": "not-the-right-app", "key_id": key_data["key_id"]},
            },
            id_=3,
        )
        result = response.json()["result"]
        assert result["isError"] is True

        response = await h.rpc(
            token,
            "tools/call",
            {
                "name": "revoke_app_key",
                "arguments": {"app_id": app_id, "key_id": key_data["key_id"]},
            },
            id_=4,
        )
        result = response.json()["result"]
        assert not result.get("isError")

    async with AsyncClient(
        transport=ASGITransport(app=main_app), base_url="http://localhost:8000"
    ) as rest_client:
        response = await rest_client.post(
            "/api/v1/log",
            json={"to": ["a@example.com"], "from": "b@example.com", "subject": "hi"},
            headers={"Authorization": f"Bearer {key_data['api_key']}"},
        )
        assert response.status_code == 401


async def test_get_integration_env_redacts_both():
    from seesee.app_service import create_app_record

    record = await create_app_record(name="Env App", created_by="test")
    token = await mint_mgmt_key(["apps:read"])

    async with MCPHarness() as h:
        await h.rpc(token, "initialize", INIT_PARAMS)
        response = await h.rpc(
            token,
            "tools/call",
            {"name": "get_integration_env", "arguments": {"app_id": record["id"]}},
            id_=2,
        )
        result = response.json()["result"]
        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert text.count(API_KEY_PLACEHOLDER) == 2
        assert not re.search(r"ss_[A-Za-z0-9_-]{20,}", text)


async def test_get_app_returns_key_metadata_only():
    from seesee.app_service import create_app_record

    record = await create_app_record(name="Meta App", created_by="test")
    token = await mint_mgmt_key(["apps:read"])

    async with MCPHarness() as h:
        await h.rpc(token, "initialize", INIT_PARAMS)
        response = await h.rpc(
            token,
            "tools/call",
            {"name": "get_app", "arguments": {"app_id": record["id"]}},
            id_=2,
        )
        result = response.json()["result"]
        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert len(data["keys"]) >= 1
        assert all("key_prefix" in k for k in data["keys"])
        assert all("key_hash" not in k for k in data["keys"])


_main_app_mount_tested = False


async def test_main_app_mount_both_slash_forms():
    global _main_app_mount_tested
    if _main_app_mount_tested:
        pytest.skip("main app session manager already consumed")
    _main_app_mount_tested = True

    from seesee.main import app as main_app
    from seesee.main import mcp_server

    token = await mint_mgmt_key(["emails:read"])

    async with (
        mcp_server.session_manager.run(),
        AsyncClient(
            transport=ASGITransport(app=main_app), base_url="http://localhost:8000"
        ) as client,
    ):
        response = await client.post(
            "/mcp",
            headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
            json=rpc_body("initialize", INIT_PARAMS),
        )
        assert response.status_code == 200

        response = await client.post(
            "/mcp/",
            headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
            json=rpc_body("initialize", INIT_PARAMS, id_=2),
        )
        assert response.status_code == 200
