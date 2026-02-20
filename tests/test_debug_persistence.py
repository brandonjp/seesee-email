"""Tests for GET /api/v1/admin/debug/persistence — persistence diagnostics."""

from httpx import AsyncClient


async def test_debug_persistence_returns_diagnostics(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """GET /api/v1/admin/debug/persistence returns all expected fields."""
    resp = await client.get(
        "/api/v1/admin/debug/persistence",
        headers=admin_auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "db_path" in data
    assert isinstance(data["db_size_bytes"], int)
    assert isinstance(data["app_count"], int)
    assert isinstance(data["email_count"], int)
    assert isinstance(data["uptime_seconds"], (int, float))
    assert "hostname" in data
    assert isinstance(data["volume_mounted"], bool)
    assert "mount_info" in data
    assert "schema_version" in data


async def test_debug_persistence_requires_admin(client: AsyncClient) -> None:
    """Persistence debug endpoint requires admin auth."""
    resp = await client.get("/api/v1/admin/debug/persistence")
    assert resp.status_code in (401, 403)
