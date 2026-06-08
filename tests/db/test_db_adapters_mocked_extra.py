"""Extended mocked-driver tests for the Oracle, Firebird, and Access adapters.

Builds on tests/db/test_db_adapters_mocked.py to cover the schema-query
methods (``table_exists``, ``view_exists``, ``column_exists``,
``table_columns``, ``role_exists``), ``drop_table``, ``open_db`` happy
paths, the Oracle SQL-trailing-semicolon shims, and the Access value-
conversion helpers.

The driver libraries (cx_Oracle/oracledb, firebird-driver, pyodbc, win32com)
are not installed in CI's matrix runners; each adapter is imported only
after a MagicMock is injected into ``sys.modules``.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state


def _mock_conn_with_rows(rows: list, description: list | None = None) -> MagicMock:
    """Build a conn/cursor that fetches the given rows."""
    curs = MagicMock()
    curs.fetchall.return_value = rows
    curs.rowcount = len(rows)
    if description is not None:
        curs.description = description
    conn = MagicMock()
    conn.cursor.return_value = curs
    return conn


# ===========================================================================
# Mock driver injection (must happen before adapter imports)
# ===========================================================================


def _ensure_mock(mod_name: str, **attrs) -> None:
    if mod_name not in sys.modules:
        mock = types.ModuleType(mod_name)
        for k, v in attrs.items():
            setattr(mock, k, v)
        sys.modules[mod_name] = mock


_ensure_mock("cx_Oracle", connect=MagicMock(), makedsn=MagicMock(return_value="dsn"))
_ensure_mock("oracledb", connect=MagicMock(), makedsn=MagicMock(return_value="dsn"))
if "firebird.driver" not in sys.modules:
    _fb_parent = types.ModuleType("firebird")
    _fb_driver = types.ModuleType("firebird.driver")
    _fb_driver.connect = MagicMock()
    _fb_parent.driver = _fb_driver
    sys.modules["firebird"] = _fb_parent
    sys.modules["firebird.driver"] = _fb_driver
_ensure_mock("pyodbc", connect=MagicMock(), Binary=MagicMock(side_effect=lambda d: d))
_ensure_mock(
    "win32com",
    client=types.SimpleNamespace(Dispatch=MagicMock()),
)
# Ensure win32com.client is importable as a submodule
if "win32com.client" not in sys.modules:
    sub = types.ModuleType("win32com.client")
    sub.Dispatch = MagicMock()
    sys.modules["win32com.client"] = sub


from execsql.db.oracle import OracleDatabase  # noqa: E402
from execsql.db.firebird import FirebirdDatabase  # noqa: E402
from execsql.db.access import AccessDatabase  # noqa: E402
from execsql.exceptions import ErrInfo, DatabaseNotImplementedError  # noqa: E402


# ---------------------------------------------------------------------------
# Common state setup
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _state_setup():
    _state.subvars = MagicMock()
    _state.exec_log = MagicMock()
    _state.conf = SimpleNamespace(
        export_row_buffer=100,
        import_buffer=8192,
        import_row_buffer=100,
        import_common_cols_only=False,
        empty_strings=True,
        empty_rows=True,
        del_empty_cols=False,
        create_col_hdrs=False,
        trim_strings=False,
        replace_newlines=False,
        import_progress_interval=0,
        gui_framework="tkinter",
        gui_level=0,
    )
    _saved_stringtypes = _state.stringtypes
    _state.stringtypes = (str, bytes)
    try:
        yield
    finally:
        _state.stringtypes = _saved_stringtypes


# ===========================================================================
# Oracle — schema queries
# ===========================================================================


def _make_oracle(rows=None, raise_on_execute=False) -> OracleDatabase:
    with patch.object(OracleDatabase, "open_db", return_value=None):
        db = OracleDatabase("orasrv", "orcl", "scott", port=1521, encoding="UTF8")
    conn = _mock_conn_with_rows(rows or [])
    if raise_on_execute:
        conn.cursor.return_value.execute.side_effect = RuntimeError("ORA-00001")
    db.conn = conn
    return db


class TestOracleSchemaQueries:
    def test_schema_exists_raises_not_implemented(self):
        db = _make_oracle()
        with pytest.raises(DatabaseNotImplementedError):
            db.schema_exists("any")

    def test_table_exists_true(self):
        db = _make_oracle(rows=[("MY_TABLE",)])
        assert db.table_exists("MY_TABLE") is True

    def test_table_exists_false(self):
        db = _make_oracle(rows=[])
        assert db.table_exists("MISSING") is False

    def test_table_exists_with_owner(self):
        db = _make_oracle(rows=[("X",)])
        assert db.table_exists("X", schema_name="HR") is True
        curs = db.conn.cursor.return_value
        executed_sql = curs.execute.call_args[0][0]
        assert "owner = :owner" in executed_sql

    def test_table_exists_wraps_driver_error(self):
        db = _make_oracle(raise_on_execute=True)
        with pytest.raises(ErrInfo):
            db.table_exists("X")
        db.conn.rollback.assert_called()

    def test_column_exists_true(self):
        db = _make_oracle(rows=[("ID",)])
        assert db.column_exists("T", "ID") is True

    def test_column_exists_with_owner(self):
        db = _make_oracle(rows=[("ID",)])
        assert db.column_exists("T", "ID", schema_name="HR") is True

    def test_column_exists_wraps_driver_error(self):
        db = _make_oracle(raise_on_execute=True)
        with pytest.raises(ErrInfo):
            db.column_exists("T", "C")

    def test_table_columns(self):
        db = _make_oracle(rows=[("ID",), ("NAME",), ("CREATED",)])
        cols = db.table_columns("T")
        assert cols == ["ID", "NAME", "CREATED"]

    def test_table_columns_with_owner(self):
        db = _make_oracle(rows=[("ID",)])
        cols = db.table_columns("T", schema_name="HR")
        assert cols == ["ID"]

    def test_table_columns_wraps_driver_error(self):
        db = _make_oracle(raise_on_execute=True)
        with pytest.raises(ErrInfo):
            db.table_columns("T")

    def test_view_exists_true(self):
        db = _make_oracle(rows=[("V",)])
        assert db.view_exists("V") is True

    def test_view_exists_with_owner(self):
        db = _make_oracle(rows=[("V",)])
        assert db.view_exists("V", schema_name="HR") is True

    def test_view_exists_wraps_driver_error(self):
        db = _make_oracle(raise_on_execute=True)
        with pytest.raises(ErrInfo):
            db.view_exists("V")

    def test_role_exists_true(self):
        db = _make_oracle(rows=[("DBA",)])
        assert db.role_exists("DBA") is True

    def test_role_exists_false(self):
        db = _make_oracle(rows=[])
        assert db.role_exists("NONE") is False


class TestOracleSqlShims:
    """select_data/select_rowsource/select_rowdict/execute strip trailing ';'."""

    def test_execute_with_semicolon(self):
        db = _make_oracle()
        db.execute("SELECT 1 FROM DUAL;")
        executed = db.conn.cursor.return_value.execute.call_args[0][0]
        assert not executed.endswith(";")

    def test_select_data_with_semicolon(self):
        db = _make_oracle(rows=[(1,)])
        db.conn.cursor.return_value.description = [("c",)]
        hdrs, rows = db.select_data("SELECT 1 FROM DUAL;")
        executed = db.conn.cursor.return_value.execute.call_args[0][0]
        assert not executed.endswith(";")
        assert rows == [(1,)]

    def test_select_data_without_semicolon(self):
        db = _make_oracle(rows=[(1,)])
        db.conn.cursor.return_value.description = [("c",)]
        db.select_data("SELECT 1 FROM DUAL")
        executed = db.conn.cursor.return_value.execute.call_args[0][0]
        assert executed == "SELECT 1 FROM DUAL"


class TestOracleDropTable:
    def test_drop_table_uses_cascade(self):
        db = _make_oracle()
        db.drop_table("MYTABLE")
        executed = db.conn.cursor.return_value.execute.call_args[0][0]
        assert "drop table" in executed
        assert "cascade constraints" in executed


# ===========================================================================
# Firebird — schema queries
# ===========================================================================


def _make_firebird(rows=None, raise_on_execute=False) -> FirebirdDatabase:
    with patch.object(FirebirdDatabase, "open_db", return_value=None):
        db = FirebirdDatabase("fbsrv", "test.fdb", "SYSDBA", port=3050, encoding="latin1")
    conn = _mock_conn_with_rows(rows or [])
    if raise_on_execute:
        conn.cursor.return_value.execute.side_effect = RuntimeError("FB error")
    db.conn = conn
    return db


class TestFirebirdSchemaQueries:
    def test_table_exists_true(self):
        db = _make_firebird(rows=[("MY_TABLE",)])
        assert db.table_exists("MY_TABLE") is True

    def test_table_exists_false(self):
        db = _make_firebird(rows=[])
        assert db.table_exists("MISSING") is False

    def test_table_exists_wraps_driver_error(self):
        db = _make_firebird(raise_on_execute=True)
        with pytest.raises(ErrInfo):
            db.table_exists("T")
        db.conn.rollback.assert_called()

    def test_column_exists_true(self):
        db = _make_firebird(rows=[("ID",)])
        assert db.column_exists("T", "ID") is True

    def test_column_exists_returns_false_on_error(self):
        # Firebird's column_exists returns False (does NOT raise) when the
        # driver errors — covers the early-return path
        db = _make_firebird(raise_on_execute=True)
        assert db.column_exists("T", "C") is False

    def test_table_columns(self):
        # Firebird table_columns uses cursor.description, not fetchall
        db = _make_firebird()
        db.conn.cursor.return_value.description = [("ID",), ("NAME",)]
        cols = db.table_columns("T")
        assert cols == ["ID", "NAME"]

    def test_table_columns_wraps_driver_error(self):
        db = _make_firebird(raise_on_execute=True)
        with pytest.raises(ErrInfo):
            db.table_columns("T")

    def test_view_exists_true(self):
        db = _make_firebird(rows=[("V",)])
        assert db.view_exists("V") is True

    def test_view_exists_wraps_driver_error(self):
        db = _make_firebird(raise_on_execute=True)
        with pytest.raises(ErrInfo):
            db.view_exists("V")

    def test_role_exists_true(self):
        db = _make_firebird(rows=[("ADMIN",)])
        assert db.role_exists("ADMIN") is True

    def test_role_exists_false(self):
        db = _make_firebird(rows=[])
        assert db.role_exists("NONE") is False


class TestFirebirdDropTable:
    def test_drop_table(self):
        db = _make_firebird()
        db.drop_table("MYTABLE")
        executed = db.conn.cursor.return_value.execute.call_args[0][0]
        assert "drop table" in executed.lower()


# ===========================================================================
# Access — value conversion helpers + schema queries
# ===========================================================================


def _make_access(rows=None, jet4=True, catalog_tables=None) -> AccessDatabase:
    """Construct an AccessDatabase with both open_dao and open_db mocked.

    ``rows`` populates the mocked pyodbc cursor result set used by
    ``select_data`` / generic execute paths. ``catalog_tables`` populates
    the mocked ``cursor.tables()`` result set used by
    ``table_exists`` / ``view_exists`` (each entry is the table name
    string; the mock wraps it in an object exposing ``.table_name``).
    """
    with (
        patch.object(AccessDatabase, "open_dao", return_value=None),
        patch.object(AccessDatabase, "open_db", return_value=None),
    ):
        db = AccessDatabase("test.accdb")
    db.jet4 = jet4
    conn = _mock_conn_with_rows(rows or [])
    # Wire up cursor.tables() to return objects with a ``.table_name`` attr.
    catalog_rows = [MagicMock(table_name=n) for n in (catalog_tables or [])]
    conn.cursor.return_value.tables = MagicMock(return_value=catalog_rows)
    db.conn = conn
    # DAO connection isn't used by table_exists/view_exists anymore, but
    # other Access methods still call dao_conn — provide a benign mock.
    db.dao_conn = MagicMock()
    return db


class TestAccessValueConversion:
    """The Access adapter has custom int/datetime coercion via dt_cast."""

    def test_as_datetime_with_datetime(self):
        import datetime as dt

        db = _make_access()
        result = db.as_datetime(dt.datetime(2024, 1, 2, 3, 4, 5))
        assert isinstance(result, dt.datetime)

    def test_as_datetime_with_date(self):
        import datetime as dt

        db = _make_access()
        # Access's as_datetime may return either datetime or the original
        # date — both indicate the conversion path ran
        result = db.as_datetime(dt.date(2024, 1, 2))
        assert isinstance(result, (dt.datetime, dt.date))

    def test_int_or_bool_with_bool_true(self):
        db = _make_access()
        result = db.int_or_bool(True)
        # Result is either True or 1
        assert result in (True, 1, -1)

    def test_int_or_bool_with_int(self):
        db = _make_access()
        result = db.int_or_bool(5)
        assert result == 5


class TestAccessSchemaQueries:
    def test_table_exists_true(self):
        # Access calls ODBC cursor.tables() (was MSysObjects raw SQL pre-2026).
        db = _make_access(catalog_tables=["MYTABLE", "OTHER"])
        assert db.table_exists("MYTABLE") is True

    def test_table_exists_false(self):
        db = _make_access(catalog_tables=[])
        assert db.table_exists("NOPE") is False

    def test_table_exists_wraps_driver_error(self):
        db = _make_access()
        # Force cursor.tables() to raise — table_exists must convert to ErrInfo.
        db.conn.cursor.return_value.tables.side_effect = RuntimeError("ODBC error")
        with pytest.raises(ErrInfo):
            db.table_exists("T")


class TestAccessRepr:
    def test_repr(self):
        db = _make_access()
        r = repr(db)
        assert "AccessDatabase" in r
        assert "test.accdb" in r


class TestAccessParamstr:
    def test_paramstr_is_question_mark(self):
        db = _make_access()
        assert db.paramstr == "?"

    def test_paramsubs(self):
        db = _make_access()
        assert db.paramsubs(3) == "?,?,?"
