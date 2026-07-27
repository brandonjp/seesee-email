"""API key lifecycle — generation, resolution, revocation. Sync helpers are shared by the async (REST/MCP) and sync (SMTP) resolvers."""

import json
import secrets
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass

from seesee.auth import hash_secret, verify_secret
from seesee.config import settings
from seesee.database import get_db
from seesee.timezone import utc_now_iso

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


_LAST_USED_DEBOUNCE_SECONDS = 60

_KEY_METADATA_COLUMNS = (
    "id, label, key_prefix, app_id, scopes, created_by, created_at, "
    "last_used_at, expires_at, revoked_at"
)


def _principal_from_row(row) -> Principal:
    return Principal(
        key_id=row["id"],
        app_id=row["app_id"],
        scopes=frozenset(json.loads(row["scopes"])),
        label=row["label"],
    )


def _debounce_cutoff(now_iso: str) -> str:
    from datetime import datetime, timedelta

    now = datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%S")
    return (now - timedelta(seconds=_LAST_USED_DEBOUNCE_SECONDS)).strftime("%Y-%m-%dT%H:%M:%S")


async def _record_use(key_id: str, now_iso: str) -> None:
    """Guarded single-statement debounce: at most one write per key per 60s."""
    db = await get_db()
    await db.execute(
        "UPDATE api_keys SET last_used_at = ? "
        "WHERE id = ? AND (last_used_at IS NULL OR last_used_at < ?)",
        (now_iso, key_id, _debounce_cutoff(now_iso)),
    )
    await db.commit()


async def resolve_key(token: str) -> Principal | None:
    """Resolve a Bearer token to a Principal.

    Returns None when no key matches. Raises KeyRevokedError / KeyExpiredError
    when the token verifies against a dead key, so callers can produce
    distinct 401 details.
    """
    now = utc_now_iso()
    db = await get_db()
    for prefix in extract_prefix(token):
        cursor = await db.execute("SELECT * FROM api_keys WHERE key_prefix = ?", (prefix,))
        rows = await cursor.fetchall()
        for row in rows:
            if verify_secret(token, row["key_hash"]):
                active, reason = key_is_active(row, now)
                if reason == "revoked":
                    raise KeyRevokedError
                if reason == "expired":
                    raise KeyExpiredError
                await _record_use(row["id"], now)
                return _principal_from_row(row)
    return await _resolve_legacy_fallback(token, now)


async def _resolve_legacy_fallback(token: str, now_iso: str) -> Principal | None:
    """0.20.0 transition only (delete in 0.21.0 with the legacy columns).

    Self-heals apps created by a 0.19.x container after the v4 backfill ran
    (deploy overlap): verify against apps.api_key and lazily insert the
    missing api_keys row — the request carries the plaintext, so the prefix
    is computed correctly even for legacy NULL-prefix rows.
    """
    if not token.startswith(APP_KEY_MARKER):
        return None
    prefix = token[len(APP_KEY_MARKER) : len(APP_KEY_MARKER) + PREFIX_LEN]
    if len(prefix) < PREFIX_LEN:
        return None
    db = await get_db()
    cursor = await db.execute("SELECT * FROM apps WHERE key_prefix = ?", (prefix,))
    rows = await cursor.fetchall()
    for app_row in rows:
        if verify_secret(token, app_row["api_key"]):
            cursor = await db.execute(
                "SELECT 1 FROM api_keys WHERE app_id = ? AND key_hash = ?",
                (app_row["id"], app_row["api_key"]),
            )
            if await cursor.fetchone() is None:
                key_id = str(uuid.uuid4())
                await db.execute(
                    "INSERT INTO api_keys (id, key_hash, key_prefix, label, app_id, "
                    "scopes, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        key_id,
                        app_row["api_key"],
                        prefix,
                        "default",
                        app_row["id"],
                        '["emails:read","emails:write"]',
                        "migration",
                        now_iso,
                    ),
                )
                await db.commit()
            cursor = await db.execute(
                "SELECT * FROM api_keys WHERE app_id = ? AND key_hash = ?",
                (app_row["id"], app_row["api_key"]),
            )
            row = await cursor.fetchone()
            await _record_use(row["id"], now_iso)
            return _principal_from_row(row)
    return None


async def create_key(
    *,
    label: str,
    app_id: str | None,
    scopes: list[str],
    expires_at: str | None,
    created_by: str,
) -> tuple[str, str]:
    """Mint a key. Returns (key_id, plaintext). Raises ValueError on an
    invalid kind/scope combination (the validity matrix is enforced HERE so
    every mint path — REST, UI, CLI, MCP — shares one validation)."""
    validate_scopes(scopes, app_id)
    plaintext = generate_key(management=app_id is None)
    marker = MGMT_KEY_MARKER if app_id is None else APP_KEY_MARKER
    prefix = plaintext[len(marker) : len(marker) + PREFIX_LEN]
    key_id = str(uuid.uuid4())
    db = await get_db()
    await db.execute(
        "INSERT INTO api_keys (id, key_hash, key_prefix, label, app_id, scopes, "
        "created_by, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            key_id,
            hash_secret(plaintext),
            prefix,
            label,
            app_id,
            json.dumps(sorted(set(scopes))),
            created_by,
            expires_at,
            utc_now_iso(),
        ),
    )
    await db.commit()
    return key_id, plaintext


async def revoke_key(key_id: str) -> bool:
    """Revoke a key. If it is the app's PRIMARY key (its hash mirrors
    apps.api_key), also tombstone the legacy columns with a hash of a value
    nobody holds — so a rollback to 0.19.x cannot resurrect a revoked
    credential. Returns False if the key does not exist or is already revoked."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
    row = await cursor.fetchone()
    if row is None or row["revoked_at"] is not None:
        return False
    now = utc_now_iso()
    await db.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (now, key_id))
    if row["app_id"] is not None:
        cursor = await db.execute("SELECT api_key FROM apps WHERE id = ?", (row["app_id"],))
        app_row = await cursor.fetchone()
        if app_row is not None and app_row["api_key"] == row["key_hash"]:
            tombstone = hash_secret(secrets.token_urlsafe(KEY_RANDOM_BYTES))
            await db.execute(
                "UPDATE apps SET api_key = ?, smtp_password = ? WHERE id = ?",
                (tombstone, tombstone, row["app_id"]),
            )
    await db.commit()
    return True


async def list_keys(app_id: str | None) -> list[dict]:
    """Key metadata for an app (or all management keys when app_id is None).
    Never returns hashes or plaintexts."""
    db = await get_db()
    if app_id is None:
        cursor = await db.execute(
            f"SELECT {_KEY_METADATA_COLUMNS} FROM api_keys "  # noqa: S608
            "WHERE app_id IS NULL ORDER BY created_at DESC"
        )
    else:
        cursor = await db.execute(
            f"SELECT {_KEY_METADATA_COLUMNS} FROM api_keys "  # noqa: S608
            "WHERE app_id = ? ORDER BY created_at DESC",
            (app_id,),
        )
    rows = await cursor.fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["scopes"] = json.loads(item["scopes"])
        result.append(item)
    return result


def resolve_smtp_password(smtp_username: str, password: str) -> dict | None:
    """SYNC resolver for the SMTP authenticator (aiosmtpd cannot await).

    Returns the app row dict on success, None on failure. A password matching
    ANY active emails:write key for the app authenticates — this is what makes
    non-destructive rotation work over SMTP. Shares the pure helpers with the
    async resolver so the two cannot drift.
    """
    import json as _json

    now = utc_now_iso()
    with closing(sqlite3.connect(settings.db_path, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        app_row = db.execute(
            "SELECT * FROM apps WHERE smtp_username = ?", (smtp_username,)
        ).fetchone()
        if app_row is None:
            return None
        rows = db.execute("SELECT * FROM api_keys WHERE app_id = ?", (app_row["id"],)).fetchall()
        for row in rows:
            active, _reason = key_is_active(row, now)
            if not active:
                continue
            if "emails:write" not in _json.loads(row["scopes"]):
                continue
            if verify_secret(password, row["key_hash"]):
                db.execute(
                    "UPDATE api_keys SET last_used_at = ? "
                    "WHERE id = ? AND (last_used_at IS NULL OR last_used_at < ?)",
                    (now, row["id"], _debounce_cutoff(now)),
                )
                db.commit()
                return dict(app_row)
        # 0.20.0 legacy fallback (delete in 0.21.0): app created by an old
        # container after the backfill — verify against apps.api_key directly.
        if verify_secret(password, app_row["api_key"]):
            return dict(app_row)
        return None
