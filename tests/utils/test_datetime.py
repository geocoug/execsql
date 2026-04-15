"""Tests for date/time parsing utilities in execsql.utils.datetime."""

from __future__ import annotations

import datetime

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

    def test_repeated_calls_work(self):
        """Calling with the same format twice should still work."""
        result1 = parse_datetime("2024-01-15 10:30:00")
        result2 = parse_datetime("2024-02-20 09:15:00")
        assert result1 is not None
        assert result2 is not None


class TestParseDatetimeExtended:
    """Tests for formats that dateutil handles beyond the old format list."""

    def test_iso8601_with_t_separator(self):
        result = parse_datetime("2024-01-15T10:30:00")
        assert isinstance(result, datetime.datetime)
        assert result.hour == 10
        assert result.minute == 30

    def test_iso8601_with_microseconds(self):
        result = parse_datetime("2024-01-15 10:30:00.123456")
        assert isinstance(result, datetime.datetime)
        assert result.microsecond == 123456

    def test_date_only_iso(self):
        result = parse_datetime("2024-01-15")
        assert isinstance(result, datetime.datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_date_only_us_slash(self):
        result = parse_datetime("01/15/2024")
        assert isinstance(result, datetime.datetime)
        assert result.month == 1

    def test_full_month_name(self):
        result = parse_datetime("January 15, 2024")
        assert isinstance(result, datetime.datetime)
        assert result.month == 1

    def test_abbreviated_month_with_period(self):
        result = parse_datetime("Jan. 15, 2024")
        assert isinstance(result, datetime.datetime)
        assert result.month == 1

    def test_day_month_year_european(self):
        result = parse_datetime("15 Jan 2024")
        assert isinstance(result, datetime.datetime)
        assert result.day == 15

    def test_am_pm_format(self):
        result = parse_datetime("01/15/2024 2:30 PM")
        assert isinstance(result, datetime.datetime)
        assert result.hour == 14
        assert result.minute == 30

    def test_bare_integer_string_rejected(self):
        """Bare numbers must not be parsed as dates (breaks type inference)."""
        assert parse_datetime("1") is None
        assert parse_datetime("42") is None
        assert parse_datetime("2024") is None

    def test_bare_float_string_rejected(self):
        assert parse_datetime("1.5") is None
        assert parse_datetime("3.14") is None

    def test_numeric_input_object_rejected(self):
        """Non-string numeric input gets stringified then rejected."""
        assert parse_datetime(20240115) is None

    def test_empty_string_returns_none(self):
        assert parse_datetime("") is None

    def test_time_only_strings_rejected(self):
        """Time-only values must not be parsed as timestamps (GH: type inference bug)."""
        assert parse_datetime("13:15:45") is None
        assert parse_datetime("9:30") is None
        assert parse_datetime("1:15:45.123") is None
        assert parse_datetime("09:30 AM") is None
        assert parse_datetime("11:00 pm") is None

    def test_datetime_with_time_still_parses(self):
        """Strings with both date and time components must still work."""
        result = parse_datetime("2026-02-25 13:15:45")
        assert isinstance(result, datetime.datetime)
        assert result.hour == 13
        assert result.minute == 15


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
        result = parse_datetimetz("2024-01-15 10:00:00+0500")
        assert result is not None
        assert result.tzinfo is not None


class TestParseDatetimetzExtended:
    """Tests for timezone-aware formats via dateutil."""

    def test_utc_suffix(self):
        result = parse_datetimetz("2024-01-15 10:00:00 UTC")
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None
        offset = result.tzinfo.utcoffset(result)
        assert offset == datetime.timedelta(0)

    def test_iso8601_z_suffix(self):
        result = parse_datetimetz("2024-01-15T10:00:00Z")
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None

    def test_naive_string_returns_none(self):
        """A datetime string without timezone info returns None."""
        result = parse_datetimetz("2024-01-15 10:00:00")
        assert result is None

    def test_negative_offset(self):
        result = parse_datetimetz("2024-06-01 12:00:00-05:00")
        assert result is not None
        offset = result.tzinfo.utcoffset(result)
        assert offset == datetime.timedelta(hours=-5)

    def test_positive_offset(self):
        result = parse_datetimetz("2024-06-01 12:00:00+09:30")
        assert result is not None
        offset = result.tzinfo.utcoffset(result)
        assert offset == datetime.timedelta(hours=9, minutes=30)
