"""Each adapter reports the execsql type of every column of a table that IMPORT or COPY loads (issue #100)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from execsql.db.base import Database
from execsql.db.target_types import kind_for_python_type, kind_for_type_name
from execsql.types import (
    DT_Binary,
    DT_Boolean,
    DT_Date,
    DT_Decimal,
    DT_Float,
    DT_Long,
    DT_Text,
    DT_Time,
    DT_Timestamp,
    DT_TimestampTZ,
)
from tests.live_db import open_backend


@pytest.mark.parametrize(
    ("type_name", "kind"),
    [
        # PostgreSQL format_type()
        ("text", DT_Text),
        ("character varying(50)", DT_Text),
        ("character(3)", DT_Text),
        ("integer", DT_Long),
        ("smallint", DT_Long),
        ("bigint", DT_Long),
        ("numeric(18,3)", DT_Decimal),
        ("numeric(10,0)", DT_Long),
        ("numeric(10)", DT_Long),
        ("numeric", DT_Decimal),
        ("double precision", DT_Float),
        ("real", DT_Float),
        ("boolean", DT_Boolean),
        ("date", DT_Date),
        ("timestamp without time zone", DT_Timestamp),
        ("timestamp(3) without time zone", DT_Timestamp),
        ("timestamp with time zone", DT_TimestampTZ),
        ("time without time zone", DT_Time),
        ("time with time zone", None),
        ("bytea", DT_Binary),
        ("integer[]", None),
        ("uuid", None),
        ("json", None),
        ("interval", None),
        ("bit(1)", DT_Boolean),
        ("bit(8)", None),
        # MySQL SHOW COLUMNS
        ("tinyint(1)", DT_Boolean),
        ("tinyint", DT_Long),
        ("tinyint(4)", DT_Long),
        ("int unsigned", DT_Long),
        ("int(11) unsigned zerofill", DT_Long),
        ("decimal(18,3)", DT_Decimal),
        ("decimal(10,0)", DT_Long),
        ("double", DT_Float),
        ("datetime", DT_Timestamp),
        ("mediumtext", DT_Text),
        ("varbinary(10)", DT_Binary),
        ("longblob", DT_Binary),
        ("enum('a','b')", None),
        ("set('a','b')", None),
        ("year", None),
        # SQL Server type_name()
        ("nvarchar", DT_Text),
        ("bit", DT_Boolean),
        ("money", DT_Decimal),
        ("datetime2", DT_Timestamp),
        ("smalldatetime", DT_Timestamp),
        ("datetimeoffset", DT_TimestampTZ),
        ("image", DT_Binary),
        ("uniqueidentifier", None),
        ("xml", None),
        # DuckDB
        ("VARCHAR", DT_Text),
        ("DECIMAL(18,3)", DT_Decimal),
        ("HUGEINT", DT_Long),
        ("UBIGINT", DT_Long),
        ("TIMESTAMP WITH TIME ZONE", DT_TimestampTZ),
        ("TIMESTAMP_NS", DT_Timestamp),
        ("BLOB", DT_Binary),
        ("VARCHAR[]", None),
        ("INTEGER[3]", None),
        ("STRUCT(a INTEGER)", None),
        ("MAP(VARCHAR, INTEGER)", None),
        ("", None),
    ],
)
def test_kind_for_type_name(type_name, kind):
    assert kind_for_type_name(type_name) is kind


def test_an_oracle_date_holds_a_time_of_day():
    assert kind_for_type_name("date", oracle=True) is DT_Timestamp
    assert kind_for_type_name("date") is DT_Date


@pytest.mark.parametrize(
    ("type_code", "scale", "kind"),
    [
        (str, None, DT_Text),
        (int, None, DT_Long),
        (bool, None, DT_Boolean),
        (float, None, DT_Float),
        (Decimal, 2, DT_Decimal),
        (Decimal, 0, DT_Long),
        (datetime.date, None, DT_Date),
        (datetime.datetime, None, DT_Timestamp),
        (datetime.time, None, DT_Time),
        # pyodbc describes SQL Server datetimeoffset as bytearray, like varbinary.
        (bytearray, None, None),
        (bytes, None, None),
        (object, None, None),
    ],
)
def test_kind_for_python_type(type_code, scale, kind):
    assert kind_for_python_type(type_code, scale) is kind


def _described(adapter_cls, description):
    """column_kinds() of an adapter whose cursor describes *description*."""
    db = MagicMock(spec=adapter_cls)
    curs = MagicMock(description=description)
    curs.fetchall.return_value = []
    db._cursor.return_value.__enter__.return_value = curs
    db._column_type_query = lambda *a, **k: Database._column_type_query(db, *a, **k)
    db._described_kind = lambda d: adapter_cls._described_kind(db, d)
    return Database.column_kinds(db, '"t"')


def test_the_default_reads_the_python_types_a_driver_describes():
    """Access, Firebird and ODBC DSNs: the driver describes a column by the Python type it returns."""
    description = [
        ("Name", str, None, 50, 50, 0, True),
        ("Count", int, None, 10, 10, 0, True),
        ("Price", Decimal, None, 19, 19, 4, True),
        ("Whole", Decimal, None, 10, 10, 0, True),
        ("Flag", bool, None, 1, 1, 0, True),
        ("When", datetime.datetime, None, 19, 19, 0, True),
        ("Data", bytearray, None, 10, 10, 0, True),
    ]
    assert _described(Database, description) == {
        "name": DT_Text,
        "count": DT_Long,
        "price": DT_Decimal,
        "whole": DT_Long,
        "flag": DT_Boolean,
        "when": DT_Timestamp,
        "data": None,
    }


def test_oracle_reads_the_dbtype_and_the_number_scale():
    oracledb = pytest.importorskip("oracledb")
    from execsql.db.oracle import OracleDatabase

    description = [
        ("NAME", oracledb.DB_TYPE_VARCHAR, 50, 50, None, None, True),
        ("QTY", oracledb.DB_TYPE_NUMBER, 11, None, 10, 0, True),
        ("PRICE", oracledb.DB_TYPE_NUMBER, 11, None, 10, 2, True),
        ("ANY_NUMBER", oracledb.DB_TYPE_NUMBER, 127, None, 0, -127, True),
        ("RATIO", oracledb.DB_TYPE_BINARY_DOUBLE, None, None, None, None, True),
        ("SEEN", oracledb.DB_TYPE_DATE, None, None, None, None, True),
        ("AT", oracledb.DB_TYPE_TIMESTAMP_TZ, None, None, None, None, True),
        ("DOC", oracledb.DB_TYPE_CLOB, None, None, None, None, True),
        ("BITS", oracledb.DB_TYPE_RAW, 16, 16, None, None, True),
        ("SPAN", oracledb.DB_TYPE_INTERVAL_DS, None, None, None, None, True),
    ]
    assert _described(OracleDatabase, description) == {
        "name": DT_Text,
        "qty": DT_Long,
        "price": DT_Decimal,
        "any_number": DT_Decimal,
        "ratio": DT_Float,
        "seen": DT_Timestamp,
        "at": DT_TimestampTZ,
        "doc": DT_Text,
        "bits": DT_Binary,
        "span": None,
    }


# ---------------------------------------------------------------------------
# Live databases: the column types each one reports for a real table
# ---------------------------------------------------------------------------

_LIVE = {
    "duckdb": [
        ("varchar", DT_Text),
        ("integer", DT_Long),
        ("bigint", DT_Long),
        ("decimal(18,3)", DT_Decimal),
        ("decimal(10,0)", DT_Long),
        ("double", DT_Float),
        ("boolean", DT_Boolean),
        ("date", DT_Date),
        ("timestamp", DT_Timestamp),
        ("timestamptz", DT_TimestampTZ),
        ("time", DT_Time),
        ("blob", DT_Binary),
        ("uuid", None),
        ("integer[]", None),
    ],
    "postgres": [
        ("text", DT_Text),
        ("varchar(50)", DT_Text),
        ("char(3)", DT_Text),
        ("integer", DT_Long),
        ("bigint", DT_Long),
        ("numeric(18,3)", DT_Decimal),
        ("numeric(10,0)", DT_Long),
        ("numeric", DT_Decimal),
        ("double precision", DT_Float),
        ("boolean", DT_Boolean),
        ("date", DT_Date),
        ("timestamp", DT_Timestamp),
        ("timestamptz", DT_TimestampTZ),
        ("time", DT_Time),
        ("bytea", DT_Binary),
        ("uuid", None),
        ("integer[]", None),
    ],
    "mysql": [
        ("text", DT_Text),
        ("varchar(50)", DT_Text),
        ("int", DT_Long),
        ("tinyint", DT_Long),
        ("boolean", DT_Boolean),
        ("bigint unsigned", DT_Long),
        ("decimal(18,3)", DT_Decimal),
        ("decimal(10,0)", DT_Long),
        ("double", DT_Float),
        ("date", DT_Date),
        ("datetime", DT_Timestamp),
        ("time", DT_Time),
        ("blob", DT_Binary),
        ("enum('a','b')", None),
        ("json", None),
    ],
    "sqlserver": [
        ("varchar(50)", DT_Text),
        ("nvarchar(max)", DT_Text),
        ("int", DT_Long),
        ("bigint", DT_Long),
        ("decimal(18,3)", DT_Decimal),
        ("numeric(10,0)", DT_Long),
        ("float", DT_Float),
        ("money", DT_Decimal),
        ("bit", DT_Boolean),
        ("date", DT_Date),
        ("datetime2", DT_Timestamp),
        ("datetimeoffset", DT_TimestampTZ),
        ("time", DT_Time),
        ("varbinary(10)", DT_Binary),
        ("uniqueidentifier", None),
    ],
}

_TABLE = "xkind_t"


def _create(db, name: str, columns: list[str]) -> None:
    with db._cursor() as curs:
        curs.execute(f"drop table if exists {name}")
        curs.execute(f"create table {name} ({', '.join(columns)})")
    db.commit()


def _drop(db, name: str) -> None:
    with db._cursor() as curs:
        curs.execute(f"drop table if exists {name}")
    db.commit()


@pytest.mark.parametrize("dbms", sorted(_LIVE))
def test_column_kinds_of_a_live_table(dbms, tmp_path, minimal_conf):
    db = open_backend(dbms, tmp_path)
    name = db.type.quoted(_TABLE)
    try:
        _create(db, name, [f"C{i} {t}" for i, (t, _kind) in enumerate(_LIVE[dbms])])
        kinds = db.column_kinds(name)
        _drop(db, name)
    finally:
        db.close()
    assert kinds == {f"c{i}": kind for i, (_t, kind) in enumerate(_LIVE[dbms])}


def test_sqlserver_falls_back_to_the_description_for_a_temp_table(tmp_path, minimal_conf):
    db = open_backend("sqlserver", tmp_path)
    try:
        with db._cursor() as curs:
            curs.execute("create table #xkind (n int, s varchar(5), d datetimeoffset)")
        kinds = db.column_kinds("#xkind")
    finally:
        db.close()
    assert kinds == {"n": DT_Long, "s": DT_Text, "d": None}


def test_postgres_finds_the_table_an_unqualified_insert_finds(tmp_path, minimal_conf):
    """With the same table name in two schemas, the one on the search path is described."""
    db = open_backend("postgres", tmp_path)
    try:
        with db._cursor() as curs:
            curs.execute("drop schema if exists xkind_other cascade")
            curs.execute("create schema xkind_other")
            curs.execute("create table xkind_other.xkind_t (v integer)")
        _create(db, "xkind_t", ["v text"])
        unqualified = db.column_kinds(db.type.quoted("xkind_t"))
        qualified = db.column_kinds(db.schema_qualified_table_name("xkind_other", "xkind_t"))
        _drop(db, "xkind_t")
        with db._cursor() as curs:
            curs.execute("drop schema xkind_other cascade")
        db.commit()
    finally:
        db.close()
    assert unqualified == {"v": DT_Text}
    assert qualified == {"v": DT_Long}


def test_a_missing_table_is_an_error(tmp_path, minimal_conf):
    from execsql.exceptions import ErrInfo

    db = open_backend("duckdb", tmp_path)
    try:
        with pytest.raises(ErrInfo, match="column types of table"):
            db.column_kinds('"no_such_table"')
    finally:
        db.close()


def test_column_kinds_returns_lower_cased_names():
    assert _described(Database, [("MixedCase", str, None, 5, 5, 0, True)]) == {"mixedcase": DT_Text}


# ---------------------------------------------------------------------------
# Converting a value for the column of an existing table it goes into
# ---------------------------------------------------------------------------


def _scanned_default(value):
    """Stands in for the conversion to the scanned type; marks what it was given."""
    return ("default", value)


def _converter(kind, scanned=DT_Text):
    from execsql.db.target_types import existing_table_converter

    return existing_table_converter(kind, scanned, _scanned_default, "n", '"t"')


@pytest.mark.parametrize("value", ["yes", "1", True, datetime.date(2024, 1, 5), None, " 7 "])
def test_a_text_column_gets_the_value_as_written(value):
    assert _converter(DT_Text, scanned=DT_Boolean)(value) == value


@pytest.mark.parametrize(
    ("value", "stored"),
    [
        ("7", 7),
        (" 7 ", 7),
        ("+3", 3),
        ("-2", -2),
        ("00701", 701),
        ("1.0", 1),
        ("2.00", 2),
        ("1e3", 1000),
        (".0", 0),
        (7, 7),
        (Decimal("2.000"), 2),
        (1.0, 1),
        (3000000000, 3000000000),
    ],
)
def test_an_integer_column_gets_whole_numbers(value, stored):
    result = _converter(DT_Long)(value)
    assert result == stored
    assert type(result) is int


@pytest.mark.parametrize("value", ["1.5", "0.1", "2.25", "1e-20", Decimal("1.50"), 0.1, 1.5])
def test_a_fraction_going_into_an_integer_column_is_an_error(value):
    from execsql.exceptions import ErrInfo

    with pytest.raises(ErrInfo, match=r"column n of \"t\": the column holds whole numbers"):
        _converter(DT_Long)(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "abc",
        "2024-01-05",
        "1_000",  # Python reads it as 1000; a database does not
        "١٢",  # Arabic-Indic digits: Python reads them as 12
        "Infinity",
        "NaN",
        "1e999999",  # a whole number far too long for any column: not expanded here
        float("inf"),
        float("nan"),
        Decimal("NaN"),
        True,
        datetime.date(2024, 1, 5),
    ],
)
def test_an_integer_column_leaves_what_is_not_a_number_to_the_old_conversion(value):
    assert _converter(DT_Long)(value) == ("default", value)


@pytest.mark.parametrize("kind", [DT_Long, DT_Decimal, DT_Float])
def test_true_false_going_into_a_number_column_is_one_or_zero(kind):
    from execsql.db.target_types import existing_table_converter

    convert = existing_table_converter(
        kind,
        DT_Boolean,
        lambda v: v in ("yes", "1", 1, True) if v is not None else None,
        "n",
        '"t"',
    )
    assert [convert(v) for v in ("yes", "no", "1", 0, True, None)] == [1, 0, 1, 0, 1, None]


@pytest.mark.parametrize(
    ("kind", "scanned"),
    [
        (None, DT_Boolean),  # no execsql type fits the column
        (DT_Boolean, DT_Boolean),
        (DT_Boolean, DT_Long),
        (DT_Decimal, DT_Decimal),
        (DT_Float, DT_Long),
        (DT_Date, DT_Timestamp),
        (DT_Timestamp, DT_Text),
        (DT_TimestampTZ, DT_TimestampTZ),
        (DT_Time, DT_Time),
        (DT_Binary, DT_Binary),
    ],
)
def test_other_columns_keep_the_old_conversion(kind, scanned):
    assert _converter(kind, scanned) is _scanned_default


# ---------------------------------------------------------------------------
# IMPORT and COPY into a table that is already there, end to end (DuckDB)
# ---------------------------------------------------------------------------


def _duckdb_run(tmp_path, sql: str):
    from execsql import run

    return run(sql=sql, dsn=f"duckdb:///{tmp_path / 't.duckdb'}", new_db=True)


def _rows(tmp_path, query: str):
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    try:
        return con.execute(query).fetchall()
    finally:
        con.close()


def test_copy_of_zero_and_one_into_existing_text_and_integer_columns(tmp_path):
    pytest.importorskip("duckdb")
    result = _duckdb_run(
        tmp_path,
        "create table src (code integer);\n"
        "insert into src values (1), (0);\n"
        "create table as_text (code varchar);\n"
        "create table as_int (code integer);\n"
        "-- !x! copy src from initial to as_text in initial\n"
        "-- !x! copy src from initial to as_int in initial\n",
    )
    assert result.success, result.errors
    assert _rows(tmp_path, "select code from as_text order by code") == [("0",), ("1",)]
    assert _rows(tmp_path, "select code from as_int order by code") == [(0,), (1,)]


def test_import_into_an_existing_text_column_keeps_the_text(tmp_path):
    pytest.importorskip("duckdb")
    (tmp_path / "in.csv").write_text("flag,day\nyes,01/05/2024\nno,02/06/2024\n")
    result = _duckdb_run(
        tmp_path,
        f"create table t (flag varchar, day varchar);\n-- !x! import to t from {tmp_path / 'in.csv'}\n",
    )
    assert result.success, result.errors
    assert _rows(tmp_path, "select * from t order by flag desc") == [("yes", "01/05/2024"), ("no", "02/06/2024")]


def test_import_of_a_fraction_into_an_existing_integer_column_fails_and_loads_nothing(tmp_path):
    pytest.importorskip("duckdb")
    (tmp_path / "in.csv").write_text("n\n2.0\n1.5\n")
    result = _duckdb_run(
        tmp_path,
        f"create table t (n integer);\n-- !x! import to t from {tmp_path / 'in.csv'}\n",
    )
    assert not result.success
    assert "the column holds whole numbers" in str(result.errors)
    assert _rows(tmp_path, "select count(*) from t") == [(0,)]


def test_import_to_new_still_types_the_table_from_the_data(tmp_path):
    pytest.importorskip("duckdb")
    (tmp_path / "in.csv").write_text("flag,day\nyes,2024-01-05\nno,2024-02-06\n")
    result = _duckdb_run(tmp_path, f"-- !x! import to new t from {tmp_path / 'in.csv'}\n")
    assert result.success, result.errors
    assert _rows(tmp_path, "select * from t order by day") == [
        (True, datetime.datetime(2024, 1, 5, 0, 0)),
        (False, datetime.datetime(2024, 2, 6, 0, 0)),
    ]
