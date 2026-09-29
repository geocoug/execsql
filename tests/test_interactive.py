"""The engine shared by ``execsql shell`` and the debug REPL (``execsql.interactive``).

Breakpoint tests run a real script through ``execsql.run()`` with stdin
reported as a terminal and ``input()`` fed from a list, so input typed at the
prompt runs inside the paused script exactly as it would for a user.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql import run
from execsql.exceptions import ErrInfo
from execsql.interactive import Prompt, _prompts, describe_error, uncommitted


class _Typed:
    """Feeds ``input()`` and records each prompt it was shown."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.prompts: list[str] = []

    def __call__(self, prompt: str = "") -> str:
        self.prompts.append(prompt)
        if not self.lines:
            raise EOFError
        return self.lines.pop(0)


def _paused(tmp_path, script: str, typed: list[str]):
    """Run *script* against a new SQLite file, typing *typed* at each BREAKPOINT."""
    out: list[str] = []
    feed = _Typed(typed)
    db = tmp_path / "t.db"
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("builtins.input", feed),
        patch("execsql.debug.repl._write", out.append),
        patch("execsql.debug.repl._use_color", return_value=False),
    ):
        result = run(sql=script, dsn=f"sqlite:///{db}", new_db=True)
    rows = sqlite3.connect(db).execute("select n from t order by n").fetchall()
    return result, "".join(out), feed, [r[0] for r in rows]


LOOP = """
create table t (n integer);
-- !x! sub ~who the-script
-- !x! sub i 0
-- !x! loop while (is_gt(4, !!i!!))
-- !x! sub_add i 1
insert into t values (!!i!!);
-- !x! if (equal(!!i!!, 2))
-- !x! breakpoint
-- !x! endif
-- !x! end loop
"""


class TestAtABreakpoint:
    def test_sql_runs_in_the_paused_scope_and_shows_rows(self, tmp_path):
        result, out, _, _ = _paused(tmp_path, LOOP, ["select '!!~who!!' as who, count(*) as n from t;", ".c"])
        assert result.success, result.errors
        assert "| the-script | 2 |" in out
        assert "(1 row)" in out

    def test_a_sub_is_still_set_when_the_script_resumes(self, tmp_path):
        script = LOOP + "insert into t values (!!extra!!);\n"
        result, _, _, rows = _paused(tmp_path, script, ["!x! sub extra 99", ".c"])
        assert result.success, result.errors
        assert rows == [1, 2, 3, 4, 99]

    def test_break_leaves_the_scripts_loop(self, tmp_path):
        result, _, _, rows = _paused(tmp_path, LOOP, ["insert into t values (100);", "-- !x! break"])
        assert result.success, result.errors
        assert rows == [1, 2, 100]

    def test_break_outside_a_loop_is_reported_and_the_prompt_stays(self, tmp_path):
        script = "create table t (n integer);\n-- !x! breakpoint\ninsert into t values (1);\n"
        result, out, _, rows = _paused(tmp_path, script, ["-- !x! break", ".c"])
        assert "BREAK metacommand outside of a LOOP block." in out
        assert result.success, result.errors
        assert rows == [1]

    def test_where_still_shows_the_breakpoint_after_input(self, tmp_path):
        _, out, _, _ = _paused(tmp_path, LOOP, ["select 1 as one;", ".where", ".c"])
        location = out.split("Location", 1)[1]
        assert "<inline>:9" in location
        assert "breakpoint" in location.lower()

    def test_an_error_ends_only_that_input(self, tmp_path):
        script = LOOP.replace("-- !x! breakpoint", "-- !x! breakpoint\n-- !x! write 'resumed'")
        typed = ["select * from missing;", "-- !x! frobnicate", "insert into t values (50);", ".c"]
        result, out, _, rows = _paused(tmp_path, script, typed)
        assert "SQL error: no such table: missing" in out
        assert "Unknown metacommand: frobnicate" in out
        assert result.success, result.errors
        assert rows == [1, 2, 3, 4, 50]

    def test_blocks_and_multi_line_sql_run_once_closed(self, tmp_path):
        typed = ["-- !x! if (equal(!!i!!, 2))", "insert into t", "  values (20);", "-- !x! endif", ".c"]
        result, _, feed, rows = _paused(tmp_path, LOOP, typed)
        assert result.success, result.errors
        assert rows == [1, 2, 3, 4, 20]
        assert feed.prompts[1].strip() == "...>"

    def test_halt_ends_the_run(self, tmp_path):
        result, _, _, rows = _paused(tmp_path, LOOP, ["-- !x! halt"])
        assert not result.success
        assert rows == [1, 2]

    def test_the_prompt_marks_uncommitted_mode_inside_a_batch(self, tmp_path):
        script = "create table t (n integer);\n-- !x! begin batch\n-- !x! breakpoint\n-- !x! end batch\n"
        _, _, feed, _ = _paused(tmp_path, script, [".c"])
        assert feed.prompts == ["execsql debug*> "]

    def test_the_prompt_is_plain_when_each_statement_commits(self, tmp_path):
        _, _, feed, _ = _paused(tmp_path, LOOP, [".c"])
        assert feed.prompts == ["execsql debug> "]


class TestUncommitted:
    @pytest.fixture(autouse=True)
    def _restore(self):
        saved = (_state.status, _state.dbs)
        yield
        _state.status, _state.dbs = saved

    def _set(self, *, in_batch=False, autocommit=True, no_db=False):
        _state.status = SimpleNamespace(batch=SimpleNamespace(in_batch=lambda: in_batch))
        pool = MagicMock()
        if no_db:
            pool.current.side_effect = RuntimeError("no database")
        else:
            pool.current.return_value = SimpleNamespace(autocommit=autocommit)
        _state.dbs = pool

    def test_autocommit_on(self):
        self._set()
        assert not uncommitted()
        assert _prompts(Prompt()) == ("execsql> ", "    ...> ")

    def test_autocommit_off(self):
        self._set(autocommit=False)
        assert uncommitted()
        assert _prompts(Prompt()) == ("execsql*> ", "     ...> ")

    def test_batch(self):
        self._set(in_batch=True)
        assert uncommitted()

    def test_no_database(self):
        self._set(no_db=True)
        assert not uncommitted()
        _state.dbs = None
        assert not uncommitted()


class TestDescribeError:
    @pytest.fixture(autouse=True)
    def _plain(self):
        with patch("execsql.debug.repl._use_color", return_value=False):
            yield

    def test_a_wrapped_driver_error_shows_the_drivers_message(self):
        err = ErrInfo("exception", exception_msg="OperationalError: no such table in base.py on line 9")
        err.__cause__ = sqlite3.OperationalError("no such table: x")
        err.cmdtype = "sql"
        assert describe_error(err) == "SQL error: no such table: x"

    def test_execsqls_own_message_names_the_command(self):
        err = ErrInfo("cmd", command_text="frobnicate", other_msg="Unknown metacommand")
        assert describe_error(err) == "Error: Unknown metacommand: frobnicate"

    def test_an_error_in_a_file_says_where(self):
        err = ErrInfo("cmd", other_msg="Bad thing")
        err.script_file, err.script_line_no = "load.sql", 12
        assert describe_error(err) == "Error: Bad thing (line 12 of load.sql)"

    def test_input_typed_at_the_prompt_has_no_location(self):
        err = ErrInfo("cmd", other_msg="Bad thing")
        err.script_file, err.script_line_no = "<shell>", 1
        assert describe_error(err) == "Error: Bad thing"

    def test_other_exceptions(self):
        assert describe_error(RuntimeError("boom")) == "Error: boom"
        assert describe_error(RuntimeError()) == "Error: RuntimeError"


class TestExitNowAtAPrompt:
    def test_an_error_is_raised_to_the_prompt(self):
        from execsql.utils.errors import exit_now

        err = ErrInfo("error", other_msg="nope")
        _state.prompt_input = lambda result: None
        try:
            with pytest.raises(ErrInfo) as caught:
                exit_now(1, err)
        finally:
            _state.prompt_input = None
        assert caught.value is err

    def test_halt_still_exits(self):
        from execsql.utils.errors import exit_now

        _state.prompt_input = lambda result: None
        try:
            with (
                patch("execsql.utils.fileio.filewriter_end"),
                pytest.raises(SystemExit) as caught,
            ):
                exit_now(3, None)
        finally:
            _state.prompt_input = None
        assert caught.value.code == 3


class TestExecuteFetch:
    def test_rows_and_none(self, tmp_path):
        from execsql.db.sqlite import SQLiteDatabase

        db = SQLiteDatabase(str(tmp_path / "f.db"))
        _state.subvars = MagicMock()
        try:
            assert db.execute("create table f (a integer, b text)", fetch=True) is None
            assert db.execute("insert into f values (1, 'x')", fetch=True) is None
            assert db.execute("select a, b from f", fetch=True) == (["a", "b"], [(1, "x")])
            assert db.execute("select a from f") is None
        finally:
            db.close()

    def test_oracle_strips_the_semicolon_and_passes_fetch(self):
        from execsql.db.base import Database
        from execsql.db.oracle import OracleDatabase

        with patch.object(Database, "execute", return_value=(["x"], [(1,)])) as base:
            result = object.__new__(OracleDatabase).execute("select 1 from dual;", fetch=True)
        base.assert_called_once_with("select 1 from dual", None, fetch=True)
        assert result == (["x"], [(1,)])

    def test_duckdb_reports_changed_rows_not_a_count_table(self, tmp_path):
        pytest.importorskip("duckdb")
        from execsql.db.duckdb import DuckDBDatabase

        db = DuckDBDatabase(str(tmp_path / "f.duckdb"))
        subvars = MagicMock()
        _state.subvars = subvars
        try:
            assert db.execute("create table f (a integer)", fetch=True) is None
            assert db.execute("insert into f values (1), (2)", fetch=True) is None
            subvars.add_substitution.assert_called_with("$LAST_ROWCOUNT", 2)
            assert db.execute('select count(*) as "Count" from f', fetch=True) == (["Count"], [(2,)])
        finally:
            db.close()
