"""API key lifecycle — generation, resolution, revocation. Sync helpers are shared by the async (REST/MCP) and sync (SMTP) resolvers."""

import argparse
import json
import secrets
import sqlite3
import sys
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC

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

    Candidate apps are matched on key_prefix OR a NULL/empty prefix. The NULL
    arm is what makes the docstring above true: an app row that never had a
    prefix cannot be found BY that prefix, and it is exactly the row the
    backfill wrote as '' (COALESCE) and that resolve_key's indexed lookup
    therefore misses. Both the api_keys row and the apps row are healed to the
    real prefix on the way out, so a given app takes this path at most once.
    """
    if not token.startswith(APP_KEY_MARKER):
        return None
    prefix = token[len(APP_KEY_MARKER) : len(APP_KEY_MARKER) + PREFIX_LEN]
    if len(prefix) < PREFIX_LEN:
        return None
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM apps WHERE key_prefix = ? OR key_prefix IS NULL OR key_prefix = ''",
        (prefix,),
    )
    rows = await cursor.fetchall()
    for app_row in rows:
        if verify_secret(token, app_row["api_key"]):
            cursor = await db.execute(
                "SELECT * FROM api_keys WHERE app_id = ? AND key_hash = ?",
                (app_row["id"], app_row["api_key"]),
            )
            row = await cursor.fetchone()
            if row is None:
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
            elif row["key_prefix"] != prefix:
                # Backfilled from a NULL apps.key_prefix as ''. Heal it so the
                # indexed lookup in resolve_key finds it next time.
                await db.execute(
                    "UPDATE api_keys SET key_prefix = ? WHERE id = ?", (prefix, row["id"])
                )
                await db.commit()
            if not app_row["key_prefix"]:
                await db.execute(
                    "UPDATE apps SET key_prefix = ? WHERE id = ?", (prefix, app_row["id"])
                )
                await db.commit()
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


def _cli_create(args) -> int:
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    try:
        validate_scopes(scopes, None)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    expires_at = None
    if args.expires_days is not None:
        from datetime import datetime, timedelta

        expires_at = (datetime.now(tz=UTC) + timedelta(days=args.expires_days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    plaintext = generate_key(management=True)
    prefix = plaintext[len(MGMT_KEY_MARKER) : len(MGMT_KEY_MARKER) + PREFIX_LEN]
    try:
        with closing(sqlite3.connect(settings.db_path)) as db:
            db.execute(
                "INSERT INTO api_keys (id, key_hash, key_prefix, label, app_id, scopes, "
                "created_by, expires_at, created_at) VALUES (?, ?, ?, ?, NULL, ?, 'cli', ?, ?)",
                (
                    str(uuid.uuid4()),
                    hash_secret(plaintext),
                    prefix,
                    args.label,
                    json.dumps(sorted(set(scopes))),
                    expires_at,
                    utc_now_iso(),
                ),
            )
            db.commit()
    except sqlite3.OperationalError:
        print("error: database not initialized — start SeeSee once first", file=sys.stderr)
        return 3
    print(plaintext)
    print(
        "Store this key now — it is shown once and cannot be recovered.",
        file=sys.stderr,
    )
    return 0


def _cli_list(args) -> int:
    try:
        with closing(sqlite3.connect(settings.db_path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                f"SELECT {_KEY_METADATA_COLUMNS} FROM api_keys "  # noqa: S608
                "WHERE app_id IS NULL ORDER BY created_at DESC"
            ).fetchall()
    except sqlite3.OperationalError:
        print("error: database not initialized — start SeeSee once first", file=sys.stderr)
        return 3
    for row in rows:
        state = "revoked" if row["revoked_at"] else "active"
        print(
            f"{row['id']}  {row['label']!r}  prefix={row['key_prefix']}  "
            f"scopes={row['scopes']}  {state}  last_used={row['last_used_at']}"
        )
    return 0


def _cli_revoke(args) -> int:
    try:
        with closing(sqlite3.connect(settings.db_path)) as db:
            cursor = db.execute(
                "UPDATE api_keys SET revoked_at = ? "
                "WHERE id = ? AND app_id IS NULL AND revoked_at IS NULL",
                (utc_now_iso(), args.key_id),
            )
            db.commit()
    except sqlite3.OperationalError:
        print("error: database not initialized — start SeeSee once first", file=sys.stderr)
        return 3
    if cursor.rowcount == 0:
        print("error: no active management key with that id", file=sys.stderr)
        return 1
    print("revoked")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m seesee.keys",
        description="Manage SeeSee management API keys (headless bootstrap).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_create = sub.add_parser("create", help="Mint a management key (printed once)")
    p_create.add_argument("--label", required=True)
    p_create.add_argument(
        "--scopes",
        required=True,
        help="Comma-separated: emails:read,apps:read,apps:write,apps:delete",
    )
    p_create.add_argument("--expires-days", type=int, default=None)
    p_create.set_defaults(func=_cli_create)
    p_list = sub.add_parser("list", help="List management keys (metadata only)")
    p_list.set_defaults(func=_cli_list)
    p_revoke = sub.add_parser("revoke", help="Revoke a management key by id")
    p_revoke.add_argument("key_id")
    p_revoke.set_defaults(func=_cli_revoke)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
