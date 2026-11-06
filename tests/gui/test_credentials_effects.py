"""Credential prompts must reach the selected backend and assign script variables."""

from __future__ import annotations

import asyncio
import builtins
import subprocess
import sys
from types import SimpleNamespace

import pytest

from execsql import api, run
from execsql import state
from execsql.db.sqlite import SQLiteDatabase
from execsql.utils import gui

COMMAND = '-- !x! PROMPT MESSAGE "Log in" CREDENTIALS login secret\n'


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "credentials.db"))
    db.conn.executescript("create table events (value text);")
    yield db
    db.close()


@pytest.fixture(params=["tk", "textual", "manager"])
def credentials(request, monkeypatch):
    choice = SimpleNamespace(kind="ok", username="alice", password="test-password", calls=0)
    original_config = api._LibraryConfig
    framework = "tkinter" if request.param == "tk" else "textual"
    monkeypatch.setattr(api, "_LibraryConfig", lambda **kw: original_config(gui_level=1, gui_framework=framework, **kw))
    monkeypatch.setattr(gui, "_active_backend", None)

    def terminal_forbidden(*args, **kwargs):
        pytest.fail("GUI credentials unexpectedly requested terminal input")

    monkeypatch.setattr("builtins.input", terminal_forbidden)
    monkeypatch.setattr("getpass.getpass", terminal_forbidden)
    if request.param == "tk":
        pytest.importorskip("tkinter")
        from execsql.gui import desktop
        from tests.gui.test_desktop_dialogs import _install_fake_tk, _mk_widget

        tk, ttk, _ = _install_fake_tk()
        monkeypatch.setattr(desktop, "tk", tk)
        monkeypatch.setattr(desktop, "ttk", ttk)
        monkeypatch.setenv("DISPLAY", ":test")  # Exercise the existing Tk selection path on headless runners.
        root = _mk_widget()
        geometry_managers = {}

        def widget(parent, *args, **kwargs):
            w = _mk_widget()

            def layout(manager):
                assert geometry_managers.setdefault(id(parent), manager) == manager, "mixed pack/grid in one parent"

            w.pack.side_effect = lambda **kw: layout("pack")
            w.grid.side_effect = lambda **kw: layout("grid")
            return w

        for cls in ("Frame", "Label", "Entry", "Button"):
            getattr(ttk, cls).side_effect = widget
        variables = []

        def variable(*args, **kwargs):
            var = _mk_widget()
            var.get.side_effect = lambda: (
                choice.username if len(variables) and var is variables[-2] else choice.password
            )
            variables.append(var)
            return var

        tk.StringVar.side_effect = variable
        monkeypatch.setattr(desktop.TkinterBackend, "start", lambda backend: setattr(backend, "_root", root))

        def interact(win):
            choice.calls += 1
            if choice.kind == "error":
                raise ValueError("credential dialog failed")
            entries = ttk.Entry.call_args_list[-2:]
            assert entries[1].kwargs["show"] == "*"
            if choice.kind in ("cancel", "escape", "close"):
                if choice.kind == "escape":
                    next(c.args[1] for c in win.bind.call_args_list if c.args[0] == "<Escape>")(None)
                elif choice.kind == "close":
                    next(c.args[1] for c in win.protocol.call_args_list if c.args[0] == "WM_DELETE_WINDOW")()
                else:
                    next(c.kwargs["command"] for c in ttk.Button.call_args_list if c.kwargs.get("text") == "Cancel")()
            else:
                next(c.kwargs["command"] for c in ttk.Button.call_args_list if c.kwargs.get("text") == "OK")()

        root.wait_window.side_effect = interact
    elif request.param == "textual":
        pytest.importorskip("textual")
        from textual.widgets import Input

        from execsql.gui.tui import CredentialsScreen, _SingleDialogApp

        def headless(app):
            choice.calls += 1
            if choice.kind == "error":
                raise ValueError("credential dialog failed")

            async def interact():
                async with app.run_test() as pilot:
                    screen = app.screen
                    assert isinstance(screen, CredentialsScreen)
                    screen.query_one("#username_input", Input).value = choice.username
                    password = screen.query_one("#password_input", Input)
                    assert password.password
                    password.value = choice.password
                    if choice.kind in ("escape", "close"):
                        await pilot.press("escape")
                    else:
                        assert await pilot.click("#btn_cancel" if choice.kind == "cancel" else "#btn_ok")
                    await pilot.pause()
                return app.return_value

            return asyncio.run(interact())

        monkeypatch.setattr(_SingleDialogApp, "run", headless)
    else:
        from execsql.gui.console import ConsoleBackend

        original_import = builtins.__import__

        def without_textual(name, *args, **kwargs):
            if name == "execsql.gui.tui":
                raise ImportError("test console fallback")
            return original_import(name, *args, **kwargs)

        def show_credentials(backend, args):
            choice.calls += 1
            assert args["message"] == "Log in"
            if choice.kind == "error":
                raise ValueError("credential dialog failed")
            if choice.kind in ("cancel", "escape", "close"):
                return {"button": None, "cancelled": True}
            return {"username": choice.username, "password": choice.password}

        monkeypatch.setattr(builtins, "__import__", without_textual)
        monkeypatch.setattr(ConsoleBackend, "show_credentials", show_credentials)

    real_enable = gui.enable_gui
    managers = []

    def enable():
        real_enable()
        if state.gui_manager_thread is not None:
            managers.append((state.gui_manager_queue, state.gui_manager_thread))

    monkeypatch.setattr(gui, "enable_gui", enable)
    yield choice
    for queue, thread in managers:
        queue.put(None)
        thread.join(2)
        assert not thread.is_alive()


def test_fresh_gui_prompt_assigns_credentials_without_terminal_input(database, credentials):
    result = run(sql=COMMAND + "-- !x! ASSERT NOT DIALOG_CANCELED()\n", connection=database)
    assert result.success, result.errors
    assert credentials.calls == 1
    assert result.variables["login"] == "alice"
    assert result.variables["secret"] == "test-password"


@pytest.mark.parametrize("kind", ["cancel", "escape", "close"])
def test_cancel_halt_off_preserves_old_credentials(database, credentials, kind):
    credentials.kind = kind
    result = run(
        sql="-- !x! SUB login previous\n-- !x! SUB secret previous\n-- !x! CANCEL_HALT OFF\n"
        + COMMAND
        + "-- !x! ASSERT DIALOG_CANCELED()\ninsert into events values ('continued');\n",
        connection=database,
    )
    assert result.success, result.errors
    assert credentials.calls == 1
    assert result.variables["login"] == result.variables["secret"] == "previous"
    assert database.conn.execute("select * from events").fetchall() == [("continued",)]


def test_cancel_halt_rolls_back_and_runs_cleanup(database, credentials):
    credentials.kind = "cancel"
    result = run(
        sql="-- !x! SUB login previous\n-- !x! SUB secret previous\n"
        "-- !x! BEGIN SCRIPT cleanup\ninsert into events values ('cleanup');\n-- !x! END SCRIPT\n"
        "-- !x! ON CANCEL_HALT EXECUTE SCRIPT cleanup\n-- !x! BEGIN BATCH\n"
        "insert into events values ('pending');\n"
        + COMMAND
        + "insert into events values ('unreachable');\n-- !x! END BATCH\n",
        connection=database,
    )
    assert not result.success
    assert any("exit status 2" in e.message for e in result.errors)
    assert "login" not in result.variables and "secret" not in result.variables
    assert database.conn.execute("select * from events").fetchall() == [("cleanup",)]


def test_gui_failure_does_not_commit_pending_work(database, credentials):
    credentials.kind = "error"
    result = run(
        sql="-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! ERROR_HALT OFF\n-- !x! BEGIN BATCH\n"
        "insert into events values ('pending');\n" + COMMAND + "-- !x! END BATCH\n",
        connection=database,
    )
    assert not result.success
    assert any("credential dialog failed" in e.message for e in result.errors)
    assert database.conn.execute("select * from events").fetchall() == []


def test_accepted_empty_credentials_are_not_cancellation(database, credentials):
    credentials.username = credentials.password = ""
    result = run(sql=COMMAND + "-- !x! ASSERT NOT DIALOG_CANCELED()\n", connection=database)
    assert result.success, result.errors
    assert result.variables["login"] == result.variables["secret"] == ""


def test_gui_level_zero_uses_terminal_input(database, monkeypatch):
    monkeypatch.setattr(gui, "enable_gui", lambda: pytest.fail("GUI initialized at level zero"))
    monkeypatch.setattr("builtins.input", lambda *args: "terminal-user")
    monkeypatch.setattr("getpass.getpass", lambda *args: "terminal-password")
    result = run(sql=COMMAND, connection=database)
    assert result.success, result.errors
    assert result.variables["login"] == "terminal-user"
    assert result.variables["secret"] == "terminal-password"


def test_native_tk_credentials_message_and_submission():
    pytest.importorskip("tkinter")
    script = """
import tkinter as tk
from tkinter import ttk
from execsql.gui.desktop import CredentialsDialog
try:
    root = tk.Tk()
except tk.TclError as exc:
    print("TK_UNAVAILABLE:", exc)
    raise SystemExit(77)
root.withdraw()
def submit():
    win = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    def walk(parent):
        for child in parent.winfo_children():
            yield child
            yield from walk(child)
    controls = list(walk(win))
    entries = [w for w in controls if isinstance(w, ttk.Entry)]
    assert entries[1].cget("show") == "*"
    entries[0].insert(0, "native-user")
    entries[1].insert(0, "native-password")
    next(w for w in controls if isinstance(w, ttk.Button) and w.cget("text") == "OK").invoke()
root.after(150, submit)
root.after(3000, root.destroy)
try:
    dialog = CredentialsDialog(root, {"message": "Log in"})
    assert dialog.result["username"] == "native-user"
    assert dialog.result["password"] == "native-password"
finally:
    root.destroy()
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=10)
    if completed.returncode == 77 and "TK_UNAVAILABLE:" in completed.stdout:
        pytest.skip(completed.stdout.strip())
    assert completed.returncode == 0, completed.stdout + completed.stderr
