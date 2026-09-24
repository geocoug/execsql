"""
Live Tier 1 database backends for tests that need a real driver.

Shared by the importer round trips and the adapter tests.  Kept as a plain
module rather than a conftest so both can import it: ``pytest_plugins`` in a
non-root conftest cannot be registered twice.

A backend whose driver is missing or whose server is not listening is probed
once per session and skipped thereafter — re-dialling per test is what pushed
the Windows CI jobs from fifteen minutes to thirty.
"""

from __future__ import annotations

import os
import socket

import pytest


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


def open_backend(dbms: str, tmp_path):
    """Open *dbms*, or skip with the cached reason if it is unusable."""
    if dbms in _unusable:
        pytest.skip(_unusable[dbms])
    try:
        return _BACKENDS[dbms](tmp_path)
    except pytest.skip.Exception:
        raise
    except Exception as exc:
        _unusable[dbms] = f"{dbms} not reachable: {type(exc).__name__}: {exc}"
        pytest.skip(_unusable[dbms])


BACKEND_NAMES = sorted(_BACKENDS)
