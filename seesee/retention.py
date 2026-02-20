"""Retention management — scheduled cleanup and body degradation.

Evaluates per-app and global retention rules:
- max_count: Keep at most N emails per app
- max_age_days: Delete emails older than N days
- max_storage_mb: Global storage cap (oldest-first deletion)
- degrade_to_text_days: Strip HTML body after N days (keep text + preview)
- degrade_to_preview_days: Strip text body after N days (keep preview only)

The most restrictive rule wins when multiple apply.
Deletion is oldest-first within each app.
Degradation is opt-in (0 = never degrade).
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from seesee.config import settings
from seesee.database import get_db
from seesee.helpers import strip_html_tags

logger = logging.getLogger("seesee.retention")

# Batch size for deletions to avoid long-running locks
DELETE_BATCH_SIZE = 500
# Smaller batch for degradation since each row requires read + update
DEGRADE_BATCH_SIZE = 100

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


def _effective_degrade_days(app_value: int | None, global_value: int) -> int:
    """Return effective degradation threshold in days.

    0 means disabled. Per-app overrides can enable degradation independently.
    When both are set (> 0), the smaller (sooner) value wins.
    """
    app_set = app_value is not None and app_value > 0
    global_set = global_value > 0

    if app_set and global_set:
        return min(app_value, global_value)
    if app_set:
        return app_value
    return global_value


async def degrade_to_text(app_id: str, cutoff: str) -> int:
    """Degrade emails from full to text_only for an app.

    Strips HTML, preserves text body and preview. Targets emails older than
    cutoff that still have body_html set.

    Returns the number of emails degraded.
    """
    db = await get_db()
    degraded = 0

    while True:
        cursor = await db.execute(
            """SELECT id, body_html, body_text, body_preview FROM emails
            WHERE app_id = ? AND body_html IS NOT NULL AND logged_at < ?
            LIMIT ?""",
            (app_id, cutoff, DEGRADE_BATCH_SIZE),
        )
        rows = await cursor.fetchall()
        if not rows:
            break

        for row in rows:
            body_text = row["body_text"]
            body_preview = row["body_preview"]

            # Generate text from HTML if not already present
            if not body_text:
                body_text = strip_html_tags(row["body_html"])

            # Generate preview if not already present
            if not body_preview:
                body_preview = (body_text or "")[:500] or None

            # Recalculate size (only text content remains)
            new_size = len(body_text.encode("utf-8")) if body_text else 0

            await db.execute(
                """UPDATE emails SET body_html = NULL, body_text = ?,
                body_preview = ?, body_size_bytes = ? WHERE id = ?""",
                (body_text, body_preview, new_size, row["id"]),
            )

        await db.commit()
        degraded += len(rows)

    return degraded


async def degrade_to_preview(app_id: str, cutoff: str) -> int:
    """Degrade emails to preview-only for an app.

    Strips both HTML and text body, preserving only the preview. Targets
    emails older than cutoff that still have body_text or body_html.

    Returns the number of emails degraded.
    """
    db = await get_db()
    degraded = 0

    while True:
        cursor = await db.execute(
            """SELECT id, body_html, body_text, body_preview FROM emails
            WHERE app_id = ? AND (body_text IS NOT NULL OR body_html IS NOT NULL)
            AND logged_at < ?
            LIMIT ?""",
            (app_id, cutoff, DEGRADE_BATCH_SIZE),
        )
        rows = await cursor.fetchall()
        if not rows:
            break

        for row in rows:
            body_preview = row["body_preview"]

            # Generate preview if not already present
            if not body_preview:
                text_source = row["body_text"]
                if not text_source and row["body_html"]:
                    text_source = strip_html_tags(row["body_html"])
                body_preview = (text_source or "")[:500] or None

            # Recalculate size (only preview remains)
            new_size = len(body_preview.encode("utf-8")) if body_preview else 0

            await db.execute(
                """UPDATE emails SET body_html = NULL, body_text = NULL,
                body_preview = ?, body_size_bytes = ? WHERE id = ?""",
                (body_preview, new_size, row["id"]),
            )

        await db.commit()
        degraded += len(rows)

    return degraded


async def run_cleanup() -> None:
    """Execute one full retention cleanup cycle across all apps and global rules."""
    db = await get_db()
    total_deleted = 0
    total_bytes_freed = 0
    total_degraded = 0

    # Fetch all apps with their per-app overrides
    cursor = await db.execute(
        "SELECT id, name, retention_max_count, retention_max_age_days, "
        "retention_degrade_to_text_days, retention_degrade_to_preview_days FROM apps"
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

        # Body degradation: full → text_only
        effective_text_days = _effective_degrade_days(
            app["retention_degrade_to_text_days"],
            settings.retention_degrade_to_text_days,
        )
        if effective_text_days > 0:
            cutoff = (datetime.now(UTC) - timedelta(days=effective_text_days)).isoformat()
            text_degraded = await degrade_to_text(app_id, cutoff)
            if text_degraded > 0:
                logger.info(
                    "Retention: degraded %d emails to text_only for app %r (after %d days)",
                    text_degraded,
                    app_name,
                    effective_text_days,
                )
                total_degraded += text_degraded

        # Body degradation: text_only → preview
        effective_preview_days = _effective_degrade_days(
            app["retention_degrade_to_preview_days"],
            settings.retention_degrade_to_preview_days,
        )
        if effective_preview_days > 0:
            cutoff = (datetime.now(UTC) - timedelta(days=effective_preview_days)).isoformat()
            preview_degraded = await degrade_to_preview(app_id, cutoff)
            if preview_degraded > 0:
                logger.info(
                    "Retention: degraded %d emails to preview for app %r (after %d days)",
                    preview_degraded,
                    app_name,
                    effective_preview_days,
                )
                total_degraded += preview_degraded

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

    if total_deleted > 0 or total_degraded > 0:
        logger.info(
            "Retention cleanup complete: %d deleted, %d degraded, ~%.1f MB freed",
            total_deleted,
            total_degraded,
            total_bytes_freed / (1024 * 1024),
        )
    else:
        logger.info("Retention cleanup complete: nothing to delete or degrade")


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
