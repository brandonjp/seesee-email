"""App management routes — CRUD for app registration and key management."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["apps"])

# TODO: GET /api/v1/apps — list apps
# TODO: POST /api/v1/apps — register app (returns API key + SMTP credentials)
# TODO: PATCH /api/v1/apps/{id} — update app settings
# TODO: POST /api/v1/apps/{id}/rotate-key — regenerate API key
