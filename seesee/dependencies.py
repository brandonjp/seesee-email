"""FastAPI dependency functions for authentication and database access."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from seesee.auth import API_KEY_PREFIX, SESSION_COOKIE_NAME, validate_session_token, verify_secret
from seesee.config import settings
from seesee.database import get_db

# ---------------------------------------------------------------------------
# Bearer token scheme for API key auth
# ---------------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_app(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict:
    """Validate API key and return the authenticated app row.

    Extracts the Bearer token, looks up by key_prefix for O(1) lookup,
    then verifies the full key against the bcrypt hash.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    if not token.startswith(API_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
        )

    prefix = token[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8]

    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM apps WHERE key_prefix = ?",
        (prefix,),
    )
    rows = await cursor.fetchall()

    for row in rows:
        if verify_secret(token, row["api_key"]):
            return dict(row)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


# ---------------------------------------------------------------------------
# HTTP Basic auth for admin endpoints
# ---------------------------------------------------------------------------
basic_scheme = HTTPBasic()


async def require_admin(
    credentials: Annotated[HTTPBasicCredentials, Depends(basic_scheme)],
) -> str:
    """Validate admin credentials via HTTP Basic Auth.

    Uses constant-time comparison to prevent timing attacks.
    """
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin password not configured",
        )

    username_correct = secrets.compare_digest(
        credentials.username.lower().encode("utf-8"),
        settings.admin_username.lower().encode("utf-8"),
    )
    password_correct = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )

    if not (username_correct and password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


# ---------------------------------------------------------------------------
# Session cookie auth for web UI routes
# ---------------------------------------------------------------------------


def _get_secret_key() -> str:
    """Get the secret key, falling back to admin_password if not configured."""
    return settings.secret_key or settings.admin_password


async def require_session(request: Request) -> str:
    """Validate session cookie and return username, or redirect to login.

    Raises a special HTTPException with 303 redirect for unauthenticated users.
    """
    secret_key = _get_secret_key()
    if not secret_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not configured")

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )

    max_age = settings.session_max_age_days * 86400
    username = validate_session_token(token, secret_key, max_age)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )

    return username


def _validate_session_cookie(request: Request) -> str | None:
    """Validate the session cookie and return the username, or None if absent/invalid."""
    secret_key = _get_secret_key()
    if not secret_key:
        return None

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    max_age = settings.session_max_age_days * 86400
    return validate_session_token(token, secret_key, max_age)


# ---------------------------------------------------------------------------
# Combined auth for routes that accept either admin credential
# ---------------------------------------------------------------------------
basic_scheme_optional = HTTPBasic(auto_error=False)


async def require_admin_or_session(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_scheme_optional)],
) -> str:
    """Validate admin auth via session cookie first, then HTTP Basic.

    Used for routes (like the email preview iframe) that must accept the
    web UI's session cookie in addition to Basic auth, without triggering
    the browser's native Basic auth prompt for cookie-bearing requests.
    """
    username = _validate_session_cookie(request)
    if username is not None:
        return username

    if credentials is not None and settings.admin_password:
        username_correct = secrets.compare_digest(
            credentials.username.lower().encode("utf-8"),
            settings.admin_username.lower().encode("utf-8"),
        )
        password_correct = secrets.compare_digest(
            credentials.password.encode("utf-8"),
            settings.admin_password.encode("utf-8"),
        )
        if username_correct and password_correct:
            return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


async def require_admin_or_app(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    basic_credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_scheme_optional)],
) -> dict:
    """Validate admin auth (session or Basic) first, then fall back to an app Bearer key.

    Returns a principal dict: {"admin": True, "username": ...} for admin
    callers, or {"admin": False, "app": <app row>} for an authenticated app.
    """
    username = _validate_session_cookie(request)
    if username is not None:
        return {"admin": True, "username": username}

    if basic_credentials is not None and settings.admin_password:
        username_correct = secrets.compare_digest(
            basic_credentials.username.lower().encode("utf-8"),
            settings.admin_username.lower().encode("utf-8"),
        )
        password_correct = secrets.compare_digest(
            basic_credentials.password.encode("utf-8"),
            settings.admin_password.encode("utf-8"),
        )
        if username_correct and password_correct:
            return {"admin": True, "username": basic_credentials.username}

    if credentials is not None:
        app = await get_current_app(credentials)
        return {"admin": False, "app": app}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
