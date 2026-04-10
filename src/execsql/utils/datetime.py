from __future__ import annotations

"""
Date and time parsing utilities for execsql.

Provides :func:`parse_datetime` and :func:`parse_datetimetz` that convert
raw string data into Python :class:`datetime.datetime` objects.  Used by
:class:`~execsql.types.DT_Timestamp`, :class:`~execsql.types.DT_TimestampTZ`,
and related data-type classes when scanning imported data for type inference.

Delegates to ``dateutil.parser.parse()`` for robust, format-agnostic parsing.
"""

import datetime
import re
from typing import Any

from dateutil import parser as _dateutil_parser

__all__ = ["parse_datetime", "parse_datetimetz"]

# Reject strings that are purely numeric (with optional decimal point or
# sign).  dateutil aggressively parses bare numbers like "1", "42", "2024"
# as dates, which breaks type inference — a column of integers would be
# misidentified as timestamps.
_NUMERIC_ONLY = re.compile(r"^[+-]?\d+\.?\d*$")


def _looks_numeric(s: str) -> bool:
    """Return True if *s* is a bare number that should not be parsed as a date."""
    return bool(_NUMERIC_ONLY.match(s.strip()))


def parse_datetime(datestr: Any) -> datetime.datetime | None:
    """Parse a date/time string into a :class:`datetime.datetime`.

    Accepts any format recognised by ``dateutil.parser.parse()``, including
    ISO 8601, US date formats (month-first), European formats, and natural
    language month names.  Returns ``None`` if the input cannot be parsed.

    Bare numeric strings (e.g. ``"1"``, ``"42"``, ``"2024"``) are rejected
    to prevent type-inference false positives.

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
    try:
        return _dateutil_parser.parse(datestr)
    except (ValueError, OverflowError, TypeError):
        return None


def parse_datetimetz(data: Any) -> datetime.datetime | None:
    """Parse a timezone-aware date/time string into a :class:`datetime.datetime`.

    Returns ``None`` if the input cannot be parsed or if the result is
    timezone-naive (no ``tzinfo``).  Accepts numeric offsets (``+05:00``,
    ``-0700``) and named timezones (``UTC``, ``EST``, etc.).

    If *data* is already a timezone-aware :class:`datetime.datetime`, it is
    returned as-is.  Naive datetimes return ``None``.
    """
    if isinstance(data, datetime.datetime):
        if data.tzinfo is None or data.tzinfo.utcoffset(data) is None:
            return None
        return data
    if not isinstance(data, str):
        return None
    if _looks_numeric(data):
        return None
    try:
        dt = _dateutil_parser.parse(data)
    except (ValueError, OverflowError, TypeError):
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return None
    return dt
