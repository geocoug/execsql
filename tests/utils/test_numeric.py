"""Tests for numeric utility functions in execsql.utils.numeric."""

from __future__ import annotations

import pytest

from execsql.utils.numeric import as_numeric, leading_zero_num


# ---------------------------------------------------------------------------
# leading_zero_num
# ---------------------------------------------------------------------------


class TestLeadingZeroNum:
    @pytest.mark.parametrize(
        "val, expected",
        [
            ("007", True),
            ("01", False),  # 0 + "1": float("1") == 1, not > 1 → False
            ("0.5", False),  # decimal starting with 0 is legitimate
            ("0", False),  # single char after stripping
            ("1", False),  # does not start with "0"
            ("100", False),  # doesn't start with "0"
            ("010.5", True),  # double leading zero path
            (42, False),  # non-string returns False
            (None, False),
            ("", False),
            ("a", False),  # non-numeric after stripping "0" prefix
            ("0a", False),  # can't parse remainder as float
            ("00x", False),  # double-zero prefix, non-numeric remainder
        ],
    )
    def test_leading_zero_num(self, val, expected):
        assert leading_zero_num(val) is expected


# ---------------------------------------------------------------------------
# as_numeric
# ---------------------------------------------------------------------------


class TestAsNumeric:
    @pytest.mark.parametrize(
        "val, expected",
        [
            ("42", 42),
            ("-7", -7),
            ("0", 0),
            ("3.14", 3.14),
            ("-0.5", -0.5),
            ("1e10", 1e10),
            (".5", 0.5),
            ("  42  ", 42),  # leading/trailing whitespace
            (10, 10),  # int passthrough
            (3.14, 3.14),  # float passthrough
        ],
    )
    def test_as_numeric_valid(self, val, expected):
        result = as_numeric(val)
        assert result == expected

    @pytest.mark.parametrize("val", ["abc", "1.2.3", None, [], ""])
    def test_as_numeric_returns_none(self, val):
        assert as_numeric(val) is None

    def test_integer_string_returns_int(self):
        result = as_numeric("42")
        assert isinstance(result, int)

    def test_float_string_returns_float(self):
        result = as_numeric("3.14")
        assert isinstance(result, float)

    def test_int_passthrough_returns_int(self):
        result = as_numeric(5)
        assert isinstance(result, int)
        assert result == 5
