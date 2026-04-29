from __future__ import annotations

"""
Mocked unit tests for Oracle, SQL Server, Firebird, and MS Access adapters.

None of these adapters' driver libraries (cx_Oracle, pyodbc, fdb, win32com)
are installed in the test environment.  Each class section injects a
``MagicMock`` module into ``sys.modules`` before importing the adapter, so
the import guard inside each ``__init__`` succeeds without a real driver.

Tests focus exclusively on **pure-logic methods** that do not require an
open database connection:
  - __repr__
  - Attribute defaults (paramstr, encoding, port)
  - paramsubs()
  - execute() — semicolon-stripping for Oracle
  - exec_cmd() — SQL generation and $LAST_ROWCOUNT update
  - schema_exists() — adapters that always return False
  - as_datetime() / int_or_bool() — Access value-conversion helpers
"""

import datetime
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state


# ---------------------------------------------------------------------------
# Shared helper — build a mock conn/cursor pair
# ---------------------------------------------------------------------------


def _mock_conn(rowcount: int = 0) -> MagicMock:
    curs = MagicMock()
    curs.rowcount = rowcount
    curs.close = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = curs
    conn.rollback = MagicMock()
    conn.close = MagicMock()
    return conn


# ===========================================================================
# Oracle adapter
# ===========================================================================


def _ensure_cx_oracle_mock() -> MagicMock:
    """Inject a MagicMock for cx_Oracle into sys.modules if not already present."""
    if "cx_Oracle" not in sys.modules:
        mock = types.ModuleType("cx_Oracle")
        mock.connect = MagicMock()
        mock.makedsn = MagicMock(return_value="fake_dsn")
        sys.modules["cx_Oracle"] = mock
    return sys.modules["cx_Oracle"]


_ensure_cx_oracle_mock()

from execsql.db.oracle import OracleDatabase  # noqa: E402


def _make_oracle(server: str = "orasrv", db: str = "orcl", user: str | None = "scott") -> OracleDatabase:
    """Return an OracleDatabase with open_db() bypassed."""
    with patch.object(OracleDatabase, "open_db", return_value=None):
        return OracleDatabase(server, db, user, port=1521, encoding="UTF8")


class TestOracleDatabase:
    """Pure-logic tests for OracleDatabase."""

    def test_repr_contains_server(self):
        db = _make_oracle(server="myhost")
        assert "myhost" in repr(db)

    def test_repr_contains_db_name(self):
        db = _make_oracle(db="mydb")
        assert "mydb" in repr(db)

    def test_repr_contains_user(self):
        db = _make_oracle(user="tiger")
        assert "tiger" in repr(db)

    def test_repr_starts_with_class_name(self):
        db = _make_oracle()
        assert repr(db).startswith("OracleDatabase(")

    def test_paramstr_is_colon_one(self):
        db = _make_oracle()
        assert db.paramstr == ":1"

    def test_paramsubs_single(self):
        db = _make_oracle()
        assert db.paramsubs(1) == ":1"

    def test_paramsubs_multiple(self):
        db = _make_oracle()
        assert db.paramsubs(3) == ":1,:2,:3"

    def test_paramsubs_five(self):
        db = _make_oracle()
        assert db.paramsubs(5) == ":1,:2,:3,:4,:5"

    def test_paramsubs_zero_is_empty(self):
        db = _make_oracle()
        assert db.paramsubs(0) == ""

    def test_execute_strips_trailing_semicolon(self):
        """OracleDatabase.execute() strips a trailing ';' before forwarding to the base class."""
        db = _make_oracle()
        conn = _mock_conn()
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.execute("SELECT 1 FROM DUAL;")

        curs = conn.cursor.return_value
        executed_sql = curs.execute.call_args[0][0]
        assert not executed_sql.endswith(";"), f"Semicolon not stripped: {executed_sql!r}"

    def test_execute_without_semicolon_unchanged(self):
        db = _make_oracle()
        conn = _mock_conn()
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.execute("SELECT 1 FROM DUAL")
        curs = conn.cursor.return_value
        executed_sql = curs.execute.call_args[0][0]
        assert executed_sql == "SELECT 1 FROM DUAL"

    def test_exec_cmd_generates_select_call_syntax(self):
        """exec_cmd builds 'select <name>()' and executes it."""
        db = _make_oracle()
        conn = _mock_conn(rowcount=5)
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.exec_cmd("do_work")

        curs = conn.cursor.return_value
        sql = curs.execute.call_args[0][0]
        assert sql == 'select "do_work"()'

    def test_exec_cmd_updates_last_rowcount(self):
        db = _make_oracle()
        conn = _mock_conn(rowcount=13)
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.exec_cmd("my_func")
        _state.subvars.add_substitution.assert_called_with("$LAST_ROWCOUNT", 13)

    def test_exec_cmd_rollback_on_error(self):
        db = _make_oracle()
        conn = _mock_conn()
        db.conn = conn
        curs = conn.cursor.return_value
        curs.execute.side_effect = RuntimeError("ORA-00000")
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        with pytest.raises(RuntimeError):
            db.exec_cmd("broken_func")

        conn.rollback.assert_called_once()

    def test_default_port_is_1521(self):
        db = _make_oracle()
        assert db.port == 1521

    def test_default_encoding_is_utf8(self):
        db = _make_oracle()
        assert db.encoding == "UTF8"

    def test_encode_commands_is_false(self):
        """Oracle adapter does not encode SQL bytes — it passes strings directly."""
        db = _make_oracle()
        assert db.encode_commands is False


# ===========================================================================
# SQL Server adapter
# ===========================================================================


def _ensure_pyodbc_mock() -> MagicMock:
    if "pyodbc" not in sys.modules:
        mock = types.ModuleType("pyodbc")
        mock.connect = MagicMock()
        mock.Binary = MagicMock(side_effect=lambda d: d)
        sys.modules["pyodbc"] = mock
    return sys.modules["pyodbc"]


_ensure_pyodbc_mock()

from execsql.db.sqlserver import SqlServerDatabase  # noqa: E402


def _make_sqlserver(
    server: str = "sqlsrv",
    db: str = "testdb",
    user: str | None = "sa",
) -> SqlServerDatabase:
    with patch.object(SqlServerDatabase, "open_db", return_value=None):
        return SqlServerDatabase(server, db, user, port=1433, encoding="latin1")


class TestSqlServerDatabase:
    """Pure-logic tests for SqlServerDatabase."""

    def test_repr_contains_server(self):
        db = _make_sqlserver(server="SQLHOST")
        assert "SQLHOST" in repr(db)

    def test_repr_contains_db_name(self):
        db = _make_sqlserver(db="sales_db")
        assert "sales_db" in repr(db)

    def test_repr_contains_user(self):
        db = _make_sqlserver(user="admin")
        assert "admin" in repr(db)

    def test_repr_starts_with_class_name(self):
        db = _make_sqlserver()
        assert repr(db).startswith("SqlServerDatabase(")

    def test_paramstr_is_question_mark(self):
        db = _make_sqlserver()
        assert db.paramstr == "?"

    def test_default_port_is_1433(self):
        db = _make_sqlserver()
        assert db.port == 1433

    def test_default_encoding_is_latin1(self):
        db = _make_sqlserver()
        assert db.encoding == "latin1"

    def test_exec_cmd_generates_execute_syntax(self):
        db = _make_sqlserver()
        conn = _mock_conn(rowcount=3)
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.exec_cmd("run_etl")

        curs = conn.cursor.return_value
        raw_arg = curs.execute.call_args[0][0]
        assert raw_arg == 'execute "run_etl";'

    def test_exec_cmd_updates_last_rowcount(self):
        db = _make_sqlserver()
        conn = _mock_conn(rowcount=99)
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.exec_cmd("sp_refresh")
        _state.subvars.add_substitution.assert_called_with("$LAST_ROWCOUNT", 99)

    def test_exec_cmd_rollback_on_error(self):
        db = _make_sqlserver()
        conn = _mock_conn()
        db.conn = conn
        curs = conn.cursor.return_value
        curs.execute.side_effect = RuntimeError("connection lost")
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        with pytest.raises(RuntimeError):
            db.exec_cmd("bad_proc")

        conn.rollback.assert_called_once()


# ===========================================================================
# Firebird adapter
# ===========================================================================


def _ensure_fdb_mock() -> MagicMock:
    if "fdb" not in sys.modules:
        mock = types.ModuleType("fdb")
        mock.connect = MagicMock()
        sys.modules["fdb"] = mock
    return sys.modules["fdb"]


_ensure_fdb_mock()

from execsql.db.firebird import FirebirdDatabase  # noqa: E402


def _make_firebird(
    server: str = "fbsrv",
    db: str = "test.fdb",
    user: str | None = "SYSDBA",
) -> FirebirdDatabase:
    with patch.object(FirebirdDatabase, "open_db", return_value=None):
        return FirebirdDatabase(server, db, user, port=3050, encoding="latin1")


class TestFirebirdDatabase:
    """Pure-logic tests for FirebirdDatabase."""

    def test_repr_contains_server(self):
        db = _make_firebird(server="fbhost")
        assert "fbhost" in repr(db)

    def test_repr_contains_db_name(self):
        db = _make_firebird(db="mydata.fdb")
        assert "mydata.fdb" in repr(db)

    def test_repr_contains_user(self):
        db = _make_firebird(user="SYSDBA")
        assert "SYSDBA" in repr(db)

    def test_repr_starts_with_class_name(self):
        db = _make_firebird()
        assert repr(db).startswith("FirebirdDatabase(")

    def test_default_port_is_3050(self):
        db = _make_firebird()
        assert db.port == 3050

    def test_port_none_defaults_to_3050(self):
        with patch.object(FirebirdDatabase, "open_db", return_value=None):
            db = FirebirdDatabase("srv", "db.fdb", "user", port=None)
        assert db.port == 3050

    def test_default_encoding_is_latin1(self):
        db = _make_firebird()
        assert db.encoding == "latin1"

    def test_encoding_none_defaults_to_latin1(self):
        with patch.object(FirebirdDatabase, "open_db", return_value=None):
            db = FirebirdDatabase("srv", "db.fdb", "user", encoding=None)
        assert db.encoding == "latin1"

    def test_paramstr_is_question_mark(self):
        db = _make_firebird()
        assert db.paramstr == "?"

    def test_schema_exists_always_returns_false(self):
        db = _make_firebird()
        assert db.schema_exists("public") is False

    def test_schema_exists_any_name_returns_false(self):
        db = _make_firebird()
        assert db.schema_exists("dbo") is False

    def test_exec_cmd_generates_execute_procedure_syntax(self):
        db = _make_firebird()
        conn = _mock_conn(rowcount=0)
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.exec_cmd("update_stats")

        curs = conn.cursor.return_value
        sql_arg = curs.execute.call_args[0][0]
        assert sql_arg == 'execute procedure "update_stats";'

    def test_exec_cmd_updates_last_rowcount(self):
        db = _make_firebird()
        conn = _mock_conn(rowcount=7)
        db.conn = conn
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        db.exec_cmd("do_thing")
        _state.subvars.add_substitution.assert_called_with("$LAST_ROWCOUNT", 7)

    def test_exec_cmd_rollback_on_error(self):
        db = _make_firebird()
        conn = _mock_conn()
        db.conn = conn
        curs = conn.cursor.return_value
        curs.execute.side_effect = RuntimeError("deadlock")
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        with pytest.raises(RuntimeError):
            db.exec_cmd("boom_proc")

        conn.rollback.assert_called_once()


# ===========================================================================
# MS Access adapter
# ===========================================================================


def _ensure_win32com_mock() -> tuple[MagicMock, MagicMock]:
    """Inject win32com and win32com.client mocks if not present."""
    if "win32com" not in sys.modules:
        win32com_mod = types.ModuleType("win32com")
        win32com_client_mod = types.ModuleType("win32com.client")
        win32com_client_mod.Dispatch = MagicMock()
        win32com_mod.client = win32com_client_mod
        sys.modules["win32com"] = win32com_mod
        sys.modules["win32com.client"] = win32com_client_mod
    return sys.modules["win32com"], sys.modules["win32com.client"]


_ensure_win32com_mock()
# pyodbc may have already been added above; ensure it's present.
_ensure_pyodbc_mock()

from execsql.db.access import AccessDatabase  # noqa: E402


def _make_access(fn: str = "test.accdb") -> AccessDatabase:
    """Return an AccessDatabase with both open_dao() and open_db() stubbed."""
    _state.exec_log = MagicMock()
    with (
        patch.object(AccessDatabase, "open_dao", return_value=None),
        patch.object(
            AccessDatabase,
            "open_db",
            return_value=None,
        ),
    ):
        db = AccessDatabase(fn)
    return db


class TestAccessDatabase:
    """Pure-logic tests for AccessDatabase."""

    def test_repr_contains_db_name(self):
        db = _make_access("sales.accdb")
        assert "sales.accdb" in repr(db)

    def test_repr_contains_encoding(self):
        db = _make_access()
        assert "windows-1252" in repr(db)

    def test_repr_starts_with_class_name(self):
        db = _make_access()
        assert repr(db).startswith("AccessDatabase(")

    def test_paramstr_is_question_mark(self):
        db = _make_access()
        assert db.paramstr == "?"

    def test_default_encoding_is_windows_1252(self):
        db = _make_access()
        assert db.encoding == "windows-1252"

    def test_schema_exists_always_returns_false(self):
        db = _make_access()
        assert db.schema_exists("dbo") is False

    def test_schema_exists_any_name_returns_false(self):
        db = _make_access()
        assert db.schema_exists("public") is False

    # -----------------------------------------------------------------------
    # as_datetime
    # -----------------------------------------------------------------------

    def test_as_datetime_none_returns_none(self):
        db = _make_access()
        assert db.as_datetime(None) is None

    def test_as_datetime_empty_string_returns_none(self):
        db = _make_access()
        assert db.as_datetime("") is None

    def test_as_datetime_datetime_object_passthrough(self):
        db = _make_access()
        dt = datetime.datetime(2024, 3, 15, 10, 30, 0)
        result = db.as_datetime(dt)
        assert result == dt

    def test_as_datetime_date_object_passthrough(self):
        db = _make_access()
        d = datetime.date(2024, 6, 1)
        result = db.as_datetime(d)
        assert result == d

    def test_as_datetime_time_object_passthrough(self):
        db = _make_access()
        t = datetime.time(8, 45, 0)
        result = db.as_datetime(t)
        assert result == t

    def test_as_datetime_iso_string_parses(self):
        db = _make_access()
        result = db.as_datetime("2024-01-20 09:00:00")
        assert isinstance(result, datetime.datetime | datetime.date)

    # -----------------------------------------------------------------------
    # int_or_bool
    # -----------------------------------------------------------------------

    def test_int_or_bool_none_returns_none(self):
        db = _make_access()
        assert db.int_or_bool(None) is None

    def test_int_or_bool_empty_string_returns_none(self):
        db = _make_access()
        assert db.int_or_bool("") is None

    def test_int_or_bool_true_returns_one(self):
        db = _make_access()
        assert db.int_or_bool(True) == 1

    def test_int_or_bool_false_returns_zero(self):
        db = _make_access()
        assert db.int_or_bool(False) == 0

    def test_int_or_bool_int_42_returns_42(self):
        db = _make_access()
        assert db.int_or_bool(42) == 42

    def test_int_or_bool_string_42_returns_42(self):
        db = _make_access()
        assert db.int_or_bool("42") == 42

    def test_int_or_bool_zero_returns_zero(self):
        db = _make_access()
        assert db.int_or_bool(0) == 0

    def test_int_or_bool_negative_returns_int(self):
        db = _make_access()
        assert db.int_or_bool(-5) == -5

    def test_int_or_bool_return_type_is_int_for_numeric(self):
        db = _make_access()
        result = db.int_or_bool("100")
        assert isinstance(result, int)
