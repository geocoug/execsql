from __future__ import annotations

"""
Date and time parsing utilities for execsql.

Provides :func:`parse_datetime` and :func:`parse_datetimetz` that convert
raw string data into Python :class:`datetime.datetime` objects.  Used by
:class:`~execsql.types.DT_Timestamp`, :class:`~execsql.types.DT_TimestampTZ`,
and related data-type classes when scanning imported data for type inference.

Delegates to ``dateutil.parser.parse()`` for robust, format-agnostic parsing,
but only accepts a full date: the year written out and nothing filled in from
today's date.  ``1-2``, ``5/6`` and ``March 5`` are not timestamps.
"""

import datetime
import re
from typing import Any, cast

from dateutil import parser as _dateutil_parser

__all__ = ["parse_datetime", "parse_datetimetz"]

# Reject strings that are purely numeric (with optional decimal point or
# sign).  dateutil aggressively parses bare numbers like "1", "42", "2024"
# as dates, which breaks type inference — a column of integers would be
# misidentified as timestamps.
_NUMERIC_ONLY = re.compile(r"^[+-]?\d+\.?\d*$")

# Match time-only strings like "13:15:45", "9:30", "1:15:45.123", "09:30 AM".
# dateutil parses these by filling in today's date, which causes DT_Timestamp
# to claim the column before DT_Time gets a chance.
_TIME_ONLY = re.compile(r"^\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:[AaPp][Mm])?$")


def _looks_numeric(s: str) -> bool:
    """Return True if *s* is a bare number that should not be parsed as a date."""
    return bool(_NUMERIC_ONLY.match(s.strip()))


def _looks_time_only(s: str) -> bool:
    """Return True if *s* is a time-only string (no date component)."""
    return bool(_TIME_ONLY.match(s.strip()))


# A year must be written out: four digits, or a two-digit year in the
# month-first m/d/yy or m-d-yy form.  Without this, dateutil reads "1 2 3" as
# 2003-01-02 and "3.5.7" as 2007-03-05.
_FULL_YEAR = re.compile(r"(?<!\d)\d{4}(?!\d)")
_SHORT_YEAR = re.compile(r"^\s*(?P<month>\d{1,2})(?P<sep>[/-])\d{1,2}(?P=sep)\d{2}(?!\d)")

# dateutil fills fields missing from the string from its ``default``.  Two
# defaults that differ in year, month and day expose any such filled-in field:
# the two parses then disagree.
_DEFAULT_A = datetime.datetime(2001, 1, 1)
_DEFAULT_B = datetime.datetime(2002, 2, 2)


def _parse(datestr: str, strict: bool) -> datetime.datetime | None:
    """Parse *datestr* with dateutil; when *strict*, only a fully written date."""
    try:
        if not strict:
            return cast(datetime.datetime, _dateutil_parser.parse(datestr))
        if not _FULL_YEAR.search(datestr):
            short = _SHORT_YEAR.match(datestr)
            # Month first only: dateutil would read 13-05-24 day-first,
            # giving one column two conventions.
            if short is None or int(short["month"]) > 12:
                return None
        a = cast(datetime.datetime, _dateutil_parser.parse(datestr, default=_DEFAULT_A))
        b = cast(datetime.datetime, _dateutil_parser.parse(datestr, default=_DEFAULT_B))
    except (ValueError, OverflowError, TypeError):
        return None
    if (a.year, a.month, a.day) != (b.year, b.month, b.day):
        return None
    return a


def parse_datetime(datestr: Any, *, strict: bool = True) -> datetime.datetime | None:
    """Parse a date/time string into a :class:`datetime.datetime`.

    Accepts formats recognised by ``dateutil.parser.parse()``, including
    ISO 8601, US date formats (month-first), European formats, and month
    names.  Returns ``None`` if the input cannot be parsed.

    With *strict* (the default, used for type inference and import), the
    string must give a full date: a four-digit year (or month-first
    ``m/d/yy`` / ``m-d-yy``) and a month and day, none filled in from
    today's date.  ``"1-2"``, ``"5/6"``,
    ``"March 5"`` and ``"Monday"`` return ``None``.  Pass ``strict=False``
    for a date a user typed into a metacommand, where today's date is a
    reasonable default.

    Bare numeric strings (e.g. ``"1"``, ``"42"``, ``"2024"``) and time-only
    strings are always rejected to prevent type-inference false positives.

    If *datestr* is already a :class:`datetime.datetime`, it is returned as-is.
    Non-string inputs are stringified before parsing.
    """
    if isinstance(datestr, datetime.datetime):
        return datestr
    if not isinstance(datestr, str):
        try:
            datestr = str(datestr)
        except Exception:
            return None
    if _looks_numeric(datestr):
        return None
    if _looks_time_only(datestr):
        return None
    return _parse(datestr, strict)


def parse_datetimetz(data: Any) -> datetime.datetime | None:
    """Parse a timezone-aware date/time string into a :class:`datetime.datetime`.

    Returns ``None`` if the input cannot be parsed or if the result is
    timezone-naive (no ``tzinfo``).  Accepts numeric offsets (``+05:00``,
    ``-0700``) and named timezones (``UTC``, ``EST``, etc.).

    If *data* is already a timezone-aware :class:`datetime.datetime`, it is
    returned as-is.  Naive datetimes return ``None``.  Like
    :func:`parse_datetime`, only a full date is accepted.
    """
    if isinstance(data, datetime.datetime):
        if data.tzinfo is None or data.tzinfo.utcoffset(data) is None:
            return None
        return data
    if not isinstance(data, str):
        return None
    if _looks_numeric(data):
        return None
    dt = _parse(data, strict=True)
    if dt is None or dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return None
    return dt
