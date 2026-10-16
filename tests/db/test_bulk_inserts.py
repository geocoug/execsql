"""IMPORT and COPY insert each batch of rows with the adapter's bulk path.

PostgreSQL copies a batch with ``COPY ... FROM STDIN`` inside a savepoint
and falls back to ``executemany`` when COPY rejects it; DuckDB binds many
rows in one ``INSERT ... VALUES``.  Both must store what ``executemany``
stored.
"""

from __future__ import annotations

import contextlib
import decimal
import importlib.util
import sys
from unittest.mock import MagicMock, patch

import pytest

from execsql.db.base import Database
from execsql.db.postgres import PostgresDatabase


class _CopyFails(Exception):
    pass


class _FakePgCursor:
    """Records the statements a PostgreSQL row inserter runs."""

    def __init__(self, copy_fails: bool = False) -> None:
        self.log: list[str] = []
        self.copy_fails = copy_fails

    def execute(self, sql, params=None):
        self.log.append(sql)

    def executemany(self, sql, rows):
        self.log.append(f"executemany {len(rows)}")

    @contextlib.contextmanager
    def copy(self, sql):
        self.log.append(sql)
        copy = MagicMock()
        yield copy
        if self.copy_fails:
            raise _CopyFails("invalid input syntax for type integer")


def _pg() -> PostgresDatabase:
    with patch.object(PostgresDatabase, "open_db", return_value=None):
        return PostgresDatabase("host", "db", "user", need_passwd=False)


def test_postgres_copies_each_batch_inside_a_savepoint():
    curs = _FakePgCursor()
    insert = _pg().row_inserter(curs, '"t"', ['"a"', '"b"'])
    insert([[1, "x"], [2, "y"]])
    assert curs.log == [
        "savepoint execsql_copy",
        'copy "t" ("a","b") from stdin',
        "release savepoint execsql_copy",
    ]


def test_postgres_falls_back_to_insert_when_copy_rejects_a_batch():
    curs = _FakePgCursor(copy_fails=True)
    insert = _pg().row_inserter(curs, '"t"', ['"a"'])
    insert([[decimal.Decimal("5.70")]])
    insert([[decimal.Decimal("6.20")]])  # the rest of the load skips COPY
    assert curs.log == [
        "savepoint execsql_copy",
        'copy "t" ("a") from stdin',
        "rollback to savepoint execsql_copy",
        "executemany 1",
        "executemany 1",
    ]


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

_AWKWARD = [  # (column type, values): conversions executemany performs
    ("integer", [decimal.Decimal("5.70"), "5", True, None]),
    ("varchar", [5, "", None, "a'b"]),
    ("double", [1, 2.5, decimal.Decimal("3.25"), None]),
    ("date", ["2020-01-02", None, "2021-03-04", "2022-05-06"]),
]


@pytest.mark.parametrize(("column_type", "values"), _AWKWARD, ids=[c for c, _ in _AWKWARD])
def test_duckdb_stores_what_executemany_stores(column_type, values, monkeypatch):
    monkeypatch.setattr(duckdb_adapter, "_PARAMS_PER_STATEMENT", 4)  # 2 rows per statement
    rows = [[i, v] for i, v in enumerate(values)]
    stored = {}
    for how in ("executemany", "insert_rows"):
        con = duckdb.connect()
        con.execute(f"create table t (a integer, v {column_type})")
        if how == "executemany":
            con.executemany("insert into t values (?, ?)", rows)
        else:
            duckdb_adapter.insert_rows(con, "t", ["a", "v"], rows)
        stored[how] = con.execute("select v from t order by a").fetchall()
    assert stored["insert_rows"] == stored["executemany"]


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
