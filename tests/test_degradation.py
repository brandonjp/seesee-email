"""Tests for graduated body degradation logic."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from seesee.config import settings
from seesee.database import get_db, init_db
from seesee.retention import (
    _effective_degrade_days,
    degrade_to_preview,
    degrade_to_text,
    run_cleanup,
)


async def _create_app(
    app_id: str | None = None,
    name: str = "Test App",
    retention_degrade_to_text_days: int | None = None,
    retention_degrade_to_preview_days: int | None = None,
) -> str:
    """Insert an app directly into the database and return its id."""
    db = await get_db()
    app_id = app_id or str(uuid.uuid4())
    await db.execute(
        """INSERT INTO apps (id, name, slug, api_key, body_storage_mode,
           retention_degrade_to_text_days, retention_degrade_to_preview_days)
        VALUES (?, ?, ?, ?, 'full', ?, ?)""",
        (
            app_id,
            name,
            name.lower().replace(" ", "-"),
            "fake_hash",
            retention_degrade_to_text_days,
            retention_degrade_to_preview_days,
        ),
    )
    await db.commit()
    return app_id


async def _insert_email(
    app_id: str,
    logged_at: datetime | None = None,
    body_html: str | None = "<h1>Hello</h1><p>World</p>",
    body_text: str | None = "Hello World",
    body_preview: str | None = "Hello World",
    body_size_bytes: int | None = None,
    subject: str = "Test",
) -> str:
    """Insert an email with body fields and return its id."""
    db = await get_db()
    email_id = str(uuid.uuid4())
    now = logged_at or datetime.now(UTC)

    if body_size_bytes is None:
        body_size_bytes = 0
        if body_html:
            body_size_bytes += len(body_html.encode("utf-8"))
        if body_text:
            body_size_bytes += len(body_text.encode("utf-8"))

    await db.execute(
        """INSERT INTO emails (id, app_id, to_addresses, from_address, subject,
           body_html, body_text, body_preview, body_size_bytes,
           status, ingest_method, logged_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sent', 'api', ?, ?)""",
        (
            email_id,
            app_id,
            '["user@example.com"]',
            "from@example.com",
            subject,
            body_html,
            body_text,
            body_preview,
            body_size_bytes,
            now.isoformat(),
            now.isoformat(),
        ),
    )
    await db.commit()
    return email_id


async def _get_email(email_id: str) -> dict:
    """Fetch an email row as a dict."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, body_html, body_text, body_preview, body_size_bytes FROM emails WHERE id = ?",
        (email_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    return dict(row)


# ---------------------------------------------------------------------------
# _effective_degrade_days helper
# ---------------------------------------------------------------------------


def test_effective_degrade_days_both_disabled():
    """When both global and app are 0, result is 0 (disabled)."""
    assert _effective_degrade_days(None, 0) == 0
    assert _effective_degrade_days(0, 0) == 0


def test_effective_degrade_days_global_only():
    """When only global is set, use global value."""
    assert _effective_degrade_days(None, 30) == 30
    assert _effective_degrade_days(0, 30) == 30


def test_effective_degrade_days_app_only():
    """When only app is set, use app value (even if global is disabled)."""
    assert _effective_degrade_days(30, 0) == 30


def test_effective_degrade_days_both_set_app_stricter():
    """When both are set, the smaller (sooner) value wins."""
    assert _effective_degrade_days(15, 30) == 15


def test_effective_degrade_days_both_set_global_stricter():
    """When global is smaller, global wins."""
    assert _effective_degrade_days(60, 30) == 30


def test_effective_degrade_days_both_equal():
    """When both are equal, return that value."""
    assert _effective_degrade_days(30, 30) == 30


# ---------------------------------------------------------------------------
# degrade_to_text (full → text_only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_degrade_to_text_strips_html():
    """Old emails with HTML should have body_html set to NULL."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=60),
        body_html="<h1>Hello</h1><p>World</p>",
        body_text="Hello World",
        body_preview="Hello World",
    )

    cutoff = (now - timedelta(days=30)).isoformat()
    degraded = await degrade_to_text(app_id, cutoff)
    assert degraded == 1

    email = await _get_email(email_id)
    assert email["body_html"] is None
    assert email["body_text"] == "Hello World"
    assert email["body_preview"] == "Hello World"
    # body_size_bytes should only reflect body_text now
    assert email["body_size_bytes"] == len(b"Hello World")


@pytest.mark.asyncio
async def test_degrade_to_text_generates_text_from_html():
    """When body_text is NULL, it should be generated from HTML before stripping."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=60),
        body_html="<h1>Hello</h1><p>World</p>",
        body_text=None,
        body_preview="Hello World",
    )

    cutoff = (now - timedelta(days=30)).isoformat()
    degraded = await degrade_to_text(app_id, cutoff)
    assert degraded == 1

    email = await _get_email(email_id)
    assert email["body_html"] is None
    assert email["body_text"] is not None
    assert "Hello" in email["body_text"]
    assert "World" in email["body_text"]


@pytest.mark.asyncio
async def test_degrade_to_text_skips_recent_emails():
    """Emails newer than the cutoff should not be degraded."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    # Old email (should be degraded)
    old_id = await _insert_email(app_id, logged_at=now - timedelta(days=60))
    # Recent email (should NOT be degraded)
    new_id = await _insert_email(app_id, logged_at=now - timedelta(days=5))

    cutoff = (now - timedelta(days=30)).isoformat()
    degraded = await degrade_to_text(app_id, cutoff)
    assert degraded == 1

    old_email = await _get_email(old_id)
    assert old_email["body_html"] is None

    new_email = await _get_email(new_id)
    assert new_email["body_html"] is not None


@pytest.mark.asyncio
async def test_degrade_to_text_skips_already_degraded():
    """Emails that already have body_html=NULL should not be touched."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    await _insert_email(
        app_id,
        logged_at=now - timedelta(days=60),
        body_html=None,
        body_text="Just text",
        body_preview="Just text",
    )

    cutoff = (now - timedelta(days=30)).isoformat()
    degraded = await degrade_to_text(app_id, cutoff)
    assert degraded == 0


@pytest.mark.asyncio
async def test_degrade_to_text_generates_preview():
    """When body_preview is NULL, it should be generated during degradation."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=60),
        body_html="<p>Some content here</p>",
        body_text="Some content here",
        body_preview=None,
    )

    cutoff = (now - timedelta(days=30)).isoformat()
    await degrade_to_text(app_id, cutoff)

    email = await _get_email(email_id)
    assert email["body_preview"] is not None
    assert "Some content" in email["body_preview"]


# ---------------------------------------------------------------------------
# degrade_to_preview (text_only → preview)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_degrade_to_preview_strips_text():
    """Old emails with body_text should have it set to NULL."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html=None,
        body_text="Full text content that is quite long",
        body_preview="Full text content",
    )

    cutoff = (now - timedelta(days=90)).isoformat()
    degraded = await degrade_to_preview(app_id, cutoff)
    assert degraded == 1

    email = await _get_email(email_id)
    assert email["body_html"] is None
    assert email["body_text"] is None
    assert email["body_preview"] == "Full text content"
    assert email["body_size_bytes"] == len(b"Full text content")


@pytest.mark.asyncio
async def test_degrade_to_preview_strips_both_html_and_text():
    """If an email still has both HTML and text, preview degradation strips both."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html="<p>HTML body</p>",
        body_text="Text body",
        body_preview="Text body",
    )

    cutoff = (now - timedelta(days=90)).isoformat()
    degraded = await degrade_to_preview(app_id, cutoff)
    assert degraded == 1

    email = await _get_email(email_id)
    assert email["body_html"] is None
    assert email["body_text"] is None
    assert email["body_preview"] == "Text body"


@pytest.mark.asyncio
async def test_degrade_to_preview_generates_preview_from_text():
    """When body_preview is NULL, generate it from body_text before stripping."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    long_text = "A" * 600
    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html=None,
        body_text=long_text,
        body_preview=None,
    )

    cutoff = (now - timedelta(days=90)).isoformat()
    await degrade_to_preview(app_id, cutoff)

    email = await _get_email(email_id)
    assert email["body_text"] is None
    assert email["body_preview"] is not None
    assert len(email["body_preview"]) == 500  # Truncated to 500 chars


@pytest.mark.asyncio
async def test_degrade_to_preview_generates_preview_from_html():
    """When only HTML exists and no preview, generate preview from HTML."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html="<p>HTML only content</p>",
        body_text=None,
        body_preview=None,
    )

    cutoff = (now - timedelta(days=90)).isoformat()
    await degrade_to_preview(app_id, cutoff)

    email = await _get_email(email_id)
    assert email["body_html"] is None
    assert email["body_text"] is None
    assert email["body_preview"] is not None
    assert "HTML only content" in email["body_preview"]


@pytest.mark.asyncio
async def test_degrade_to_preview_skips_already_degraded():
    """Emails with only preview (no text or html) should not be touched."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html=None,
        body_text=None,
        body_preview="Preview only",
    )

    cutoff = (now - timedelta(days=90)).isoformat()
    degraded = await degrade_to_preview(app_id, cutoff)
    assert degraded == 0


@pytest.mark.asyncio
async def test_degrade_to_preview_skips_recent_emails():
    """Emails newer than the cutoff should not be degraded."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    old_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html=None,
        body_text="Old text",
    )
    new_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=5),
        body_html=None,
        body_text="New text",
    )

    cutoff = (now - timedelta(days=90)).isoformat()
    degraded = await degrade_to_preview(app_id, cutoff)
    assert degraded == 1

    old_email = await _get_email(old_id)
    assert old_email["body_text"] is None

    new_email = await _get_email(new_id)
    assert new_email["body_text"] == "New text"


# ---------------------------------------------------------------------------
# Graduated degradation (full → text → preview via run_cleanup)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_cleanup_graduated_degradation(monkeypatch):
    """run_cleanup applies both text and preview degradation in sequence."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 10000)
    monkeypatch.setattr(settings, "retention_max_age_days", 365)
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)
    monkeypatch.setattr(settings, "retention_degrade_to_text_days", 30)
    monkeypatch.setattr(settings, "retention_degrade_to_preview_days", 90)

    app_id = await _create_app()
    now = datetime.now(UTC)

    # Recent email (< 30 days) — should remain full
    recent_id = await _insert_email(app_id, logged_at=now - timedelta(days=5))
    # Medium email (30-90 days) — should degrade to text_only
    medium_id = await _insert_email(app_id, logged_at=now - timedelta(days=60))
    # Old email (> 90 days) — should degrade to preview
    old_id = await _insert_email(app_id, logged_at=now - timedelta(days=120))

    await run_cleanup()

    recent = await _get_email(recent_id)
    assert recent["body_html"] is not None
    assert recent["body_text"] is not None

    medium = await _get_email(medium_id)
    assert medium["body_html"] is None
    assert medium["body_text"] is not None
    assert medium["body_preview"] is not None

    old = await _get_email(old_id)
    assert old["body_html"] is None
    assert old["body_text"] is None
    assert old["body_preview"] is not None


@pytest.mark.asyncio
async def test_run_cleanup_degradation_disabled_by_default(monkeypatch):
    """With default config (0), no degradation should occur."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 10000)
    monkeypatch.setattr(settings, "retention_max_age_days", 9999)
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)
    monkeypatch.setattr(settings, "retention_degrade_to_text_days", 0)
    monkeypatch.setattr(settings, "retention_degrade_to_preview_days", 0)

    app_id = await _create_app()
    now = datetime.now(UTC)

    email_id = await _insert_email(app_id, logged_at=now - timedelta(days=365))

    await run_cleanup()

    email = await _get_email(email_id)
    assert email["body_html"] is not None
    assert email["body_text"] is not None


@pytest.mark.asyncio
async def test_run_cleanup_per_app_override_enables_degradation(monkeypatch):
    """Per-app override can enable degradation even if global is disabled."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 10000)
    monkeypatch.setattr(settings, "retention_max_age_days", 365)
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)
    monkeypatch.setattr(settings, "retention_degrade_to_text_days", 0)
    monkeypatch.setattr(settings, "retention_degrade_to_preview_days", 0)

    # App with per-app override
    app_id = await _create_app(retention_degrade_to_text_days=30)
    now = datetime.now(UTC)

    email_id = await _insert_email(app_id, logged_at=now - timedelta(days=60))

    await run_cleanup()

    email = await _get_email(email_id)
    assert email["body_html"] is None
    assert email["body_text"] is not None


@pytest.mark.asyncio
async def test_run_cleanup_per_app_override_stricter(monkeypatch):
    """Per-app override that is stricter (smaller) than global should win."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 10000)
    monkeypatch.setattr(settings, "retention_max_age_days", 365)
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)
    monkeypatch.setattr(settings, "retention_degrade_to_text_days", 60)
    monkeypatch.setattr(settings, "retention_degrade_to_preview_days", 0)

    # App with stricter override (degrade after 15 days instead of 60)
    app_id = await _create_app(retention_degrade_to_text_days=15)
    now = datetime.now(UTC)

    # 20 days old — global says keep, app says degrade
    email_id = await _insert_email(app_id, logged_at=now - timedelta(days=20))

    await run_cleanup()

    email = await _get_email(email_id)
    assert email["body_html"] is None  # Degraded by app override


@pytest.mark.asyncio
async def test_run_cleanup_multiple_apps_independent_degradation(monkeypatch):
    """Degradation processes each app independently."""
    await init_db()
    monkeypatch.setattr(settings, "retention_max_count", 10000)
    monkeypatch.setattr(settings, "retention_max_age_days", 365)
    monkeypatch.setattr(settings, "retention_max_storage_mb", 500)
    monkeypatch.setattr(settings, "retention_degrade_to_text_days", 0)
    monkeypatch.setattr(settings, "retention_degrade_to_preview_days", 0)

    # App 1: has per-app degradation enabled
    app1_id = await _create_app(name="App One", retention_degrade_to_text_days=30)
    # App 2: no degradation
    app2_id = await _create_app(name="App Two")

    now = datetime.now(UTC)
    email1_id = await _insert_email(app1_id, logged_at=now - timedelta(days=60))
    email2_id = await _insert_email(app2_id, logged_at=now - timedelta(days=60))

    await run_cleanup()

    email1 = await _get_email(email1_id)
    assert email1["body_html"] is None  # Degraded

    email2 = await _get_email(email2_id)
    assert email2["body_html"] is not None  # Not degraded


# ---------------------------------------------------------------------------
# FTS5 consistency after degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fts_index_updated_after_text_degradation():
    """FTS5 index should reflect body_text changes after degradation."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    # Email with unique text in body_text
    await _insert_email(
        app_id,
        logged_at=now - timedelta(days=60),
        body_html="<p>UniqueHTMLContent</p>",
        body_text="UniqueTextContent",
        body_preview="UniqueTextContent",
    )

    db = await get_db()

    # Verify body_text is searchable before degradation
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?",
        ("UniqueTextContent",),
    )
    assert (await cursor.fetchone())[0] == 1

    # Degrade to text (body_html removed, body_text preserved)
    cutoff = (now - timedelta(days=30)).isoformat()
    await degrade_to_text(app_id, cutoff)

    # body_text should still be searchable
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?",
        ("UniqueTextContent",),
    )
    assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_fts_index_updated_after_preview_degradation():
    """FTS5 index should be updated when body_text is removed by preview degradation."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html=None,
        body_text="SearchableBodyText",
        body_preview="SearchablePrev",
    )

    db = await get_db()

    # Verify body_text is searchable before degradation
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?",
        ("SearchableBodyText",),
    )
    assert (await cursor.fetchone())[0] == 1

    # Degrade to preview (body_text removed)
    cutoff = (now - timedelta(days=90)).isoformat()
    await degrade_to_preview(app_id, cutoff)

    # body_text no longer searchable (it was removed)
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?",
        ("SearchableBodyText",),
    )
    assert (await cursor.fetchone())[0] == 0

    # body_preview should still be searchable
    cursor = await db.execute(
        "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH ?",
        ("SearchablePrev",),
    )
    assert (await cursor.fetchone())[0] == 1


# ---------------------------------------------------------------------------
# body_size_bytes accuracy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_size_bytes_updated_after_text_degradation():
    """body_size_bytes should reflect only remaining content after degradation."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    html = "<h1>Big HTML Content</h1>" * 100
    text = "Small text"
    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=60),
        body_html=html,
        body_text=text,
    )

    original = await _get_email(email_id)
    original_size = original["body_size_bytes"]

    cutoff = (now - timedelta(days=30)).isoformat()
    await degrade_to_text(app_id, cutoff)

    degraded = await _get_email(email_id)
    assert degraded["body_size_bytes"] == len(text.encode("utf-8"))
    assert degraded["body_size_bytes"] < original_size


@pytest.mark.asyncio
async def test_body_size_bytes_updated_after_preview_degradation():
    """body_size_bytes should reflect only preview content after degradation."""
    await init_db()
    app_id = await _create_app()
    now = datetime.now(UTC)

    text = "Long text content " * 50
    preview = text[:500]
    email_id = await _insert_email(
        app_id,
        logged_at=now - timedelta(days=120),
        body_html=None,
        body_text=text,
        body_preview=preview,
    )

    cutoff = (now - timedelta(days=90)).isoformat()
    await degrade_to_preview(app_id, cutoff)

    degraded = await _get_email(email_id)
    assert degraded["body_size_bytes"] == len(preview.encode("utf-8"))
