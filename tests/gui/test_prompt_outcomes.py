"""GUI transports must preserve script error, cancellation and transaction rules."""

from __future__ import annotations

import asyncio
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from execsql import run, state
from execsql.db.sqlite import SQLiteDatabase
from execsql.gui import gui_manager_loop
from execsql.metacommands import prompt

DISPLAY = '-- !x! PROMPT DISPLAY source MESSAGE "Confirm"\n'


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "prompts.db"))
    db.conn.executescript(
        "create table source (id integer); insert into source values (1); create table events (v text);"
        "create table form_spec (sub_var text, prompt text); insert into form_spec values ('chosen', 'Value');",
    )
    yield db
    db.close()


@pytest.fixture(params=["tk", "textual", "manager", "persistent"])
def transport(request, monkeypatch):
    """Keep real queue adapters; replace only dispatch or terminal ownership."""
    dispatch = Mock()
    threads = []
    if request.param == "tk":
        pytest.importorskip("tkinter")
        from execsql.gui.desktop import _TkinterSyncQueue

        manager = _TkinterSyncQueue(SimpleNamespace(dispatch=dispatch, _root=None))
    elif request.param == "textual":
        pytest.importorskip("textual")
        from execsql.gui.tui import _SingleDialogApp, _TextualSyncQueue

        monkeypatch.setattr(_SingleDialogApp, "run", lambda app: dispatch(app._screen_args))
        manager = _TextualSyncQueue()
    elif request.param == "manager":
        manager = queue.Queue()
        thread = threading.Thread(target=gui_manager_loop, args=(manager, SimpleNamespace(dispatch=dispatch)))
        thread.start()
        threads.append(thread)
    else:
        pytest.importorskip("textual")
        from execsql.gui.tui import ConsoleApp, _build_screen_map, _ConsoleDialogQueue

        app = object.__new__(ConsoleApp)
        app._dialog_queue = _ConsoleDialogQueue()
        app._screen_map = _build_screen_map()
        app._script_thread = None

        async def push_screen_wait(screen):
            return dispatch(screen.args)

        app.push_screen_wait = push_screen_wait
        app.run_worker = lambda work, **kwargs: asyncio.run(work())

        class Manager:
            def put(self, spec):
                app._dialog_queue.put(spec)
                app._poll_dialog_queue()

        manager = Manager()

    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", manager))
    yield dispatch
    for thread in threads:
        manager.put(None)
        thread.join(2)
        assert not thread.is_alive()


@pytest.mark.parametrize("halt_errors", ["ON", "OFF"])
def test_failed_confirmation_fails_the_batch_instead_of_committing(database, transport, halt_errors):
    transport.side_effect = ValueError("dialog exploded")
    result = run(
        sql=(
            "-- !x! CANCEL_HALT OFF\n"
            f"-- !x! METACOMMAND_ERROR_HALT {halt_errors}\n"
            "-- !x! ERROR_HALT OFF\n"
            "-- !x! BEGIN BATCH\n"
            "insert into events values ('unconfirmed');\n" + DISPLAY + "-- !x! END BATCH\n"
        ),
        connection=database,
    )
    assert not result.success
    assert any("dialog exploded" in error.message for error in result.errors)
    assert database.conn.execute("select * from events").fetchall() == []


def test_halt_still_stops_if_its_dialog_fails(database, transport, monkeypatch):
    from execsql.metacommands import control

    transport.side_effect = ValueError("dialog exploded")
    monkeypatch.setattr(control, "enable_gui", prompt.enable_gui)
    monkeypatch.setattr(control, "gui_console_isrunning", lambda: True)
    result = run(
        sql=("-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! HALT \"Stop\"\ninsert into events values ('unreachable');\n"),
        connection=database,
    )
    assert not result.success
    assert any("dialog exploded" in error.message for error in result.errors)
    assert database.conn.execute("select * from events").fetchall() == []


def test_cancel_halt_off_continues_and_records_cancellation(database, transport):
    transport.return_value = {"button": None, "cancelled": True}
    result = run(
        sql=(
            "-- !x! CANCEL_HALT OFF\n" + DISPLAY + "-- !x! IF (DIALOG_CANCELED()) { SUB cancelled yes }\n"
            "insert into events values ('continued');\n"
        ),
        connection=database,
    )
    assert result.success, result.errors
    assert result.variables.get("cancelled") == "yes"
    assert database.conn.execute("select * from events").fetchall() == [("continued",)]


def test_cancellation_flag_tracks_the_last_dialog_and_can_be_reset(database, transport):
    transport.side_effect = [
        {"button": None, "cancelled": True},
        {"button": 1},
        {"button": None, "cancelled": True},
    ]
    result = run(
        sql=(
            "-- !x! CANCEL_HALT OFF\n"
            + DISPLAY
            + "-- !x! ASSERT DIALOG_CANCELED()\n"
            + DISPLAY
            + "-- !x! ASSERT NOT DIALOG_CANCELED()\n"
            + DISPLAY
            + "-- !x! RESET DIALOG_CANCELED\n"
            "-- !x! ASSERT NOT DIALOG_CANCELED()\n"
        ),
        connection=database,
    )
    assert result.success, result.errors


def test_pause_quit_records_cancellation_without_halting(database, transport):
    transport.return_value = {"quit": True}
    result = run(
        sql=(
            '-- !x! CANCEL_HALT OFF\n-- !x! PROMPT PAUSE "Wait"\n'
            "-- !x! ASSERT DIALOG_CANCELED()\n"
            "insert into events values ('continued');\n"
        ),
        connection=database,
    )
    assert result.success, result.errors
    assert database.conn.execute("select * from events").fetchall() == [("continued",)]


def test_cancel_halt_runs_cleanup_once_after_rolling_back_batch(database, transport):
    transport.return_value = {"button": None, "cancelled": True}
    result = run(
        sql=(
            "-- !x! BEGIN SCRIPT cleanup\n"
            "insert into events values ('cleanup');\n"
            "-- !x! END SCRIPT\n"
            "-- !x! ON CANCEL_HALT EXECUTE SCRIPT cleanup\n"
            "-- !x! BEGIN BATCH\n"
            "insert into events values ('unconfirmed');\n" + DISPLAY + "insert into events values ('unreachable');\n"
            "-- !x! END BATCH\n"
        ),
        connection=database,
    )
    assert not result.success
    assert database.conn.execute("select * from events").fetchall() == [("cleanup",)]


@pytest.mark.parametrize("halt", ["ON", "OFF"])
def test_message_cancel_obeys_the_script_policy(database, transport, halt):
    transport.return_value = {"button": None, "cancelled": True}
    result = run(
        sql=(
            f"-- !x! CANCEL_HALT {halt}\n-- !x! PROMPT MESSAGE \"Notice\"\ninsert into events values ('continued');\n"
        ),
        connection=database,
    )
    assert result.success is (halt == "OFF"), result.errors
    expected = [("continued",)] if halt == "OFF" else []
    assert database.conn.execute("select * from events").fetchall() == expected


@pytest.mark.parametrize("operation", ["display", "openfile", "savefile", "directory", "entry", "form", "pause"])
@pytest.mark.parametrize("gesture", ["escape", "cancel"])
def test_textual_cancel_reaches_the_handler(database, monkeypatch, operation, gesture):
    pytest.importorskip("textual")
    from execsql.gui.tui import _SingleDialogApp, _TextualSyncQueue

    def headless_run(app):
        async def interact():
            async with app.run_test() as pilot:
                await pilot.pause()
                if gesture == "escape":
                    await pilot.press("escape")
                else:
                    button = "btn_cancel" if operation in ("openfile", "savefile", "directory") else "btn_cancel_exit"
                    assert await pilot.click(f"#{button}")
                await pilot.pause()
            return app.return_value

        return asyncio.run(interact())

    monkeypatch.setattr(_SingleDialogApp, "run", headless_run)
    manager = _TextualSyncQueue()
    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", manager))
    commands = {
        "display": DISPLAY,
        "openfile": "-- !x! PROMPT OPENFILE SUB chosen\n",
        "savefile": "-- !x! PROMPT SAVEFILE SUB chosen\n",
        "directory": "-- !x! PROMPT DIRECTORY SUB chosen\n",
        "entry": '-- !x! PROMPT ENTER_SUB chosen MESSAGE "Value"\n',
        "form": '-- !x! PROMPT ENTRY_FORM form_spec MESSAGE "Values"\n',
        "pause": '-- !x! PROMPT PAUSE "Wait"\n',
    }
    result = run(
        sql="-- !x! CANCEL_HALT OFF\n" + commands[operation] + "insert into events values ('continued');\n",
        connection=database,
        variables={"chosen": "unchanged"},
    )
    assert result.success, result.errors
    assert result.variables["chosen"] == "unchanged"
    assert database.conn.execute("select * from events").fetchall() == [("continued",)]


def test_persistent_textual_escape_continues_the_real_script_worker(database, monkeypatch):
    pytest.importorskip("textual")
    from execsql.gui.tui import ConsoleApp, DisplayScreen, _ConsoleDialogQueue

    dialog_queue = _ConsoleDialogQueue()
    results = queue.Queue()
    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", dialog_queue))

    def execute():
        results.put(
            run(
                sql="-- !x! CANCEL_HALT OFF\n" + DISPLAY + "insert into events values ('continued');\n",
                dsn=f"sqlite:///{database.db_name}",
            ),
        )

    app = ConsoleApp(execute, dialog_queue)

    async def interact():
        async with app.run_test() as pilot:
            for _ in range(100):
                if isinstance(app.screen, DisplayScreen):
                    break
                await pilot.pause(0.01)
            assert isinstance(app.screen, DisplayScreen)
            await pilot.press("escape")
            for _ in range(100):
                if not results.empty():
                    break
                await pilot.pause(0.01)
            assert not results.empty()

    asyncio.run(interact())
    app._script_thread.join(2)
    assert not app._script_thread.is_alive()
    result = results.get_nowait()
    assert result.success, result.errors
    assert database.conn.execute("select * from events").fetchall() == [("continued",)]
