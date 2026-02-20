"""Email ingest routes — POST /api/v1/log and /api/v1/log/batch."""

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from seesee.database import get_db
from seesee.dependencies import get_current_app
from seesee.helpers import apply_body_storage_mode
from seesee.timezone import utc_iso, utc_now, utc_now_iso
from seesee.models import (
    BatchLogError,
    BatchLogRequest,
    BatchLogResponse,
    EmailLogRequest,
    EmailLogResponse,
)

logger = logging.getLogger("seesee.ingest")

router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post(
    "/log",
    response_model=EmailLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def log_email(
    email: EmailLogRequest,
    app: dict = Depends(get_current_app),  # noqa: B008
) -> EmailLogResponse:
    """Log a single email. Requires API key authentication."""
    db = await get_db()

    email_id = str(uuid.uuid4())
    now = utc_now()
    now_iso = utc_now_iso()

    body_html, body_text, body_preview, body_size_bytes = apply_body_storage_mode(
        email.body_html,
        email.body_text,
        app["body_storage_mode"],
    )

    # Serialize list/dict fields to JSON for SQLite TEXT columns
    to_json = json.dumps(email.to)
    cc_json = json.dumps(email.cc) if email.cc else None
    bcc_json = json.dumps(email.bcc) if email.bcc else None
    tags_json = json.dumps(email.tags) if email.tags else None
    metadata_json = json.dumps(email.metadata) if email.metadata else None

    logged_at_iso = utc_iso(email.logged_at) if email.logged_at else now_iso

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
            email.from_address,
            email.subject,
            body_html,
            body_text,
            body_preview,
            body_size_bytes,
            email.status,
            email.provider,
            email.provider_message_id,
            email.error_message,
            metadata_json,
            cc_json,
            bcc_json,
            email.reply_to,
            tags_json,
            "api",
            logged_at_iso,
            now_iso,
        ),
    )

    # Update app's last_activity_at
    await db.execute(
        "UPDATE apps SET last_activity_at = ? WHERE id = ?",
        (now_iso, app["id"]),
    )

    await db.commit()

    return EmailLogResponse(
        id=email_id,
        status="logged",
        created_at=now,
    )


async def _insert_single_email(email: EmailLogRequest, app: dict) -> str:
    """Insert a single email into the database. Returns the email ID."""
    db = await get_db()
    email_id = str(uuid.uuid4())
    now_iso = utc_now_iso()

    body_html, body_text, body_preview, body_size_bytes = apply_body_storage_mode(
        email.body_html, email.body_text, app["body_storage_mode"]
    )

    to_json = json.dumps(email.to)
    cc_json = json.dumps(email.cc) if email.cc else None
    bcc_json = json.dumps(email.bcc) if email.bcc else None
    tags_json = json.dumps(email.tags) if email.tags else None
    metadata_json = json.dumps(email.metadata) if email.metadata else None
    logged_at_iso = utc_iso(email.logged_at) if email.logged_at else now_iso

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
            email.from_address,
            email.subject,
            body_html,
            body_text,
            body_preview,
            body_size_bytes,
            email.status,
            email.provider,
            email.provider_message_id,
            email.error_message,
            metadata_json,
            cc_json,
            bcc_json,
            email.reply_to,
            tags_json,
            "api",
            logged_at_iso,
            now_iso,
        ),
    )
    return email_id


@router.post(
    "/log/batch",
    response_model=BatchLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def log_email_batch(
    request: BatchLogRequest,
    app: dict = Depends(get_current_app),  # noqa: B008
) -> BatchLogResponse:
    """Log a batch of emails (max 100). Requires API key authentication."""
    db = await get_db()
    logged = 0
    errors: list[BatchLogError] = []

    for i, email in enumerate(request.emails):
        try:
            await _insert_single_email(email, app)
            logged += 1
        except Exception as exc:
            logger.warning("Batch item %d failed: %s", i, exc)
            errors.append(BatchLogError(index=i, error=str(exc)))

    # Update app's last_activity_at
    if logged > 0:
        await db.execute(
            "UPDATE apps SET last_activity_at = ? WHERE id = ?",
            (utc_now_iso(), app["id"]),
        )

    await db.commit()

    return BatchLogResponse(logged=logged, errors=errors)
