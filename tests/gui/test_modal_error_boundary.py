"""Mounted modal failures must follow script error policy without quitting the UI."""

from __future__ import annotations

import asyncio
import functools
import sqlite3

import pytest
from typer.testing import CliRunner

pytest.importorskip("textual")

from execsql import state  # noqa: E402
from execsql.cli import app as cli  # noqa: E402
from execsql.gui import tui  # noqa: E402


def failing_screen(phase):
    from textual.widgets import Static

    class BrokenChild(Static):
        def on_mount(self):
            raise ValueError("child mount failed")

    class FailingForm(tui.EntryFormScreen):
        def compose(self):
            if self.args.get("message") == "Bad" and phase == "compose":
                raise ValueError("form compose failed")
            yield from super().compose()
            if self.args.get("message") == "Bad" and phase == "child-mount":
                yield BrokenChild()

        def on_mount(self):
            if self.args.get("message") == "Bad" and phase == "mount":
                raise ValueError("form mount failed")

    return FailingForm


@pytest.mark.parametrize("phase", ["validation", "compose", "mount", "child-mount"])
@pytest.mark.parametrize("halt", [False, True])
def test_cli_form_failure_obeys_error_policy_and_rolls_back(monkeypatch, tmp_path, halt, phase):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("execsql.utils.gui._active_backend", None)
    monkeypatch.setattr("execsql.utils.gui._console_running", False)
    callbacks = []
    errors = []
    from execsql.utils.gui import ConsoleUIError
    from execsql.metacommands import prompt

    original_response = prompt.get_gui_response

    def checked_response(*args):
        try:
            return original_response(*args)
        except ConsoleUIError as exc:
            errors.append(str(exc))
            raise

    monkeypatch.setattr(prompt, "get_gui_response", checked_response)
    monkeypatch.setattr(tui, "EntryFormScreen", failing_screen(phase))

    def register(fn, *args, **kwargs):
        callbacks.append(functools.partial(fn, *args, **kwargs))
        return fn

    monkeypatch.setattr("atexit.register", register)
    path = tmp_path / "forms.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "create table events(v text);"
            "create table bad(sub_var text, prompt text, initial_value text, validation_regex text);"
            "insert into bad values('chosen', 'Value', 'a', '[');"
            "create table good as select 'chosen' sub_var, 'Value' prompt, 'recovered' initial_value;",
        )
    apps = []

    def headless(app):
        apps.append(app)

        async def interact():
            async with app.run_test(size=(100, 40)) as pilot:
                for _ in range(400):
                    if app._exit:
                        break
                    if (
                        isinstance(app.screen, tui.EntryFormScreen)
                        and app.screen.is_mounted
                        and (phase == "validation" or app.screen.args.get("message") == "Good")
                    ):
                        screen = app.screen
                        await pilot.pause()
                        if app.screen is screen:
                            await pilot.click("#btn_ok")
                    elif isinstance(app.screen, tui.MsgScreen) and app.screen.query("#btn_0"):
                        await pilot.click("#btn_0")
                    await asyncio.sleep(0.01)
                assert app._exit, "Form failure left the script waiting"
            assert not app._script_thread.is_alive()

        asyncio.run(interact())

    monkeypatch.setattr(tui.ConsoleApp, "run", headless)
    config = tmp_path / "console.conf"
    config.write_text("[interface]\nconsole_wait_when_done=No\nconsole_wait_when_error_halt=No\n")
    sql = (
        f"-- !x! METACOMMAND_ERROR_HALT {'ON' if halt else 'OFF'}\n"
        "-- !x! ERROR_HALT OFF\n-- !x! CANCEL_HALT OFF\n-- !x! BEGIN BATCH\n"
        "insert into events values('pending');\n-- !x! PROMPT ENTRY_FORM bad MESSAGE \"Bad\"\n"
        "-- !x! IF (METACOMMAND_ERROR()) { SUB caught yes }\n"
        "-- !x! IF (DIALOG_CANCELED()) { SUB canceled yes }\n-- !x! END BATCH\n"
        "-- !x! PROMPT ENTRY_FORM good MESSAGE \"Good\"\ninsert into events values('!!chosen!!');\n"
    )
    result = CliRunner().invoke(
        cli,
        ["run", "--config", str(config), "--dsn", f"sqlite:///{path}", "-v3", "--gui-framework", "textual", "-c", sql],
    )
    for callback in reversed(callbacks):
        callback()
    assert result.exit_code == (1 if halt else 0), (result.output, result.exception)
    assert len(apps) == 1
    assert not apps[0]._quit_requested
    assert apps[0]._exception is None
    expected_error = (
        "unterminated character set"
        if phase == "validation"
        else "child mount failed"
        if phase == "child-mount"
        else f"form {phase} failed"
    )
    assert len(errors) == 1
    assert expected_error in errors[0]
    if not halt:
        assert state.subvars.sub_exists("caught")
        assert not state.subvars.sub_exists("canceled")
    with sqlite3.connect(path) as conn:
        assert conn.execute("select * from events").fetchall() == ([] if halt else [("recovered",)])


@pytest.mark.parametrize("phase", ["validation", "compose", "mount", "child-mount"])
def test_single_dialog_reports_mounted_failure_through_checked_response(phase):
    import queue

    from execsql.utils.gui import ConsoleUIError
    from execsql.utils.gui import GUI_ENTRY, EntrySpec, get_gui_response

    app = tui._SingleDialogApp(
        failing_screen(phase),
        {
            "message": "Bad",
            "entry_specs": [EntrySpec("chosen", "Value", initial_value="a", validation_regex="[")],
        },
    )

    async def interact():
        async with app.run_test(size=(100, 40)) as pilot:
            for _ in range(100):
                if app._exit:
                    break
                if phase == "validation" and isinstance(app.screen, tui.EntryFormScreen) and app.screen.is_mounted:
                    screen = app.screen
                    await pilot.pause()
                    if app.screen is screen:
                        await pilot.click("#btn_ok")
                await asyncio.sleep(0.01)
            assert app._exit

    asyncio.run(interact())
    assert app._exception is None
    response = queue.Queue()
    response.put(app.return_value)
    with pytest.raises(ConsoleUIError, match="failed"):
        get_gui_response(response, GUI_ENTRY)
    assert response.empty()


def test_console_failure_outside_the_modal_keeps_textual_failure_handling():
    import queue

    from execsql.utils.gui import GUI_ENTRY, EntrySpec, GuiSpec, get_gui_response

    dialogs = tui._ConsoleDialogQueue()
    spec = GuiSpec(GUI_ENTRY, {"entry_specs": [EntrySpec("chosen", "Value")]}, queue.Queue())

    def runner():
        dialogs.put(spec)
        get_gui_response(spec.return_queue, GUI_ENTRY)

    app = tui.ConsoleApp(runner, dialogs)

    def fail_console():
        raise RuntimeError("console timer failed")

    async def interact():
        async with app.run_test(size=(100, 40)):
            for _ in range(100):
                if isinstance(app.screen, tui.EntryFormScreen) and app.screen.is_mounted:
                    break
                await asyncio.sleep(0.01)
            assert isinstance(app.screen, tui.EntryFormScreen)
            app.call_later(fail_console)
            for _ in range(100):
                if app._exit:
                    break
                await asyncio.sleep(0.01)
            assert app._exit

    with pytest.raises(RuntimeError, match="console timer failed"):
        asyncio.run(interact())
    assert isinstance(app._exception, RuntimeError)
    assert isinstance(app._script_exception, KeyboardInterrupt)
    assert not app._script_thread.is_alive()
    assert spec.return_queue.empty()
