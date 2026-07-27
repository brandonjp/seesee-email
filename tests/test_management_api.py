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


async def test_mgmt_key_creates_app(client: AsyncClient) -> None:
    from seesee.database import get_db

    plaintext = await create_mgmt_key(["apps:write"])
    resp = await client.post(
        "/api/v1/apps",
        json={"name": "Mgmt Created App", "body_storage_mode": "full"},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    app_id = body["id"]

    ingest_resp = await client.post(
        "/api/v1/log",
        json={
            "from": "sender@example.com",
            "to": ["recipient@example.com"],
            "subject": "Test",
            "body_text": "Hello",
        },
        headers={"Authorization": f"Bearer {body['api_key']}"},
    )
    assert ingest_resp.status_code == 201

    db = await get_db()
    cursor = await db.execute("SELECT created_by FROM api_keys WHERE app_id = ?", (app_id,))
    row = await cursor.fetchone()
    assert row["created_by"] != "admin"


async def test_apps_write_cannot_delete(client: AsyncClient) -> None:
    write_key = await create_mgmt_key(["apps:write"])
    resp = await client.post(
        "/api/v1/apps",
        json={"name": "App To Not Delete", "body_storage_mode": "full"},
        headers={"Authorization": f"Bearer {write_key}"},
    )
    app_id = resp.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/apps/{app_id}", headers={"Authorization": f"Bearer {write_key}"}
    )
    assert delete_resp.status_code == 403


async def test_apps_delete_can_delete(client: AsyncClient, admin_auth_header: dict) -> None:
    app_data = await create_test_app(client, admin_auth_header)
    delete_key = await create_mgmt_key(["apps:delete"])

    delete_resp = await client.delete(
        f"/api/v1/apps/{app_data['id']}",
        headers={"Authorization": f"Bearer {delete_key}"},
    )
    assert delete_resp.status_code == 200


async def test_get_single_app(client: AsyncClient, admin_auth_header: dict) -> None:
    app_data = await create_test_app(client, admin_auth_header)
    read_key = await create_mgmt_key(["apps:read"])

    resp = await client.get(
        f"/api/v1/apps/{app_data['id']}",
        headers={"Authorization": f"Bearer {read_key}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == app_data["id"]

    missing_resp = await client.get(
        "/api/v1/apps/nonexistent-id",
        headers={"Authorization": f"Bearer {read_key}"},
    )
    assert missing_resp.status_code == 404
