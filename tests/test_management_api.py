"""Tests for the management REST API — require_scope gate (Bearer/Basic only)."""

from httpx import AsyncClient

from tests.conftest import create_test_app


async def create_mgmt_key(scopes: list[str]) -> str:
    """Mint a management key directly and return its plaintext."""
    from seesee import keys

    _key_id, plaintext = await keys.create_key(
        label="test-mgmt", app_id=None, scopes=scopes, expires_at=None, created_by="test"
    )
    return plaintext


async def test_basic_admin_still_lists_apps(client: AsyncClient, admin_auth_header: dict) -> None:
    resp = await client.get("/api/v1/apps", headers=admin_auth_header)
    assert resp.status_code == 200


async def test_mgmt_key_lists_apps(client: AsyncClient) -> None:
    plaintext = await create_mgmt_key(["apps:read"])
    resp = await client.get("/api/v1/apps", headers={"Authorization": f"Bearer {plaintext}"})
    assert resp.status_code == 200


async def test_missing_scope_403(client: AsyncClient) -> None:
    plaintext = await create_mgmt_key(["emails:read"])
    resp = await client.get("/api/v1/apps", headers={"Authorization": f"Bearer {plaintext}"})
    assert resp.status_code == 403
    assert "apps:read" in resp.json()["detail"]


async def test_app_key_403_on_apps_read(client: AsyncClient, admin_auth_header: dict) -> None:
    app_data = await create_test_app(client, admin_auth_header)
    resp = await client.get(
        "/api/v1/apps", headers={"Authorization": f"Bearer {app_data['api_key']}"}
    )
    assert resp.status_code == 403


async def test_session_cookie_never_authenticates_api(client: AsyncClient) -> None:
    """B1 regression test: cookie auth must never authenticate a REST API route."""
    login_resp = await client.post(
        "/login",
        data={"username": "admin", "password": "testpassword"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 303
    resp = await client.get("/api/v1/apps")
    assert resp.status_code == 401


async def test_no_credentials_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/apps")
    assert resp.status_code == 401
