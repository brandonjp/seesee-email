"""Tests for email ingest endpoints — POST /api/v1/log."""

import json

import pytest

from seesee.database import get_db
from tests.conftest import create_test_app

MINIMAL_EMAIL = {
    "to": ["user@example.com"],
    "from": "noreply@myapp.com",
    "subject": "Test Subject",
}


@pytest.mark.asyncio
async def test_log_email_success(client, admin_auth_header):
    """POST /api/v1/log with valid API key returns 201."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json=MINIMAL_EMAIL,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "logged"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_log_email_invalid_api_key(client):
    """POST /api/v1/log with wrong Bearer token returns 401."""
    response = await client.post(
        "/api/v1/log",
        json=MINIMAL_EMAIL,
        headers={"Authorization": "Bearer ss_invalid_key_12345678901234567890"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_log_email_no_auth(client):
    """POST /api/v1/log without Authorization header returns 401."""
    response = await client.post("/api/v1/log", json=MINIMAL_EMAIL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_log_email_missing_required_fields(client, admin_auth_header):
    """POST /api/v1/log with missing required fields returns 422."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]
    headers = {"Authorization": f"Bearer {api_key}"}

    # Missing "to"
    response = await client.post(
        "/api/v1/log",
        json={"from": "a@b.com", "subject": "Test"},
        headers=headers,
    )
    assert response.status_code == 422

    # Missing "subject"
    response = await client.post(
        "/api/v1/log",
        json={"to": ["a@b.com"], "from": "a@b.com"},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_log_email_full_body_storage(client, admin_auth_header):
    """App with mode 'full': both body_html and body_text are stored."""
    app_data = await create_test_app(client, admin_auth_header, body_storage_mode="full")
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json={
            **MINIMAL_EMAIL,
            "body_html": "<h1>Hello</h1>",
            "body_text": "Hello",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    email_id = response.json()["id"]

    db = await get_db()
    cursor = await db.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
    row = await cursor.fetchone()
    assert row["body_html"] == "<h1>Hello</h1>"
    assert row["body_text"] == "Hello"
    assert row["body_preview"] == "Hello"


@pytest.mark.asyncio
async def test_log_email_text_only_storage(client, admin_auth_header):
    """App with mode 'text_only': body_html is NULL, body_text is stored."""
    app_data = await create_test_app(
        client, admin_auth_header, name="TextOnly App", body_storage_mode="text_only"
    )
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json={
            **MINIMAL_EMAIL,
            "body_html": "<h1>Hello HTML</h1>",
            "body_text": "Hello Text",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    email_id = response.json()["id"]

    db = await get_db()
    cursor = await db.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
    row = await cursor.fetchone()
    assert row["body_html"] is None
    assert row["body_text"] == "Hello Text"
    assert row["body_preview"] == "Hello Text"


@pytest.mark.asyncio
async def test_log_email_preview_storage(client, admin_auth_header):
    """App with mode 'preview': both body_html and body_text are NULL, preview populated."""
    app_data = await create_test_app(
        client, admin_auth_header, name="Preview App", body_storage_mode="preview"
    )
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json={
            **MINIMAL_EMAIL,
            "body_html": "<h1>Hello HTML</h1>",
            "body_text": "Hello preview text content",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    email_id = response.json()["id"]

    db = await get_db()
    cursor = await db.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
    row = await cursor.fetchone()
    assert row["body_html"] is None
    assert row["body_text"] is None
    assert row["body_preview"] == "Hello preview text content"


@pytest.mark.asyncio
async def test_log_email_preview_from_html_only(client, admin_auth_header):
    """When only body_html is provided, body_preview is generated from stripped HTML."""
    app_data = await create_test_app(client, admin_auth_header, name="HTML Only App")
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json={
            **MINIMAL_EMAIL,
            "body_html": "<h1>Title</h1><p>Content here</p>",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    email_id = response.json()["id"]

    db = await get_db()
    cursor = await db.execute("SELECT body_preview FROM emails WHERE id = ?", (email_id,))
    row = await cursor.fetchone()
    assert row["body_preview"] == "Title Content here"


@pytest.mark.asyncio
async def test_log_email_body_size_bytes_before_stripping(client, admin_auth_header):
    """body_size_bytes reflects original size, not post-stripping size."""
    app_data = await create_test_app(
        client, admin_auth_header, name="Size App", body_storage_mode="preview"
    )
    api_key = app_data["api_key"]

    html_body = "<h1>Big HTML Content</h1>"
    text_body = "Big text content"

    response = await client.post(
        "/api/v1/log",
        json={
            **MINIMAL_EMAIL,
            "body_html": html_body,
            "body_text": text_body,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    email_id = response.json()["id"]

    expected_size = len(html_body.encode("utf-8")) + len(text_body.encode("utf-8"))

    db = await get_db()
    cursor = await db.execute("SELECT body_size_bytes FROM emails WHERE id = ?", (email_id,))
    row = await cursor.fetchone()
    assert row["body_size_bytes"] == expected_size


@pytest.mark.asyncio
async def test_log_email_updates_last_activity(client, admin_auth_header):
    """Logging an email updates the app's last_activity_at."""
    app_data = await create_test_app(client, admin_auth_header, name="Activity App")
    api_key = app_data["api_key"]
    app_id = app_data["id"]

    # Before logging, last_activity_at should be None
    db = await get_db()
    cursor = await db.execute("SELECT last_activity_at FROM apps WHERE id = ?", (app_id,))
    row = await cursor.fetchone()
    assert row["last_activity_at"] is None

    # Log an email
    await client.post(
        "/api/v1/log",
        json=MINIMAL_EMAIL,
        headers={"Authorization": f"Bearer {api_key}"},
    )

    cursor = await db.execute("SELECT last_activity_at FROM apps WHERE id = ?", (app_id,))
    row = await cursor.fetchone()
    assert row["last_activity_at"] is not None


@pytest.mark.asyncio
async def test_log_email_optional_fields(client, admin_auth_header):
    """All optional fields are stored correctly."""
    app_data = await create_test_app(client, admin_auth_header, name="Full Fields App")
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json={
            **MINIMAL_EMAIL,
            "body_html": "<p>html</p>",
            "body_text": "text",
            "status": "failed",
            "provider": "resend",
            "provider_message_id": "msg_123",
            "error_message": "550 User not found",
            "metadata": {"user_id": "u1", "template": "welcome"},
            "cc": ["cc@example.com"],
            "bcc": ["bcc@example.com"],
            "reply_to": "reply@example.com",
            "tags": ["transactional", "auth"],
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    email_id = response.json()["id"]

    db = await get_db()
    cursor = await db.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
    row = await cursor.fetchone()
    assert row["status"] == "failed"
    assert row["provider"] == "resend"
    assert row["provider_message_id"] == "msg_123"
    assert row["error_message"] == "550 User not found"
    assert json.loads(row["metadata"]) == {"user_id": "u1", "template": "welcome"}
    assert json.loads(row["cc_addresses"]) == ["cc@example.com"]
    assert json.loads(row["bcc_addresses"]) == ["bcc@example.com"]
    assert row["reply_to"] == "reply@example.com"
    assert json.loads(row["tags"]) == ["transactional", "auth"]
    assert row["ingest_method"] == "api"


@pytest.mark.asyncio
async def test_log_email_fts_indexed(client, admin_auth_header):
    """After logging, the email is findable via FTS5 search."""
    app_data = await create_test_app(client, admin_auth_header, name="FTS App")
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json={
            "to": ["user@example.com"],
            "from": "noreply@myapp.com",
            "subject": "UniqueSearchTerm password reset",
            "body_text": "Your password has been reset successfully.",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201

    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM emails_fts WHERE emails_fts MATCH ?",
        ("UniqueSearchTerm",),
    )
    rows = await cursor.fetchall()
    assert len(rows) == 1
    assert "UniqueSearchTerm" in rows[0]["subject"]
