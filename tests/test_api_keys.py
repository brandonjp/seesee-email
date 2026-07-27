"""Tests for seesee.keys — sync core (generation, prefix extraction, scope matrix)."""

import pytest

from seesee import keys
from seesee.auth import verify_secret
from seesee.database import get_db
from seesee.keys import (
    KeyExpiredError,
    KeyRevokedError,
    extract_prefix,
    generate_key,
    key_is_active,
    validate_scopes,
)
from tests.conftest import create_test_app


def test_generate_key_formats():
    app_key = generate_key()
    assert app_key.startswith("ss_")
    assert not app_key.startswith("ss_mgmt_")

    mgmt_key = generate_key(management=True)
    assert mgmt_key.startswith("ss_mgmt_")


def test_extract_prefix_app_key():
    token = "ss_" + "a" * 43
    assert extract_prefix(token) == ["aaaaaaaa"]


def test_extract_prefix_mgmt_key():
    token = "ss_mgmt_" + "b" * 43
    assert extract_prefix(token) == ["b" * 8, "mgmt_bbb"]


def test_extract_prefix_ambiguous_app_key():
    token = "ss_mgmt_xyzabcde" + "c" * 27
    candidates = extract_prefix(token)
    assert len(candidates) == 2
    assert "xyzabcde" in candidates
    assert "mgmt_xyz" in candidates


def test_extract_prefix_too_short():
    assert extract_prefix("ss_abc") == []
    assert extract_prefix("ss_mgmt_ab") == []
    assert extract_prefix("garbage") == []


def test_key_is_active():
    active_row = {"revoked_at": None, "expires_at": None}
    assert key_is_active(active_row, "2026-01-01T00:00:00") == (True, "")

    revoked_row = {"revoked_at": "2026-01-01T00:00:00", "expires_at": None}
    assert key_is_active(revoked_row, "2026-01-02T00:00:00") == (False, "revoked")

    expired_row = {"revoked_at": None, "expires_at": "2020-01-01T00:00:00"}
    assert key_is_active(expired_row, "2026-01-01T00:00:00") == (False, "expired")

    future_row = {"revoked_at": None, "expires_at": "2099-01-01T00:00:00"}
    assert key_is_active(future_row, "2026-01-01T00:00:00") == (True, "")


def test_validate_scopes_matrix():
    # App key: emails scopes OK, apps scopes invalid
    validate_scopes(["emails:read"], "app1")
    with pytest.raises(ValueError):
        validate_scopes(["apps:write"], "app1")

    # Management key: apps scopes OK, emails:write invalid
    validate_scopes(["apps:read", "apps:write"], None)
    with pytest.raises(ValueError):
        validate_scopes(["emails:write"], None)

    # Empty list always invalid
    with pytest.raises(ValueError):
        validate_scopes([], None)


@pytest.mark.asyncio
async def test_create_and_resolve_management_key():
    key_id, plaintext = await keys.create_key(
        label="ci", app_id=None, scopes=["apps:read"], expires_at=None, created_by="cli"
    )
    principal = await keys.resolve_key(plaintext)
    assert principal is not None
    assert principal.key_id == key_id
    assert principal.app_id is None
    assert principal.scopes == frozenset({"apps:read"})


@pytest.mark.asyncio
async def test_create_and_resolve_app_key(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    key_id, plaintext = await keys.create_key(
        label="second",
        app_id=app_data["id"],
        scopes=["emails:read"],
        expires_at=None,
        created_by="admin",
    )
    principal = await keys.resolve_key(plaintext)
    assert principal is not None
    assert principal.key_id == key_id
    assert principal.app_id == app_data["id"]
    assert principal.scopes == frozenset({"emails:read"})


@pytest.mark.asyncio
async def test_resolve_unknown_returns_none():
    assert await keys.resolve_key(generate_key()) is None


@pytest.mark.asyncio
async def test_revoked_key_raises():
    key_id, plaintext = await keys.create_key(
        label="revoke-me", app_id=None, scopes=["apps:read"], expires_at=None, created_by="cli"
    )
    assert await keys.revoke_key(key_id) is True
    with pytest.raises(KeyRevokedError):
        await keys.resolve_key(plaintext)


@pytest.mark.asyncio
async def test_expired_key_raises():
    _, plaintext = await keys.create_key(
        label="expired",
        app_id=None,
        scopes=["apps:read"],
        expires_at="2000-01-01T00:00:00",
        created_by="cli",
    )
    with pytest.raises(KeyExpiredError):
        await keys.resolve_key(plaintext)


@pytest.mark.asyncio
async def test_last_used_debounce():
    key_id, plaintext = await keys.create_key(
        label="debounce", app_id=None, scopes=["apps:read"], expires_at=None, created_by="cli"
    )
    db = await get_db()

    await keys.resolve_key(plaintext)
    cursor = await db.execute("SELECT last_used_at FROM api_keys WHERE id = ?", (key_id,))
    first = (await cursor.fetchone())["last_used_at"]

    await keys.resolve_key(plaintext)
    cursor = await db.execute("SELECT last_used_at FROM api_keys WHERE id = ?", (key_id,))
    second = (await cursor.fetchone())["last_used_at"]

    assert first == second


@pytest.mark.asyncio
async def test_create_key_validates_matrix():
    with pytest.raises(ValueError):
        await keys.create_key(
            label="bad", app_id="x", scopes=["apps:write"], expires_at=None, created_by="admin"
        )


@pytest.mark.asyncio
async def test_revoke_primary_tombstones_legacy(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    plaintext = app_data["api_key"]

    principal = await keys.resolve_key(plaintext)
    assert principal is not None

    assert await keys.revoke_key(principal.key_id) is True

    db = await get_db()
    cursor = await db.execute("SELECT api_key FROM apps WHERE id = ?", (app_data["id"],))
    row = await cursor.fetchone()
    assert not verify_secret(plaintext, row["api_key"])

    with pytest.raises(KeyRevokedError):
        await keys.resolve_key(plaintext)


@pytest.mark.asyncio
async def test_legacy_fallback_lazy_migrates(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    plaintext = app_data["api_key"]

    db = await get_db()
    await db.execute("DELETE FROM api_keys WHERE app_id = ?", (app_data["id"],))
    await db.commit()

    principal = await keys.resolve_key(plaintext)
    assert principal is not None
    assert principal.app_id == app_data["id"]

    cursor = await db.execute(
        "SELECT COUNT(*) AS c FROM api_keys WHERE app_id = ?", (app_data["id"],)
    )
    row = await cursor.fetchone()
    assert row["c"] == 1


@pytest.mark.asyncio
async def test_list_keys_never_leaks_hashes():
    await keys.create_key(
        label="listed", app_id=None, scopes=["apps:read"], expires_at=None, created_by="cli"
    )
    result = await keys.list_keys(None)
    assert len(result) >= 1
    for item in result:
        assert "key_hash" not in item


@pytest.mark.asyncio
async def test_rest_auth_via_api_keys_table(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    response = await client.post(
        "/api/v1/log",
        json={"to": ["user@example.com"], "from": "noreply@myapp.com", "subject": "Hi"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_revoked_key_gets_distinct_401(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]

    principal = await keys.resolve_key(api_key)
    assert await keys.revoke_key(principal.key_id) is True

    response = await client.post(
        "/api/v1/log",
        json={"to": ["user@example.com"], "from": "noreply@myapp.com", "subject": "Hi"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "API key revoked"

    db = await get_db()
    cursor = await db.execute("SELECT api_key FROM apps WHERE id = ?", (app_data["id"],))
    row = await cursor.fetchone()
    assert not verify_secret(api_key, row["api_key"])


@pytest.mark.asyncio
async def test_mgmt_key_cannot_ingest(client):
    _, plaintext = await keys.create_key(
        label="mgmt",
        app_id=None,
        scopes=["emails:read"],
        expires_at=None,
        created_by="cli",
    )

    response = await client.post(
        "/api/v1/log",
        json={"to": ["user@example.com"], "from": "noreply@myapp.com", "subject": "Hi"},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "App API key required"


@pytest.mark.asyncio
async def test_rotate_key_dual_write(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    old_key = app_data["api_key"]

    response = await client.post(
        f"/api/v1/apps/{app_data['id']}/rotate-key",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    new_key = response.json()["api_key"]

    old_response = await client.post(
        "/api/v1/log",
        json={"to": ["user@example.com"], "from": "noreply@myapp.com", "subject": "Hi"},
        headers={"Authorization": f"Bearer {old_key}"},
    )
    assert old_response.status_code == 401

    new_response = await client.post(
        "/api/v1/log",
        json={"to": ["user@example.com"], "from": "noreply@myapp.com", "subject": "Hi"},
        headers={"Authorization": f"Bearer {new_key}"},
    )
    assert new_response.status_code == 201

    db = await get_db()
    cursor = await db.execute(
        "SELECT revoked_at FROM api_keys WHERE app_id = ? ORDER BY created_at", (app_data["id"],)
    )
    rows = await cursor.fetchall()
    revoked_states = [row["revoked_at"] is not None for row in rows]
    assert True in revoked_states
    assert False in revoked_states


@pytest.mark.asyncio
async def test_cli_create_and_resolve(capsys):
    await get_db()
    exit_code = keys.main(["create", "--label", "ci", "--scopes", "apps:write,emails:read"])
    assert exit_code == 0
    plaintext = capsys.readouterr().out.strip()

    principal = await keys.resolve_key(plaintext)
    assert principal is not None
    assert principal.app_id is None
    assert principal.scopes == frozenset({"apps:write", "emails:read"})

    db = await get_db()
    cursor = await db.execute("SELECT created_by FROM api_keys WHERE id = ?", (principal.key_id,))
    row = await cursor.fetchone()
    assert row["created_by"] == "cli"


def test_cli_create_invalid_scopes_exits_2():
    exit_code = keys.main(["create", "--label", "x", "--scopes", "emails:write"])
    assert exit_code == 2


@pytest.mark.asyncio
async def test_cli_list_and_revoke(capsys):
    await get_db()
    keys.main(["create", "--label", "listme", "--scopes", "apps:read"])
    plaintext = capsys.readouterr().out.strip()
    principal = await keys.resolve_key(plaintext)

    keys.main(["list"])
    output = capsys.readouterr().out
    assert "listme" in output

    exit_code = keys.main(["revoke", principal.key_id])
    assert exit_code == 0

    exit_code = keys.main(["revoke", principal.key_id])
    assert exit_code == 1
