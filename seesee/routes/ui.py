"""Web UI routes — server-rendered HTML pages via Jinja2."""

from fastapi import APIRouter

router = APIRouter(tags=["ui"])

# TODO: GET / — dashboard
# TODO: GET /login — login page
# TODO: POST /login — handle login
# TODO: GET /emails — email list with search/filter
# TODO: GET /emails/{id} — email detail
# TODO: GET /apps — app management
# TODO: GET /apps/{id} — app detail
# TODO: GET /settings — global settings
