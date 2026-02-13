"""SQLite database setup, schema creation, FTS5 indexing, and migrations.

Uses aiosqlite for async access. WAL mode is enabled for concurrent reads.
All queries must use parameterized values — never string-format SQL.
"""

import aiosqlite

from seesee.config import settings

_db: aiosqlite.Connection | None = None

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
    global _db
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


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
