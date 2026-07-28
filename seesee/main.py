"""FastAPI application entry point for SeeSee."""

import logging
import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from seesee import __version__
from seesee.config import settings
from seesee.database import close_db, get_db, init_db
from seesee.mcp_server import build_mcp_asgi_app, create_mcp_server
from seesee.retention import start_retention_scheduler, stop_retention_scheduler
from seesee.routes import admin, apps, emails, export, ingest, stats, ui, webhooks
from seesee.smtp_server import start_smtp_server, stop_smtp_server

logger = logging.getLogger("seesee")


def _warn_if_base_url_looks_wrong() -> None:
    """Warn when base_url is http:// on what looks like a real deployment.

    The Secure-cookie flag falls back to the live request scheme, so this is a
    diagnostic rather than the mechanism — but if the proxy's forwarded headers
    are ever distrusted, an http:// base_url is the difference between secure
    and insecure cookies, and nothing else would say so. base_url is also what
    builds the URLs in the integration ENV block, which are wrong either way.
    """
    if not settings.base_url.lower().startswith("http://"):
        return
    host = settings.base_url.split("://", 1)[-1].split("/")[0].split(":")[0].lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".local"):
        return
    logger.warning(
        "SEESEE_BASE_URL is %r — an http:// URL on a non-local host. If this "
        "deployment is reachable over HTTPS, set it to the https:// URL: it is "
        "used to build the integration ENV vars, and it is the fallback that "
        "marks session and flash cookies Secure when the reverse proxy's "
        "X-Forwarded-Proto is not trusted (see SEESEE_FORWARDED_ALLOW_IPS). "
        "The flash cookie briefly carries a plaintext API key.",
        settings.base_url,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    _warn_if_base_url_looks_wrong()
    await init_db()
    if settings.smtp_enabled:
        await start_smtp_server()
    await start_retention_scheduler()
    async with mcp_server.session_manager.run():
        yield
    await stop_retention_scheduler()
    if settings.smtp_enabled:
        await stop_smtp_server()
    await close_db()


app = FastAPI(
    title="SeeSee",
    description="Lightweight, self-hosted sent email log aggregator.",
    version=__version__,
    docs_url="/docs",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return consistent error format or redirect for session auth."""
    # Handle session auth redirects (303 from require_session)
    if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(url=exc.headers["Location"], status_code=303)

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


# Static files and templates — use package-relative paths so it works
# regardless of the working directory (e.g. pytest runs from project root).
_pkg_dir = pathlib.Path(__file__).parent
_static_dir = _pkg_dir / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
_templates_dir = _pkg_dir / "templates"
if _templates_dir.is_dir():
    templates = Jinja2Templates(directory=str(_templates_dir))

    # Register timezone display filter for server-rendered timestamp fallbacks.
    # Templates use: {{ timestamp | display_dt }} — shows time in SEESEE_DISPLAY_TIMEZONE.
    # JS enhances these to relative times with local-timezone tooltips.
    from seesee.timezone import format_for_display

    templates.env.filters["display_dt"] = format_for_display

    # Expose version + build metadata to all templates (sidebar brand + footer).
    templates.env.globals["app_version"] = __version__
    templates.env.globals["build_display"] = (
        format_for_display(settings.build_time, "%Y-%m-%d %H:%M:%S %Z")
        if settings.build_time
        else "local dev"
    )

    from seesee.csrf import csrf_token_for

    templates.env.globals["csrf_token_for"] = csrf_token_for

# Register route modules
app.include_router(ingest.router)
app.include_router(apps.router)
app.include_router(emails.router)
app.include_router(export.router)
app.include_router(stats.router)
app.include_router(admin.router)
app.include_router(webhooks.router)
app.include_router(ui.router)

mcp_server = create_mcp_server()
app.mount("/mcp", build_mcp_asgi_app(mcp_server))


class _MCPPathRewrite:
    """Serve POST /mcp without a trailing-slash 307 (mounted app lives at /mcp/)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
        await self.app(scope, receive, send)


app.add_middleware(_MCPPathRewrite)


@app.get("/api/v1/health")
async def health_check() -> dict:
    """Health check endpoint for monitoring and container orchestration."""
    db_status = "ok"
    try:
        db = await get_db()
        cursor = await db.execute("SELECT 1")
        await cursor.fetchone()
    except Exception:
        db_status = "error"

    overall = "ok" if db_status == "ok" else "degraded"

    return {
        "status": overall,
        "version": __version__,
        "database": db_status,
    }
