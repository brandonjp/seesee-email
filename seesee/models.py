"""Pydantic models for SeeSee API request and response validation."""

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Ingest models
# ---------------------------------------------------------------------------


class EmailLogRequest(BaseModel):
    """Request body for POST /api/v1/log."""

    to: list[str] = Field(..., min_length=1, description="Recipient addresses")
    from_address: str = Field(..., alias="from", description="Sender address")
    subject: str = Field(..., min_length=1, description="Email subject")
    body_html: str | None = None
    body_text: str | None = None
    status: str = "sent"
    provider: str | None = None
    provider_message_id: str | None = None
    error_message: str | None = None
    metadata: dict | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    reply_to: str | None = None
    tags: list[str] | None = None
    logged_at: datetime | None = None

    model_config = {"populate_by_name": True}


class EmailLogResponse(BaseModel):
    """Response body for POST /api/v1/log."""

    id: str
    status: str = "logged"
    created_at: datetime


class BatchLogResponse(BaseModel):
    """Response body for POST /api/v1/log/batch."""

    logged: int
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Email query models
# ---------------------------------------------------------------------------


class EmailSummary(BaseModel):
    """Email summary for list views."""

    id: str
    app_id: str
    to_addresses: list[str]
    from_address: str
    subject: str
    body_preview: str | None = None
    status: str
    provider: str | None = None
    ingest_method: str
    logged_at: datetime
    created_at: datetime


class EmailDetail(EmailSummary):
    """Full email detail including body content."""

    body_html: str | None = None
    body_text: str | None = None
    body_size_bytes: int = 0
    provider_message_id: str | None = None
    error_message: str | None = None
    metadata: dict | None = None
    cc_addresses: list[str] | None = None
    bcc_addresses: list[str] | None = None
    reply_to: str | None = None
    tags: list[str] | None = None


class EmailListResponse(BaseModel):
    """Paginated email list response."""

    emails: list[EmailSummary]
    total: int
    page: int
    per_page: int
    pages: int


# ---------------------------------------------------------------------------
# App models
# ---------------------------------------------------------------------------


class AppCreateRequest(BaseModel):
    """Request body for POST /api/v1/apps."""

    name: str = Field(..., min_length=1, description="Human-readable app name")
    body_storage_mode: str = "full"
    retention_max_count: int | None = None
    retention_max_age_days: int | None = None


class AppResponse(BaseModel):
    """App detail response."""

    id: str
    name: str
    slug: str
    body_storage_mode: str
    retention_max_count: int | None = None
    retention_max_age_days: int | None = None
    created_at: datetime
    last_activity_at: datetime | None = None


class AppCreateResponse(AppResponse):
    """App creation response (includes plaintext credentials, shown once)."""

    api_key: str
    smtp_username: str
    smtp_password: str


# ---------------------------------------------------------------------------
# Stats models
# ---------------------------------------------------------------------------


class DashboardStats(BaseModel):
    """Response body for GET /api/v1/stats."""

    total_emails: int
    emails_24h: int
    emails_7d: int
    emails_30d: int
    total_apps: int
    by_status: dict[str, int] = {}
    by_app: list[dict] = []
