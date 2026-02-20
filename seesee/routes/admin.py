"""Admin management routes — cleanup, diagnostics."""

import os
import pathlib
import socket
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from seesee.config import settings
from seesee.database import _get_mount_info, get_db, get_startup_time
from seesee.dependencies import require_admin
from seesee.models import CleanupResponse, PersistenceDiagnostics
from seesee.retention import run_cleanup

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post(
    "/cleanup",
    response_model=CleanupResponse,
    dependencies=[Depends(require_admin)],
)
async def trigger_cleanup() -> CleanupResponse:
    """Trigger an immediate retention cleanup cycle. Requires admin auth."""
    await run_cleanup()
    return CleanupResponse(message="Cleanup completed")


@router.get(
    "/debug/persistence",
    response_model=PersistenceDiagnostics,
    dependencies=[Depends(require_admin)],
)
async def debug_persistence() -> PersistenceDiagnostics:
    """Return persistence diagnostics for debugging volume issues. Requires admin auth."""
    db = await get_db()
    db_path = pathlib.Path(settings.db_path)

    # File stats
    db_size = 0
    db_modified = None
    if db_path.exists():
        stat = db_path.stat()
        db_size = stat.st_size
        db_modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()

    # Counts
    cursor = await db.execute("SELECT COUNT(*) FROM apps")
    app_count = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM emails")
    email_count = (await cursor.fetchone())[0]

    # Schema version
    cursor = await db.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
    row = await cursor.fetchone()
    schema_version = row[0] if row else None

    # Oldest app
    cursor = await db.execute("SELECT MIN(created_at) FROM apps")
    row = await cursor.fetchone()
    oldest_app = row[0] if row and row[0] else None

    # Uptime
    startup = get_startup_time()
    uptime = time.monotonic() - startup if startup > 0 else 0.0

    # Mount detection
    data_dir = str(db_path.parent)
    mount_info = _get_mount_info(data_dir)
    volume_mounted = os.path.ismount(data_dir)

    return PersistenceDiagnostics(
        db_path=str(db_path.resolve()),
        db_size_bytes=db_size,
        db_modified_at=db_modified,
        app_count=app_count,
        email_count=email_count,
        schema_version=schema_version,
        oldest_app_created_at=oldest_app,
        uptime_seconds=round(uptime, 2),
        hostname=socket.gethostname(),
        volume_mounted=volume_mounted,
        mount_info=mount_info,
    )
