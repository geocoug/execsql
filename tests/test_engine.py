"""Tests for execsql.script.engine.

Covers the classes and functions that remain after the legacy execution
engine was replaced by the AST executor:
- MetaCommand / MetaCommandList — dispatch table
- SqlStmt / MetacommandStmt — command wrappers
- ScriptCmd / CommandList — used by _flatten_for_legacy savedscripts
- ScriptExecSpec — deferred execution spec (construction only)
- substitute_vars() — variable expansion
- set_system_vars() — system variable population
- current_script_line() — execution location tracking
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.config import StatObj, WriteHooks
from execsql.exceptions import ErrInfo
from execsql.script import (
    CounterVars,
    IfLevels,
    MetaCommand,
    MetaCommandList,
    MetacommandStmt,
    SqlStmt,
    SubVarSet,
)
from execsql.script.engine import (
    CommandList,
    ScriptCmd,
    ScriptExecSpec,
    current_script_line,
    set_system_vars,
    substitute_vars,
)


# ---------------------------------------------------------------------------
# Helpers — minimal _state setup required by engine tests
# ---------------------------------------------------------------------------


def _setup_engine_state(subvars=None, status=None):
    """Populate the _state singletons required by the engine functions."""
    _state.if_stack = IfLevels()
    _state.counters = CounterVars()
    _state.subvars = subvars if subvars is not None else SubVarSet()
    _state.status = status if status is not None else StatObj()
    _state.commandliststack = []
    _state.output = WriteHooks()
    # Stub exec_log so read_sqlstring / read_sqlfile don't fail
    mock_log = MagicMock()
    mock_log.log_status_info = MagicMock()
    _state.exec_log = mock_log
    # metacommandlist — empty by default; override per-test as needed
    _state.metacommandlist = MetaCommandList()


@pytest.fixture()
def engine_state():
    """Reset _state to a fully usable engine configuration."""
    _setup_engine_state()
    return _state


# ---------------------------------------------------------------------------
# MetaCommand.run()
# ---------------------------------------------------------------------------


class TestMetaCommandRun:
    def test_no_match_returns_false_none(self):
        mc = MetaCommand(re.compile(r"^\s*HELLO\s*$", re.I), lambda **kw: None)
        matched, rv = mc.run("GOODBYE")
        assert matched is False
        assert rv is None

    def test_match_calls_handler_returns_true(self, engine_state):
        called_with = {}

        def handler(**kw):
            called_with.update(kw)
            return "ok"

        mc = MetaCommand(re.compile(r"^\s*DO\s+(?P<what>\w+)\s*$", re.I), handler)
        matched, rv = mc.run("DO SOMETHING")
        assert matched is True
        assert rv == "ok"
        assert called_with["what"] == "SOMETHING"
        assert called_with["metacommandline"] == "DO SOMETHING"

    def test_match_increments_hitcount(self, engine_state):
        mc = MetaCommand(re.compile(r"^\s*PING\s*$", re.I), lambda **kw: None)
        mc.run("PING")
        assert mc.hitcount == 1
        mc.run("PING")
        assert mc.hitcount == 2

    def test_no_match_does_not_increment_hitcount(self, engine_state):
        mc = MetaCommand(re.compile(r"^\s*PING\s*$", re.I), lambda **kw: None)
        mc.run("PONG")
        assert mc.hitcount == 0

    def test_handler_raises_errinf_no_halt(self, engine_state):
        """ErrInfo from handler: sets metacommand_error, returns (True, None)."""
        _state.status.halt_on_metacommand_err = False

        def bad_handler(**kw):
            raise ErrInfo("error", other_msg="oops")

        mc = MetaCommand(re.compile(r"^\s*FAIL\s*$", re.I), bad_handler, set_error_flag=True)
        matched, rv = mc.run("FAIL")
        assert matched is True
        assert rv is None
        assert _state.status.metacommand_error is True

    def test_handler_raises_general_exception_no_halt(self, engine_state):
        """Generic exception from handler is converted to ErrInfo."""
        _state.status.halt_on_metacommand_err = False

        def bad_handler(**kw):
            raise ValueError("boom")

        mc = MetaCommand(re.compile(r"^\s*BOOM\s*$", re.I), bad_handler, set_error_flag=True)
        matched, rv = mc.run("BOOM")
        assert matched is True
        assert rv is None
        assert _state.status.metacommand_error is True

    def test_successful_run_clears_metacommand_error(self, engine_state):
        _state.status.metacommand_error = True
        mc = MetaCommand(
            re.compile(r"^\s*GOOD\s*$", re.I),
            lambda **kw: "fine",
            set_error_flag=True,
        )
        mc.run("GOOD")
        assert _state.status.metacommand_error is False

    def test_set_error_flag_false_does_not_touch_metacommand_error(self, engine_state):
        _state.status.metacommand_error = True
        mc = MetaCommand(
            re.compile(r"^\s*NOFLAG\s*$", re.I),
            lambda **kw: None,
            set_error_flag=False,
        )
        mc.run("NOFLAG")
        # metacommand_error must not be cleared
        assert _state.status.metacommand_error is True

    def test_handler_raises_system_exit_propagates(self, engine_state):
        def exit_handler(**kw):
            raise SystemExit(0)

        mc = MetaCommand(re.compile(r"^\s*EXIT\s*$", re.I), exit_handler)
        with pytest.raises(SystemExit):
            mc.run("EXIT")

    def test_halt_on_metacommand_err_calls_exit_now(self, engine_state):
        """When halt_on_metacommand_err is True and handler raises, exit_now is called."""
        _state.status.halt_on_metacommand_err = True

        def bad_handler(**kw):
            raise ErrInfo("error", other_msg="halt me")

        mc = MetaCommand(re.compile(r"^\s*HALTNOW\s*$", re.I), bad_handler)
        # exit_now is imported lazily inside MetaCommand.run(), so patch at its source module
        with patch("execsql.utils.errors.exit_now") as mock_exit:
            mock_exit.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                mc.run("HALTNOW")
        mock_exit.assert_called_once()

    def test_repr_contains_pattern(self):
        mc = MetaCommand(re.compile(r"^\s*ABC\s*$", re.I), lambda **kw: None, "test cmd")
        r = repr(mc)
        assert "ABC" in r


# ---------------------------------------------------------------------------
# MetaCommandList
# ---------------------------------------------------------------------------


class TestMetaCommandList:
    def test_add_and_eval_match(self, engine_state):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HI\s*$", lambda **kw: "hello")
        matched, rv = mcl.eval("HI")
        assert matched is True
        assert rv == "hello"

    def test_add_and_eval_no_match(self, engine_state):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HI\s*$", lambda **kw: "hello")
        matched, rv = mcl.eval("GOODBYE")
        assert matched is False
        assert rv is None

    def test_add_list_of_patterns(self, engine_state):
        mcl = MetaCommandList()
        mcl.add([r"^\s*ONE\s*$", r"^\s*TWO\s*$"], lambda **kw: "num")
        m1, _ = mcl.eval("ONE")
        m2, _ = mcl.eval("TWO")
        assert m1 is True
        assert m2 is True

    def test_add_tuple_of_patterns(self, engine_state):
        mcl = MetaCommandList()
        mcl.add((r"^\s*AAA\s*$", r"^\s*BBB\s*$"), lambda **kw: "aabb")
        m1, _ = mcl.eval("AAA")
        assert m1 is True

    def test_last_registered_first_checked(self, engine_state):
        results = []
        mcl = MetaCommandList()
        mcl.add(r"^\s*CMD\s*$", lambda **kw: results.append("first") or "first")
        mcl.add(r"^\s*CMD\s*$", lambda **kw: results.append("second") or "second")
        matched, rv = mcl.eval("CMD")
        assert matched is True
        assert rv == "second"
        assert results == ["second"]

    def test_get_match_returns_node_and_match(self, engine_state):
        mcl = MetaCommandList()
        mcl.add(r"^\s*FIND\s+(?P<name>\w+)\s*$", lambda **kw: None)
        result = mcl.get_match("FIND alice")
        assert result is not None
        node, m = result
        assert isinstance(node, MetaCommand)
        assert m.group("name") == "alice"

    def test_get_match_returns_none_no_match(self, engine_state):
        mcl = MetaCommandList()
        mcl.add(r"^\s*FIND\s*$", lambda **kw: None)
        result = mcl.get_match("NOTFOUND")
        assert result is None

    def test_iter_over_commands(self, engine_state):
        mcl = MetaCommandList()
        mcl.add(r"^\s*A\s*$", lambda **kw: None)
        mcl.add(r"^\s*B\s*$", lambda **kw: None)
        cmds = list(mcl)
        assert len(cmds) == 2

    def test_keywords_by_category(self, engine_state):
        mcl = MetaCommandList()
        mcl.add(r"^\s*SELECT\s*$", lambda **kw: None, description="SELECT", category="data")
        mcl.add(r"^\s*INSERT\s*$", lambda **kw: None, description="INSERT", category="data")
        result = mcl.keywords_by_category()
        assert "data" in result
        assert "SELECT" in result["data"]
        assert "INSERT" in result["data"]

    def test_keywords_by_category_deduplicates(self, engine_state):
        mcl = MetaCommandList()
        mcl.add(r"^\s*FOO\s*$", lambda **kw: None, description="FOO", category="cat")
        mcl.add(r"^\s*FOO\s*$", lambda **kw: None, description="FOO", category="cat")
        result = mcl.keywords_by_category()
        assert result["cat"].count("FOO") == 1

    def test_run_when_false_skips_when_if_stack_false(self, engine_state):
        called = []
        mcl = MetaCommandList()
        mcl.add(r"^\s*SKIP\s*$", lambda **kw: called.append(True), run_when_false=False)
        _state.if_stack.nest(False)
        mcl.eval("SKIP")
        assert called == []

    def test_run_when_false_runs_despite_false_if_stack(self, engine_state):
        called = []
        mcl = MetaCommandList()
        mcl.add(r"^\s*RUN\s*$", lambda **kw: called.append(True), run_when_false=True)
        _state.if_stack.nest(False)
        mcl.eval("RUN")
        assert called == [True]

    def test_unkeyed_pattern_falls_back_to_full_list(self, engine_state):
        """A pattern with no extractable keyword lands in _unkeyed and still matches."""
        mcl = MetaCommandList()
        # Pattern has no leading keyword extractable by _KEYWORD_RX
        mcl.add(r"^(?:\d+)\s+things$", lambda **kw: "yes")
        matched, rv = mcl.eval("42 things")
        assert matched is True
        assert rv == "yes"


# ---------------------------------------------------------------------------
# SqlStmt
# ---------------------------------------------------------------------------


class TestSqlStmt:
    def test_constructor_collapses_double_semicolons(self):
        stmt = SqlStmt("SELECT 1;;")
        assert stmt.statement.endswith(";")
        assert ";;" not in stmt.statement

    def test_commandline_returns_statement(self):
        stmt = SqlStmt("SELECT 1;")
        assert stmt.commandline() == "SELECT 1;"

    def test_repr(self):
        stmt = SqlStmt("SELECT 1;")
        assert "SELECT 1;" in repr(stmt)


# ---------------------------------------------------------------------------
# MetacommandStmt
# ---------------------------------------------------------------------------


class TestMetacommandStmt:
    def test_constructor_stores_statement(self):
        ms = MetacommandStmt("SET myvar = hello")
        assert ms.statement == "SET myvar = hello"

    def test_commandline_prefixes_metacommand(self):
        ms = MetacommandStmt("SET myvar = hello")
        assert ms.commandline() == "-- !x! SET myvar = hello"

    def test_repr(self):
        ms = MetacommandStmt("SET x = 1")
        assert "SET x = 1" in repr(ms)

    def test_run_dispatches_to_metacommandlist(self, engine_state):
        called = []
        _state.metacommandlist.add(
            r"^\s*NOOP\s*$",
            lambda **kw: called.append(True),
        )
        ms = MetacommandStmt("NOOP")
        ms.run()
        assert called == [True]

    def test_run_raises_on_unknown_metacommand(self, engine_state):
        """An unrecognised metacommand with all_true if-stack raises ErrInfo."""
        ms = MetacommandStmt("UNKNOWN_CMD_XYZ")
        with pytest.raises(ErrInfo):
            ms.run()

    def test_run_does_not_raise_when_if_stack_false(self, engine_state):
        """Unknown metacommand is silently ignored when if-stack is False."""
        _state.if_stack.nest(False)
        ms = MetacommandStmt("UNKNOWN_CMD_XYZ")
        # Should return None, not raise
        rv = ms.run()
        assert rv is None

    def test_run_sets_metacommand_error_on_exception(self, engine_state):
        _state.status.halt_on_metacommand_err = False

        def boom(**kw):
            raise RuntimeError("kaboom")

        _state.metacommandlist.add(r"^\s*BOOM\s*$", boom)
        ms = MetacommandStmt("BOOM")
        ms.run()
        assert _state.status.metacommand_error is True

    def test_run_propagates_system_exit(self, engine_state):
        def sys_exit(**kw):
            raise SystemExit(1)

        _state.metacommandlist.add(r"^\s*BYE\s*$", sys_exit)
        ms = MetacommandStmt("BYE")
        with pytest.raises(SystemExit):
            ms.run()

    def test_run_expands_vars_before_dispatch(self, engine_state):
        seen = []
        _state.subvars.add_substitution("$CMD", "ALPHA")
        _state.metacommandlist.add(r"^\s*ALPHA\s*$", lambda **kw: seen.append("alpha"))
        ms = MetacommandStmt("!!$CMD!!")
        ms.run()
        assert seen == ["alpha"]

    def test_run_halt_on_metacommand_err_raises_on_eval_errinf(self, engine_state):
        """When halt_on_metacommand_err is True and eval raises ErrInfo, MetacommandStmt raises too."""
        _state.status.halt_on_metacommand_err = True
        # Cause metacommandlist.eval() to propagate an ErrInfo (not via MetaCommand.run
        # but by having eval itself raise — simulated by replacing eval entirely)
        with patch.object(_state.metacommandlist, "eval", side_effect=ErrInfo("error", other_msg="bad eval")):
            ms = MetacommandStmt("ANYTHING")
            with pytest.raises(ErrInfo):
                ms.run()


# ---------------------------------------------------------------------------
# ScriptCmd
# ---------------------------------------------------------------------------


class TestScriptCmd:
    def test_current_script_line(self):
        sc = ScriptCmd("myfile.sql", 42, "sql", SqlStmt("SELECT 1;"))
        assert sc.current_script_line() == ("myfile.sql", 42)

    def test_commandline_sql_type(self):
        sc = ScriptCmd("f.sql", 1, "sql", SqlStmt("SELECT 1;"))
        assert sc.commandline() == "SELECT 1;"

    def test_commandline_cmd_type(self):
        sc = ScriptCmd("f.sql", 1, "cmd", MetacommandStmt("SET x = 1"))
        assert sc.commandline() == "-- !x! SET x = 1"

    def test_repr(self):
        sc = ScriptCmd("f.sql", 10, "sql", SqlStmt("SELECT 1;"))
        r = repr(sc)
        assert "f.sql" in r
        assert "10" in r


# ---------------------------------------------------------------------------
# CommandList
# ---------------------------------------------------------------------------


def _make_script_cmd(stmt="SELECT 1;", cmd_type="sql", source="test.sql", lineno=1):
    if cmd_type == "sql":
        return ScriptCmd(source, lineno, "sql", SqlStmt(stmt))
    else:
        return ScriptCmd(source, lineno, "cmd", MetacommandStmt(stmt))


class TestCommandList:
    def test_raises_on_none_cmdlist(self):
        with pytest.raises(ErrInfo):
            CommandList(None, "mylist")

    def test_empty_cmdlist_allowed(self):
        cl = CommandList([], "mylist")
        assert cl.current_command() is None

    def test_add_appends_command(self):
        cl = CommandList([], "mylist")
        sc = _make_script_cmd()
        cl.add(sc)
        assert cl.current_command() is sc

    def test_current_command_returns_none_when_exhausted(self):
        sc = _make_script_cmd()
        cl = CommandList([sc], "mylist")
        cl.cmdptr = 1  # advance past end
        assert cl.current_command() is None

    def test_iter_yields_commands(self):
        sc1 = _make_script_cmd("SELECT 1;", lineno=1)
        sc2 = _make_script_cmd("SELECT 2;", lineno=2)
        cl = CommandList([sc1, sc2], "mylist")
        items = list(cl)
        assert len(items) == 2
        assert items[0] is sc1
        assert items[1] is sc2

    def test_run_next_raises_stop_iteration_when_empty(self, engine_state):
        cl = CommandList([], "mylist")
        with pytest.raises(StopIteration):
            cl.run_next()

    def test_set_paramvals_with_matching_names(self):
        cl = CommandList([], "myscript", paramnames=["x", "y"])
        from execsql.script.variables import ScriptArgSubVarSet

        save = ScriptArgSubVarSet()
        save.add_substitution("#x", "1")
        save.add_substitution("#y", "2")
        cl.set_paramvals(save)  # should not raise

    def test_set_paramvals_mismatch_raises(self):
        cl = CommandList([], "myscript", paramnames=["x", "y"])
        from execsql.script.variables import ScriptArgSubVarSet

        save = ScriptArgSubVarSet()
        save.add_substitution("#x", "1")
        # y is missing
        with pytest.raises(ErrInfo):
            cl.set_paramvals(save)


# ---------------------------------------------------------------------------
# substitute_vars()
# ---------------------------------------------------------------------------


class TestSubstituteVars:
    def test_no_vars_returns_unchanged(self, engine_state):
        result = substitute_vars("SELECT 1")
        assert result == "SELECT 1"

    def test_substitutes_global_var(self, engine_state):
        _state.subvars.add_substitution("$MYVAR", "hello")
        result = substitute_vars("SELECT '!!$MYVAR!!'")
        assert result == "SELECT 'hello'"

    def test_merges_local_vars(self, engine_state):
        localvars = SubVarSet()
        localvars.add_substitution("$LOCAL", "world")
        result = substitute_vars("SELECT '!!$LOCAL!!'", localvars)
        assert result == "SELECT 'world'"

    def test_local_vars_override_global(self, engine_state):
        _state.subvars.add_substitution("$V", "global")
        localvars = SubVarSet()
        localvars.add_substitution("$V", "local")
        result = substitute_vars("!!$V!!", localvars)
        assert result == "local"

    def test_counter_substitution(self, engine_state):
        result = substitute_vars("x=!!$COUNTER_1!!")
        assert result == "x=1"

    def test_deferred_var_converted_to_eager(self, engine_state):
        """Deferred !{$var}! tokens are converted to !!$var!! form."""
        result = substitute_vars("value: !{$myvar}!")
        assert result == "value: !!$myvar!!"

    def test_cycle_detection_raises_errinf(self, engine_state):
        """After _MAX_SUBSTITUTION_DEPTH iterations substitute_vars raises ErrInfo.

        We force the outer loop to keep running by patching CounterVars.substitute_all
        so it always reports a substitution was made.  This is the only way to
        exhaust the depth limit without a true self-referential variable loop
        (which would hang inside SubVarSet.substitute_all).
        """
        iteration_count = [0]

        def fake_sub_all(text):
            iteration_count[0] += 1
            return text, True  # always claims a substitution was made

        with (
            patch.object(_state.counters, "substitute_all", side_effect=fake_sub_all),
            pytest.raises(ErrInfo, match="[Cc]ycle"),
        ):
            substitute_vars("SELECT 1")


# ---------------------------------------------------------------------------
# set_system_vars()
# ---------------------------------------------------------------------------


class TestSetSystemVars:
    def _make_db(self):
        db = SimpleNamespace(
            autocommit=False,
            user="testuser",
            server_name="localhost",
            db_name="mydb",
            need_passwd=False,
            type=SimpleNamespace(dbms_id="TestDB"),
        )
        db.name = lambda: "TestDB(server localhost; database mydb)"
        return db

    def test_populates_cancel_halt_state(self, engine_state):
        _state.status.cancel_halt = True
        pool = MagicMock()
        pool.current.return_value = self._make_db()
        pool.current_alias.return_value = "main"
        _state.dbs = pool
        mock_timer = MagicMock()
        mock_timer.elapsed.return_value = 0
        _state.timer = mock_timer
        set_system_vars()
        assert _state.subvars.varvalue("$CANCEL_HALT_STATE") == "ON"

    def test_populates_error_halt_state(self, engine_state):
        _state.status.halt_on_err = False
        pool = MagicMock()
        pool.current.return_value = self._make_db()
        pool.current_alias.return_value = "main"
        _state.dbs = pool
        mock_timer = MagicMock()
        mock_timer.elapsed.return_value = 0
        _state.timer = mock_timer
        set_system_vars()
        assert _state.subvars.varvalue("$ERROR_HALT_STATE") == "OFF"

    def test_populates_db_name(self, engine_state):
        pool = MagicMock()
        pool.current.return_value = self._make_db()
        pool.current_alias.return_value = "main"
        _state.dbs = pool
        mock_timer = MagicMock()
        mock_timer.elapsed.return_value = 5
        _state.timer = mock_timer
        set_system_vars()
        assert _state.subvars.varvalue("$DB_NAME") == "mydb"

    def test_populates_db_user(self, engine_state):
        pool = MagicMock()
        pool.current.return_value = self._make_db()
        pool.current_alias.return_value = "main"
        _state.dbs = pool
        mock_timer = MagicMock()
        mock_timer.elapsed.return_value = 0
        _state.timer = mock_timer
        set_system_vars()
        assert _state.subvars.varvalue("$DB_USER") == "testuser"

    def test_current_time_not_set_by_set_system_vars(self, engine_state):
        """$CURRENT_TIME is set per-statement in run_and_increment, not in set_system_vars."""
        pool = MagicMock()
        pool.current.return_value = self._make_db()
        pool.current_alias.return_value = "main"
        _state.dbs = pool
        mock_timer = MagicMock()
        mock_timer.elapsed.return_value = 0
        _state.timer = mock_timer
        set_system_vars()
        assert _state.subvars.varvalue("$CURRENT_TIME") is None

    def test_populates_version_numbers(self, engine_state):
        pool = MagicMock()
        pool.current.return_value = self._make_db()
        pool.current_alias.return_value = "main"
        _state.dbs = pool
        mock_timer = MagicMock()
        mock_timer.elapsed.return_value = 0
        _state.timer = mock_timer
        set_system_vars()
        assert _state.subvars.varvalue("$VERSION1") is not None

    def test_populates_uuid(self, engine_state):
        pool = MagicMock()
        pool.current.return_value = self._make_db()
        pool.current_alias.return_value = "main"
        _state.dbs = pool
        mock_timer = MagicMock()
        mock_timer.elapsed.return_value = 0
        _state.timer = mock_timer
        set_system_vars()
        val = _state.subvars.varvalue("$UUID")
        assert val is not None and len(val) == 36


# ---------------------------------------------------------------------------
# current_script_line()
# ---------------------------------------------------------------------------


class TestCurrentScriptLine:
    def test_empty_stack_returns_empty(self, engine_state):
        _state.commandliststack = []
        assert current_script_line() == ("", 0)

    def test_active_command_returns_source_and_lineno(self, engine_state):
        sc = ScriptCmd("myscript.sql", 7, "sql", SqlStmt("SELECT 1;"))
        cl = CommandList([sc], "myscript.sql")
        _state.commandliststack = [cl]
        assert current_script_line() == ("myscript.sql", 7)

    def test_exhausted_list_returns_listname_and_length(self, engine_state):
        sc = ScriptCmd("myscript.sql", 7, "sql", SqlStmt("SELECT 1;"))
        cl = CommandList([sc], "myscript")
        cl.cmdptr = 1  # exhausted
        _state.commandliststack = [cl]
        source, line = current_script_line()
        assert "myscript" in source
        assert line == 1


# Legacy parser tests (_parse_script_lines, read_sqlstring, read_sqlfile,
# runscripts, ScriptFile) removed — these functions were deleted when the
# AST parser/executor became the only execution engine.


# ---------------------------------------------------------------------------
# ScriptExecSpec (construction-only — .execute() was removed with the legacy engine)
# ---------------------------------------------------------------------------


class TestScriptExecSpec:
    def _make_saved_script(self, name="myscript", cmds=None, paramnames=None):
        if cmds is None:
            cmds = []
        cl = CommandList(cmds, name, paramnames)
        _state.savedscripts[name] = cl

    def test_raises_on_missing_script(self, engine_state):
        _state.savedscripts = {}
        with pytest.raises(ErrInfo, match="no SCRIPT"):
            ScriptExecSpec(script_id="nonexistent", argexp=None, looptype=None, loopcond=None)

    def test_looptype_none_when_not_provided(self, engine_state):
        self._make_saved_script("s_noloop")
        spec = ScriptExecSpec(script_id="s_noloop", argexp=None, looptype=None, loopcond=None)
        assert spec.looptype is None

    def test_looptype_uppercased(self, engine_state):
        self._make_saved_script("s_up")
        spec = ScriptExecSpec(script_id="s_up", argexp=None, looptype="while", loopcond="1==2")
        assert spec.looptype == "WHILE"
