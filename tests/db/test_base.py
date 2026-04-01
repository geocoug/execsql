"""
Tests for execsql.db.base — Database abstract base and DatabasePool.

Database.open_db() requires a real driver connection; those tests are
deferred to integration tests.  Here we test:

- _default_dt_cast() and Database.dt_cast property / setter
- Database construction, repr, and pure-logic helpers.
- Database.cursor() lazy-open path
- Database.close() with autocommit OFF (warning logged)
- Database.execute() with list/tuple SQL and rollback-on-error path
- Database.commit() / rollback() connection-guard paths
- Database.select_rowsource() error + encoding decode paths
- Database.select_rowdict() error + encoding decode paths
- Database.schema_exists() / table_exists() / column_exists() / table_columns()
  / view_exists() — happy paths and error wrapping via mocked cursors
- Database.drop_table() via real SQLite connection and base-class path
- Database.populate_table() — base-class implementation via BaseTestDatabase
  (happy path, missing cols, too-many cols, too-few values, string processing,
   empty rows skipping, error wrapping, progress logging)
- Database.import_tabular_file() — table-not-found, extra-cols, common-cols-only,
  and happy-path (mocked csv_file_obj)
- Database.import_entire_file() — happy path and missing-file
- DatabasePool init, add, aliases, current, make_current, disconnect, closeall
  (including reassignment logging and exception swallowing in closeall)
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.db.base import Database, DatabasePool, _default_dt_cast
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Fake database subclass — never connects to anything
# ---------------------------------------------------------------------------


class FakeDatabase(Database):
    """Minimal Database subclass for testing DatabasePool without a driver."""

    def __init__(self, server=None, db=None):
        super().__init__(server_name=server, db_name=db)
        # type must be set or name() will fail (self.type.dbms_id)
        self.type = SimpleNamespace(dbms_id="fake")

    def open_db(self):
        pass

    def exec_cmd(self, querycommand):
        pass

    def close(self):
        self.conn = None

    def rollback(self):
        pass


# ---------------------------------------------------------------------------
# FakeDatabase with a real mock conn — lets us test base-class methods
# that need self.conn without opening a real driver connection.
# ---------------------------------------------------------------------------


class ConnectedFakeDatabase(Database):
    """FakeDatabase that installs a MagicMock as self.conn so base-class
    methods that branch on ``self.conn`` are exercisable without a driver."""

    def __init__(self):
        super().__init__(server_name=None, db_name="fake.db")
        self.type = SimpleNamespace(dbms_id="fake", quoted=lambda x: f'"{x}"')
        self.conn = MagicMock()

    def open_db(self):
        self.conn = MagicMock()

    def exec_cmd(self, querycommand):
        pass


# ---------------------------------------------------------------------------
# SQLite fixture — real in-memory connection used for integration-style tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Return an in-memory SQLiteDatabase, closed after each test."""
    from execsql.db.sqlite import SQLiteDatabase

    d = SQLiteDatabase(":memory:")
    yield d
    d.close()


# ---------------------------------------------------------------------------
# BaseTestDatabase — uses dbt_sqlite type system but does NOT override
# populate_table, so the base-class implementation runs.
# ---------------------------------------------------------------------------


class BaseTestDatabase(Database):
    """Concrete Database subclass that uses a real SQLite connection and
    the dbt_sqlite type system but inherits base-class populate_table.

    SQLiteDatabase overrides populate_table, which is why we need this
    separate class to exercise the base-class code paths.
    """

    def __init__(self):
        from execsql.types import dbt_sqlite

        super().__init__(server_name=None, db_name=":memory:")
        self.type = dbt_sqlite
        self.autocommit = True
        self.conn = None
        self.open_db()

    def open_db(self):
        self.conn = sqlite3.connect(":memory:")

    def exec_cmd(self, querycommand):
        pass


@pytest.fixture
def base_db():
    """Return a BaseTestDatabase using in-memory SQLite; closed after each test."""
    d = BaseTestDatabase()
    yield d
    d.close()


def _make_tablespec_typed(col_specs: list[tuple[str, type]]):
    """Build a zero-argument callable returning a tablespec with properly-typed columns.

    col_specs is a list of (column_name, DT_class) pairs.  The DT_class must
    be a key in dbt_sqlite.dialect (e.g. DT_Integer, DT_Text, DT_Float).
    """

    class FakeCol:
        def __init__(self, name: str, dt_class: type) -> None:
            self.name = name
            self._dt_class = dt_class

        def column_type(self):
            return (None, self._dt_class)

    class FakeSpec:
        def __init__(self) -> None:
            self.cols = [FakeCol(n, dt) for n, dt in col_specs]

    def tablespec_src():
        return FakeSpec()

    return tablespec_src


# ---------------------------------------------------------------------------
# _default_dt_cast and dt_cast property / setter
# ---------------------------------------------------------------------------


class TestDefaultDtCast:
    def test_returns_dict_with_expected_keys(self):
        """_default_dt_cast() should map all standard Python types."""
        import datetime
        from decimal import Decimal

        cast = _default_dt_cast()
        assert int in cast
        assert float in cast
        assert str in cast
        assert bool in cast
        assert datetime.datetime in cast
        assert datetime.date in cast
        assert Decimal in cast
        assert bytearray in cast

    def test_int_maps_to_int(self):
        cast = _default_dt_cast()
        assert cast[int] is int

    def test_bytearray_maps_to_bytearray(self):
        cast = _default_dt_cast()
        assert cast[bytearray] is bytearray

    def test_bool_callable_returns_value(self):
        """The bool cast callable should convert a truthy string to a bool-like result."""
        cast = _default_dt_cast()
        # The callable is DT_Boolean().from_data — it must be callable without error
        result = cast[bool](True)
        assert result is not None


class TestDtCastProperty:
    def test_dt_cast_lazily_initialised_on_first_access(self):
        """dt_cast must be None until first accessed, then populated."""
        db = FakeDatabase()
        # Force _dt_cast to None (it is class-level None by default)
        db._dt_cast = None
        cast = db.dt_cast
        assert cast is not None
        assert isinstance(cast, dict)

    def test_dt_cast_cached_on_second_access(self):
        """dt_cast should return the same dict object on repeated access."""
        db = FakeDatabase()
        db._dt_cast = None
        first = db.dt_cast
        second = db.dt_cast
        assert first is second

    def test_dt_cast_setter_stores_custom_mapping(self):
        """Assigning to db.dt_cast should replace the internal mapping."""
        db = FakeDatabase()
        custom = {int: str}
        db.dt_cast = custom
        assert db._dt_cast is custom
        assert db.dt_cast is custom


# ---------------------------------------------------------------------------
# Database base class
# ---------------------------------------------------------------------------


class TestDatabaseInit:
    def test_server_name_stored(self):
        db = FakeDatabase(server="myhost", db="mydb")
        assert db.server_name == "myhost"

    def test_db_name_stored(self):
        db = FakeDatabase(db="mydb")
        assert db.db_name == "mydb"

    def test_user_none_by_default(self):
        db = FakeDatabase()
        assert db.user is None

    def test_password_none_initially(self):
        db = FakeDatabase()
        assert db.password is None

    def test_conn_none_initially(self):
        db = FakeDatabase()
        assert db.conn is None

    def test_autocommit_true_by_default(self):
        db = FakeDatabase()
        assert db.autocommit is True

    def test_paramstr_default(self):
        db = FakeDatabase()
        assert db.paramstr == "?"


class TestDatabaseRepr:
    def test_repr_contains_server_and_db(self):
        db = FakeDatabase(server="myhost", db="mydb")
        r = repr(db)
        assert "myhost" in r
        assert "mydb" in r

    def test_repr_starts_with_database(self):
        db = FakeDatabase()
        assert repr(db).startswith("Database(")


class TestDatabaseName:
    def test_name_with_server(self):
        db = FakeDatabase(server="myhost", db="mydb")
        name = db.name()
        assert "myhost" in name
        assert "mydb" in name

    def test_name_without_server(self):
        db = FakeDatabase(server=None, db="myfile.db")
        name = db.name()
        assert "myfile.db" in name


class TestDatabaseIsAbstract:
    def test_cannot_instantiate_database_directly(self):
        with pytest.raises(TypeError, match="abstract method"):
            Database(server_name=None, db_name="x")


# ---------------------------------------------------------------------------
# quote_identifier
# ---------------------------------------------------------------------------


class TestQuoteIdentifier:
    def test_simple_identifier(self):
        db = FakeDatabase()
        assert db.quote_identifier("my_table") == '"my_table"'

    def test_identifier_with_embedded_double_quote(self):
        db = FakeDatabase()
        assert db.quote_identifier('my"table') == '"my""table"'

    def test_identifier_with_multiple_double_quotes(self):
        db = FakeDatabase()
        assert db.quote_identifier('a"b"c') == '"a""b""c"'

    def test_empty_identifier(self):
        db = FakeDatabase()
        assert db.quote_identifier("") == '""'

    def test_identifier_with_spaces(self):
        db = FakeDatabase()
        assert db.quote_identifier("my table") == '"my table"'

    def test_identifier_with_special_chars(self):
        db = FakeDatabase()
        assert db.quote_identifier("col; DROP TABLE--") == '"col; DROP TABLE--"'


# ---------------------------------------------------------------------------
# cursor() — lazy open_db() call
# ---------------------------------------------------------------------------


class TestCursorLazyOpen:
    def test_cursor_calls_open_db_when_conn_is_none(self):
        """cursor() must call open_db() if conn is None, then return conn.cursor()."""
        db = ConnectedFakeDatabase()
        # Reset conn so the lazy-open branch is taken
        db.conn = None
        opened = []

        def fake_open_db():
            db.conn = MagicMock()
            opened.append(True)

        db.open_db = fake_open_db
        curs = db.cursor()
        assert len(opened) == 1
        assert curs is not None

    def test_cursor_skips_open_db_when_conn_already_set(self):
        """cursor() must not call open_db() if conn is already set."""
        db = ConnectedFakeDatabase()
        opened = []

        original_open = db.open_db

        def tracking_open():
            opened.append(True)
            return original_open()

        db.open_db = tracking_open
        db.cursor()
        assert opened == []


# ---------------------------------------------------------------------------
# close() — autocommit-off warning path
# ---------------------------------------------------------------------------


class TestDatabaseCloseAutocommitOff:
    def test_close_with_autocommit_off_calls_exec_log(self):
        """close() with autocommit=False must log a warning via exec_log."""
        db = ConnectedFakeDatabase()
        db.autocommit = False

        mock_log = MagicMock()
        _state.exec_log = mock_log

        db.close()

        mock_log.log_status_info.assert_called_once()
        assert "AUTOCOMMIT is OFF" in mock_log.log_status_info.call_args[0][0]

    def test_close_with_autocommit_on_does_not_log(self):
        """close() with autocommit=True must not log any warning."""
        db = ConnectedFakeDatabase()
        db.autocommit = True

        mock_log = MagicMock()
        _state.exec_log = mock_log

        db.close()

        mock_log.log_status_info.assert_not_called()

    def test_close_sets_conn_to_none(self):
        """After close(), conn must be None."""
        db = ConnectedFakeDatabase()
        db.close()
        assert db.conn is None

    def test_close_when_conn_is_none_is_noop(self):
        """close() when conn is already None must not raise."""
        db = ConnectedFakeDatabase()
        db.conn = None
        db.close()  # should not raise


# ---------------------------------------------------------------------------
# execute() — list/tuple SQL and rollback-on-error
# ---------------------------------------------------------------------------


class TestExecuteListTupleSql:
    def test_execute_with_list_sql_joins_tokens(self, db):
        """execute() should join a list of SQL tokens with spaces."""
        db.execute(["CREATE TABLE t", "(id INTEGER);"])
        hdrs, rows = db.select_data("SELECT * FROM t;")
        assert hdrs == ["id"]

    def test_execute_with_tuple_sql_joins_tokens(self, db):
        """execute() should join a tuple of SQL tokens with spaces."""
        db.execute(("CREATE TABLE t2", "(val TEXT);"))
        hdrs, _ = db.select_data("SELECT * FROM t2;")
        assert hdrs == ["val"]

    def test_execute_rollback_called_on_error(self, db):
        """On a driver error, execute() must attempt rollback before re-raising."""
        rollback_called = []
        original_rollback = db.rollback

        def tracking_rollback():
            rollback_called.append(True)
            return original_rollback()

        db.rollback = tracking_rollback

        with pytest.raises(Exception):  # noqa: B017
            db.execute("THIS IS NOT VALID SQL !!!;")

        assert rollback_called == [True]

    def test_execute_re_raises_after_rollback(self, db):
        """execute() must re-raise the original exception after rollback."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INVALID SQL;")

    def test_execute_re_raises_even_when_rollback_also_raises(self, db):
        """execute() must re-raise the original exception even if rollback() also raises.

        This covers lines 164-165 (the inner except Exception: pass).
        """
        # Patch rollback() to raise, and make cursor fail on execute
        db.rollback = lambda: (_ for _ in ()).throw(RuntimeError("rollback also failed"))
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DEFINITELY NOT SQL;")


# ---------------------------------------------------------------------------
# commit() — connection guard paths
# ---------------------------------------------------------------------------


class TestCommitConnectionGuard:
    def test_commit_with_conn_none_is_noop(self):
        """commit() must not raise when conn is None."""
        db = FakeDatabase()
        db.conn = None
        db.commit()  # should not raise

    def test_commit_with_autocommit_false_does_not_call_conn_commit(self):
        """commit() must NOT call conn.commit() when autocommit is False."""
        db = ConnectedFakeDatabase()
        db.autocommit = False
        db.commit()
        db.conn.commit.assert_not_called()

    def test_commit_with_autocommit_true_calls_conn_commit(self):
        """commit() must call conn.commit() when autocommit is True."""
        db = ConnectedFakeDatabase()
        db.autocommit = True
        db.commit()
        db.conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# rollback() — connection guard path
# ---------------------------------------------------------------------------


class TestRollbackConnectionGuard:
    def test_rollback_with_conn_none_is_noop(self):
        """rollback() must not raise when conn is None."""

        class NullRollbackDb(Database):
            def open_db(self):
                pass

            def exec_cmd(self, querycommand):
                pass

        db = NullRollbackDb(server_name=None, db_name=None)
        db.type = SimpleNamespace(dbms_id="fake")
        db.conn = None
        db.rollback()  # should not raise

    def test_rollback_swallows_driver_errors(self):
        """rollback() must not propagate exceptions from conn.rollback()."""
        db = ConnectedFakeDatabase()
        db.conn.rollback.side_effect = Exception("driver rollback failure")
        db.rollback()  # should not raise


# ---------------------------------------------------------------------------
# select_rowsource() — error and encoding paths
# ---------------------------------------------------------------------------


class TestSelectRowsourceErrorPath:
    def test_raises_on_execute_error_and_rolls_back(self, db):
        """select_rowsource() must rollback and re-raise on cursor.execute failure."""
        rollback_called = []
        original_rollback = db.rollback

        def tracking_rollback():
            rollback_called.append(True)
            return original_rollback()

        db.rollback = tracking_rollback

        with pytest.raises(Exception):  # noqa: B017
            db.select_rowsource("SELECT * FROM nonexistent_table_xyz;")

        assert rollback_called == [True]


class TestSelectRowsourceEncoding:
    def test_bytes_decoded_when_encoding_set(self):
        """Rows with bytes values must be decoded using db.encoding when set."""
        db = ConnectedFakeDatabase()
        db.encoding = "utf-8"

        mock_curs = MagicMock()
        mock_curs.description = [("col",)]
        mock_curs.rowcount = 1
        # fetchmany() returns one batch of one row, then empty
        mock_curs.fetchmany.side_effect = [
            [(b"hello bytes",)],
            [],
        ]

        with patch.object(db, "cursor", return_value=mock_curs):
            hdrs, gen = db.select_rowsource("SELECT col FROM fake;")
            rows = list(gen)

        assert hdrs == ["col"]
        assert rows == [["hello bytes"]]

    def test_non_bytes_values_passed_through_when_encoding_set(self):
        """Non-bytes values must be passed through unchanged even if encoding is set."""
        db = ConnectedFakeDatabase()
        db.encoding = "utf-8"

        mock_curs = MagicMock()
        mock_curs.description = [("n",)]
        mock_curs.rowcount = 1
        mock_curs.fetchmany.side_effect = [
            [(42,)],
            [],
        ]

        with patch.object(db, "cursor", return_value=mock_curs):
            _, gen = db.select_rowsource("SELECT n FROM fake;")
            rows = list(gen)

        assert rows == [[42]]

    def test_no_encoding_yields_raw_rows(self):
        """When encoding is falsy, rows are yielded as-is without any decoding."""
        db = ConnectedFakeDatabase()
        db.encoding = None

        mock_curs = MagicMock()
        mock_curs.description = [("val",)]
        mock_curs.rowcount = 1
        mock_curs.fetchmany.side_effect = [
            [("raw_string",)],
            [],
        ]

        with patch.object(db, "cursor", return_value=mock_curs):
            _, gen = db.select_rowsource("SELECT val FROM fake;")
            rows = list(gen)

        assert rows == [("raw_string",)]


# ---------------------------------------------------------------------------
# select_rowdict() — error and encoding paths
# ---------------------------------------------------------------------------


class TestSelectRowdictErrorPath:
    def test_raises_on_execute_error_and_rolls_back(self, db):
        """select_rowdict() must rollback and re-raise on cursor.execute failure."""
        rollback_called = []
        original_rollback = db.rollback

        def tracking_rollback():
            rollback_called.append(True)
            return original_rollback()

        db.rollback = tracking_rollback

        with pytest.raises(Exception):  # noqa: B017
            db.select_rowdict("SELECT * FROM nonexistent_xyz;")

        assert rollback_called == [True]


class TestSelectRowdictEncoding:
    def test_bytes_decoded_in_rowdict_when_encoding_set(self):
        """select_rowdict() must decode bytes values when db.encoding is set."""
        db = ConnectedFakeDatabase()
        db.encoding = "utf-8"

        mock_curs = MagicMock()
        mock_curs.description = [("name",)]
        mock_curs.rowcount = 1
        mock_curs.fetchone.side_effect = [
            (b"encoded value",),
            None,
        ]

        with patch.object(db, "cursor", return_value=mock_curs):
            hdrs, it = db.select_rowdict("SELECT name FROM fake;")
            rows = list(it)

        assert hdrs == ["name"]
        assert rows[0]["name"] == "encoded value"

    def test_non_bytes_passed_through_in_rowdict_when_encoding_set(self):
        """Non-bytes values in rowdict must not be modified even with encoding set."""
        db = ConnectedFakeDatabase()
        db.encoding = "utf-8"

        mock_curs = MagicMock()
        mock_curs.description = [("score",)]
        mock_curs.rowcount = 1
        mock_curs.fetchone.side_effect = [(99,), None]

        with patch.object(db, "cursor", return_value=mock_curs):
            _, it = db.select_rowdict("SELECT score FROM fake;")
            rows = list(it)

        assert rows[0]["score"] == 99

    def test_no_encoding_rowdict_uses_raw_row(self):
        """When encoding is falsy, rowdict uses raw row values."""
        db = ConnectedFakeDatabase()
        db.encoding = None

        mock_curs = MagicMock()
        mock_curs.description = [("x",)]
        mock_curs.rowcount = 1
        mock_curs.fetchone.side_effect = [("plain",), None]

        with patch.object(db, "cursor", return_value=mock_curs):
            _, it = db.select_rowdict("SELECT x FROM fake;")
            rows = list(it)

        assert rows[0]["x"] == "plain"


# ---------------------------------------------------------------------------
# schema_exists() — mocked cursor
# ---------------------------------------------------------------------------


class TestSchemaExistsMocked:
    def test_returns_true_when_row_found(self):
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = [("public",)]

        with patch.object(db, "cursor", return_value=mock_curs):
            result = db.schema_exists("public")

        assert result is True

    def test_returns_false_when_no_rows(self):
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = []

        with patch.object(db, "cursor", return_value=mock_curs):
            result = db.schema_exists("nonexistent")

        assert result is False


# ---------------------------------------------------------------------------
# table_exists() — error-wrapping paths (base class)
# ---------------------------------------------------------------------------


class TestTableExistsBaseErrorPaths:
    def test_errrinfo_propagates_without_wrapping(self):
        """ErrInfo raised inside table_exists cursor should not be double-wrapped."""
        db = ConnectedFakeDatabase()
        original = ErrInfo(type="db", other_msg="passthrough")
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = original

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.table_exists("some_table")
        assert exc_info.value is original

    def test_generic_exception_wrapped_in_errrinfo(self):
        """A non-ErrInfo exception inside table_exists should be wrapped in ErrInfo."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = RuntimeError("driver error")

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.table_exists("bad_table")
        assert "Failed test for existence" in str(exc_info.value)

    def test_with_schema_name_includes_schema_in_query(self):
        """table_exists() with schema_name must include a schema filter in the SQL."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = [("my_table",)]
        executed_sql = []

        def capture_execute(sql, params):
            executed_sql.append(sql)

        mock_curs.execute.side_effect = capture_execute

        with patch.object(db, "cursor", return_value=mock_curs):
            db.table_exists("my_table", schema_name="myschema")

        assert any("table_schema" in s for s in executed_sql)


# ---------------------------------------------------------------------------
# column_exists() — schema clause and error paths (base class)
# ---------------------------------------------------------------------------


class TestColumnExistsBaseClass:
    def test_with_schema_name_includes_schema_filter(self):
        """column_exists() with schema_name must include table_schema in the SQL."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = [("id",)]
        executed_sql = []

        def capture_execute(sql, params):
            executed_sql.append(sql)

        mock_curs.execute.side_effect = capture_execute

        with patch.object(db, "cursor", return_value=mock_curs):
            db.column_exists("my_table", "id", schema_name="myschema")

        assert any("table_schema" in s for s in executed_sql)

    def test_no_schema_name_omits_schema_filter(self):
        """column_exists() without schema_name must not include table_schema in the SQL."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = []
        executed_sql = []

        def capture_execute(sql, params):
            executed_sql.append(sql)

        mock_curs.execute.side_effect = capture_execute

        with patch.object(db, "cursor", return_value=mock_curs):
            db.column_exists("my_table", "missing_col")

        assert not any("table_schema" in s for s in executed_sql)

    def test_errrinfo_propagates_without_wrapping(self):
        """ErrInfo raised inside column_exists should not be double-wrapped."""
        db = ConnectedFakeDatabase()
        original = ErrInfo(type="db", other_msg="direct ErrInfo")
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = original

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.column_exists("t", "col")
        assert exc_info.value is original

    def test_generic_exception_wrapped_in_errrinfo(self):
        """A non-ErrInfo exception inside column_exists should be wrapped in ErrInfo."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = RuntimeError("driver error")

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.column_exists("t", "col")
        assert "Failed test for existence of column" in str(exc_info.value)

    def test_returns_true_when_column_found(self):
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = [("id",)]

        with patch.object(db, "cursor", return_value=mock_curs):
            result = db.column_exists("t", "id")

        assert result is True

    def test_returns_false_when_column_not_found(self):
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = []

        with patch.object(db, "cursor", return_value=mock_curs):
            result = db.column_exists("t", "nonexistent")

        assert result is False


# ---------------------------------------------------------------------------
# table_columns() — schema clause and error paths (base class)
# ---------------------------------------------------------------------------


class TestTableColumnsBaseClass:
    def test_with_schema_name_includes_schema_filter(self):
        """table_columns() with schema_name must include table_schema in the SQL."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = [("id",), ("name",)]
        executed_sql = []

        def capture_execute(sql, params):
            executed_sql.append(sql)

        mock_curs.execute.side_effect = capture_execute

        with patch.object(db, "cursor", return_value=mock_curs):
            db.table_columns("my_table", schema_name="myschema")

        assert any("table_schema" in s for s in executed_sql)

    def test_errrinfo_propagates_without_wrapping(self):
        """ErrInfo raised inside table_columns should not be double-wrapped."""
        db = ConnectedFakeDatabase()
        original = ErrInfo(type="db", other_msg="direct ErrInfo")
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = original

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.table_columns("any")
        assert exc_info.value is original

    def test_generic_exception_wrapped_in_errrinfo(self):
        """A non-ErrInfo exception inside table_columns should be wrapped in ErrInfo."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = RuntimeError("driver error")

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.table_columns("bad_table")
        assert "Failed to get column names" in str(exc_info.value)

    def test_returns_column_name_list(self):
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = [("alpha",), ("beta",)]

        with patch.object(db, "cursor", return_value=mock_curs):
            cols = db.table_columns("t")

        assert cols == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# view_exists() — base class (mocked cursor)
# ---------------------------------------------------------------------------


class TestViewExistsBaseClass:
    def test_returns_true_when_view_found(self):
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = [("my_view",)]

        with patch.object(db, "cursor", return_value=mock_curs):
            result = db.view_exists("my_view")

        assert result is True

    def test_returns_false_when_no_views(self):
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = []

        with patch.object(db, "cursor", return_value=mock_curs):
            result = db.view_exists("nonexistent")

        assert result is False

    def test_with_schema_name_includes_schema_filter(self):
        """view_exists() with schema_name must include table_schema in the SQL."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.fetchall.return_value = []
        executed_sql = []

        def capture_execute(sql, params):
            executed_sql.append(sql)

        mock_curs.execute.side_effect = capture_execute

        with patch.object(db, "cursor", return_value=mock_curs):
            db.view_exists("my_view", schema_name="public")

        assert any("table_schema" in s for s in executed_sql)

    def test_errrinfo_propagates_without_wrapping(self):
        """ErrInfo raised inside view_exists should not be double-wrapped."""
        db = ConnectedFakeDatabase()
        original = ErrInfo(type="db", other_msg="direct ErrInfo")
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = original

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.view_exists("any")
        assert exc_info.value is original

    def test_generic_exception_wrapped_in_errrinfo(self):
        """A non-ErrInfo exception inside view_exists should be wrapped in ErrInfo."""
        db = ConnectedFakeDatabase()
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        mock_curs.execute.side_effect = RuntimeError("db error")

        with patch.object(db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            db.view_exists("bad_view")
        assert "Failed test for existence of view" in str(exc_info.value)


# ---------------------------------------------------------------------------
# drop_table() — via SQLite
# ---------------------------------------------------------------------------


class TestDropTable:
    def test_drop_existing_table_via_sqlite(self, db):
        """drop_table() should remove the table from the database."""
        db.execute("CREATE TABLE droptarget (id INTEGER);")
        assert db.table_exists("droptarget") is True
        db.drop_table("droptarget")
        assert db.table_exists("droptarget") is False

    def test_drop_nonexistent_table_is_noop(self, db):
        """drop_table() with IF EXISTS should not raise for a missing table."""
        db.drop_table("nonexistent_table_xyz")  # should not raise

    def test_drop_table_base_class_calls_commit(self):
        """The base class drop_table() must call commit() after executing DROP.

        This is verified through ConnectedFakeDatabase, which does NOT override
        drop_table(), so the base-class implementation runs.
        """
        db = ConnectedFakeDatabase()
        commit_calls = []
        original_commit = db.commit

        def tracking_commit():
            commit_calls.append(True)
            return original_commit()

        db.commit = tracking_commit
        # _cursor() context manager requires the mock cursor to support __enter__/__exit__
        mock_curs = MagicMock()
        mock_curs.__enter__ = lambda s: s
        mock_curs.__exit__ = MagicMock(return_value=False)
        with patch.object(db, "cursor", return_value=mock_curs):
            db.drop_table('"some_table"')

        assert commit_calls == [True]


# ---------------------------------------------------------------------------
# import_entire_file() — base class via SQLite
# ---------------------------------------------------------------------------


class TestImportEntireFile:
    """Tests for Database.import_entire_file() via SQLiteDatabase (which doesn't override it),
    exercising the base-class implementation in db/base.py lines 628-634."""

    def test_imports_file_contents_as_blob(self, base_db, tmp_path):
        """import_entire_file() must read the file and insert its contents."""
        blob_file = tmp_path / "test.bin"
        blob_content = b"\x00\x01\x02\x03\xff\xfe"
        blob_file.write_bytes(blob_content)

        base_db.execute("CREATE TABLE blobs (data BLOB);")
        base_db.import_entire_file(None, "blobs", "data", str(blob_file))

        _, result = base_db.select_data("SELECT data FROM blobs;")
        assert len(result) == 1
        assert bytes(result[0][0]) == blob_content

    def test_missing_file_raises_file_not_found(self, base_db, tmp_path):
        """import_entire_file() must raise FileNotFoundError for a missing file."""
        base_db.execute("CREATE TABLE blobs (data BLOB);")
        with pytest.raises(FileNotFoundError):
            base_db.import_entire_file(None, "blobs", "data", str(tmp_path / "missing.bin"))

    def test_empty_file_stored_as_empty_blob(self, base_db, tmp_path):
        """import_entire_file() must handle an empty file without error."""
        empty_file = tmp_path / "empty.bin"
        empty_file.write_bytes(b"")
        base_db.execute("CREATE TABLE blobs (data BLOB);")
        base_db.import_entire_file(None, "blobs", "data", str(empty_file))
        _, result = base_db.select_data("SELECT data FROM blobs;")
        assert bytes(result[0][0]) == b""


# ---------------------------------------------------------------------------
# populate_table() — base class implementation via BaseTestDatabase
# ---------------------------------------------------------------------------


class TestPopulateTableBase:
    """Tests for the base-class populate_table() via BaseTestDatabase.

    SQLiteDatabase overrides this method; these tests exercise the abstract
    base-class logic that all other DBMS adapters inherit.
    """

    @pytest.fixture(autouse=True)
    def _setup_conf(self, minimal_conf):
        """Add populate_table-specific conf attributes not in minimal_conf."""
        minimal_conf.import_row_buffer = 100
        minimal_conf.import_progress_interval = 0
        minimal_conf.show_progress = False
        minimal_conf.empty_rows = True

    def test_happy_path_inserts_rows(self, base_db, minimal_conf):
        """populate_table() must insert all rows from the rowsource."""
        from execsql.types import DT_Integer, DT_Text

        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        base_db.populate_table(None, "t", iter([[1, "alice"], [2, "bob"]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT id, name FROM t ORDER BY id;")
        assert rows == [(1, "alice"), (2, "bob")]

    def test_empty_rowsource_inserts_nothing(self, base_db):
        """An empty rowsource must result in zero inserted rows."""
        from execsql.types import DT_Integer

        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        base_db.populate_table(None, "t", iter([]), ["id"], ts)
        _, rows = base_db.select_data("SELECT * FROM t;")
        assert rows == []

    def test_missing_column_raises_errrinfo(self, base_db):
        """populate_table() must raise ErrInfo when column_list contains unknown columns."""
        from execsql.types import DT_Integer

        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        with pytest.raises(ErrInfo) as exc_info:
            base_db.populate_table(None, "t", iter([]), ["id", "nonexistent"], ts)
        assert "nonexistent" in str(exc_info.value)

    def test_too_many_cols_raises_errrinfo(self, base_db, minimal_conf):
        """A row with more values than columns must raise ErrInfo."""
        from execsql.types import DT_Integer

        minimal_conf.del_empty_cols = False
        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        with pytest.raises(ErrInfo) as exc_info:
            base_db.populate_table(None, "t", iter([[1, 2, 3]]), ["id"], ts)
        assert "Too many data columns" in str(exc_info.value)

    def test_too_many_cols_truncated_when_extra_are_empty(self, base_db, minimal_conf):
        """Extra columns that are all None/empty are silently truncated when del_empty_cols=True."""
        from execsql.types import DT_Integer

        minimal_conf.del_empty_cols = True
        minimal_conf.empty_strings = True
        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        # Extra columns are all None — should be truncated silently
        base_db.populate_table(None, "t", iter([[1, None, None]]), ["id"], ts)
        _, rows = base_db.select_data("SELECT id FROM t;")
        assert rows == [(1,)]

    def test_sentinel_row_skipped(self, base_db):
        """A row of [None] (single-element None) must be skipped — it is the sentinel."""
        from execsql.types import DT_Integer

        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        base_db.populate_table(None, "t", iter([[None]]), ["id"], ts)
        _, rows = base_db.select_data("SELECT * FROM t;")
        assert rows == []

    def test_all_none_row_skipped_when_empty_rows_false(self, base_db, minimal_conf):
        """All-None rows must be skipped when empty_rows=False."""
        from execsql.types import DT_Integer, DT_Text

        minimal_conf.empty_rows = False
        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        base_db.populate_table(None, "t", iter([[None, None]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT * FROM t;")
        assert rows == []

    def test_all_none_row_inserted_when_empty_rows_true(self, base_db, minimal_conf):
        """All-None rows must be inserted when empty_rows=True (default)."""
        from execsql.types import DT_Integer, DT_Text

        minimal_conf.empty_rows = True
        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        base_db.populate_table(None, "t", iter([[None, None]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT * FROM t;")
        assert len(rows) == 1

    def test_trim_strings_trims_whitespace(self, base_db, minimal_conf):
        """With trim_strings=True, leading/trailing whitespace in string values is stripped."""
        from execsql.types import DT_Integer, DT_Text

        minimal_conf.trim_strings = True
        minimal_conf.replace_newlines = False
        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        base_db.populate_table(None, "t", iter([[1, "  hello  "]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT name FROM t;")
        assert rows[0][0] == "hello"

    def test_replace_newlines_collapses_newlines(self, base_db, minimal_conf):
        """With replace_newlines=True, embedded newlines in strings are replaced with space."""
        from execsql.types import DT_Integer, DT_Text

        minimal_conf.replace_newlines = True
        minimal_conf.trim_strings = False
        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        base_db.populate_table(None, "t", iter([[1, "line1\nline2"]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT name FROM t;")
        assert "\n" not in rows[0][0]
        assert "line1" in rows[0][0]

    def test_empty_strings_false_nullifies_blank_strings(self, base_db, minimal_conf):
        """With empty_strings=False, whitespace-only strings are stored as NULL."""
        from execsql.types import DT_Integer, DT_Text

        minimal_conf.empty_strings = False
        minimal_conf.trim_strings = False
        minimal_conf.replace_newlines = False
        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        base_db.populate_table(None, "t", iter([[1, "   "]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT name FROM t;")
        assert rows[0][0] is None

    def test_none_string_value_not_modified_during_processing(self, base_db, minimal_conf):
        """None values in string columns must not raise AttributeError during processing."""
        from execsql.types import DT_Integer, DT_Text

        minimal_conf.trim_strings = True
        minimal_conf.replace_newlines = True
        minimal_conf.empty_strings = False
        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        base_db.populate_table(None, "t", iter([[1, None]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT name FROM t;")
        assert rows[0][0] is None

    def test_column_subset_inserts_only_selected_columns(self, base_db, minimal_conf):
        """populate_table() with a column_list subset must only insert matching columns."""
        from execsql.types import DT_Integer, DT_Text, DT_Float

        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT, score REAL);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text), ("score", DT_Float)])
        # Provide data for id+name only; score not in column_list
        base_db.populate_table(None, "t", iter([[99, "carol"]]), ["id", "name"], ts)
        _, rows = base_db.select_data("SELECT id, name, score FROM t;")
        assert rows[0][0] == 99
        assert rows[0][1] == "carol"
        assert rows[0][2] is None

    def test_db_error_during_insert_raises_errrinfo(self, base_db, minimal_conf):
        """A DB error during executemany must be wrapped in ErrInfo."""
        from execsql.types import DT_Integer, DT_Text

        base_db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        # Insert two rows with duplicate primary key — second should fail
        with pytest.raises(ErrInfo) as exc_info:
            base_db.populate_table(
                None,
                "t",
                iter([[1, "first"], [1, "duplicate"]]),
                ["id", "name"],
                ts,
            )
        assert "Can't load data into table" in str(exc_info.value)

    def test_errrinfo_propagates_without_double_wrapping(self, base_db, minimal_conf):
        """ErrInfo raised during executemany must propagate as-is (not double-wrapped)."""
        from execsql.types import DT_Integer, DT_Text

        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        ts = _make_tablespec_typed([("id", DT_Integer), ("name", DT_Text)])
        original_err = ErrInfo(type="db", other_msg="original error")

        mock_curs = MagicMock()
        mock_curs.executemany.side_effect = original_err

        with patch.object(base_db, "cursor", return_value=mock_curs), pytest.raises(ErrInfo) as exc_info:
            base_db.populate_table(None, "t", iter([[1, "x"]]), ["id", "name"], ts)
        assert exc_info.value is original_err

    def test_progress_logged_at_interval(self, base_db, minimal_conf):
        """exec_log.log_status_info must be called at import_progress_interval."""
        from execsql.types import DT_Integer

        minimal_conf.import_progress_interval = 2
        mock_log = MagicMock()
        _state.exec_log = mock_log

        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        rows = [[i] for i in range(1, 5)]
        base_db.populate_table(None, "t", iter(rows), ["id"], ts)

        calls = [str(c) for c in mock_log.log_status_info.call_args_list]
        interval_calls = [c for c in calls if "so far" in c]
        assert len(interval_calls) >= 1

    def test_completion_always_logged_when_exec_log_set(self, base_db, minimal_conf):
        """The completion message must be logged after populate_table finishes."""
        from execsql.types import DT_Integer

        mock_log = MagicMock()
        _state.exec_log = mock_log

        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        base_db.populate_table(None, "t", iter([[1]]), ["id"], ts)

        calls = [str(c) for c in mock_log.log_status_info.call_args_list]
        completion_calls = [c for c in calls if "complete" in c]
        assert len(completion_calls) == 1

    def test_no_error_when_exec_log_is_none(self, base_db, minimal_conf):
        """No error should occur when _state.exec_log is None."""
        from execsql.types import DT_Integer

        _state.exec_log = None
        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        base_db.populate_table(None, "t", iter([[1]]), ["id"], ts)  # must not raise

    def test_extra_empty_cols_truncated_when_non_empty_cols_present(self, base_db, minimal_conf):
        """Extra columns that contain non-empty values raise ErrInfo even with del_empty_cols."""
        from execsql.types import DT_Integer

        minimal_conf.del_empty_cols = True
        minimal_conf.empty_strings = True
        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        # The extra column contains a non-empty value — must raise
        with pytest.raises(ErrInfo) as exc_info:
            base_db.populate_table(None, "t", iter([[1, "not_empty"]]), ["id"], ts)
        assert "Too many data columns" in str(exc_info.value)


# ---------------------------------------------------------------------------
# import_tabular_file() — base class (mocked csv_file_obj)
# ---------------------------------------------------------------------------


def _make_csv_obj(csv_cols, table_rows, csvfname="test.csv"):
    """Build a mock csv_file_obj suitable for import_tabular_file() tests."""
    obj = MagicMock()
    obj.column_headers.return_value = csv_cols
    obj.csvfname = csvfname
    # reader() returns an iterator; next(f) skips the header
    header_and_rows = [csv_cols] + table_rows
    obj.reader.return_value = iter(header_and_rows)
    # data_table_def() returns a mock tablespec used in populate_table
    fake_cols = []
    for col in csv_cols:
        fc = MagicMock()
        fc.name = col
        fc.column_type.return_value = (None, _int_type_stub())
        fake_cols.append(fc)
    fake_spec = MagicMock()
    fake_spec.cols = fake_cols
    obj.data_table_def.return_value = fake_spec
    return obj


class _int_type_stub:
    """Minimal data type stub that acts as int for populate_table()."""

    def from_data(self, val):
        return val


class TestImportTabularFile:
    """Tests for Database.import_tabular_file() (base-class implementation).

    import_tabular_file() calls table_exists() and table_columns(), which
    use information_schema — not available in SQLite.  We mock those two
    methods on the base_db instance so the rest of the import logic runs
    through the base-class implementation.
    """

    @pytest.fixture(autouse=True)
    def _setup_conf(self, minimal_conf):
        minimal_conf.import_row_buffer = 100
        minimal_conf.import_progress_interval = 0
        minimal_conf.show_progress = False
        minimal_conf.empty_rows = True

    def test_raises_when_table_does_not_exist(self, base_db, minimal_conf):
        """import_tabular_file() must raise ErrInfo when the target table is absent."""
        minimal_conf.import_common_cols_only = False
        csv_obj = _make_csv_obj(["id"], [])
        with patch.object(base_db, "table_exists", return_value=False), pytest.raises(ErrInfo) as exc_info:
            base_db.import_tabular_file(None, "nonexistent_table", csv_obj, skipheader=True)
        assert "Table doesn't exist" in str(exc_info.value)

    def test_raises_when_csv_has_extra_cols(self, base_db, minimal_conf):
        """import_tabular_file() must raise ErrInfo when csv has columns not in the table."""
        minimal_conf.import_common_cols_only = False
        csv_obj = _make_csv_obj(["id", "extra_col"], [])
        with (
            patch.object(base_db, "table_exists", return_value=True),
            patch.object(base_db, "table_columns", return_value=["id"]),
            pytest.raises(ErrInfo) as exc_info,
        ):
            base_db.import_tabular_file(None, "t", csv_obj, skipheader=True)
        assert "extra_col" in str(exc_info.value)

    def test_import_common_cols_only_skips_extra_csv_cols(self, base_db, minimal_conf):
        """With import_common_cols_only=True, extra csv columns are silently ignored.

        The csv has columns [id, extra]; the table only has [id].  The importer
        should build import_cols = [id] and skip rows' extra values.
        """
        from execsql.types import DT_Integer

        minimal_conf.import_common_cols_only = True
        base_db.execute("CREATE TABLE t (id INTEGER);")

        # reader yields 2-column rows; data_table_def's tablespec has 2 cols too
        csv_obj = MagicMock()
        csv_obj.column_headers.return_value = ["id", "extra"]
        csv_obj.csvfname = "test.csv"
        csv_obj.reader.return_value = iter([["id", "extra"], [1, 999]])

        fake_id_col = MagicMock()
        fake_id_col.name = "id"
        fake_id_col.column_type.return_value = (None, DT_Integer)

        fake_extra_col = MagicMock()
        fake_extra_col.name = "extra"
        fake_extra_col.column_type.return_value = (None, DT_Integer)

        fake_spec = MagicMock()
        fake_spec.cols = [fake_id_col, fake_extra_col]
        csv_obj.data_table_def.return_value = fake_spec

        # table_columns returns only ["id"] so import_cols = ["id"]
        with (
            patch.object(base_db, "table_exists", return_value=True),
            patch.object(base_db, "table_columns", return_value=["id"]),
        ):
            base_db.import_tabular_file(None, "t", csv_obj, skipheader=True)

        _, result = base_db.select_data("SELECT id FROM t;")
        assert len(result) == 1
        assert result[0][0] == 1

    def test_happy_path_all_cols_match(self, base_db, minimal_conf):
        """import_tabular_file() happy path: csv columns match table columns exactly.

        This exercises line 608 (import_cols = csv_cols) — the normal path when
        import_common_cols_only=False and there are no extra CSV columns.
        """
        from execsql.types import DT_Integer, DT_Text

        minimal_conf.import_common_cols_only = False
        base_db.execute("CREATE TABLE t (id INTEGER, name TEXT);")

        csv_obj = MagicMock()
        csv_obj.column_headers.return_value = ["id", "name"]
        csv_obj.csvfname = "test.csv"
        csv_obj.reader.return_value = iter([["id", "name"], [42, "carol"]])

        fake_id_col = MagicMock()
        fake_id_col.name = "id"
        fake_id_col.column_type.return_value = (None, DT_Integer)

        fake_name_col = MagicMock()
        fake_name_col.name = "name"
        fake_name_col.column_type.return_value = (None, DT_Text)

        fake_spec = MagicMock()
        fake_spec.cols = [fake_id_col, fake_name_col]
        csv_obj.data_table_def.return_value = fake_spec

        with (
            patch.object(base_db, "table_exists", return_value=True),
            patch.object(base_db, "table_columns", return_value=["id", "name"]),
        ):
            base_db.import_tabular_file(None, "t", csv_obj, skipheader=True)

        _, result = base_db.select_data("SELECT id, name FROM t;")
        assert len(result) == 1
        assert result[0] == (42, "carol")

    def test_get_ts_closure_caches_tablespec(self, base_db, minimal_conf):
        """The get_ts() closure in import_tabular_file() must cache the tablespec.

        This exercises lines 611->613 — the branch where get_ts.tablespec is
        already populated so data_table_def() is not called a second time.
        We do this by inserting multiple rows so populate_table() calls get_ts()
        more than once internally.
        """
        from execsql.types import DT_Integer

        minimal_conf.import_common_cols_only = False
        minimal_conf.import_row_buffer = 2  # force multiple buffer iterations
        base_db.execute("CREATE TABLE t (id INTEGER);")

        csv_obj = MagicMock()
        csv_obj.column_headers.return_value = ["id"]
        csv_obj.csvfname = "test.csv"
        # 5 rows — with buffer=2 this triggers multiple iterations
        csv_obj.reader.return_value = iter([["id"], [1], [2], [3], [4], [5]])

        fake_id_col = MagicMock()
        fake_id_col.name = "id"
        fake_id_col.column_type.return_value = (None, DT_Integer)
        fake_spec = MagicMock()
        fake_spec.cols = [fake_id_col]
        csv_obj.data_table_def.return_value = fake_spec

        with (
            patch.object(base_db, "table_exists", return_value=True),
            patch.object(base_db, "table_columns", return_value=["id"]),
        ):
            base_db.import_tabular_file(None, "t", csv_obj, skipheader=True)

        _, result = base_db.select_data("SELECT id FROM t ORDER BY id;")
        assert len(result) == 5
        # data_table_def() called only once (get_ts caches on first call)
        csv_obj.data_table_def.assert_called_once()

    def test_populate_table_with_show_progress_true_rich_available(self, base_db, minimal_conf):
        """When show_progress=True and rich is available, the progress bar is used."""
        from execsql.types import DT_Integer

        minimal_conf.show_progress = True
        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])
        # This exercises lines 457-469 when rich IS installed
        base_db.populate_table(None, "t", iter([[1], [2]]), ["id"], ts)
        _, rows = base_db.select_data("SELECT id FROM t ORDER BY id;")
        assert len(rows) == 2

    def test_populate_table_with_show_progress_true_rich_unavailable(self, base_db, minimal_conf):
        """When show_progress=True but rich is not importable, fall back silently.

        This exercises lines 469-470 (the except ImportError: use_progress = False path).
        """
        import sys
        from execsql.types import DT_Integer

        minimal_conf.show_progress = True
        base_db.execute("CREATE TABLE t (id INTEGER);")
        ts = _make_tablespec_typed([("id", DT_Integer)])

        # Temporarily remove rich from sys.modules and block its import
        saved = {}
        for key in list(sys.modules.keys()):
            if key == "rich" or key.startswith("rich."):
                saved[key] = sys.modules.pop(key)

        import builtins

        real_import = builtins.__import__

        def block_rich(name, *args, **kwargs):
            if name == "rich.progress" or name == "rich.console" or name == "rich":
                raise ImportError("rich not available")
            return real_import(name, *args, **kwargs)

        try:
            with patch.object(builtins, "__import__", side_effect=block_rich):
                base_db.populate_table(None, "t", iter([[1], [2]]), ["id"], ts)
        finally:
            # Restore rich modules
            sys.modules.update(saved)

        _, rows = base_db.select_data("SELECT id FROM t ORDER BY id;")
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# DatabasePool
# ---------------------------------------------------------------------------


class TestDatabasePoolInit:
    def test_pool_empty_initially(self):
        p = DatabasePool()
        assert p.aliases() == []

    def test_repr(self):
        p = DatabasePool()
        assert repr(p) == "DatabasePool()"

    def test_initial_db_none(self):
        p = DatabasePool()
        assert p.initial_db is None

    def test_current_db_none(self):
        p = DatabasePool()
        assert p.current_db is None

    def test_do_rollback_true(self):
        p = DatabasePool()
        assert p.do_rollback is True


class TestDatabasePoolAdd:
    def test_add_first_db_sets_initial_and_current(self):
        p = DatabasePool()
        db = FakeDatabase(server="s", db="d")
        p.add("main", db)
        assert p.initial_db == "main"
        assert p.current_db == "main"

    def test_add_second_db_does_not_change_initial_or_current(self):
        p = DatabasePool()
        db1 = FakeDatabase(server="s1", db="d1")
        db2 = FakeDatabase(server="s2", db="d2")
        p.add("main", db1)
        p.add("secondary", db2)
        assert p.initial_db == "main"
        assert p.current_db == "main"

    def test_add_lowercase_alias(self):
        p = DatabasePool()
        p.add("MAIN", FakeDatabase())
        assert "main" in p.aliases()

    def test_add_initial_to_nonempty_pool_raises(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        with pytest.raises(ErrInfo):
            p.add("initial", FakeDatabase())

    def test_aliases_returns_added_names(self):
        p = DatabasePool()
        p.add("a", FakeDatabase())
        p.add("b", FakeDatabase())
        assert set(p.aliases()) == {"a", "b"}

    def test_reassign_alias_logs_and_closes_old_connection(self):
        """Reassigning an existing alias must close the old connection and log a message."""

        # Set up _state.status with a BatchLevels that returns False for uses_db
        mock_status = MagicMock()
        mock_status.batch.uses_db.return_value = False
        _state.status = mock_status

        mock_log = MagicMock()
        _state.exec_log = mock_log

        p = DatabasePool()
        db1 = FakeDatabase(server="s1", db="d1")
        db2 = FakeDatabase(server="s2", db="d2")
        p.add("main", db1)
        # Second add under same alias: triggers reassignment path
        p.add("main", db2)

        mock_log.log_status_info.assert_called_once()
        assert "Reassigning" in mock_log.log_status_info.call_args[0][0]

    def test_reassign_alias_when_in_use_raises(self):
        """Reassigning an alias used in a running batch must raise ErrInfo."""
        mock_status = MagicMock()
        mock_status.batch.uses_db.return_value = True
        _state.status = mock_status

        p = DatabasePool()
        db1 = FakeDatabase(server="s1", db="d1")
        p.add("main", db1)

        with pytest.raises(ErrInfo):
            p.add("main", FakeDatabase(server="s2", db="d2"))


class TestDatabasePoolCurrent:
    def test_current_returns_first_added_db(self):
        p = DatabasePool()
        db = FakeDatabase(server="s", db="d")
        p.add("main", db)
        assert p.current() is db

    def test_current_alias_returns_string(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        assert p.current_alias() == "main"

    def test_initial_returns_first_db(self):
        p = DatabasePool()
        db = FakeDatabase()
        p.add("first", db)
        p.add("second", FakeDatabase())
        assert p.initial() is db

    def test_aliased_as_returns_correct_db(self):
        p = DatabasePool()
        db1 = FakeDatabase()
        db2 = FakeDatabase()
        p.add("a", db1)
        p.add("b", db2)
        assert p.aliased_as("b") is db2


class TestDatabasePoolMakeCurrent:
    def test_make_current_changes_current_db(self):
        p = DatabasePool()
        p.add("a", FakeDatabase())
        p.add("b", FakeDatabase())
        p.make_current("b")
        assert p.current_db == "b"

    def test_make_current_case_insensitive(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        p.make_current("MAIN")
        assert p.current_db == "main"

    def test_make_current_unknown_alias_raises(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        with pytest.raises(ErrInfo):
            p.make_current("unknown")


class TestDatabasePoolDisconnect:
    def test_disconnect_current_raises(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        with pytest.raises(ErrInfo):
            p.disconnect("main")

    def test_disconnect_nonexistent_alias_is_noop(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        # Should not raise — silently ignored
        p.disconnect("ghost")

    def test_disconnect_noncurrent_removes_alias(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        p.add("secondary", FakeDatabase())
        p.disconnect("secondary")
        assert "secondary" not in p.aliases()

    def test_disconnect_initial_alias_literally_named_raises(self):
        """disconnect('initial') when 'initial' is in pool should raise ErrInfo."""
        # 'initial' is blocked from being added to a non-empty pool, so we
        # manually insert it to exercise the disconnect guard.
        p = DatabasePool()
        p.add("main", FakeDatabase())
        p.pool["initial"] = FakeDatabase()
        with pytest.raises(ErrInfo):
            p.disconnect("initial")


class TestDatabasePoolCloseAll:
    def test_closeall_closes_all_connections(self):
        from execsql.db.sqlite import SQLiteDatabase

        p = DatabasePool()
        db1 = SQLiteDatabase(":memory:")
        db2 = SQLiteDatabase(":memory:")
        p.add("a", db1)
        p.add("b", db2)
        p.closeall()
        # After closeall, both connections should be None
        assert db1.conn is None
        assert db2.conn is None

    def test_closeall_resets_pool_to_empty(self):
        """After closeall(), the pool itself should be empty and current_db None."""
        p = DatabasePool()
        p.add("main", FakeDatabase())
        p.closeall()
        assert p.aliases() == []
        assert p.current_db is None

    def test_closeall_with_do_rollback_false_skips_rollback(self):
        """When do_rollback is False, closeall() must not call rollback() on connections."""
        from execsql.db.sqlite import SQLiteDatabase

        p = DatabasePool()
        p.do_rollback = False
        d = SQLiteDatabase(":memory:")
        rollback_calls = []
        original_rollback = d.rollback

        def tracking_rollback():
            rollback_calls.append(True)
            return original_rollback()

        d.rollback = tracking_rollback
        p.add("main", d)
        p.closeall()
        assert rollback_calls == []

    def test_closeall_swallows_close_exceptions_and_logs(self):
        """closeall() must log but not propagate exceptions raised during db.close()."""
        p = DatabasePool()
        bad_db = FakeDatabase(server="s", db="d")
        bad_db.conn = MagicMock()
        bad_db.conn.close.side_effect = RuntimeError("close failed")

        # Override the FakeDatabase.close() to actually try closing conn
        def real_close():
            if bad_db.conn:
                bad_db.conn.close()
                bad_db.conn = None

        bad_db.close = real_close
        bad_db.rollback = lambda: None

        mock_log = MagicMock()
        _state.exec_log = mock_log

        p.add("bad", bad_db)
        # closeall() must not raise even when close fails
        p.closeall()

        mock_log.log_status_error.assert_called_once()

    def test_closeall_silently_handles_none_exec_log(self):
        """closeall() must not raise when _state.exec_log is None during a close error."""
        p = DatabasePool()
        bad_db = FakeDatabase(server="s", db="d")
        bad_db.conn = MagicMock()
        bad_db.conn.close.side_effect = RuntimeError("close failed")

        def real_close():
            if bad_db.conn:
                bad_db.conn.close()
                bad_db.conn = None

        bad_db.close = real_close
        bad_db.rollback = lambda: None
        _state.exec_log = None

        p.add("bad", bad_db)
        p.closeall()  # should not raise


# ---------------------------------------------------------------------------
# Database deeper methods — exercised via SQLiteDatabase (no mocking)
# ---------------------------------------------------------------------------


class TestDatabaseDeeperMethods:
    """Tests for base-class methods not covered by the FakeDatabase tests above.

    These use a real in-memory SQLiteDatabase so the actual code paths in
    Database (not the stub overrides) are exercised.
    """

    @pytest.fixture
    def db(self):
        from execsql.db.sqlite import SQLiteDatabase

        d = SQLiteDatabase(":memory:")
        yield d
        d.close()

    def test_autocommit_off_then_on(self, db):
        db.autocommit_off()
        assert db.autocommit is False
        db.autocommit_on()
        assert db.autocommit is True

    def test_incomplete_subclass_cannot_be_instantiated(self):
        # A subclass that only implements open_db but not exec_cmd cannot be instantiated.
        class IncompleteDatabase(Database):
            def open_db(self):
                pass

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteDatabase(server_name=None, db_name=None)

    def test_select_rowdict_returns_dicts(self, db):
        db.execute("CREATE TABLE t (a INTEGER, b TEXT);")
        db.execute("INSERT INTO t VALUES (1, 'hello');")
        db.execute("INSERT INTO t VALUES (2, 'world');")
        hdrs, dicts = db.select_rowdict("SELECT * FROM t ORDER BY a;")
        rows = list(dicts)
        assert hdrs == ["a", "b"]
        assert rows == [{"a": 1, "b": "hello"}, {"a": 2, "b": "world"}]

    def test_select_rowdict_empty_table(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        hdrs, dicts = db.select_rowdict("SELECT * FROM t;")
        rows = list(dicts)
        assert hdrs == ["id"]
        assert rows == []

    def test_cursor_returns_cursor_object(self, db):
        curs = db.cursor()
        assert curs is not None

    def test_role_exists_raises_not_implemented(self, db):
        from execsql.exceptions import DatabaseNotImplementedError

        with pytest.raises(DatabaseNotImplementedError):
            db.role_exists("some_role")

    def test_select_data_returns_headers_and_rows(self, db):
        db.execute("CREATE TABLE t (a INTEGER, b TEXT);")
        db.execute("INSERT INTO t VALUES (1, 'x');")
        hdrs, rows = db.select_data("SELECT a, b FROM t;")
        assert hdrs == ["a", "b"]
        assert len(rows) == 1
        assert rows[0][0] == 1

    def test_select_rowsource_returns_generator(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        db.execute("INSERT INTO t VALUES (10);")
        db.execute("INSERT INTO t VALUES (20);")
        hdrs, gen = db.select_rowsource("SELECT id FROM t ORDER BY id;")
        assert hdrs == ["id"]
        rows = list(gen)
        assert len(rows) == 2

    def test_execute_with_paramlist(self, db):
        db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        db.execute("INSERT INTO t VALUES (?, ?);", [1, "Alice"])
        _, rows = db.select_data("SELECT name FROM t WHERE id = 1;")
        assert rows[0][0] == "Alice"

    def test_paramsubs(self, db):
        result = db.paramsubs(3)
        assert result == "?,?,?"

    def test_paramsubs_single(self, db):
        result = db.paramsubs(1)
        assert result == "?"

    def test_schema_qualified_name_no_schema(self, db):
        # SQLiteDatabase has a proper type.quoted; no schema -> just quoted table name
        result = db.schema_qualified_table_name(None, "mytable")
        assert "mytable" in result

    def test_schema_qualified_name_with_schema(self, db):
        result = db.schema_qualified_table_name("myschema", "mytable")
        assert "myschema" in result
        assert "mytable" in result

    def test_rollback_does_not_raise(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        # rollback on a connection that has no pending transaction is OK
        db.rollback()

    def test_drop_table_removes_table(self, db):
        db.execute("CREATE TABLE droptarget (id INTEGER);")
        db.execute("INSERT INTO droptarget VALUES (1);")
        db.drop_table("droptarget")
        # Table should no longer exist; select_data re-raises the raw driver exception
        with pytest.raises(sqlite3.OperationalError):
            db.select_data("SELECT * FROM droptarget;")

    def test_table_columns_returns_column_names(self, db):
        db.execute("CREATE TABLE t (alpha INTEGER, beta TEXT);")
        cols = db.table_columns("t")
        assert "alpha" in cols
        assert "beta" in cols

    def test_commit_no_error(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        db.execute("INSERT INTO t VALUES (1);")
        db.commit()  # should not raise

    def test_autocommit_off_no_error(self, db):
        db.autocommit_off()
        assert db.autocommit is False
        db.autocommit_on()
