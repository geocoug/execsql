from __future__ import annotations

"""
Date and time parsing utilities for execsql.

Provides :func:`parse_datetime`, :func:`parse_datetimetz`, and related
helpers that try a battery of format strings to convert raw string data
into Python :class:`datetime.datetime` / :class:`datetime.date` /
:class:`datetime.time` objects.  Used by :class:`~execsql.types.DT_Timestamp`,
:class:`~execsql.types.DT_TimestampTZ`, and related data-type classes when
scanning imported data for type inference.
"""

import collections
import datetime
import re
from typing import Any


dt_fmts = collections.deque(
    (
        "%c",
        "%x %X",
        "%m/%d/%y %H%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %I:%M%p",
        "%m/%d/%y %I:%M %p",
        "%m/%d/%y %I:%M:%S%p",
        "%m/%d/%y %I:%M:%S %p",
        "%m/%d/%Y %H%M",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M%p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %I:%M:%S%p",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%d %H%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %I:%M%p",
        "%Y-%m-%d %I:%M %p",
        "%Y-%m-%d %I:%M:%S%p",
        "%Y-%m-%d %I:%M:%S %p",
        "%Y/%m/%d %H%M",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %I:%M%p",
        "%Y/%m/%d %I:%M %p",
        "%Y/%m/%d %I:%M:%S%p",
        "%Y/%m/%d %I:%M:%S %p",
        "%Y/%m/%d %X",
        "%b %d, %Y %X",
        "%b %d, %Y %I:%M %p",
        "%b %d %Y %X",
        "%b %d %Y %I:%M %p",
        "%d %b, %Y %X",
        "%d %b, %Y %I:%M %p",
        "%d %b %Y %X",
        "%d %b %Y %I:%M %p",
        "%b. %d, %Y %X",
        "%b. %d, %Y %I:%M %p",
        "%b. %d %Y %X",
        "%b. %d %Y %I:%M %p",
        "%d %b., %Y %X",
        "%d %b., %Y %I:%M %p",
        "%d %b. %Y %X",
        "%d %b. %Y %I:%M %p",
        "%B %d, %Y %X",
        "%B %d, %Y %I:%M %p",
        "%B %d %Y %X",
        "%B %d %Y %I:%M %p",
        "%d %B, %Y %X",
        "%d %B, %Y %I:%M %p",
        "%d %B %Y %X",
        "%d %B %Y %I:%M %p",
        "%x",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%b %d %Y",
        "%d %b, %Y",
        "%d %b %Y",
        "%b. %d, %Y",
        "%b. %d %Y",
        "%d %b., %Y",
        "%d %b. %Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%d %B, %Y",
        "%d %B %Y",
    ),
)


def parse_datetime(datestr: Any) -> datetime.datetime | None:
    if isinstance(datestr, datetime.datetime):
        return datestr
    if not isinstance(datestr, str):
        try:
            datestr = str(datestr)
        except Exception:
            return None
    dt = None
    for i, f in enumerate(dt_fmts):  # noqa: B007
        try:
            dt = datetime.datetime.strptime(datestr, f)
        except Exception:
            continue
        break
    if i:
        del dt_fmts[i]
        dt_fmts.appendleft(f)
    return dt


dtzrx = re.compile(r"(.+)\s*([+-])(\d{1,2}):?(\d{2})$")

timestamptz_fmts = collections.deque(
    (
        "%c%Z",
        "%c %Z",
        "%x %X%Z",
        "%x %X %Z",
        "%m/%d/%Y%Z",
        "%m/%d/%Y %Z",
        "%m/%d/%y%Z",
        "%m/%d/%y %Z",
        "%m/%d/%y %H%M%Z",
        "%m/%d/%y %H%M %Z",
        "%m/%d/%y %H:%M%Z",
        "%m/%d/%y %H:%M %Z",
        "%m/%d/%y %H:%M:%S%Z",
        "%m/%d/%y %H:%M:%S %Z",
        "%m/%d/%y %I:%M%p%Z",
        "%m/%d/%y %I:%M%p %Z",
        "%m/%d/%y %I:%M %p%Z",
        "%m/%d/%y %I:%M %p %Z",
        "%m/%d/%y %I:%M:%S%p%Z",
        "%m/%d/%y %I:%M:%S%p %Z",
        "%m/%d/%y %I:%M:%S %p%Z",
        "%m/%d/%y %I:%M:%S %p %Z",
        "%m/%d/%Y %H%M%Z",
        "%m/%d/%Y %H%M %Z",
        "%m/%d/%Y %H:%M%Z",
        "%m/%d/%Y %H:%M %Z",
        "%m/%d/%Y %H:%M:%S%Z",
        "%m/%d/%Y %H:%M:%S %Z",
        "%m/%d/%Y %I:%M%p%Z",
        "%m/%d/%Y %I:%M%p %Z",
        "%m/%d/%Y %I:%M %p%Z",
        "%m/%d/%Y %I:%M %p %Z",
        "%m/%d/%Y %I:%M:%S%p%Z",
        "%m/%d/%Y %I:%M:%S%p %Z",
        "%m/%d/%Y %I:%M:%S %p%Z",
        "%m/%d/%Y %I:%M:%S %p %Z",
        "%Y-%m-%d %H%M%Z",
        "%Y-%m-%d %H%M %Z",
        "%Y-%m-%d %H:%M%Z",
        "%Y-%m-%d %H:%M %Z",
        "%Y-%m-%d %H:%M:%S%Z",
        "%Y-%m-%d %H:%M:%S %Z",
        "%Y-%m-%d %I:%M%p%Z",
        "%Y-%m-%d %I:%M%p %Z",
        "%Y-%m-%d %I:%M %p%Z",
        "%Y-%m-%d %I:%M %p %Z",
        "%Y-%m-%d %I:%M:%S%p%Z",
        "%Y-%m-%d %I:%M:%S%p %Z",
        "%Y-%m-%d %I:%M:%S %p%Z",
        "%Y-%m-%d %I:%M:%S %p %Z",
        "%Y/%m/%d %H%M%Z",
        "%Y/%m/%d %H%M %Z",
        "%Y/%m/%d %H:%M%Z",
        "%Y/%m/%d %H:%M %Z",
        "%Y/%m/%d %H:%M:%S%Z",
        "%Y/%m/%d %H:%M:%S %Z",
        "%Y/%m/%d %I:%M%p%Z",
        "%Y/%m/%d %I:%M%p %Z",
        "%Y/%m/%d %I:%M %p%Z",
        "%Y/%m/%d %I:%M %p %Z",
        "%Y/%m/%d %I:%M:%S%p%Z",
        "%Y/%m/%d %I:%M:%S%p %Z",
        "%Y/%m/%d %I:%M:%S %p%Z",
        "%Y/%m/%d %I:%M:%S %p %Z",
        "%Y/%m/%d %X%Z",
        "%Y/%m/%d %X %Z",
        "%b %d, %Y %X%Z",
        "%b %d, %Y %X %Z",
        "%b %d, %Y %I:%M %p%Z",
        "%b %d, %Y %I:%M %p %Z",
        "%b %d %Y %X%Z",
        "%b %d %Y %X %Z",
        "%b %d %Y %I:%M %p%Z",
        "%b %d %Y %I:%M %p %Z",
        "%d %b, %Y %X%Z",
        "%d %b, %Y %X %Z",
        "%d %b, %Y %I:%M %p%Z",
        "%d %b, %Y %I:%M %p %Z",
        "%d %b %Y %X%Z",
        "%d %b %Y %X %Z",
        "%d %b %Y %I:%M %p%Z",
        "%d %b %Y %I:%M %p %Z",
        "%b. %d, %Y %X%Z",
        "%b. %d, %Y %X %Z",
        "%b. %d, %Y %I:%M %%Z",
        "%b. %d, %Y %I:%M %p %Z",
        "%b. %d %Y %X%Z",
        "%b. %d %Y %X %Z",
        "%b. %d %Y %I:%M %p%Z",
        "%b. %d %Y %I:%M %p %Z",
        "%d %b., %Y %X%Z",
        "%d %b., %Y %X %Z",
        "%d %b., %Y %I:%M %p%Z",
        "%d %b., %Y %I:%M %p %Z",
        "%d %b. %Y %X%Z",
        "%d %b. %Y %X %Z",
        "%d %b. %Y %I:%M %p%Z",
        "%d %b. %Y %I:%M %p %Z",
        "%B %d, %Y %X%Z",
        "%B %d, %Y %X %Z",
        "%B %d, %Y %I:%M %p%Z",
        "%B %d, %Y %I:%M %p %Z",
        "%B %d %Y %X%Z",
        "%B %d %Y %X %Z",
        "%B %d %Y %I:%M %p%Z",
        "%B %d %Y %I:%M %p %Z",
        "%d %B, %Y %X%Z",
        "%d %B, %Y %X %Z",
        "%d %B, %Y %I:%M %p%Z",
        "%d %B, %Y %I:%M %p %Z",
        "%d %B %Y %X%Z",
        "%d %B %Y %X %Z",
        "%d %B %Y %I:%M %p%Z",
        "%d %B %Y %I:%M %p %Z",
    ),
)


def parse_datetimetz(data: Any) -> datetime.datetime | None:
    # Import Tz locally to avoid circular imports
    from execsql.types import Tz

    if isinstance(data, datetime.datetime):
        if data.tzinfo is None or data.tzinfo.utcoffset(data) is None:
            return None
        return data
    if not isinstance(data, str):
        return None
    dt = None
    # Check for numeric timezone
    try:
        datestr, sign, hr, min = dtzrx.match(data).groups()
        dt = parse_datetime(datestr)
        if not dt:
            return None
        sign = -1 if sign == "-" else 1
        return datetime.datetime(
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
            tzinfo=Tz(sign, int(hr), int(min)),
        )
    except Exception:
        # Check for alphabetic timezone
        for i, f in enumerate(timestamptz_fmts):  # noqa: B007
            try:
                dt = datetime.datetime.strptime(data, f)
            except Exception:
                continue
            break
        if i:
            del timestamptz_fmts[i]
            timestamptz_fmts.appendleft(f)
        return dt
