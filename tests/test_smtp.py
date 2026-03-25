"""Tests for SMTP ingest server."""

import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock

import pytest
from aiosmtpd.smtp import Envelope, Session

from seesee.database import get_db
from seesee.smtp_server import (
    SeeSeeHandler,
    SmtpAuthenticator,
    parse_mime_message,
)
from tests.conftest import create_test_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(app: dict | None = None) -> MagicMock:
    """Create a mock aiosmtpd Session with optional authenticated app."""
    session = MagicMock()
    if app is not None:
        session.app = app
    else:
        # Simulate no auth — configure so getattr(session, "app", None) returns None
        session.configure_mock(**{"app": None})
    return session


def _make_envelope(
    mail_from: str = "sender@test.com",
    rcpt_tos: list[str] | None = None,
    content: bytes = b"",
) -> Envelope:
    """Create an Envelope with the given fields."""
    envelope = Envelope()
    envelope.mail_from = mail_from
    envelope.rcpt_tos = rcpt_tos or ["rcpt@test.com"]
    envelope.content = content
    return envelope


def _build_simple_text_email(
    from_addr: str = "sender@test.com",
    to_addr: str = "rcpt@test.com",
    subject: str = "Test Subject",
    body: str = "Hello world",
    cc: str | None = None,
    reply_to: str | None = None,
) -> bytes:
    """Build a simple text/plain MIME message."""
    msg = MIMEText(body, "plain")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    return msg.as_bytes()


def _build_html_email(
    from_addr: str = "sender@test.com",
    to_addr: str = "rcpt@test.com",
    subject: str = "HTML Subject",
    body: str = "<h1>Hello</h1><p>World</p>",
) -> bytes:
    """Build a simple text/html MIME message."""
    msg = MIMEText(body, "html")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    return msg.as_bytes()


def _build_multipart_alternative(
    from_addr: str = "sender@test.com",
    to_addr: str = "rcpt@test.com",
    subject: str = "Multipart Subject",
    text_body: str = "Plain text version",
    html_body: str = "<h1>HTML version</h1>",
) -> bytes:
    """Build a multipart/alternative message with text and HTML parts."""
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg.as_bytes()


def _build_multipart_mixed_with_attachment(
    from_addr: str = "sender@test.com",
    to_addr: str = "rcpt@test.com",
    subject: str = "Mixed Subject",
    text_body: str = "See attached",
    html_body: str = "<p>See attached</p>",
) -> bytes:
    """Build a multipart/mixed message with a text/html alternative and a fake attachment."""
    outer = MIMEMultipart("mixed")
    outer["From"] = from_addr
    outer["To"] = to_addr
    outer["Subject"] = subject

    # Inner alternative part
    inner = MIMEMultipart("alternative")
    inner.attach(MIMEText(text_body, "plain"))
    inner.attach(MIMEText(html_body, "html"))
    outer.attach(inner)

    # Attachment (plain text file as attachment)
    attachment = MIMEText("file contents", "plain")
    attachment.add_header("Content-Disposition", "attachment", filename="readme.txt")
    outer.attach(attachment)

    return outer.as_bytes()


# ---------------------------------------------------------------------------
# MIME parsing tests
# ---------------------------------------------------------------------------


class TestParseMimeMessage:
    """Tests for parse_mime_message()."""

    def test_simple_text_email(self):
        raw = _build_simple_text_email(
            from_addr="alice@example.com",
            to_addr="bob@example.com",
            subject="Hello Bob",
            body="Hi there!",
        )
        result = parse_mime_message(raw)

        assert result["subject"] == "Hello Bob"
        assert result["from_address"] == "alice@example.com"
        assert result["to_addresses"] == ["bob@example.com"]
        assert "Hi there!" in result["body_text"]
        assert result["body_html"] is None
        assert result["cc_addresses"] == []
        assert result["reply_to"] is None
        assert result["body_size_bytes"] == len(raw)

    def test_html_email(self):
        raw = _build_html_email(body="<h1>Title</h1><p>Content</p>")
        result = parse_mime_message(raw)

        assert "<h1>Title</h1><p>Content</p>" in result["body_html"]
        assert result["body_text"] is None
        assert result["subject"] == "HTML Subject"

    def test_multipart_alternative(self):
        raw = _build_multipart_alternative(
            text_body="Plain version",
            html_body="<b>HTML version</b>",
        )
        result = parse_mime_message(raw)

        assert "Plain version" in result["body_text"]
        assert "<b>HTML version</b>" in result["body_html"]
        assert result["subject"] == "Multipart Subject"

    def test_multipart_mixed_with_attachment(self):
        """Attachments are ignored; only inline text/html parts are extracted."""
        raw = _build_multipart_mixed_with_attachment(
            text_body="Main body text",
            html_body="<p>Main body HTML</p>",
        )
        result = parse_mime_message(raw)

        assert "Main body text" in result["body_text"]
        assert "<p>Main body HTML</p>" in result["body_html"]
        # The attachment content should NOT appear in body_text
        assert "file contents" not in (result["body_text"] or "")

    def test_cc_and_reply_to_headers(self):
        raw = _build_simple_text_email(
            cc="cc1@example.com, cc2@example.com",
            reply_to="reply@example.com",
        )
        result = parse_mime_message(raw)

        assert "cc1@example.com" in result["cc_addresses"]
        assert "cc2@example.com" in result["cc_addresses"]
        assert result["reply_to"] == "reply@example.com"

    def test_empty_message(self):
        raw = b"From: a@b.com\r\nTo: c@d.com\r\nSubject: Empty\r\n\r\n"
        result = parse_mime_message(raw)

        assert result["subject"] == "Empty"
        assert result["from_address"] == "a@b.com"
        assert result["to_addresses"] == ["c@d.com"]


# ---------------------------------------------------------------------------
# SMTP AUTH tests
# ---------------------------------------------------------------------------


class TestSmtpAuthenticator:
    """Tests for SmtpAuthenticator."""

    @pytest.mark.asyncio
    async def test_auth_success(self, client, admin_auth_header):
        """Valid SMTP credentials authenticate successfully (API key as password)."""
        app_data = await create_test_app(client, admin_auth_header)
        smtp_username = app_data["smtp_username"]
        api_key = app_data["api_key"]

        authenticator = SmtpAuthenticator()
        server = MagicMock()
        session = MagicMock(spec=Session)
        envelope = Envelope()

        auth_data = MagicMock()
        auth_data.login = smtp_username.encode()
        auth_data.password = api_key.encode()

        result = await authenticator(server, session, envelope, "LOGIN", auth_data)

        assert result.success is True
        # App should be stored on the session
        assert session.app["id"] == app_data["id"]

    @pytest.mark.asyncio
    async def test_auth_wrong_password(self, client, admin_auth_header):
        """Wrong password returns auth failure."""
        app_data = await create_test_app(client, admin_auth_header)
        smtp_username = app_data["smtp_username"]

        authenticator = SmtpAuthenticator()
        server = MagicMock()
        session = MagicMock(spec=Session)
        envelope = Envelope()

        auth_data = MagicMock()
        auth_data.login = smtp_username.encode()
        auth_data.password = b"wrong_password"

        result = await authenticator(server, session, envelope, "LOGIN", auth_data)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_auth_unknown_username(self, client, admin_auth_header):
        """Unknown SMTP username returns auth failure."""
        # Ensure DB is initialized (create an app first to ensure schema exists)
        await create_test_app(client, admin_auth_header)

        authenticator = SmtpAuthenticator()
        server = MagicMock()
        session = MagicMock(spec=Session)
        envelope = Envelope()

        auth_data = MagicMock()
        auth_data.login = b"nonexistent-app"
        auth_data.password = b"whatever"

        result = await authenticator(server, session, envelope, "LOGIN", auth_data)

        assert result.success is False


# ---------------------------------------------------------------------------
# Handler tests — require AUTH before MAIL/RCPT/DATA
# ---------------------------------------------------------------------------


class TestSeeSeeHandler:
    """Tests for SeeSeeHandler (AUTH enforcement and data handling)."""

    @pytest.mark.asyncio
    async def test_handle_mail_requires_auth(self):
        """MAIL FROM is rejected without prior authentication."""
        handler = SeeSeeHandler()
        session = _make_session(app=None)
        envelope = Envelope()
        result = await handler.handle_MAIL(MagicMock(), session, envelope, "a@b.com", [])
        assert "530" in result

    @pytest.mark.asyncio
    async def test_handle_rcpt_requires_auth(self):
        """RCPT TO is rejected without prior authentication."""
        handler = SeeSeeHandler()
        session = _make_session(app=None)
        envelope = Envelope()
        result = await handler.handle_RCPT(MagicMock(), session, envelope, "a@b.com", [])
        assert "530" in result

    @pytest.mark.asyncio
    async def test_handle_data_requires_auth(self):
        """DATA is rejected without prior authentication."""
        handler = SeeSeeHandler()
        session = _make_session(app=None)
        envelope = Envelope()
        result = await handler.handle_DATA(MagicMock(), session, envelope)
        assert "530" in result

    @pytest.mark.asyncio
    async def test_handle_mail_with_auth(self):
        """MAIL FROM is accepted with authenticated session."""
        handler = SeeSeeHandler()
        app = {"id": "test", "name": "Test", "body_storage_mode": "full"}
        session = _make_session(app=app)
        envelope = Envelope()
        result = await handler.handle_MAIL(MagicMock(), session, envelope, "a@b.com", [])
        assert result == "250 OK"
        assert envelope.mail_from == "a@b.com"

    @pytest.mark.asyncio
    async def test_handle_rcpt_with_auth(self):
        """RCPT TO is accepted with authenticated session."""
        handler = SeeSeeHandler()
        app = {"id": "test", "name": "Test", "body_storage_mode": "full"}
        session = _make_session(app=app)
        envelope = Envelope()
        result = await handler.handle_RCPT(MagicMock(), session, envelope, "rcpt@b.com", [])
        assert result == "250 OK"
        assert "rcpt@b.com" in envelope.rcpt_tos


# ---------------------------------------------------------------------------
# Database insertion via SMTP path
# ---------------------------------------------------------------------------


class TestSmtpDatabaseInsertion:
    """Tests for email storage via the SMTP ingest path."""

    @pytest.mark.asyncio
    async def test_handle_data_stores_email(self, client, admin_auth_header):
        """A complete SMTP DATA flow stores the email in the database."""
        app_data = await create_test_app(client, admin_auth_header)

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "Test App",
            "body_storage_mode": "full",
        }
        session = _make_session(app=app)

        raw_msg = _build_simple_text_email(
            from_addr="sender@test.com",
            to_addr="rcpt@test.com",
            subject="SMTP Test Email",
            body="Hello from SMTP",
        )
        envelope = _make_envelope(content=raw_msg)

        result = await handler.handle_DATA(MagicMock(), session, envelope)

        assert result == "250 Message accepted for delivery"

        # Verify in database
        db = await get_db()
        cursor = await db.execute("SELECT * FROM emails WHERE app_id = ?", (app_data["id"],))
        row = await cursor.fetchone()
        assert row is not None
        assert row["subject"] == "SMTP Test Email"
        assert row["from_address"] == "sender@test.com"
        assert json.loads(row["to_addresses"]) == ["rcpt@test.com"]
        assert row["ingest_method"] == "smtp"
        assert row["status"] == "sent"
        assert "Hello from SMTP" in row["body_text"]

    @pytest.mark.asyncio
    async def test_handle_data_stores_html_email(self, client, admin_auth_header):
        """HTML email bodies are stored correctly."""
        app_data = await create_test_app(client, admin_auth_header)

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "Test App",
            "body_storage_mode": "full",
        }
        session = _make_session(app=app)

        raw_msg = _build_multipart_alternative(
            subject="HTML Test",
            text_body="Plain fallback",
            html_body="<h1>Rich HTML</h1>",
        )
        envelope = _make_envelope(content=raw_msg)

        result = await handler.handle_DATA(MagicMock(), session, envelope)

        assert result == "250 Message accepted for delivery"

        db = await get_db()
        cursor = await db.execute("SELECT * FROM emails WHERE app_id = ?", (app_data["id"],))
        row = await cursor.fetchone()
        assert row is not None
        assert "<h1>Rich HTML</h1>" in row["body_html"]
        assert "Plain fallback" in row["body_text"]

    @pytest.mark.asyncio
    async def test_ingest_method_is_smtp(self, client, admin_auth_header):
        """Emails ingested via SMTP have ingest_method='smtp'."""
        app_data = await create_test_app(client, admin_auth_header)

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "Test App",
            "body_storage_mode": "full",
        }
        session = _make_session(app=app)

        raw_msg = _build_simple_text_email(subject="Method Check")
        envelope = _make_envelope(content=raw_msg)

        await handler.handle_DATA(MagicMock(), session, envelope)

        db = await get_db()
        cursor = await db.execute(
            "SELECT ingest_method FROM emails WHERE app_id = ?", (app_data["id"],)
        )
        row = await cursor.fetchone()
        assert row["ingest_method"] == "smtp"

    @pytest.mark.asyncio
    async def test_updates_last_activity(self, client, admin_auth_header):
        """SMTP ingest updates the app's last_activity_at timestamp."""
        app_data = await create_test_app(client, admin_auth_header)
        app_id = app_data["id"]

        # Verify last_activity_at is initially None
        db = await get_db()
        cursor = await db.execute("SELECT last_activity_at FROM apps WHERE id = ?", (app_id,))
        row = await cursor.fetchone()
        assert row["last_activity_at"] is None

        handler = SeeSeeHandler()
        app = {"id": app_id, "name": "Test App", "body_storage_mode": "full"}
        session = _make_session(app=app)

        raw_msg = _build_simple_text_email(subject="Activity Test")
        envelope = _make_envelope(content=raw_msg)

        await handler.handle_DATA(MagicMock(), session, envelope)

        cursor = await db.execute("SELECT last_activity_at FROM apps WHERE id = ?", (app_id,))
        row = await cursor.fetchone()
        assert row["last_activity_at"] is not None

    @pytest.mark.asyncio
    async def test_fts_indexed_after_smtp_ingest(self, client, admin_auth_header):
        """Email ingested via SMTP is searchable via FTS5."""
        app_data = await create_test_app(client, admin_auth_header)

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "Test App",
            "body_storage_mode": "full",
        }
        session = _make_session(app=app)

        raw_msg = _build_simple_text_email(
            subject="UniqueFtsSmtpTerm password reset",
            body="Your password has been reset.",
        )
        envelope = _make_envelope(content=raw_msg)

        await handler.handle_DATA(MagicMock(), session, envelope)

        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM emails_fts WHERE emails_fts MATCH ?",
            ("UniqueFtsSmtpTerm",),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Body storage mode enforcement via SMTP
# ---------------------------------------------------------------------------


class TestSmtpBodyStorageMode:
    """Tests that body_storage_mode is enforced when ingesting via SMTP."""

    @pytest.mark.asyncio
    async def test_full_mode_stores_both(self, client, admin_auth_header):
        """In 'full' mode, both HTML and text are stored."""
        app_data = await create_test_app(client, admin_auth_header, body_storage_mode="full")

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "Test App",
            "body_storage_mode": "full",
        }
        session = _make_session(app=app)

        raw_msg = _build_multipart_alternative(
            text_body="Text body",
            html_body="<p>HTML body</p>",
        )
        envelope = _make_envelope(content=raw_msg)

        await handler.handle_DATA(MagicMock(), session, envelope)

        db = await get_db()
        cursor = await db.execute("SELECT * FROM emails WHERE app_id = ?", (app_data["id"],))
        row = await cursor.fetchone()
        assert "<p>HTML body</p>" in row["body_html"]
        assert "Text body" in row["body_text"]
        assert row["body_preview"] is not None

    @pytest.mark.asyncio
    async def test_text_only_mode_strips_html(self, client, admin_auth_header):
        """In 'text_only' mode, body_html is NULL."""
        app_data = await create_test_app(
            client, admin_auth_header, name="TextOnly SMTP", body_storage_mode="text_only"
        )

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "TextOnly SMTP",
            "body_storage_mode": "text_only",
        }
        session = _make_session(app=app)

        raw_msg = _build_multipart_alternative(
            text_body="Stored text",
            html_body="<p>Discarded HTML</p>",
        )
        envelope = _make_envelope(content=raw_msg)

        await handler.handle_DATA(MagicMock(), session, envelope)

        db = await get_db()
        cursor = await db.execute("SELECT * FROM emails WHERE app_id = ?", (app_data["id"],))
        row = await cursor.fetchone()
        assert row["body_html"] is None
        assert "Stored text" in row["body_text"]
        assert row["body_preview"] is not None

    @pytest.mark.asyncio
    async def test_preview_mode_strips_all(self, client, admin_auth_header):
        """In 'preview' mode, both body_html and body_text are NULL, only preview remains."""
        app_data = await create_test_app(
            client, admin_auth_header, name="Preview SMTP", body_storage_mode="preview"
        )

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "Preview SMTP",
            "body_storage_mode": "preview",
        }
        session = _make_session(app=app)

        raw_msg = _build_multipart_alternative(
            text_body="Preview source text",
            html_body="<p>Preview source html</p>",
        )
        envelope = _make_envelope(content=raw_msg)

        await handler.handle_DATA(MagicMock(), session, envelope)

        db = await get_db()
        cursor = await db.execute("SELECT * FROM emails WHERE app_id = ?", (app_data["id"],))
        row = await cursor.fetchone()
        assert row["body_html"] is None
        assert row["body_text"] is None
        assert "Preview source text" in row["body_preview"]


# ---------------------------------------------------------------------------
# Capture-only mode
# ---------------------------------------------------------------------------


class TestCaptureOnlyMode:
    """Test that SMTP ingest captures emails without forwarding."""

    @pytest.mark.asyncio
    async def test_email_captured_and_stored(self, client, admin_auth_header):
        """SMTP ingest captures and stores emails."""
        app_data = await create_test_app(client, admin_auth_header)

        handler = SeeSeeHandler()
        app = {
            "id": app_data["id"],
            "name": "Test App",
            "body_storage_mode": "full",
        }
        session = _make_session(app=app)

        raw_msg = _build_simple_text_email(subject="Capture Only")
        envelope = _make_envelope(content=raw_msg)

        result = await handler.handle_DATA(MagicMock(), session, envelope)

        assert result == "250 Message accepted for delivery"

        # Email is stored
        db = await get_db()
        cursor = await db.execute("SELECT * FROM emails WHERE app_id = ?", (app_data["id"],))
        row = await cursor.fetchone()
        assert row is not None
        assert row["error_message"] is None
