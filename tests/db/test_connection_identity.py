"""Optional passwords must not change the requested connection identity."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from execsql import state
from execsql.db import factory
from execsql.utils import gui

ADAPTERS = [
    ("p", "Postgres", "postgres", "psycopg"),
    ("m", "MySQL", "mysql", "pymysql"),
    ("o", "Oracle", "oracle", "oracledb"),
    ("f", "Firebird", "firebird", "firebird.driver"),
    ("d", "Dsn", "dsn", "pyodbc"),
]


@pytest.fixture
def adapter(request, monkeypatch):
    kind, name, module, driver_name = request.param
    driver = pytest.importorskip(driver_name)
    implementation = importlib.import_module("execsql.db." + module)
    conn = MagicMock()
    conn.info.encoding = "UTF8"
    connect = MagicMock(return_value=conn)
    monkeypatch.setattr(driver, "connect", connect)

    def forbidden(*args, **kwargs):
        pytest.fail("Explicit no-prompt connection requested a password")

    monkeypatch.setattr(implementation, "get_password", forbidden)
    monkeypatch.setattr("getpass.getpass", forbidden)
    return SimpleNamespace(kind=kind, open=getattr(factory, "db_" + name), connect=connect, conn=conn)


def assert_credentials(adapter, username, password):
    adapter.connect.assert_called_once()
    if adapter.kind in ("d", "s"):
        connection_string = adapter.connect.call_args.args[0].lower()

        def attribute(key, value):
            if value is None:
                assert key + "=" not in connection_string
                return
            quoted = "{" + value.replace("}", "}}") + "}"
            expected = [key + "=" + quoted.lower() + ";"]
            if adapter.kind == "s":
                expected.append(key + "=" + value.lower() + ";")
            assert any(item in connection_string for item in expected), connection_string

        attribute("uid", username)
        attribute("pwd", password)
    else:
        kwargs = adapter.connect.call_args.kwargs
        if username:
            assert kwargs["user"] == username
        else:
            assert "user" not in kwargs
        if password is not None:
            assert kwargs["password"] == password
        else:
            assert "password" not in kwargs


@pytest.mark.parametrize("adapter", ADAPTERS, indirect=True)
@pytest.mark.parametrize("username", ["alice", None])
@pytest.mark.parametrize("password", [None, "", "  typed-value  "])
def test_adapter_credentials_are_independent_of_password_prompt_flag(adapter, username, password):
    args = ("catalog",) if adapter.kind == "d" else ("dbhost", "catalog")
    db = adapter.open(*args, user=username, pw_needed=False, password=password)
    assert_credentials(adapter, username, password)
    db.close()


@pytest.mark.parametrize("adapter", ADAPTERS + [("s", "SqlServer", "sqlserver", "pyodbc")], indirect=True)
@pytest.mark.parametrize("password", ["", "  typed-value  "])
def test_connection_dialog_keeps_username_through_real_adapter(monkeypatch, adapter, password):
    pool = MagicMock()
    monkeypatch.setattr(state, "dbs", pool)
    state.conf.gui_level = 2

    class ResponseQueue:
        def put(self, spec):
            spec.return_queue.put(
                {
                    "db_type": adapter.kind,
                    "server": "dbhost",
                    "database": "catalog",
                    "username": "alice",
                    "password": password,
                },
            )

    monkeypatch.setattr(gui, "enable_gui", lambda: setattr(state, "gui_manager_queue", ResponseQueue()))
    gui.gui_connect("chosen", "Choose connection")
    assert_credentials(adapter, "alice", password or None)
    pool.add.assert_called_once()
    assert pool.add.call_args.args[0] == "chosen"
    assert pool.add.call_args.args[1].user == "alice"
    pool.add.call_args.args[1].close()


@pytest.mark.parametrize("adapter", [ADAPTERS[-1]], indirect=True)
def test_username_without_password_remains_odbc_quoted(adapter):
    username = "ali}ce;ROLE=admin"
    db = adapter.open("catalog", user=username, pw_needed=False, password=None)
    assert_credentials(adapter, username, None)
    db.close()
