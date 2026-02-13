"""Email query routes — GET /api/v1/emails, /{id}, /{id}/preview."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["emails"])

# TODO: GET /api/v1/emails — search/filter emails with pagination
# TODO: GET /api/v1/emails/{id} — get email detail
# TODO: GET /api/v1/emails/{id}/preview — render HTML preview (sandboxed)
# TODO: PATCH /api/v1/emails/{id}/status — update email status
