"""Tests for DELETE /api/v1/emails — bulk delete (GDPR erasure)."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_app

MINIMAL_EMAIL = {
    "to": ["user@example.com"],
    "from": "noreply@myapp.com",
    "subject": "Test Subject",
}


async def _log_email(client: AsyncClient, api_key: str, overrides: dict | None = None) -> dict:
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
async def test_bulk_delete_by_app_id(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails?app_id=... deletes all emails for that app."""
    app1 = await create_test_app(client, admin_auth_header, name="App One")
    app2 = await create_test_app(client, admin_auth_header, name="App Two")

    for i in range(3):
        await _log_email(client, app1["api_key"], {"subject": f"App1 email {i}"})
    for i in range(2):
        await _log_email(client, app2["api_key"], {"subject": f"App2 email {i}"})

    resp = await client.delete(
        "/api/v1/emails",
        params={"app_id": app1["id"]},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 3

    # App2 emails should still exist
    resp = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert resp.json()["total"] == 2
    assert all(e["app_id"] == app2["id"] for e in resp.json()["emails"])


@pytest.mark.asyncio
async def test_bulk_delete_by_status(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails?status=... deletes emails with that status."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(client, app["api_key"], {"subject": "Sent", "status": "sent"})
    await _log_email(client, app["api_key"], {"subject": "Failed 1", "status": "failed"})
    await _log_email(client, app["api_key"], {"subject": "Failed 2", "status": "failed"})

    resp = await client.delete(
        "/api/v1/emails",
        params={"status": "failed"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    # Only the sent email should remain
    resp = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert resp.json()["total"] == 1
    assert resp.json()["emails"][0]["status"] == "sent"


@pytest.mark.asyncio
async def test_bulk_delete_by_provider(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails?provider=... deletes emails from that provider."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(client, app["api_key"], {"subject": "Resend", "provider": "resend"})
    await _log_email(client, app["api_key"], {"subject": "SendGrid", "provider": "sendgrid"})

    resp = await client.delete(
        "/api/v1/emails",
        params={"provider": "resend"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    resp = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert resp.json()["total"] == 1
    assert resp.json()["emails"][0]["provider"] == "sendgrid"


@pytest.mark.asyncio
async def test_bulk_delete_by_fts_query(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails?q=... deletes emails matching FTS search."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(client, app["api_key"], {"subject": "Password Reset Notification"})
    await _log_email(client, app["api_key"], {"subject": "Welcome to the platform"})
    await _log_email(client, app["api_key"], {"subject": "Invoice #1234"})

    resp = await client.delete(
        "/api/v1/emails",
        params={"q": "Password"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    resp = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_bulk_delete_by_date_range(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails with date_from/date_to deletes in range."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(client, app["api_key"], {"subject": "Old", "logged_at": "2024-01-15T00:00:00"})
    await _log_email(client, app["api_key"], {"subject": "Mid", "logged_at": "2024-06-15T00:00:00"})
    await _log_email(client, app["api_key"], {"subject": "New", "logged_at": "2025-01-15T00:00:00"})

    resp = await client.delete(
        "/api/v1/emails",
        params={"date_from": "2024-01-01", "date_to": "2024-12-31"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    resp = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert resp.json()["total"] == 1
    assert resp.json()["emails"][0]["subject"] == "New"


@pytest.mark.asyncio
async def test_bulk_delete_combined_filters(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails with multiple filters combines them with AND."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client, app["api_key"], {"subject": "S1", "status": "sent", "provider": "resend"}
    )
    await _log_email(
        client, app["api_key"], {"subject": "S2", "status": "failed", "provider": "resend"}
    )
    await _log_email(
        client, app["api_key"], {"subject": "S3", "status": "sent", "provider": "sendgrid"}
    )

    resp = await client.delete(
        "/api/v1/emails",
        params={"status": "sent", "provider": "resend"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    resp = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_bulk_delete_empty_results(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails with filters matching nothing returns 0 deleted."""
    app = await create_test_app(client, admin_auth_header)
    await _log_email(client, app["api_key"], {"subject": "Existing email"})

    resp = await client.delete(
        "/api/v1/emails",
        params={"status": "nonexistent-status"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0

    # Original email still exists
    resp = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_bulk_delete_no_filter_rejected(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails without any filter returns 422."""
    resp = await client.delete(
        "/api/v1/emails",
        headers=admin_auth_header,
    )
    assert resp.status_code == 422
    assert "filter" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bulk_delete_requires_admin(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails requires admin auth."""
    resp = await client.delete(
        "/api/v1/emails",
        params={"status": "sent"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_bulk_delete_fts_consistency(client: AsyncClient, admin_auth_header: dict) -> None:
    """After bulk delete, FTS index is consistent — deleted emails don't appear in search."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(client, app["api_key"], {"subject": "Password Reset"})
    await _log_email(client, app["api_key"], {"subject": "Welcome Email"})
    await _log_email(client, app["api_key"], {"subject": "Invoice Receipt"})

    # Delete by FTS query
    resp = await client.delete(
        "/api/v1/emails",
        params={"q": "Password"},
        headers=admin_auth_header,
    )
    assert resp.json()["deleted"] == 1

    # FTS search for deleted term should return nothing
    resp = await client.get(
        "/api/v1/emails",
        params={"q": "Password"},
        headers=admin_auth_header,
    )
    assert resp.json()["total"] == 0

    # FTS search for remaining emails should work
    resp = await client.get(
        "/api/v1/emails",
        params={"q": "Welcome"},
        headers=admin_auth_header,
    )
    assert resp.json()["total"] == 1

    resp = await client.get(
        "/api/v1/emails",
        params={"q": "Invoice"},
        headers=admin_auth_header,
    )
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_bulk_delete_fts_consistency_after_status_filter(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """After bulk delete by status, FTS searches for deleted emails return nothing."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client, app["api_key"], {"subject": "Unique Alpha Subject", "status": "failed"}
    )
    await _log_email(client, app["api_key"], {"subject": "Unique Beta Subject", "status": "sent"})

    # Delete failed emails
    resp = await client.delete(
        "/api/v1/emails",
        params={"status": "failed"},
        headers=admin_auth_header,
    )
    assert resp.json()["deleted"] == 1

    # FTS search for the deleted email's subject returns nothing
    resp = await client.get(
        "/api/v1/emails",
        params={"q": "Alpha"},
        headers=admin_auth_header,
    )
    assert resp.json()["total"] == 0

    # FTS search for the remaining email works
    resp = await client.get(
        "/api/v1/emails",
        params={"q": "Beta"},
        headers=admin_auth_header,
    )
    assert resp.json()["total"] == 1
