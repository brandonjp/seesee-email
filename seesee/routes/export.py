"""Data export routes — GET /api/v1/export (GDPR right of access)."""

import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from seesee.database import get_db
from seesee.dependencies import require_admin
from seesee.models import ExportEmail, ExportResponse

router = APIRouter(prefix="/api/v1", tags=["export"])

_EXPORT_COLS = (
    "id, app_id, to_addresses, from_address, subject, body_preview, "
    "body_html, body_text, status, provider, ingest_method, logged_at, "
    "cc_addresses, bcc_addresses"
)

# CSV column headers and corresponding field names
_CSV_COLUMNS = [
    "id",
    "app_id",
    "to_addresses",
    "from_address",
    "subject",
    "body_preview",
    "body_html",
    "body_text",
    "status",
    "provider",
    "ingest_method",
    "logged_at",
    "cc_addresses",
    "bcc_addresses",
]


def _parse_json_or_none(value: str | None) -> list | None:
    """Parse a JSON string from SQLite, returning None if empty."""
    if value is None:
        return None
    return json.loads(value)


def _row_to_export_email(row: dict) -> ExportEmail:
    """Convert a database row to an ExportEmail."""
    return ExportEmail(
        id=row["id"],
        app_id=row["app_id"],
        to_addresses=json.loads(row["to_addresses"]),
        from_address=row["from_address"],
        subject=row["subject"],
        body_preview=row["body_preview"],
        body_html=row["body_html"],
        body_text=row["body_text"],
        status=row["status"],
        provider=row["provider"],
        ingest_method=row["ingest_method"],
        logged_at=row["logged_at"],
        cc_addresses=_parse_json_or_none(row["cc_addresses"]),
        bcc_addresses=_parse_json_or_none(row["bcc_addresses"]),
    )


def _wants_csv(request: Request, format_param: str | None) -> bool:
    """Determine if the client wants CSV output."""
    if format_param and format_param.lower() == "csv":
        return True
    accept = request.headers.get("accept", "")
    return "text/csv" in accept


def _build_csv(recipient: str, emails: list[ExportEmail]) -> str:
    """Build a CSV string from export emails."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_CSV_COLUMNS)
    for email in emails:
        writer.writerow(
            [
                email.id,
                email.app_id,
                json.dumps(email.to_addresses),
                email.from_address,
                email.subject,
                email.body_preview or "",
                email.body_html or "",
                email.body_text or "",
                email.status,
                email.provider or "",
                email.ingest_method,
                str(email.logged_at),
                json.dumps(email.cc_addresses) if email.cc_addresses else "",
                json.dumps(email.bcc_addresses) if email.bcc_addresses else "",
            ]
        )
    return output.getvalue()


@router.get(
    "/export",
    response_model=ExportResponse,
    dependencies=[Depends(require_admin)],
)
async def export_recipient_data(
    request: Request,
    recipient: str = Query(..., description="Recipient email address to export data for"),
    format: str | None = Query(None, description="Response format: json (default) or csv"),
) -> ExportResponse | StreamingResponse:
    """Export all emails associated with a recipient address (GDPR Article 15).

    Searches to_addresses, cc_addresses, and bcc_addresses fields for the
    given recipient email. Returns all matching emails with metadata and body
    content.

    Supports JSON (default) and CSV output via the `format` query parameter
    or the `Accept: text/csv` header.
    """
    db = await get_db()

    # Validate recipient is a non-empty email-like string
    recipient = recipient.strip().lower()
    if not recipient or "@" not in recipient:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid recipient email address is required",
        )

    # Search across to_addresses, cc_addresses, and bcc_addresses.
    # These are stored as JSON arrays in SQLite, so we use LIKE with the
    # email address quoted as it would appear inside a JSON array.
    # The lower() ensures case-insensitive matching.
    like_pattern = f'%"{recipient}"%'
    query_sql = (
        f"SELECT {_EXPORT_COLS} FROM emails "  # noqa: S608
        "WHERE lower(to_addresses) LIKE ? "
        "OR lower(cc_addresses) LIKE ? "
        "OR lower(bcc_addresses) LIKE ? "
        "ORDER BY logged_at ASC"
    )
    cursor = await db.execute(query_sql, [like_pattern, like_pattern, like_pattern])
    rows = await cursor.fetchall()

    emails = [_row_to_export_email(dict(row)) for row in rows]

    if _wants_csv(request, format):
        csv_content = _build_csv(recipient, emails)
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="export-{recipient}.csv"',
            },
        )

    return ExportResponse(
        recipient=recipient,
        total=len(emails),
        exported_at=datetime.now(UTC),
        emails=emails,
    )
