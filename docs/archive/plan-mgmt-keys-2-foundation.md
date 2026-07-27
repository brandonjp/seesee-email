# Management Keys Foundation — Schema v4, `seesee/keys.py`, Auth Rewire

Sub-plan 2 of 4 for the 0.20.0 management-keys + MCP feature. Unified `api_keys` table, key-resolution module (sync/async split), rewired REST + SMTP auth with the transition-release legacy-column policy, and the CLI bootstrap. Design (source of truth — read §1, §1a, §3, §4, §9): `docs/superpowers/specs/2026-07-26-management-keys-mcp-design.md`.

⛔ **PREREQUISITE — `docs/plan-mgmt-keys-1-csrf.md` must be complete first** (same branch).

**Branch:** `feature/management-keys-mcp`

**Critical rule:** The entire existing test suite passes in every chunk, and **NO existing test file may be modified in this plan** — especially not `tests/test_smtp_integration.py`, `tests/test_smtp.py`, `tests/test_apps.py`, `tests/test_auth.py`, `tests/test_ingest.py`. If a change requires editing an existing test, the change is wrong — rework it. New tests go in the new files `tests/test_migration_v4.py`, `tests/test_api_keys.py`, `tests/test_smtp_keys.py`.

**Second critical rule:** The SMTP authenticator (`seesee/smtp_server.py`) must remain a **plain sync callable** — never `async def`, never calling async code. See the docstring at `smtp_server.py:63-75` for why (this exact bug silently broke all ingest for months).

**Testing:** `python -m pytest -x -q`. Lint: `ruff check . && ruff format --check .`

**Datetime convention:** all timestamps are UTC strings in `%Y-%m-%dT%H:%M:%S` format via `seesee.timezone.utc_now_iso()` — lexicographically comparable in SQL. Never store any other format.

---

## Chunk 1: Prerequisite gate + schema v4 (`seesee/database.py`, `tests/test_migration_v4.py`)

- [x] Step 1 (GATE): Run `test -f seesee/csrf.py && grep -q "Depends(require_csrf)" seesee/routes/ui.py && echo GATE-OK`. If this does not print `GATE-OK`, **HALT** — sub-plan 1 (`docs/plan-mgmt-keys-1-csrf.md`) has not run. Do not proceed or attempt to work around it.
- [x] Step 2: In `seesee/database.py`, set `SCHEMA_VERSION = 4` and append to `SCHEMA_SQL` (after the `emails_au` trigger):

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT PRIMARY KEY,
    key_hash     TEXT NOT NULL,
    key_prefix   TEXT NOT NULL,
    label        TEXT NOT NULL,
    app_id       TEXT REFERENCES apps(id),
    scopes       TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    expires_at   DATETIME,
    last_used_at DATETIME,
    revoked_at   DATETIME,
    created_at   DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_app_id ON api_keys(app_id);
```

(`app_id IS NULL` = management key. Fresh databases are born at v4 with this table via `SCHEMA_SQL` — the migration below only runs for databases upgrading from ≤3, because `init_db` stamps the version before `_run_migrations()`.)

- [x] Step 3: In `_run_migrations()`, after the `current_version < 3` block, add the v4 backfill. It MUST be this single statement (idempotent via `NOT EXISTS`; single-statement so concurrent deploying containers cannot interleave; `COALESCE` migrates NULL-prefix rows with an empty prefix so SMTP keeps working for them):

```python
    if current_version < 4:
        # Backfill one api_keys row per existing app. Single INSERT..SELECT:
        # idempotent (NOT EXISTS) and atomic under SQLite's writer lock, so a
        # deploy-overlap re-run can neither duplicate nor interleave.
        await _db.execute(
            """INSERT INTO api_keys
                   (id, key_hash, key_prefix, label, app_id, scopes, created_by, created_at)
               SELECT lower(hex(randomblob(16))), a.api_key, COALESCE(a.key_prefix, ''),
                      'default', a.id, '["emails:read","emails:write"]', 'migration',
                      a.created_at
               FROM apps a
               WHERE NOT EXISTS (SELECT 1 FROM api_keys k WHERE k.app_id = a.id)"""
        )
        current_version = 4
        await _db.commit()
        logger.info("Database migrated to schema version 4")
```

- [x] Step 4: Create `tests/test_migration_v4.py`. Use stdlib `sqlite3` to seed a pre-v4 database, then run `init_db()` against it. Tests (all `async` where they call `init_db`, following the async patterns in existing tests):
  - `test_fresh_db_has_api_keys_table` — after `init_db()` on a fresh path, `PRAGMA table_info(api_keys)` lists the 11 columns, and `schema_version` is `4`.
  - `test_v3_backfill` — seed: create a db file with `sqlite3` containing a `metadata` table (`schema_version` = `'3'`) and an `apps` table (copy the `apps` DDL from `SCHEMA_SQL`) with one row (`id='app1'`, `api_key=<bcrypt hash of a known plaintext via seesee.auth.hash_secret>`, `key_prefix=<first 8 chars of the random segment>`, other columns filled minimally). After `init_db()`: exactly one `api_keys` row exists with `app_id='app1'`, `key_hash` equal to the seeded hash, `key_prefix` equal to the seeded prefix, `scopes='["emails:read","emails:write"]'`, `created_by='migration'`, `label='default'`.
  - `test_backfill_idempotent` — after the v3 seed and `init_db()`, close the db, set `schema_version` back to `'3'` with sqlite3, run `init_db()` again: still exactly one `api_keys` row for `app1`.
  - `test_null_prefix_migrates_with_empty_prefix` — seed a v3 app row with `key_prefix=NULL`; after `init_db()` its `api_keys` row has `key_prefix=''` (not skipped).
- [x] Step 5: `python -m pytest -x -q` — full suite passes. `ruff check . && ruff format --check .`
- [x] Step 6: Commit: `git add seesee/database.py tests/test_migration_v4.py && git commit -m "feat(keys): schema v4 — unified api_keys table + backfill migration"`

### ✅ Review Checkpoint — Chunk 1
- [ ] `grep -n "SCHEMA_VERSION = 4" seesee/database.py`
- [ ] The backfill is ONE `INSERT INTO api_keys ... SELECT ... WHERE NOT EXISTS` statement — no Python loop over apps
- [ ] `api_keys` DDL appears in `SCHEMA_SQL` (not only in the migration): `grep -n "CREATE TABLE IF NOT EXISTS api_keys" seesee/database.py` hits inside the `SCHEMA_SQL` string
- [ ] `git diff HEAD~1 --name-only -- tests/` lists ONLY `tests/test_migration_v4.py`
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 2: `seesee/keys.py` — pure sync core (`seesee/keys.py`, `tests/test_api_keys.py`)

- [x] Step 1: Create `seesee/keys.py` with the module docstring `"""API key lifecycle — generation, resolution, revocation. Sync helpers are shared by the async (REST/MCP) and sync (SMTP) resolvers."""` and this content:

```python
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
        raise ValueError(
            f"Invalid scope(s) for {kind} key: {', '.join(sorted(invalid))}"
        )
```

- [x] Step 2: Create `tests/test_api_keys.py` with sync unit tests:
  - `test_generate_key_formats` — `generate_key()` starts with `ss_` and does NOT start with `ss_mgmt_`; `generate_key(management=True)` starts with `ss_mgmt_`.
  - `test_extract_prefix_app_key` — for `"ss_" + "a" * 43`: exactly one candidate, `"aaaaaaaa"`.
  - `test_extract_prefix_mgmt_key` — for `"ss_mgmt_" + "b" * 43`: TWO candidates, `["b" * 8, "mgmt_bbb"]` (mgmt marker slice first, then the ss_ slice `"mgmt_" + "bbb"`).
  - `test_extract_prefix_ambiguous_app_key` — an app key whose random segment starts `mgmt_`: `"ss_mgmt_xyzabcde..."` is indistinguishable from a mgmt key by text — both slices returned; assert both present.
  - `test_extract_prefix_too_short` — `"ss_abc"` and `"ss_mgmt_ab"` → `[]`; `"garbage"` → `[]`.
  - `test_key_is_active` — active row → `(True, "")`; `revoked_at` set → `(False, "revoked")`; `expires_at` in the past → `(False, "expired")`; `expires_at` in the future → active. Use plain dicts as rows.
  - `test_validate_scopes_matrix` — app key with `["emails:read"]` OK; app key with `["apps:write"]` raises ValueError; management key (`app_id=None`) with `["apps:read", "apps:write"]` OK; management key with `["emails:write"]` raises; empty list raises.
- [x] Step 3: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [x] Step 4: Commit: `git add seesee/keys.py tests/test_api_keys.py && git commit -m "feat(keys): key module sync core — generation, prefix extraction, scope matrix"`

### ✅ Review Checkpoint — Chunk 2
- [ ] `python -c "from seesee.keys import Principal, generate_key, extract_prefix, key_is_active, validate_scopes, KeyRevokedError, KeyExpiredError"` succeeds
- [ ] `extract_prefix` tries the LONGER marker first and can return two candidates; returns `[]` for short tokens
- [ ] Nothing in `keys.py` branches on the token prefix to decide key kind
- [ ] `git diff HEAD~1 --name-only -- tests/` lists ONLY `tests/test_api_keys.py`
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 3: `seesee/keys.py` — async layer (`seesee/keys.py`, `tests/test_api_keys.py`)

- [x] Step 1: Add to `seesee/keys.py` (imports: `json`, `uuid`, `datetime`, `from seesee.database import get_db`, `from seesee.timezone import utc_now_iso`):

```python
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
    return (now - timedelta(seconds=_LAST_USED_DEBOUNCE_SECONDS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


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
        cursor = await db.execute(
            "SELECT api_key FROM apps WHERE id = ?", (row["app_id"],)
        )
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
```

- [x] Step 2: Extend `tests/test_api_keys.py` with async tests (use the `client`/db fixtures pattern from `conftest.py`; `init_db` runs implicitly via `get_db`):
  - `test_create_and_resolve_management_key` — `create_key(label="ci", app_id=None, scopes=["apps:read"], expires_at=None, created_by="cli")` → `resolve_key(plaintext)` returns a Principal with `app_id is None`, `scopes == frozenset({"apps:read"})`.
  - `test_create_and_resolve_app_key` — app key round-trip (create an app first via the REST API with the `client` + `admin_auth_header` fixtures, then `create_key(app_id=...)`).
  - `test_resolve_unknown_returns_none` — a fresh `generate_key()` never stored → `None`.
  - `test_revoked_key_raises` — create, `revoke_key(key_id)`, then `resolve_key` raises `KeyRevokedError`.
  - `test_expired_key_raises` — create with `expires_at="2000-01-01T00:00:00"` → `KeyExpiredError`.
  - `test_last_used_debounce` — resolve the same key twice in quick succession; `last_used_at` after the second call equals the value after the first (one write).
  - `test_create_key_validates_matrix` — `create_key(app_id="x", scopes=["apps:write"], ...)` raises ValueError.
  - `test_revoke_primary_tombstones_legacy` — create an app via REST (plaintext key K, hash mirrored in `apps.api_key`); find its `api_keys` row; `revoke_key` it; assert `apps.api_key` changed (no longer verifies K) and `resolve_key(K)` raises `KeyRevokedError`.
  - `test_legacy_fallback_lazy_migrates` — create an app via REST, then DELETE its `api_keys` row directly (simulating a deploy-overlap orphan); `resolve_key(K)` succeeds AND a new `api_keys` row now exists for the app.
  - `test_list_keys_never_leaks_hashes` — `list_keys` result dicts contain no `key_hash` key.
- [x] Step 3: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [x] Step 4: Commit: `git add seesee/keys.py tests/test_api_keys.py && git commit -m "feat(keys): async resolver, mint/revoke/list, legacy fallback, tombstone"`

### ✅ Review Checkpoint — Chunk 3
- [ ] `_record_use` is a single guarded `UPDATE ... WHERE ... (last_used_at IS NULL OR last_used_at < ?)` — no read-compare-write
- [ ] `create_key` calls `validate_scopes` (matrix enforced at the shared mint path)
- [ ] `revoke_key` tombstones `apps.api_key`/`smtp_password` when the revoked key's hash matches `apps.api_key`
- [ ] `_resolve_legacy_fallback` lazily INSERTs the missing `api_keys` row on success
- [ ] `git diff HEAD~2 --name-only -- tests/` still lists only new test files
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 4: Rewire REST auth + dual-write (`seesee/dependencies.py`, `seesee/routes/apps.py`, `tests/test_api_keys.py`)

External behavior of existing routes must not change — the regression bar is the whole untouched suite.

- [x] Step 1: Rewrite `get_current_app` in `seesee/dependencies.py` to resolve through `seesee.keys` while keeping its exact return contract (the full app row as a dict) and its existing 401 messages for the missing-header and bad-format cases:

```python
async def get_current_app(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict:
    """Validate an app API key and return the authenticated app row.

    Resolution lives in seesee.keys (unified api_keys table). This dependency
    additionally requires an APP-bound key carrying emails:write — management
    keys cannot ingest.
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
    try:
        principal = await keys.resolve_key(token)
    except keys.KeyRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key revoked"
        ) from exc
    except keys.KeyExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired"
        ) from exc
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    if principal.app_id is None or "emails:write" not in principal.scopes:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="App API key required"
        )
    db = await get_db()
    cursor = await db.execute("SELECT * FROM apps WHERE id = ?", (principal.app_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    return dict(row)
```

Add `from seesee import keys` to the imports. `require_admin_or_app` needs no change — its Bearer branch already delegates to `get_current_app`.

- [x] Step 2: In `seesee/routes/apps.py` `create_app`, after the `INSERT INTO apps` and before `db.commit()`, dual-write the primary key row (design §1a — apps created under 0.20.0 keep working after a rollback because `apps.api_key` still holds the real hash):

```python
    await db.execute(
        "INSERT INTO api_keys (id, key_hash, key_prefix, label, app_id, scopes, "
        "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            api_key_hash,
            key_prefix,
            "default",
            app_id,
            '["emails:read","emails:write"]',
            "admin",
            now_iso,
        ),
    )
```

- [x] Step 3: In `rotate_key` (same file), preserve legacy immediate-invalidation semantics across BOTH tables: first `SELECT id, api_key FROM apps WHERE id = ?` (replacing the current `SELECT id`), then after computing the new hash: (a) `UPDATE apps ...` as today; (b) revoke the old primary row: `UPDATE api_keys SET revoked_at = <utc_now_iso()> WHERE app_id = ? AND key_hash = ? AND revoked_at IS NULL` with the OLD `api_key` hash; (c) insert the new key row (same INSERT shape as Step 2, `created_by`, `'admin'`, new hash/prefix, `label` `'default'`).
- [x] Step 4: Extend `tests/test_api_keys.py`:
  - `test_rest_auth_via_api_keys_table` — create app via REST; `POST /api/v1/emails` (the ingest route, Bearer = plaintext key) still 201s (proves the rewire path).
  - `test_revoked_key_gets_distinct_401` — revoke the app's primary key; ingest POST → 401 with detail `"API key revoked"`; also assert the app's OLD plaintext no longer authenticates even against `apps.api_key` (tombstone).
  - `test_mgmt_key_cannot_ingest` — mint a management key with `emails:read`; Bearer ingest POST → 401 `"App API key required"`.
  - `test_rotate_key_dual_write` — rotate via REST; old key 401s (revoked), new key ingests; `api_keys` has a revoked row and an active row for the app.
- [ ] Step 5: `python -m pytest -x -q` — the ENTIRE suite must pass with zero modifications to existing test files. If `test_apps.py`/`test_auth.py`/`test_ingest.py` fail, fix the implementation.
- [ ] Step 6: `ruff check . && ruff format --check .`
- [ ] Step 7: Commit: `git add seesee/dependencies.py seesee/routes/apps.py tests/test_api_keys.py && git commit -m "feat(keys): REST auth resolves via api_keys; create/rotate dual-write legacy columns"`

### ✅ Review Checkpoint — Chunk 4
- [ ] `get_current_app` returns the full app ROW dict (not a Principal) — `grep -A3 "SELECT \* FROM apps WHERE id" seesee/dependencies.py`
- [ ] Distinct 401 details exist: `grep -n '"API key revoked"\|"API key expired"' seesee/dependencies.py`
- [ ] `create_app` writes BOTH `apps.api_key` AND an `api_keys` row with the same hash
- [ ] `rotate_key` revokes the old `api_keys` row AND updates `apps` (legacy semantics preserved)
- [ ] `git diff HEAD~3 --name-only -- tests/` lists ONLY `tests/test_migration_v4.py` and `tests/test_api_keys.py`
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean

---

## Chunk 5: SMTP multi-key auth (`seesee/keys.py`, `seesee/smtp_server.py`, `tests/test_smtp_keys.py`)

⚠️ This chunk touches the file with the project's worst historical bug. The authenticator stays a plain sync callable; `tests/test_smtp_integration.py` and `tests/test_smtp.py` are FROZEN — if either needs edits, the implementation is wrong.

- [x] Step 1: Add to `seesee/keys.py` a sync resolver using stdlib `sqlite3` (imports at module top: `import sqlite3`, `from contextlib import closing`, `from seesee.config import settings`):

```python
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
        rows = db.execute(
            "SELECT * FROM api_keys WHERE app_id = ?", (app_row["id"],)
        ).fetchall()
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
```

(The async lazy-insert self-heal will adopt such an app on its first REST call; the SMTP path deliberately stays read-mostly and does not insert.)

- [x] Step 2: In `seesee/smtp_server.py`, replace the body of `SmtpAuthenticator.__call__`'s `try:` block: keep the username/password decoding as is, then:

```python
        try:
            app_row = resolve_smtp_password(username, password)
            if app_row is None:
                logger.warning("SMTP AUTH failed for %r", username)
                return AuthResult(success=False, handled=False)
            session.app = app_row  # type: ignore[attr-defined]
            logger.info("SMTP AUTH success for app %r (id=%s)", app_row["name"], app_row["id"])
            return AuthResult(success=True)
        except Exception:
            logger.exception("SMTP AUTH error")
            return AuthResult(success=False, handled=False)
```

Add `from seesee.keys import resolve_smtp_password` to the imports; remove the now-unused `sqlite3`/`closing`/`verify_secret` imports ONLY if nothing else in the file uses them (check first). Keep the class docstring (the sync-callable warning) verbatim.

- [x] Step 3: Create `tests/test_smtp_keys.py` (NEW file — do not touch `test_smtp.py`), following the direct-authenticator-call style used in `tests/test_smtp.py`:
  - `test_authenticator_still_sync` — `import asyncio, inspect; assert not asyncio.iscoroutinefunction(SmtpAuthenticator.__call__)` and `assert not inspect.iscoroutinefunction(resolve_smtp_password)`.
  - `test_second_key_authenticates` — create an app via REST; mint a second key via `keys.create_key(app_id=..., scopes=["emails:write"], ...)`; the authenticator accepts the SECOND plaintext as SMTP password.
  - `test_original_key_still_works` — after minting the second key, the original creation-time key still authenticates (multi-key overlap window).
  - `test_revoked_key_rejected_over_smtp` — revoke the second key; the authenticator now rejects its plaintext (and the tombstone test: revoke the PRIMARY key → its plaintext is rejected too, including via the legacy-column path).
  - `test_emails_read_only_key_rejected` — mint an app key with scopes `["emails:read"]`; its plaintext must NOT authenticate over SMTP.
- [x] Step 4: `python -m pytest -x -q` — full suite, including `test_smtp_integration.py`, passes unmodified.
- [x] Step 5: `ruff check . && ruff format --check .`
- [x] Step 6: Commit: `git add seesee/keys.py seesee/smtp_server.py tests/test_smtp_keys.py && git commit -m "feat(keys): SMTP auth accepts any active emails:write key (sync resolver)"`

### ✅ Review Checkpoint — Chunk 5
- [ ] `SmtpAuthenticator.__call__` is NOT a coroutine function: `python -c "import asyncio; from seesee.smtp_server import SmtpAuthenticator; assert not asyncio.iscoroutinefunction(SmtpAuthenticator.__call__)"`
- [ ] `resolve_smtp_password` uses stdlib `sqlite3` with `busy_timeout` — no aiosqlite, no asyncio imports in its body
- [ ] `git diff HEAD~1 -- tests/test_smtp.py tests/test_smtp_integration.py` is EMPTY
- [ ] Tests pass: `python -m pytest -x -q` (watch `test_smtp_integration.py` specifically)
- [ ] Git status is clean

---

## Chunk 6: CLI bootstrap + version (`seesee/keys.py`, `tests/test_api_keys.py`, `pyproject.toml`, `seesee/__init__.py`, `CHANGELOG.md`)

- [x] Step 1: Append to `seesee/keys.py` a sync CLI (headless bootstrap — no running server; design §9). Sync `sqlite3` throughout; `created_by='cli'`:

```python
def _cli_create(args) -> int:
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    try:
        validate_scopes(scopes, None)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    expires_at = None
    if args.expires_days is not None:
        from datetime import datetime, timedelta, timezone

        expires_at = (
            datetime.now(tz=timezone.utc) + timedelta(days=args.expires_days)
        ).strftime("%Y-%m-%dT%H:%M:%S")
    plaintext = generate_key(management=True)
    prefix = plaintext[len(MGMT_KEY_MARKER) : len(MGMT_KEY_MARKER) + PREFIX_LEN]
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
    print(plaintext)
    print(
        "Store this key now — it is shown once and cannot be recovered.",
        file=sys.stderr,
    )
    return 0


def _cli_list(args) -> int:
    with closing(sqlite3.connect(settings.db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            f"SELECT {_KEY_METADATA_COLUMNS} FROM api_keys "  # noqa: S608
            "WHERE app_id IS NULL ORDER BY created_at DESC"
        ).fetchall()
    for row in rows:
        state = "revoked" if row["revoked_at"] else "active"
        print(
            f"{row['id']}  {row['label']!r}  prefix={row['key_prefix']}  "
            f"scopes={row['scopes']}  {state}  last_used={row['last_used_at']}"
        )
    return 0


def _cli_revoke(args) -> int:
    with closing(sqlite3.connect(settings.db_path)) as db:
        cursor = db.execute(
            "UPDATE api_keys SET revoked_at = ? "
            "WHERE id = ? AND app_id IS NULL AND revoked_at IS NULL",
            (utc_now_iso(), args.key_id),
        )
        db.commit()
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
```

Add `import argparse` and `import sys` to the module imports. NOTE: the CLI assumes the database schema exists (server has booted at least once); if `sqlite3.OperationalError: no such table` occurs, that precondition failed — wrap the `_cli_create`/`_cli_list`/`_cli_revoke` db work in `try/except sqlite3.OperationalError` printing `error: database not initialized — start SeeSee once first` and returning 3.

- [x] Step 2: Extend `tests/test_api_keys.py`:
  - `test_cli_create_and_resolve` — after `init_db()` (get a db via the fixtures), call `keys.main(["create", "--label", "ci", "--scopes", "apps:write,emails:read"])` capturing stdout (capsys); the printed key resolves via `resolve_key` to a management Principal with those scopes and `created_by` recorded as `cli` in the row.
  - `test_cli_create_invalid_scopes_exits_2` — `main(["create", "--label", "x", "--scopes", "emails:write"])` returns 2 (management keys cannot carry `emails:write`).
  - `test_cli_list_and_revoke` — create via CLI, `list` output contains the label, `revoke <id>` returns 0, second revoke returns 1.
- [x] Step 3: Bump version to `0.19.18-dev` in `pyproject.toml` and `seesee/__init__.py`. Add to `CHANGELOG.md` `[Unreleased]` → `### Added`: `- Unified api_keys table (schema v4): multi-key-per-app, management keys (ss_mgmt_), scoped credentials, safe rotation over REST and SMTP, CLI bootstrap (python -m seesee.keys)`
- [x] Step 4: `python -m pytest -x -q`; `ruff check . && ruff format --check .`
- [ ] Step 5: Commit: `git add seesee/keys.py tests/test_api_keys.py pyproject.toml seesee/__init__.py CHANGELOG.md && git commit -m "feat(keys): CLI bootstrap for management keys; bump 0.19.18-dev"`

### ✅ Review Checkpoint — Chunk 6
- [ ] `python -m seesee.keys create --label t --scopes bogus` exits non-zero with a scope error (run against a scratch `SEESEE_DB_PATH`)
- [ ] CLI never prints hashes; `list` prints metadata only
- [ ] Version `0.19.18-dev` in both files; `python -m pytest tests/test_version_sync.py -q` passes
- [ ] `git diff` since plan start (`git diff $(git merge-base HEAD main) --name-only -- tests/` if needed) shows NO modified existing test files — only `test_migration_v4.py`, `test_api_keys.py`, `test_smtp_keys.py` added
- [ ] Tests pass: `python -m pytest -x -q`
- [ ] Git status is clean
