"""Tests for email detail and preview — GET /api/v1/emails/{id}, /{id}/preview."""

import pytest

from seesee.auth import SESSION_COOKIE_NAME, create_session_token
from seesee.config import settings
from tests.conftest import create_test_app

FULL_EMAIL = {
    "to": ["user@example.com"],
    "from": "noreply@myapp.com",
    "subject": "Test Subject",
    "body_html": "<h1>Hello</h1><p>World</p>",
    "body_text": "Hello World",
    "status": "sent",
    "provider": "resend",
    "provider_message_id": "msg_abc123",
    "error_message": None,
    "metadata": {"campaign": "onboarding"},
    "cc": ["cc@example.com"],
    "bcc": ["bcc@example.com"],
    "reply_to": "reply@example.com",
    "tags": ["welcome", "transactional"],
}


async def _log_email(client, api_key, overrides=None):
    """Helper to log an email and return response data."""
    payload = {**FULL_EMAIL, **(overrides or {})}
    response = await client.post(
        "/api/v1/log",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_get_email_detail(client, admin_auth_header):
    """GET /api/v1/emails/{id} returns full email detail."""
    app_data = await create_test_app(client, admin_auth_header)
    logged = await _log_email(client, app_data["api_key"])
    email_id = logged["id"]

    response = await client.get(f"/api/v1/emails/{email_id}", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == email_id
    assert data["app_id"] == app_data["id"]
    assert data["to_addresses"] == ["user@example.com"]
    assert data["from_address"] == "noreply@myapp.com"
    assert data["subject"] == "Test Subject"
    assert data["body_html"] == "<h1>Hello</h1><p>World</p>"
    assert data["body_text"] == "Hello World"
    assert data["body_preview"] == "Hello World"
    assert data["status"] == "sent"
    assert data["provider"] == "resend"
    assert data["provider_message_id"] == "msg_abc123"
    assert data["metadata"] == {"campaign": "onboarding"}
    assert data["cc_addresses"] == ["cc@example.com"]
    assert data["bcc_addresses"] == ["bcc@example.com"]
    assert data["reply_to"] == "reply@example.com"
    assert data["tags"] == ["welcome", "transactional"]
    assert data["ingest_method"] == "api"
    assert data["body_size_bytes"] > 0


@pytest.mark.asyncio
async def test_get_email_not_found(client, admin_auth_header):
    """GET /api/v1/emails/{id} returns 404 for non-existent ID."""
    response = await client.get("/api/v1/emails/nonexistent-id", headers=admin_auth_header)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_email_requires_admin(client, admin_auth_header):
    """GET /api/v1/emails/{id} without auth returns 401."""
    app_data = await create_test_app(client, admin_auth_header)
    logged = await _log_email(client, app_data["api_key"])

    response = await client.get(f"/api/v1/emails/{logged['id']}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_preview_email_html(client, admin_auth_header):
    """GET /api/v1/emails/{id}/preview returns HTML content with CSP headers."""
    app_data = await create_test_app(client, admin_auth_header)
    logged = await _log_email(client, app_data["api_key"])

    response = await client.get(f"/api/v1/emails/{logged['id']}/preview", headers=admin_auth_header)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Content-Security-Policy" in response.headers
    assert "<h1>Hello</h1><p>World</p>" in response.text


@pytest.mark.asyncio
async def test_preview_email_text_fallback(client, admin_auth_header):
    """Preview falls back to body_text when body_html is not available."""
    app_data = await create_test_app(
        client, admin_auth_header, name="TextOnly", body_storage_mode="text_only"
    )
    logged = await _log_email(client, app_data["api_key"])

    response = await client.get(f"/api/v1/emails/{logged['id']}/preview", headers=admin_auth_header)
    assert response.status_code == 200
    # Should be wrapped in <pre> since it's plain text
    assert "<pre" in response.text
    assert "Hello World" in response.text


@pytest.mark.asyncio
async def test_preview_email_escapes_text(client, admin_auth_header):
    """Preview escapes HTML entities when falling back to plain text."""
    app_data = await create_test_app(
        client, admin_auth_header, name="EscapeApp", body_storage_mode="text_only"
    )
    logged = await _log_email(
        client,
        app_data["api_key"],
        {"body_text": 'Hello <script>alert("xss")</script>', "body_html": None},
    )

    response = await client.get(f"/api/v1/emails/{logged['id']}/preview", headers=admin_auth_header)
    assert response.status_code == 200
    # Script tag should be escaped, not rendered
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


@pytest.mark.asyncio
async def test_preview_email_not_found(client, admin_auth_header):
    """GET /api/v1/emails/{id}/preview returns 404 for non-existent ID."""
    response = await client.get("/api/v1/emails/nonexistent-id/preview", headers=admin_auth_header)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_preview_email_requires_admin(client):
    """GET /api/v1/emails/{id}/preview without auth returns 401."""
    response = await client.get("/api/v1/emails/some-id/preview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_preview_email_with_session_cookie(client, admin_auth_header):
    """GET /api/v1/emails/{id}/preview with a valid session cookie returns 200 HTML."""
    app_data = await create_test_app(client, admin_auth_header)
    logged = await _log_email(client, app_data["api_key"])

    token = create_session_token("admin", settings.secret_key or settings.admin_password)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = await client.get(f"/api/v1/emails/{logged['id']}/preview")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<h1>Hello</h1><p>World</p>" in response.text


@pytest.mark.asyncio
async def test_preview_email_with_basic_auth_still_works(client, admin_auth_header):
    """GET /api/v1/emails/{id}/preview still accepts HTTP Basic admin auth."""
    app_data = await create_test_app(client, admin_auth_header)
    logged = await _log_email(client, app_data["api_key"])

    response = await client.get(f"/api/v1/emails/{logged['id']}/preview", headers=admin_auth_header)
    assert response.status_code == 200
    assert "<h1>Hello</h1><p>World</p>" in response.text


@pytest.mark.asyncio
async def test_preview_email_anonymous_returns_401_not_basic_prompt(client):
    """GET /api/v1/emails/{id}/preview with no credentials returns 401, not a Basic challenge loop."""
    response = await client.get("/api/v1/emails/some-id/preview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_preview_email_invalid_session_cookie_returns_401(client):
    """An invalid/expired session cookie returns 401, not a 303 redirect."""
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-valid-token")

    response = await client.get("/api/v1/emails/some-id/preview")
    assert response.status_code == 401
