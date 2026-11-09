"""Exercise SQLite ownership through the actual persistent-console CLI."""

from __future__ import annotations

import asyncio
import functools
import sqlite3
import threading

import pytest
from typer.testing import CliRunner

pytest.importorskip("textual")

from execsql.cli import app as cli  # noqa: E402
from execsql.db.sqlite import SQLiteDatabase  # noqa: E402
from execsql.gui.tui import ActionScreen, ConnectScreen, ConsoleApp, DisplayScreen, MsgScreen  # noqa: E402


@pytest.fixture
def console_cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("execsql.utils.gui._active_backend", None)
    monkeypatch.setattr("execsql.utils.gui._console_running", False)
    callbacks = []
    operations = []
    connections = []
    main_thread = threading.get_ident()

    def register(fn, *args, **kwargs):
        callbacks.append(functools.partial(fn, *args, **kwargs))
        return fn

    monkeypatch.setattr("atexit.register", register)
    for name in ("open_db", "execute", "rollback", "close"):
        original = getattr(SQLiteDatabase, name)

        def record(db, *args, _name=name, _original=original, **kwargs):
            operations.append((_name, threading.get_ident()))
            result = _original(db, *args, **kwargs)
            if _name == "open_db":
                connections.append(db)
            return result

        monkeypatch.setattr(SQLiteDatabase, name, record)

    def invoke(sql, *, dsn=None, interrupt=False, connect=None, cancel=False, close_gate=None):
        config = tmp_path / "console.conf"
        config.write_text("[interface]\nconsole_wait_when_done=No\nconsole_wait_when_error_halt=No\n")

        def headless(app):
            async def interact():
                async with app.run_test(size=(100, 40)) as pilot:
                    for _ in range(400):
                        if app._exit:
                            break
                        if close_gate is not None and close_gate[0].is_set():
                            app.action_request_quit()
                            close_gate[1].set()
                        if isinstance(app.screen, ConnectScreen):
                            await pilot.pause()
                            if cancel:
                                await pilot.click("#btn_cancel")
                            elif connect is not None:
                                from textual.widgets import Input, Select

                                app.screen.query_one("#db_type_select", Select).value = "l"
                                app.screen.query_one("#database_input", Input).value = str(connect)
                                await pilot.pause()
                                await pilot.click("#btn_ok")
                        elif isinstance(app.screen, MsgScreen) and app.screen.query("#btn_0"):
                            await pilot.click("#btn_0")
                        elif isinstance(app.screen, ActionScreen) and app.screen.query("#action_0"):
                            await pilot.pause()
                            await pilot.click("#action_0")
                        elif interrupt and isinstance(app.screen, DisplayScreen):
                            app.action_request_quit()
                        await pilot.pause(0.01)
                    assert app._exit, "Console did not finish"
                assert not app._script_thread.is_alive()

            asyncio.run(interact())

        monkeypatch.setattr(ConsoleApp, "run", headless)
        args = ["run", "--config", str(config), "-v3", "--gui-framework", "textual", "-c", sql]
        if dsn is not None:
            args.extend(["--dsn", dsn])
        result = CliRunner().invoke(cli, args)
        # Simulate process cleanup on the main thread as well as worker cleanup.
        for callback in reversed(callbacks):
            callback()
        return result

    yield invoke, operations, connections, main_thread


@pytest.mark.parametrize("memory", [True, False])
def test_initial_sqlite_connection_is_created_used_and_closed_on_worker(console_cli, tmp_path, memory):
    invoke, operations, connections, main_thread = console_cli
    path = ":memory:" if memory else str(tmp_path / "initial.sqlite")
    if not memory:
        sqlite3.connect(path).close()
    result = invoke("create table t(n integer);\ninsert into t values(42);", dsn=f"sqlite:///{path}")
    assert result.exit_code == 0, (result.output, result.exception)
    assert {name for name, _ in operations} >= {"open_db", "execute", "close"}
    owners = {thread for _, thread in operations}
    assert len(owners) == 1 and main_thread not in owners
    assert all(db.conn is None for db in connections)
    if not memory:
        with sqlite3.connect(path) as conn:
            assert conn.execute("select * from t").fetchall() == [(42,)]


@pytest.mark.parametrize("prompt", [False, True])
def test_runtime_sqlite_alias_is_closed_on_its_worker(console_cli, tmp_path, prompt):
    invoke, operations, connections, main_thread = console_cli
    path = tmp_path / "alias.sqlite"
    if prompt:
        sqlite3.connect(path).close()
    connect = (
        "-- !x! PROMPT CONNECT AS other\n"
        if prompt
        else f'-- !x! CONNECT TO SQLITE(FILE="{path.as_posix()}", NEW) AS other\n'
    )
    result = invoke(
        connect + "-- !x! USE other\ncreate table t(n integer);\ninsert into t values(7);",
        dsn="sqlite:///:memory:",
        connect=path if prompt else None,
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert len(connections) == 2
    assert len({thread for _, thread in operations}) == 1
    assert main_thread not in {thread for _, thread in operations}
    assert all(db.conn is None for db in connections)
    with sqlite3.connect(path) as conn:
        assert conn.execute("select * from t").fetchall() == [(7,)]


@pytest.mark.parametrize(
    "ending,code",
    [("-- !x! HALT EXIT_STATUS 7\n", 7), ("select * from missing;", 1), ("quit", 130)],
)
def test_failed_or_interrupted_script_rolls_back_and_closes_on_worker(console_cli, tmp_path, ending, code):
    invoke, operations, connections, main_thread = console_cli
    path = tmp_path / "rollback.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("create table t(n integer)")
    sql = "-- !x! BEGIN BATCH\ninsert into t values(99);\n"
    sql += '-- !x! PROMPT DISPLAY t MESSAGE "Waiting"\n' if ending == "quit" else ending
    sql += "\n-- !x! END BATCH\n"
    result = invoke(sql, dsn=f"sqlite:///{path}", interrupt=ending == "quit")
    assert result.exit_code == code, (result.output, result.exception)
    assert "rollback" in {name for name, _ in operations}
    assert len({thread for _, thread in operations}) == 1
    assert main_thread not in {thread for _, thread in operations}
    assert all(db.conn is None for db in connections)
    with sqlite3.connect(path) as conn:
        assert conn.execute("select * from t").fetchall() == []


@pytest.mark.parametrize("cancel", [False, True])
def test_initial_connection_dialog_runs_before_worker_sql(console_cli, tmp_path, cancel):
    invoke, operations, connections, main_thread = console_cli
    path = tmp_path / "chosen.sqlite"
    sqlite3.connect(path).close()
    result = invoke("create table chosen(n integer);", connect=path, cancel=cancel)
    assert result.exit_code == (1 if cancel else 0), (result.output, result.exception)
    assert all(thread != main_thread for _, thread in operations)
    assert all(db.conn is None for db in connections)
    if not cancel:
        with sqlite3.connect(path) as conn:
            assert conn.execute("select * from chosen").fetchall() == []


def test_initial_connection_failure_exits_without_waiting_for_a_closed_console(console_cli, tmp_path):
    invoke, operations, _, _ = console_cli
    result = invoke("select 1;", dsn=f"sqlite:///{tmp_path / 'missing' / 'db.sqlite'}")
    assert result.exit_code == 1, (result.output, result.exception)
    assert not operations


@pytest.mark.parametrize("action", [False, True])
@pytest.mark.parametrize("unexpected", [False, True])
def test_fatal_error_runs_cleanup_before_worker_connections_close(
    console_cli,
    monkeypatch,
    tmp_path,
    action,
    unexpected,
):
    invoke, operations, connections, main_thread = console_cli
    path = tmp_path / "fatal.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "create table marker (value text);"
            "create table actions (sequence integer, label text, prompt text, script text, data_required boolean);"
            "insert into actions values (1, 'Run', 'Run failing script', 'failing', 0);",
        )
    if unexpected:

        def fail_condition(*args, **kwargs):
            raise RuntimeError("condition engine failed")

        monkeypatch.setattr("execsql.script.executor._condition_holds", fail_condition)
    command = '-- !x! PROMPT ACTION actions MESSAGE "Choose"\n' if action else "-- !x! EXECUTE SCRIPT failing\n"
    result = invoke(
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! ON ERROR_HALT EXECUTE SCRIPT failed\n"
        "-- !x! BEGIN SCRIPT failed\ninsert into marker values ('cleanup');\n-- !x! END SCRIPT\n"
        "-- !x! BEGIN SCRIPT failing\n-- !x! IF (HAS_ROWZ(marker))\n-- !x! ENDIF\n-- !x! END SCRIPT\n"
        "-- !x! BEGIN BATCH\ninsert into marker values ('pending');\n"
        + command
        + "-- !x! END BATCH\ninsert into marker values ('continued');\n",
        dsn=f"sqlite:///{path}",
    )
    assert result.exit_code == 1, (result.output, result.exception)
    assert isinstance(result.exception, SystemExit), (result.output, result.exception)
    from execsql import state

    message = "condition engine failed" if unexpected else "Unknown condition test"
    assert message in state.halt_error.errmsg()
    assert len({thread for _, thread in operations}) == 1
    assert main_thread not in {thread for _, thread in operations}
    assert all(db.conn is None for db in connections)
    with sqlite3.connect(path) as conn:
        assert conn.execute("select * from marker").fetchall() == [("cleanup",)]


def test_quit_during_connection_cleanup_finishes_on_worker(console_cli, monkeypatch, tmp_path):
    invoke, operations, connections, main_thread = console_cli
    entered, release = threading.Event(), threading.Event()
    original = SQLiteDatabase.close

    def close(db):
        if not entered.is_set():
            entered.set()
            assert release.wait(20)
        original(db)

    monkeypatch.setattr(SQLiteDatabase, "close", close)
    try:
        result = invoke(
            f'-- !x! CONNECT TO SQLITE(FILE="{(tmp_path / "other.sqlite").as_posix()}", NEW) AS other\nselect 1;',
            dsn="sqlite:///:memory:",
            close_gate=(entered, release),
        )
    finally:
        release.set()
    assert result.exit_code == 130, (result.output, result.exception)
    assert entered.is_set()
    assert len(connections) == 2
    assert all(thread != main_thread for _, thread in operations)
    assert all(db.conn is None for db in connections)
