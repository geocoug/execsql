"""Connection controls must reach factories, with explicit no-reprompt semantics."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from execsql import state
from execsql.utils import gui


@pytest.mark.parametrize(
    "kind,factory",
    [
        ("p", "db_Postgres"),
        ("m", "db_MySQL"),
        ("s", "db_SqlServer"),
        ("o", "db_Oracle"),
        ("f", "db_Firebird"),
        ("d", "db_Dsn"),
    ],
)
@pytest.mark.parametrize("password", ["  private;{}  ", ""])
def test_connection_fields_reach_factory_without_secondary_prompt(monkeypatch, kind, factory, password):
    factory_mock = Mock()
    monkeypatch.setattr("execsql.db.factory." + factory, factory_mock)
    pool = Mock()
    monkeypatch.setattr(state, "dbs", pool)
    gui._apply_connect_result(
        "chosen",
        {
            "db_type": kind,
            "server": "dbhost",
            "database": "catalog",
            "username": "alice",
            "port": "6543",
            "encoding": "LATIN1",
            "password": password,
        },
    )
    expected = {"user": "alice", "pw_needed": bool(password), "password": password or None, "encoding": "LATIN1"}
    if kind == "d":
        factory_mock.assert_called_once_with("catalog", **expected)
    else:
        factory_mock.assert_called_once_with("dbhost", "catalog", port=6543, **expected)
    pool.add.assert_called_once_with("chosen", factory_mock.return_value)


@pytest.mark.parametrize("port", ["0", "-1", "65536", "5.5", "abc"])
def test_bad_port_never_opens_connection(monkeypatch, port):
    factory = Mock()
    monkeypatch.setattr(state, "dbs", Mock())
    monkeypatch.setattr("execsql.db.factory.db_Postgres", factory)
    with pytest.raises((ValueError, gui.ConsoleUIError), match="[Pp]ort"):
        gui._apply_connect_result("chosen", {"db_type": "p", "port": port})
    factory.assert_not_called()


@pytest.fixture(params=["console", "textual", "tk"])
def connection_ui(request, monkeypatch):
    """Return actual backend interaction, retaining widget callbacks and layout."""

    def interact(values, *, invalid_first=False, cancel=False):
        if request.param == "console":
            from execsql.gui.console import ConsoleBackend

            kind = values["db_type"]
            if kind in ("l", "k", "a"):
                answers = [kind, values["database"]]
            else:
                answers = [kind]
                if kind != "d":
                    answers.append(values["server"])
                answers.extend([values["database"], values["username"], values["encoding"]])
                if kind != "d":
                    answers.extend((["bad"] if invalid_first else []) + [values["port"]])
            answers = iter(answers)
            monkeypatch.setattr("builtins.input", lambda *args: next(answers))
            monkeypatch.setattr("getpass.getpass", lambda *args: values["password"])
            return ConsoleBackend().show_connect({})
        if request.param == "textual":
            pytest.importorskip("textual")
            from textual.widgets import Input, Select
            from execsql.gui.tui import ConnectScreen, _SingleDialogApp
            from tests.gui.textual_helpers import finish_dialog

            async def run():
                app = _SingleDialogApp(ConnectScreen, {})
                async with app.run_test(size=(110, 42)) as pilot:
                    screen = app.screen
                    screen.query_one("#db_type_select", Select).value = values["db_type"]
                    await pilot.pause()
                    for name in ("server", "database", "username", "password", "port", "encoding"):
                        screen.query_one("#" + name + "_input", Input).value = values[name]
                    assert screen.query_one("#password_input", Input).password
                    file_based = values["db_type"] in ("l", "k", "a")
                    assert screen.query_one("#password_row").display is not file_based
                    assert screen.query_one("#server_row").display == (not file_based and values["db_type"] != "d")
                    assert screen.query_one("#port_row").display == (not file_based and values["db_type"] != "d")
                    if invalid_first:
                        screen.query_one("#port_input", Input).value = "bad"
                        assert await pilot.click("#btn_ok")
                        await pilot.pause()
                        assert app.screen is screen
                        screen.query_one("#port_input", Input).value = values["port"]
                        await pilot.pause(0.5)
                    if cancel:
                        await finish_dialog(pilot, pilot.press("escape"))
                    else:
                        await pilot.pause()
                        await finish_dialog(pilot, pilot.click("#btn_ok"))
                return app.return_value

            return asyncio.run(run())
        pytest.importorskip("tkinter")
        from execsql.gui import desktop
        from tests.gui.test_desktop_dialogs import _install_fake_tk, _mk_widget

        tk, ttk, _ = _install_fake_tk()
        monkeypatch.setattr(desktop, "tk", tk)
        monkeypatch.setattr(desktop, "ttk", ttk)
        root = _mk_widget()
        variables = []

        def variable(*args, **kwargs):
            var = _mk_widget()
            var.get.return_value = ""
            variables.append(var)
            return var

        tk.StringVar.side_effect = variable
        kinds = [k for k, _ in desktop._DB_TYPE_OPTIONS]
        combos = []

        def combo(*args, **kwargs):
            widget = _mk_widget()
            if not combos:
                widget.current.return_value = kinds.index(values["db_type"])
            combos.append(widget)
            return widget

        ttk.Combobox.side_effect = combo

        def click(win):
            for var, name in zip(variables, ("server", "database", "username", "password", "port", "encoding")):
                var.get.return_value = values[name]
            buttons = {
                c.kwargs["text"]: c.kwargs["command"] for c in ttk.Button.call_args_list if "command" in c.kwargs
            }
            assert any(c.kwargs.get("show") == "*" for c in ttk.Entry.call_args_list)
            if values["db_type"] in ("l", "k", "a"):
                browse = buttons["Browse…"]
                monkeypatch.setattr(desktop.filedialog, "askopenfilename", lambda **kw: values["database"])
                browse()
                variables[1].set.assert_called_once_with(values["database"])
            if invalid_first:
                variables[4].get.return_value = "bad"
                buttons["Connect"]()
                win.destroy.assert_not_called()
                variables[4].get.return_value = values["port"]
            buttons["Cancel" if cancel else "Connect"]()

        root.wait_window.side_effect = click
        return desktop.ConnectDialog(root, {}).result

    return request.param, interact


@pytest.mark.parametrize("kind", ["p", "s", "m", "o", "f", "d", "l", "k", "a"])
@pytest.mark.parametrize("password", ["  private;{}  ", ""])
def test_actual_connection_controls_reach_factory(connection_ui, monkeypatch, kind, password):
    name, interact = connection_ui
    factory_name = {
        "p": "Postgres",
        "s": "SqlServer",
        "m": "MySQL",
        "o": "Oracle",
        "f": "Firebird",
        "d": "Dsn",
        "l": "SQLite",
        "k": "DuckDB",
        "a": "Access",
    }[kind]
    factory = Mock()
    monkeypatch.setattr("execsql.db.factory.db_" + factory_name, factory)
    monkeypatch.setattr(state, "dbs", Mock())
    values = {
        "db_type": kind,
        "server": "dbhost",
        "database": "catalog",
        "username": "alice",
        "password": password,
        "port": "6543",
        "encoding": "LATIN1",
    }
    result = interact(values)
    gui._apply_connect_result("chosen", result)
    if kind in ("l", "k", "a"):
        factory.assert_called_once_with("catalog")
    else:
        kwargs = {"user": "alice", "pw_needed": bool(password), "password": password or None, "encoding": "LATIN1"}
        if kind == "d":
            factory.assert_called_once_with("catalog", **kwargs)
        else:
            factory.assert_called_once_with("dbhost", "catalog", port=6543, **kwargs)


def test_invalid_port_can_be_corrected_in_actual_controls(connection_ui):
    _, interact = connection_ui
    result = interact(
        {
            "db_type": "p",
            "server": "host",
            "database": "db",
            "username": "user",
            "password": "",
            "port": "6543",
            "encoding": "",
        },
        invalid_first=True,
    )
    assert result["port"] == 6543


@pytest.mark.parametrize("kind", ["p", "d", "l"])
def test_empty_optional_fields_keep_driver_defaults(connection_ui, kind):
    _, interact = connection_ui
    result = interact(
        {"db_type": kind, "server": "", "database": "db", "username": "", "password": "", "port": "", "encoding": ""},
    )
    assert result["port"] is None
    assert result["encoding"] is None
    assert result["password"] is None


def test_cancelled_connect_does_not_return_credentials(connection_ui):
    name, interact = connection_ui
    if name == "console":
        pytest.skip("Console connection selection has no cancel button")
    result = interact(
        {
            "db_type": "p",
            "server": "host",
            "database": "db",
            "username": "alice",
            "password": "private",
            "port": "",
            "encoding": "",
        },
        cancel=True,
    )
    assert not result.get("db_type")
    assert not result.get("password")


def test_native_tk_connection_modes_and_submission():
    """Exercise native geometry, file-mode switching, masking and submitted values."""
    import subprocess
    import sys

    pytest.importorskip("tkinter")
    script = """
import tkinter as tk
from tkinter import ttk
from execsql.gui.desktop import ConnectDialog, _DB_TYPE_OPTIONS
try:
    root = tk.Tk()
except tk.TclError as exc:
    print("TK_UNAVAILABLE:", exc)
    raise SystemExit(77)
root.withdraw()
errors = []
def failed(*exc):
    import traceback
    errors.append(''.join(traceback.format_exception(*exc)))
    root.destroy()
root.report_callback_exception = failed
def submit():
    win = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    def walk(parent):
        for child in parent.winfo_children():
            yield child
            yield from walk(child)
    controls = list(walk(win))
    combos = [w for w in controls if isinstance(w, ttk.Combobox)]
    entries = [w for w in controls if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
    browse = next(w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == 'Browse…')
    selector = combos[0]
    assert entries[3].cget('show') == '*'
    for kind in ('l', 'k', 'a'):
        selector.current([k for k,v in _DB_TYPE_OPTIONS].index(kind))
        selector.event_generate('<<ComboboxSelected>>')
        win.update_idletasks()
        assert not entries[0].winfo_manager()
        assert not entries[3].winfo_manager()
        assert browse.winfo_manager() == 'grid'
        assert entries[1].winfo_manager() == 'grid'
    selector.current(0)
    selector.event_generate('<<ComboboxSelected>>')
    win.update_idletasks()
    assert entries[0].winfo_manager() == 'grid'
    assert not browse.winfo_manager()
    for entry, value in zip(entries, ('dbhost', 'catalog', 'alice', '  private  ', '6543')):
        entry.insert(0, value)
    combos[1].set('LATIN1')
    next(w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == 'Connect').invoke()
wait_window = root.wait_window
def wait_for_dialog(win):
    def ready():
        if not win.winfo_viewable():
            root.after(10, ready)
            return
        # Submission destroys the window; use a timer rather than an Aqua idle callback.
        root.after(0, submit)
    root.after_idle(ready)
    root.after(20000, root.destroy)
    return wait_window(win)
root.wait_window = wait_for_dialog
try:
    dialog = ConnectDialog(root, {'message':'Select a connection'})
    assert not errors, errors
    assert dialog.result == dict(db_type='p', server='dbhost', database='catalog', db_file=None, username='alice', password='  private  ', port=6543, encoding='LATIN1'), dialog.result
finally:
    root.destroy()
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    if completed.returncode == 77 and "TK_UNAVAILABLE:" in completed.stdout:
        pytest.skip(completed.stdout.strip())
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "kind,module,driver_name",
    [
        ("p", "postgres", "psycopg"),
        ("s", "sqlserver", "pyodbc"),
        ("m", "mysql", "pymysql"),
        ("o", "oracle", "oracledb"),
        ("f", "firebird", "firebird.driver"),
        ("d", "dsn", "pyodbc"),
    ],
)
@pytest.mark.parametrize("password", ["", "  typed-password  "])
def test_real_adapter_auth_failure_never_opens_another_password_prompt(
    monkeypatch,
    kind,
    module,
    driver_name,
    password,
):
    """Use actual factories/adapters with a failing driver, not a factory double."""
    import importlib
    from execsql.exceptions import ErrInfo
    from execsql.utils import auth

    driver = pytest.importorskip(driver_name)
    adapter = importlib.import_module("execsql.db." + module)
    connect = Mock(side_effect=RuntimeError("authentication rejected"))
    monkeypatch.setattr(driver, "connect", connect)

    def forbidden(*args, **kwargs):
        pytest.fail("PROMPT CONNECT requested another password")

    monkeypatch.setattr(adapter, "get_password", forbidden)
    monkeypatch.setattr("getpass.getpass", forbidden)
    pool = Mock()
    monkeypatch.setattr(state, "dbs", pool)
    # An earlier keyring login must not affect this explicit connection attempt.
    monkeypatch.setattr(auth._login, "from_keyring", True)
    monkeypatch.setattr(auth._login, "pending_store", None)
    with pytest.raises(ErrInfo):
        gui._apply_connect_result(
            "chosen",
            {"db_type": kind, "server": "host", "database": "catalog", "username": "alice", "password": password},
        )
    assert connect.called
    assert not auth.password_from_keyring()
    pool.add.assert_not_called()


@pytest.mark.parametrize("size", [(80, 24), (100, 36)])
def test_textual_connection_fields_can_be_completed_by_keyboard(size):
    pytest.importorskip("textual")
    from textual.widgets import Input, Select
    from execsql.gui.tui import ConnectScreen, _SingleDialogApp

    async def run():
        app = _SingleDialogApp(ConnectScreen, {})
        async with app.run_test(size=size) as pilot:
            screen = app.screen
            screen.query_one("#db_type_select", Select).value = "l"
            await pilot.pause()
            screen.query_one("#db_type_select", Select).value = "p"
            await pilot.pause()
            assert screen.query_one("#password_row").display
            screen.query_one("#server_input", Input).focus()
            for text in ("host", "catalog", "alice", "typed-password", "6543", "LATIN1"):
                await pilot.press(*text)
                await pilot.press("tab")
            assert screen.focused.id == "btn_ok"
            await pilot.press("enter")
            await pilot.pause()
        return app.return_value

    result = asyncio.run(run())
    assert result["server"] == "host"
    assert result["database"] == "catalog"
    assert result["username"] == "alice"
    assert result["password"] == "typed-password"
    assert result["port"] == 6543
    assert result["encoding"] == "LATIN1"
