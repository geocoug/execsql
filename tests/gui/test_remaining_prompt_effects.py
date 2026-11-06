"""Remaining prompt interactions must reach real database and script effects."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from execsql import api, run, state
from execsql.db.sqlite import SQLiteDatabase
from execsql.metacommands import prompt
from execsql.utils import gui


@pytest.fixture(params=["console", "textual", "tk"])
def driver(request, monkeypatch):
    control = SimpleNamespace(
        name=request.param,
        answers=[],
        interact=None,
        tk=None,
        path="",
        cancelled=False,
        requests=[],
    )
    original_config = api._LibraryConfig
    monkeypatch.setattr(api, "_LibraryConfig", lambda **kw: original_config(gui_level=2, **kw))
    monkeypatch.setattr(gui, "_active_backend", None)
    if request.param == "console":
        from execsql.gui.console import ConsoleBackend

        backend = ConsoleBackend()

        def answer(*args):
            assert control.answers, "Unexpected terminal input"
            return control.answers.pop(0)

        monkeypatch.setattr("builtins.input", answer)

        class Manager:
            def put(self, spec):
                control.requests.append(spec)
                spec.return_queue.put(backend.dispatch(spec))

        manager = Manager()
    elif request.param == "textual":
        pytest.importorskip("textual")
        from execsql.gui.tui import _SingleDialogApp, _TextualSyncQueue

        def headless(app):
            async def interact():
                async with app.run_test(size=(110, 40)) as pilot:
                    await pilot.pause()
                    await control.interact(app, pilot)
                    await pilot.pause()
                    assert app.return_value is not None
                return app.return_value

            return asyncio.run(interact())

        monkeypatch.setattr(_SingleDialogApp, "run", headless)
        native = _TextualSyncQueue()

        class Manager:
            def put(self, spec):
                control.requests.append(spec)
                native.put(spec)

        manager = Manager()
    else:
        pytest.importorskip("tkinter")
        from execsql.gui import desktop
        from tests.gui.test_desktop_dialogs import _install_fake_tk, _mk_widget

        tk, ttk, _ = _install_fake_tk()
        monkeypatch.setattr(desktop, "tk", tk)
        monkeypatch.setattr(desktop, "ttk", ttk)
        root = _mk_widget()

        def variable(*args, **kwargs):
            var = _mk_widget()
            var.get.return_value = kwargs.get("value", "")
            return var

        tk.StringVar.side_effect = variable
        root.wait_window.side_effect = lambda win: control.tk(win, tk, ttk)
        for method in ("askopenfilename", "asksaveasfilename", "askdirectory"):
            monkeypatch.setattr(desktop.filedialog, method, lambda **kw: "" if control.cancelled else control.path)
        backend = desktop.TkinterBackend()
        backend._root = root
        native = desktop._TkinterSyncQueue(backend)
        control.widgets = (tk, ttk)

        class Manager:
            def put(self, spec):
                control.requests.append(spec)
                native.put(spec)

        manager = Manager()
    enable = lambda: setattr(state, "gui_manager_queue", manager)
    monkeypatch.setattr(prompt, "enable_gui", enable)
    monkeypatch.setattr(gui, "enable_gui", enable)
    from execsql.metacommands import control as control_commands

    monkeypatch.setattr(control_commands, "enable_gui", enable)
    return control


@pytest.fixture(params=["sqlite", "duckdb"])
def row_database(request, tmp_path):
    if request.param == "sqlite":
        db = SQLiteDatabase(str(tmp_path / "rows.sqlite"))
    else:
        pytest.importorskip("duckdb")
        from execsql.db.duckdb import DuckDBDatabase

        db = DuckDBDatabase(str(tmp_path / "rows.duckdb"))
    for sql in (
        "create table source (label text, id bigint, payload blob);",
        "create table destination (extra text default 'new', payload blob, id bigint check(id <> 99), label text);",
        "insert into destination values ('existing', NULL, 0, 'keep');",
    ):
        db.conn.execute(sql)
    for row in [("O'Brien", 2**60, b"\x00\xff"), (None, 2, b"")]:
        db.conn.execute("insert into source values (?, ?, ?)", row)
    db.conn.commit()
    yield db
    db.close()


def choose_rows(driver, *, cancel=False):
    driver.answers = ["1"]
    if driver.name == "textual":
        from textual.widgets import DataTable

        async def interact(app, pilot):
            source = app.screen.query_one("#source_table", DataTable)
            source.focus()
            await pilot.press("enter", "enter", "down", "enter")
            await pilot.pause()
            assert app.screen.query_one("#dest_table", DataTable).row_count == 4
            if cancel:
                await pilot.press("escape")
            else:
                assert await pilot.click("#btn_0")

        driver.interact = interact
    elif driver.name == "tk":
        from tests.gui.test_desktop_dialogs import _mk_widget

        tk, ttk = driver.widgets
        source, dest = _mk_widget(), _mk_widget()
        source.get_children.return_value = ("first", "second")
        source.item.side_effect = AssertionError("Selection must preserve original native row values")
        dest.get_children.return_value = ("existing",)
        ttk.Treeview.side_effect = [source, dest]

        def interact(win, tk, ttk):
            select = next(c.args[1] for c in source.bind.call_args_list if c.args[0] == "<Double-1>")
            for row in ("first", "first", "second"):
                source.selection.return_value = (row,)
                select(None)
            assert dest.insert.call_count == 4
            if cancel:
                next(c.args[1] for c in win.bind.call_args_list if c.args[0] == "<Escape>")(None)
            else:
                next(c.kwargs["command"] for c in tk.Button.call_args_list if c.kwargs.get("text") == "Continue")()

        driver.tk = interact


ROW_COMMAND = '-- !x! PROMPT SELECT_ROWS FROM source INTO destination MESSAGE "Choose"\n'


def stored_rows(db):
    return db.conn.execute("select extra, payload, id, label from destination order by id, label").fetchall()


def test_widget_selection_reaches_destination_with_exact_values_and_duplicates(row_database, driver):
    choose_rows(driver)
    result = run(sql=ROW_COMMAND, connection=row_database)
    assert result.success, result.errors
    expected = [("existing", None, 0, "keep")]
    if driver.name != "console":
        expected += [
            ("new", b"", 2, None),
            ("new", b"\x00\xff", 2**60, "O'Brien"),
            ("new", b"\x00\xff", 2**60, "O'Brien"),
        ]
    assert stored_rows(row_database) == expected
    assert len(driver.requests) == 1


@pytest.mark.parametrize("driver", ["textual", "tk"], indirect=True)
@pytest.mark.parametrize("halt", [False, True])
def test_widget_cancel_discards_selected_rows_and_honors_policy(row_database, driver, halt):
    choose_rows(driver, cancel=True)
    result = run(
        sql=f"-- !x! CANCEL_HALT {'ON' if halt else 'OFF'}\n" + ROW_COMMAND + "-- !x! SUB after yes\n",
        connection=row_database,
    )
    assert result.success is not halt, result.errors
    assert result.variables.get("after") == (None if halt else "yes")
    assert stored_rows(row_database) == [("existing", None, 0, "keep")]


@pytest.mark.parametrize("driver", ["textual", "tk"], indirect=True)
def test_widget_selection_rolls_back_all_rows_on_late_constraint_failure(row_database, driver):
    row_database.conn.execute("update source set id=99 where id=2")
    row_database.conn.commit()
    choose_rows(driver)
    result = run(sql=ROW_COMMAND, connection=row_database)
    assert not result.success
    assert any("constraint" in error.message.lower() for error in result.errors)
    assert stored_rows(row_database) == [("existing", None, 0, "keep")]


@pytest.mark.parametrize("operation", ["OPENFILE", "SAVEFILE", "DIRECTORY"])
@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
def test_path_picker_returns_to_the_correct_script_variable(driver, tmp_path, operation, local, cancel):
    selected = tmp_path / ("folder with spaces" if operation == "DIRECTORY" else "file with spaces.sql")
    if operation == "DIRECTORY":
        selected.mkdir()
    elif operation == "OPENFILE":
        selected.write_text("select 1;\n")
    driver.path = str(selected)
    driver.cancelled = cancel
    driver.answers = ["" if cancel else str(selected)]
    if driver.name == "textual":
        from textual.widgets import Input

        async def interact(app, pilot):
            app.screen.query_one("#path_input", Input).value = str(selected)
            assert await pilot.click("#btn_cancel" if cancel else "#btn_ok")

        driver.interact = interact
    var = "~picked" if local else "picked"
    command = f"-- !x! SUB{'_LOCAL' if local else ''} picked old\n-- !x! PROMPT {operation} SUB {var}\n"
    if cancel:
        command += f"-- !x! ASSERT NOT SUB_DEFINED({var})\n-- !x! ASSERT DIALOG_CANCELED()\n"
    else:
        command += f"-- !x! SUB captured [!!{var}!!]\n-- !x! ASSERT NOT DIALOG_CANCELED()\n"
    if local:
        command = (
            "-- !x! BEGIN SCRIPT pick\n"
            + command
            + "-- !x! END SCRIPT\n-- !x! EXECUTE SCRIPT pick\n-- !x! ASSERT NOT SUB_DEFINED(~picked)\n"
        )
    result = run(sql="-- !x! CANCEL_HALT OFF\n" + command, dsn="sqlite:///:memory:")
    assert result.success, result.errors
    assert result.variables.get("captured") == (None if cancel else f"[{selected}]")
    if local or cancel:
        assert "picked" not in result.variables
    else:
        assert result.variables["picked"] == str(selected)


@pytest.mark.parametrize("keyboard", [False, True])
@pytest.mark.parametrize("answer", ["Yes", "No"])
@pytest.mark.parametrize("compare", [False, True])
def test_actual_answer_widget_assigns_yes_or_no(driver, answer, compare, keyboard):
    driver.answers = ["1" if answer == "Yes" else "2"]
    if driver.name == "textual":
        from textual.widgets import Button

        async def interact(app, pilot):
            button = next(button for button in app.screen.query(Button) if str(button.label) == answer)
            if keyboard:
                button.focus()
                await pilot.press("enter")
            else:
                assert await pilot.click(button)

        driver.interact = interact
    elif driver.name == "tk":

        def interact(win, tk, ttk):
            call = next(c for c in tk.Button.call_args_list if c.kwargs.get("text") == answer)
            if keyboard:
                bindings = call.args[0].winfo_toplevel().bind.call_args_list
                next(c.args[1] for c in bindings if c.args[0] == ("y" if answer == "Yes" else "n"))(None)
            else:
                call.kwargs["command"]()

        driver.tk = interact
    db = SQLiteDatabase(":memory:")
    try:
        db.conn.executescript(
            "create table first_table (id integer); insert into first_table values(1); create table second_table as select * from first_table;",
        )
        suffix = " COMPARE first_table BESIDE second_table KEY(id)" if compare else " DISPLAY first_table"
        result = run(sql='-- !x! PROMPT ASK "Proceed?" SUB answer' + suffix + "\n", connection=db)
        assert result.success, result.errors
        assert result.variables["answer"] == answer
    finally:
        db.close()


def test_actual_connect_widget_creates_usable_sqlite_alias(driver, tmp_path):
    path = tmp_path / "selected.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("create table effects (value text)")
    driver.answers = ["l", "", str(path), "", ""]
    if driver.name == "textual":
        from textual.widgets import Input, Select

        async def interact(app, pilot):
            app.screen.query_one("#db_type_select", Select).value = "l"
            app.screen.query_one("#database_input", Input).value = str(path)
            assert await pilot.click("#btn_ok")

        driver.interact = interact
    elif driver.name == "tk":

        def interact(win, tk, ttk):
            next(c.kwargs["command"] for c in ttk.Button.call_args_list if c.kwargs.get("text") == "Connect")()

        tk, ttk = driver.widgets
        from tests.gui.test_desktop_dialogs import _mk_widget

        combo = _mk_widget()
        combo.current.return_value = 2
        ttk.Combobox.side_effect = lambda *a, **kw: combo
        original_entry = ttk.Entry.side_effect
        count = 0

        def entry(*args, **kwargs):
            nonlocal count
            count += 1
            kwargs["textvariable"].get.return_value = str(path) if count == 2 else ""
            return original_entry(*args, **kwargs)

        ttk.Entry.side_effect = entry
        driver.tk = interact
    result = run(
        sql="-- !x! PROMPT MESSAGE \"Choose\" CONNECT AS selected\n-- !x! USE selected\ninsert into effects values ('written through alias');\n",
        dsn="sqlite:///:memory:",
    )
    assert result.success, result.errors
    with sqlite3.connect(path) as conn:
        assert conn.execute("select value from effects").fetchall() == [("written through alias",)]


@pytest.mark.parametrize("driver", ["textual", "tk"], indirect=True)
def test_actual_selected_rows_obey_the_callers_held_transaction(row_database, driver):
    choose_rows(driver)
    result = run(sql="-- !x! AUTOCOMMIT OFF\n" + ROW_COMMAND, connection=row_database)
    assert result.success, result.errors
    assert len(stored_rows(row_database)) == 4
    row_database.conn.rollback()
    assert stored_rows(row_database) == [("existing", None, 0, "keep")]


@pytest.mark.parametrize("operation", ["OPENFILE", "SAVEFILE"])
def test_file_chooser_assigns_related_filename_variables(driver, tmp_path, operation):
    selected = tmp_path / "sample.data.sql"
    selected.write_text("select 1;\n")
    driver.path = str(selected)
    driver.answers = [str(selected)]
    if driver.name == "textual":
        from textual.widgets import Input

        async def interact(app, pilot):
            app.screen.query_one("#path_input", Input).value = str(selected)
            assert await pilot.click("#btn_ok")

        driver.interact = interact
    result = run(sql=f"-- !x! PROMPT {operation} SUB chosen filename folder ext stem\n", dsn="sqlite:///:memory:")
    assert result.success, result.errors
    assert result.variables["chosen"] == str(selected)
    assert result.variables["filename"] == "sample.data.sql"
    assert result.variables["folder"] == str(tmp_path)
    assert result.variables["ext"] == "sql"
    assert result.variables["stem"] == "sample.data"


@pytest.mark.parametrize("operation", ["message", "pause", "halt", "map", "display"])
def test_dialog_confirmation_controls_real_script_flow(driver, monkeypatch, operation):
    driver.answers = ["" if operation == "pause" else "1"]
    if driver.name == "textual":
        from textual.widgets import Button

        async def interact(app, pilot):
            candidates = [
                button for button in app.screen.query(Button) if str(button.label) in ("Continue", "Close", "OK")
            ]
            assert candidates
            assert await pilot.click(candidates[-1])

        driver.interact = interact
    elif driver.name == "tk":
        if operation == "map":
            monkeypatch.setitem(sys.modules, "tkintermapview", None)

        def interact(win, tk, ttk):
            if operation == "pause":
                next(c.kwargs["command"] for c in ttk.Button.call_args_list if c.kwargs.get("text") == "Continue")()
            else:
                label = "Continue" if operation in ("map", "display") else "Close"
                calls = tk.Button.call_args_list + ttk.Button.call_args_list
                next(c.kwargs["command"] for c in calls if c.kwargs.get("text") == label)()

        driver.tk = interact
    command = {
        "message": '-- !x! PROMPT MESSAGE "Hello"\n',
        "display": '-- !x! PROMPT DISPLAY source MESSAGE "Data"\n',
        "pause": '-- !x! PROMPT PAUSE "Wait"\n',
        "halt": '-- !x! HALT "Stop" DISPLAY source EXIT_STATUS 7\n',
        "map": '-- !x! PROMPT MESSAGE "Places" MAP source LAT lat LON lon LABEL label\n',
    }[operation]
    db = SQLiteDatabase(":memory:")
    try:
        db.conn.executescript(
            "create table source (lat real, lon real, label text); insert into source values(40.1,-120.2,'Point');",
        )
        result = run(sql=command + "-- !x! SUB after yes\n", connection=db)
        if operation == "halt":
            assert not result.success
            assert any("exit status 7" in error.message for error in result.errors)
            assert "after" not in result.variables
        else:
            assert result.success, result.errors
            assert result.variables["after"] == "yes"
        assert len(driver.requests) == 1
    finally:
        db.close()


@pytest.mark.parametrize("driver", ["textual"], indirect=True)
@pytest.mark.parametrize("compare", [False, True])
@pytest.mark.parametrize("escape", [False, True])
@pytest.mark.parametrize("halt", [False, True])
def test_textual_ask_cancel_is_distinct_from_no(driver, compare, escape, halt):
    async def interact(app, pilot):
        if escape:
            await pilot.press("escape")
        else:
            assert await pilot.click("#btn_cancel_exit")

    driver.interact = interact
    suffix = " COMPARE first_table BESIDE second_table KEY(id)" if compare else " DISPLAY first_table"
    sql = (
        "create table first_table (id integer);\ninsert into first_table values (1);\n"
        "create table second_table as select * from first_table;\n"
        "-- !x! SUB answer previous\n"
        f"-- !x! CANCEL_HALT {'ON' if halt else 'OFF'}\n"
        '-- !x! PROMPT ASK "Proceed?" SUB answer' + suffix + "\n"
        "-- !x! ASSERT DIALOG_CANCELED()\n-- !x! SUB after yes\n"
    )
    result = run(sql=sql, dsn="sqlite:///:memory:")
    assert result.success is not halt, result.errors
    assert result.variables["answer"] == "previous"
    assert result.variables.get("after") == (None if halt else "yes")
    if halt:
        assert any("exit status 2" in error.message for error in result.errors)
