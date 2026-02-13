"""Tests for app update and key rotation — PATCH /api/v1/apps/{id}, POST /api/v1/apps/{id}/rotate-key."""

import pytest

from tests.conftest import create_test_app


@pytest.mark.asyncio
async def test_update_app_name(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} updates the app name."""
    app_data = await create_test_app(client, admin_auth_header, name="Original Name")

    response = await client.patch(
        f"/api/v1/apps/{app_data['id']}",
        json={"name": "Updated Name"},
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    # Slug should remain unchanged
    assert data["slug"] == app_data["slug"]


@pytest.mark.asyncio
async def test_update_app_body_storage_mode(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} can change body_storage_mode."""
    app_data = await create_test_app(client, admin_auth_header)
    assert app_data["body_storage_mode"] == "full"

    response = await client.patch(
        f"/api/v1/apps/{app_data['id']}",
        json={"body_storage_mode": "text_only"},
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["body_storage_mode"] == "text_only"


@pytest.mark.asyncio
async def test_update_app_invalid_body_storage_mode(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} rejects invalid body_storage_mode."""
    app_data = await create_test_app(client, admin_auth_header)

    response = await client.patch(
        f"/api/v1/apps/{app_data['id']}",
        json={"body_storage_mode": "invalid"},
        headers=admin_auth_header,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_app_retention_settings(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} can set retention overrides."""
    app_data = await create_test_app(client, admin_auth_header)
    assert app_data["retention_max_count"] is None

    response = await client.patch(
        f"/api/v1/apps/{app_data['id']}",
        json={"retention_max_count": 500, "retention_max_age_days": 30},
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["retention_max_count"] == 500
    assert data["retention_max_age_days"] == 30


@pytest.mark.asyncio
async def test_update_app_clear_retention(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} can clear retention overrides by sending null."""
    # Create with retention
    response = await client.post(
        "/api/v1/apps",
        json={"name": "RetApp", "retention_max_count": 100},
        headers=admin_auth_header,
    )
    assert response.status_code == 201
    app_data = response.json()
    assert app_data["retention_max_count"] == 100

    # Clear it
    response = await client.patch(
        f"/api/v1/apps/{app_data['id']}",
        json={"retention_max_count": None},
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["retention_max_count"] is None


@pytest.mark.asyncio
async def test_update_app_no_fields(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} with empty body returns 422."""
    app_data = await create_test_app(client, admin_auth_header)

    response = await client.patch(
        f"/api/v1/apps/{app_data['id']}",
        json={},
        headers=admin_auth_header,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_app_not_found(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} returns 404 for non-existent app."""
    response = await client.patch(
        "/api/v1/apps/nonexistent-id",
        json={"name": "Updated"},
        headers=admin_auth_header,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_app_requires_admin(client, admin_auth_header):
    """PATCH /api/v1/apps/{id} without auth returns 401."""
    app_data = await create_test_app(client, admin_auth_header)

    response = await client.patch(
        f"/api/v1/apps/{app_data['id']}",
        json={"name": "Updated"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rotate_key_returns_new_key(client, admin_auth_header):
    """POST /api/v1/apps/{id}/rotate-key returns a new API key."""
    app_data = await create_test_app(client, admin_auth_header)
    old_key = app_data["api_key"]

    response = await client.post(
        f"/api/v1/apps/{app_data['id']}/rotate-key",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["api_key"].startswith("ss_")
    assert data["api_key"] != old_key
    assert "message" in data


@pytest.mark.asyncio
async def test_rotate_key_invalidates_old_key(client, admin_auth_header):
    """After key rotation, the old API key no longer works."""
    app_data = await create_test_app(client, admin_auth_header)
    old_key = app_data["api_key"]

    # Rotate key
    rotate_resp = await client.post(
        f"/api/v1/apps/{app_data['id']}/rotate-key",
        headers=admin_auth_header,
    )
    new_key = rotate_resp.json()["api_key"]

    # Old key should fail
    response = await client.post(
        "/api/v1/log",
        json={"to": ["a@b.com"], "from": "x@y.com", "subject": "Test"},
        headers={"Authorization": f"Bearer {old_key}"},
    )
    assert response.status_code == 401

    # New key should work
    response = await client.post(
        "/api/v1/log",
        json={"to": ["a@b.com"], "from": "x@y.com", "subject": "Test"},
        headers={"Authorization": f"Bearer {new_key}"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_rotate_key_not_found(client, admin_auth_header):
    """POST /api/v1/apps/{id}/rotate-key returns 404 for non-existent app."""
    response = await client.post(
        "/api/v1/apps/nonexistent-id/rotate-key",
        headers=admin_auth_header,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rotate_key_requires_admin(client, admin_auth_header):
    """POST /api/v1/apps/{id}/rotate-key without auth returns 401."""
    app_data = await create_test_app(client, admin_auth_header)

    response = await client.post(f"/api/v1/apps/{app_data['id']}/rotate-key")
    assert response.status_code == 401
