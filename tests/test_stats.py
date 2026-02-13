"""Tests for dashboard statistics — GET /api/v1/stats."""

import pytest

from tests.conftest import create_test_app

MINIMAL_EMAIL = {
    "to": ["user@example.com"],
    "from": "noreply@myapp.com",
    "subject": "Test Subject",
}


async def _log_email(client, api_key, overrides=None):
    """Helper to log an email."""
    payload = {**MINIMAL_EMAIL, **(overrides or {})}
    response = await client.post(
        "/api/v1/log",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_stats_empty(client, admin_auth_header):
    """GET /api/v1/stats with no data returns zeroes."""
    response = await client.get("/api/v1/stats", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["total_emails"] == 0
    assert data["emails_24h"] == 0
    assert data["emails_7d"] == 0
    assert data["emails_30d"] == 0
    assert data["total_apps"] == 0
    assert data["by_status"] == {}
    assert data["by_app"] == []


@pytest.mark.asyncio
async def test_stats_with_data(client, admin_auth_header):
    """GET /api/v1/stats returns correct counts with data present."""
    app1 = await create_test_app(client, admin_auth_header, name="App Alpha")
    app2 = await create_test_app(client, admin_auth_header, name="App Beta")

    # Log emails for app1
    await _log_email(client, app1["api_key"], {"subject": "Email 1", "status": "sent"})
    await _log_email(client, app1["api_key"], {"subject": "Email 2", "status": "sent"})
    await _log_email(client, app1["api_key"], {"subject": "Email 3", "status": "failed"})

    # Log emails for app2
    await _log_email(client, app2["api_key"], {"subject": "Email 4", "status": "sent"})

    response = await client.get("/api/v1/stats", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert data["total_emails"] == 4
    assert data["emails_24h"] == 4  # All were just logged
    assert data["emails_7d"] == 4
    assert data["emails_30d"] == 4
    assert data["total_apps"] == 2

    # Status breakdown
    assert data["by_status"]["sent"] == 3
    assert data["by_status"]["failed"] == 1

    # By-app breakdown (app1 has 3, app2 has 1)
    app_counts = {entry["id"]: entry["count"] for entry in data["by_app"]}
    assert app_counts[app1["id"]] == 3
    assert app_counts[app2["id"]] == 1


@pytest.mark.asyncio
async def test_stats_includes_apps_with_no_emails(client, admin_auth_header):
    """GET /api/v1/stats includes apps with zero emails in by_app."""
    app_data = await create_test_app(client, admin_auth_header, name="Empty App")

    response = await client.get("/api/v1/stats", headers=admin_auth_header)
    data = response.json()
    assert data["total_apps"] == 1
    assert len(data["by_app"]) == 1
    assert data["by_app"][0]["id"] == app_data["id"]
    assert data["by_app"][0]["count"] == 0


@pytest.mark.asyncio
async def test_stats_requires_admin(client):
    """GET /api/v1/stats without auth returns 401."""
    response = await client.get("/api/v1/stats")
    assert response.status_code == 401
