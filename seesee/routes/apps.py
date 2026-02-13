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
from seesee.models import (
    AppCreateRequest,
    AppCreateResponse,
    AppResponse,
    AppUpdateRequest,
    KeyRotateResponse,
)

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


@router.patch(
    "/apps/{app_id}",
    response_model=AppResponse,
    dependencies=[Depends(require_admin)],
)
async def update_app(app_id: str, request: AppUpdateRequest) -> AppResponse:
    """Update an app's settings. Requires admin auth."""
    db = await get_db()

    # Verify app exists
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, created_at, last_activity_at FROM apps WHERE id = ?",
        (app_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    # Build SET clause from provided (non-None) fields
    updates: dict[str, str | int | None] = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.body_storage_mode is not None:
        if request.body_storage_mode not in VALID_BODY_STORAGE_MODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"body_storage_mode must be one of: "
                    f"{', '.join(sorted(VALID_BODY_STORAGE_MODES))}"
                ),
            )
        updates["body_storage_mode"] = request.body_storage_mode
    # Allow explicit null to clear retention overrides
    if "retention_max_count" in request.model_fields_set:
        updates["retention_max_count"] = request.retention_max_count
    if "retention_max_age_days" in request.model_fields_set:
        updates["retention_max_age_days"] = request.retention_max_age_days

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(app_id)
    await db.execute(f"UPDATE apps SET {set_clause} WHERE id = ?", values)  # noqa: S608
    await db.commit()

    # Return updated row
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, created_at, last_activity_at FROM apps WHERE id = ?",
        (app_id,),
    )
    updated = await cursor.fetchone()
    return AppResponse(
        id=updated["id"],
        name=updated["name"],
        slug=updated["slug"],
        body_storage_mode=updated["body_storage_mode"],
        retention_max_count=updated["retention_max_count"],
        retention_max_age_days=updated["retention_max_age_days"],
        created_at=updated["created_at"],
        last_activity_at=updated["last_activity_at"],
    )


@router.post(
    "/apps/{app_id}/rotate-key",
    response_model=KeyRotateResponse,
    dependencies=[Depends(require_admin)],
)
async def rotate_key(app_id: str) -> KeyRotateResponse:
    """Regenerate the API key for an app. Old key is immediately invalidated."""
    db = await get_db()

    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    new_key = generate_api_key()
    new_prefix = new_key[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8]
    new_hash = hash_secret(new_key)

    await db.execute(
        "UPDATE apps SET api_key = ?, key_prefix = ? WHERE id = ?",
        (new_hash, new_prefix, app_id),
    )
    await db.commit()

    return KeyRotateResponse(api_key=new_key)
