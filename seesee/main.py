"""FastAPI application entry point for SeeSee."""

import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from seesee import __version__
from seesee.database import close_db, get_db, init_db
from seesee.routes import apps, emails, ingest, stats, ui


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    await init_db()
    # TODO: Start SMTP server if enabled
    # TODO: Start retention scheduler
    yield
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

# Register route modules
app.include_router(ingest.router)
app.include_router(apps.router)
app.include_router(emails.router)
app.include_router(stats.router)
app.include_router(ui.router)


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
