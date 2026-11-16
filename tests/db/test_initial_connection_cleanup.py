"""An adapter owns acquired driver handles until construction succeeds."""

import importlib
import sqlite3
from unittest.mock import MagicMock

import pytest

from execsql import inspect_schema


@pytest.mark.parametrize("corrupt", [False, True])
def test_owned_sqlite_handle_closes_on_setup_failure_or_success(tmp_path, monkeypatch, corrupt):
    target = tmp_path / "input.sqlite"
    if corrupt:
        target.write_bytes(b"not a sqlite database" * 100)
    else:
        sqlite3.connect(target).close()
    handles = []

    class Tracked(sqlite3.Connection):
        close_count = 0

        def close(self):
            self.close_count += 1
            super().close()

    original = sqlite3.connect

    def connect(*args, **kwargs):
        handle = original(*args, **kwargs, factory=Tracked)
        handles.append(handle)
        return handle

    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr("execsql.config.ConfigData._search_paths", classmethod(lambda *a, **kw: []))
    try:
        report = inspect_schema(dsn=f"sqlite:///{target}")
        assert report["success"] is (not corrupt), report
        assert len(handles) == 1
        assert handles[0].close_count == 1
    finally:
        for handle in handles:
            if handle.close_count == 0:
                handle.close()


@pytest.mark.usefixtures("fake_drivers")
@pytest.mark.parametrize(
    "module,name,args",
    [
        ("sqlite", "SQLiteDatabase", (":memory:",)),
        ("duckdb", "DuckDBDatabase", (":memory:",)),
        ("postgres", "PostgresDatabase", ("host", "db", None)),
        ("mysql", "MySQLDatabase", ("host", "db", None)),
        ("sqlserver", "SqlServerDatabase", ("host", "db", None)),
        ("oracle", "OracleDatabase", ("host", "db", None)),
        ("firebird", "FirebirdDatabase", ("host", "db", None)),
        ("access", "AccessDatabase", ("input.accdb",)),
        ("dsn", "DsnDatabase", ("example", None)),
    ],
)
@pytest.mark.parametrize("failure", [RuntimeError("setup failed"), KeyboardInterrupt(), SystemExit(17)])
def test_adapters_close_acquired_connection_if_initial_setup_raises(monkeypatch, module, name, args, failure):
    cls = getattr(importlib.import_module(f"execsql.db.{module}"), name)
    connection = MagicMock()
    captured = []

    def open_db(db):
        captured.append(db)
        db.conn = connection
        raise failure

    monkeypatch.setattr(cls, "open_db", open_db)
    if module == "access":
        monkeypatch.setattr(cls, "open_dao", lambda db: None)
    with pytest.raises(type(failure)) as raised:
        cls(*args)
    assert raised.value is failure
    connection.close.assert_called_once()
    assert captured[0].conn is None


@pytest.mark.parametrize("dialect", ["mysql", "sqlserver"])
@pytest.mark.parametrize("failure", [RuntimeError("setup SQL failed"), KeyboardInterrupt()])
def test_real_driver_session_setup_failure_closes_connection(monkeypatch, dialect, failure):
    driver = pytest.importorskip("pymysql" if dialect == "mysql" else "pyodbc")
    implementation = importlib.import_module(f"execsql.db.{dialect}")
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = failure
    monkeypatch.setattr(driver, "connect", MagicMock(return_value=conn))
    if dialect == "sqlserver":
        monkeypatch.setattr(driver, "drivers", lambda: ["ODBC Driver 18 for SQL Server"])
    cls = implementation.MySQLDatabase if dialect == "mysql" else implementation.SqlServerDatabase
    with pytest.raises(Exception if isinstance(failure, Exception) else type(failure)):
        cls("host", "db", None, need_passwd=False)
    conn.cursor.return_value.execute.assert_called()
    conn.close.assert_called_once()


def test_cleanup_error_preserves_original_setup_failure(monkeypatch):
    from execsql.db.sqlite import SQLiteDatabase

    conn = MagicMock()
    conn.close.side_effect = RuntimeError("close also failed")
    failure = KeyboardInterrupt()
    instances = []

    def open_db(db):
        instances.append(db)
        db.conn = conn
        raise failure

    monkeypatch.setattr(SQLiteDatabase, "open_db", open_db)
    with pytest.raises(KeyboardInterrupt) as raised:
        SQLiteDatabase(":memory:")
    assert raised.value is failure
    conn.close.assert_called_once()
    assert instances[0].conn is None
