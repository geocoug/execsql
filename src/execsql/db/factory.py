from __future__ import annotations

"""
Database connection factory for execsql.

Provides one convenience constructor function per supported DBMS
(``db_Access``, ``db_Postgres``, ``db_SQLite``, ``db_MySQL``,
``db_Oracle``, ``db_Firebird``, ``db_SqlServer``, ``db_DuckDB``,
``db_Dsn``) that instantiate the appropriate adapter subclass and handle
common setup such as prompting for a password when required.  These
functions are the canonical way to open a new database connection from
:mod:`execsql.cli` and the connection-related metacommand handlers.
"""

from pathlib import Path

from execsql.exceptions import ErrInfo
from execsql.db.access import AccessDatabase
from execsql.db.dsn import DsnDatabase
from execsql.db.sqlserver import SqlServerDatabase
from execsql.db.postgres import PostgresDatabase
from execsql.db.oracle import OracleDatabase
from execsql.db.sqlite import SQLiteDatabase
from execsql.db.duckdb import DuckDBDatabase
from execsql.db.mysql import MySQLDatabase
from execsql.db.firebird import FirebirdDatabase

__all__ = [
    "db_Access",
    "db_Dsn",
    "db_DuckDB",
    "db_Firebird",
    "db_MySQL",
    "db_Oracle",
    "db_Postgres",
    "db_SQLite",
    "db_SqlServer",
]


def db_Access(
    Access_fn: str,
    pw_needed: bool = False,
    user: str | None = None,
    encoding: str | None = None,
) -> AccessDatabase:
    if not Path(Access_fn).exists():
        raise ErrInfo(
            type="error",
            other_msg=f'Access database file "{Access_fn}" does not exist.',
        )
    return AccessDatabase(Access_fn, need_passwd=pw_needed, user_name=user, encoding=encoding)


def db_Postgres(
    server_name: str,
    database_name: str,
    user: str | None = None,
    pw_needed: bool = True,
    port: int | None = None,
    encoding: str | None = None,
    new_db: bool = False,
    password: str | None = None,
) -> PostgresDatabase:
    return PostgresDatabase(server_name, database_name, user, pw_needed, port, new_db=new_db, password=password)


def db_SQLite(
    sqlite_fn: str,
    new_db: bool = False,
    encoding: str | None = None,
) -> SQLiteDatabase:
    if new_db:
        from execsql.utils.fileio import check_dir

        check_dir(sqlite_fn)
    else:
        if not Path(sqlite_fn).exists():
            raise ErrInfo(
                type="error",
                other_msg=f'SQLite database file "{sqlite_fn}" does not exist.',
            )
    return SQLiteDatabase(sqlite_fn)


def db_SqlServer(
    server_name: str,
    database_name: str,
    user: str | None = None,
    pw_needed: bool = True,
    port: int | None = None,
    encoding: str | None = None,
) -> SqlServerDatabase:
    return SqlServerDatabase(server_name, database_name, user, pw_needed, port, encoding)


def db_MySQL(
    server_name: str,
    database_name: str,
    user: str | None = None,
    pw_needed: bool = True,
    port: int | None = None,
    encoding: str | None = None,
) -> MySQLDatabase:
    return MySQLDatabase(server_name, database_name, user, pw_needed, port, encoding)


def db_DuckDB(
    duckdb_fn: str,
    new_db: bool = False,
    encoding: str | None = None,
) -> DuckDBDatabase:
    if new_db:
        from execsql.utils.fileio import check_dir

        check_dir(duckdb_fn)
    else:
        if not Path(duckdb_fn).exists():
            raise ErrInfo(
                type="error",
                other_msg=f'DuckDB database file "{duckdb_fn}" does not exist.',
            )
    return DuckDBDatabase(duckdb_fn)


def db_Oracle(
    server_name: str,
    database_name: str,
    user: str | None = None,
    pw_needed: bool = True,
    port: int | None = None,
    encoding: str | None = None,
) -> OracleDatabase:
    return OracleDatabase(server_name, database_name, user, pw_needed, port, encoding)


def db_Firebird(
    server_name: str,
    database_name: str,
    user: str | None = None,
    pw_needed: bool = True,
    port: int | None = None,
    encoding: str | None = None,
) -> FirebirdDatabase:
    return FirebirdDatabase(server_name, database_name, user, pw_needed, port, encoding)


def db_Dsn(
    dsn_name: str,
    user: str | None = None,
    pw_needed: bool = True,
    encoding: str | None = None,
) -> DsnDatabase:
    return DsnDatabase(dsn_name=dsn_name, user_name=user, need_passwd=pw_needed, encoding=encoding)
