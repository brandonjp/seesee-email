"""Tests for DELETE endpoints — single email and app purge."""

from httpx import AsyncClient

from tests.conftest import create_test_app


async def _create_email(client: AsyncClient, admin_auth_header: dict) -> tuple[str, str]:
    """Helper: create an app and log an email. Returns (email_id, app_id)."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]
    app_id = app_data["id"]
    resp = await client.post(
        "/api/v1/log",
        json={
            "to": ["user@example.com"],
            "from": "sender@example.com",
            "subject": "Delete test email",
            "status": "sent",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return resp.json()["id"], app_id


async def test_delete_single_email(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails/{id} deletes the email."""
    email_id, _ = await _create_email(client, admin_auth_header)

    resp = await client.delete(
        f"/api/v1/emails/{email_id}",
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()

    # Verify it's gone
    resp = await client.get(
        f"/api/v1/emails/{email_id}",
        headers=admin_auth_header,
    )
    assert resp.status_code == 404


async def test_delete_nonexistent_email(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/emails/{id} with bad ID returns 404."""
    resp = await client.delete(
        "/api/v1/emails/nonexistent-id",
        headers=admin_auth_header,
    )
    assert resp.status_code == 404


async def test_delete_email_requires_admin(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE email requires admin auth."""
    email_id, _ = await _create_email(client, admin_auth_header)

    resp = await client.delete(f"/api/v1/emails/{email_id}")
    assert resp.status_code in (401, 403)


async def test_purge_app_emails(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/apps/{app_id}/emails deletes all emails for the app."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]
    app_id = app_data["id"]

    # Log a few emails
    for i in range(3):
        await client.post(
            "/api/v1/log",
            json={
                "to": [f"user{i}@example.com"],
                "from": "sender@example.com",
                "subject": f"Purge test {i}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    resp = await client.delete(
        f"/api/v1/apps/{app_id}/emails",
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert "3" in resp.json()["message"]

    # Verify all gone
    resp = await client.get(
        f"/api/v1/emails?app_id={app_id}",
        headers=admin_auth_header,
    )
    assert resp.json()["total"] == 0


async def test_purge_nonexistent_app(client: AsyncClient, admin_auth_header: dict) -> None:
    """Purge for nonexistent app returns 404."""
    resp = await client.delete(
        "/api/v1/apps/nonexistent-id/emails",
        headers=admin_auth_header,
    )
    assert resp.status_code == 404


async def test_purge_requires_admin(client: AsyncClient, admin_auth_header: dict) -> None:
    """Purge requires admin auth."""
    app_data = await create_test_app(client, admin_auth_header)
    app_id = app_data["id"]

    resp = await client.delete(f"/api/v1/apps/{app_id}/emails")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Delete app (app + all emails)
# ---------------------------------------------------------------------------


async def test_delete_app(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/apps/{app_id} deletes the app and all its emails."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]
    app_id = app_data["id"]

    # Log a few emails
    for i in range(3):
        await client.post(
            "/api/v1/log",
            json={
                "to": [f"user{i}@example.com"],
                "from": "sender@example.com",
                "subject": f"Delete app test {i}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    resp = await client.delete(
        f"/api/v1/apps/{app_id}",
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert "3" in resp.json()["message"]
    assert app_data["name"] in resp.json()["message"]

    # Verify app is gone
    resp = await client.get("/api/v1/apps", headers=admin_auth_header)
    app_ids = [a["id"] for a in resp.json()]
    assert app_id not in app_ids


async def test_delete_app_no_emails(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/apps/{app_id} works when the app has no emails."""
    app_data = await create_test_app(client, admin_auth_header)
    app_id = app_data["id"]

    resp = await client.delete(
        f"/api/v1/apps/{app_id}",
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert "0" in resp.json()["message"]


async def test_delete_nonexistent_app(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE /api/v1/apps/{app_id} with bad ID returns 404."""
    resp = await client.delete(
        "/api/v1/apps/nonexistent-id",
        headers=admin_auth_header,
    )
    assert resp.status_code == 404


async def test_delete_app_requires_admin(client: AsyncClient, admin_auth_header: dict) -> None:
    """DELETE app requires admin auth."""
    app_data = await create_test_app(client, admin_auth_header)
    app_id = app_data["id"]

    resp = await client.delete(f"/api/v1/apps/{app_id}")
    assert resp.status_code in (401, 403)
