"""
Tests for execsql.db.sqlite — SQLiteDatabase adapter.

Uses an in-memory SQLite database (:memory:) so no external services or
files are required.  Tests cover construction, basic DML, metadata queries,
and the methods defined in the SQLiteDatabase subclass.

Note: SQLiteDatabase.__init__ calls open_db(), which establishes a real
sqlite3 connection.  This is acceptable in unit tests because sqlite3 is
part of the Python standard library and :memory: creates a private,
throw-away database with no file I/O.
"""

from __future__ import annotations

import pytest

from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Return an in-memory SQLiteDatabase, closed after each test."""
    d = SQLiteDatabase(":memory:")
    yield d
    d.close()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestSQLiteDatabaseInit:
    def test_creates_connection(self, db):
        assert db.conn is not None

    def test_db_name_stored(self, db):
        assert db.db_name == ":memory:"

    def test_server_name_is_none(self, db):
        assert db.server_name is None

    def test_encoding_is_utf8(self, db):
        # SQLite itself reports encoding as "UTF-8"
        assert db.encoding.upper().replace("-", "") in ("UTF8", "UTF-8".replace("-", ""))

    def test_repr(self, db):
        r = repr(db)
        assert ":memory:" in r


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------


class TestTableExists:
    def test_nonexistent_table(self, db):
        assert db.table_exists("no_such_table") is False

    def test_existing_table(self, db):
        db.conn.execute("CREATE TABLE t (id INTEGER);")
        assert db.table_exists("t") is True

    def test_schema_arg_ignored_for_sqlite(self, db):
        # SQLite has no schemas; the schema_name arg is accepted but unused.
        db.conn.execute("CREATE TABLE t2 (id INTEGER);")
        assert db.table_exists("t2", schema_name="main") is True


# ---------------------------------------------------------------------------
# View existence
# ---------------------------------------------------------------------------


class TestViewExists:
    def test_nonexistent_view(self, db):
        assert db.view_exists("no_view") is False

    def test_existing_view(self, db):
        db.conn.execute("CREATE TABLE src (x INTEGER);")
        db.conn.execute("CREATE VIEW v AS SELECT x FROM src;")
        assert db.view_exists("v") is True


# ---------------------------------------------------------------------------
# Schema existence
# ---------------------------------------------------------------------------


class TestSchemaExists:
    def test_schema_exists_always_false(self, db):
        # SQLiteDatabase.schema_exists always returns False
        assert db.schema_exists("main") is False


# ---------------------------------------------------------------------------
# Column existence
# ---------------------------------------------------------------------------


class TestColumnExists:
    def test_existing_column(self, db):
        db.conn.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        assert db.column_exists("t", "id") is True

    def test_nonexistent_column(self, db):
        db.conn.execute("CREATE TABLE t2 (id INTEGER);")
        assert db.column_exists("t2", "nonexistent") is False


# ---------------------------------------------------------------------------
# Table columns
# ---------------------------------------------------------------------------


class TestTableColumns:
    def test_returns_column_names(self, db):
        db.conn.execute("CREATE TABLE t (alpha INTEGER, beta TEXT);")
        cols = db.table_columns("t")
        assert cols == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# execute / select_data / select_rowsource
# ---------------------------------------------------------------------------


class TestExecuteAndSelect:
    def test_execute_create_and_insert(self, db):
        db.execute("CREATE TABLE t (id INTEGER, val TEXT);")
        db.execute("INSERT INTO t VALUES (1, 'hello');")
        hdrs, rows = db.select_data("SELECT * FROM t;")
        assert rows == [(1, "hello")]

    def test_select_data_headers(self, db):
        db.execute("CREATE TABLE t (a INTEGER, b TEXT);")
        db.execute("INSERT INTO t VALUES (1, 'x');")
        hdrs, rows = db.select_data("SELECT * FROM t;")
        assert "a" in hdrs
        assert "b" in hdrs

    def test_select_data_empty_table(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        hdrs, rows = db.select_data("SELECT * FROM t;")
        assert rows == []

    def test_select_rowsource_yields_rows(self, db):
        db.execute("CREATE TABLE t (n INTEGER);")
        for i in range(5):
            db.execute(f"INSERT INTO t VALUES ({i});")
        hdrs, rows = db.select_rowsource("SELECT * FROM t ORDER BY n;")
        result = list(rows)
        assert len(result) == 5
        # Row values should be integers 0–4
        assert [r[0] for r in result] == list(range(5))

    def test_select_rowsource_headers(self, db):
        db.execute("CREATE TABLE t (x INTEGER);")
        hdrs, _ = db.select_rowsource("SELECT * FROM t;")
        assert hdrs == ["x"]


# ---------------------------------------------------------------------------
# commit / rollback
# ---------------------------------------------------------------------------


class TestTransactions:
    def test_commit_does_not_raise(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        db.commit()  # autocommit is True; this is a no-op for sqlite3

    def test_rollback_does_not_raise_on_empty(self, db):
        db.rollback()  # Should not raise even with nothing to roll back


# ---------------------------------------------------------------------------
# drop_table
# ---------------------------------------------------------------------------


class TestDropTable:
    def test_drop_existing_table(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        assert db.table_exists("t") is True
        db.drop_table("t")
        assert db.table_exists("t") is False

    def test_drop_nonexistent_table_is_noop(self, db):
        # SQLiteDatabase uses "DROP TABLE IF EXISTS"
        db.drop_table("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# schema_qualified_table_name (base class, exercised via SQLite)
# ---------------------------------------------------------------------------


class TestSchemaQualifiedName:
    def test_without_schema(self, db):
        name = db.schema_qualified_table_name(None, "my_table")
        assert "my_table" in name

    def test_with_schema(self, db):
        name = db.schema_qualified_table_name("main", "my_table")
        assert "main" in name
        assert "my_table" in name


# ---------------------------------------------------------------------------
# paramsubs (base class)
# ---------------------------------------------------------------------------


class TestParamSubs:
    def test_single_param(self, db):
        s = db.paramsubs(1)
        assert "?" in s

    def test_multiple_params(self, db):
        s = db.paramsubs(3)
        assert s.count("?") == 3
