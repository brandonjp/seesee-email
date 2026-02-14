"""SMTP ingest server using aiosmtpd.

Listens on a configurable port (default 2525) and:
1. Authenticates senders against per-app SMTP credentials
2. Parses MIME messages (extracts to, from, subject, HTML/text body)
3. Logs the email to the database
4. Optionally relays the message to an upstream SMTP server
"""

import email
import email.policy
import json
import logging
import uuid
import warnings
from datetime import UTC, datetime
from email.message import EmailMessage

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, AuthResult, Envelope, LoginPassword, Session

from seesee.auth import verify_secret
from seesee.config import settings
from seesee.database import get_db
from seesee.helpers import apply_body_storage_mode

logger = logging.getLogger("seesee.smtp")

# ---------------------------------------------------------------------------
# Suppress aiosmtpd's noisy "AUTH without TLS" warnings.  TLS termination is
# handled by the reverse proxy (Traefik / Caddy / nginx), so this is expected.
#
# aiosmtpd emits TWO separate messages in SMTP.__init__:
#   1. warnings.warn("Requiring AUTH while not requiring TLS …")
#   2. log.warning("auth_required == True but auth_require_tls == False")
#
# We silence both at module level because the Controller creates the SMTP
# instance in a separate thread (so a context-manager approach is unreliable).
# ---------------------------------------------------------------------------
warnings.filterwarnings(
    "ignore",
    message="Requiring AUTH while not requiring TLS",
    category=UserWarning,
)


class _SuppressAuthTlsLogFilter(logging.Filter):
    """Drop the single 'auth_required == True but auth_require_tls == False' record."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "auth_required" not in record.getMessage()


logging.getLogger("mail.log").addFilter(_SuppressAuthTlsLogFilter())


# ---------------------------------------------------------------------------
# SMTP Authenticator
# ---------------------------------------------------------------------------


class SmtpAuthenticator:
    """Authenticate SMTP clients against per-app credentials in the database."""

    async def __call__(
        self,
        server: SMTP,
        session: Session,
        envelope: Envelope,
        mechanism: str,
        auth_data: LoginPassword,
    ) -> AuthResult:
        """Validate LOGIN/PLAIN credentials against app smtp_username + smtp_password."""
        username = (
            auth_data.login.decode() if isinstance(auth_data.login, bytes) else auth_data.login
        )
        password = (
            auth_data.password.decode()
            if isinstance(auth_data.password, bytes)
            else auth_data.password
        )

        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT * FROM apps WHERE smtp_username = ?",
                (username,),
            )
            app_row = await cursor.fetchone()

            if app_row is None:
                logger.warning("SMTP AUTH failed: unknown username %r", username)
                return AuthResult(success=False, handled=False)

            if not verify_secret(password, app_row["smtp_password"]):
                logger.warning("SMTP AUTH failed: wrong password for %r", username)
                return AuthResult(success=False, handled=False)

            # Store the authenticated app on the session for later use
            session.app = dict(app_row)  # type: ignore[attr-defined]
            logger.info("SMTP AUTH success for app %r (id=%s)", app_row["name"], app_row["id"])
            return AuthResult(success=True)

        except Exception:
            logger.exception("SMTP AUTH error")
            return AuthResult(success=False, handled=False)


# ---------------------------------------------------------------------------
# MIME message parsing
# ---------------------------------------------------------------------------


def parse_mime_message(raw_data: bytes) -> dict:
    """Parse a raw MIME message and extract email fields.

    Returns a dict with: subject, from_address, to_addresses, cc_addresses,
    reply_to, body_html, body_text, body_size_bytes.
    """
    msg = email.message_from_bytes(raw_data, policy=email.policy.default)

    subject = msg.get("Subject", "") or ""
    from_address = msg.get("From", "") or ""
    reply_to = msg.get("Reply-To") or None

    # Parse address lists
    to_addresses = _parse_address_list(msg.get_all("To"))
    cc_addresses = _parse_address_list(msg.get_all("Cc"))

    # Extract bodies
    body_html = None
    body_text = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            # Skip multipart containers and attachments
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain" and body_text is None:
                body_text = _decode_payload(part)
            elif content_type == "text/html" and body_html is None:
                body_html = _decode_payload(part)
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            body_text = _decode_payload(msg)
        elif content_type == "text/html":
            body_html = _decode_payload(msg)

    body_size_bytes = len(raw_data)

    return {
        "subject": subject,
        "from_address": from_address,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
        "reply_to": reply_to,
        "body_html": body_html,
        "body_text": body_text,
        "body_size_bytes": body_size_bytes,
    }


def _decode_payload(part: EmailMessage) -> str | None:
    """Safely decode a MIME part payload to a string."""
    try:
        payload = part.get_content()
        if isinstance(payload, str):
            return payload
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
    except Exception:
        logger.debug("Failed to decode MIME part", exc_info=True)
    return None


def _parse_address_list(header_values: list | None) -> list[str]:
    """Parse a list of address header values into a flat list of addresses."""
    if not header_values:
        return []
    addresses: list[str] = []
    for val in header_values:
        if val is None:
            continue
        val_str = str(val)
        for addr in val_str.split(","):
            addr = addr.strip()
            if addr:
                addresses.append(addr)
    return addresses


# ---------------------------------------------------------------------------
# SMTP Handler — receives messages after AUTH
# ---------------------------------------------------------------------------


class SeeSeeHandler:
    """aiosmtpd handler that logs emails to the database and optionally relays."""

    async def handle_RCPT(  # noqa: N802
        self,
        server: SMTP,
        session: Session,
        envelope: Envelope,
        address: str,
        rcpt_options: list[str],
    ) -> str:
        """Accept recipient addresses (require prior AUTH)."""
        if not getattr(session, "app", None):
            return "530 5.7.0 Authentication required"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_MAIL(  # noqa: N802
        self,
        server: SMTP,
        session: Session,
        envelope: Envelope,
        address: str,
        mail_options: list[str],
    ) -> str:
        """Accept sender address (require prior AUTH)."""
        if not getattr(session, "app", None):
            return "530 5.7.0 Authentication required"
        envelope.mail_from = address
        return "250 OK"

    async def handle_DATA(  # noqa: N802
        self,
        server: SMTP,
        session: Session,
        envelope: Envelope,
    ) -> str:
        """Process the received message: parse, store in DB, optionally relay."""
        app = getattr(session, "app", None)
        if not app:
            return "530 5.7.0 Authentication required"

        try:
            raw_data = envelope.content
            if isinstance(raw_data, str):
                raw_data = raw_data.encode("utf-8")

            parsed = parse_mime_message(raw_data)

            # Use envelope addresses if MIME headers are missing/empty
            to_addresses = parsed["to_addresses"]
            if not to_addresses and envelope.rcpt_tos:
                to_addresses = list(envelope.rcpt_tos)

            from_address = parsed["from_address"]
            if not from_address and envelope.mail_from:
                from_address = envelope.mail_from

            # Store to database
            email_id = await _store_email(
                app=app,
                to_addresses=to_addresses,
                from_address=from_address,
                subject=parsed["subject"],
                body_html=parsed["body_html"],
                body_text=parsed["body_text"],
                body_size_bytes=parsed["body_size_bytes"],
                cc_addresses=parsed["cc_addresses"],
                reply_to=parsed["reply_to"],
            )

            # Optional relay
            relay_status = None
            if settings.smtp_relay_host:
                relay_status = await _relay_message(raw_data, envelope)
                if relay_status != "relayed":
                    # Update the email record to note relay failure
                    db = await get_db()
                    await db.execute(
                        "UPDATE emails SET error_message = ? WHERE id = ?",
                        (f"Relay failed: {relay_status}", email_id),
                    )
                    await db.commit()

            logger.info(
                "SMTP email logged: id=%s app=%s to=%s relay=%s",
                email_id,
                app["name"],
                to_addresses,
                relay_status or "none",
            )
            return "250 Message accepted for delivery"

        except Exception:
            logger.exception("Failed to process SMTP message")
            return "451 Requested action aborted: error in processing"


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


async def _store_email(
    *,
    app: dict,
    to_addresses: list[str],
    from_address: str,
    subject: str,
    body_html: str | None,
    body_text: str | None,
    body_size_bytes: int,
    cc_addresses: list[str] | None,
    reply_to: str | None,
) -> str:
    """Insert the parsed email into the database. Returns the email_id."""
    db = await get_db()

    email_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    # Apply the app's body_storage_mode
    stored_html, stored_text, body_preview, _ = apply_body_storage_mode(
        body_html, body_text, app["body_storage_mode"]
    )

    to_json = json.dumps(to_addresses)
    cc_json = json.dumps(cc_addresses) if cc_addresses else None

    await db.execute(
        """INSERT INTO emails (
            id, app_id, to_addresses, from_address, subject,
            body_html, body_text, body_preview, body_size_bytes,
            status, provider, provider_message_id, error_message,
            metadata, cc_addresses, bcc_addresses, reply_to, tags,
            ingest_method, logged_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            email_id,
            app["id"],
            to_json,
            from_address,
            subject,
            stored_html,
            stored_text,
            body_preview,
            body_size_bytes,
            "sent",
            None,  # provider
            None,  # provider_message_id
            None,  # error_message
            None,  # metadata
            cc_json,
            None,  # bcc_addresses
            reply_to,
            None,  # tags
            "smtp",
            now.isoformat(),
            now.isoformat(),
        ),
    )

    # Update app's last_activity_at
    await db.execute(
        "UPDATE apps SET last_activity_at = ? WHERE id = ?",
        (now.isoformat(), app["id"]),
    )

    await db.commit()
    return email_id


# ---------------------------------------------------------------------------
# Optional upstream relay
# ---------------------------------------------------------------------------


async def _relay_message(raw_data: bytes, envelope: Envelope) -> str:
    """Forward the raw message to the configured upstream SMTP server.

    Returns 'relayed' on success, or an error description on failure.
    """
    try:
        import aiosmtplib

        await aiosmtplib.send(
            raw_data,
            sender=envelope.mail_from,
            recipients=envelope.rcpt_tos,
            hostname=settings.smtp_relay_host,
            port=settings.smtp_relay_port,
            username=settings.smtp_relay_username or None,
            password=settings.smtp_relay_password or None,
            use_tls=settings.smtp_relay_tls,
        )
        logger.info("Relayed message to %s:%d", settings.smtp_relay_host, settings.smtp_relay_port)
        return "relayed"
    except Exception as exc:
        logger.error("Relay failed: %s", exc)
        return str(exc)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


_controller: Controller | None = None


async def start_smtp_server() -> None:
    """Start the SMTP server on the configured port."""
    global _controller

    handler = SeeSeeHandler()
    authenticator = SmtpAuthenticator()

    _controller = Controller(
        handler,
        hostname="0.0.0.0",
        port=settings.smtp_port,
        authenticator=authenticator,
        auth_required=True,
        auth_require_tls=False,
    )
    _controller.start()
    logger.info("SMTP server started on port %d", settings.smtp_port)


async def stop_smtp_server() -> None:
    """Stop the SMTP server gracefully."""
    global _controller
    if _controller is not None:
        _controller.stop()
        _controller = None
        logger.info("SMTP server stopped")
