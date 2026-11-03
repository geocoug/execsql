"""SQLite existing integer targets reject fractions without changing other loads."""

from __future__ import annotations

import datetime
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

import execsql
from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo
from execsql.models import DataTable
from execsql.types import DT_Decimal, DT_Long, DT_Text


@pytest.fixture
def db():
    database = SQLiteDatabase(":memory:")
    try:
        yield database
    finally:
        database.close()


def populate(db, value, *, existing=True, schema=None, table="t"):
    data = [(value,)]
    db.populate_table(schema, table, data, ["v"], lambda: DataTable(["v"], data), existing_table=existing)


@pytest.mark.parametrize(
    "declaration,strict",
    [("INTEGER", ""), ("BIGINT", ""), ("DECIMAL(10,0)", ""), ("INTEGER", " STRICT")],
)
@pytest.mark.parametrize(
    "value",
    [
        "1.5",
        ".5",
        "1.0000000000000001",
        "9223372036854775808",
        "-9223372036854775809",
        "1e1000",
        "1e9999999999999999999",
        2**63,
        Decimal("9223372036854775808"),
    ],
)
def test_integer_validation_rejects_without_retaining_earlier_batches(db, minimal_conf, declaration, strict, value):
    minimal_conf.import_row_buffer = 1
    db.conn.execute(f"CREATE TABLE t(v {declaration}){strict}")
    db.conn.execute("INSERT INTO t VALUES (42)")
    db.conn.commit()
    rows = [("7",), (value,)]
    with pytest.raises(ErrInfo, match="column v.*whole numbers"):
        db.populate_table(None, "t", rows, ["v"], lambda: DataTable(["v"], rows), existing_table=True)
    assert db.conn.execute("SELECT v FROM t").fetchall() == [(42,)]
    assert not db.conn.in_transaction


@pytest.mark.parametrize(
    "value,expected",
    [
        ("7", 7),
        ("+7", 7),
        (" 7 ", 7),
        ("7.0", 7),
        ("7e0", 7),
        ("1e3", 1000),
        ("-0", 0),
        ("9223372036854775807", 2**63 - 1),
        ("-9223372036854775808", -(2**63)),
        (Decimal("7.00"), 7),
        (7.0, 7),
        (True, 1),
    ],
)
@pytest.mark.parametrize("strict", ["", " STRICT"])
def test_integral_inputs_keep_their_stored_value(db, value, expected, strict):
    db.conn.execute(f"CREATE TABLE t(v INTEGER){strict}")
    populate(db, value)
    assert db.conn.execute("SELECT v, typeof(v) FROM t").fetchall() == [(expected, "integer")]


@pytest.mark.parametrize("schema,table", [("aux", "t"), ("attached.db", "table.with.dot"), ('a"b', 't"z')])
def test_column_kinds_preserves_qualified_and_quoted_identifiers(db, schema, table):
    quote = db.quote_identifier
    db.conn.execute(f"ATTACH ':memory:' AS {quote(schema)}")
    db.conn.execute(f'CREATE TABLE {quote(schema)}.{quote(table)}("V" INTEGER, text_col TEXT, d DECIMAL(10,2))')
    db.conn.execute(f"CREATE TABLE main.{quote(table)}(v TEXT)")
    kinds = db.column_kinds(db.schema_qualified_table_name(schema, table))
    assert kinds == {"v": DT_Long, "text_col": DT_Text, "d": DT_Decimal}
    with pytest.raises(ErrInfo, match="whole numbers"):
        populate(db, "1.5", schema=schema, table=table)
    assert not db.conn.execute(f"SELECT v FROM {quote(schema)}.{quote(table)}").fetchall()
    assert not db.conn.execute(f"SELECT v FROM main.{quote(table)}").fetchall()


def test_unqualified_column_kinds_resolves_temp_before_main(db):
    db.conn.execute("CREATE TABLE main.t(v INTEGER)")
    db.conn.execute("CREATE TEMP TABLE t(v TEXT)")
    assert db.column_kinds("t") == {"v": DT_Text}
    populate(db, "1.5")
    assert db.conn.execute("SELECT v FROM temp.t").fetchall() == [("1.5",)]
    assert not db.conn.execute("SELECT v FROM main.t").fetchall()


@pytest.mark.parametrize("format", ["csv", "json", "copy-double", "copy-decimal"])
@pytest.mark.parametrize("strict", ["", " STRICT"])
def test_public_load_paths_reject_fractional_integer_values(db, tmp_path, format, strict):
    db.conn.execute(f"CREATE TABLE t(v INTEGER){strict}")
    db.conn.execute("INSERT INTO t VALUES (42)")
    db.conn.commit()
    if format == "csv":
        path = tmp_path / "rows.csv"
        path.write_text("v\n7\n1.0000000000000001\n")
        script = f'-- !x! IMPORT TO t FROM "{path}"\n'
    elif format == "json":
        path = tmp_path / "rows.json"
        path.write_text(json.dumps([{"v": 7}, {"v": 1.5}]))
        script = f'-- !x! IMPORT TO t FROM JSON "{path}"\n'
    else:
        pytest.importorskip("duckdb")
        path = tmp_path / "source.duckdb"
        import duckdb

        source = duckdb.connect(str(path))
        try:
            source.execute("CREATE TABLE source(v " + ("DOUBLE" if format == "copy-double" else "DECIMAL(20,16)") + ")")
            source.execute("INSERT INTO source VALUES (7), (1.5)")
        finally:
            source.close()
        script = f'-- !x! CONNECT TO DUCKDB(FILE="{path}") AS src\n-- !x! COPY source FROM src TO t IN initial\n'
    result = execsql.run(sql=script, connection=db)
    assert not result.success
    assert "whole numbers" in result.errors[0].message
    assert db.conn.execute("SELECT v FROM t").fetchall() == [(42,)]


DECLARATIONS = ["INTEGER", "BIGINT", "DECIMAL(10,0)", "TEXT", "REAL", "NUMERIC", "BLOB", "", "POINT"]
VALUES = [
    "7",
    "+7",
    " 7 ",
    "7.0",
    "7e0",
    "1e3",
    "-0",
    "1.5",
    ".5",
    "1.0000000000000001",
    "9223372036854775807",
    "9223372036854775808",
    "-9223372036854775809",
    "1e45",
    "0x10",
    "abc",
    "yes",
    "",
    None,
    True,
    7,
    7.5,
    Decimal("1.5"),
    Decimal("7.00"),
    b"abc",
    datetime.date(2026, 1, 2),
    datetime.datetime(2026, 1, 2, 3, 4),
]


@pytest.mark.parametrize("declaration", DECLARATIONS)
@pytest.mark.parametrize("value", VALUES, ids=str)
def test_stored_values_match_previous_sqlite_load_except_integer_rejections(db, declaration, value):
    db.conn.execute(f"CREATE TABLE t(v {declaration})")
    old_value = str(value) if type(value) in (Decimal, datetime.datetime, datetime.time) else value
    old = sqlite3.connect(":memory:")
    try:
        old.execute(f"CREATE TABLE t(v {declaration})")
        old.execute("INSERT INTO t VALUES (?)", (old_value,))
        before = old.execute("SELECT quote(v), typeof(v) FROM t").fetchone()
    finally:
        old.close()
    try:
        populate(db, value)
    except ErrInfo:
        assert declaration in ("INTEGER", "BIGINT", "DECIMAL(10,0)")
        number = Decimal(value) if not isinstance(value, Decimal) else value
        assert number != number.to_integral_value() or not -(2**63) <= number <= 2**63 - 1
        assert not db.conn.execute("SELECT v FROM t").fetchall()
    else:
        # A one-column NULL row is deliberately skipped by the existing loader.
        after = db.conn.execute("SELECT quote(v), typeof(v) FROM t").fetchall()
        assert after == ([] if value is None else [before])


def test_new_table_loading_keeps_existing_behavior(db):
    db.conn.execute("CREATE TABLE t(v INTEGER)")
    populate(db, "1.5", existing=False)
    assert db.conn.execute("SELECT v, typeof(v) FROM t").fetchall() == [(1.5, "real")]


@pytest.mark.parametrize("name", ["t); DROP TABLE t; --", "a.b.c", '"unterminated'])
def test_invalid_qualified_metadata_name_cannot_execute_sql(db, name):
    db.conn.execute("CREATE TABLE t(v INTEGER)")
    with pytest.raises(ErrInfo, match="Invalid SQLite table name"):
        db.column_kinds(name)
    assert db.table_exists("t")


def test_generated_column_metadata_and_projection_order(db):
    db.conn.execute("CREATE TABLE t(v INTEGER, note TEXT, doubled INTEGER AS (v*2))")
    assert db.column_kinds("t") == {"v": DT_Long, "note": DT_Text, "doubled": DT_Long}
    rows = [("note", "7.0")]
    db.populate_table(None, "t", rows, ["v", "note"], lambda: DataTable(["note", "v"], rows), existing_table=True)
    assert db.conn.execute("SELECT v, note, doubled FROM t").fetchall() == [(7, "note", 14)]


def test_fractional_input_in_unselected_source_column_is_not_validated(db):
    db.conn.execute("CREATE TABLE t(v INTEGER)")
    rows = [("7", "1.5")]
    db.populate_table(None, "t", rows, ["v"], lambda: DataTable(["v", "unused"], rows), existing_table=True)
    assert db.conn.execute("SELECT v FROM t").fetchall() == [(7,)]


def test_failed_load_of_noninteger_column_rolls_back_earlier_batches(db, minimal_conf):
    minimal_conf.import_row_buffer = 1
    db.conn.execute("CREATE TABLE t(v TEXT CHECK(v != 'bad'))")
    db.conn.execute("INSERT INTO t VALUES ('before')")
    db.conn.commit()
    rows = [("ok",), ("bad",)]
    with pytest.raises(ErrInfo):
        db.populate_table(None, "t", rows, ["v"], lambda: DataTable(["v"], rows), existing_table=True)
    assert db.conn.execute("SELECT v FROM t").fetchall() == [("before",)]


_INTEGER_CORRECTIONS = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "sqlite_integer_conversions.json").read_text(encoding="utf-8"),
)


@pytest.mark.parametrize("declaration", DECLARATIONS)
@pytest.mark.parametrize("case", _INTEGER_CORRECTIONS, ids=lambda case: case["name"])
def test_exact_integral_conversion_has_explicit_before_and_after_records(db, declaration, case):
    value = Decimal(case["source"]) if case["source_kind"] == "decimal" else case["source"]
    old = sqlite3.connect(":memory:")
    try:
        old.execute(f"CREATE TABLE t(v {declaration})")
        old.execute("INSERT INTO t VALUES (?)", (str(value),))
        previous, previous_type = old.execute("SELECT v, typeof(v) FROM t").fetchone()
    finally:
        old.close()
    before = {"value": repr(previous), "storage": previous_type}
    db.conn.execute(f"CREATE TABLE t(v {declaration})")
    populate(db, value)
    actual, actual_type = db.conn.execute("SELECT v, typeof(v) FROM t").fetchone()
    after = {"value": repr(actual), "storage": actual_type}
    if declaration in ("INTEGER", "BIGINT", "DECIMAL(10,0)"):
        assert case["why"]
        assert before == case["before"]
        assert after == case["after"]
        assert actual == int(Decimal(case["source"]))
    else:
        assert after == before
