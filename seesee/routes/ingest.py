"""Email ingest routes — POST /api/v1/log and /api/v1/log/batch."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["ingest"])

# TODO: POST /api/v1/log — log a single email
# TODO: POST /api/v1/log/batch — log multiple emails (max 100)
