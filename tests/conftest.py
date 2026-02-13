"""Shared test fixtures for SeeSee tests."""

import base64

import pytest
from httpx import ASGITransport, AsyncClient

from seesee.config import settings
from seesee.database import close_db


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Use a temporary database for every test."""
    db_path = str(tmp_path / "test_seesee.db")
    monkeypatch.setenv("SEESEE_DB_PATH", db_path)
    monkeypatch.setenv("SEESEE_ADMIN_PASSWORD", "testpassword")
    # Patch the already-instantiated settings singleton directly
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(settings, "admin_password", "testpassword")


@pytest.fixture(autouse=True)
async def _reset_db():
    """Ensure database connection is closed between tests."""
    yield
    await close_db()


@pytest.fixture
def admin_auth_header():
    """Return HTTP Basic auth header for admin endpoints."""
    credentials = base64.b64encode(b"admin:testpassword").decode()
    return {"Authorization": f"Basic {credentials}"}


@pytest.fixture
async def client():
    """Provide an async test client with app lifespan."""
    from seesee.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def create_test_app(
    client: AsyncClient,
    admin_auth_header: dict,
    name: str = "Test App",
    body_storage_mode: str = "full",
) -> dict:
    """Helper to create a test app and return the response data (includes plaintext API key)."""
    response = await client.post(
        "/api/v1/apps",
        json={"name": name, "body_storage_mode": body_storage_mode},
        headers=admin_auth_header,
    )
    assert response.status_code == 201
    return response.json()
