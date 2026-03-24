from __future__ import annotations

"""
Numeric utility functions for execsql.

Provides:

- :func:`leading_zero_num` — returns ``True`` if a string looks like a
  number with a leading zero (e.g. ``"007"``), used to prevent
  misclassifying zero-padded identifiers as integers.
- :func:`format_number` — formats a numeric value according to a format
  string, used by the ``FORMAT NUMBER`` substitution variant.
"""

import re
from typing import Any


def leading_zero_num(dataval: Any) -> bool:
    # Returns True if the data value is potentially a number but has a leading zero
    if not isinstance(dataval, str):
        return False
    if len(dataval) < 2:
        return False
    if dataval[0] != "0":
        return False
    dataval = dataval[1:]
    if dataval[0] == "0" and len(dataval) > 1:
        try:
            x = float(dataval[1:])
        except Exception:
            return False
        return True
    else:
        try:
            x = float(dataval)
        except Exception:
            return False
        if x > 1:
            return True
    return False


def as_numeric(strval: Any) -> int | float | None:
    # Converts the given value to an int, a float, or None.
    if type(strval) in (int, float):
        return strval
    if not isinstance(strval, str):
        strval = str(strval)
    if re.match(r"^\s*[+-]?\d+\s*$", strval):
        return int(strval)
    if re.match(r"^\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*$", strval):
        return float(strval)
    return None
