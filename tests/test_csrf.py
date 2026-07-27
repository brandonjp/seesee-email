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
