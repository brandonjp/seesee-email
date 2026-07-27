"""Tests for schema v4 migration — unified api_keys table + backfill."""

import sqlite3

import pytest

from seesee.auth import hash_secret
from seesee.config import settings
from seesee.database import close_db, init_db
from seesee.timezone import utc_now_iso

_SEED_METADATA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_SEED_APPS_SQL = """
CREATE TABLE IF NOT EXISTS apps (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    api_key TEXT NOT NULL,
    key_prefix TEXT,
    smtp_username TEXT,
    smtp_password TEXT,
    body_storage_mode TEXT NOT NULL DEFAULT 'full',
    retention_max_count INTEGER,
    retention_max_age_days INTEGER,
    retention_degrade_to_text_days INTEGER,
    retention_degrade_to_preview_days INTEGER,
    created_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    last_activity_at DATETIME
);
"""


def _seed_v3_db(db_path: str, api_key_hash: str, key_prefix: str | None) -> None:
    """Create a pre-v4 database file with one app row via stdlib sqlite3."""
    with sqlite3.connect(db_path) as db:
        db.executescript(_SEED_METADATA_SQL)
        db.executescript(_SEED_APPS_SQL)
        db.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '3')")
        db.execute(
            "INSERT INTO apps (id, name, slug, api_key, key_prefix, smtp_username, "
            "smtp_password, created_at) "
            "VALUES ('app1', 'App One', 'app-one', ?, ?, 'app-one', ?, ?)",
            (api_key_hash, key_prefix, api_key_hash, utc_now_iso()),
        )
        db.commit()


@pytest.mark.asyncio
async def test_fresh_db_has_api_keys_table():
    """A fresh database is born at v4 with the api_keys table."""
    await init_db()
    from seesee.database import _db

    cursor = await _db.execute("PRAGMA table_info(api_keys)")
    columns = await cursor.fetchall()
    assert len(columns) == 11

    cursor = await _db.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
    row = await cursor.fetchone()
    assert row[0] == "4"


@pytest.mark.asyncio
async def test_v3_backfill():
    """Upgrading from v3 backfills exactly one api_keys row per app."""
    known_plaintext = "ss_" + "a" * 32
    key_prefix = "aaaaaaaa"
    api_key_hash = hash_secret(known_plaintext)
    _seed_v3_db(settings.db_path, api_key_hash, key_prefix)

    await init_db()
    from seesee.database import _db

    cursor = await _db.execute("SELECT * FROM api_keys WHERE app_id = 'app1'")
    rows = await cursor.fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["app_id"] == "app1"
    assert row["key_hash"] == api_key_hash
    assert row["key_prefix"] == key_prefix
    assert row["scopes"] == '["emails:read","emails:write"]'
    assert row["created_by"] == "migration"
    assert row["label"] == "default"


@pytest.mark.asyncio
async def test_backfill_idempotent():
    """Re-running the v4 migration does not duplicate the backfilled row."""
    known_plaintext = "ss_" + "b" * 32
    key_prefix = "bbbbbbbb"
    api_key_hash = hash_secret(known_plaintext)
    _seed_v3_db(settings.db_path, api_key_hash, key_prefix)

    await init_db()
    await close_db()

    with sqlite3.connect(settings.db_path) as db:
        db.execute("UPDATE metadata SET value = '3' WHERE key = 'schema_version'")
        db.commit()

    await init_db()
    from seesee.database import _db

    cursor = await _db.execute("SELECT * FROM api_keys WHERE app_id = 'app1'")
    rows = await cursor.fetchall()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_null_prefix_migrates_with_empty_prefix():
    """A v3 app row with a NULL key_prefix migrates with an empty-string prefix."""
    known_plaintext = "ss_" + "c" * 32
    api_key_hash = hash_secret(known_plaintext)
    _seed_v3_db(settings.db_path, api_key_hash, None)

    await init_db()
    from seesee.database import _db

    cursor = await _db.execute("SELECT * FROM api_keys WHERE app_id = 'app1'")
    row = await cursor.fetchone()
    assert row["key_prefix"] == ""


# ---------------------------------------------------------------------------
# The upgrade that actually matters: keys issued before 0.20.0 must keep
# working afterwards, on both transports. Backfilling the right ROWS is not the
# same as the credential still authenticating.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_upgrade_key_still_authenticates_over_rest():
    known_plaintext = "ss_" + "d" * 32
    _seed_v3_db(settings.db_path, hash_secret(known_plaintext), known_plaintext[3:11])

    await init_db()

    from seesee import keys

    principal = await keys.resolve_key(known_plaintext)
    assert principal is not None, "an app key minted before 0.20.0 must survive the upgrade"
    assert principal.app_id == "app1"
    assert "emails:write" in principal.scopes


@pytest.mark.asyncio
async def test_pre_upgrade_key_still_authenticates_over_smtp():
    known_plaintext = "ss_" + "e" * 32
    _seed_v3_db(settings.db_path, hash_secret(known_plaintext), known_plaintext[3:11])

    await init_db()

    from seesee.keys import resolve_smtp_password

    app_row = resolve_smtp_password("app-one", known_plaintext)
    assert app_row is not None, "SMTP credentials must survive the upgrade too"
    assert app_row["id"] == "app1"


@pytest.mark.asyncio
async def test_pre_upgrade_key_with_null_prefix_still_authenticates():
    """The backfill stores '' for a NULL key_prefix, so the prefix index cannot
    find the row — the legacy fallback has to carry these until 0.21.0."""
    known_plaintext = "ss_" + "f" * 32
    _seed_v3_db(settings.db_path, hash_secret(known_plaintext), None)

    await init_db()

    from seesee import keys

    principal = await keys.resolve_key(known_plaintext)
    assert principal is not None
    assert principal.app_id == "app1"


@pytest.mark.asyncio
async def test_null_prefix_is_healed_on_first_use():
    """After the fallback rescues a NULL-prefix app, both rows carry the real
    prefix, so the next request takes the fast indexed path."""
    known_plaintext = "ss_" + "g" * 32
    _seed_v3_db(settings.db_path, hash_secret(known_plaintext), None)

    await init_db()

    from seesee import keys
    from seesee.database import _db

    assert await keys.resolve_key(known_plaintext) is not None

    expected = known_plaintext[3:11]
    cursor = await _db.execute("SELECT key_prefix FROM api_keys WHERE app_id = 'app1'")
    assert (await cursor.fetchone())["key_prefix"] == expected
    cursor = await _db.execute("SELECT key_prefix FROM apps WHERE id = 'app1'")
    assert (await cursor.fetchone())["key_prefix"] == expected
