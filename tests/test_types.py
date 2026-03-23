"""
Tests for the data-type system in execsql.types.

Covers DataType subclass matching/conversion and DbType dialect operations.
The conftest ``minimal_conf`` fixture (autouse) provides the _state.conf
attributes required by DT_Boolean and DT_Integer.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from execsql.types import (
    DT_Binary,
    DT_Boolean,
    DT_Character,
    DT_Date,
    DT_Decimal,
    DT_Float,
    DT_Integer,
    DT_Long,
    DT_Text,
    DT_Time,
    DT_Timestamp,
    DT_TimestampTZ,
    DT_Varchar,
    DbType,
    dbt_postgres,
    dbt_sqlite,
    dbt_duckdb,
    dbt_sqlserver,
)


# ---------------------------------------------------------------------------
# DT_Boolean
# ---------------------------------------------------------------------------


class TestDTBoolean:
    def setup_method(self):
        self.dt = DT_Boolean()

    @pytest.mark.parametrize("val", ["yes", "no", "true", "false", "1", "0", True, False])
    def test_matches_valid(self, val):
        assert self.dt.matches(val) is True

    @pytest.mark.parametrize("val", ["y", "n", "t", "f"])
    def test_matches_short_forms_when_boolean_words_false(self, val):
        # boolean_words=False → y/n/t/f are accepted
        assert self.dt.matches(val) is True

    @pytest.mark.parametrize("val", [2, "maybe", "yes_no", "", 3.14])
    def test_no_match_invalid(self, val):
        assert self.dt.matches(val) is False

    def test_null_does_not_match(self):
        assert self.dt.matches(None) is False

    def test_from_data_true_string(self):
        assert self.dt.from_data("true") is True

    def test_from_data_false_string(self):
        assert self.dt.from_data("false") is False

    def test_from_data_int_one(self):
        assert self.dt.from_data("1") is True

    def test_from_data_int_zero(self):
        assert self.dt.from_data("0") is False

    def test_from_data_bool_passthrough(self):
        assert self.dt.from_data(True) is True
        assert self.dt.from_data(False) is False

    def test_boolean_words_mode(self, minimal_conf):
        minimal_conf.boolean_words = True
        dt = DT_Boolean()
        # y/n/t/f should NOT match in boolean_words mode
        assert dt.matches("y") is False
        assert dt.matches("yes") is True


# ---------------------------------------------------------------------------
# DT_Integer
# ---------------------------------------------------------------------------


class TestDTInteger:
    def setup_method(self):
        self.dt = DT_Integer()

    @pytest.mark.parametrize("val", [0, 1, -1, 100, "42", "-7", 2_147_483_647])
    def test_matches_valid(self, val):
        assert self.dt.matches(val) is True

    @pytest.mark.parametrize("val", [3.14, "3.14", 2_147_483_648, "2147483648", "abc", None])
    def test_no_match_invalid(self, val):
        assert self.dt.matches(val) is False

    def test_leading_zero_string_not_matched(self):
        assert self.dt.matches("007") is False

    def test_from_data_int_passthrough(self):
        assert self.dt.from_data(5) == 5

    def test_from_data_string(self):
        assert self.dt.from_data("42") == 42

    def test_from_data_float_whole(self):
        assert self.dt.from_data(3.0) == 3


# ---------------------------------------------------------------------------
# DT_Long
# ---------------------------------------------------------------------------


class TestDTLong:
    def setup_method(self):
        self.dt = DT_Long()

    def test_matches_large_int(self):
        assert self.dt.matches(2_147_483_648) is True

    def test_from_data_int_string(self):
        assert self.dt.from_data("9999999999") == 9_999_999_999

    def test_float_nan_returns_none(self):
        import math

        assert self.dt.from_data(float("nan")) is None


# ---------------------------------------------------------------------------
# DT_Float
# ---------------------------------------------------------------------------


class TestDTFloat:
    def setup_method(self):
        self.dt = DT_Float()

    @pytest.mark.parametrize("val", [1.5, "3.14", "1e10", "-0.5", ".5", 0.0])
    def test_matches_valid(self, val):
        assert self.dt.matches(val) is True

    @pytest.mark.parametrize("val", ["abc", None, "1.2.3"])
    def test_no_match_invalid(self, val):
        assert self.dt.matches(val) is False

    def test_leading_zero_not_matched(self):
        assert self.dt.matches("07.5") is False

    def test_from_data_passthrough(self):
        assert self.dt.from_data(1.5) == 1.5


# ---------------------------------------------------------------------------
# DT_Decimal
# ---------------------------------------------------------------------------


class TestDTDecimal:
    def setup_method(self):
        self.dt = DT_Decimal()

    def test_matches_decimal_string(self):
        assert self.dt.matches("3.14") is True

    def test_matches_negative(self):
        assert self.dt.matches("-1.5") is True

    def test_matches_integer_string(self):
        # DT_Decimal accepts integers — the regex allows digits without a decimal point
        assert self.dt.matches("42") is True

    def test_precision_and_scale_set(self):
        self.dt.from_data("3.14")
        assert self.dt.precision == 3
        assert self.dt.scale == 2

    def test_from_data_decimal_object(self):
        d = Decimal("1.5")
        result = self.dt.from_data(d)
        assert result == d


# ---------------------------------------------------------------------------
# DT_Character
# ---------------------------------------------------------------------------


class TestDTCharacter:
    def setup_method(self):
        self.dt = DT_Character()

    def test_matches_short_string(self):
        assert self.dt.matches("hello") is True

    def test_matches_long_string(self):
        # DT_Character accepts any string that is already a str instance
        assert self.dt.matches("x" * 256) is True

    def test_no_match_bytearray(self):
        assert self.dt.matches(bytearray(b"abc")) is False

    def test_no_match_null(self):
        assert self.dt.matches(None) is False

    def test_lenspec_is_true(self):
        assert self.dt.lenspec is True


# ---------------------------------------------------------------------------
# DT_Varchar
# ---------------------------------------------------------------------------


class TestDTVarchar:
    def setup_method(self):
        self.dt = DT_Varchar()

    def test_lenspec_and_varlen(self):
        assert self.dt.lenspec is True
        assert self.dt.varlen is True

    def test_no_match_bytearray(self):
        assert self.dt.matches(bytearray(b"data")) is False


# ---------------------------------------------------------------------------
# DT_Text
# ---------------------------------------------------------------------------


class TestDTText:
    def setup_method(self):
        self.dt = DT_Text()

    def test_matches_any_string(self):
        assert self.dt.matches("x" * 1000) is True

    def test_no_match_bytearray(self):
        assert self.dt.matches(bytearray(b"abc")) is False

    def test_lenspec_is_false(self):
        assert self.dt.lenspec is False


# ---------------------------------------------------------------------------
# DT_Binary
# ---------------------------------------------------------------------------


class TestDTBinary:
    def setup_method(self):
        self.dt = DT_Binary()

    def test_data_type_is_bytearray(self):
        assert self.dt.data_type is bytearray


# ---------------------------------------------------------------------------
# DT_Date
# ---------------------------------------------------------------------------


class TestDTDate:
    def setup_method(self):
        self.dt = DT_Date()

    @pytest.mark.parametrize(
        "val",
        [
            "2024-01-15",
            "01/15/2024",
            "01/15/24",
            "Jan 15, 2024",
            "15 Jan 2024",
            datetime.date(2024, 1, 15),
        ],
    )
    def test_matches_valid_dates(self, val):
        assert self.dt.matches(val) is True

    @pytest.mark.parametrize("val", ["not-a-date", "99/99/9999", None, 42])
    def test_no_match_invalid(self, val):
        assert self.dt.matches(val) is False

    def test_from_data_passthrough_date(self):
        d = datetime.date(2024, 6, 1)
        assert self.dt.from_data(d) == d


# ---------------------------------------------------------------------------
# DT_Time
# ---------------------------------------------------------------------------


class TestDTTime:
    def setup_method(self):
        self.dt = DT_Time()

    @pytest.mark.parametrize(
        "val",
        [
            "14:30",
            "14:30:00",
            "2:30 PM",
            "02:30:00 PM",
        ],
    )
    def test_matches_valid_times(self, val):
        assert self.dt.matches(val) is True

    @pytest.mark.parametrize("val", ["not-a-time", None, 42])
    def test_no_match_invalid(self, val):
        assert self.dt.matches(val) is False


# ---------------------------------------------------------------------------
# DT_Timestamp
# ---------------------------------------------------------------------------


class TestDTTimestamp:
    def setup_method(self):
        self.dt = DT_Timestamp()

    @pytest.mark.parametrize(
        "val",
        [
            "2024-01-15 14:30:00",
            "01/15/2024 14:30",
            datetime.datetime(2024, 1, 15, 14, 30),
        ],
    )
    def test_matches_valid(self, val):
        assert self.dt.matches(val) is True

    def test_datetime_passthrough(self):
        dt = datetime.datetime(2024, 6, 1, 12, 0, 0)
        assert self.dt.from_data(dt) == dt


# ---------------------------------------------------------------------------
# DT_TimestampTZ
# ---------------------------------------------------------------------------


class TestDTTimestampTZ:
    def setup_method(self):
        self.dt = DT_TimestampTZ()

    def test_aware_datetime_matches(self):
        import datetime as dt

        tz = dt.timezone(dt.timedelta(hours=5))
        aware = dt.datetime(2024, 1, 15, 10, 0, tzinfo=tz)
        assert self.dt.matches(aware) is True

    def test_naive_datetime_does_not_match(self):
        naive = datetime.datetime(2024, 1, 15, 10, 0)
        assert self.dt.matches(naive) is False

    def test_tz_string_matches(self):
        # Numeric timezone must be adjacent to datetime (no space before +)
        assert self.dt.matches("2024-01-15 10:00:00+05:00") is True


# ---------------------------------------------------------------------------
# DbType
# ---------------------------------------------------------------------------


class TestDbType:
    def test_quoted_plain_identifier(self):
        dbt = DbType("test", '""')
        assert dbt.quoted("simple_name") == "simple_name"

    def test_quoted_identifier_with_space(self):
        dbt = DbType("test", '""')
        assert dbt.quoted("my table") == '"my table"'

    def test_quoted_identifier_with_dash(self):
        dbt = DbType("test", '""')
        assert dbt.quoted("my-col") == '"my-col"'

    def test_column_spec_text(self):
        spec = dbt_postgres.column_spec("name", DT_Text, None, True)
        assert "name" in spec
        assert "text" in spec.lower()

    def test_column_spec_varchar_with_length(self):
        spec = dbt_postgres.column_spec("label", DT_Varchar, 50, False)
        assert "50" in spec
        assert "NOT NULL" in spec

    def test_column_spec_integer_not_null(self):
        spec = dbt_postgres.column_spec("id", DT_Integer, None, False)
        assert "NOT NULL" in spec

    def test_column_spec_integer_nullable(self):
        spec = dbt_postgres.column_spec("id", DT_Integer, None, True)
        assert "NOT NULL" not in spec

    def test_sqlite_dialect_integer(self):
        spec = dbt_sqlite.column_spec("count", DT_Integer, None, False)
        assert "integer" in spec.lower()

    def test_duckdb_dialect_boolean(self):
        spec = dbt_duckdb.column_spec("flag", DT_Boolean, None, False)
        assert "BOOLEAN" in spec

    def test_sqlserver_dialect_text(self):
        spec = dbt_sqlserver.column_spec("body", DT_Text, None, True)
        assert "varchar(max)" in spec.lower()

    def test_repr(self):
        assert "PostgreSQL" in repr(dbt_postgres)

    def test_unknown_type_raises(self):
        from execsql.exceptions import DbTypeError

        dbt = DbType("TestDB", '""')
        # dialect is None — accessing any type should raise
        with pytest.raises(Exception):
            dbt.column_spec("col", DT_Integer, None, False)
