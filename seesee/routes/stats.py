"""Dashboard statistics route — GET /api/v1/stats."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["stats"])

# TODO: GET /api/v1/stats — dashboard statistics (counts by app, status, provider, time)
