"""Email ingest routes — POST /api/v1/log and /api/v1/log/batch."""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from seesee.database import get_db
from seesee.dependencies import get_current_app
from seesee.helpers import apply_body_storage_mode
from seesee.models import EmailLogRequest, EmailLogResponse

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
    now = datetime.now(UTC)

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

    logged_at = email.logged_at or now

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
            logged_at.isoformat(),
            now.isoformat(),
        ),
    )

    # Update app's last_activity_at
    await db.execute(
        "UPDATE apps SET last_activity_at = ? WHERE id = ?",
        (now.isoformat(), app["id"]),
    )

    await db.commit()

    return EmailLogResponse(
        id=email_id,
        status="logged",
        created_at=now,
    )
