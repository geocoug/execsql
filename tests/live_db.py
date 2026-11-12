"""
Live Tier 1 database backends for tests that need a real driver.

Shared by the importer round trips and the adapter tests.  Kept as a plain
module rather than a conftest so both can import it: ``pytest_plugins`` in a
non-root conftest cannot be registered twice.

A backend whose driver is missing or whose server is not listening is probed
once per session and skipped thereafter — re-dialling per test is what pushed
the Windows CI jobs from fifteen minutes to thirty.

EXECSQL_REQUIRED_BACKENDS lists backends provisioned for this run. Their
connection and driver failures are errors, never cached as optional skips.
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
    return _mysql_family_db("MYSQL", "3306")


def _mariadb_db(tmp_path):
    return _mysql_family_db("MARIADB", "3307")


def _mysql_family_db(prefix, default_port):
    pytest.importorskip("pymysql", reason="pymysql not installed")
    host = os.environ.get(f"EXECSQL_{prefix}_HOST", "localhost")
    port = int(os.environ.get(f"EXECSQL_{prefix}_PORT", default_port))
    if not _server_listening(host, port):
        raise OSError(f"nothing listening at {host}:{port}")
    from execsql.db.mysql import MySQLDatabase

    db = MySQLDatabase(
        host,
        os.environ.get(f"EXECSQL_{prefix}_DATABASE", "execsql_test"),
        user_name=os.environ.get(f"EXECSQL_{prefix}_USER", "execsql"),
        need_passwd=False,
        port=port,
        password=os.environ.get(f"EXECSQL_{prefix}_PASSWORD", "execsql"),
    )
    db.open_db()
    return db


def _sqlserver_db(tmp_path):
    pytest.importorskip("pyodbc", reason="pyodbc not installed")
    host = os.environ.get("EXECSQL_MSSQL_HOST", "localhost")
    port = int(os.environ.get("EXECSQL_MSSQL_PORT", "1433"))
    if not _server_listening(host, port):
        raise OSError(f"nothing listening at {host}:{port}")
    from execsql.db.sqlserver import SqlServerDatabase

    return SqlServerDatabase(
        server_name=f"{host},{port}",
        db_name=os.environ.get("EXECSQL_MSSQL_DATABASE", "execsql_test"),
        user_name=os.environ.get("EXECSQL_MSSQL_USER", "sa"),
        password=os.environ.get("EXECSQL_MSSQL_PASSWORD", "ExecSql_Test123!"),
        trust_server_certificate=True,
    )


#: Backends ``open_backend`` can open that are not in ``BACKEND_NAMES``: the
#: importer round trips parametrize over that list and do not cover these.
_OTHER_BACKENDS = {"sqlserver": _sqlserver_db, "mariadb": _mariadb_db}


_BACKENDS = {
    "sqlite": _sqlite_db,
    "duckdb": _duckdb_db,
    "postgres": _postgres_db,
    "mysql": _mysql_db,
}

#: Why a backend is unusable, cached after the first attempt — see the exporter
#: conftest for what re-dialling per test cost on Windows CI.
_unusable: dict[str, str] = {}


def required_backends() -> set[str]:
    """Read the explicitly required test backends; reject misspelled names."""
    names = {name.strip() for name in os.environ.get("EXECSQL_REQUIRED_BACKENDS", "").split(",") if name.strip()}
    unknown = names - {*_BACKENDS, *_OTHER_BACKENDS, "mariadb"}
    if unknown:
        raise pytest.UsageError(f"Unknown EXECSQL_REQUIRED_BACKENDS: {', '.join(sorted(unknown))}")
    return names


def backend_unavailable(dbms: str, reason: str) -> None:
    """Fail for a required backend, or skip an optional local backend."""
    if dbms in required_backends():
        pytest.fail(f"Required database backend {dbms}: {reason}", pytrace=False)
    pytest.skip(reason)


def open_backend(dbms: str, tmp_path, *, factory=None):
    """Open *dbms*, failing unavailable required backends instead of skipping."""
    # Validate the selection even when the requested backend is available.
    required = dbms in required_backends()
    if dbms in _unusable:
        backend_unavailable(dbms, _unusable[dbms])
    connect = factory if factory is not None else {**_BACKENDS, **_OTHER_BACKENDS}[dbms]
    try:
        return connect(tmp_path)
    except pytest.skip.Exception as exc:
        backend_unavailable(dbms, str(exc))
    except Exception as exc:
        reason = f"{dbms} not reachable: {type(exc).__name__}: {exc}"
        if not required:
            _unusable[dbms] = reason
        backend_unavailable(dbms, reason)


BACKEND_NAMES = sorted(_BACKENDS)
