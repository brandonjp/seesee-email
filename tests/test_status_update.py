"""Tests for PATCH /api/v1/emails/{id}/status — email status update."""

from httpx import AsyncClient

from tests.conftest import create_test_app


async def _create_email(client: AsyncClient, admin_auth_header: dict) -> tuple[str, str]:
    """Helper: create an app and log an email. Returns (email_id, api_key)."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]
    resp = await client.post(
        "/api/v1/log",
        json={
            "to": ["user@example.com"],
            "from": "sender@example.com",
            "subject": "Status test email",
            "status": "sent",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return resp.json()["id"], api_key


async def test_status_update_valid(client: AsyncClient, admin_auth_header: dict) -> None:
    """PATCH /api/v1/emails/{id}/status updates status."""
    email_id, _ = await _create_email(client, admin_auth_header)

    resp = await client.patch(
        f"/api/v1/emails/{email_id}/status",
        json={"status": "delivered"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "delivered"
    assert data["id"] == email_id


async def test_status_update_to_bounced(client: AsyncClient, admin_auth_header: dict) -> None:
    """Status can be updated to 'bounced'."""
    email_id, _ = await _create_email(client, admin_auth_header)

    resp = await client.patch(
        f"/api/v1/emails/{email_id}/status",
        json={"status": "bounced"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "bounced"


async def test_status_update_invalid_email(client: AsyncClient, admin_auth_header: dict) -> None:
    """PATCH on non-existent email returns 404."""
    resp = await client.patch(
        "/api/v1/emails/nonexistent-id/status",
        json={"status": "delivered"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 404


async def test_status_update_invalid_status(client: AsyncClient, admin_auth_header: dict) -> None:
    """PATCH with empty status is rejected."""
    email_id, _ = await _create_email(client, admin_auth_header)

    resp = await client.patch(
        f"/api/v1/emails/{email_id}/status",
        json={"status": ""},
        headers=admin_auth_header,
    )
    assert resp.status_code == 422


async def test_status_update_requires_admin(client: AsyncClient, admin_auth_header: dict) -> None:
    """PATCH status requires admin auth."""
    email_id, _ = await _create_email(client, admin_auth_header)

    resp = await client.patch(
        f"/api/v1/emails/{email_id}/status",
        json={"status": "delivered"},
    )
    assert resp.status_code in (401, 403)
