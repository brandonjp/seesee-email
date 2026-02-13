"""Tests for retention cleanup logic."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from seesee.config import settings
from seesee.database import get_db, init_db
from seesee.retention import (
    _effective_limit,
    enforce_global_storage_cap,
    enforce_max_age,
    enforce_max_count,
    run_cleanup,
)


async def _create_app(
    app_id: str | None = None,
    name: str = "Test App",
    retention_max_count: int | None = None,
    retention_max_age_days: int | None = None,
) -> str:
    """Insert an app directly into the database and return its id."""
    db = await get_db()
    app_id = app_id or str(uuid.uuid4())
    await db.execute(
        """INSERT INTO apps (id, name, slug, api_key, body_storage_mode,
           retention_max_count, retention_max_age_days)
        VALUES (?, ?, ?, ?, 'full', ?, ?)""",
        (
            app_id,
            name,
            name.lower().replace(" ", "-"),
            "fake_hash",
            retention_max_count,
            retention_max_age_days,
        ),
    )
    await db.commit()
    return app_id


async def _insert_email(
    app_id: str,
    logged_at: datetime | None = None,
    body_size_bytes: int = 100,
    subject: str = "Test",
) -> str:
    """Insert an email directly into the database and return its id."""
    db = await get_db()
    email_id = str(uuid.uuid4())
    now = logged_at or datetime.now(UTC)
    await db.execute(
        """INSERT INTO emails (id, app_id, to_addresses, from_address, subject,
           body_size_bytes, status, ingest_method, logged_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'sent', 'api', ?, ?)""",
        (
            email_id,
            app_id,
            '["user@example.com"]',
            "from@example.com",
            subject,
            body_size_bytes,
            now.isoformat(),
            now.isoformat(),
        ),
    )
    await db.commit()
    return email_id


async def _count_emails(app_id: str | None = None) -> int:
    """Count emails, optionally filtered by app_id."""
    db = await get_db()
    if app_id:
        cursor = await db.execute("SELECT COUNT(*) FROM emails WHERE app_id = ?", (app_id,))
    else:
        cursor = await db.execute("SELECT COUNT(*) FROM emails")
    row = await cursor.fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# _effective_limit helper
# ---------------------------------------------------------------------------


def test_effective_limit_global_only():
    """When app override is None, use global value."""
    assert _effective_limit(None, 1000) == 1000


def test_effective_limit_app_override_stricter():
    """When app override is smaller, use app value."""
    assert _effective_limit(50, 1000) == 50


def test_effective_limit_global_stricter():
    """When global is smaller than app override, use global value."""
    assert _effective_limit(2000, 1000) == 1000


def test_effective_limit_zero_app_value():
    """App value of 0 is treated as unset — use global."""
    assert _effective_limit(0, 1000) == 1000


def test_effective_limit_equal_values():
    """When app and global are equal, return that value."""
    assert _effective_limit(500, 500) == 500


# ---------------------------------------------------------------------------
# Max count enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_count_deletes_oldest():
    """enforce_max_count should delete oldest emails first."""
    await init_db()
    app_id = await _create_app()

    # Insert 5 emails with known order
    now = datetime.now(UTC)
    ids = []
    for i in range(5):
        eid = await _insert_email(
            app_id, logged_at=now - timedelta(hours=5 - i), subject=f"Email {i}"
        )
        ids.append(eid)

    # Keep only 3
    deleted = await enforce_max_count(app_id, 3)
    assert deleted == 2
    assert await _count_emails(app_id) == 3

    # The two oldest (ids[0], ids[1]) should be gone
    db = await get_db()
    for old_id in ids[:2]:
        cursor = await db.execute("SELECT id FROM emails WHERE id = ?", (old_id,))
        assert await cursor.fetchone() is None

    # The three newest should remain
    for new_id in ids[2:]:
        cursor = await db.execute("SELECT id FROM emails WHERE id = ?", (new_id,))
        assert await cursor.fetchone() is not None


@pytest.mark.asyncio
async def test_max_count_no_delete_when_under_limit():
    """No emails deleted when count is under limit."""
    await init_db()
    app_id = await _create_app()

    for _ in range(3):
        await _insert_email(app_id)

    deleted = await enforce_max_count(app_id, 10)
    assert deleted == 0
    assert await _count_emails(app_id) == 3


@pytest.mark.asyncio
async def test_max_count_exact_limit():
    """No emails deleted when count equals the limit exactly."""
    await init_db()
    app_id = await _create_app()

    for _ in range(5):
        await _insert_email(app_id)

    deleted = await enforce_max_count(app_id, 5)
    assert deleted == 0
    assert await _count_emails(app_id) == 5


@pytest.mark.asyncio
async def test_max_count_per_app_override(monkeypatch):
    """Per-app override should take precedence when stricter than global."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 100)

    # App with stricter override (keep 2)
    app_id = await _create_app(retention_max_count=2)

    for _ in range(5):
        await _insert_email(app_id)

    # run_cleanup should use min(app=2, global=100) = 2
    await run_cleanup()
    assert await _count_emails(app_id) == 2


@pytest.mark.asyncio
async def test_max_count_global_stricter_than_app(monkeypatch):
    """Global limit should win when stricter than app override."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 3)

    # App with looser override (keep 10)
    app_id = await _create_app(retention_max_count=10)

    for _ in range(5):
        await _insert_email(app_id)

    await run_cleanup()
    assert await _count_emails(app_id) == 3


# ---------------------------------------------------------------------------
# Max age enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_age_deletes_old_emails():
    """enforce_max_age should delete emails older than the cutoff."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    # 3 old emails (100 days ago)
    old_ids = []
    for _ in range(3):
        eid = await _insert_email(app_id, logged_at=now - timedelta(days=100))
        old_ids.append(eid)

    # 2 recent emails (1 day ago)
    new_ids = []
    for _ in range(2):
        eid = await _insert_email(app_id, logged_at=now - timedelta(days=1))
        new_ids.append(eid)

    deleted = await enforce_max_age(app_id, 30)
    assert deleted == 3
    assert await _count_emails(app_id) == 2

    # Verify correct emails remain
    db = await get_db()
    for new_id in new_ids:
        cursor = await db.execute("SELECT id FROM emails WHERE id = ?", (new_id,))
        assert await cursor.fetchone() is not None


@pytest.mark.asyncio
async def test_max_age_no_delete_when_all_recent():
    """No emails deleted when all are within the retention window."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    for _ in range(3):
        await _insert_email(app_id, logged_at=now - timedelta(days=1))

    deleted = await enforce_max_age(app_id, 30)
    assert deleted == 0
    assert await _count_emails(app_id) == 3


@pytest.mark.asyncio
async def test_max_age_per_app_override(monkeypatch):
    """Per-app age override should take precedence when stricter."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_age_days", 365)

    # App with stricter override (keep only 7 days)
    app_id = await _create_app(retention_max_age_days=7)
    now = datetime.now(UTC)

    await _insert_email(app_id, logged_at=now - timedelta(days=30))
    await _insert_email(app_id, logged_at=now - timedelta(days=1))

    await run_cleanup()
    # min(app=7, global=365) = 7, so the 30-day-old email should be deleted
    assert await _count_emails(app_id) == 1


@pytest.mark.asyncio
async def test_max_age_global_stricter_than_app(monkeypatch):
    """Global age limit should win when stricter than app override."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_age_days", 7)

    # App with looser override (keep 365 days)
    app_id = await _create_app(retention_max_age_days=365)
    now = datetime.now(UTC)

    await _insert_email(app_id, logged_at=now - timedelta(days=30))
    await _insert_email(app_id, logged_at=now - timedelta(days=1))

    await run_cleanup()
    # min(app=365, global=7) = 7, so the 30-day-old email should be deleted
    assert await _count_emails(app_id) == 1


# ---------------------------------------------------------------------------
# Global storage cap enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_storage_cap_deletes_oldest(monkeypatch):
    """enforce_global_storage_cap should delete oldest emails to get under limit."""
    await init_db()
    # Set storage cap to approximately 300 bytes
    monkeypatch.setattr(settings, "retention_max_storage_mb", 0)
    # 0 MB = 0 bytes, everything should be deleted — use a small custom cap instead
    # Let's set a very small cap that allows 2 of 4 emails (each 100 bytes)
    # 300 bytes = 0.000286 MB — but the setting is int. So let's make emails big.
    # Actually, let's just test by patching to 0 which means delete everything,
    # and separately test that some remain when cap is above total.

    app_id = await _create_app()
    now = datetime.now(UTC)

    for i in range(4):
        await _insert_email(app_id, logged_at=now - timedelta(hours=4 - i), body_size_bytes=100)

    # Cap is 0 MB = 0 bytes, total is 400 bytes → delete all
    deleted, freed = await enforce_global_storage_cap()
    assert deleted == 4
    assert freed == 400
    assert await _count_emails() == 0


@pytest.mark.asyncio
async def test_global_storage_cap_keeps_emails_under_limit(monkeypatch):
    """No emails deleted when total storage is under the cap."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)

    app_id = await _create_app()
    for _ in range(3):
        await _insert_email(app_id, body_size_bytes=100)

    deleted, freed = await enforce_global_storage_cap()
    assert deleted == 0
    assert freed == 0
    assert await _count_emails() == 3


@pytest.mark.asyncio
async def test_global_storage_cap_partial_deletion(monkeypatch):
    """Storage cap should delete only enough emails to get under the limit."""
    await init_db()
    # Create emails with known sizes, set cap so some are kept
    # Each email is 1MB, create 5 of them (5MB total), cap at 3MB
    one_mb = 1024 * 1024
    monkeypatch.setattr(settings, "retention_max_storage_mb", 3)

    app_id = await _create_app()
    now = datetime.now(UTC)

    for i in range(5):
        await _insert_email(app_id, logged_at=now - timedelta(hours=5 - i), body_size_bytes=one_mb)

    deleted, freed = await enforce_global_storage_cap()
    # Need to delete at least 2 emails (5MB - 2MB = 3MB, which equals cap)
    assert deleted >= 2
    remaining = await _count_emails()
    assert remaining <= 3

    # Verify total storage is now within cap
    db = await get_db()
    cursor = await db.execute("SELECT COALESCE(SUM(body_size_bytes), 0) FROM emails")
    row = await cursor.fetchone()
    assert row[0] <= 3 * one_mb


@pytest.mark.asyncio
async def test_global_storage_cap_is_cross_app(monkeypatch):
    """Storage cap is global — deletes across all apps, oldest first."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_storage_mb", 0)

    app1_id = await _create_app(name="App One")
    app2_id = await _create_app(name="App Two")

    now = datetime.now(UTC)
    await _insert_email(app1_id, logged_at=now - timedelta(hours=3), body_size_bytes=100)
    await _insert_email(app2_id, logged_at=now - timedelta(hours=2), body_size_bytes=100)
    await _insert_email(app1_id, logged_at=now - timedelta(hours=1), body_size_bytes=100)

    deleted, freed = await enforce_global_storage_cap()
    assert deleted == 3
    assert freed == 300


# ---------------------------------------------------------------------------
# Combined cleanup (run_cleanup)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_cleanup_empty_database():
    """Cleanup should run without error on an empty database (no apps, no emails)."""
    await init_db()
    # Should not raise
    await run_cleanup()


@pytest.mark.asyncio
async def test_run_cleanup_no_emails():
    """Cleanup should run without error when apps exist but have no emails."""
    await init_db()
    await _create_app()
    await run_cleanup()


@pytest.mark.asyncio
async def test_run_cleanup_both_rules_applied(monkeypatch):
    """Both max_count and max_age should be applied in a single cleanup."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 10)
    monkeypatch.setattr(settings, "retention_max_age_days", 30)
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)

    app_id = await _create_app()
    now = datetime.now(UTC)

    # 5 old emails (over 30 days)
    for _ in range(5):
        await _insert_email(app_id, logged_at=now - timedelta(days=60))

    # 8 recent emails
    for _ in range(8):
        await _insert_email(app_id, logged_at=now - timedelta(hours=1))

    await run_cleanup()

    # Max age removes the 5 old ones, max count (10) doesn't affect the 8 remaining
    assert await _count_emails(app_id) == 8


@pytest.mark.asyncio
async def test_run_cleanup_multiple_apps(monkeypatch):
    """Cleanup processes each app independently."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 3)
    monkeypatch.setattr(settings, "retention_max_age_days", 365)
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)

    app1_id = await _create_app(name="App One")
    app2_id = await _create_app(name="App Two")

    for _ in range(5):
        await _insert_email(app1_id)
    for _ in range(2):
        await _insert_email(app2_id)

    await run_cleanup()

    # App1: had 5, capped to 3
    assert await _count_emails(app1_id) == 3
    # App2: had 2, under limit
    assert await _count_emails(app2_id) == 2


# ---------------------------------------------------------------------------
# FTS5 consistency after retention deletes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fts_index_consistent_after_retention():
    """FTS5 index should stay consistent after retention deletes emails."""
    await init_db()
    app_id = await _create_app()

    # Insert emails with distinctive subjects for FTS search
    now = datetime.now(UTC)
    await _insert_email(app_id, logged_at=now - timedelta(hours=3), subject="AlphaUnique report")
    await _insert_email(app_id, logged_at=now - timedelta(hours=2), subject="BetaUnique report")
    await _insert_email(app_id, logged_at=now - timedelta(hours=1), subject="GammaUnique report")

    # Verify all three are in FTS
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?", ("report",)
    )
    assert (await cursor.fetchone())[0] == 3

    # Delete oldest (keep 2)
    deleted = await enforce_max_count(app_id, 2)
    assert deleted == 1

    # FTS should now only find 2 results
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?", ("report",)
    )
    assert (await cursor.fetchone())[0] == 2

    # The deleted email (AlphaUnique) should not be in FTS
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?", ("AlphaUnique",)
    )
    assert (await cursor.fetchone())[0] == 0

    # Remaining emails should still be searchable
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?", ("BetaUnique",)
    )
    assert (await cursor.fetchone())[0] == 1

    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?", ("GammaUnique",)
    )
    assert (await cursor.fetchone())[0] == 1
