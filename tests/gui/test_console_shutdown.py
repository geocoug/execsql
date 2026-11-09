"""Console shutdown must wait for the script worker and its rollback."""

from __future__ import annotations

import asyncio
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("textual")

from execsql import state  # noqa: E402
from execsql.cli.run import _execute_script_textual_console  # noqa: E402
from execsql.exceptions import ScriptExit  # noqa: E402
from execsql.gui.tui import ConsoleApp, DisplayScreen, _ConsoleDialogQueue  # noqa: E402
from execsql.utils.gui import GUI_DISPLAY, GuiSpec, get_gui_response  # noqa: E402


async def eventually(pilot, predicate):
    async def wait():
        while not predicate():
            await pilot.pause(0.01)

    try:
        await asyncio.wait_for(wait(), timeout=10)
    except asyncio.TimeoutError:
        raise AssertionError("Timed out waiting for a deterministic worker state") from None


@pytest.mark.parametrize("wait_on_exit", [False, True])
def test_quit_keeps_ui_alive_until_blocked_work_and_cleanup_finish(wait_on_exit):
    from execsql.gui import tui
    from textual.widgets import Label

    entered, work, cleaning, cleanup, finished = (threading.Event() for _ in range(5))

    def runner():
        entered.set()
        try:
            work.wait(20)
        finally:
            cleaning.set()
            cleanup.wait(20)
            finished.set()

    app = ConsoleApp(runner, _ConsoleDialogQueue(), wait_on_exit=wait_on_exit)

    async def interact():
        async with app.run_test() as pilot:
            try:
                await eventually(pilot, entered.is_set)
                with patch.object(
                    tui.ctypes.pythonapi,
                    "PyThreadState_SetAsyncExc",
                    wraps=tui.ctypes.pythonapi.PyThreadState_SetAsyncExc,
                ) as inject:
                    await pilot.press("ctrl+c", "ctrl+c")
                    assert not app._exit
                    assert app._script_thread.is_alive()
                    assert "Stopping" in str(app.query_one("#status_bar", Label).render())
                    assert inject.call_count == 1
                    work.set()
                    await eventually(pilot, cleaning.is_set)
                    await pilot.press("ctrl+c")
                    assert inject.call_count == 1
                    assert not finished.is_set() and not app._exit
                    cleanup.set()
                    await eventually(pilot, lambda: not app._script_thread.is_alive())
                    await eventually(pilot, lambda: app._exit)
                    assert finished.is_set()
            finally:
                work.set()
                cleanup.set()
                await eventually(pilot, lambda: not app._script_thread.is_alive())

    asyncio.run(interact())
    assert isinstance(app._script_exception, SystemExit)


def test_quit_releases_pending_dialog_without_injecting_or_late_reply():
    from execsql.gui import tui

    dialogs = _ConsoleDialogQueue()
    replies = queue.Queue()
    spec = GuiSpec(GUI_DISPLAY, {"textentry": True, "button_list": [("OK", 1)]}, replies)
    cleaned = threading.Event()

    def runner():
        try:
            dialogs.put(spec)
            get_gui_response(replies, GUI_DISPLAY)
        finally:
            cleaned.set()

    app = ConsoleApp(runner, dialogs)

    async def interact():
        async with app.run_test() as pilot:
            try:
                await eventually(pilot, lambda: isinstance(app.screen, DisplayScreen))
                with patch.object(
                    tui.ctypes.pythonapi,
                    "PyThreadState_SetAsyncExc",
                    wraps=tui.ctypes.pythonapi.PyThreadState_SetAsyncExc,
                ) as inject:
                    await pilot.press("ctrl+c")
                    await eventually(pilot, cleaned.is_set)
                    await eventually(pilot, lambda: not app._script_thread.is_alive())
                    assert not inject.called
                    assert replies.empty()
            finally:
                replies.put({"interrupted": True})
                await eventually(pilot, lambda: not app._script_thread.is_alive())

    asyncio.run(interact())
    assert isinstance(app._script_exception, KeyboardInterrupt)


def test_shutdown_queue_interrupts_pending_and_future_requests_once():
    dialogs = _ConsoleDialogQueue()
    spec = GuiSpec(GUI_DISPLAY, {}, queue.Queue())
    dialogs.put(spec)
    assert dialogs.get_nowait() is spec
    assert dialogs.interrupt()
    with pytest.raises(KeyboardInterrupt):
        get_gui_response(spec.return_queue, GUI_DISPLAY)
    dialogs.reply(spec, {"button": 1})
    assert spec.return_queue.empty()
    late = GuiSpec(GUI_DISPLAY, {}, queue.Queue())
    dialogs.put(late)
    with pytest.raises(KeyboardInterrupt):
        get_gui_response(late.return_queue, GUI_DISPLAY)
    with pytest.raises(queue.Empty):
        dialogs.get_nowait()


@pytest.mark.parametrize("wait_on_exit", [False, True])
def test_finishing_normally_then_closing_does_not_become_an_interrupt(wait_on_exit):
    app = ConsoleApp(lambda: None, _ConsoleDialogQueue(), wait_on_exit=wait_on_exit)

    async def interact():
        async with app.run_test() as pilot:
            await eventually(pilot, lambda: app._script_thread is not None and not app._script_thread.is_alive())
            if wait_on_exit:
                assert not app._exit
                await pilot.press("ctrl+c")
            await eventually(pilot, lambda: app._exit)

    asyncio.run(interact())
    assert app._script_exception is None
    assert not app._quit_requested


def test_cli_waits_for_worker_rollback_before_reset_and_interrupted_exit(monkeypatch, minimal_conf):
    from execsql.gui import tui

    entered, work, cleaning, cleanup = (threading.Event() for _ in range(4))
    events = []
    db = Mock(autocommit=True)
    expected_ctx = state.get_context()

    def rollback():
        assert state.get_context() is expected_ctx
        cleaning.set()
        cleanup.wait(20)
        events.append("rollback")

    db.rollback.side_effect = rollback
    pool = Mock(do_rollback=True)
    pool.aliases.return_value = ["initial"]
    pool.aliased_as.return_value = db
    state.dbs = pool
    state.output = Mock()
    state.output.reset.side_effect = lambda: events.append("reset")
    state.exec_log = Mock()
    minimal_conf.gui_wait_on_exit = False
    monkeypatch.setattr("execsql.utils.gui._active_backend", SimpleNamespace(_console_app=None))

    def execute(tree, *, ctx):
        assert ctx is expected_ctx
        entered.set()
        work.wait(20)

    monkeypatch.setattr("execsql.script.executor.execute", execute)

    def headless(app):
        async def interact():
            async with app.run_test() as pilot:
                try:
                    await eventually(pilot, entered.is_set)
                    app.action_request_quit()
                    assert not app._exit
                    state.output.reset.assert_not_called()
                    assert pool.do_rollback
                    state.exec_log.log_exit_end.assert_not_called()
                    work.set()
                    await eventually(pilot, cleaning.is_set)
                    assert not app._exit
                    state.output.reset.assert_not_called()
                    cleanup.set()
                    await eventually(pilot, lambda: not app._script_thread.is_alive())
                    await eventually(pilot, lambda: app._exit)
                finally:
                    work.set()
                    cleanup.set()
                    await eventually(pilot, lambda: not app._script_thread.is_alive())

        return asyncio.run(interact())

    monkeypatch.setattr(tui.ConsoleApp, "run", headless)
    with pytest.raises(SystemExit) as stopped:
        _execute_script_textual_console(object(), minimal_conf)
    assert stopped.value.code == 130
    assert events == ["rollback", "reset"]
    assert pool.do_rollback
    state.exec_log.log_exit_interrupted.assert_called_once()
    state.exec_log.log_exit_end.assert_not_called()


@pytest.mark.parametrize("halt", [False, True])
def test_cli_preserves_normal_completion_and_script_halt(monkeypatch, minimal_conf, halt):
    from execsql.gui import tui

    state.dbs = Mock(do_rollback=True)
    state.output = Mock()
    state.exec_log = Mock()
    minimal_conf.gui_wait_on_exit = False
    monkeypatch.setattr("execsql.utils.gui._active_backend", SimpleNamespace(_console_app=None))

    def execute(tree, *, ctx):
        if halt:
            raise ScriptExit(7)

    monkeypatch.setattr("execsql.script.executor.execute", execute)

    def headless(app):
        async def interact():
            async with app.run_test() as pilot:
                await eventually(pilot, lambda: app._exit)
            assert not app._script_thread.is_alive()

        return asyncio.run(interact())

    monkeypatch.setattr(tui.ConsoleApp, "run", headless)
    if halt:
        with pytest.raises(SystemExit) as stopped:
            _execute_script_textual_console(object(), minimal_conf)
        assert stopped.value.code == 7
        assert state.dbs.do_rollback
        state.exec_log.log_exit_end.assert_not_called()
    else:
        monkeypatch.setattr("execsql.cli.run._flush_output_files", Mock())
        _execute_script_textual_console(object(), minimal_conf)
        assert not state.dbs.do_rollback
        state.exec_log.log_exit_end.assert_called_once()
    state.exec_log.log_exit_interrupted.assert_not_called()


def test_unmount_releases_dialog_and_keeps_loop_for_cleanup_output():
    dialogs = _ConsoleDialogQueue()
    spec = GuiSpec(GUI_DISPLAY, {"button_list": [("OK", 1)]}, queue.Queue())
    cleaned = threading.Event()

    def runner():
        try:
            dialogs.put(spec)
            get_gui_response(spec.return_queue, GUI_DISPLAY)
        finally:
            app.write_console("cleanup finished")
            cleaned.set()

    app = ConsoleApp(runner, dialogs)

    async def interact():
        async with app.run_test() as pilot:
            await eventually(pilot, lambda: isinstance(app.screen, DisplayScreen))

    asyncio.run(interact())
    assert cleaned.is_set()
    assert not app._script_thread.is_alive()
    assert isinstance(app._script_exception, KeyboardInterrupt)
    assert app._console_lines == ["cleanup finished"]


def test_real_script_rolls_back_before_quit_closes_console(monkeypatch, tmp_path):
    import sqlite3
    from execsql import run
    from execsql.db.sqlite import SQLiteDatabase
    from execsql.metacommands import prompt

    path = tmp_path / "shutdown.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "create table events (value text); create table source(id integer); insert into source values(1);",
        )
    dialogs = _ConsoleDialogQueue()
    cleaning, release, rolled_back = (threading.Event() for _ in range(3))
    original_rollback = SQLiteDatabase.rollback

    def rollback(db):
        cleaning.set()
        release.wait(20)
        original_rollback(db)
        rolled_back.set()

    monkeypatch.setattr(SQLiteDatabase, "rollback", rollback)
    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", dialogs))

    def runner():
        run(
            sql="-- !x! BEGIN BATCH\ninsert into events values ('pending');\n"
            '-- !x! PROMPT DISPLAY source MESSAGE "Confirm"\n-- !x! END BATCH\n',
            dsn=f"sqlite:///{path}",
        )

    app = ConsoleApp(runner, dialogs, wait_on_exit=True)

    async def interact():
        async with app.run_test() as pilot:
            try:
                await eventually(pilot, lambda: isinstance(app.screen, DisplayScreen))
                await pilot.press("ctrl+c")
                await eventually(pilot, cleaning.is_set)
                await pilot.press("ctrl+c")
                assert not app._exit and not rolled_back.is_set()
                release.set()
                await eventually(pilot, lambda: not app._script_thread.is_alive())
                await eventually(pilot, lambda: app._exit)
            finally:
                release.set()
                if app._script_thread.is_alive() and not app._quit_requested:
                    app.action_request_quit()
                await eventually(pilot, lambda: not app._script_thread.is_alive())

    asyncio.run(interact())
    assert rolled_back.is_set()
    assert isinstance(app._script_exception, KeyboardInterrupt)
    with sqlite3.connect(path) as conn:
        assert conn.execute("select * from events").fetchall() == []
