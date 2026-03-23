"""
Tests for execsql.db.factory — database connection convenience constructors.

Tests fall into two categories:

1. Error-path tests: functions that raise ErrInfo when a required file does
   not exist.  These are fully self-contained and need no real driver.

2. Happy-path tests for in-memory databases (SQLite :memory:, DuckDB :memory:):
   verified only when the corresponding driver is available.
"""

from __future__ import annotations

import pytest

from execsql.db.factory import db_Access, db_SQLite, db_DuckDB
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Error paths — non-existent files
# ---------------------------------------------------------------------------


class TestDbAccessErrors:
    def test_nonexistent_file_raises(self):
        with pytest.raises(ErrInfo):
            db_Access("/tmp/__does_not_exist__.mdb")


class TestDbSQLiteErrors:
    def test_nonexistent_file_raises(self):
        with pytest.raises(ErrInfo):
            db_SQLite("/tmp/__does_not_exist__.db")


class TestDbDuckDBErrors:
    def test_nonexistent_file_raises(self):
        try:
            import duckdb  # noqa: F401
        except ImportError:
            pytest.skip("duckdb not installed")
        with pytest.raises(ErrInfo):
            db_DuckDB("/tmp/__does_not_exist__.duckdb")


# ---------------------------------------------------------------------------
# Happy path — in-memory databases
# ---------------------------------------------------------------------------


class TestDbSQLiteInMemory:
    def test_new_db_memory_returns_sqlite(self):
        db = db_SQLite(":memory:", new_db=True)
        assert db is not None
        assert db.conn is not None
        db.close()


class TestDbDuckDBInMemory:
    def test_new_db_memory_returns_duckdb(self):
        try:
            import duckdb  # noqa: F401
        except ImportError:
            pytest.skip("duckdb not installed")
        db = db_DuckDB(":memory:", new_db=True)
        assert db is not None
        assert db.conn is not None
        db.close()
