"""Action dialog choices must run the configured SCRIPT with the right data."""

from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from execsql import run, state
from execsql.db.sqlite import SQLiteDatabase
from execsql.metacommands import prompt

COMMAND = '-- !x! PROMPT ACTION actions MESSAGE "Choose" DISPLAY source CONTINUE\n'
SCRIPTS = """
-- !x! BEGIN SCRIPT selected
-- !x! SUB seen_id !!@id!!
-- !x! SUB seen_name [!!@name!!]
-- !x! SUB seen_note [!!@note!!]
insert into marker values ('selected');
-- !x! END SCRIPT
-- !x! BEGIN SCRIPT standalone
-- !x! SUB seen_id !!@id!!
-- !x! SUB seen_name [!!@name!!]
-- !x! SUB seen_note [!!@note!!]
insert into marker values ('standalone');
-- !x! END SCRIPT
"""


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "actions.db"))
    db.conn.executescript(
        "create table source (id integer, name text, note text);"
        "insert into source values (1, 'first', 'value'), (1152921504606846976, 'O''Brien', NULL);"
        "create table previous as select 0 as id, 'old' as name, 'old' as note;"
        "create table marker (action text);"
        "create table actions (sequence integer, label text, prompt text, script text, data_required boolean);"
        "insert into actions values (2, 'Plain', 'No data needed', 'standalone', 0),"
        "(1, 'Row', 'Use selected data', 'selected', 1);",
    )
    yield db
    db.close()


@pytest.fixture(params=["console", "textual", "tk"])
def selector(request, monkeypatch):
    choice = SimpleNamespace(kind="selected", received=[])
    if request.param == "console":
        from execsql.gui.console import ConsoleBackend

        native = ConsoleBackend()
        answers = None

        def answer(*args):
            nonlocal answers
            if choice.received[-1] == "msg":
                return "1"
            if answers is None:
                answers = list(
                    {
                        "selected": ["r 2", "1"],
                        "standalone": ["r 2", "2"],
                        "guard": ["1", "2"],
                        "continue": ["0"],
                        "cancel": [""],
                    }[choice.kind],
                )
            assert answers, "Unexpected extra action input"
            return answers.pop(0)

        monkeypatch.setattr("builtins.input", answer)

        class Manager:
            def put(self, spec):
                choice.received.append(spec.gui_type)
                spec.return_queue.put(native.dispatch(spec))

        manager = Manager()
    elif request.param == "textual":
        pytest.importorskip("textual")
        from textual.widgets import Button, DataTable

        from execsql.gui.tui import ActionScreen, _SingleDialogApp, _TextualSyncQueue

        def headless(app):
            async def interact():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    if not isinstance(app.screen, ActionScreen):
                        await pilot.click("#btn_0")
                    else:
                        assert app.screen.query_one("#action_0", Button).disabled
                        if choice.kind in ("selected", "standalone", "keyboard"):
                            if choice.kind == "keyboard":
                                app.screen.query_one("#action_table", DataTable).focus()
                                await pilot.press("down")
                            else:
                                assert await pilot.click("#action_table", offset=(2, 2))
                            await pilot.pause()
                            assert not app.screen.query_one("#action_0", Button).disabled
                        elif choice.kind == "guard":
                            await pilot.click("#action_0")
                            assert isinstance(app.screen, ActionScreen)
                        if choice.kind == "cancel":
                            await pilot.press("escape")
                        else:
                            button = {
                                "selected": "action_0",
                                "keyboard": "action_0",
                                "standalone": "action_1",
                                "guard": "action_1",
                                "continue": "action_continue",
                            }[choice.kind]
                            assert await pilot.click(f"#{button}")
                    await pilot.pause()
                return app.return_value

            return asyncio.run(interact())

        monkeypatch.setattr(_SingleDialogApp, "run", headless)
        native = _TextualSyncQueue()

        class Manager:
            def put(self, spec):
                choice.received.append(spec.gui_type)
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
        tree = _mk_widget()
        tree.get_children.return_value = ("first", "second")
        tree.selection.return_value = ()
        tree.item.side_effect = AssertionError("Do not reconstruct action data from displayed strings")
        ttk.Treeview.side_effect = None
        ttk.Treeview.return_value = tree

        def interact(win):
            calls = ttk.Button.call_args_list + tk.Button.call_args_list

            def button(label):
                return next(c for c in calls if c.kwargs.get("text", "").split("\n")[0] == label)

            if choice.received[-1] != "action":
                button("Close").kwargs["command"]()
                return
            required = button("Row")
            assert required.kwargs.get("state") == "disabled"
            if choice.kind in ("selected", "standalone"):
                tree.selection.return_value = ("second",)
                next(c.args[1] for c in tree.bind.call_args_list if c.args[0] == "<<TreeviewSelect>>")(None)
            elif choice.kind == "guard":
                required.kwargs["command"]()
                win.destroy.assert_not_called()
            if choice.kind == "cancel":
                next(c.args[1] for c in win.bind.call_args_list if c.args[0] == "<Escape>")(None)
            else:
                label = {"selected": "Row", "standalone": "Plain", "guard": "Plain", "continue": "Continue"}[
                    choice.kind
                ]
                button(label).kwargs["command"]()

        root.wait_window.side_effect = interact
        backend = desktop.TkinterBackend()
        backend._root = root
        native = desktop._TkinterSyncQueue(backend)

        class Manager:
            def put(self, spec):
                choice.received.append(spec.gui_type)
                native.put(spec)

        manager = Manager()
    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", manager))
    return choice


@pytest.mark.parametrize("kind", ["selected", "standalone", "continue", "cancel", "guard"])
def test_actual_action_choice_has_exactly_the_documented_effect(database, selector, kind):
    selector.kind = kind
    result = run(
        sql=(
            "-- !x! CANCEL_HALT OFF\n-- !x! SELECT_SUB previous\n"
            + COMMAND
            + "-- !x! SUB after_name [!!@name!!]\n-- !x! SUB main_after yes\n"
            + SCRIPTS
        ),
        connection=database,
    )
    assert result.success, result.errors
    expected_action = "standalone" if kind == "guard" else kind
    markers = [(expected_action,)] if kind in ("selected", "standalone", "guard") else []
    assert database.conn.execute("select * from marker").fetchall() == markers
    if markers:
        assert result.variables["seen_id"] == ("1152921504606846976" if kind == "selected" else "0")
        assert result.variables["seen_name"] == ("[O'Brien]" if kind == "selected" else "[old]")
        assert result.variables["seen_note"] == ("[]" if kind == "selected" else "[old]")
    assert result.variables["after_name"] == ("[O'Brien]" if kind == "selected" else "[old]")
    assert result.variables["main_after"] == "yes"


def test_action_sql_obeys_held_transaction(database, selector):
    selector.kind = "standalone"
    result = run(sql="-- !x! AUTOCOMMIT OFF\n-- !x! SELECT_SUB previous\n" + SCRIPTS + COMMAND, connection=database)
    assert result.success, result.errors
    assert database.conn.execute("select * from marker").fetchall() == [("standalone",)]
    assert database.conn.in_transaction
    with sqlite3.connect(database.db_name) as observer:
        assert observer.execute("select * from marker").fetchall() == []
    database.conn.rollback()


@pytest.mark.parametrize("selector", ["textual"], indirect=True)
def test_keyboard_selection_supplies_action_data(database, selector):
    selector.kind = "keyboard"
    result = run(sql=SCRIPTS + COMMAND, connection=database)
    assert result.success, result.errors
    assert database.conn.execute("select * from marker").fetchall() == [("selected",)]
    assert result.variables["seen_id"] == "1152921504606846976"
    assert result.variables["seen_name"] == "[O'Brien]"
    assert result.variables["seen_note"] == "[]"


def test_action_script_can_open_another_dialog(database, selector):
    selector.kind = "standalone"
    script = "-- !x! BEGIN SCRIPT standalone\n-- !x! PROMPT MESSAGE \"Nested\"\ninsert into marker values ('nested');\n-- !x! END SCRIPT\n"
    result = run(sql=script + COMMAND, connection=database)
    assert result.success, result.errors
    assert database.conn.execute("select * from marker").fetchall() == [("nested",)]
    assert selector.received == ["action", "msg"]


def test_cancel_halt_does_not_run_an_action(database, selector):
    selector.kind = "cancel"
    result = run(sql=SCRIPTS + COMMAND + "-- !x! SUB unreachable yes\n", connection=database)
    assert not result.success
    assert any("exit status 2" in e.message for e in result.errors)
    assert database.conn.execute("select * from marker").fetchall() == []
    assert "unreachable" not in result.variables


def test_failed_action_sql_fails_the_enclosing_batch(database, selector):
    selector.kind = "standalone"
    script = """
-- !x! BEGIN SCRIPT standalone
insert into marker values ('inside');
insert into missing_table values (1);
insert into marker values ('after failure');
-- !x! END SCRIPT
-- !x! ERROR_HALT OFF
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! BEGIN BATCH
insert into marker values ('before');
"""
    result = run(
        sql=script + COMMAND + "-- !x! END BATCH\ninsert into marker values ('outside');\n",
        connection=database,
    )
    assert not result.success
    assert any(e.sql and "missing_table" in e.sql for e in result.errors)
    assert database.conn.execute("select * from marker").fetchall() == [("outside",)]


@pytest.mark.parametrize("failure", ["missing", "required", "blank"])
def test_invalid_action_target_does_not_replace_old_data_variables(database, selector, failure):
    selector.kind = "selected"
    scripts = SCRIPTS
    if failure == "required":
        scripts = scripts.replace("BEGIN SCRIPT selected", "BEGIN SCRIPT selected WITH PARAMETERS (needed)")
        expected = "missing required parameter"
    else:
        database.conn.execute(
            "update actions set script = ? where sequence = 1",
            ("missing" if failure == "missing" else None,),
        )
        database.conn.commit()
        expected = "script named missing" if failure == "missing" else "script name is required"
    result = run(
        sql=(
            "-- !x! SELECT_SUB previous\n-- !x! METACOMMAND_ERROR_HALT OFF\n"
            + scripts
            + COMMAND
            + "-- !x! SUB after_name [!!@name!!]\n"
        ),
        connection=database,
    )
    assert not result.success
    assert any(expected in e.message.lower() for e in result.errors)
    assert database.conn.execute("select * from marker").fetchall() == []
    assert result.variables["after_name"] == "[old]"


def test_action_uses_script_frames_nested_calls_and_break(database, selector):
    selector.kind = "standalone"
    scripts = """
-- !x! BEGIN SCRIPT standalone
-- !x! SUB_LOCAL scratch scoped
-- !x! EXECUTE SCRIPT inner
-- !x! BREAK
insert into marker values ('unreachable');
-- !x! END SCRIPT
-- !x! BEGIN SCRIPT inner
insert into marker values ('nested');
-- !x! END SCRIPT
"""
    result = run(
        sql=scripts + COMMAND + "-- !x! ASSERT NOT SUB_DEFINED(~scratch)\n-- !x! SUB main_after yes\n",
        connection=database,
    )
    assert result.success, result.errors
    assert database.conn.execute("select * from marker").fetchall() == [("nested",)]
    assert result.variables["main_after"] == "yes"


@pytest.mark.parametrize("empty_display", [False, True])
def test_data_required_action_cannot_run_without_display_data(database, selector, empty_display):
    selector.kind = "guard"
    command = COMMAND
    if empty_display:
        database.conn.execute("delete from source")
        database.conn.commit()
    else:
        command = command.replace(" DISPLAY source", "")
    result = run(sql="-- !x! SELECT_SUB previous\n" + SCRIPTS + command, connection=database)
    assert result.success, result.errors
    assert database.conn.execute("select * from marker").fetchall() == [("standalone",)]
    assert result.variables["seen_name"] == "[old]"


@pytest.mark.parametrize("invocation", ["action", "execute"])
@pytest.mark.parametrize(
    ("body", "message", "cleanup"),
    [
        pytest.param("-- !x! IF (HASROWS(missing_table))\n-- !x! ENDIF\n", "missing_table", False, id="database-if"),
        pytest.param("-- !x! IF (HAS_ROWZ(source))\n-- !x! ENDIF\n", "Unknown condition test", False, id="if"),
        pytest.param(
            "-- !x! IF (FALSE)\n-- !x! ELSEIF (HAS_ROWZ(source))\n-- !x! ENDIF\n",
            "Unknown condition test",
            False,
            id="elseif",
        ),
        pytest.param(
            "-- !x! IF (TRUE)\n-- !x! ANDIF (HAS_ROWZ(source))\n-- !x! ENDIF\n",
            "Unknown condition test",
            False,
            id="andif",
        ),
        pytest.param(
            "-- !x! IF (FALSE)\n-- !x! ORIF (HAS_ROWZ(source))\n-- !x! ENDIF\n",
            "Unknown condition test",
            False,
            id="orif",
        ),
        pytest.param(
            "-- !x! LOOP WHILE (HAS_ROWZ(source))\n-- !x! END LOOP\n",
            "Unknown condition test",
            False,
            id="loop",
        ),
        pytest.param("-- !x! ASSERT HAS_ROWZ(source)\n", "Unknown condition test", True, id="assert"),
        pytest.param(
            "-- !x! WAIT_UNTIL HAS_ROWZ(source) CONTINUE AFTER 1 SECONDS\n",
            "Unknown condition test",
            True,
            id="wait-until",
        ),
        pytest.param("-- !x! NO_SUCH_COMMAND\n", "Unknown metacommand", False, id="unknown-command"),
    ],
)
def test_action_preserves_required_script_halts(database, selector, invocation, body, message, cleanup):
    selector.kind = "standalone"
    command = COMMAND if invocation == "action" else "-- !x! EXECUTE SCRIPT standalone\n"
    result = run(
        sql=(
            "-- !x! METACOMMAND_ERROR_HALT OFF\n"
            "-- !x! ON ERROR_HALT EXECUTE SCRIPT failed\n"
            "-- !x! BEGIN SCRIPT failed\ninsert into marker values ('cleanup');\n-- !x! END SCRIPT\n"
            "-- !x! BEGIN SCRIPT standalone\n"
            + body
            + "insert into marker values ('inner continued');\n-- !x! END SCRIPT\n"
            + command
            + "insert into marker values ('caller continued');\n-- !x! SUB reached yes\n"
        ),
        connection=database,
    )
    assert not result.success
    assert len(result.errors) == 1
    assert message in result.errors[0].message
    assert result.errors[0].source == "<inline>"
    assert "reached" not in result.variables
    assert database.conn.execute("select * from marker").fetchall() == ([("cleanup",)] if cleanup else [])


@pytest.mark.parametrize("invocation", ["action", "execute"])
def test_action_preserves_unexpected_script_errors(database, selector, monkeypatch, invocation):
    selector.kind = "standalone"

    def fail_condition(*args, **kwargs):
        raise RuntimeError("script condition engine failed")

    monkeypatch.setattr("execsql.script.executor._condition_holds", fail_condition)
    command = COMMAND if invocation == "action" else "-- !x! EXECUTE SCRIPT standalone\n"
    result = run(
        sql=(
            "-- !x! METACOMMAND_ERROR_HALT OFF\n"
            "-- !x! BEGIN SCRIPT standalone\n-- !x! IF (TRUE)\n-- !x! ENDIF\n-- !x! END SCRIPT\n"
            + command
            + "insert into marker values ('continued');\n"
        ),
        connection=database,
    )
    assert not result.success
    assert len(result.errors) == 1
    assert result.errors[0].message == "script condition engine failed"
    assert result.errors[0].source == "<runtime>"
    assert database.conn.execute("select * from marker").fetchall() == []


@pytest.mark.parametrize("invocation", ["action", "execute"])
def test_cli_action_fatal_condition_rolls_back_before_one_error_cleanup(database, selector, monkeypatch, invocation):
    from typer.testing import CliRunner
    from execsql.cli import app

    selector.kind = "standalone"
    monkeypatch.setattr("execsql.utils.gui._active_backend", None)
    monkeypatch.setattr("execsql.utils.gui._console_running", False)
    command = COMMAND if invocation == "action" else "-- !x! EXECUTE SCRIPT standalone\n"
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! ON ERROR_HALT EXECUTE SCRIPT failed\n"
        "-- !x! BEGIN SCRIPT failed\ninsert into marker values ('cleanup');\n-- !x! END SCRIPT\n"
        "-- !x! BEGIN SCRIPT standalone\n-- !x! IF (HASROWS(missing_table))\n-- !x! ENDIF\n-- !x! END SCRIPT\n"
        "-- !x! BEGIN BATCH\ninsert into marker values ('pending');\n"
        + command
        + "-- !x! END BATCH\ninsert into marker values ('caller continued');\n"
    )
    try:
        result = CliRunner().invoke(app, ["run", "--dsn", f"sqlite:///{database.db_name}", "-c", sql])
    finally:
        state.dbs.closeall()
    assert result.exit_code == 1, (result.output, result.exception)
    assert database.conn.execute("select * from marker").fetchall() == [("cleanup",)]
