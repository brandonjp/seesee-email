"""Tests for POST /api/v1/admin/cleanup — manual cleanup trigger."""

from httpx import AsyncClient


async def test_cleanup_succeeds(client: AsyncClient, admin_auth_header: dict) -> None:
    """POST /api/v1/admin/cleanup returns success message."""
    resp = await client.post(
        "/api/v1/admin/cleanup",
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Cleanup completed"


async def test_cleanup_requires_admin(client: AsyncClient) -> None:
    """Cleanup requires admin auth."""
    resp = await client.post("/api/v1/admin/cleanup")
    assert resp.status_code in (401, 403)
