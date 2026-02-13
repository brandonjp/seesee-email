"""Tests for the health check endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from seesee.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    """GET /api/v1/health returns 200 with status ok."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
