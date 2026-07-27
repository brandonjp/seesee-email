"""API key lifecycle — generation, resolution, revocation. Sync helpers are shared by the async (REST/MCP) and sync (SMTP) resolvers."""

import secrets
from dataclasses import dataclass

from seesee.auth import hash_secret, verify_secret  # noqa: F401  (verify used in later chunks)

APP_KEY_MARKER = "ss_"
MGMT_KEY_MARKER = "ss_mgmt_"
PREFIX_LEN = 8
KEY_RANDOM_BYTES = 32

APP_KEY_SCOPES = frozenset({"emails:read", "emails:write"})
MGMT_KEY_SCOPES = frozenset({"emails:read", "apps:read", "apps:write", "apps:delete"})
ALL_SCOPES = APP_KEY_SCOPES | MGMT_KEY_SCOPES


@dataclass(frozen=True)
class Principal:
    key_id: str
    app_id: str | None  # None = management key
    scopes: frozenset[str]
    label: str


class KeyRevokedError(Exception):
    """The presented key verified but has been revoked."""


class KeyExpiredError(Exception):
    """The presented key verified but is past its expiry."""


def generate_key(management: bool = False) -> str:
    marker = MGMT_KEY_MARKER if management else APP_KEY_MARKER
    return f"{marker}{secrets.token_urlsafe(KEY_RANDOM_BYTES)}"


def extract_prefix(token: str) -> list[str]:
    """Return candidate key_prefix slices for a presented token.

    ss_mgmt_ is a superstring of ss_, and a random segment can itself begin
    with "mgmt_" — so a token matching both markers yields BOTH candidate
    slices, and the caller must try each. The token's textual prefix NEVER
    determines key kind; the database row (app_id IS NULL) is authoritative.
    Returns [] for tokens too short to contain marker + prefix.
    """
    candidates = []
    if token.startswith(MGMT_KEY_MARKER) and len(token) >= len(MGMT_KEY_MARKER) + PREFIX_LEN:
        candidates.append(token[len(MGMT_KEY_MARKER) : len(MGMT_KEY_MARKER) + PREFIX_LEN])
    if token.startswith(APP_KEY_MARKER) and len(token) >= len(APP_KEY_MARKER) + PREFIX_LEN:
        candidates.append(token[len(APP_KEY_MARKER) : len(APP_KEY_MARKER) + PREFIX_LEN])
    return candidates


def key_is_active(row, now_iso: str) -> tuple[bool, str]:
    """Return (active, reason). reason is '' | 'revoked' | 'expired'."""
    if row["revoked_at"] is not None:
        return False, "revoked"
    if row["expires_at"] is not None and row["expires_at"] < now_iso:
        return False, "expired"
    return True, ""


def validate_scopes(scopes: list[str], app_id: str | None) -> None:
    """Enforce the kind/scope validity matrix. Raises ValueError on violation."""
    requested = set(scopes)
    if not requested:
        raise ValueError("At least one scope is required")
    allowed = APP_KEY_SCOPES if app_id is not None else MGMT_KEY_SCOPES
    invalid = requested - allowed
    if invalid:
        kind = "app" if app_id is not None else "management"
        raise ValueError(f"Invalid scope(s) for {kind} key: {', '.join(sorted(invalid))}")
