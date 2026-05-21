"""Real-Access tests for Windows CI runners.

These tests run only on Windows with the Microsoft Access Database Engine
(2016 Redistributable or later) installed.  They create a fresh ``.accdb``
file via DAO and exercise the ``AccessDatabase`` adapter against it.

The module skips outside Windows and when win32com / ODBC drivers are not
available, so it is harmless on Ubuntu / macOS runners.

CI setup (handled in `.github/workflows/ci-cd.yml`):
  - Install Access Database Engine via `choco install accessdatabaseengine-x64`
  - Install pywin32 + pyodbc via the project's mssql + dev extras
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import execsql.state as _state


# ---------------------------------------------------------------------------
# Hard skips outside Windows + with missing drivers
# ---------------------------------------------------------------------------


if sys.platform != "win32":
    pytest.skip("Access real-driver tests run on Windows only", allow_module_level=True)


try:
    import win32com.client  # noqa: F401
except ImportError:
    pytest.skip(
        "win32com (pywin32) not installed — Access tests require pywin32",
        allow_module_level=True,
    )


try:
    import pyodbc

    _ACCESS_DRIVERS = [d for d in pyodbc.drivers() if "Access" in d]
except Exception:
    _ACCESS_DRIVERS = []

if not _ACCESS_DRIVERS:
    pytest.skip(
        "Microsoft Access Database Engine not installed (install the 2016 x64 Redistributable on Windows)",
        allow_module_level=True,
    )


from execsql.db.access import AccessDatabase  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
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


@pytest.fixture(scope="module")
def accdb_path(tmp_path_factory):
    """Create a fresh .accdb via DAO and return its path."""
    tmp = tmp_path_factory.mktemp("access")
    fn = str(tmp / f"test_{uuid.uuid4().hex[:8]}.accdb")

    daoEngine = win32com.client.Dispatch("DAO.DBEngine.120")
    # dbLangGeneral = ";LANGID=0x0409;CP=1252;COUNTRY=0"; dbVersion150 = 128 (Access 2010+)
    daoEngine.CreateDatabase(fn, ";LANGID=0x0409;CP=1252;COUNTRY=0", 128)
    return fn


@pytest.fixture(scope="module")
def db(accdb_path):
    inst = AccessDatabase(accdb_path)
    yield inst
    try:
        inst.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_repr(self, db, accdb_path):
        r = repr(db)
        assert "AccessDatabase" in r
        assert Path(accdb_path).name in r or accdb_path in r

    def test_jet4_flag_for_accdb(self, db):
        # .accdb files use Jet 4+ (the ACE engine)
        assert db.jet4 is True

    def test_paramstr_is_question_mark(self, db):
        assert db.paramstr == "?"

    def test_dao_conn_open(self, db):
        assert db.dao_conn is not None

    def test_odbc_conn_open(self, db):
        assert db.conn is not None


# ---------------------------------------------------------------------------
# Schema queries against real Jet
# ---------------------------------------------------------------------------


@pytest.fixture
def with_table(db):
    """Create a fresh test table and drop it after."""
    name = "execsql_test_t"
    try:
        db.execute(f"CREATE TABLE {name} (id INTEGER, name TEXT(50));")
    except Exception:
        # Table may exist from prior run — drop and recreate
        try:
            db.execute(f"DROP TABLE {name};")
        except Exception:
            pass
        db.execute(f"CREATE TABLE {name} (id INTEGER, name TEXT(50));")
    yield name
    try:
        db.execute(f"DROP TABLE {name};")
    except Exception:
        pass


class TestSchemaQueries:
    def test_table_exists(self, db, with_table):
        assert db.table_exists(with_table) is True
        assert db.table_exists("execsql_no_such_table") is False

    def test_column_exists(self, db, with_table):
        assert db.column_exists(with_table, "id") is True
        assert db.column_exists(with_table, "name") is True
        assert db.column_exists(with_table, "missing_col") is False

    def test_table_columns(self, db, with_table):
        cols = [c.lower() for c in db.table_columns(with_table)]
        assert "id" in cols
        assert "name" in cols


# ---------------------------------------------------------------------------
# Data CRUD via execute + select_data
# ---------------------------------------------------------------------------


class TestDataCrud:
    def test_insert_and_select(self, db, with_table):
        db.execute(f"INSERT INTO {with_table} (id, name) VALUES (1, 'Alice');")
        db.execute(f"INSERT INTO {with_table} (id, name) VALUES (2, 'Bob');")
        hdrs, rows = db.select_data(f"SELECT id, name FROM {with_table} ORDER BY id;")
        assert [h.lower() for h in hdrs] == ["id", "name"]
        assert len(rows) == 2
        assert rows[0][0] == 1
        assert rows[1][1] == "Bob"

    def test_select_rowsource(self, db, with_table):
        db.execute(f"INSERT INTO {with_table} (id, name) VALUES (1, 'A');")
        db.execute(f"INSERT INTO {with_table} (id, name) VALUES (2, 'B');")
        _hdrs, rs = db.select_rowsource(f"SELECT id FROM {with_table} ORDER BY id;")
        rows = list(rs)
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_releases_connections(self, accdb_path):
        inst = AccessDatabase(accdb_path)
        assert inst.dao_conn is not None
        assert inst.conn is not None
        inst.close()
        assert inst.dao_conn is None
        assert inst.conn is None
