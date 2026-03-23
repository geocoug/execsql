from __future__ import annotations

"""
Database adapter package for execsql.

Re-exports :class:`~execsql.db.base.Database`,
:class:`~execsql.db.base.DatabasePool`, and all nine DBMS-specific adapter
classes so callers can do::

    from execsql.db import PostgresDatabase, DatabasePool

rather than importing from the individual sub-modules.
"""

from execsql.db.base import Database, DatabasePool
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
    "Database",
    "DatabasePool",
    "AccessDatabase",
    "DsnDatabase",
    "SqlServerDatabase",
    "PostgresDatabase",
    "OracleDatabase",
    "SQLiteDatabase",
    "DuckDBDatabase",
    "MySQLDatabase",
    "FirebirdDatabase",
]
