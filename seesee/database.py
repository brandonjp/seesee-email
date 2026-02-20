"""SQLite database setup, schema creation, FTS5 indexing, and migrations.

Uses aiosqlite for async access. WAL mode is enabled for concurrent reads.
All queries must use parameterized values — never string-format SQL.
"""

import logging
import pathlib
import time

import aiosqlite

from seesee.config import settings

logger = logging.getLogger("seesee")

_db: aiosqlite.Connection | None = None
_startup_time: float = 0.0

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    last_activity_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_apps_key_prefix ON apps(key_prefix);

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL REFERENCES apps(id),
    to_addresses TEXT NOT NULL,
    from_address TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_html TEXT,
    body_text TEXT,
    body_preview TEXT,
    body_size_bytes INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'sent',
    provider TEXT,
    provider_message_id TEXT,
    error_message TEXT,
    metadata TEXT,
    cc_addresses TEXT,
    bcc_addresses TEXT,
    reply_to TEXT,
    tags TEXT,
    ingest_method TEXT NOT NULL DEFAULT 'api',
    logged_at DATETIME NOT NULL DEFAULT (datetime('now')),
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_emails_app_id ON emails(app_id);
CREATE INDEX IF NOT EXISTS idx_emails_status ON emails(status);
CREATE INDEX IF NOT EXISTS idx_emails_logged_at ON emails(logged_at);
CREATE INDEX IF NOT EXISTS idx_emails_created_at ON emails(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
    subject,
    body_text,
    body_preview,
    to_addresses,
    from_address,
    error_message,
    content='emails',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS emails_ai AFTER INSERT ON emails BEGIN
    INSERT INTO emails_fts(rowid, subject, body_text, body_preview, to_addresses, from_address, error_message)
    VALUES (NEW.rowid, NEW.subject, NEW.body_text, NEW.body_preview, NEW.to_addresses, NEW.from_address, NEW.error_message);
END;

CREATE TRIGGER IF NOT EXISTS emails_ad AFTER DELETE ON emails BEGIN
    INSERT INTO emails_fts(emails_fts, rowid, subject, body_text, body_preview, to_addresses, from_address, error_message)
    VALUES ('delete', OLD.rowid, OLD.subject, OLD.body_text, OLD.body_preview, OLD.to_addresses, OLD.from_address, OLD.error_message);
END;

CREATE TRIGGER IF NOT EXISTS emails_au AFTER UPDATE ON emails BEGIN
    INSERT INTO emails_fts(emails_fts, rowid, subject, body_text, body_preview, to_addresses, from_address, error_message)
    VALUES ('delete', OLD.rowid, OLD.subject, OLD.body_text, OLD.body_preview, OLD.to_addresses, OLD.from_address, OLD.error_message);
    INSERT INTO emails_fts(rowid, subject, body_text, body_preview, to_addresses, from_address, error_message)
    VALUES (NEW.rowid, NEW.subject, NEW.body_text, NEW.body_preview, NEW.to_addresses, NEW.from_address, NEW.error_message);
END;
"""


async def get_db() -> aiosqlite.Connection:
    """Get the database connection, initializing if needed."""
    global _db
    if _db is None:
        await init_db()
    assert _db is not None
    return _db


async def init_db() -> None:
    """Initialize the database connection and create schema."""
    global _db, _startup_time

    db_path = pathlib.Path(settings.db_path)
    db_existed = db_path.exists()
    db_size_before = db_path.stat().st_size if db_existed else 0

    _db = await aiosqlite.connect(settings.db_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(SCHEMA_SQL)
    await _db.execute(
        "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    await _db.commit()

    _startup_time = time.monotonic()

    # --- Persistence diagnostics ---
    db_size_after = db_path.stat().st_size if db_path.exists() else 0

    cursor = await _db.execute("SELECT COUNT(*) FROM apps")
    app_count = (await cursor.fetchone())[0]

    cursor = await _db.execute("SELECT COUNT(*) FROM emails")
    email_count = (await cursor.fetchone())[0]

    mount_info = _get_mount_info(str(db_path.parent))

    logger.info("--- SeeSee Persistence Diagnostics ---")
    logger.info("Database path: %s", settings.db_path)
    logger.info(
        "Database file: %s (size before init: %d bytes, after: %d bytes)",
        "EXISTING" if db_existed else "NEW",
        db_size_before,
        db_size_after,
    )
    logger.info("Data: %d apps, %d emails", app_count, email_count)
    logger.info("Mount info for %s: %s", db_path.parent, mount_info)

    if not db_existed or app_count == 0:
        logger.warning(
            "DATABASE APPEARS FRESHLY CREATED (0 apps). "
            "If you expected existing data, your volume may not be persisting "
            "across deploys. Check your Coolify Storages configuration or "
            "docker-compose volume mounts."
        )

    logger.info("--- End Persistence Diagnostics ---")


def get_startup_time() -> float:
    """Return the monotonic timestamp recorded at startup."""
    return _startup_time


def _get_mount_info(directory: str) -> str:
    """Check /proc/mounts to determine what filesystem a directory is on.

    Returns a human-readable string describing the mount, or a fallback
    message on non-Linux systems.
    """
    proc_mounts = pathlib.Path("/proc/mounts")
    if not proc_mounts.exists():
        return "(/proc/mounts not available)"

    try:
        mounts_text = proc_mounts.read_text()
        best_match = ""
        best_line = ""
        for line in mounts_text.strip().splitlines():
            parts = line.split()
            if len(parts) >= 4:
                mount_point = parts[1]
                if directory.startswith(mount_point) and len(mount_point) > len(best_match):
                    best_match = mount_point
                    best_line = line
        if best_line:
            parts = best_line.split()
            return f"device={parts[0]} mount={parts[1]} fstype={parts[2]}"
        return "(no matching mount found)"
    except Exception as e:
        return f"(error reading /proc/mounts: {e})"


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
