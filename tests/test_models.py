"""
Tests for Column and DataTable type inference (execsql.models).

The conftest ``minimal_conf`` fixture provides the _state.conf attributes
that Column and DataTable read during type scanning.
"""

from __future__ import annotations

import datetime

import pytest

from execsql.exceptions import ColumnError, DataTableError
from execsql.models import Column, DataTable, JsonDatatype, to_json_type
from execsql.types import (
    DT_Boolean,
    DT_Character,
    DT_Date,
    DT_Float,
    DT_Integer,
    DT_Long,
    DT_Text,
    DT_Timestamp,
    DT_Varchar,
    dbt_postgres,
)


# ---------------------------------------------------------------------------
# Column
# ---------------------------------------------------------------------------


class TestColumn:
    def test_requires_name(self):
        with pytest.raises(Exception):
            Column("")

    def test_repr(self):
        assert "my_col" in repr(Column("my_col"))

    def test_integer_column(self):
        col = Column("age")
        for v in ["25", "30", "42"]:
            col.eval_types(v)
        name, dt, maxlen, nullable, prec, scale = col.column_type()
        assert dt is DT_Integer

    def test_float_column(self):
        col = Column("price")
        for v in ["1.5", "3.14", "0.99"]:
            col.eval_types(v)
        name, dt, maxlen, nullable, prec, scale = col.column_type()
        assert dt is DT_Float

    def test_text_column(self):
        col = Column("notes")
        for v in ["hello world", "foo bar baz", "a" * 300]:
            col.eval_types(v)
        name, dt, maxlen, nullable, prec, scale = col.column_type()
        # Long strings should resolve to Text (no length spec required)
        assert dt in (DT_Text, DT_Varchar, DT_Character)

    def test_boolean_column(self):
        col = Column("active")
        for v in ["true", "false", "true"]:
            col.eval_types(v)
        name, dt, *_ = col.column_type()
        assert dt is DT_Boolean

    def test_date_column(self):
        col = Column("dob")
        for v in ["2024-01-15", "2023-06-01", "1999-12-31"]:
            col.eval_types(v)
        name, dt, *_ = col.column_type()
        # Date-only strings may resolve to DT_Date or DT_Timestamp depending on type priority
        assert dt in (DT_Date, DT_Timestamp)

    def test_timestamp_column(self):
        col = Column("created_at")
        for v in ["2024-01-15 10:30:00", "2023-06-01 08:00:00"]:
            col.eval_types(v)
        name, dt, *_ = col.column_type()
        assert dt is DT_Timestamp

    def test_nullable_column(self):
        col = Column("optional")
        col.eval_types("42")
        col.eval_types(None)
        col.eval_types("10")
        name, dt, maxlen, nullable, *_ = col.column_type()
        assert nullable is True

    def test_all_null_column_resolves_to_text(self):
        col = Column("empty")
        col.eval_types(None)
        col.eval_types(None)
        name, dt, *_ = col.column_type()
        assert dt is DT_Text

    def test_mixed_integer_float_resolves_to_float(self):
        col = Column("mixed")
        col.eval_types("1")
        col.eval_types("2.5")
        col.eval_types("3")
        name, dt, *_ = col.column_type()
        assert dt is DT_Float

    def test_whitespace_name_stripped(self):
        col = Column("  spaced  ")
        assert col.name == "spaced"

    def test_only_strings_mode(self, minimal_conf):
        minimal_conf.only_strings = True
        col = Column("val")
        for v in ["42", "hello", "3.14"]:
            col.eval_types(v)
        name, dt, *_ = col.column_type()
        assert dt in (DT_Character, DT_Varchar, DT_Text)

    def test_trim_strings_applied(self, minimal_conf):
        minimal_conf.trim_strings = True
        col = Column("trimmed")
        col.eval_types("  42  ")
        # After trimming, "42" should match Integer
        name, dt, *_ = col.column_type()
        assert dt is DT_Integer

    def test_empty_string_as_null_when_not_empty_strings(self, minimal_conf):
        minimal_conf.empty_strings = False
        col = Column("val")
        col.eval_types("")
        col.eval_types("")
        # All values are treated as null → Text
        name, dt, *_ = col.column_type()
        assert dt is DT_Text

    def test_column_type_cached(self):
        col = Column("x")
        col.eval_types("1")
        first = col.column_type()
        second = col.column_type()
        assert first == second


# ---------------------------------------------------------------------------
# DataTable
# ---------------------------------------------------------------------------


class TestDataTable:
    def _make_table(self, col_names, rows):
        return DataTable(col_names, iter(rows))

    def test_basic_integer_table(self):
        dt = self._make_table(["id", "val"], [["1", "100"], ["2", "200"], ["3", "300"]])
        assert len(dt.cols) == 2
        assert dt.cols[0].column_type()[1] is DT_Integer
        assert dt.cols[1].column_type()[1] is DT_Integer

    def test_create_table_sql(self):
        dt = self._make_table(["id"], [["1"], ["2"], ["3"]])
        sql = dt.create_table(dbt_postgres, None, "my_table")
        assert "CREATE TABLE" in sql
        assert "my_table" in sql
        assert "integer" in sql.lower()

    def test_create_table_with_schema(self):
        dt = self._make_table(["id"], [["1"]])
        sql = dt.create_table(dbt_postgres, "public", "my_table")
        assert "public" in sql
        assert "my_table" in sql

    def test_create_table_pretty(self):
        dt = self._make_table(["id"], [["1"]])
        sql = dt.create_table(dbt_postgres, None, "t", pretty=True)
        assert "\n" in sql

    def test_short_row_counted(self):
        dt = self._make_table(["a", "b", "c"], [["1", "2"], ["3", "4"], ["5", "6"]])
        assert dt.shortrows == 3

    def test_too_many_columns_raises(self):
        with pytest.raises(DataTableError):
            self._make_table(["a"], [["1", "2", "3"]])

    def test_empty_table(self):
        dt = self._make_table(["a", "b"], [])
        assert dt.inputrows == 0
        assert dt.datarows == 0

    def test_column_declarations(self):
        dt = self._make_table(["name"], [["Alice"], ["Bob"]])
        decls = dt.column_declarations(dbt_postgres)
        assert len(decls) == 1
        assert "name" in decls[0].lower() or "name" in decls[0]


# ---------------------------------------------------------------------------
# JsonDatatype
# ---------------------------------------------------------------------------


class TestJsonDatatype:
    def test_has_type_constants(self):
        jdt = JsonDatatype()
        assert JsonDatatype.integer == "integer"
        assert JsonDatatype.string == "string"
        assert JsonDatatype.boolean == "boolean"
        assert JsonDatatype.date == "date"
        assert JsonDatatype.datetime == "datetime"

    def test_to_json_type_mapping(self):
        assert to_json_type[DT_Integer] == "integer"
        assert to_json_type[DT_Boolean] == "boolean"
        assert to_json_type[DT_Float] == "number"
        assert to_json_type[DT_Text] == "string"
        assert to_json_type[DT_Date] == "date"
        assert to_json_type[DT_Timestamp] == "datetime"
