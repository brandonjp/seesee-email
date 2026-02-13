"""App management routes — CRUD for app registration and key management."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from seesee.auth import (
    API_KEY_PREFIX,
    generate_api_key,
    generate_slug,
    generate_smtp_password,
    hash_secret,
)
from seesee.database import get_db
from seesee.dependencies import require_admin
from seesee.models import AppCreateRequest, AppCreateResponse, AppResponse

router = APIRouter(prefix="/api/v1", tags=["apps"])

VALID_BODY_STORAGE_MODES = {"full", "text_only", "preview"}


@router.post(
    "/apps",
    response_model=AppCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_app(request: AppCreateRequest) -> AppCreateResponse:
    """Register a new application. Returns API key and SMTP credentials (shown once)."""
    if request.body_storage_mode not in VALID_BODY_STORAGE_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body_storage_mode must be one of: {', '.join(sorted(VALID_BODY_STORAGE_MODES))}",
        )

    db = await get_db()

    # Generate slug with collision handling
    base_slug = generate_slug(request.name)
    slug = base_slug
    suffix = 2
    while True:
        cursor = await db.execute("SELECT 1 FROM apps WHERE slug = ?", (slug,))
        if await cursor.fetchone() is None:
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    # Generate credentials
    app_id = str(uuid.uuid4())
    api_key = generate_api_key()
    key_prefix = api_key[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8]
    api_key_hash = hash_secret(api_key)

    smtp_username = slug
    smtp_password = generate_smtp_password()
    smtp_password_hash = hash_secret(smtp_password)

    now = datetime.now(UTC)

    await db.execute(
        """INSERT INTO apps (id, name, slug, api_key, key_prefix, smtp_username, smtp_password,
                             body_storage_mode, retention_max_count, retention_max_age_days, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            app_id,
            request.name,
            slug,
            api_key_hash,
            key_prefix,
            smtp_username,
            smtp_password_hash,
            request.body_storage_mode,
            request.retention_max_count,
            request.retention_max_age_days,
            now.isoformat(),
        ),
    )
    await db.commit()

    return AppCreateResponse(
        id=app_id,
        name=request.name,
        slug=slug,
        body_storage_mode=request.body_storage_mode,
        retention_max_count=request.retention_max_count,
        retention_max_age_days=request.retention_max_age_days,
        created_at=now,
        last_activity_at=None,
        api_key=api_key,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
    )


@router.get(
    "/apps",
    response_model=list[AppResponse],
    dependencies=[Depends(require_admin)],
)
async def list_apps() -> list[AppResponse]:
    """List all registered applications. Requires admin auth."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, created_at, last_activity_at FROM apps ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        AppResponse(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            body_storage_mode=row["body_storage_mode"],
            retention_max_count=row["retention_max_count"],
            retention_max_age_days=row["retention_max_age_days"],
            created_at=row["created_at"],
            last_activity_at=row["last_activity_at"],
        )
        for row in rows
    ]
