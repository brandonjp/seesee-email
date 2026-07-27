"""App management routes — CRUD for app registration and key management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from seesee import keys
from seesee.app_service import create_app_record
from seesee.auth import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_secret,
)
from seesee.database import get_db
from seesee.dependencies import require_scope
from seesee.helpers import VALID_BODY_STORAGE_MODES
from seesee.keys import Principal
from seesee.models import (
    AppCreateRequest,
    AppCreateResponse,
    AppResponse,
    AppUpdateRequest,
    KeyCreateRequest,
    KeyCreateResponse,
    KeyMetadata,
    KeyRotateResponse,
)
from seesee.timezone import iso_in_days, utc_now_iso

router = APIRouter(prefix="/api/v1", tags=["apps"])


@router.post(
    "/apps",
    response_model=AppCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_app(
    request: AppCreateRequest,
    principal: Principal = Depends(require_scope("apps:write")),  # noqa: B008
) -> AppCreateResponse:
    """Register a new application. Returns API key and SMTP credentials (shown once)."""
    try:
        record = await create_app_record(**request.model_dump(), created_by=principal.key_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return AppCreateResponse(**record)


@router.get(
    "/apps",
    response_model=list[AppResponse],
    dependencies=[Depends(require_scope("apps:read"))],
)
async def list_apps() -> list[AppResponse]:
    """List all registered applications. Requires admin auth."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, retention_degrade_to_text_days, "
        "retention_degrade_to_preview_days, created_at, last_activity_at "
        "FROM apps ORDER BY created_at DESC"
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
            retention_degrade_to_text_days=row["retention_degrade_to_text_days"],
            retention_degrade_to_preview_days=row["retention_degrade_to_preview_days"],
            created_at=row["created_at"],
            last_activity_at=row["last_activity_at"],
        )
        for row in rows
    ]


@router.get(
    "/apps/{app_id}",
    response_model=AppResponse,
    dependencies=[Depends(require_scope("apps:read"))],
)
async def get_app(app_id: str) -> AppResponse:
    """Fetch a single app record. Requires apps:read."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, retention_degrade_to_text_days, "
        "retention_degrade_to_preview_days, created_at, last_activity_at "
        "FROM apps WHERE id = ?",
        (app_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return AppResponse(**dict(row))


@router.patch(
    "/apps/{app_id}",
    response_model=AppResponse,
    dependencies=[Depends(require_scope("apps:write"))],
)
async def update_app(app_id: str, request: AppUpdateRequest) -> AppResponse:
    """Update an app's settings. Requires admin auth."""
    db = await get_db()

    # Verify app exists
    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, retention_degrade_to_text_days, "
        "retention_degrade_to_preview_days, created_at, last_activity_at "
        "FROM apps WHERE id = ?",
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
    if "retention_degrade_to_text_days" in request.model_fields_set:
        updates["retention_degrade_to_text_days"] = request.retention_degrade_to_text_days
    if "retention_degrade_to_preview_days" in request.model_fields_set:
        updates["retention_degrade_to_preview_days"] = request.retention_degrade_to_preview_days

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
        "retention_max_age_days, retention_degrade_to_text_days, "
        "retention_degrade_to_preview_days, created_at, last_activity_at "
        "FROM apps WHERE id = ?",
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
        retention_degrade_to_text_days=updated["retention_degrade_to_text_days"],
        retention_degrade_to_preview_days=updated["retention_degrade_to_preview_days"],
        created_at=updated["created_at"],
        last_activity_at=updated["last_activity_at"],
    )


@router.post(
    "/apps/{app_id}/rotate-key",
    response_model=KeyRotateResponse,
)
async def rotate_key(
    app_id: str,
    principal: Principal = Depends(require_scope("apps:write")),  # noqa: B008
) -> KeyRotateResponse:
    """Regenerate the API key for an app. Old key is immediately invalidated."""
    db = await get_db()

    cursor = await db.execute("SELECT id, api_key FROM apps WHERE id = ?", (app_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    old_hash = row["api_key"]

    new_key = generate_api_key()
    new_prefix = new_key[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8]
    new_hash = hash_secret(new_key)
    now_iso = utc_now_iso()

    await db.execute(
        "UPDATE apps SET api_key = ?, key_prefix = ?, smtp_password = ? WHERE id = ?",
        (new_hash, new_prefix, new_hash, app_id),
    )
    await db.execute(
        "UPDATE api_keys SET revoked_at = ? "
        "WHERE app_id = ? AND key_hash = ? AND revoked_at IS NULL",
        (now_iso, app_id, old_hash),
    )
    await db.execute(
        "INSERT INTO api_keys (id, key_hash, key_prefix, label, app_id, scopes, "
        "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            new_hash,
            new_prefix,
            "default",
            app_id,
            '["emails:read","emails:write"]',
            principal.key_id,
            now_iso,
        ),
    )
    await db.commit()

    return KeyRotateResponse(api_key=new_key)


@router.delete(
    "/apps/{app_id}/emails",
    dependencies=[Depends(require_scope("apps:delete"))],
)
async def purge_app_emails(app_id: str) -> dict:
    """Delete all emails for an app. Requires admin auth."""
    db = await get_db()

    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM emails WHERE app_id = ?", (app_id,))
    count = (await cursor.fetchone())["cnt"]

    await db.execute("DELETE FROM emails WHERE app_id = ?", (app_id,))
    await db.commit()

    return {"message": f"Deleted {count} emails"}


@router.delete(
    "/apps/{app_id}",
    dependencies=[Depends(require_scope("apps:delete"))],
)
async def delete_app(app_id: str) -> dict:
    """Delete an app and all its emails. Requires admin auth."""
    db = await get_db()

    cursor = await db.execute("SELECT id, name FROM apps WHERE id = ?", (app_id,))
    app = await cursor.fetchone()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM emails WHERE app_id = ?", (app_id,))
    email_count = (await cursor.fetchone())["cnt"]

    # Delete emails and api_keys first (FK constraint: no CASCADE), then the app
    await db.execute("DELETE FROM emails WHERE app_id = ?", (app_id,))
    await db.execute("DELETE FROM api_keys WHERE app_id = ?", (app_id,))
    await db.execute("DELETE FROM apps WHERE id = ?", (app_id,))
    await db.commit()

    return {"message": f"Deleted app '{app['name']}' and {email_count} emails"}


@router.get(
    "/apps/{app_id}/keys",
    response_model=list[KeyMetadata],
    dependencies=[Depends(require_scope("apps:read"))],
)
async def list_app_keys(app_id: str) -> list[KeyMetadata]:
    """List key metadata for an app. Requires apps:read."""
    db = await get_db()
    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return [KeyMetadata(**k) for k in await keys.list_keys(app_id)]


@router.post(
    "/apps/{app_id}/keys",
    response_model=KeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_app_key(
    app_id: str,
    request: KeyCreateRequest,
    principal: Principal = Depends(require_scope("apps:write")),  # noqa: B008
) -> KeyCreateResponse:
    """Mint an additional key for an app (safe rotation: mint, deploy, revoke old)."""
    db = await get_db()
    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    expires_at = None
    if request.expires_days is not None:
        expires_at = iso_in_days(request.expires_days)
    try:
        key_id, plaintext = await keys.create_key(
            label=request.label,
            app_id=app_id,
            scopes=request.scopes,
            expires_at=expires_at,
            created_by=principal.key_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    metadata = [k for k in await keys.list_keys(app_id) if k["id"] == key_id][0]
    return KeyCreateResponse(**metadata, api_key=plaintext)


@router.delete(
    "/apps/{app_id}/keys/{key_id}",
    dependencies=[Depends(require_scope("apps:write"))],
)
async def revoke_app_key(app_id: str, key_id: str) -> dict:
    """Revoke one of an app's keys.

    404 unless the key exists AND belongs to this app — revocation by bare
    key_id would let apps:write revoke management keys (lockout/DoS). There
    is deliberately no REST route that revokes a management key.
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT id FROM api_keys WHERE id = ? AND app_id = ?", (key_id, app_id)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await keys.revoke_key(key_id)
    return {"message": "Key revoked"}
