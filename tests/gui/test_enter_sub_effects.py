"""ENTER_SUB edits must reach script variables with documented type/case controls."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from execsql import run, state
from execsql.db.sqlite import SQLiteDatabase
from execsql.metacommands import prompt


@pytest.fixture(params=["console", "textual", "tk"])
def entry(request, monkeypatch):
    choice = SimpleNamespace(values=["value"], cancel=False, keyboard=False, password=False, rejected=0)
    if request.param == "console":
        from execsql.gui.console import ConsoleBackend

        class Manager:
            def put(self, spec):
                answers = iter(choice.values)

                def read(*args, **kwargs):
                    if args and args[0] == "Choice: ":
                        return "1"
                    try:
                        return next(answers) or ""
                    except StopIteration:
                        pytest.fail("Entry requested an unexpected extra value")

                monkeypatch.setattr("builtins.input", read)
                monkeypatch.setattr("getpass.getpass", read)
                spec.return_queue.put(ConsoleBackend().dispatch(spec))

        manager = Manager()
    elif request.param == "textual":
        pytest.importorskip("textual")
        from textual.widgets import Input
        from execsql.gui.tui import DisplayScreen, _SingleDialogApp, _TextualSyncQueue

        def headless(app):
            async def interact():
                async with app.run_test() as pilot:
                    screen = app.screen
                    assert isinstance(screen, DisplayScreen)
                    widget = screen.query_one("#text_input", Input)
                    assert widget.password == choice.password
                    for index, value in enumerate(choice.values):
                        if value is not None:
                            widget.value = value
                        if choice.cancel:
                            await pilot.press("escape")
                            break
                        if choice.keyboard:
                            widget.focus()
                            await pilot.press("enter")
                        else:
                            if index:
                                await pilot.pause(0.4)  # Allow the button debounce before a corrected retry.
                            assert await pilot.click("#btn_0")
                        await pilot.pause()
                        if index < len(choice.values) - 1:
                            assert app.screen is screen
                            assert app.return_value is None
                            assert state.subvars.varvalue("answer") == "previous"
                            choice.rejected += 1
                    await pilot.pause()
                    assert app.return_value is not None
                return app.return_value

            return asyncio.run(interact())

        monkeypatch.setattr(_SingleDialogApp, "run", headless)
        manager = _TextualSyncQueue()
    else:
        pytest.importorskip("tkinter")
        from tkinter import messagebox
        from execsql.gui import desktop
        from tests.gui.test_desktop_dialogs import _install_fake_tk, _mk_widget

        tk, ttk, _ = _install_fake_tk()
        monkeypatch.setattr(desktop, "tk", tk)
        monkeypatch.setattr(desktop, "ttk", ttk)
        root = _mk_widget()
        windows = []
        tk.Toplevel.side_effect = lambda *args: windows.append(_mk_widget()) or windows[-1]
        variables = []

        def variable(*args, **kwargs):
            var = _mk_widget()
            var.get.return_value = kwargs.get("value") or ""
            variables.append(var)
            return var

        tk.StringVar.side_effect = variable
        monkeypatch.setattr(
            messagebox,
            "showerror",
            lambda *args, **kw: setattr(choice, "rejected", choice.rejected + 1),
        )

        def interact(win):
            assert ttk.Entry.call_args_list[-1].kwargs["show"] == ("*" if choice.password else "")
            for index, value in enumerate(choice.values):
                if value is not None:
                    variables[-1].get.return_value = value
                if choice.cancel:
                    next(c.args[1] for c in win.bind.call_args_list if c.args[0] == "<Escape>")(None)
                    break
                if choice.keyboard:
                    # _add_buttons binds Return through the button frame's toplevel.
                    frame = next(c.args[0] for c in tk.Button.call_args_list if c.kwargs.get("text") == "OK")
                    bound = frame.winfo_toplevel().bind.call_args_list
                    next(c.args[1] for c in bound if c.args[0] == "<Return>")(None)
                else:
                    next(c.kwargs["command"] for c in tk.Button.call_args_list if c.kwargs.get("text") == "OK")()
                if index < len(choice.values) - 1:
                    win.destroy.assert_not_called()
                    assert state.subvars.varvalue("answer") == "previous"

        root.wait_window.side_effect = interact
        backend = desktop.TkinterBackend()
        backend._root = root
        manager = desktop._TkinterSyncQueue(backend)
    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", manager))
    return choice


def execute(entry, options="", *, initial="", local=False, display=False, halt=False):
    name = "~answer" if local else "answer"
    command = f'-- !x! PROMPT ENTER_SUB {name} {"PASSWORD " if entry.password else ""}MESSAGE "Enter"'
    if display:
        command += " DISPLAY source"
    command += (" " + options if options else "") + (f' INITIALLY "{initial}"' if initial else "") + "\n"
    if local:
        command = (
            "-- !x! BEGIN SCRIPT fill\n"
            + command
            + "-- !x! SUB captured [!!~answer!!]\n-- !x! END SCRIPT\n-- !x! EXECUTE SCRIPT fill\n-- !x! ASSERT NOT SUB_DEFINED(~answer)\n"
        )
    db = SQLiteDatabase(":memory:")
    try:
        db.conn.executescript("create table source (value text); insert into source values ('context');")
        return run(
            sql=f"-- !x! SUB answer previous\n-- !x! CANCEL_HALT {'ON' if halt else 'OFF'}\n" + command,
            connection=db,
        )
    finally:
        db.close()


@pytest.mark.parametrize("keyboard", [False, True])
@pytest.mark.parametrize(
    "options, raw, expected",
    [
        ("TYPE INT", "-0012", "-0012"),
        ("TYPE FLOAT", "-.50", "-.50"),
        ("TYPE FLOAT", "12.", "12."),
        ("TYPE BOOL", "tR", "True"),
        ("TYPE BOOL", "FaL", "False"),
        ("TYPE IDENT", "User_12", "User_12"),
        ("", "  spaced value  ", "  spaced value  "),
        ("LCASE", "MiXeD", "mixed"),
        ("UCASE", "MiXeD", "MIXED"),
        ("TYPE BOOL UCASE", "f", "FALSE"),
        ("TYPE BOOL LCASE", "t", "true"),
        ("TYPE IDENT LCASE", "User_12", "user_12"),
    ],
)
def test_confirmed_entry_assigns_documented_text(entry, keyboard, options, raw, expected):
    entry.values = [raw]
    entry.keyboard = keyboard
    result = execute(entry, options)
    assert result.success, result.errors
    assert result.variables["answer"] == expected


@pytest.mark.parametrize("keyboard", [False, True])
@pytest.mark.parametrize(
    "options, invalid, corrected",
    [
        ("TYPE INT", ["letters", "1.2", "--2", "-"], "12"),
        ("TYPE FLOAT", ["1.2.3", "1-2", ".", "1e3"], ".25"),
        ("TYPE BOOL", ["truth", "yes", "0"], "f"),
        ("TYPE IDENT", ["1name", "_name", "bad-name", "has space"], "Valid_1"),
    ],
)
def test_invalid_entry_stays_open_until_corrected(entry, keyboard, options, invalid, corrected):
    entry.values = invalid + [corrected]
    entry.keyboard = keyboard
    result = execute(entry, options)
    assert result.success, result.errors
    assert result.variables["answer"] == ("False" if options == "TYPE BOOL" else corrected)
    if entry.rejected:
        assert entry.rejected == len(invalid)


@pytest.mark.parametrize("options", ["TYPE INT", "TYPE FLOAT", "TYPE BOOL", "TYPE IDENT", "UCASE"])
def test_empty_confirmation_is_allowed(entry, options):
    entry.values = [""]
    result = execute(entry, options)
    assert result.success, result.errors
    assert result.variables["answer"] == ""


@pytest.mark.parametrize("entry", ["textual", "tk"], indirect=True)
def test_cancel_does_not_validate_or_replace_existing_value(entry):
    entry.values = ["invalid"]
    entry.cancel = True
    result = execute(entry, "TYPE INT")
    assert result.success, result.errors
    assert result.variables["answer"] == "previous"
    assert not entry.rejected


def test_password_case_controls_and_local_scope(entry):
    entry.values = ["mIxEd"]
    entry.password = True
    result = execute(entry, "UCASE", local=True, display=True)
    assert result.success, result.errors
    assert result.variables["answer"] == "previous"
    assert result.variables["captured"] == "[MIXED]"


def test_invalid_initial_value_requires_correction(entry):
    entry.values = [None, "12"]
    result = execute(entry, "TYPE INT", initial="invalid")
    assert result.success, result.errors
    assert result.variables["answer"] == "12"


@pytest.mark.parametrize("entry", ["textual", "tk"], indirect=True)
def test_cancel_halt_bypasses_validation_and_stops(entry):
    entry.values = ["invalid"]
    entry.cancel = True
    result = execute(entry, "TYPE INT", halt=True)
    assert not result.success
    assert any("exit status 2" in error.message for error in result.errors)
    assert result.variables["answer"] == "previous"
    assert not entry.rejected


def test_password_validation_does_not_echo_rejected_value(entry, capsys):
    entry.values = ["not-a-numeric-password", "12"]
    entry.password = True
    result = execute(entry, "TYPE INT")
    assert result.success, result.errors
    assert result.variables["answer"] == "12"
    output = capsys.readouterr()
    assert "not-a-numeric-password" not in output.out + output.err


def test_handler_rejects_invalid_confirmation_from_custom_transport(monkeypatch):
    class Manager:
        def put(self, spec):
            spec.return_queue.put({"button": 1, "return_value": "invalid"})

    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", Manager()))
    result = run(
        sql='-- !x! SUB answer previous\n-- !x! PROMPT ENTER_SUB answer MESSAGE "Enter" TYPE INT\n',
        dsn="sqlite:///:memory:",
    )
    assert not result.success
    assert result.variables["answer"] == "previous"
