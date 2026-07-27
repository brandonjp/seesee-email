"""CSRF token tests — unit round-trip now; endpoint enforcement tests below."""

from httpx import AsyncClient

from seesee.csrf import CSRF_FIELD_NAME, make_csrf_token, validate_csrf_token
from tests.conftest import create_test_app


def test_csrf_round_trip():
    token = make_csrf_token("admin", "sekrit")
    assert validate_csrf_token(token, "admin", "sekrit", 3600)


def test_csrf_wrong_username_rejected():
    token = make_csrf_token("admin", "sekrit")
    assert not validate_csrf_token(token, "other", "sekrit", 3600)


def test_csrf_wrong_secret_rejected():
    token = make_csrf_token("admin", "sekrit")
    assert not validate_csrf_token(token, "admin", "different", 3600)


def test_csrf_garbage_rejected():
    assert not validate_csrf_token("not-a-token", "admin", "sekrit", 3600)


async def _login(client: AsyncClient) -> None:
    response = await client.post("/login", data={"username": "admin", "password": "testpassword"})
    assert response.status_code == 303


async def test_session_post_without_token_rejected(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    await _login(client)
    response = await client.post(f"/apps/{app_data['id']}/rename", data={"name": "Renamed"})
    assert response.status_code == 403


async def test_session_post_with_token_accepted(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    await _login(client)
    token = make_csrf_token("admin", "testpassword")
    response = await client.post(
        f"/apps/{app_data['id']}/rename",
        data={"name": "Renamed", CSRF_FIELD_NAME: token},
    )
    assert response.status_code == 303


async def test_header_token_accepted(client):
    await _login(client)
    token = make_csrf_token("admin", "testpassword")
    response = await client.post("/settings/cleanup", headers={"X-CSRF-Token": token})
    assert response.status_code == 303


async def test_bearer_rest_unaffected(client, admin_auth_header):
    response = await client.post(
        "/api/v1/apps", json={"name": "No CSRF Needed"}, headers=admin_auth_header
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Logout (code review 2026-07-27)
# ---------------------------------------------------------------------------


async def test_logout_without_token_rejected(client):
    """base.html ships a token on the logout form; the handler must check it."""
    await _login(client)
    response = await client.post("/logout")
    assert response.status_code == 403


async def test_logout_with_token_accepted(client):
    await _login(client)
    page = await client.get("/")
    token = _extract_meta_csrf(page.text)
    response = await client.post("/logout", data={CSRF_FIELD_NAME: token})
    assert response.status_code == 303


async def test_logout_without_session_still_works(client):
    """A visitor whose session already expired must not be stranded behind a
    logout button that 403s — there is nothing left to protect."""
    response = await client.post("/logout")
    assert response.status_code == 303


def _extract_meta_csrf(html: str) -> str:
    import re

    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, "base.html should expose a csrf-token meta tag"
    return match.group(1)
