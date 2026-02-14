"""Admin management routes — cleanup, diagnostics."""

from fastapi import APIRouter, Depends

from seesee.dependencies import require_admin
from seesee.models import CleanupResponse
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
