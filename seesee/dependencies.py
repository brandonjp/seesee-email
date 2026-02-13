"""FastAPI dependency functions for authentication and database access."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from seesee.auth import API_KEY_PREFIX, verify_secret
from seesee.config import settings
from seesee.database import get_db

# ---------------------------------------------------------------------------
# Bearer token scheme for API key auth
# ---------------------------------------------------------------------------
bearer_scheme = HTTPBearer()


async def get_current_app(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> dict:
    """Validate API key and return the authenticated app row.

    Extracts the Bearer token, looks up by key_prefix for O(1) lookup,
    then verifies the full key against the bcrypt hash.
    """
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
        credentials.username.encode("utf-8"),
        settings.admin_username.encode("utf-8"),
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
