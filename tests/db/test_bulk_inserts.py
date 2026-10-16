"""IMPORT and COPY insert each batch of rows through the adapter's row inserter.

The default runs ``executemany``; DuckDB binds many rows in one
``INSERT ... VALUES``, which must store exactly what ``executemany`` stores.
"""

from __future__ import annotations

import datetime
import decimal
import importlib.util
import sys
from unittest.mock import MagicMock

import pytest

from execsql.db.base import Database


def test_the_default_inserter_runs_executemany():
    db = MagicMock(spec=Database)
    db.paramsubs.return_value = "?,?"
    curs = MagicMock()
    Database.row_inserter(db, curs, '"t"', ['"a"', '"b"'])([[1, 2]])
    curs.executemany.assert_called_once_with('insert into "t" ("a","b") values (?,?);', [[1, 2]])


# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------

duckdb = pytest.importorskip("duckdb")
from execsql.db import duckdb as duckdb_adapter  # noqa: E402

_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
# Every Python type a converted IMPORT or COPY row can hold, with edge values.
_VALUES = [
    None,
    0,
    -7,
    2**31,
    2**63 - 1,
    True,
    False,
    0.1,
    1.0000000000000002,
    1e20,
    -0.0,
    float("inf"),
    float("nan"),
    3.0,
    decimal.Decimal("0.1"),
    decimal.Decimal("1.50"),
    decimal.Decimal("1E+3"),
    decimal.Decimal("-0.000"),
    decimal.Decimal("123456789012345678901234567890.123"),
    "",
    "abc",
    "a\tb",
    "a\nb",
    "back\\slash",
    "\\N",
    "quote'\"",
    "Ünïcødé",
    "  pad  ",
    "5",
    "5.7",
    "t",
    "2020-01-02",
    "2020-01-02 03:04:05",
    "{1,2}",
    datetime.date(2020, 1, 2),
    datetime.datetime(2020, 1, 2, 3, 4, 5),
    datetime.datetime(2020, 1, 2, 3, 4, 5, 123456),
    datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=_TZ),
    datetime.time(1, 2, 3),
    datetime.time(1, 2, 3, 400000),
    b"\x00\x01ab",
    bytearray(b"xy"),
]
_COLUMN_TYPES = [
    "varchar",
    "integer",
    "bigint",
    "decimal(18,3)",
    "double",
    "boolean",
    "date",
    "timestamp",
    "timestamptz",
    "blob",
]


def _stored(typ: str, rows: list[list[object]], how: str) -> object:
    con = duckdb.connect()
    con.execute("set timezone = 'America/Los_Angeles'")
    con.execute(f"create table t (i integer, v {typ})")
    try:
        if how == "executemany":
            con.executemany("insert into t (i, v) values (?, ?)", rows)
        else:
            duckdb_adapter.insert_rows(con, "t", ["i", "v"], rows)
    except duckdb.Error as e:
        return type(e).__name__
    return con.execute("select v::varchar from t order by i").fetchall()


@pytest.mark.parametrize("column_type", _COLUMN_TYPES)
def test_duckdb_stores_what_executemany_stores(column_type, monkeypatch):
    """Each value alone, and all of them in one statement, store (or fail) exactly as with executemany."""
    monkeypatch.setattr(duckdb_adapter, "_PARAMS_PER_STATEMENT", 4)  # 2 rows per statement
    for value in _VALUES:
        rows = [[0, value]]
        assert _stored(column_type, rows, "insert_rows") == _stored(column_type, rows, "executemany"), value
    monkeypatch.setattr(duckdb_adapter, "_PARAMS_PER_STATEMENT", 10_000)  # every value in one statement
    texts = [[i, v] for i, v in enumerate(_VALUES) if isinstance(v, str) or v is None]
    assert _stored(column_type, texts, "insert_rows") == _stored(column_type, texts, "executemany")


def _pandas_seen_by(monkeypatch, installed: bool) -> tuple[list[object], object]:
    """Run insert_rows with pandas (not) installed; return what sys.modules held for it."""
    monkeypatch.delitem(sys.modules, "pandas", raising=False)
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: (MagicMock() if installed else None) if name == "pandas" else real_find_spec(name, *a),
    )
    seen: list[object] = []
    curs = MagicMock()
    curs.execute.side_effect = lambda *_a: seen.append(sys.modules.get("pandas", "absent"))
    duckdb_adapter.insert_rows(curs, "t", ["a"], [[1], [2]])
    return seen, sys.modules.get("pandas", "absent")


def test_duckdb_skips_the_pandas_lookup_only_while_inserting(monkeypatch):
    during, after = _pandas_seen_by(monkeypatch, installed=False)
    assert during == [None]
    assert after == "absent"


def test_duckdb_leaves_an_installed_pandas_alone(monkeypatch):
    during, after = _pandas_seen_by(monkeypatch, installed=True)
    assert during == ["absent"]
    assert after == "absent"


def test_copy_into_duckdb_loads_every_row(tmp_path):
    from execsql import run

    src = tmp_path / "src.db"
    run(
        sql="create table data (id integer, name text, amount numeric);\n"
        "insert into data values (1, 'a', 1.5), (2, '', null), (3, null, 2.25);\n",
        dsn=f"sqlite:///{src}",
        new_db=True,
    )
    target = f"duckdb:///{tmp_path / 'target.duckdb'}"
    result = run(
        sql="create table data (id integer, name varchar, amount double);\n"
        f"-- !x! connect to sqlite(file={src}) as src\n"
        "-- !x! copy data from src to data in initial\n",
        dsn=target,
        new_db=True,
    )
    assert result.success, result.errors
    con = duckdb.connect(str(tmp_path / "target.duckdb"))
    assert con.execute("select * from data order by id").fetchall() == [(1, "a", 1.5), (2, "", None), (3, None, 2.25)]
