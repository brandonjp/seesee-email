"""Tests for SMTP multi-key auth (seesee.keys.resolve_smtp_password)."""

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest
from aiosmtpd.smtp import Envelope, Session

from seesee import keys
from seesee.keys import resolve_smtp_password
from seesee.smtp_server import SmtpAuthenticator
from tests.conftest import create_test_app


def _authenticate(username: str, password: str):
    authenticator = SmtpAuthenticator()
    server = MagicMock()
    session = MagicMock(spec=Session)
    envelope = Envelope()

    auth_data = MagicMock()
    auth_data.login = username.encode()
    auth_data.password = password.encode()

    return authenticator(server, session, envelope, "LOGIN", auth_data), session


def test_authenticator_still_sync():
    assert not asyncio.iscoroutinefunction(SmtpAuthenticator.__call__)
    assert not inspect.iscoroutinefunction(resolve_smtp_password)


@pytest.mark.asyncio
async def test_second_key_authenticates(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    smtp_username = app_data["smtp_username"]

    _, second_plaintext = await keys.create_key(
        label="second",
        app_id=app_data["id"],
        scopes=["emails:write"],
        expires_at=None,
        created_by="admin",
    )

    result, session = _authenticate(smtp_username, second_plaintext)
    assert result.success is True
    assert session.app["id"] == app_data["id"]


@pytest.mark.asyncio
async def test_original_key_still_works(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    smtp_username = app_data["smtp_username"]
    original_plaintext = app_data["api_key"]

    await keys.create_key(
        label="second",
        app_id=app_data["id"],
        scopes=["emails:write"],
        expires_at=None,
        created_by="admin",
    )

    result, session = _authenticate(smtp_username, original_plaintext)
    assert result.success is True
    assert session.app["id"] == app_data["id"]


@pytest.mark.asyncio
async def test_revoked_key_rejected_over_smtp(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    smtp_username = app_data["smtp_username"]
    original_plaintext = app_data["api_key"]

    second_key_id, second_plaintext = await keys.create_key(
        label="second",
        app_id=app_data["id"],
        scopes=["emails:write"],
        expires_at=None,
        created_by="admin",
    )
    assert await keys.revoke_key(second_key_id) is True

    result, _ = _authenticate(smtp_username, second_plaintext)
    assert result.success is False

    primary_principal = await keys.resolve_key(original_plaintext)
    assert await keys.revoke_key(primary_principal.key_id) is True

    result, _ = _authenticate(smtp_username, original_plaintext)
    assert result.success is False


@pytest.mark.asyncio
async def test_emails_read_only_key_rejected(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    smtp_username = app_data["smtp_username"]

    _, read_only_plaintext = await keys.create_key(
        label="read-only",
        app_id=app_data["id"],
        scopes=["emails:read"],
        expires_at=None,
        created_by="admin",
    )

    result, _ = _authenticate(smtp_username, read_only_plaintext)
    assert result.success is False
