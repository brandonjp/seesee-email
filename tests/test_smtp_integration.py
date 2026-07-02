"""Integration tests driving a real aiosmtpd Controller with a real SMTP client.

These exist because unit tests that call SmtpAuthenticator directly (and await
it) cannot catch how aiosmtpd actually invokes the authenticator: synchronously,
without awaiting. An ``async def`` authenticator returns a coroutine object,
which aiosmtpd's legacy result handling treats as a successful login — the
credential check never runs, ``session.authenticated`` is never set, and every
subsequent MAIL FROM is rejected with ``530 Authentication required``.
"""

import asyncio
import inspect
import smtplib
import socket

import pytest
from aiosmtpd.controller import Controller

from seesee.database import get_db
from seesee.smtp_server import SeeSeeHandler, SmtpAuthenticator
from tests.conftest import create_test_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def smtp_controller(client):
    """Start a real SMTP server wired exactly like production start_smtp_server()."""
    port = _free_port()
    controller = Controller(
        SeeSeeHandler(),
        hostname="127.0.0.1",
        port=port,
        authenticator=SmtpAuthenticator(),
        auth_required=True,
        auth_require_tls=False,
    )
    controller.start()
    yield controller, port
    controller.stop()


def test_authenticator_is_sync():
    """aiosmtpd never awaits the authenticator — it must be a plain callable."""
    assert not inspect.iscoroutinefunction(SmtpAuthenticator.__call__), (
        "SmtpAuthenticator.__call__ must be synchronous: aiosmtpd calls the "
        "authenticator without awaiting it, so an async def silently breaks AUTH"
    )


class TestSmtpWireAuth:
    """AUTH PLAIN → MAIL FROM over a real socket."""

    @pytest.mark.asyncio
    async def test_valid_credentials_full_send(self, client, admin_auth_header, smtp_controller):
        """Valid app credentials can complete AUTH → MAIL → RCPT → DATA and the email is stored."""
        app_data = await create_test_app(client, admin_auth_header)
        _, port = smtp_controller

        def send() -> None:
            with smtplib.SMTP("127.0.0.1", port, timeout=10) as smtp:
                smtp.login(app_data["smtp_username"], app_data["api_key"])
                smtp.sendmail(
                    "sender@test.com",
                    ["rcpt@test.com"],
                    b"From: sender@test.com\r\nTo: rcpt@test.com\r\n"
                    b"Subject: Wire Test\r\n\r\nHello over the wire",
                )

        await asyncio.to_thread(send)

        db = await get_db()
        cursor = await db.execute("SELECT * FROM emails WHERE app_id = ?", (app_data["id"],))
        row = await cursor.fetchone()
        assert row is not None
        assert row["subject"] == "Wire Test"
        assert row["ingest_method"] == "smtp"

    @pytest.mark.asyncio
    async def test_invalid_credentials_rejected(self, client, admin_auth_header, smtp_controller):
        """Bogus credentials must be rejected at AUTH time (535), not accepted."""
        await create_test_app(client, admin_auth_header)
        _, port = smtp_controller

        def attempt_login() -> None:
            with smtplib.SMTP("127.0.0.1", port, timeout=10) as smtp:
                smtp.login("bogus-user", "bogus-password")

        with pytest.raises(smtplib.SMTPAuthenticationError):
            await asyncio.to_thread(attempt_login)

    @pytest.mark.asyncio
    async def test_mail_from_rejected_without_auth(
        self, client, admin_auth_header, smtp_controller
    ):
        """MAIL FROM without AUTH is rejected with 530."""
        await create_test_app(client, admin_auth_header)
        _, port = smtp_controller

        def attempt_mail() -> tuple[int, bytes]:
            with smtplib.SMTP("127.0.0.1", port, timeout=10) as smtp:
                smtp.ehlo("test.local")
                return smtp.docmd("MAIL", "FROM:<sender@test.com>")

        code, _ = await asyncio.to_thread(attempt_mail)
        assert code == 530
