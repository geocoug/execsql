"""A real row-picker request must produce the documented data substitutions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from execsql import run, state
from execsql.metacommands import data


@pytest.fixture(params=["sqlite", "duckdb"])
def database(request, tmp_path):
    if request.param == "sqlite":
        from execsql.db.sqlite import SQLiteDatabase

        db = SQLiteDatabase(str(tmp_path / "selection.db"))
        db.conn.executescript(
            "create table source (id integer, name text, note text);"
            "insert into source values (1, 'first', 'value'), (1152921504606846976, 'O''Brien', NULL);"
            "create table previous as select 0 as id, 'old' as name, 'old' as note, 'keep' as untouched;",
        )
        expected_id = "1152921504606846976"
    else:
        pytest.importorskip("duckdb")
        from execsql.db.duckdb import DuckDBDatabase

        db = DuckDBDatabase(str(tmp_path / "selection.duckdb"))
        db.conn.execute(
            "create table source (id decimal(38,18), name varchar, note varchar);"
            "insert into source values (1, 'first', 'value'), (12345678901234567890.123456789012345678, 'O''Brien', NULL);"
            "create table previous as select 0 as id, 'old' as name, 'old' as note, 'keep' as untouched;",
        )
        expected_id = "12345678901234567890.123456789012345678"
    yield SimpleNamespace(db=db, expected_id=expected_id)
    db.close()


CASES = [
    ("console", "select"),
    ("console", "invalid"),
    ("console", "continue"),
    ("console", "cancel"),
    ("console", "eof"),
    ("textual", "select"),
    ("textual", "enter"),
    ("textual", "double"),
    ("textual", "continue"),
    ("textual", "continue_enter"),
    ("textual", "cancel"),
    ("textual", "escape"),
    ("tk", "select"),
    ("tk", "double"),
    ("tk", "enter"),
    ("tk", "continue"),
    ("tk", "continue_enter"),
    ("tk", "cancel"),
    ("tk", "escape"),
    ("tk", "window"),
    ("tk", "no_selection"),
]


def _install_selector(monkeypatch, backend, gesture):
    if backend == "console":
        from execsql.gui.console import ConsoleBackend

        native = ConsoleBackend()
        answers = iter(
            {"invalid": ["invalid", "c", "2"], "continue": ["c"], "cancel": [""], "eof": [EOFError()]}.get(
                gesture,
                ["2"],
            ),
        )

        def answer(*args):
            value = next(answers)
            if isinstance(value, EOFError):
                raise value
            return value

        monkeypatch.setattr("builtins.input", answer)

        class Manager:
            def put(self, spec):
                spec.return_queue.put(native.dispatch(spec))

        manager = Manager()
    elif backend == "textual":
        pytest.importorskip("textual")
        from textual.widgets import DataTable

        from execsql.gui.tui import _SingleDialogApp, _TextualSyncQueue

        def headless(app):
            async def interact():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    table = app.screen.query_one("#sel_table", DataTable)
                    assert table.row_count == 2
                    table.move_cursor(row=1)
                    await pilot.pause()
                    if gesture in ("enter", "continue_enter"):
                        table.focus()
                        await pilot.press("enter")
                    elif gesture == "double":
                        from textual import events

                        table.move_cursor(row=0)
                        table.focus()
                        await pilot.pause()
                        # Textual 1.0 Pilot leaks Click's chain argument into
                        # MouseDown when times > 1. Exercise its Click path directly.
                        assert await pilot._post_mouse_events(
                            [events.Click],
                            "#sel_table",
                            offset=(2, 2),
                            times=2,
                        )
                    elif gesture == "escape":
                        await pilot.press("escape")
                    else:
                        button = {"select": "btn_0", "continue": "btn_1", "cancel": "btn_cancel_exit"}[gesture]
                        assert await pilot.click(f"#{button}")
                    await pilot.pause()
                return app.return_value

            return asyncio.run(interact())

        monkeypatch.setattr(_SingleDialogApp, "run", headless)
        manager = _TextualSyncQueue()
    else:
        pytest.importorskip("tkinter")
        from execsql.gui import desktop
        from tests.gui.test_desktop_dialogs import _install_fake_tk, _mk_widget

        tk, ttk, _ = _install_fake_tk()
        monkeypatch.setattr(desktop, "tk", tk)
        monkeypatch.setattr(desktop, "ttk", ttk)
        win = _mk_widget()
        tk.Toplevel.side_effect = None
        tk.Toplevel.return_value = win

        def frame(*args, **kwargs):
            widget = _mk_widget()
            widget.winfo_toplevel.return_value = win
            return widget

        ttk.Frame.side_effect = frame
        tree = _mk_widget()
        tree.get_children.return_value = ("first", "second")
        tree.selection.return_value = ("second",)
        tree.item.side_effect = AssertionError("Do not recover source values from displayed strings")
        ttk.Treeview.side_effect = None
        ttk.Treeview.return_value = tree
        root = _mk_widget()

        def interact(win):
            assert tree.insert.call_count == 2

            def click(label):
                calls = tk.Button.call_args_list + ttk.Button.call_args_list
                next(call.kwargs["command"] for call in calls if call.kwargs.get("text") == label)()

            if gesture == "double":
                next(call.args[1] for call in tree.bind.call_args_list if call.args[0] == "<Double-1>")(None)
            elif gesture in ("enter", "continue_enter"):
                next(call.args[1] for call in win.bind.call_args_list if call.args[0] == "<Return>")(None)
            elif gesture == "escape":
                next(call.args[1] for call in win.bind.call_args_list if call.args[0] == "<Escape>")(None)
            elif gesture == "window":
                next(call.args[1] for call in win.protocol.call_args_list if call.args[0] == "WM_DELETE_WINDOW")()
            else:
                if gesture == "no_selection":
                    tree.selection.return_value = ()
                    click("OK")
                    win.destroy.assert_not_called()
                    tree.selection.return_value = ("second",)
                click({"continue": "Continue", "cancel": "Cancel"}.get(gesture, "OK"))

        root.wait_window.side_effect = interact
        native = desktop.TkinterBackend()
        native._root = root
        manager = desktop._TkinterSyncQueue(native)
    monkeypatch.setattr(data, "enable_gui", lambda: setattr(state, "gui_manager_queue", manager))


@pytest.mark.parametrize(("backend", "gesture"), CASES)
def test_selection_roundtrip_assigns_or_clears_the_documented_variables(database, monkeypatch, backend, gesture):
    _install_selector(monkeypatch, backend, gesture)
    continuing = gesture in ("continue", "continue_enter")
    command = '-- !x! PROMPT SELECT_SUB source MESSAGE "Pick a row"' + (" CONTINUE" if continuing else "") + "\n"
    result = run(
        sql=(
            "-- !x! CANCEL_HALT OFF\n"
            "-- !x! SELECT_SUB previous\n" + command + "-- !x! IF (SUB_DEFINED(@id)) { SUB captured_id !!@id!! }\n"
            "-- !x! IF (SUB_DEFINED(@name)) { SUB captured_name [!!@name!!] }\n"
            "-- !x! IF (SUB_DEFINED(@note)) { SUB captured_note [!!@note!!] }\n"
            "-- !x! SUB untouched !!@untouched!!\n"
        ),
        connection=database.db,
    )
    assert result.success, result.errors
    selected = gesture in ("select", "invalid", "enter", "double", "no_selection")
    expected = {"captured_id": database.expected_id, "captured_name": "[O'Brien]", "captured_note": "[]"}
    for name, value in expected.items():
        if selected:
            assert result.variables[name] == value
        else:
            assert name not in result.variables
    assert result.variables["untouched"] == "keep"


@pytest.mark.parametrize("backend", ["console", "textual", "tk"])
def test_cancel_halt_stops_before_the_following_statement(database, monkeypatch, backend):
    _install_selector(monkeypatch, backend, "cancel")
    result = run(
        sql='-- !x! PROMPT SELECT_SUB source MESSAGE "Pick a row"\n-- !x! SUB unreachable yes\n',
        connection=database.db,
    )
    assert not result.success
    assert any("exit status 2" in error.message for error in result.errors)
    assert "unreachable" not in result.variables


def test_empty_source_is_an_error_before_opening_a_dialog(database, monkeypatch):
    from unittest.mock import Mock

    database.db.conn.execute("create table empty_source as select * from source where 1 = 0")
    enable = Mock(side_effect=AssertionError("An empty source must not open a dialog"))
    monkeypatch.setattr(data, "enable_gui", enable)
    result = run(sql='-- !x! PROMPT SELECT_SUB empty_source MESSAGE "Pick"\n', connection=database.db)
    assert not result.success
    assert any("has no rows" in error.message for error in result.errors)
    enable.assert_not_called()


@pytest.mark.parametrize("row", [None, [], {"id": 1}])
def test_invalid_backend_selection_is_an_error_instead_of_confirmation(database, monkeypatch, row):
    class Manager:
        def put(self, spec):
            spec.return_queue.put({"button": 1, "row": row})

    monkeypatch.setattr(data, "enable_gui", lambda: setattr(state, "gui_manager_queue", Manager()))
    result = run(
        sql='-- !x! PROMPT SELECT_SUB source MESSAGE "Pick"\n-- !x! SUB unreachable yes\n',
        connection=database.db,
    )
    assert not result.success
    assert any("invalid source row" in error.message for error in result.errors)
    assert "unreachable" not in result.variables
