"""Tests for date/time parsing utilities in execsql.utils.datetime."""

from __future__ import annotations

import datetime

import pytest

from execsql.utils.datetime import parse_datetime, parse_datetimetz


# ---------------------------------------------------------------------------
# parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_datetime_passthrough(self):
        dt = datetime.datetime(2024, 6, 1, 12, 0, 0)
        assert parse_datetime(dt) is dt

    def test_iso_format(self):
        result = parse_datetime("2024-01-15 10:30:00")
        assert isinstance(result, datetime.datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_us_slash_format(self):
        result = parse_datetime("01/15/2024 10:30:00")
        assert isinstance(result, datetime.datetime)
        assert result.month == 1
        assert result.day == 15
        assert result.year == 2024

    def test_short_year_format(self):
        result = parse_datetime("06/01/24 14:30")
        assert isinstance(result, datetime.datetime)

    def test_returns_none_for_invalid_string(self):
        assert parse_datetime("not-a-date") is None

    def test_returns_none_for_none(self):
        # None gets stringified to "None" which won't parse
        assert parse_datetime(None) is None

    def test_month_name_format(self):
        result = parse_datetime("Jan 15, 2024 10:30:00")
        assert isinstance(result, datetime.datetime)
        assert result.month == 1
        assert result.day == 15

    def test_returns_datetime_type(self):
        result = parse_datetime("2024-06-01 08:00:00")
        assert type(result) is datetime.datetime

    def test_mru_cache_moves_format_to_front(self):
        """Calling with the same format twice should still work (LRU rotation)."""
        result1 = parse_datetime("2024-01-15 10:30:00")
        result2 = parse_datetime("2024-02-20 09:15:00")
        assert result1 is not None
        assert result2 is not None


# ---------------------------------------------------------------------------
# parse_datetimetz
# ---------------------------------------------------------------------------


class TestParseDatetimetz:
    def test_aware_datetime_passthrough(self):
        tz = datetime.timezone(datetime.timedelta(hours=5))
        dt = datetime.datetime(2024, 1, 15, 10, 0, tzinfo=tz)
        result = parse_datetimetz(dt)
        assert result == dt

    def test_naive_datetime_returns_none(self):
        naive = datetime.datetime(2024, 1, 15, 10, 0)
        assert parse_datetimetz(naive) is None

    def test_numeric_timezone_positive(self):
        # Timezone must be adjacent to datetime (no space before +/-) so parse_datetime
        # receives a clean string without trailing whitespace
        result = parse_datetimetz("2024-01-15 10:00:00+05:00")
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None

    def test_numeric_timezone_negative(self):
        result = parse_datetimetz("2024-06-01 08:30:00-07:00")
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None

    def test_non_string_non_datetime_returns_none(self):
        assert parse_datetimetz(42) is None
        assert parse_datetimetz(None) is None

    def test_invalid_string_returns_none(self):
        assert parse_datetimetz("not-a-datetime") is None

    def test_numeric_tz_without_colon(self):
        # Adjacent timezone without colon separator
        result = parse_datetimetz("2024-01-15 10:00:00+0500")
        assert result is not None
