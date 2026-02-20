"""Dashboard statistics route — GET /api/v1/stats."""

from fastapi import APIRouter, Depends

from seesee.database import get_db
from seesee.dependencies import require_admin
from seesee.models import DashboardStats
from seesee.timezone import utc_cutoff_iso

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get(
    "/stats",
    response_model=DashboardStats,
    dependencies=[Depends(require_admin)],
)
async def get_stats() -> DashboardStats:
    """Return dashboard statistics — email counts by time window, status, and app."""
    db = await get_db()

    # Total emails
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM emails")
    total_emails = (await cursor.fetchone())["cnt"]

    # Emails in time windows (use Python-computed UTC cutoffs for format consistency)
    cutoff_1d = utc_cutoff_iso(1)
    cutoff_7d = utc_cutoff_iso(7)
    cutoff_30d = utc_cutoff_iso(30)

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM emails WHERE logged_at >= ?", (cutoff_1d,)
    )
    emails_24h = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM emails WHERE logged_at >= ?", (cutoff_7d,)
    )
    emails_7d = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM emails WHERE logged_at >= ?", (cutoff_30d,)
    )
    emails_30d = (await cursor.fetchone())["cnt"]

    # Total apps
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM apps")
    total_apps = (await cursor.fetchone())["cnt"]

    # Breakdown by status
    cursor = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM emails GROUP BY status ORDER BY cnt DESC"
    )
    by_status = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

    # Breakdown by app (include app name)
    cursor = await db.execute(
        "SELECT a.id, a.name, COUNT(e.id) as count "
        "FROM apps a LEFT JOIN emails e ON e.app_id = a.id "
        "GROUP BY a.id ORDER BY count DESC"
    )
    by_app = [
        {"id": row["id"], "name": row["name"], "count": row["count"]}
        for row in await cursor.fetchall()
    ]

    return DashboardStats(
        total_emails=total_emails,
        emails_24h=emails_24h,
        emails_7d=emails_7d,
        emails_30d=emails_30d,
        total_apps=total_apps,
        by_status=by_status,
        by_app=by_app,
    )
