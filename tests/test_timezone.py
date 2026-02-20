"""Tests for timezone utilities and consistent timestamp handling."""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from seesee.timezone import (
    _parse_stored_iso,
    display_day_start_utc,
    format_for_display,
    get_display_tz,
    utc_cutoff_iso,
    utc_iso,
    utc_now,
    utc_now_iso,
)


class TestUtcNow:
    def test_returns_utc_aware_datetime(self):
        dt = utc_now()
        assert dt.tzinfo is not None
        assert dt.tzinfo == UTC

    def test_returns_current_time(self):
        before = datetime.now(UTC)
        dt = utc_now()
        after = datetime.now(UTC)
        assert before <= dt <= after


class TestUtcNowIso:
    def test_format_is_consistent(self):
        result = utc_now_iso()
        # Format: YYYY-MM-DDTHH:MM:SS (exactly 19 chars, no offset, no microseconds)
        assert len(result) == 19
        assert result[4] == "-"
        assert result[7] == "-"
        assert result[10] == "T"
        assert result[13] == ":"
        assert result[16] == ":"

    def test_no_offset_suffix(self):
        result = utc_now_iso()
        assert "+" not in result
        assert "Z" not in result

    def test_no_microseconds(self):
        result = utc_now_iso()
        assert "." not in result


class TestUtcIso:
    def test_utc_aware_datetime(self):
        dt = datetime(2025, 2, 20, 14, 30, 45, tzinfo=UTC)
        assert utc_iso(dt) == "2025-02-20T14:30:45"

    def test_naive_datetime_assumed_utc(self):
        dt = datetime(2025, 2, 20, 14, 30, 45)
        assert utc_iso(dt) == "2025-02-20T14:30:45"

    def test_non_utc_timezone_converts(self):
        # America/Chicago is UTC-6 (or UTC-5 during DST)
        chicago = ZoneInfo("America/Chicago")
        # Jan 15 is CST (UTC-6), so 2 PM CST = 8 PM UTC
        dt = datetime(2025, 1, 15, 14, 0, 0, tzinfo=chicago)
        result = utc_iso(dt)
        assert result == "2025-01-15T20:00:00"

    def test_non_hour_offset_timezone(self):
        # Asia/Kolkata is UTC+5:30
        kolkata = ZoneInfo("Asia/Kolkata")
        dt = datetime(2025, 2, 20, 15, 30, 0, tzinfo=kolkata)
        result = utc_iso(dt)
        assert result == "2025-02-20T10:00:00"

    def test_strips_microseconds(self):
        dt = datetime(2025, 2, 20, 14, 30, 45, 123456, tzinfo=UTC)
        result = utc_iso(dt)
        assert result == "2025-02-20T14:30:45"
        assert "." not in result


class TestUtcCutoffIso:
    def test_cutoff_1_day(self):
        result = utc_cutoff_iso(1)
        expected_approx = datetime.now(UTC) - timedelta(days=1)
        # Parse back and verify it's within a second of expected
        parsed = datetime.fromisoformat(result).replace(tzinfo=UTC)
        assert abs((parsed - expected_approx).total_seconds()) < 2

    def test_cutoff_30_days(self):
        result = utc_cutoff_iso(30)
        expected_approx = datetime.now(UTC) - timedelta(days=30)
        parsed = datetime.fromisoformat(result).replace(tzinfo=UTC)
        assert abs((parsed - expected_approx).total_seconds()) < 2

    def test_format_consistent(self):
        result = utc_cutoff_iso(7)
        assert len(result) == 19
        assert "+" not in result
        assert "." not in result


class TestGetDisplayTz:
    def test_default_is_utc(self):
        tz = get_display_tz()
        assert str(tz) == "UTC"

    def test_valid_timezone(self, monkeypatch):
        from seesee.config import settings

        monkeypatch.setattr(settings, "display_timezone", "America/Chicago")
        tz = get_display_tz()
        assert str(tz) == "America/Chicago"

    def test_invalid_timezone_falls_back_to_utc(self, monkeypatch):
        from seesee.config import settings

        monkeypatch.setattr(settings, "display_timezone", "Invalid/Timezone")
        tz = get_display_tz()
        assert str(tz) == "UTC"


class TestFormatForDisplay:
    def test_utc_default(self):
        result = format_for_display("2025-02-20T14:30:45")
        assert "2025" in result
        assert "UTC" in result

    def test_with_chicago_timezone(self, monkeypatch):
        from seesee.config import settings

        monkeypatch.setattr(settings, "display_timezone", "America/Chicago")
        result = format_for_display("2025-02-20T14:30:45")
        # Feb 20, 2025 at 14:30 UTC = 8:30 AM CST
        assert "8:30" in result or "8:30" in result.replace("\u202f", " ")
        assert "CST" in result

    def test_with_kolkata_timezone(self, monkeypatch):
        from seesee.config import settings

        monkeypatch.setattr(settings, "display_timezone", "Asia/Kolkata")
        result = format_for_display("2025-02-20T14:30:45")
        # 14:30 UTC = 20:00 IST
        assert "8:00" in result or "8:00" in result.replace("\u202f", " ")
        assert "IST" in result

    def test_handles_old_isoformat_with_offset(self):
        # Handle legacy timestamps stored with +00:00 suffix
        result = format_for_display("2025-02-20T14:30:45.123456+00:00")
        assert "2025" in result

    def test_handles_sqlite_format(self):
        # Handle SQLite datetime() format (space separator)
        result = format_for_display("2025-02-20 14:30:45")
        assert "2025" in result

    def test_invalid_string_returns_original(self):
        result = format_for_display("not-a-date")
        assert result == "not-a-date"

    def test_empty_string_returns_original(self):
        result = format_for_display("")
        assert result == ""


class TestDisplayDayStartUtc:
    def test_today_in_utc_is_midnight_utc(self):
        result = display_day_start_utc(0)
        parsed = datetime.fromisoformat(result).replace(tzinfo=UTC)
        assert parsed.hour == 0
        assert parsed.minute == 0
        assert parsed.second == 0
        assert parsed.date() == datetime.now(UTC).date()

    def test_today_in_chicago(self, monkeypatch):
        from seesee.config import settings

        monkeypatch.setattr(settings, "display_timezone", "America/Chicago")
        result = display_day_start_utc(0)
        parsed = datetime.fromisoformat(result).replace(tzinfo=UTC)
        # Chicago midnight in UTC should be 06:00 (CST) or 05:00 (CDT)
        assert parsed.hour in (5, 6)

    def test_yesterday(self):
        result_today = display_day_start_utc(0)
        result_yesterday = display_day_start_utc(-1)
        today = datetime.fromisoformat(result_today).replace(tzinfo=UTC)
        yesterday = datetime.fromisoformat(result_yesterday).replace(tzinfo=UTC)
        assert (today - yesterday).days == 1


class TestParseStoredIso:
    def test_standard_format(self):
        dt = _parse_stored_iso("2025-02-20T14:30:45")
        assert dt.year == 2025
        assert dt.month == 2
        assert dt.day == 20
        assert dt.hour == 14
        assert dt.minute == 30
        assert dt.second == 45
        assert dt.tzinfo == UTC

    def test_with_offset(self):
        dt = _parse_stored_iso("2025-02-20T14:30:45+00:00")
        assert dt.hour == 14
        assert dt.tzinfo is not None

    def test_with_microseconds_and_offset(self):
        dt = _parse_stored_iso("2025-02-20T14:30:45.123456+00:00")
        assert dt.hour == 14
        assert dt.microsecond == 123456

    def test_sqlite_space_separator(self):
        dt = _parse_stored_iso("2025-02-20 14:30:45")
        assert dt.hour == 14
        assert dt.tzinfo == UTC

    def test_with_z_suffix(self):
        dt = _parse_stored_iso("2025-02-20T14:30:45Z")
        assert dt.hour == 14
        assert dt.tzinfo is not None

    def test_whitespace_stripped(self):
        dt = _parse_stored_iso("  2025-02-20T14:30:45  ")
        assert dt.hour == 14


class TestTimestampFormatConsistency:
    """Verify that the standardized format allows correct lexicographic comparisons."""

    def test_utc_now_iso_sorts_correctly(self):
        """Two consecutive calls should produce sortable strings."""
        t1 = utc_now_iso()
        # Simulate a later time
        later = (datetime.now(UTC) + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
        assert t1 <= later

    def test_cutoff_compares_correctly_with_stored(self):
        """Cutoff strings should compare correctly with stored timestamps."""
        stored = "2025-02-20T14:30:45"  # An email logged at this time
        cutoff_before = "2025-02-20T14:00:00"  # 30 min before the email
        cutoff_after = "2025-02-20T15:00:00"  # 30 min after the email

        # stored >= cutoff_before should be True (email is within window)
        assert stored >= cutoff_before
        # stored >= cutoff_after should be False (email is outside window)
        assert not (stored >= cutoff_after)

    def test_no_format_mismatch_with_old_data(self):
        """Old-format timestamps (with +00:00) should still sort correctly
        when compared to new-format timestamps, as long as the date portion differs."""
        old_format = "2025-02-19T14:30:45.123456+00:00"
        new_format = "2025-02-20T14:30:45"

        # Different dates: old < new regardless of format suffix
        assert old_format < new_format


class TestDstTransitions:
    """Test that timezone operations handle DST transitions correctly."""

    def test_chicago_cst_to_cdt_transition(self, monkeypatch):
        """Verify display formatting works around Chicago's DST spring-forward."""
        from seesee.config import settings

        monkeypatch.setattr(settings, "display_timezone", "America/Chicago")

        # 2025-03-09 is spring-forward day in US (2 AM CST -> 3 AM CDT)
        # 07:30 UTC on that day = 1:30 AM CST (before transition)
        before = format_for_display("2025-03-09T07:30:00")
        assert "CST" in before

        # 08:30 UTC = 3:30 AM CDT (after transition)
        after = format_for_display("2025-03-09T08:30:00")
        assert "CDT" in after

    def test_chatham_non_hour_offset(self, monkeypatch):
        """Pacific/Chatham is UTC+12:45 (or UTC+13:45 during DST)."""
        from seesee.config import settings

        monkeypatch.setattr(settings, "display_timezone", "Pacific/Chatham")
        result = format_for_display("2025-02-20T14:30:45")
        assert "2025" in result  # Should not crash
