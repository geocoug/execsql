"""Entry form interaction must produce correctly scoped script values."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from execsql import run, state
from execsql.db.sqlite import SQLiteDatabase
from execsql.metacommands import prompt


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "forms.db"))
    db.conn.executescript(
        "create table specs (sequence integer, sub_var text, prompt text, entry_type text, lookup_table text);"
        "create table choices (value text);"
        "insert into choices values ('red'), ('O''Brien'), ('blue'), ('red');"
        "create table observed (value text);",
    )
    yield db
    db.close()


@pytest.fixture(params=["console", "textual", "tk"])
def form(request, monkeypatch):
    interaction = SimpleNamespace(values={}, cancel=False)
    if request.param == "console":
        from execsql.gui.console import ConsoleBackend

        backend = ConsoleBackend()

        class Manager:
            def put(self, spec):
                answers = []
                for entry in spec.args["entry_specs"]:
                    value = interaction.values.get(entry.name, "")
                    if entry.entry_type == "listbox":
                        value = ",".join(str(i + 1) for i in value)
                    answers.append(value)
                answers.append("n" if interaction.cancel else "y")
                pending = iter(answers)
                monkeypatch.setattr("builtins.input", lambda *args: next(pending))
                spec.return_queue.put(backend.dispatch(spec))

        manager = Manager()
    elif request.param == "textual":
        pytest.importorskip("textual")
        from textual.widgets import Input, SelectionList

        from execsql.gui.tui import EntryFormScreen, _SingleDialogApp, _TextualSyncQueue

        def headless(app):
            async def interact():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    screen = app.screen
                    assert isinstance(screen, EntryFormScreen)
                    for entry in screen._specs:
                        widget = screen._inputs[entry.name]
                        value = interaction.values.get(entry.name, "")
                        if isinstance(widget, SelectionList):
                            for index in value:
                                widget.select((index, str(entry.lookup_list[index])))
                        else:
                            assert isinstance(widget, Input)
                            widget.value = value
                    if interaction.cancel:
                        await pilot.press("escape")
                    else:
                        screen.query_one("#btn_ok").scroll_visible(immediate=True)
                        await pilot.pause()
                        assert await pilot.click("#btn_ok")
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
        root = _mk_widget()
        original_close = desktop.EntryFormDialog._close

        def close(dialog, win, specs, ok):
            for entry in specs:
                kind, widget = dialog._widgets[entry.name]
                value = interaction.values.get(entry.name, "")
                if kind == "listbox":
                    widget.curselection.return_value = value
                    widget.get.side_effect = lambda i, entry=entry: entry.lookup_list[i]
                else:
                    widget.get.return_value = value
            original_close(dialog, win, specs, ok)

        monkeypatch.setattr(desktop.EntryFormDialog, "_close", close)

        def choose(win):
            label = "Cancel" if interaction.cancel else "OK"
            next(c.kwargs["command"] for c in ttk.Button.call_args_list if c.kwargs.get("text") == label)()

        root.wait_window.side_effect = choose
        backend = desktop.TkinterBackend()
        backend._root = root
        manager = desktop._TkinterSyncQueue(backend)
    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", manager))
    return interaction


def add_specs(database, specs):
    database.conn.executemany("insert into specs values (?, ?, ?, ?, ?)", specs)
    database.conn.commit()


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("local_value", ["local", ""])
def test_form_fields_keep_their_declared_scope(database, form, reverse, local_value):
    specs = [(1, "globalx", "Global", None, None), (2, "~localx", "Local", None, None)]
    if reverse:
        specs = [(3 - seq, *rest) for seq, *rest in specs]
    add_specs(database, specs)
    form.values = {"globalx": "global", "~localx": local_value}
    local_assertion = (
        "-- !x! ASSERT SUB_DEFINED(~localx)\n-- !x! SUB captured_local !!~localx!!\n"
        if local_value
        else "-- !x! ASSERT NOT SUB_DEFINED(~localx)\n"
    )
    result = run(
        sql=(
            "-- !x! SUB globalx previous\n-- !x! SUB localx untouched\n-- !x! SUB unrelated preserved\n"
            "-- !x! BEGIN SCRIPT fill\n-- !x! SUB_LOCAL localx previous\n"
            '-- !x! PROMPT ENTRY_FORM specs MESSAGE "Fill"\n'
            + local_assertion
            + "-- !x! SUB captured_global !!globalx!!\n-- !x! END SCRIPT\n"
            "-- !x! EXECUTE SCRIPT fill\n-- !x! ASSERT NOT SUB_DEFINED(~localx)\n"
            "-- !x! SUB after_global !!globalx!!\n"
        ),
        connection=database,
    )
    assert result.success, result.errors
    assert result.variables["globalx"] == result.variables["captured_global"] == "global"
    assert result.variables["after_global"] == "global"
    assert result.variables["localx"] == "untouched"
    assert result.variables["unrelated"] == "preserved"
    assert result.variables.get("captured_local") == (local_value or None)


@pytest.mark.parametrize(
    "selection, expected",
    [([2], "'blue'"), ([0, 1], "'red','O''Brien'"), ([0, 3], "'red','red'"), ([], None)],
)
@pytest.mark.parametrize("cancel", [False, True])
def test_listbox_confirmation_assigns_quoted_selections(database, form, selection, expected, cancel):
    add_specs(database, [(1, "picked", "Pick", "listbox", "choices")])
    form.values = {"picked": selection}
    form.cancel = cancel
    result = run(
        sql='-- !x! CANCEL_HALT OFF\n-- !x! PROMPT ENTRY_FORM specs MESSAGE "Pick"\n-- !x! SUB after yes\n',
        connection=database,
    )
    assert result.success, result.errors
    assert result.variables.get("picked") == (None if cancel else expected)
    assert result.variables["after"] == "yes"


@pytest.mark.parametrize("entry_type", ["dropdown", "select"])
def test_lookup_rejects_unlisted_value_before_accepting_valid_choice(database, monkeypatch, entry_type):
    pytest.importorskip("textual")
    from execsql.gui.tui import EntryFormScreen, _SingleDialogApp, _TextualSyncQueue

    add_specs(database, [(1, "picked", "Pick", entry_type, "choices")])
    rejected = []

    def headless(app):
        async def interact():
            async with app.run_test() as pilot:
                screen = app.screen
                assert isinstance(screen, EntryFormScreen)
                screen._inputs["picked"].value = "unlisted"
                screen.query_one("#btn_ok").scroll_visible(immediate=True)
                await pilot.pause()
                assert await pilot.click("#btn_ok")
                await pilot.pause()
                assert app.screen is screen
                assert app.return_value is None
                assert any("valid" in message.lower() for message in screen._validate())
                rejected.append(True)
                screen._inputs["picked"].value = "blue"
                await pilot.pause(0.4)  # Wait for Textual Button debounce before retrying.
                assert await pilot.click("#btn_ok")
                await pilot.pause()
                assert app.return_value["button"] == 1
            return app.return_value

        return asyncio.run(interact())

    monkeypatch.setattr(_SingleDialogApp, "run", headless)
    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", _TextualSyncQueue()))
    result = run(sql='-- !x! PROMPT ENTRY_FORM specs MESSAGE "Pick"\n', connection=database)
    assert result.success, result.errors
    assert rejected == [True]
    assert result.variables["picked"] == "blue"


@pytest.mark.parametrize("entry_type", ["dropdown", "select"])
def test_valid_lookup_value_reaches_script_on_every_backend(database, form, entry_type):
    add_specs(database, [(1, "picked", "Pick", entry_type, "choices")])
    form.values = {"picked": "blue"}
    result = run(sql='-- !x! PROMPT ENTRY_FORM specs MESSAGE "Pick"\n', connection=database)
    assert result.success, result.errors
    assert result.variables["picked"] == "blue"


def test_form_cancel_halt_stops_script(database, form):
    add_specs(database, [(1, "picked", "Pick", "listbox", "choices")])
    form.values = {"picked": [1]}
    form.cancel = True
    result = run(
        sql="-- !x! PROMPT ENTRY_FORM specs MESSAGE \"Pick\"\ninsert into observed values ('unreachable');\n",
        connection=database,
    )
    assert not result.success
    assert any("exit status 2" in error.message for error in result.errors)
    assert "picked" not in result.variables
    assert database.conn.execute("select * from observed").fetchall() == []
