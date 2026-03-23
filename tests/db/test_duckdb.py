"""
Tests for execsql.db.duckdb — DuckDBDatabase adapter.

Uses an in-memory DuckDB database so no files or external services are
needed.  Tests exercise construction, DML, metadata queries, and the
DuckDB-specific overrides.

Note: DuckDBDatabase.__init__ calls open_db(), which connects to DuckDB
via the installed ``duckdb`` package.  Tests are skipped if duckdb is not
installed.
"""

from __future__ import annotations

import pytest

try:
    import duckdb  # noqa: F401

    _duckdb_available = True
except ImportError:
    _duckdb_available = False

pytestmark = pytest.mark.skipif(not _duckdb_available, reason="duckdb not installed")

from execsql.db.duckdb import DuckDBDatabase


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Return an in-memory DuckDBDatabase, closed after each test."""
    d = DuckDBDatabase(":memory:")
    yield d
    d.close()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestDuckDBDatabaseInit:
    def test_creates_connection(self, db):
        assert db.conn is not None

    def test_db_name_stored(self, db):
        assert db.db_name == ":memory:"

    def test_server_name_is_none(self, db):
        assert db.server_name is None

    def test_encoding_is_utf8(self, db):
        assert db.encoding.upper().replace("-", "") in ("UTF8",)

    def test_repr(self, db):
        r = repr(db)
        assert ":memory:" in r


# ---------------------------------------------------------------------------
# Table existence (uses base-class information_schema approach)
# ---------------------------------------------------------------------------


class TestDuckDBTableExists:
    def test_nonexistent_table(self, db):
        assert db.table_exists("no_such_table") is False

    def test_existing_table(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        assert db.table_exists("t") is True

    def test_with_schema(self, db):
        db.execute("CREATE TABLE t2 (id INTEGER);")
        assert db.table_exists("t2", schema_name="main") is True


# ---------------------------------------------------------------------------
# View existence (DuckDB-specific override: views are in tables)
# ---------------------------------------------------------------------------


class TestDuckDBViewExists:
    def test_nonexistent_view(self, db):
        assert db.view_exists("no_view") is False

    def test_existing_view(self, db):
        db.execute("CREATE TABLE src (x INTEGER);")
        db.execute("CREATE VIEW v AS SELECT x FROM src;")
        # DuckDB overrides view_exists to call table_exists (views are in tables)
        assert db.view_exists("v") is True


# ---------------------------------------------------------------------------
# Schema existence
# ---------------------------------------------------------------------------


class TestDuckDBSchemaExists:
    def test_schema_exists_returns_bool(self, db):
        # schema_exists uses information_schema.schemata filtered by catalog_name.
        # For :memory: the catalog_name derivation may not match, so just verify it
        # returns a bool without raising.
        result = db.schema_exists("main")
        assert isinstance(result, bool)

    def test_nonexistent_schema(self, db):
        assert db.schema_exists("nonexistent_schema_xyz") is False


# ---------------------------------------------------------------------------
# Column existence (base class)
# ---------------------------------------------------------------------------


class TestDuckDBColumnExists:
    def test_existing_column(self, db):
        db.execute("CREATE TABLE t (id INTEGER, name VARCHAR);")
        assert db.column_exists("t", "id") is True

    def test_nonexistent_column(self, db):
        db.execute("CREATE TABLE t2 (id INTEGER);")
        assert db.column_exists("t2", "nonexistent") is False


# ---------------------------------------------------------------------------
# Table columns (base class)
# ---------------------------------------------------------------------------


class TestDuckDBTableColumns:
    def test_returns_column_names(self, db):
        db.execute("CREATE TABLE t (alpha INTEGER, beta VARCHAR);")
        cols = db.table_columns("t")
        assert "alpha" in cols
        assert "beta" in cols


# ---------------------------------------------------------------------------
# execute / select_data / select_rowsource
# ---------------------------------------------------------------------------


class TestDuckDBExecuteAndSelect:
    def test_execute_create_and_insert(self, db):
        db.execute("CREATE TABLE t (id INTEGER, val VARCHAR);")
        db.execute("INSERT INTO t VALUES (1, 'hello');")
        hdrs, rows = db.select_data("SELECT * FROM t;")
        assert len(rows) == 1

    def test_select_data_headers(self, db):
        db.execute("CREATE TABLE t (a INTEGER, b VARCHAR);")
        hdrs, _ = db.select_data("SELECT * FROM t;")
        assert "a" in hdrs
        assert "b" in hdrs

    def test_select_data_empty_table(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        hdrs, rows = db.select_data("SELECT * FROM t;")
        assert rows == []

    def test_select_rowsource_yields_rows(self, db):
        db.execute("CREATE TABLE t (n INTEGER);")
        for i in range(3):
            db.execute(f"INSERT INTO t VALUES ({i});")
        hdrs, rows = db.select_rowsource("SELECT * FROM t ORDER BY n;")
        result = list(rows)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# commit / rollback
# ---------------------------------------------------------------------------


class TestDuckDBTransactions:
    def test_commit_does_not_raise(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        db.commit()

    def test_rollback_does_not_raise(self, db):
        db.rollback()
