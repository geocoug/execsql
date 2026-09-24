"""
Real-database fixtures for importer round-trip tests.

The exporter suite proved the point in one direction: a stub database cannot
show what a driver actually returns, and fourteen bugs were hiding in that gap.
The importers have the same gap in the opposite direction — nothing in the
suite has ever written a real file, imported it through a real driver, and
checked what landed in the table.

``import_db`` gives each test a live connection with no tables of its own; the
test writes the file, imports it, and queries the result back.  Backends are
probed once per session, so a machine with no server listening skips instantly
rather than re-dialling for every parametrised test.
"""

from __future__ import annotations

import datetime
import os
import socket
from decimal import Decimal

import pytest

import execsql.state as _state

TABLE_NAME = "import_roundtrip"

#: Every table an importer test may create.  All are dropped before and after
#: each test: PostgreSQL and MySQL keep their server between tests, so a table
#: left behind makes the next `is_new` import fail with "already exists".
TEST_TABLES = (TABLE_NAME, "nl_table")

#: The values every importer test writes to a file and expects back.
#: Each one exists because it is a plausible way for an importer to go wrong:
#: a quote that ends a field early, a delimiter inside a value, a newline that
#: splits a row, an empty field that should be NULL rather than "".
HEADERS = ["id", "n_int", "n_dec", "t_plain", "t_unicode", "t_awkward", "d_date"]

ROWS = [
    [
        1,
        -42,
        Decimal("1234.567"),
        "plain",
        "café — naïve ± 30° ⚡",
        'has "quotes", a comma, and a\nnewline',
        datetime.date(2026, 9, 24),
    ],
    [2, None, None, None, None, None, None],
]


def _server_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    """True if something accepts a TCP connection at *host*:*port*."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _sqlite_db(tmp_path):
    from execsql.db.sqlite import SQLiteDatabase

    return SQLiteDatabase(str(tmp_path / "import.sqlite"))


def _duckdb_db(tmp_path):
    pytest.importorskip("duckdb", reason="duckdb not installed")
    from execsql.db.duckdb import DuckDBDatabase

    return DuckDBDatabase(str(tmp_path / "import.duckdb"))


def _postgres_db(tmp_path):
    pytest.importorskip("psycopg", reason="psycopg (psycopg3) not installed")
    host = os.environ.get("EXECSQL_PG_HOST", "localhost")
    port = int(os.environ.get("EXECSQL_PG_PORT", "5432"))
    if not _server_listening(host, port):
        raise OSError(f"nothing listening at {host}:{port}")
    from execsql.db.postgres import PostgresDatabase

    db = PostgresDatabase(
        host,
        os.environ.get("EXECSQL_PG_DATABASE", "execsql_test"),
        user_name=os.environ.get("EXECSQL_PG_USER", "execsql"),
        need_passwd=False,
        port=port,
        password=os.environ.get("EXECSQL_PG_PASSWORD", "execsql"),
    )
    db.open_db()
    return db


def _mysql_db(tmp_path):
    pytest.importorskip("pymysql", reason="pymysql not installed")
    host = os.environ.get("EXECSQL_MYSQL_HOST", "localhost")
    port = int(os.environ.get("EXECSQL_MYSQL_PORT", "3306"))
    if not _server_listening(host, port):
        raise OSError(f"nothing listening at {host}:{port}")
    from execsql.db.mysql import MySQLDatabase

    db = MySQLDatabase(
        host,
        os.environ.get("EXECSQL_MYSQL_DATABASE", "execsql_test"),
        user_name=os.environ.get("EXECSQL_MYSQL_USER", "execsql"),
        need_passwd=False,
        port=port,
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

#: Why a backend is unusable, cached after the first attempt — see the exporter
#: conftest for what re-dialling per test cost on Windows CI.
_unusable: dict[str, str] = {}


@pytest.fixture(params=sorted(_BACKENDS), ids=sorted(_BACKENDS))
def import_db(request, tmp_path, minimal_conf):
    """A live Tier 1 connection with the round-trip table dropped and ready."""
    dbms = request.param
    if dbms in _unusable:
        pytest.skip(_unusable[dbms])
    try:
        db = _BACKENDS[dbms](tmp_path)
    except pytest.skip.Exception:
        raise
    except Exception as exc:
        _unusable[dbms] = f"{dbms} not reachable: {type(exc).__name__}: {exc}"
        pytest.skip(_unusable[dbms])

    # minimal_conf covers the pure modules.  The import path and the adapters
    # read a handful more — PostgreSQL's COPY FROM needs a buffer size, and
    # without it the import fails with an AttributeError wrapped in "Can't
    # import from file to table".
    _state.conf.scan_lines = 100
    _state.conf.import_common_cols_only = False
    _state.conf.import_buffer = 32 * 1024
    _state.conf.import_row_buffer = 1000
    _state.conf.export_row_buffer = 1000
    _state.conf.import_progress_interval = 0

    from execsql.db.base import DatabasePool

    pool = DatabasePool()
    pool.add("initial", db)
    _state.dbs = pool

    _drop(db)
    db.dbms_name = dbms  # type: ignore[attr-defined]
    yield db
    _drop(db)
    db.close()


def requires_local_infile(db) -> None:
    """Skip when MySQL's server-side LOAD DATA LOCAL INFILE is switched off.

    The importer's fast path uses it, and MySQL 8 disables it by default. CI
    turns it on; a contributor running a stock container would otherwise see a
    failure that says nothing about execsql.
    """
    if getattr(db, "dbms_name", None) != "mysql":
        return
    try:
        with db._cursor() as curs:
            curs.execute("show global variables like 'local_infile';")
            row = curs.fetchone()
    except Exception:
        return
    if row and str(row[1]).upper() not in ("ON", "1"):
        pytest.skip(
            "MySQL server has local_infile=OFF; start it with --local-infile=1 to exercise the LOAD DATA import path",
        )


def _drop(db) -> None:
    for table in TEST_TABLES:
        try:
            with db._cursor() as curs:
                curs.execute(f"drop table if exists {table};")
            db.commit()
        except Exception:
            pass


def write_csv(path, rows=None, headers=None, delimiter=",") -> str:
    """Write the round-trip values as a real CSV file, quoting as the stdlib does."""
    import csv

    rows = ROWS if rows is None else rows
    headers = HEADERS if headers is None else headers
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["" if v is None else str(v) for v in row])
    return str(path)
