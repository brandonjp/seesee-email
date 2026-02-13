"""Tests for app management endpoints — POST /api/v1/apps, GET /api/v1/apps."""

import base64

import pytest

from tests.conftest import create_test_app


@pytest.mark.asyncio
async def test_create_app_returns_credentials(client, admin_auth_header):
    """POST /api/v1/apps returns 201 with API key and SMTP credentials."""
    app_data = await create_test_app(client, admin_auth_header, name="BookLink.fyi")

    assert "id" in app_data
    assert app_data["name"] == "BookLink.fyi"
    assert app_data["slug"] == "booklink-fyi"
    assert app_data["api_key"].startswith("ss_")
    assert app_data["smtp_username"] == "booklink-fyi"
    assert len(app_data["smtp_password"]) > 20
    assert app_data["body_storage_mode"] == "full"
    assert "created_at" in app_data


@pytest.mark.asyncio
async def test_create_app_requires_admin_auth(client):
    """POST /api/v1/apps without auth returns 401."""
    response = await client.post(
        "/api/v1/apps",
        json={"name": "Test App"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_app_wrong_credentials(client):
    """POST /api/v1/apps with wrong admin credentials returns 401."""
    bad_creds = base64.b64encode(b"admin:wrongpassword").decode()
    response = await client.post(
        "/api/v1/apps",
        json={"name": "Test App"},
        headers={"Authorization": f"Basic {bad_creds}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_app_slug_collision(client, admin_auth_header):
    """Creating two apps with the same name produces different slugs."""
    app1 = await create_test_app(client, admin_auth_header, name="My App")
    app2 = await create_test_app(client, admin_auth_header, name="My App")

    assert app1["slug"] == "my-app"
    assert app2["slug"] == "my-app-2"


@pytest.mark.asyncio
async def test_create_app_invalid_body_storage_mode(client, admin_auth_header):
    """Invalid body_storage_mode returns 422."""
    response = await client.post(
        "/api/v1/apps",
        json={"name": "Test App", "body_storage_mode": "invalid"},
        headers=admin_auth_header,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_app_with_retention_settings(client, admin_auth_header):
    """App creation with custom retention settings stores them correctly."""
    app_data = await create_test_app(client, admin_auth_header, name="Retention App")
    # Default: no per-app overrides
    assert app_data["retention_max_count"] is None
    assert app_data["retention_max_age_days"] is None

    # Now create with overrides
    response = await client.post(
        "/api/v1/apps",
        json={"name": "Custom Retention", "retention_max_count": 500, "retention_max_age_days": 30},
        headers=admin_auth_header,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["retention_max_count"] == 500
    assert data["retention_max_age_days"] == 30


@pytest.mark.asyncio
async def test_list_apps_returns_all(client, admin_auth_header):
    """GET /api/v1/apps returns all registered apps without credentials."""
    await create_test_app(client, admin_auth_header, name="App One")
    await create_test_app(client, admin_auth_header, name="App Two")

    response = await client.get("/api/v1/apps", headers=admin_auth_header)
    assert response.status_code == 200
    apps = response.json()
    assert len(apps) == 2
    names = {a["name"] for a in apps}
    assert names == {"App One", "App Two"}
    # Credentials should not be in the list response
    for app in apps:
        assert "api_key" not in app
        assert "smtp_password" not in app


@pytest.mark.asyncio
async def test_list_apps_requires_admin_auth(client):
    """GET /api/v1/apps without auth returns 401."""
    response = await client.get("/api/v1/apps")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_apps_empty(client, admin_auth_header):
    """GET /api/v1/apps with no registered apps returns empty list."""
    response = await client.get("/api/v1/apps", headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json() == []
