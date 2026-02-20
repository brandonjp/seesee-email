"""Email query routes — GET /api/v1/emails, /{id}, /{id}/preview, PATCH /{id}/status, DELETE."""

import json
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from seesee.database import get_db
from seesee.dependencies import require_admin
from seesee.models import EmailDetail, EmailListResponse, EmailSummary, StatusUpdateRequest

router = APIRouter(prefix="/api/v1", tags=["emails"])

# Columns shared across list and detail queries
_SUMMARY_COLS = (
    "id, app_id, to_addresses, from_address, subject, body_preview, "
    "status, provider, ingest_method, logged_at, created_at"
)
_DETAIL_COLS = (
    f"{_SUMMARY_COLS}, body_html, body_text, body_size_bytes, body_degraded_at, "
    "provider_message_id, error_message, metadata, cc_addresses, "
    "bcc_addresses, reply_to, tags"
)

# Columns that are safe to ORDER BY
_ALLOWED_SORT_FIELDS = {"logged_at", "created_at", "subject"}


def _parse_json_or_none(value: str | None) -> list | dict | None:
    """Parse a JSON string from SQLite, returning None if empty."""
    if value is None:
        return None
    return json.loads(value)


def _row_to_summary(row: dict) -> EmailSummary:
    """Convert a database row to an EmailSummary."""
    return EmailSummary(
        id=row["id"],
        app_id=row["app_id"],
        to_addresses=json.loads(row["to_addresses"]),
        from_address=row["from_address"],
        subject=row["subject"],
        body_preview=row["body_preview"],
        status=row["status"],
        provider=row["provider"],
        ingest_method=row["ingest_method"],
        logged_at=row["logged_at"],
        created_at=row["created_at"],
    )


def _row_to_detail(row: dict) -> EmailDetail:
    """Convert a database row to an EmailDetail."""
    return EmailDetail(
        id=row["id"],
        app_id=row["app_id"],
        to_addresses=json.loads(row["to_addresses"]),
        from_address=row["from_address"],
        subject=row["subject"],
        body_preview=row["body_preview"],
        status=row["status"],
        provider=row["provider"],
        ingest_method=row["ingest_method"],
        logged_at=row["logged_at"],
        created_at=row["created_at"],
        body_html=row["body_html"],
        body_text=row["body_text"],
        body_size_bytes=row["body_size_bytes"] or 0,
        body_degraded_at=row["body_degraded_at"],
        provider_message_id=row["provider_message_id"],
        error_message=row["error_message"],
        metadata=_parse_json_or_none(row["metadata"]),
        cc_addresses=_parse_json_or_none(row["cc_addresses"]),
        bcc_addresses=_parse_json_or_none(row["bcc_addresses"]),
        reply_to=row["reply_to"],
        tags=_parse_json_or_none(row["tags"]),
    )


@router.get(
    "/emails",
    response_model=EmailListResponse,
    dependencies=[Depends(require_admin)],
)
async def list_emails(
    q: str | None = Query(None, description="Full-text search query"),
    app_id: str | None = Query(None, description="Filter by app ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    provider: str | None = Query(None, description="Filter by provider"),
    date_from: str | None = Query(None, description="Filter emails logged on or after (ISO date)"),
    date_to: str | None = Query(None, description="Filter emails logged on or before (ISO date)"),
    sort: str = Query("logged_at", description="Sort field: logged_at, created_at, subject"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
) -> EmailListResponse:
    """List and search emails with pagination. Requires admin auth."""
    db = await get_db()

    # Validate sort field
    if sort not in _ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort must be one of: {', '.join(sorted(_ALLOWED_SORT_FIELDS))}",
        )
    sort_order = "ASC" if order.lower() == "asc" else "DESC"

    # Build WHERE conditions
    conditions: list[str] = []
    params: list[str | int] = []

    if q:
        conditions.append("e.rowid IN (SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?)")
        params.append(q)
    if app_id:
        conditions.append("e.app_id = ?")
        params.append(app_id)
    if status_filter:
        conditions.append("e.status = ?")
        params.append(status_filter)
    if provider:
        conditions.append("e.provider = ?")
        params.append(provider)
    if date_from:
        conditions.append("e.logged_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("e.logged_at <= ?")
        params.append(date_to)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Count total matching rows
    count_sql = f"SELECT COUNT(*) as cnt FROM emails e {where_clause}"  # noqa: S608
    cursor = await db.execute(count_sql, params)
    total = (await cursor.fetchone())["cnt"]

    # Fetch page
    offset = (page - 1) * per_page
    query_sql = (
        f"SELECT {_SUMMARY_COLS} FROM emails e {where_clause} "  # noqa: S608
        f"ORDER BY e.{sort} {sort_order} LIMIT ? OFFSET ?"
    )
    cursor = await db.execute(query_sql, [*params, per_page, offset])
    rows = await cursor.fetchall()

    pages = max(1, math.ceil(total / per_page))

    return EmailListResponse(
        emails=[_row_to_summary(dict(row)) for row in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get(
    "/emails/{email_id}",
    response_model=EmailDetail,
    dependencies=[Depends(require_admin)],
)
async def get_email(email_id: str) -> EmailDetail:
    """Get full email detail by ID. Requires admin auth."""
    db = await get_db()
    cursor = await db.execute(
        f"SELECT {_DETAIL_COLS} FROM emails WHERE id = ?",  # noqa: S608
        (email_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    return _row_to_detail(dict(row))


@router.get(
    "/emails/{email_id}/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
async def preview_email(email_id: str) -> HTMLResponse:
    """Return sandboxed HTML preview of an email's body.

    Serves a minimal HTML document with restrictive Content-Security-Policy
    headers. Designed to be loaded inside an iframe with sandbox attributes.
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT body_html, body_text, body_preview FROM emails WHERE id = ?",
        (email_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    # Prefer body_html, fall back to body_text, then body_preview
    body = row["body_html"] or row["body_text"] or row["body_preview"] or ""

    # If we fell back to plain text, wrap in <pre> for readability
    if not row["body_html"] and body:
        # Escape HTML entities in plain text to prevent injection
        body = (
            body.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        body = f'<pre style="white-space:pre-wrap;font-family:sans-serif;">{body}</pre>'

    html = (
        "<!DOCTYPE html>\n"
        '<html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<style>body{margin:0;padding:16px;font-family:sans-serif;}</style>"
        "</head><body>\n"
        f"{body}\n"
        "</body></html>"
    )

    return HTMLResponse(
        content=html,
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data: https:;"
            ),
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@router.patch(
    "/emails/{email_id}/status",
    response_model=EmailDetail,
    dependencies=[Depends(require_admin)],
)
async def update_email_status(email_id: str, request: StatusUpdateRequest) -> EmailDetail:
    """Update an email's status. Requires admin auth.

    Use case: provider webhooks update delivery status after initial logging.
    """
    db = await get_db()

    cursor = await db.execute("SELECT id FROM emails WHERE id = ?", (email_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    await db.execute(
        "UPDATE emails SET status = ? WHERE id = ?",
        (request.status, email_id),
    )
    await db.commit()

    cursor = await db.execute(
        f"SELECT {_DETAIL_COLS} FROM emails WHERE id = ?",  # noqa: S608
        (email_id,),
    )
    row = await cursor.fetchone()
    return _row_to_detail(dict(row))


@router.delete(
    "/emails/{email_id}",
    dependencies=[Depends(require_admin)],
)
async def delete_email(email_id: str) -> dict:
    """Delete a single email. Requires admin auth."""
    db = await get_db()

    cursor = await db.execute("SELECT id FROM emails WHERE id = ?", (email_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    await db.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    await db.commit()

    return {"message": "Email deleted"}
