"""Retention management — scheduled cleanup of old emails.

Evaluates per-app and global retention rules:
- max_count: Keep at most N emails per app
- max_age_days: Delete emails older than N days
- max_storage_mb: Global storage cap (oldest-first deletion)

The most restrictive rule wins when multiple apply.
Deletion is oldest-first within each app.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from seesee.config import settings
from seesee.database import get_db

logger = logging.getLogger("seesee.retention")

# Batch size for deletions to avoid long-running locks
DELETE_BATCH_SIZE = 500

_scheduler_task: asyncio.Task | None = None


async def enforce_max_count(app_id: str, effective_limit: int) -> int:
    """Delete oldest emails for an app if it exceeds the effective max count.

    Returns the number of emails deleted.
    """
    db = await get_db()
    deleted = 0

    while True:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM emails WHERE app_id = ?",
            (app_id,),
        )
        row = await cursor.fetchone()
        total = row[0]

        excess = total - effective_limit
        if excess <= 0:
            break

        batch = min(excess, DELETE_BATCH_SIZE)
        await db.execute(
            """DELETE FROM emails WHERE id IN (
                SELECT id FROM emails
                WHERE app_id = ?
                ORDER BY logged_at ASC
                LIMIT ?
            )""",
            (app_id, batch),
        )
        await db.commit()
        deleted += batch

    return deleted


async def enforce_max_age(app_id: str, effective_days: int) -> int:
    """Delete emails older than the effective age limit for an app.

    Returns the number of emails deleted.
    """
    db = await get_db()
    cutoff = (datetime.now(UTC) - timedelta(days=effective_days)).isoformat()
    deleted = 0

    while True:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM emails
            WHERE app_id = ? AND logged_at < ?""",
            (app_id, cutoff),
        )
        row = await cursor.fetchone()
        remaining = row[0]

        if remaining <= 0:
            break

        batch = min(remaining, DELETE_BATCH_SIZE)
        await db.execute(
            """DELETE FROM emails WHERE id IN (
                SELECT id FROM emails
                WHERE app_id = ? AND logged_at < ?
                ORDER BY logged_at ASC
                LIMIT ?
            )""",
            (app_id, cutoff, batch),
        )
        await db.commit()
        deleted += batch

    return deleted


async def enforce_global_storage_cap() -> tuple[int, int]:
    """Delete oldest emails globally until total storage is under the cap.

    Returns (emails_deleted, bytes_freed).
    """
    db = await get_db()
    cap_bytes = settings.retention_max_storage_mb * 1024 * 1024
    deleted = 0
    bytes_freed = 0

    while True:
        cursor = await db.execute("SELECT COALESCE(SUM(body_size_bytes), 0) FROM emails")
        row = await cursor.fetchone()
        total_bytes = row[0]

        if total_bytes <= cap_bytes:
            break

        # Fetch a batch of oldest emails to delete
        cursor = await db.execute(
            """SELECT id, body_size_bytes FROM emails
            ORDER BY logged_at ASC
            LIMIT ?""",
            (DELETE_BATCH_SIZE,),
        )
        rows = await cursor.fetchall()
        if not rows:
            break

        ids = [r["id"] for r in rows]
        batch_bytes = sum(r["body_size_bytes"] or 0 for r in rows)

        placeholders = ",".join("?" for _ in ids)
        await db.execute(
            f"DELETE FROM emails WHERE id IN ({placeholders})",  # noqa: S608
            ids,
        )
        await db.commit()
        deleted += len(ids)
        bytes_freed += batch_bytes

    return deleted, bytes_freed


def _effective_limit(app_value: int | None, global_value: int) -> int:
    """Return the most restrictive (smallest) of app-level and global limits.

    If the app override is set (non-None, > 0), use min(app, global).
    Otherwise use the global value.
    """
    if app_value is not None and app_value > 0:
        return min(app_value, global_value)
    return global_value


async def run_cleanup() -> None:
    """Execute one full retention cleanup cycle across all apps and global rules."""
    db = await get_db()
    total_deleted = 0
    total_bytes_freed = 0

    # Fetch all apps with their per-app overrides
    cursor = await db.execute(
        "SELECT id, name, retention_max_count, retention_max_age_days FROM apps"
    )
    apps = await cursor.fetchall()

    for app in apps:
        app_id = app["id"]
        app_name = app["name"]

        # Max count enforcement
        effective_count = _effective_limit(app["retention_max_count"], settings.retention_max_count)
        count_deleted = await enforce_max_count(app_id, effective_count)
        if count_deleted > 0:
            logger.info(
                "Retention: deleted %d emails from app %r (max_count=%d)",
                count_deleted,
                app_name,
                effective_count,
            )
            total_deleted += count_deleted

        # Max age enforcement
        effective_age = _effective_limit(
            app["retention_max_age_days"], settings.retention_max_age_days
        )
        age_deleted = await enforce_max_age(app_id, effective_age)
        if age_deleted > 0:
            logger.info(
                "Retention: deleted %d emails from app %r (max_age=%d days)",
                age_deleted,
                app_name,
                effective_age,
            )
            total_deleted += age_deleted

    # Global storage cap
    storage_deleted, storage_bytes_freed = await enforce_global_storage_cap()
    if storage_deleted > 0:
        logger.info(
            "Retention: deleted %d emails to enforce storage cap (~%.1f MB freed)",
            storage_deleted,
            storage_bytes_freed / (1024 * 1024),
        )
        total_deleted += storage_deleted
        total_bytes_freed += storage_bytes_freed

    if total_deleted > 0:
        logger.info(
            "Retention cleanup complete: %d emails deleted, ~%.1f MB freed",
            total_deleted,
            total_bytes_freed / (1024 * 1024),
        )
    else:
        logger.info("Retention cleanup complete: nothing to delete")


async def _scheduler_loop() -> None:
    """Background loop that runs cleanup on the configured interval."""
    interval_seconds = settings.retention_cleanup_interval_minutes * 60
    logger.info(
        "Retention scheduler started (interval=%d minutes)",
        settings.retention_cleanup_interval_minutes,
    )

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await run_cleanup()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Retention cleanup failed")


async def start_retention_scheduler() -> None:
    """Start the background retention scheduler task."""
    global _scheduler_task
    if _scheduler_task is not None:
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())


async def stop_retention_scheduler() -> None:
    """Cancel the background retention scheduler task."""
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _scheduler_task
        _scheduler_task = None
        logger.info("Retention scheduler stopped")
