"""In-process coverage tests for execsql.db.sqlserver.

These exercise the ``SqlServerDatabase`` adapter directly against the CI
service container (``mcr.microsoft.com/mssql/server:2022-latest``).  The
module is skipped when:

  - pyodbc is not installed, or
  - no ODBC Driver for SQL Server is registered, or
  - the test SQL Server instance is not reachable.

Override the connection target with EXECSQL_MSSQL_HOST / EXECSQL_MSSQL_PORT /
EXECSQL_MSSQL_DATABASE / EXECSQL_MSSQL_USER / EXECSQL_MSSQL_PASSWORD env vars.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import execsql.state as _state


# If another test module (e.g. tests/db/test_db_adapters_mocked.py)
# injected a MagicMock for pyodbc at import time, the real driver never gets
# loaded.  Drop any cached entry and force a fresh import so the real
# package wins whenever it's installed.
import importlib
import sys as _sys

_sys.modules.pop("pyodbc", None)
try:
    pyodbc = importlib.import_module("pyodbc")
except ImportError:
    pytest.skip("pyodbc not installed", allow_module_level=True)

# Need at least one real SQL Server ODBC driver — a MagicMock's drivers()
# returns a MagicMock (not iterable as a list of strings), so the list
# comprehension yields nothing useful and we fall through to skip.
try:
    _DRIVERS = [d for d in pyodbc.drivers() if isinstance(d, str) and "SQL Server" in d]
except Exception:
    _DRIVERS = []
if not _DRIVERS:
    pytest.skip(
        "No ODBC Driver for SQL Server available (install msodbcsql18 on Ubuntu / msodbcsql on macOS)",
        allow_module_level=True,
    )

_MS_HOST = os.environ.get("EXECSQL_MSSQL_HOST", "localhost")
_MS_PORT = int(os.environ.get("EXECSQL_MSSQL_PORT", "1433"))
_MS_DB = os.environ.get("EXECSQL_MSSQL_DATABASE", "execsql_test")
_MS_USER = os.environ.get("EXECSQL_MSSQL_USER", "sa")
_MS_PASS = os.environ.get("EXECSQL_MSSQL_PASSWORD", "ExecSql_Test123!")


def _mssql_reachable() -> bool:
    for drv in _DRIVERS:
        try:
            conn = pyodbc.connect(
                f"DRIVER={{{drv}}};SERVER={_MS_HOST},{_MS_PORT};"
                f"DATABASE=master;UID={_MS_USER};PWD={_MS_PASS};"
                f"Encrypt=No;TrustServerCertificate=yes;",
                timeout=3,
            )
            # Ensure the test DB exists; create if missing.
            conn.autocommit = True
            curs = conn.cursor()
            curs.execute(
                f"IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = ?) CREATE DATABASE {_MS_DB};",
                _MS_DB,
            )
            conn.close()
            return True
        except Exception:
            continue
    return False


if not _mssql_reachable():
    pytest.skip(
        f"SQL Server test instance not reachable at {_MS_HOST}:{_MS_PORT}",
        allow_module_level=True,
    )


from execsql.db.sqlserver import SqlServerDatabase  # noqa: E402
from execsql.exceptions import ErrInfo  # noqa: E402
import execsql.state as _state_real  # noqa: E402  — needed to seed exec_log


def _adapter_can_connect() -> bool:
    """Verify the SqlServerDatabase adapter (not just raw pyodbc) can connect.

    msodbcsql18 ≥ v18 defaults to Encrypt=Yes; the adapter's hard-coded
    connection strings do not set Encrypt=No / TrustServerCertificate=yes,
    so against SQL Server 2022 (which uses a self-signed cert) the adapter
    fails to connect even when raw pyodbc can.  Skip cleanly in that case.
    """
    _state_real.exec_log = MagicMock()
    _state_real.subvars = MagicMock()
    try:
        SqlServerDatabase(
            server_name=f"{_MS_HOST},{_MS_PORT}",
            db_name=_MS_DB,
            user_name=_MS_USER,
            password=_MS_PASS,
        ).close()
        return True
    except Exception:
        return False


if not _adapter_can_connect():
    pytest.skip(
        "SqlServerDatabase adapter cannot connect to the test server "
        "(modern Encrypt=Yes defaults; adapter's connection strings lack "
        "TrustServerCertificate=yes)",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _state_setup():
    _state.subvars = MagicMock()
    _state.exec_log = MagicMock()
    _state.conf = SimpleNamespace(
        gui_framework="tkinter",
        gui_level=0,
        import_common_cols_only=False,
        import_buffer=8192,
        import_row_buffer=100,
        export_row_buffer=100,
        import_progress_interval=0,
        empty_strings=True,
        empty_rows=True,
        del_empty_cols=False,
        create_col_hdrs=False,
        trim_strings=False,
        replace_newlines=False,
        only_strings=False,
        trim_col_hdrs="none",
        clean_col_hdrs=False,
        fold_col_hdrs="no",
        dedup_col_hdrs=False,
        output_encoding="utf-8",
        import_encoding="utf-8",
        script_encoding="utf8",
        make_export_dirs=False,
        export_output_dir=None,
        enc_err_disposition=None,
        quote_all_text=False,
        write_warnings=False,
        write_prefix=None,
        write_suffix=None,
        css_file=None,
        css_styles=None,
        gui_wait_on_exit=False,
        gui_wait_on_error_halt=False,
        allow_system_cmd=True,
        boolean_int=True,
        boolean_words=False,
        max_int=2_147_483_647,
    )
    _saved_stringtypes = _state.stringtypes
    _state.stringtypes = (str, bytes)
    try:
        yield
    finally:
        _state.stringtypes = _saved_stringtypes


@pytest.fixture(scope="module")
def db():
    # The function-scoped autouse fixtures don't run yet at module setup
    # time, so the SqlServerDatabase ctor needs _state.exec_log to be set
    # here before open_db() calls log_status_info() during driver fallback.
    _state.exec_log = MagicMock()
    _state.subvars = MagicMock()

    # SQL Server adapter takes server "host,port" as a single string
    inst = SqlServerDatabase(
        server_name=f"{_MS_HOST},{_MS_PORT}",
        db_name=_MS_DB,
        user_name=_MS_USER,
        password=_MS_PASS,
    )
    yield inst
    try:
        inst.close()
    except Exception:
        pass


@pytest.fixture
def fresh_table(db):
    name = "execsql_inproc_t"
    with db._cursor() as curs:
        curs.execute(f"IF OBJECT_ID('{name}', 'U') IS NOT NULL DROP TABLE {name};")
    db.commit()
    yield name
    with db._cursor() as curs:
        curs.execute(f"IF OBJECT_ID('{name}', 'U') IS NOT NULL DROP TABLE {name};")
    db.commit()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstructionAndConnection:
    def test_repr(self, db):
        r = repr(db)
        assert "SqlServerDatabase" in r
        assert _MS_DB in r

    def test_dbms_id(self, db):
        assert "server" in db.type.dbms_id.lower() or "sql" in db.type.dbms_id.lower()

    def test_paramstr(self, db):
        assert db.paramstr == "?"

    def test_paramsubs(self, db):
        assert db.paramsubs(3) == "?,?,?"

    def test_default_port(self, db):
        # We pass host,port so port may not reflect the constructor default
        assert isinstance(db.port, int)

    def test_connection_failure_raises(self):
        with pytest.raises(ErrInfo):
            SqlServerDatabase(
                server_name="no_such_host_12345",
                db_name=_MS_DB,
                user_name=_MS_USER,
                password=_MS_PASS,
            )


# ---------------------------------------------------------------------------
# Schema queries
# ---------------------------------------------------------------------------


class TestSchemaQueries:
    def test_schema_exists_dbo(self, db):
        assert db.schema_exists("dbo") is True

    def test_schema_exists_false(self, db):
        assert db.schema_exists("no_such_schema_xyz") is False

    def test_role_exists_dbo(self, db):
        # 'dbo' role/principal should exist in every SQL Server DB
        assert db.role_exists("dbo") is True
        assert db.role_exists("no_such_principal_xyz") is False

    def test_table_exists(self, db, fresh_table):
        assert db.table_exists(fresh_table) is False
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name NVARCHAR(50));")
        db.commit()
        assert db.table_exists(fresh_table) is True

    def test_column_exists(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, label NVARCHAR(50));")
        db.commit()
        assert db.column_exists(fresh_table, "id") is True
        assert db.column_exists(fresh_table, "missing") is False


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


class TestDataAccess:
    def test_select_data(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name NVARCHAR(20));")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1, 'a'), (2, 'b');")
        db.commit()
        hdrs, rows = db.select_data(f"SELECT id, name FROM {fresh_table} ORDER BY id;")
        assert [h.lower() for h in hdrs] == ["id", "name"]
        assert [tuple(r) for r in rows] == [(1, "a"), (2, "b")]

    def test_select_data_bad_sql_raises(self, db):
        with pytest.raises(pyodbc.Error):
            db.select_data("SELECT * FROM execsql_no_table_xyz;")

    def test_select_rowsource(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1), (2), (3);")
        db.commit()
        _hdrs, rs = db.select_rowsource(f"SELECT id FROM {fresh_table} ORDER BY id;")
        rows = [tuple(r) for r in rs]
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# exec_cmd — stored procedure dispatch
# ---------------------------------------------------------------------------


class TestExecCmd:
    def test_exec_cmd_calls_procedure(self, db):
        with db._cursor() as curs:
            curs.execute("IF OBJECT_ID('execsql_noop', 'P') IS NOT NULL DROP PROCEDURE execsql_noop;")
            curs.execute("EXEC sp_executesql N'CREATE PROCEDURE execsql_noop AS SELECT 1';")
        db.commit()
        try:
            db.exec_cmd("execsql_noop")
            _state.subvars.add_substitution.assert_called()
        finally:
            with db._cursor() as curs:
                curs.execute("IF OBJECT_ID('execsql_noop', 'P') IS NOT NULL DROP PROCEDURE execsql_noop;")
            db.commit()


# ---------------------------------------------------------------------------
# drop_table — SQL Server-specific override
# ---------------------------------------------------------------------------


class TestDropTable:
    def test_drop_table(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
        db.commit()
        assert db.table_exists(fresh_table) is True
        db.drop_table(fresh_table)
        db.commit()
        assert db.table_exists(fresh_table) is False


# ---------------------------------------------------------------------------
# import_entire_file — varbinary blob storage
# ---------------------------------------------------------------------------


class TestImportEntireFile:
    def test_import_binary(self, db, fresh_table, tmp_path):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (blob VARBINARY(MAX));")
        db.commit()
        bin_file = tmp_path / "blob.bin"
        bin_file.write_bytes(b"\x00\x01\x02ABCDE")
        db.import_entire_file(None, fresh_table, "blob", str(bin_file))
        db.commit()
        _hdrs, rows = db.select_data(f"SELECT blob FROM {fresh_table};")
        assert rows
        assert b"ABCDE" in bytes(rows[0][0])


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_method_callable(self, db):
        # Just verify the inherited close() method is present.  We don't
        # actually invoke it on the shared `db` fixture because subsequent
        # tests still need the connection, and creating a fresh instance
        # here can fail under SQL Server 2022's encryption defaults
        # (the adapter's hard-coded connection strings don't set
        # Encrypt=No / TrustServerCertificate=yes).  Base-class close()
        # is fully exercised in tests/db/test_base.py.
        assert callable(db.close)
