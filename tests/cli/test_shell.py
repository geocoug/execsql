"""``execsql shell``: an interactive session, driven here through piped input."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys

import pytest


@pytest.fixture
def work(tmp_path):
    return tmp_path


def _shell(work, session: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(work), "USERPROFILE": str(work), "NO_COLOR": "1"}
    return subprocess.run(
        [sys.executable, "-m", "execsql", "shell", *args],
        input=session,
        cwd=work,
        capture_output=True,
        text=True,
        env=env,
    )


class TestSession:
    def test_in_memory_sqlite_by_default(self, work):
        result = _shell(work, "create table t (id integer);\ninsert into t values (1), (2);\nselect * from t;\n")
        assert result.returncode == 0, result.stderr
        assert "| id |" in result.stdout
        assert "(2 rows)" in result.stdout
        assert not list(work.glob("*.db"))

    def test_statement_across_lines(self, work):
        result = _shell(work, "select 1 as a,\n  2 as b\n;\n")
        assert "| a | b |" in result.stdout

    def test_metacommands_with_and_without_the_comment_marker(self, work):
        result = _shell(work, '!x! sub who shell\n-- !x! write "hello !!who!!"\n')
        assert "hello shell" in result.stdout

    def test_variables_are_substituted_in_sql(self, work):
        result = _shell(work, "!x! sub n 7\nselect !!n!! * 6 as answer;\n")
        assert "| 42     |" in result.stdout

    def test_block_stays_open_until_closed(self, work):
        session = '-- !x! if (true)\n-- !x! write "inside"\n-- !x! endif\n-- !x! write "after"\n'
        result = _shell(work, session)
        assert "inside" in result.stdout
        assert "after" in result.stdout

    def test_script_block_survives_to_a_later_input(self, work):
        session = (
            '-- !x! begin script greet\n-- !x! write "hi from greet"\n-- !x! end script\n-- !x! execute script greet\n'
        )
        assert "hi from greet" in _shell(work, session).stdout

    def test_errors_do_not_end_the_session(self, work):
        result = _shell(work, "select * from missing;\nselect 5 as five;\n")
        assert "SQL error: no such table: missing" in result.stdout
        assert "| five |" in result.stdout
        assert result.returncode == 0

    def test_local_variables_last_from_one_input_to_the_next(self, work):
        result = _shell(work, "-- !x! sub ~colour blue\nselect '!!~colour!!' as colour;\n")
        assert "| blue   |" in result.stdout

    def test_a_metacommand_error_does_not_end_the_session(self, work):
        result = _shell(work, '-- !x! frobnicate\n-- !x! write "still here"\n')
        assert "Unknown metacommand: frobnicate" in result.stdout
        assert "still here" in result.stdout

    def test_break_outside_a_loop_is_an_error(self, work):
        result = _shell(work, "-- !x! break\nselect 1 as one;\n")
        assert "BREAK metacommand outside of a LOOP block." in result.stdout
        assert "| one |" in result.stdout

    def test_an_included_file_shows_its_results_and_where_it_failed(self, work):
        (work / "part.sql").write_text("select 3 as three;\nselect * from missing;\n", encoding="utf-8")
        result = _shell(work, "-- !x! include part.sql\n")
        assert "| three |" in result.stdout
        assert "no such table: missing (line 2 of " in result.stdout

    def test_leaving_with_autocommit_off_says_what_is_lost(self, work):
        session = "create table k (x integer);\n-- !x! autocommit off\ninsert into k values (1);\n"
        result = _shell(work, session, "-tl", "k.db", "-n")
        assert "Not committed: AUTOCOMMIT is OFF" in result.stdout
        assert sqlite3.connect(work / "k.db").execute("select count(*) from k").fetchone() == (0,)

    def test_commit_keeps_work_done_with_autocommit_off(self, work):
        session = "create table k (x integer);\n-- !x! autocommit off\ninsert into k values (1);\ncommit;\n"
        _shell(work, session, "-tl", "k.db", "-n")
        assert sqlite3.connect(work / "k.db").execute("select count(*) from k").fetchone() == (1,)

    def test_unfinished_block_at_end_of_input_is_not_run(self, work):
        result = _shell(work, '-- !x! if (true)\n-- !x! write "never"\n')
        assert "never" not in result.stdout
        assert "input ended inside an unfinished statement or block" in result.stdout


class TestDotCommands:
    def test_vars_and_set(self, work):
        result = _shell(work, ".set colour blue\n.vars colour\n")
        assert "colour = blue" in result.stdout

    def test_quit_stops_reading(self, work):
        result = _shell(work, 'select 1;\n.quit\n-- !x! write "not reached"\n')
        assert "not reached" not in result.stdout

    def test_scripts(self, work):
        result = _shell(work, "-- !x! begin script greet\n-- !x! end script\n.scripts\n")
        assert "greet()" in result.stdout

    def test_help(self, work):
        assert ".vars [VAR | all]" in _shell(work, ".help\n").stdout

    def test_unknown_command(self, work):
        assert "Unknown command: '.nope'" in _shell(work, ".nope\n").stdout


class TestDatabases:
    def test_new_db_creates_and_keeps_the_data(self, work):
        result = _shell(work, "create table k (x integer);\ninsert into k values (42);\n", "-tl", "made.db", "-n")
        assert result.returncode == 0, result.stderr
        assert sqlite3.connect(work / "made.db").execute("select x from k").fetchall() == [(42,)]

    def test_missing_file_without_new_db_is_an_error_that_names_the_fix(self, work):
        result = _shell(work, "select 1;\n", "-tl", "nope.db")
        assert result.returncode == 1
        assert "Use -n (--new-db) to create it" in result.stdout + result.stderr
        assert not (work / "nope.db").exists()

    def test_halt_ends_the_shell_with_its_status(self, work):
        result = _shell(work, "-- !x! halt\nselect 1;\n")
        assert result.returncode == 3
        assert "(1 row)" not in result.stdout


# ---------------------------------------------------------------------------
# In process, so the session loop is measured by coverage: _run's shell mode
# with the FileWriter subprocess and GUI hooks patched out, as the ping tests do.
# ---------------------------------------------------------------------------


@pytest.fixture
def in_process(tmp_path, monkeypatch):
    import contextlib
    import io
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.chdir(tmp_path)
    targets = [
        "execsql.cli.run.FileWriter",
        "execsql.cli.run.filewriter_end",
        "execsql.cli.run.gui_console_off",
        "execsql.cli.run.gui_console_on",
        "execsql.cli.run.gui_console_isrunning",
        "execsql.cli.run.gui_console_wait_user",
        "execsql.cli.run.atexit",
    ]

    def run(session: str, *positional: str, new_db: bool = False) -> str:
        from execsql.cli.run import _run

        with contextlib.ExitStack() as stack:
            mocks = [stack.enter_context(patch(t, MagicMock())) for t in targets]
            mocks[0].return_value.is_alive.return_value = True
            monkeypatch.setattr("sys.stdin", io.StringIO(session))
            out = io.StringIO()
            monkeypatch.setattr("sys.stdout", out)

            _run(
                positional=list(positional),
                sub_vars=None,
                boolean_int=None,
                make_dirs=None,
                database_encoding=None,
                script_encoding=None,
                output_encoding=None,
                import_encoding=None,
                user_logfile=False,
                new_db=new_db,
                port=None,
                scanlines=None,
                db_type="l" if positional else None,
                user=None,
                use_gui=None,
                shell=True,
            )
            return out.getvalue()

    yield run

    # _run left the mocked FileWriter in global state, reporting itself
    # alive: a later test that writes a file would wait forever on its queue.
    import execsql.state as _state
    import execsql.utils.fileio as _fileio

    _state.filewriter = None
    _fileio.filewriter = None
    _state.output = None
    _state.exec_log = None


class TestInProcess:
    def test_sql_and_results(self, in_process):
        out = in_process("create table t (id integer);\ninsert into t values (1), (2);\nselect * from t;\n")
        assert "(2 rows affected)" in out
        assert "(2 rows)" in out

    def test_variables_blocks_and_dot_commands(self, in_process):
        session = (
            "!x! sub n 7\n"
            "-- !x! if (true)\n"
            "-- !x! sub m 6\n"
            "-- !x! endif\n"
            "select !!n!! * !!m!! as answer;\n"
            ".set colour blue\n"
            ".vars colour\n"
            ".vars\n"
            ".set\n"
            ".nope\n"
            ".help\n"
        )
        out = in_process(session)
        assert "| 42     |" in out
        assert "colour = blue" in out
        assert "Usage: .set VAR VALUE" in out
        assert "Unknown command: '.nope'" in out
        assert ".quit" in out

    def test_errors_and_unfinished_input(self, in_process):
        out = in_process("select * from missing;\n-- !x! endif\n.cancel\n-- !x! if (true)\n")
        assert "SQL error:" in out
        assert "has no matching IF" in out
        assert "input ended inside an unfinished statement or block" in out

    def test_local_variables_break_and_autocommit(self, in_process):
        session = (
            "-- !x! sub ~colour blue\nselect '!!~colour!!' as colour;\n-- !x! break\n.vars all\n-- !x! autocommit off\n"
        )
        out = in_process(session)
        assert "| blue   |" in out
        assert "BREAK metacommand outside of a LOOP block." in out
        assert "Environment (&)" in out
        assert "Not committed: AUTOCOMMIT is OFF" in out

    def test_quit(self, in_process):
        out = in_process("select 1 as one;\n.quit\nselect 2 as two;\n")
        assert "| one |" in out
        assert "| two |" not in out

    def test_file_database_with_new_db(self, in_process, tmp_path):
        in_process("create table k (x integer);\ninsert into k values (42);\n", "made.db", new_db=True)
        assert sqlite3.connect(tmp_path / "made.db").execute("select x from k").fetchall() == [(42,)]


def test_banner_names_the_database():
    from types import SimpleNamespace

    from execsql.shell import _banner

    memory = SimpleNamespace(name=lambda: ":memory:", db_name=":memory:", type=SimpleNamespace(dbms_id="SQLite"))
    assert "in-memory SQLite database" in _banner(memory)
    assert "no database" in _banner(None)
