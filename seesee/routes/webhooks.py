"""Provider webhook receivers — POST /api/v1/webhooks/{provider}.

Receives delivery status callbacks from email providers (Resend, SendGrid)
and updates matching emails' status fields in SeeSee.
"""

import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request, status

from seesee.config import settings
from seesee.database import get_db
from seesee.models import WebhookEventResult, WebhookResponse

logger = logging.getLogger("seesee.webhooks")

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Supported providers and their event-to-status mappings
RESEND_STATUS_MAP: dict[str, str] = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
}

SENDGRID_STATUS_MAP: dict[str, str] = {
    "processed": "sent",
    "delivered": "delivered",
    "bounce": "bounced",
    "dropped": "dropped",
    "deferred": "deferred",
    "spamreport": "complained",
}

SUPPORTED_PROVIDERS = {"resend", "sendgrid"}

# Svix signature tolerance: 5 minutes
_SVIX_TIMESTAMP_TOLERANCE = 300


def _verify_resend_signature(body: bytes, headers: dict[str, str], secret: str) -> bool:
    """Verify Resend webhook signature using Svix HMAC-SHA256.

    Resend uses Svix for webhook delivery. The signature is computed as:
    HMAC-SHA256(secret, "{svix-id}.{svix-timestamp}.{body}")

    The secret has a "whsec_" prefix; the remaining part is base64-encoded.
    """
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not all([svix_id, svix_timestamp, svix_signature]):
        logger.warning("Resend webhook missing Svix headers")
        return False

    # Check timestamp freshness
    try:
        ts = int(svix_timestamp)
        if abs(time.time() - ts) > _SVIX_TIMESTAMP_TOLERANCE:
            logger.warning("Resend webhook timestamp too old or too new: %s", svix_timestamp)
            return False
    except (ValueError, TypeError):
        logger.warning("Resend webhook invalid timestamp: %s", svix_timestamp)
        return False

    # Strip "whsec_" prefix and decode base64 secret
    secret_str = secret
    if secret_str.startswith("whsec_"):
        secret_str = secret_str[6:]
    try:
        secret_bytes = base64.b64decode(secret_str)
    except Exception:
        logger.warning("Resend webhook secret is not valid base64")
        return False

    # Compute expected signature
    signed_content = f"{svix_id}.{svix_timestamp}.{body.decode('utf-8')}"
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_content.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    # The svix-signature header may contain multiple signatures separated by spaces
    for sig in svix_signature.split():
        if sig.startswith("v1,"):
            sig_value = sig[3:]
            if hmac.compare_digest(sig_value, expected):
                return True

    logger.warning("Resend webhook signature mismatch")
    return False


def _verify_sendgrid_token(token: str | None, secret: str) -> bool:
    """Verify SendGrid webhook using a shared token.

    Users configure their SendGrid webhook URL to include a verification
    token as a query parameter: ...?verification_token=YOUR_SECRET
    """
    if not token:
        logger.warning("SendGrid webhook missing verification_token query parameter")
        return False
    return hmac.compare_digest(token, secret)


def _parse_resend_events(payload: dict) -> list[tuple[str, str, str]]:
    """Parse Resend webhook payload into (provider_message_id, event_type, new_status) tuples."""
    events = []
    event_type = payload.get("type", "")
    new_status = RESEND_STATUS_MAP.get(event_type)
    if not new_status:
        return events

    data = payload.get("data", {})
    provider_message_id = data.get("email_id", "")
    if provider_message_id:
        events.append((provider_message_id, event_type, new_status))

    return events


def _parse_sendgrid_events(payload: list | dict) -> list[tuple[str, str, str]]:
    """Parse SendGrid Event Webhook payload into (provider_message_id, event_type, new_status) tuples.

    SendGrid sends an array of event objects. Each has an "event" field and
    "sg_message_id" for matching.
    """
    events = []
    # SendGrid always sends an array of events
    if isinstance(payload, dict):
        payload = [payload]

    for event_obj in payload:
        event_type = event_obj.get("event", "")
        new_status = SENDGRID_STATUS_MAP.get(event_type)
        if not new_status:
            continue

        sg_message_id = event_obj.get("sg_message_id", "")
        if sg_message_id:
            events.append((sg_message_id, event_type, new_status))

    return events


async def _match_and_update(provider: str, provider_message_id: str, new_status: str) -> str | None:
    """Find an email by provider + provider_message_id and update its status.

    Returns the email ID if matched, None otherwise.
    """
    db = await get_db()

    # Exact match on provider + provider_message_id
    cursor = await db.execute(
        "SELECT id FROM emails WHERE provider = ? AND provider_message_id = ?",
        (provider, provider_message_id),
    )
    row = await cursor.fetchone()

    # For SendGrid: also try matching without the filter suffix
    # SendGrid message IDs in webhooks may include ".filterXXX.XXX.XXX.X" suffixes
    if row is None and provider == "sendgrid" and ".filter" in provider_message_id:
        base_id = provider_message_id.split(".filter")[0]
        cursor = await db.execute(
            "SELECT id FROM emails WHERE provider = ? AND provider_message_id = ?",
            (provider, base_id),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    email_id = row["id"]
    await db.execute(
        "UPDATE emails SET status = ? WHERE id = ?",
        (new_status, email_id),
    )
    await db.commit()

    logger.info(
        "Webhook: updated email %s status to '%s' (provider=%s, provider_message_id=%s)",
        email_id,
        new_status,
        provider,
        provider_message_id,
    )
    return email_id


@router.post("/{provider}", response_model=WebhookResponse)
async def receive_webhook(
    provider: str,
    request: Request,
    verification_token: str | None = Query(None),
) -> WebhookResponse:
    """Receive a delivery status webhook from an email provider.

    Supported providers: resend, sendgrid.
    Verifies the webhook signature/token if the corresponding secret is configured.
    Matches events to stored emails by provider_message_id and updates status.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown webhook provider: {provider}",
        )

    body = await request.body()

    # --- Signature / token verification ---
    if provider == "resend":
        secret = settings.webhook_secret_resend
        if secret:
            headers = dict(request.headers)
            if not _verify_resend_signature(body, headers, secret):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )
        else:
            logger.warning(
                "SEESEE_WEBHOOK_SECRET_RESEND not configured — "
                "skipping signature verification for Resend webhook"
            )

    elif provider == "sendgrid":
        secret = settings.webhook_secret_sendgrid
        if secret:
            if not _verify_sendgrid_token(verification_token, secret):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook verification token",
                )
        else:
            logger.warning(
                "SEESEE_WEBHOOK_SECRET_SENDGRID not configured — "
                "skipping token verification for SendGrid webhook"
            )

    # --- Parse payload ---
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    # --- Extract events ---
    if provider == "resend":
        parsed_events = _parse_resend_events(payload)
    elif provider == "sendgrid":
        parsed_events = _parse_sendgrid_events(payload)
    else:
        parsed_events = []

    # --- Match and update ---
    results: list[WebhookEventResult] = []
    matched_count = 0

    for provider_message_id, event_type, new_status in parsed_events:
        email_id = await _match_and_update(provider, provider_message_id, new_status)
        matched = email_id is not None
        if matched:
            matched_count += 1
        results.append(
            WebhookEventResult(
                provider_message_id=provider_message_id,
                event_type=event_type,
                new_status=new_status,
                email_id=email_id,
                matched=matched,
            )
        )

    return WebhookResponse(
        processed=len(results),
        matched=matched_count,
        events=results,
    )
