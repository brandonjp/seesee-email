"""FastAPI application entry point for SeeSee."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from seesee import __version__
from seesee.config import settings
from seesee.database import init_db, close_db


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

# Static files and templates
app.mount("/static", StaticFiles(directory="seesee/static"), name="static")
templates = Jinja2Templates(directory="seesee/templates")

# Register route modules
# TODO: Uncomment as routes are implemented
# from seesee.routes import ingest, emails, apps, stats, ui
# app.include_router(ingest.router)
# app.include_router(emails.router)
# app.include_router(apps.router)
# app.include_router(stats.router)
# app.include_router(ui.router)


@app.get("/api/v1/health")
async def health_check() -> dict:
    """Health check endpoint for monitoring and container orchestration."""
    return {
        "status": "ok",
        "version": __version__,
    }
