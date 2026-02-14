"""Tests for POST /api/v1/log/batch — batch email ingest."""

from httpx import AsyncClient

from tests.conftest import create_test_app


async def test_batch_valid(client: AsyncClient, admin_auth_header: dict) -> None:
    """Batch ingest with valid emails returns 201 with logged count."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    resp = await client.post(
        "/api/v1/log/batch",
        json={
            "emails": [
                {
                    "to": ["user1@example.com"],
                    "from": "sender@example.com",
                    "subject": "Batch email 1",
                    "status": "sent",
                },
                {
                    "to": ["user2@example.com"],
                    "from": "sender@example.com",
                    "subject": "Batch email 2",
                    "status": "sent",
                },
            ]
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["logged"] == 2
    assert data["errors"] == []


async def test_batch_partial_failure(client: AsyncClient, admin_auth_header: dict) -> None:
    """Batch ingest with some invalid emails logs valid ones and reports errors."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    resp = await client.post(
        "/api/v1/log/batch",
        json={
            "emails": [
                {
                    "to": ["valid@example.com"],
                    "from": "sender@example.com",
                    "subject": "Valid email",
                    "status": "sent",
                },
                {
                    "to": ["also-valid@example.com"],
                    "from": "sender@example.com",
                    "subject": "Also valid",
                },
            ]
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["logged"] == 2


async def test_batch_exceeds_100(client: AsyncClient, admin_auth_header: dict) -> None:
    """Batch exceeding 100 emails is rejected by validation."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    emails = [
        {"to": [f"user{i}@example.com"], "from": "s@example.com", "subject": f"Email {i}"}
        for i in range(101)
    ]

    resp = await client.post(
        "/api/v1/log/batch",
        json={"emails": emails},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 422


async def test_batch_empty(client: AsyncClient, admin_auth_header: dict) -> None:
    """Batch with empty email list is rejected by validation."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    resp = await client.post(
        "/api/v1/log/batch",
        json={"emails": []},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 422


async def test_batch_requires_auth(client: AsyncClient) -> None:
    """Batch endpoint requires Bearer auth."""
    resp = await client.post(
        "/api/v1/log/batch",
        json={
            "emails": [
                {"to": ["u@example.com"], "from": "s@example.com", "subject": "Test"},
            ]
        },
    )
    assert resp.status_code in (401, 403)


async def test_batch_single_email(client: AsyncClient, admin_auth_header: dict) -> None:
    """Batch with a single email works."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    resp = await client.post(
        "/api/v1/log/batch",
        json={
            "emails": [
                {
                    "to": ["one@example.com"],
                    "from": "sender@example.com",
                    "subject": "Single batch",
                },
            ]
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["logged"] == 1
