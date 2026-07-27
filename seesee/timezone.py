"""Timezone utilities for SeeSee.

All dates are stored in UTC. The SEESEE_DISPLAY_TIMEZONE setting controls how
dates are shown in admin views. API responses always use UTC ISO 8601.

Usage:
    from seesee.timezone import utc_now, utc_now_iso, format_for_display

    # Storage — always UTC
    now_iso = utc_now_iso()          # "2025-02-20T14:30:45"
    dt_iso = utc_iso(some_datetime)  # same format

    # Admin display
    formatted = format_for_display("2025-02-20T14:30:45")  # "Feb 20, 2025 8:30 AM CST"
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from seesee.config import settings


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string for storage.

    Format: YYYY-MM-DDTHH:MM:SS — no microseconds, no offset suffix.
    This is consistent across all storage paths and allows correct
    lexicographic comparison in SQLite queries.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def utc_iso(dt: datetime) -> str:
    """Convert a datetime to a consistent ISO string for storage.

    If the datetime is naive (no tzinfo), it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def utc_cutoff_iso(days_ago: int) -> str:
    """Return a UTC ISO string for N days ago.

    Used for time-window queries (e.g., "last 24 hours", "last 30 days")
    and retention cutoffs.
    """
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def iso_in_days(days: int) -> str:
    """Return a UTC ISO string for N days from now (key expiry)."""
    return (datetime.now(tz=UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def get_display_tz() -> ZoneInfo:
    """Get the configured display timezone, falling back to UTC.

    Reads from settings.display_timezone (env: SEESEE_DISPLAY_TIMEZONE).
    """
    tz_name = settings.display_timezone
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        return ZoneInfo("UTC")


def format_for_display(
    iso_string: str,
    fmt: str = "%b %-d, %Y %-I:%M %p %Z",
) -> str:
    """Format a UTC ISO timestamp string for display in the admin timezone.

    Args:
        iso_string: UTC timestamp in ISO 8601 format (as stored in the DB).
        fmt: strftime format string. Default: "Feb 20, 2025 2:30 PM CST".

    Returns:
        The formatted string in the display timezone, or the original string
        on parse failure.
    """
    try:
        dt = _parse_stored_iso(iso_string)
        display_tz = get_display_tz()
        return dt.astimezone(display_tz).strftime(fmt)
    except (ValueError, TypeError, OSError):
        return iso_string


def display_now() -> datetime:
    """Return the current time in the display timezone (timezone-aware)."""
    return datetime.now(get_display_tz())


def display_day_start_utc(date_offset_days: int = 0) -> str:
    """Return the UTC timestamp for the start of a display-timezone day.

    Args:
        date_offset_days: 0 for today, -1 for yesterday, etc.

    Returns:
        ISO string in UTC representing midnight of the target day
        in the display timezone.
    """
    tz = get_display_tz()
    now_local = datetime.now(tz)
    target_date = (now_local + timedelta(days=date_offset_days)).date()
    local_midnight = datetime(target_date.year, target_date.month, target_date.day, tzinfo=tz)
    return utc_iso(local_midnight)


def _parse_stored_iso(iso_string: str) -> datetime:
    """Parse an ISO 8601 string from storage into a UTC-aware datetime.

    Handles formats produced by both Python's isoformat() and our
    standardized storage format:
    - "2025-02-20T14:30:45"            (no offset — assumed UTC)
    - "2025-02-20T14:30:45+00:00"      (explicit UTC offset)
    - "2025-02-20T14:30:45.123456+00:00" (with microseconds)
    - "2025-02-20 14:30:45"            (SQLite format — space separator)
    """
    s = iso_string.strip()

    # Python 3.11+ fromisoformat handles Z and offsets
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # Replace space separator with T for fromisoformat compatibility
    if len(s) >= 11 and s[10] == " ":
        s = s[:10] + "T" + s[11:]

    dt = datetime.fromisoformat(s)

    # If naive (no offset), assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt
