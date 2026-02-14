"""Web UI routes — server-rendered HTML pages via Jinja2."""

import contextlib
import json
import math
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.responses import Response

from seesee.auth import (
    API_KEY_PREFIX,
    SESSION_COOKIE_NAME,
    create_session_token,
    generate_api_key,
    generate_slug,
    generate_smtp_password,
    hash_secret,
)
from seesee.config import settings
from seesee.database import get_db
from seesee.dependencies import require_session
from seesee.retention import run_cleanup

router = APIRouter(tags=["ui"])

FLASH_COOKIE_NAME = "seesee_flash"
_FLASH_MAX_AGE = 60  # seconds — only needs to survive one redirect

_templates: Jinja2Templates | None = None


def _get_templates() -> Jinja2Templates:
    """Get templates instance, importing from main to avoid circular imports."""
    global _templates
    if _templates is None:
        from seesee.main import templates

        _templates = templates
    return _templates


def _get_secret_key() -> str:
    """Get the secret key, falling back to admin_password if not configured."""
    return settings.secret_key or settings.admin_password


def _set_flash(response: Response, data: dict) -> None:
    """Store flash data in a signed, short-lived cookie."""
    serializer = URLSafeTimedSerializer(_get_secret_key(), salt="seesee-flash")
    response.set_cookie(
        FLASH_COOKIE_NAME,
        serializer.dumps(data),
        max_age=_FLASH_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def _pop_flash(request: Request) -> dict | None:
    """Read and return flash data from the cookie, or None."""
    cookie = request.cookies.get(FLASH_COOKIE_NAME)
    if not cookie:
        return None
    serializer = URLSafeTimedSerializer(_get_secret_key(), salt="seesee-flash")
    with contextlib.suppress(BadSignature, SignatureExpired):
        return serializer.loads(cookie, max_age=_FLASH_MAX_AGE)
    return None


# ---------------------------------------------------------------------------
# Auth routes (no session required)
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None) -> HTMLResponse:
    """Render the login page."""
    tmpl = _get_templates()
    return tmpl.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    """Validate credentials and set session cookie."""
    secret_key = _get_secret_key()
    if not secret_key or not settings.admin_password:
        tmpl = _get_templates()
        return tmpl.TemplateResponse(
            "login.html",
            {"request": request, "error": "Admin password not configured"},
            status_code=403,
        )

    username_ok = secrets.compare_digest(
        username.encode("utf-8"),
        settings.admin_username.encode("utf-8"),
    )
    password_ok = secrets.compare_digest(
        password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )

    if not (username_ok and password_ok):
        tmpl = _get_templates()
        return tmpl.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )

    token = create_session_token(username, secret_key)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.session_max_age_days * 86400,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: str = Depends(require_session)) -> HTMLResponse:
    """Dashboard page with email stats."""
    db = await get_db()
    tmpl = _get_templates()

    # Total emails
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM emails")
    total_emails = (await cursor.fetchone())["cnt"]

    # Time-window counts
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM emails WHERE logged_at >= datetime('now', '-1 day')"
    )
    emails_24h = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM emails WHERE logged_at >= datetime('now', '-7 days')"
    )
    emails_7d = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM emails WHERE logged_at >= datetime('now', '-30 days')"
    )
    emails_30d = (await cursor.fetchone())["cnt"]

    # Total apps
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM apps")
    total_apps = (await cursor.fetchone())["cnt"]

    # Status breakdown
    cursor = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM emails GROUP BY status ORDER BY cnt DESC"
    )
    by_status = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

    # Per-app counts
    cursor = await db.execute(
        "SELECT a.id, a.name, COUNT(e.id) as count "
        "FROM apps a LEFT JOIN emails e ON e.app_id = a.id "
        "GROUP BY a.id ORDER BY count DESC"
    )
    by_app = [
        {"id": row["id"], "name": row["name"], "count": row["count"]}
        for row in await cursor.fetchall()
    ]

    # Daily volume for last 30 days (for sparkline)
    cursor = await db.execute(
        "SELECT DATE(logged_at) as day, COUNT(*) as cnt "
        "FROM emails WHERE logged_at >= datetime('now', '-30 days') "
        "GROUP BY DATE(logged_at) ORDER BY day"
    )
    daily_volume = [{"day": row["day"], "count": row["cnt"]} for row in await cursor.fetchall()]

    return tmpl.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "current_page": "dashboard",
            "total_emails": total_emails,
            "emails_24h": emails_24h,
            "emails_7d": emails_7d,
            "emails_30d": emails_30d,
            "total_apps": total_apps,
            "by_status": by_status,
            "by_app": by_app,
            "daily_volume": daily_volume,
            "base_url": settings.base_url,
        },
    )


# ---------------------------------------------------------------------------
# Email list
# ---------------------------------------------------------------------------

_SUMMARY_COLS = (
    "e.id, e.app_id, e.to_addresses, e.from_address, e.subject, e.body_preview, "
    "e.status, e.provider, e.ingest_method, e.logged_at, e.created_at"
)
_ALLOWED_SORT = {"logged_at", "created_at", "subject"}


@router.get("/emails", response_class=HTMLResponse)
async def email_list(
    request: Request,
    user: str = Depends(require_session),
    q: str | None = Query(None),
    app_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    provider: str | None = Query(None),
    sort: str = Query("logged_at"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> HTMLResponse:
    """Email list with search, filters, and pagination."""
    db = await get_db()
    tmpl = _get_templates()

    if sort not in _ALLOWED_SORT:
        sort = "logged_at"
    sort_order = "ASC" if order.lower() == "asc" else "DESC"

    conditions: list[str] = []
    params: list[str | int] = []

    if q:
        conditions.append("e.rowid IN (SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?)")
        params.append(q)
    if app_id:
        conditions.append("e.app_id = ?")
        params.append(app_id)
    if status_filter:
        conditions.append("e.status = ?")
        params.append(status_filter)
    if provider:
        conditions.append("e.provider = ?")
        params.append(provider)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Count
    cursor = await db.execute(
        f"SELECT COUNT(*) as cnt FROM emails e {where_clause}",  # noqa: S608
        params,
    )
    total = (await cursor.fetchone())["cnt"]

    # Fetch page
    offset = (page - 1) * per_page
    cursor = await db.execute(
        f"SELECT {_SUMMARY_COLS} FROM emails e {where_clause} "  # noqa: S608
        f"ORDER BY e.{sort} {sort_order} LIMIT ? OFFSET ?",
        [*params, per_page, offset],
    )
    rows = await cursor.fetchall()
    emails_list = []
    for row in rows:
        r = dict(row)
        r["to_addresses"] = json.loads(r["to_addresses"]) if r["to_addresses"] else []
        emails_list.append(r)

    pages = max(1, math.ceil(total / per_page))

    # Get apps for filter dropdown
    cursor = await db.execute("SELECT id, name FROM apps ORDER BY name")
    apps = [dict(row) for row in await cursor.fetchall()]

    # Get distinct statuses for filter
    cursor = await db.execute("SELECT DISTINCT status FROM emails ORDER BY status")
    statuses = [row["status"] for row in await cursor.fetchall()]

    # Get distinct providers for filter
    cursor = await db.execute(
        "SELECT DISTINCT provider FROM emails WHERE provider IS NOT NULL ORDER BY provider"
    )
    providers = [row["provider"] for row in await cursor.fetchall()]

    return tmpl.TemplateResponse(
        "emails.html",
        {
            "request": request,
            "user": user,
            "current_page": "emails",
            "emails": emails_list,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "q": q or "",
            "app_id": app_id or "",
            "status_filter": status_filter or "",
            "provider_filter": provider or "",
            "sort": sort,
            "order": order,
            "apps": apps,
            "statuses": statuses,
            "providers": providers,
        },
    )


# ---------------------------------------------------------------------------
# Email detail
# ---------------------------------------------------------------------------


@router.get("/emails/{email_id}", response_class=HTMLResponse)
async def email_detail(
    request: Request,
    email_id: str,
    user: str = Depends(require_session),
) -> HTMLResponse:
    """Email detail with tabbed content (preview, HTML source, text, metadata)."""
    db = await get_db()
    tmpl = _get_templates()

    cursor = await db.execute(
        "SELECT e.*, a.name as app_name FROM emails e "
        "LEFT JOIN apps a ON a.id = e.app_id WHERE e.id = ?",
        (email_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return tmpl.TemplateResponse(
            "email_detail.html",
            {"request": request, "user": user, "current_page": "emails", "email": None},
            status_code=404,
        )

    email = dict(row)
    email["to_addresses"] = json.loads(email["to_addresses"]) if email["to_addresses"] else []
    email["cc_addresses"] = json.loads(email["cc_addresses"]) if email.get("cc_addresses") else None
    email["bcc_addresses"] = (
        json.loads(email["bcc_addresses"]) if email.get("bcc_addresses") else None
    )
    email["tags"] = json.loads(email["tags"]) if email.get("tags") else None
    email["metadata"] = json.loads(email["metadata"]) if email.get("metadata") else None

    return tmpl.TemplateResponse(
        "email_detail.html",
        {
            "request": request,
            "user": user,
            "current_page": "emails",
            "email": email,
        },
    )


# ---------------------------------------------------------------------------
# App management
# ---------------------------------------------------------------------------


@router.get("/apps", response_class=HTMLResponse)
async def app_list(
    request: Request,
    user: str = Depends(require_session),
) -> HTMLResponse:
    """App management page — list apps, add new, manage credentials."""
    db = await get_db()
    tmpl = _get_templates()

    cursor = await db.execute(
        "SELECT a.id, a.name, a.slug, a.body_storage_mode, a.retention_max_count, "
        "a.retention_max_age_days, a.created_at, a.last_activity_at, "
        "COUNT(e.id) as email_count "
        "FROM apps a LEFT JOIN emails e ON e.app_id = a.id "
        "GROUP BY a.id ORDER BY a.created_at DESC"
    )
    apps = [dict(row) for row in await cursor.fetchall()]

    # Read one-time flash data from signed cookie
    flash = _pop_flash(request)
    created_credentials = flash.get("created_credentials") if flash else None
    rotated_key = flash.get("rotated_key") if flash else None

    response = tmpl.TemplateResponse(
        "apps.html",
        {
            "request": request,
            "user": user,
            "current_page": "apps",
            "apps": apps,
            "created_credentials": created_credentials,
            "rotated_key": rotated_key,
        },
    )
    if flash:
        response.delete_cookie(FLASH_COOKIE_NAME)
    return response


@router.post("/apps", response_class=HTMLResponse)
async def create_app_ui(
    request: Request,
    user: str = Depends(require_session),
    name: str = Form(...),
    body_storage_mode: str = Form("full"),
) -> RedirectResponse:
    """Create a new app via the web UI form."""
    db = await get_db()

    valid_modes = {"full", "text_only", "preview"}
    if body_storage_mode not in valid_modes:
        body_storage_mode = "full"

    # Generate slug with collision handling
    base_slug = generate_slug(name)
    slug = base_slug
    suffix = 2
    while True:
        cursor = await db.execute("SELECT 1 FROM apps WHERE slug = ?", (slug,))
        if await cursor.fetchone() is None:
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    app_id = str(uuid.uuid4())
    api_key = generate_api_key()
    key_prefix = api_key[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8]
    api_key_hash = hash_secret(api_key)

    smtp_username = slug
    smtp_password = generate_smtp_password()
    smtp_password_hash = hash_secret(smtp_password)

    now = datetime.now(UTC)

    await db.execute(
        """INSERT INTO apps (id, name, slug, api_key, key_prefix, smtp_username, smtp_password,
                             body_storage_mode, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            app_id,
            name,
            slug,
            api_key_hash,
            key_prefix,
            smtp_username,
            smtp_password_hash,
            body_storage_mode,
            now.isoformat(),
        ),
    )
    await db.commit()

    # Flash credentials via signed cookie (consumed on next page load)
    response = RedirectResponse(url="/apps", status_code=303)
    _set_flash(response, {
        "created_credentials": {
            "api_key": api_key,
            "smtp_username": smtp_username,
            "smtp_password": smtp_password,
        }
    })
    return response


@router.post("/apps/{app_id}/rotate-key")
async def rotate_key_ui(
    app_id: str,
    user: str = Depends(require_session),
) -> RedirectResponse:
    """Rotate an app's API key via the web UI."""
    db = await get_db()

    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        return RedirectResponse(url="/apps", status_code=303)

    new_key = generate_api_key()
    new_prefix = new_key[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8]
    new_hash = hash_secret(new_key)

    await db.execute(
        "UPDATE apps SET api_key = ?, key_prefix = ? WHERE id = ?",
        (new_hash, new_prefix, app_id),
    )
    await db.commit()

    response = RedirectResponse(url="/apps", status_code=303)
    _set_flash(response, {"rotated_key": new_key})
    return response


# ---------------------------------------------------------------------------
# App detail
# ---------------------------------------------------------------------------


@router.get("/apps/{app_id}", response_class=HTMLResponse)
async def app_detail(
    request: Request,
    app_id: str,
    user: str = Depends(require_session),
) -> HTMLResponse:
    """App detail page — stats, integration snippets, management."""
    db = await get_db()
    tmpl = _get_templates()

    cursor = await db.execute(
        "SELECT id, name, slug, body_storage_mode, retention_max_count, "
        "retention_max_age_days, created_at, last_activity_at FROM apps WHERE id = ?",
        (app_id,),
    )
    app = await cursor.fetchone()
    if app is None:
        return tmpl.TemplateResponse(
            "app_detail.html",
            {"request": request, "user": user, "current_page": "apps", "app": None},
            status_code=404,
        )
    app = dict(app)

    # Email stats
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM emails WHERE app_id = ?", (app_id,))
    app["email_count"] = (await cursor.fetchone())["cnt"]

    # Emails by status
    cursor = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM emails WHERE app_id = ? GROUP BY status ORDER BY cnt DESC",
        (app_id,),
    )
    app["by_status"] = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

    # Last activity
    cursor = await db.execute(
        "SELECT logged_at FROM emails WHERE app_id = ? ORDER BY logged_at DESC LIMIT 1",
        (app_id,),
    )
    row = await cursor.fetchone()
    app["last_email_at"] = row["logged_at"] if row else None

    # Read one-time flash data from signed cookie
    flash = _pop_flash(request)
    rotated_key = flash.get("rotated_key") if flash else None

    response = tmpl.TemplateResponse(
        "app_detail.html",
        {
            "request": request,
            "user": user,
            "current_page": "apps",
            "app": app,
            "base_url": settings.base_url,
            "smtp_port": settings.smtp_port,
            "rotated_key": rotated_key,
        },
    )
    if flash:
        response.delete_cookie(FLASH_COOKIE_NAME)
    return response


@router.post("/apps/{app_id}/purge")
async def purge_app_emails_ui(
    app_id: str,
    user: str = Depends(require_session),
) -> RedirectResponse:
    """Purge all emails for an app via the web UI."""
    db = await get_db()

    cursor = await db.execute("SELECT id FROM apps WHERE id = ?", (app_id,))
    if await cursor.fetchone() is None:
        return RedirectResponse(url="/apps", status_code=303)

    await db.execute("DELETE FROM emails WHERE app_id = ?", (app_id,))
    await db.commit()

    return RedirectResponse(url=f"/apps/{app_id}?purged=1", status_code=303)


@router.post("/emails/{email_id}/delete")
async def delete_email_ui(
    email_id: str,
    user: str = Depends(require_session),
) -> RedirectResponse:
    """Delete a single email via the web UI."""
    db = await get_db()

    cursor = await db.execute("SELECT id FROM emails WHERE id = ?", (email_id,))
    if await cursor.fetchone() is None:
        return RedirectResponse(url="/emails", status_code=303)

    await db.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    await db.commit()

    return RedirectResponse(url="/emails?deleted=1", status_code=303)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: str = Depends(require_session),
) -> HTMLResponse:
    """Settings page — display retention config, storage usage."""
    db = await get_db()
    tmpl = _get_templates()

    # Storage stats
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM emails")
    email_count = (await cursor.fetchone())["cnt"]

    cursor = await db.execute("SELECT COALESCE(SUM(body_size_bytes), 0) as total FROM emails")
    storage_bytes = (await cursor.fetchone())["total"]

    # Database file size
    cursor = await db.execute(
        "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
    )
    row = await cursor.fetchone()
    db_size_bytes = row["size"] if row else 0

    return tmpl.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "current_page": "settings",
            "settings": settings,
            "email_count": email_count,
            "storage_bytes": storage_bytes,
            "db_size_bytes": db_size_bytes,
        },
    )


@router.post("/settings/cleanup")
async def run_cleanup_ui(
    user: str = Depends(require_session),
) -> RedirectResponse:
    """Trigger an immediate retention cleanup via the web UI."""
    await run_cleanup()
    return RedirectResponse(url="/settings?cleanup=1", status_code=303)
