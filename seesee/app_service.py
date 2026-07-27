"""App provisioning service — shared by the REST route and MCP tools."""

import uuid

from seesee.auth import (
    API_KEY_PREFIX,
    generate_api_key,
    generate_slug,
    hash_secret,
)
from seesee.database import get_db
from seesee.helpers import VALID_BODY_STORAGE_MODES
from seesee.timezone import utc_now, utc_now_iso


async def create_app_record(
    *,
    name,
    body_storage_mode="full",
    retention_max_count=None,
    retention_max_age_days=None,
    retention_degrade_to_text_days=None,
    retention_degrade_to_preview_days=None,
    created_by="admin",
) -> dict:
    """Register a new application. Returns API key and SMTP credentials (shown once)."""
    if body_storage_mode not in VALID_BODY_STORAGE_MODES:
        raise ValueError(
            f"body_storage_mode must be one of: {', '.join(sorted(VALID_BODY_STORAGE_MODES))}"
        )

    db = await get_db()

    # Generate slug with collision handling
    base_slug = generate_slug(name)
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

    now = utc_now()
    now_iso = utc_now_iso()

    await db.execute(
        """INSERT INTO apps (id, name, slug, api_key, key_prefix, smtp_username, smtp_password,
                             body_storage_mode, retention_max_count, retention_max_age_days,
                             retention_degrade_to_text_days, retention_degrade_to_preview_days,
                             created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            app_id,
            name,
            slug,
            api_key_hash,
            key_prefix,
            smtp_username,
            api_key_hash,
            body_storage_mode,
            retention_max_count,
            retention_max_age_days,
            retention_degrade_to_text_days,
            retention_degrade_to_preview_days,
            now_iso,
        ),
    )

    await db.execute(
        "INSERT INTO api_keys (id, key_hash, key_prefix, label, app_id, scopes, "
        "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            api_key_hash,
            key_prefix,
            "default",
            app_id,
            '["emails:read","emails:write"]',
            created_by,
            now_iso,
        ),
    )

    await db.commit()

    return {
        "id": app_id,
        "name": name,
        "slug": slug,
        "body_storage_mode": body_storage_mode,
        "retention_max_count": retention_max_count,
        "retention_max_age_days": retention_max_age_days,
        "retention_degrade_to_text_days": retention_degrade_to_text_days,
        "retention_degrade_to_preview_days": retention_degrade_to_preview_days,
        "created_at": now,
        "last_activity_at": None,
        "api_key": api_key,
        "smtp_username": smtp_username,
    }
