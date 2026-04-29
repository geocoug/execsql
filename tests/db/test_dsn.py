from __future__ import annotations

"""
Tests for execsql.db.dsn — DsnDatabase (ODBC DSN adapter).

``pyodbc`` is not installed in the test environment (it is an optional
dependency), so the entire module is mocked via ``sys.modules`` before
``DsnDatabase`` is imported.  Every test that exercises connection or
cursor behaviour wires up its own ``MagicMock`` objects.

Coverage:
- Constructor attributes (type, db_name, user, encoding, paramstr)
- __repr__
- open_db() — no-password path, with-password path
- open_db() — "Optional feature not implemented" autocommit fallback
- open_db() — hard connection failure raises ErrInfo
- exec_cmd() — correct SQL, $LAST_ROWCOUNT updated
- exec_cmd() — rollback called on cursor error
- import_entire_file() — reads file, calls INSERT with pyodbc.Binary
- import_entire_file() — schema-qualified table name in SQL
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo

# ---------------------------------------------------------------------------
# Module-level pyodbc mock — injected before DsnDatabase is importable.
# ---------------------------------------------------------------------------

_pyodbc_mock = types.ModuleType("pyodbc")
_pyodbc_mock.connect = MagicMock()
_pyodbc_mock.Binary = MagicMock(side_effect=lambda data: b"<binary:%d>" % len(data))
sys.modules.setdefault("pyodbc", _pyodbc_mock)

# Now we can import the class under test.
from execsql.db.dsn import DsnDatabase  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn(rowcount: int = 0) -> MagicMock:
    """Return a MagicMock mimicking a pyodbc connection + cursor."""
    curs = MagicMock()
    curs.rowcount = rowcount
    curs.close = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = curs
    conn.rollback = MagicMock()
    conn.close = MagicMock()
    return conn


def _make_dsn(dsn_name: str = "TESTDSN", user: str | None = "alice", *, password: str | None = None) -> DsnDatabase:
    """Build a DsnDatabase with open_db() stubbed out to avoid a real connection."""
    with patch.object(DsnDatabase, "open_db", return_value=None):
        db = DsnDatabase(dsn_name, user, need_passwd=False, encoding="utf-8", password=password)
    return db


# ---------------------------------------------------------------------------
# TestDsnDatabaseInit
# ---------------------------------------------------------------------------


class TestDsnDatabaseInit:
    """Constructor sets the expected attributes without opening a real connection."""

    def test_db_name(self):
        db = _make_dsn("MY_DSN")
        assert db.db_name == "MY_DSN"

    def test_user(self):
        db = _make_dsn(user="bob")
        assert db.user == "bob"

    def test_user_none(self):
        db = _make_dsn(user=None)
        assert db.user is None

    def test_encoding(self):
        db = _make_dsn()
        assert db.encoding == "utf-8"

    def test_encoding_none_defaults_stored_as_given(self):
        # When encoding=None is passed the value should be stored as-is
        # (DsnDatabase does not normalise the encoding in __init__).
        with patch.object(DsnDatabase, "open_db", return_value=None):
            db = DsnDatabase("DSN", "user", encoding=None)
        assert db.encoding is None

    def test_paramstr_is_question_mark(self):
        db = _make_dsn()
        assert db.paramstr == "?"

    def test_conn_is_none_before_open(self):
        db = _make_dsn()
        # open_db was stubbed — conn should still be None.
        assert db.conn is None

    def test_repr_contains_dsn_name(self):
        db = _make_dsn("MY_DSN", "alice")
        r = repr(db)
        assert "MY_DSN" in r

    def test_repr_contains_user(self):
        db = _make_dsn("DSN1", "carol")
        r = repr(db)
        assert "carol" in r

    def test_repr_format(self):
        db = _make_dsn("SALES", "eve")
        r = repr(db)
        assert r.startswith("DsnDatabase(")


# ---------------------------------------------------------------------------
# TestDsnDatabaseOpenDb
# ---------------------------------------------------------------------------


class TestDsnDatabaseOpenDb:
    """open_db() connection logic (with pyodbc mocked)."""

    def test_successful_connection_without_password(self):
        """No-password path calls pyodbc.connect with just the DSN string."""
        conn = _make_conn()
        mock_connect = MagicMock(return_value=conn)

        with (
            patch.dict("sys.modules", {"pyodbc": _pyodbc_mock}),
            patch.object(
                sys.modules["pyodbc"],
                "connect",
                mock_connect,
            ),
            patch("execsql.db.dsn.get_password", return_value=""),
            patch(
                "execsql.db.dsn.password_from_keyring",
                return_value=False,
            ),
        ):
            db = DsnDatabase("MYDSN", "alice", need_passwd=False, encoding="utf-8")

        assert db.conn is conn
        mock_connect.assert_called()
        _, first_call_kwargs = mock_connect.call_args_list[0]
        assert "autocommit" not in first_call_kwargs

    def test_successful_connection_with_password(self):
        """With-password path passes Uid/Pwd in the connection string."""
        conn = _make_conn()
        mock_connect = MagicMock(return_value=conn)

        with (
            patch.dict("sys.modules", {"pyodbc": _pyodbc_mock}),
            patch.object(
                sys.modules["pyodbc"],
                "connect",
                mock_connect,
            ),
            patch("execsql.db.dsn.get_password", return_value="s3cr3t"),
            patch(
                "execsql.db.dsn.password_from_keyring",
                return_value=False,
            ),
        ):
            db = DsnDatabase("MYDSN", "alice", need_passwd=True, encoding="utf-8", password="s3cr3t")

        assert db.conn is conn
        connect_str = mock_connect.call_args_list[0][0][0]
        assert "Uid=alice" in connect_str
        assert "Pwd=s3cr3t" in connect_str

    def test_autocommit_fallback_on_optional_feature_error(self):
        """When pyodbc raises 'Optional feature not implemented', retry with autocommit=True."""
        conn_autocommit = _make_conn()
        call_count = [0]

        def _side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Optional feature not implemented")
            return conn_autocommit

        mock_connect = MagicMock(side_effect=_side_effect)

        with (
            patch.dict("sys.modules", {"pyodbc": _pyodbc_mock}),
            patch.object(
                sys.modules["pyodbc"],
                "connect",
                mock_connect,
            ),
            patch("execsql.db.dsn.get_password", return_value=""),
            patch(
                "execsql.db.dsn.password_from_keyring",
                return_value=False,
            ),
        ):
            db = DsnDatabase("FALLBACK", "alice", need_passwd=False, encoding="utf-8")

        assert db.conn is conn_autocommit
        _, second_kwargs = mock_connect.call_args_list[1]
        assert second_kwargs.get("autocommit") is True

    def test_connection_failure_raises_errinfo(self):
        """A hard connection failure (non-autocommit-fallback) raises ErrInfo."""
        mock_connect = MagicMock(side_effect=Exception("Driver not found"))

        with (
            patch.dict("sys.modules", {"pyodbc": _pyodbc_mock}),
            patch.object(
                sys.modules["pyodbc"],
                "connect",
                mock_connect,
            ),
            patch("execsql.db.dsn.get_password", return_value=""),
            patch(
                "execsql.db.dsn.password_from_keyring",
                return_value=False,
            ),
            pytest.raises(ErrInfo),
        ):
            DsnDatabase("BADSN", "alice", need_passwd=False, encoding="utf-8")
        _pyodbc_mock.connect.side_effect = None


# ---------------------------------------------------------------------------
# TestDsnDatabaseExecCmd
# ---------------------------------------------------------------------------


class TestDsnDatabaseExecCmd:
    """exec_cmd() generates the right SQL and updates state."""

    def _make_connected(self, rowcount: int = 7) -> DsnDatabase:
        db = _make_dsn()
        db.conn = _make_conn(rowcount)
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()
        return db

    def test_exec_cmd_executes_execute_syntax(self):
        db = self._make_connected()
        db.exec_cmd("my_proc")
        curs = db.conn.cursor.return_value
        executed_sql = curs.execute.call_args[0][0]
        assert executed_sql == 'execute "my_proc";'

    def test_exec_cmd_updates_last_rowcount(self):
        db = self._make_connected(rowcount=42)
        db.exec_cmd("proc_name")
        _state.subvars.add_substitution.assert_called_with("$LAST_ROWCOUNT", 42)

    def test_exec_cmd_rollback_on_error(self):
        db = self._make_connected()
        curs = db.conn.cursor.return_value
        curs.execute.side_effect = Exception("DB error")
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()

        with pytest.raises(Exception, match="DB error"):
            db.exec_cmd("bad_proc")

        db.conn.rollback.assert_called_once()

    def test_exec_cmd_passes_string_not_bytes(self):
        """exec_cmd() passes a str (not bytes) to curs.execute()."""
        db = self._make_connected()
        db.encoding = "latin1"
        db.exec_cmd("stored_proc")
        curs = db.conn.cursor.return_value
        executed_arg = curs.execute.call_args[0][0]
        assert isinstance(executed_arg, str)
        assert executed_arg == 'execute "stored_proc";'


# ---------------------------------------------------------------------------
# TestDsnDatabaseImportEntireFile
# ---------------------------------------------------------------------------


class TestDsnDatabaseImportEntireFile:
    """import_entire_file() reads the file and issues the correct INSERT."""

    def _make_connected(self) -> DsnDatabase:
        db = _make_dsn()
        db.conn = _make_conn()
        _state.subvars = MagicMock()
        _state.exec_log = MagicMock()
        return db

    def test_reads_file_and_calls_execute_with_binary(self, tmp_path):
        db = self._make_connected()
        f = tmp_path / "blob.bin"
        f.write_bytes(b"\x00\x01\x02\x03")

        mock_binary = MagicMock(side_effect=lambda data: b"<binary>")
        with patch.object(sys.modules["pyodbc"], "Binary", mock_binary):
            db.import_entire_file(None, "my_table", "blob_col", str(f))

        mock_binary.assert_called_once_with(b"\x00\x01\x02\x03")
        curs = db.conn.cursor.return_value
        assert curs.execute.called

    def test_sql_contains_table_name(self, tmp_path):
        db = self._make_connected()
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello")

        db.import_entire_file(None, "my_table", "col", str(f))

        curs = db.conn.cursor.return_value
        sql_arg = curs.execute.call_args[0][0]
        assert "my_table" in sql_arg

    def test_sql_contains_column_name(self, tmp_path):
        db = self._make_connected()
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello")

        db.import_entire_file(None, "tbl", "payload_col", str(f))

        curs = db.conn.cursor.return_value
        sql_arg = curs.execute.call_args[0][0]
        assert "payload_col" in sql_arg

    def test_schema_qualified_table_name_in_sql(self, tmp_path):
        """When schema_name is provided the SQL should contain schema.table."""
        db = self._make_connected()
        f = tmp_path / "data.bin"
        f.write_bytes(b"x")

        db.import_entire_file("dbo", "documents", "content", str(f))

        curs = db.conn.cursor.return_value
        sql_arg = curs.execute.call_args[0][0]
        # Both schema and table must appear in the INSERT.
        assert "dbo" in sql_arg
        assert "documents" in sql_arg

    def test_uses_param_placeholder(self, tmp_path):
        db = self._make_connected()
        f = tmp_path / "data.bin"
        f.write_bytes(b"y")

        db.import_entire_file(None, "t", "c", str(f))

        curs = db.conn.cursor.return_value
        sql_arg = curs.execute.call_args[0][0]
        assert "?" in sql_arg

    def test_missing_file_raises(self, tmp_path):
        db = self._make_connected()
        with pytest.raises(FileNotFoundError):
            db.import_entire_file(None, "tbl", "col", str(tmp_path / "missing.bin"))
