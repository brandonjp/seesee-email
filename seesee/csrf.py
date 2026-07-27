"""Signed CSRF tokens for session-authenticated UI form POSTs.

Tokens are signed with the session secret and bound to the session username.
Bearer-authenticated REST and MCP routes never use ambient credentials and
therefore never require CSRF tokens.
"""

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from seesee.config import settings
from seesee.dependencies import _get_secret_key, _validate_session_cookie

CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
_CSRF_SALT = "seesee-csrf"


def make_csrf_token(username: str, secret_key: str) -> str:
    """Create a signed CSRF token bound to the given session username."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_CSRF_SALT)
    return serializer.dumps({"u": username})


def validate_csrf_token(token: str, username: str, secret_key: str, max_age_seconds: int) -> bool:
    """Return True if the token is validly signed and bound to this username."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_CSRF_SALT)
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("u") == username


def csrf_token_for(request: Request) -> str:
    """Template helper: return a CSRF token for the current session, or ''.

    Registered as a Jinja global so templates can embed tokens without every
    GET handler passing one through its context.
    """
    username = _validate_session_cookie(request)
    if username is None:
        return ""
    return make_csrf_token(username, _get_secret_key())


async def require_csrf(request: Request) -> None:
    """FastAPI dependency: reject session POSTs lacking a valid CSRF token.

    Reads the token from the X-CSRF-Token header (fetch() callers) or the
    csrf_token form field (regular form posts). Starlette caches form parsing,
    so reading the form here does not conflict with Form(...) parameters.
    """
    username = _validate_session_cookie(request)
    if username is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    token = request.headers.get(CSRF_HEADER_NAME)
    if not token:
        form = await request.form()
        value = form.get(CSRF_FIELD_NAME, "")
        token = value if isinstance(value, str) else ""
    max_age = settings.session_max_age_days * 86400
    if not token or not validate_csrf_token(token, username, _get_secret_key(), max_age):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid"
        )
