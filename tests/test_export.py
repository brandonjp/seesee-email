"""Tests for GET /api/v1/export — data export per recipient (GDPR right of access)."""

import csv
import io

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_app


async def _log_email(client: AsyncClient, api_key: str, overrides: dict | None = None) -> dict:
    """Helper to log an email and return the response data."""
    payload = {
        "to": ["user@example.com"],
        "from": "noreply@myapp.com",
        "subject": "Test Subject",
        **(overrides or {}),
    }
    response = await client.post(
        "/api/v1/log",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_export_by_to_address(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export returns emails where recipient is in to_addresses."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["alice@example.com"],
            "subject": "Hello Alice",
        },
    )
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["bob@example.com"],
            "subject": "Hello Bob",
        },
    )
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["alice@example.com", "charlie@example.com"],
            "subject": "Hello Alice and Charlie",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipient"] == "alice@example.com"
    assert data["total"] == 2
    subjects = {e["subject"] for e in data["emails"]}
    assert subjects == {"Hello Alice", "Hello Alice and Charlie"}


@pytest.mark.asyncio
async def test_export_by_cc_address(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export returns emails where recipient is in cc_addresses."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["bob@example.com"],
            "cc": ["alice@example.com"],
            "subject": "CC to Alice",
        },
    )
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["bob@example.com"],
            "subject": "No Alice",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["subject"] == "CC to Alice"


@pytest.mark.asyncio
async def test_export_by_bcc_address(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export returns emails where recipient is in bcc_addresses."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["bob@example.com"],
            "bcc": ["alice@example.com"],
            "subject": "BCC to Alice",
        },
    )
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["bob@example.com"],
            "subject": "No Alice",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["subject"] == "BCC to Alice"


@pytest.mark.asyncio
async def test_export_across_to_cc_bcc(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export finds recipient across to, cc, and bcc fields."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["alice@example.com"],
            "subject": "In TO",
        },
    )
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["other@example.com"],
            "cc": ["alice@example.com"],
            "subject": "In CC",
        },
    )
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["other@example.com"],
            "bcc": ["alice@example.com"],
            "subject": "In BCC",
        },
    )
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["other@example.com"],
            "subject": "Not Alice",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    subjects = {e["subject"] for e in data["emails"]}
    assert subjects == {"In TO", "In CC", "In BCC"}


@pytest.mark.asyncio
async def test_export_no_results(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export for a recipient with no emails returns empty list."""
    app = await create_test_app(client, admin_auth_header)
    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["bob@example.com"],
            "subject": "Not for Alice",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipient"] == "alice@example.com"
    assert data["total"] == 0
    assert data["emails"] == []


@pytest.mark.asyncio
async def test_export_requires_admin(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export endpoint requires admin auth."""
    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_export_requires_recipient(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export endpoint requires recipient parameter."""
    resp = await client.get(
        "/api/v1/export",
        headers=admin_auth_header,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_export_rejects_invalid_recipient(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """Export endpoint rejects invalid email addresses."""
    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "not-an-email"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 422
    assert "valid recipient" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_export_case_insensitive(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export matches recipients case-insensitively."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["Alice@Example.COM"],
            "subject": "Mixed Case",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_export_includes_body_content(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export includes body_html, body_text, and body_preview."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["alice@example.com"],
            "subject": "With Body",
            "body_html": "<p>Hello Alice</p>",
            "body_text": "Hello Alice",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    email = resp.json()["emails"][0]
    assert email["body_html"] == "<p>Hello Alice</p>"
    assert email["body_text"] == "Hello Alice"
    assert email["body_preview"] is not None


@pytest.mark.asyncio
async def test_export_includes_metadata_fields(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """Export includes key metadata: subject, from, status, provider, logged_at."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["alice@example.com"],
            "subject": "Metadata Test",
            "status": "delivered",
            "provider": "resend",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    email = resp.json()["emails"][0]
    assert email["subject"] == "Metadata Test"
    assert email["from_address"] == "noreply@myapp.com"
    assert email["status"] == "delivered"
    assert email["provider"] == "resend"
    assert email["logged_at"] is not None
    assert email["ingest_method"] == "api"


@pytest.mark.asyncio
async def test_export_csv_format_param(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export with format=csv returns CSV content."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["alice@example.com"],
            "subject": "CSV Test Email",
            "body_text": "Hello from CSV",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com", "format": "csv"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "export-alice@example.com.csv" in resp.headers.get("content-disposition", "")

    # Parse CSV and verify content
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["subject"] == "CSV Test Email"
    assert rows[0]["from_address"] == "noreply@myapp.com"
    assert rows[0]["body_text"] == "Hello from CSV"


@pytest.mark.asyncio
async def test_export_csv_accept_header(client: AsyncClient, admin_auth_header: dict) -> None:
    """Export with Accept: text/csv returns CSV content."""
    app = await create_test_app(client, admin_auth_header)

    await _log_email(
        client,
        app["api_key"],
        {
            "to": ["alice@example.com"],
            "subject": "Accept CSV",
        },
    )

    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "alice@example.com"},
        headers={**admin_auth_header, "accept": "text/csv"},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_export_csv_empty_results(client: AsyncClient, admin_auth_header: dict) -> None:
    """CSV export with no matching emails returns header-only CSV."""
    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "nobody@example.com", "format": "csv"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 0
    # Header should still be present
    assert "id" in resp.text
    assert "subject" in resp.text


@pytest.mark.asyncio
async def test_export_has_exported_at(client: AsyncClient, admin_auth_header: dict) -> None:
    """JSON export includes exported_at timestamp."""
    resp = await client.get(
        "/api/v1/export",
        params={"recipient": "nobody@example.com"},
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert "exported_at" in resp.json()
    assert resp.json()["exported_at"] is not None
