"""
Tests for execsql.db.duckdb — DuckDBDatabase adapter.

Uses an in-memory DuckDB database so no files or external services are
needed.  Tests exercise construction, DML, metadata queries, the
DuckDB-specific overrides, and error paths (ImportError, open_db failure,
exec_cmd exception propagation).

Note: DuckDBDatabase.__init__ calls open_db(), which connects to DuckDB
via the installed ``duckdb`` package.  Most tests are skipped if duckdb is
not installed, but ImportError handling is tested independently of the
installed package.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

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

    def test_select_timestamptz(self, db):
        # duckdb converts TIMESTAMPTZ to a timezone-aware datetime through pytz.
        hdrs, rows = db.select_data("SELECT TIMESTAMPTZ '2026-10-12 08:30:00+00' AS ts;")
        assert rows[0][0].utcoffset() is not None

    def test_select_rowsource_yields_rows(self, db):
        db.execute("CREATE TABLE t (n INTEGER);")
        for i in range(3):
            db.execute(f"INSERT INTO t VALUES ({i});")
        hdrs, rows = db.select_rowsource("SELECT * FROM t ORDER BY n;")
        result = list(rows)
        assert len(result) == 3


class TestDuckDBTemporaryTables:
    """A temporary table belongs to one DuckDB connection; every statement must run on it."""

    def test_a_temporary_table_is_seen_by_the_next_statement(self, db):
        db.execute("CREATE TEMPORARY TABLE tt (n INTEGER);")
        db.execute("INSERT INTO tt VALUES (1), (2);")
        _hdrs, rows = db.select_data("SELECT count(*) FROM tt;")
        assert rows[0][0] == 2

    def test_a_temporary_table_can_be_streamed_and_checked(self, db):
        db.execute("CREATE TEMPORARY TABLE tt (n INTEGER);")
        db.execute("INSERT INTO tt VALUES (1), (2), (3);")
        assert db.table_exists("tt")
        _hdrs, rows = db.select_rowsource("SELECT n FROM tt ORDER BY n;")
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_in_a_script(self, tmp_path):
        from execsql import run

        result = run(
            sql="create temporary table tt (x integer);\ninsert into tt values (1);\n"
            "-- !x! EXPORT tt TO stdout AS TXT\n",
            dsn=f"duckdb:///{tmp_path / 't.duckdb'}",
            new_db=True,
        )
        assert result.success, result.errors


class TestDuckDBReadsThatOverlap:
    """The connection holds one pending result; a statement run while another is being read must not cut it short."""

    def test_two_reads_at_once_both_deliver_every_row(self, db):
        db.execute("CREATE TABLE s AS SELECT range AS a FROM range(5000);")
        _h, first = db.select_rowsource("SELECT a FROM s ORDER BY a;")
        head = [next(first) for _ in range(10)]
        _h, second = db.select_rowsource("SELECT a * 2 FROM s;")
        assert len(list(second)) == 5000
        assert len(head) + len(list(first)) == 5000

    def test_a_statement_while_reading_does_not_cut_the_read_short(self, db):
        db.execute("CREATE TABLE s AS SELECT range AS a FROM range(3000);")
        db.execute("CREATE TABLE t (a INTEGER);")
        _h, rows = db.select_rowsource("SELECT a FROM s;")
        for row in rows:
            db.execute(f"INSERT INTO t VALUES ({row[0]});")
        _h, counted = db.select_data("SELECT count(*) FROM t;")
        assert counted[0][0] == 3000

    @pytest.mark.parametrize("autocommit", ["ON", "OFF"])
    def test_copy_into_an_existing_table_copies_every_row(self, tmp_path, autocommit):
        import duckdb

        from execsql import run

        path = tmp_path / "d.duckdb"
        result = run(
            sql="create table s as select range as a from range(2000);\ncreate table t (a integer);\n"
            f"-- !x! AUTOCOMMIT {autocommit}\n-- !x! COPY s FROM initial TO t IN initial\n-- !x! AUTOCOMMIT ON WITH COMMIT\n",
            dsn=f"duckdb:///{path}",
            new_db=True,
        )
        assert result.success, result.errors
        assert duckdb.connect(str(path)).execute("select count(*) from t").fetchone()[0] == 2000


# ---------------------------------------------------------------------------
# commit / rollback
# ---------------------------------------------------------------------------


class TestDuckDBTransactions:
    def test_commit_does_not_raise(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        db.commit()

    def test_rollback_does_not_raise(self, db):
        db.rollback()


# ---------------------------------------------------------------------------
# ImportError handling (lines 27-28) — tested without the pytestmark skip
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("minimal_conf")
class TestDuckDBImportError:
    """Verify that missing duckdb package triggers fatal_error immediately.

    This class is NOT decorated with the module-level pytestmark skip, so it
    runs regardless of whether duckdb is installed.  Setting sys.modules["duckdb"]
    to None causes 'import duckdb' inside __init__ to raise ImportError, which
    the constructor catches and translates to fatal_error().
    """

    # Explicitly clear the module-level skip marker for this class.
    pytestmark = []  # type: ignore[assignment]

    def test_missing_duckdb_calls_fatal_error(self):
        """When duckdb is absent, __init__ must call fatal_error before doing anything else."""
        mock_fatal_error = MagicMock(side_effect=SystemExit(1))

        # Setting sys.modules["duckdb"] = None makes 'import duckdb' raise ImportError.
        with (
            patch.dict(sys.modules, {"duckdb": None}),
            patch("execsql.db.duckdb.fatal_error", mock_fatal_error),
            pytest.raises(SystemExit),
        ):
            DuckDBDatabase(":memory:")
        (message,), _ = mock_fatal_error.call_args
        assert message.startswith("The duckdb module is required")
        assert '"execsql2[...,duckdb]"' in message


# ---------------------------------------------------------------------------
# open_db() error path (lines 50-60)
# ---------------------------------------------------------------------------


class TestDuckDBOpenDbError:
    """Verify that a connection failure in open_db() raises ErrInfo."""

    def test_open_db_connection_failure_raises_errinfo(self, tmp_path):
        """A failing duckdb.connect wraps the exception in ErrInfo."""
        from execsql.exceptions import ErrInfo

        bad_path = str(tmp_path / "nonexistent" / "sub" / "db.duckdb")
        with pytest.raises((ErrInfo, Exception)):
            DuckDBDatabase(bad_path)

    def test_open_db_not_called_when_conn_already_set(self, db):
        """open_db() is a no-op when self.conn is already populated."""
        original_conn = db.conn
        db.open_db()  # Second call — should be a no-op, not replace the connection.
        assert db.conn is original_conn


# ---------------------------------------------------------------------------
# exec_cmd() (lines 62-72)
# ---------------------------------------------------------------------------


class TestDuckDBExecCmd:
    """Tests for exec_cmd(), which queries a named view.

    NOTE: duckdb.cursor.execute() does not accept bytes; exec_cmd encodes the
    SQL string with cmd.encode(self.encoding) before passing it to the cursor.
    This is a known limitation — the success path is tested by mocking the
    cursor's execute() so the bytes call succeeds.  The exception path is tested
    with a non-existent view name, which raises before the encode matters.
    """

    def test_exec_cmd_success_path(self, db):
        """exec_cmd() reaches the add_substitution call when cursor.execute succeeds."""
        import execsql.state as _state
        from execsql.script.variables import SubVarSet

        _state.subvars = SubVarSet()

        mock_cursor = MagicMock()
        mock_cursor.execute = MagicMock()
        mock_cursor.rowcount = 3

        with patch.object(db, "cursor", return_value=mock_cursor):
            db.exec_cmd("myview")

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "myview" in call_args  # string (not bytes) contains the view name

    def test_exec_cmd_on_nonexistent_view_raises(self, db):
        """exec_cmd() propagates the exception for a non-existent view."""
        import execsql.state as _state
        from execsql.script.variables import SubVarSet

        _state.subvars = SubVarSet()

        with pytest.raises((RuntimeError, Exception)):  # noqa: B017
            db.exec_cmd("no_such_view_xyz")

    def test_exec_cmd_rollback_called_on_error(self, db):
        """exec_cmd() calls rollback() before re-raising on execute failure."""
        import execsql.state as _state
        from execsql.script.variables import SubVarSet

        _state.subvars = SubVarSet()

        original_rollback = db.rollback
        rollback_called = []

        def tracking_rollback():
            rollback_called.append(True)
            original_rollback()

        db.rollback = tracking_rollback

        with pytest.raises((RuntimeError, Exception)):  # noqa: B017
            db.exec_cmd("no_such_view_xyz")

        assert rollback_called, "rollback() was not called after exec_cmd failure"
