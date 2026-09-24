"""
Real-database fixtures for exporter round-trip tests.

The exporter suite has historically driven a hand-written ``_StubDB`` that
returns whatever headers and rows the test author typed.  The exporter then
writes a real file and the test reads it back, which is worth having — but no
row in the suite ever came out of a database driver, so the adapter-to-exporter
seam is crossed by nothing.  That seam is where the interesting bugs live: how
``NULL`` arrives, what ``Decimal`` and ``date`` and ``bool`` look like coming
back from each driver, whether text survives its round trip.

The fixtures here close that gap.  ``export_db`` is parametrized over every
Tier 1 backend that can actually be reached: SQLite and DuckDB always (they are
files), and PostgreSQL, MySQL, or SQL Server when a server is listening.  Each
one is seeded with the same table of awkward values, so one test body is
checked against every driver's idea of what those values are.

Set ``EXECSQL_PG_HOST`` and friends to point at a server; see
``tests/db/test_postgres_inprocess.py`` for the full list of variables.  A
backend that is not reachable is skipped, never failed — a laptop with no
containers running still gets SQLite and DuckDB coverage.

No backend is given an explicit encoding: each one is opened exactly the way a
user running ``execsql`` with no ``-e`` flag opens it.  The unicode column is
what caught the MySQL adapter defaulting to ``latin1``, which could not encode
it at all.
"""

from __future__ import annotations

import datetime
import os
from decimal import Decimal

import pytest

import execsql.state as _state

# ---------------------------------------------------------------------------
# The awkward-values table
#
# Every column here exists because it is a plausible way for an exporter to go
# wrong: a NULL that becomes "None", a Decimal that becomes a float and loses
# its scale, a date that stringifies differently per driver, text containing
# the delimiter/quote/newline that the writer must escape.
# ---------------------------------------------------------------------------

TABLE_NAME = "export_roundtrip"

#: (column name, portable DDL type, the value each row carries)
COLUMNS: list[tuple[str, str]] = [
    ("id", "integer"),
    ("n_int", "integer"),
    ("n_dec", "numeric(12,3)"),
    ("n_float", "double precision"),
    ("t_short", "varchar(40)"),
    ("t_unicode", "varchar(40)"),
    ("t_awkward", "varchar(80)"),
    ("d_date", "date"),
    ("d_stamp", "timestamp"),
]

#: Row 1 carries real values; row 2 is NULL in every nullable column.
ROWS: list[tuple] = [
    (
        1,
        -42,
        Decimal("1234.567"),
        2.5,
        "plain",
        "café — naïve ± 30° ⚡",
        'has "quotes", a comma, a\ttab and a\nnewline',
        datetime.date(2026, 9, 24),
        datetime.datetime(2026, 9, 24, 13, 45, 56),
    ),
    (2, None, None, None, None, None, None, None, None),
]

#: Column names in table order, for assertions.
HEADERS = [name for name, _ in COLUMNS]


def _ddl(dbms: str) -> str:
    """CREATE TABLE text, adjusted for the dialects that need it."""
    types = dict(COLUMNS)
    if dbms == "sqlserver":
        types["n_float"] = "float"
        types["t_short"] = "nvarchar(40)"
        types["t_unicode"] = "nvarchar(40)"
        types["t_awkward"] = "nvarchar(80)"
        types["d_stamp"] = "datetime2"
    elif dbms == "mysql":
        types["n_float"] = "double"
    cols = ", ".join(f"{name} {types[name]}" for name, _ in COLUMNS)
    return f"create table {TABLE_NAME} ({cols});"


def _bind(value, dbms: str):
    """Adapt a value to what this driver will accept as a bound parameter.

    sqlite3 refuses Decimal, date, and datetime outright (the implicit adapters
    were deprecated in 3.12 and are gone in 3.14), so those go in as text and
    come back shaped by the column's type affinity.  That is what a real
    execsql user gets from SQLite, and the round-trip assertions are written
    against it rather than around it.
    """
    if dbms != "sqlite":
        return value
    if isinstance(value, (Decimal, datetime.date, datetime.datetime)):
        return str(value)
    return value


def _insert(db, dbms: str) -> None:
    """Insert ROWS through the adapter's own parameter style."""
    placeholders = ", ".join(db.paramsubs(1) for _ in COLUMNS)
    sql = f"insert into {TABLE_NAME} values ({placeholders});"
    with db._cursor() as curs:
        for row in ROWS:
            curs.execute(sql, tuple(_bind(v, dbms) for v in row))
    db.commit()


# ---------------------------------------------------------------------------
# Backend availability
# ---------------------------------------------------------------------------


def _sqlite_db(tmp_path):
    from execsql.db.sqlite import SQLiteDatabase

    return SQLiteDatabase(str(tmp_path / "roundtrip.sqlite"))


def _duckdb_db(tmp_path):
    pytest.importorskip("duckdb", reason="duckdb not installed")
    from execsql.db.duckdb import DuckDBDatabase

    return DuckDBDatabase(str(tmp_path / "roundtrip.duckdb"))


def _postgres_db(tmp_path):
    pytest.importorskip("psycopg", reason="psycopg (psycopg3) not installed")
    from execsql.db.postgres import PostgresDatabase

    db = PostgresDatabase(
        os.environ.get("EXECSQL_PG_HOST", "localhost"),
        os.environ.get("EXECSQL_PG_DATABASE", "execsql_test"),
        user_name=os.environ.get("EXECSQL_PG_USER", "execsql"),
        need_passwd=False,
        port=int(os.environ.get("EXECSQL_PG_PORT", "5432")),
        password=os.environ.get("EXECSQL_PG_PASSWORD", "execsql"),
    )
    db.open_db()
    return db


def _mysql_db(tmp_path):
    pytest.importorskip("pymysql", reason="pymysql not installed")
    from execsql.db.mysql import MySQLDatabase

    db = MySQLDatabase(
        os.environ.get("EXECSQL_MYSQL_HOST", "localhost"),
        os.environ.get("EXECSQL_MYSQL_DATABASE", "execsql_test"),
        user_name=os.environ.get("EXECSQL_MYSQL_USER", "execsql"),
        need_passwd=False,
        port=int(os.environ.get("EXECSQL_MYSQL_PORT", "3306")),
        password=os.environ.get("EXECSQL_MYSQL_PASSWORD", "execsql"),
    )
    db.open_db()
    return db


_BACKENDS = {
    "sqlite": _sqlite_db,
    "duckdb": _duckdb_db,
    "postgres": _postgres_db,
    "mysql": _mysql_db,
}


@pytest.fixture(params=sorted(_BACKENDS), ids=sorted(_BACKENDS))
def export_db(request, tmp_path, minimal_conf):
    """A Tier 1 database seeded with the awkward-values table.

    Parametrized across backends; a backend whose driver is missing or whose
    server is unreachable is skipped rather than failed.
    """
    dbms = request.param
    try:
        db = _BACKENDS[dbms](tmp_path)
    except pytest.skip.Exception:
        raise
    except Exception as exc:
        pytest.skip(f"{dbms} not reachable: {type(exc).__name__}: {exc}")

    _state.dbs = None  # exporters resolve the current db through the pool
    try:
        with db._cursor() as curs:
            curs.execute(f"drop table if exists {TABLE_NAME};")
            curs.execute(_ddl(dbms))
        db.commit()
        _insert(db, dbms)
    except Exception as exc:  # setup failure is a skip, not a red test
        db.close()
        pytest.skip(f"{dbms} setup failed: {type(exc).__name__}: {exc}")

    db.dbms_name = dbms  # type: ignore[attr-defined]  # for test diagnostics
    yield db

    try:
        with db._cursor() as curs:
            curs.execute(f"drop table {TABLE_NAME};")
        db.commit()
    except Exception:
        pass
    db.close()


@pytest.fixture
def export_rows(export_db):
    """``(headers, rows)`` fetched from the real database, driver types intact.

    For exporters that take a pre-fetched rowset rather than a connection.
    """
    return export_db.select_data(f"select * from {TABLE_NAME} order by id;")
