"""Tests for email search and filter — GET /api/v1/emails."""

import pytest

from tests.conftest import create_test_app

MINIMAL_EMAIL = {
    "to": ["user@example.com"],
    "from": "noreply@myapp.com",
    "subject": "Test Subject",
}


async def _log_email(client, api_key, overrides=None):
    """Helper to log an email and return the response data."""
    payload = {**MINIMAL_EMAIL, **(overrides or {})}
    response = await client.post(
        "/api/v1/log",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_list_emails_empty(client, admin_auth_header):
    """GET /api/v1/emails with no emails returns empty list with pagination."""
    response = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["emails"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["per_page"] == 20
    assert data["pages"] == 1


@pytest.mark.asyncio
async def test_list_emails_returns_results(client, admin_auth_header):
    """GET /api/v1/emails returns logged emails."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    await _log_email(client, api_key, {"subject": "First Email"})
    await _log_email(client, api_key, {"subject": "Second Email"})

    response = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["emails"]) == 2


@pytest.mark.asyncio
async def test_list_emails_pagination(client, admin_auth_header):
    """GET /api/v1/emails respects page and per_page parameters."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    for i in range(5):
        await _log_email(client, api_key, {"subject": f"Email {i}"})

    # Page 1 with per_page=2
    response = await client.get(
        "/api/v1/emails", params={"per_page": 2, "page": 1}, headers=admin_auth_header
    )
    data = response.json()
    assert data["total"] == 5
    assert len(data["emails"]) == 2
    assert data["page"] == 1
    assert data["per_page"] == 2
    assert data["pages"] == 3

    # Page 3 should have 1 result
    response = await client.get(
        "/api/v1/emails", params={"per_page": 2, "page": 3}, headers=admin_auth_header
    )
    data = response.json()
    assert len(data["emails"]) == 1


@pytest.mark.asyncio
async def test_list_emails_filter_by_app_id(client, admin_auth_header):
    """GET /api/v1/emails?app_id=... filters by app."""
    app1 = await create_test_app(client, admin_auth_header, name="App One")
    app2 = await create_test_app(client, admin_auth_header, name="App Two")

    await _log_email(client, app1["api_key"], {"subject": "From App 1"})
    await _log_email(client, app2["api_key"], {"subject": "From App 2"})
    await _log_email(client, app2["api_key"], {"subject": "Also App 2"})

    response = await client.get(
        "/api/v1/emails", params={"app_id": app2["id"]}, headers=admin_auth_header
    )
    data = response.json()
    assert data["total"] == 2
    assert all(e["app_id"] == app2["id"] for e in data["emails"])


@pytest.mark.asyncio
async def test_list_emails_filter_by_status(client, admin_auth_header):
    """GET /api/v1/emails?status=... filters by status."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    await _log_email(client, api_key, {"subject": "Sent Email", "status": "sent"})
    await _log_email(client, api_key, {"subject": "Failed Email", "status": "failed"})

    response = await client.get(
        "/api/v1/emails", params={"status": "failed"}, headers=admin_auth_header
    )
    data = response.json()
    assert data["total"] == 1
    assert data["emails"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_list_emails_filter_by_provider(client, admin_auth_header):
    """GET /api/v1/emails?provider=... filters by provider."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    await _log_email(client, api_key, {"subject": "Resend", "provider": "resend"})
    await _log_email(client, api_key, {"subject": "SendGrid", "provider": "sendgrid"})

    response = await client.get(
        "/api/v1/emails", params={"provider": "resend"}, headers=admin_auth_header
    )
    data = response.json()
    assert data["total"] == 1
    assert data["emails"][0]["provider"] == "resend"


@pytest.mark.asyncio
async def test_list_emails_fts_search(client, admin_auth_header):
    """GET /api/v1/emails?q=... searches via FTS5."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    await _log_email(client, api_key, {"subject": "Password Reset Notification"})
    await _log_email(client, api_key, {"subject": "Welcome to the platform"})
    await _log_email(client, api_key, {"subject": "Invoice #1234"})

    response = await client.get(
        "/api/v1/emails", params={"q": "Password"}, headers=admin_auth_header
    )
    data = response.json()
    assert data["total"] == 1
    assert "Password" in data["emails"][0]["subject"]


@pytest.mark.asyncio
async def test_list_emails_sort_asc(client, admin_auth_header):
    """GET /api/v1/emails?sort=subject&order=asc sorts correctly."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    await _log_email(client, api_key, {"subject": "Charlie"})
    await _log_email(client, api_key, {"subject": "Alpha"})
    await _log_email(client, api_key, {"subject": "Bravo"})

    response = await client.get(
        "/api/v1/emails",
        params={"sort": "subject", "order": "asc"},
        headers=admin_auth_header,
    )
    data = response.json()
    subjects = [e["subject"] for e in data["emails"]]
    assert subjects == ["Alpha", "Bravo", "Charlie"]


@pytest.mark.asyncio
async def test_list_emails_invalid_sort_field(client, admin_auth_header):
    """GET /api/v1/emails?sort=invalid returns 422."""
    response = await client.get(
        "/api/v1/emails", params={"sort": "invalid"}, headers=admin_auth_header
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_emails_requires_admin(client):
    """GET /api/v1/emails without auth returns 401."""
    response = await client.get("/api/v1/emails")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_emails_combined_filters(client, admin_auth_header):
    """GET /api/v1/emails with multiple filters combines them with AND."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    await _log_email(
        client, api_key, {"subject": "Sent via Resend", "status": "sent", "provider": "resend"}
    )
    await _log_email(
        client, api_key, {"subject": "Failed via Resend", "status": "failed", "provider": "resend"}
    )
    await _log_email(
        client, api_key, {"subject": "Sent via SendGrid", "status": "sent", "provider": "sendgrid"}
    )

    response = await client.get(
        "/api/v1/emails",
        params={"status": "sent", "provider": "resend"},
        headers=admin_auth_header,
    )
    data = response.json()
    assert data["total"] == 1
    assert data["emails"][0]["subject"] == "Sent via Resend"
