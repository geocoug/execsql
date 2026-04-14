"""
Unit tests for execsql.debug.repl — the interactive debug REPL.

These tests exercise the internal helper functions (_print_var, _set_var,
_print_where, _print_stack, _print_all_vars, _format_help, _run_sql,
_handle_dot_command, _use_color, _c, _enable_step_mode) and the public
x_breakpoint entry point.

The REPL reads from stdin and writes to _state.output, so tests mock stdin
and capture output via a StringIO-backed WriteHooks.
"""

from __future__ import annotations

import io
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.config import WriteHooks
from execsql.debug.repl import (
    _c,
    _debug_repl,
    _enable_step_mode,
    _format_help,
    _handle_dot_command,
    _print_all_vars,
    _print_stack,
    _print_var,
    _print_where,
    _run_sql,
    _set_var,
    _use_color,
    x_breakpoint,
)
from execsql.script.variables import SubVarSet


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def capture():
    """Capture REPL output via a StringIO-backed WriteHooks."""
    buf = io.StringIO()
    hooks = WriteHooks(standard_output_func=buf.write)
    _state.output = hooks
    yield buf
    _state.output = None


@pytest.fixture
def subvars():
    """Provide a SubVarSet with a few test variables."""
    sv = SubVarSet()
    sv.add_substitution("logfile", "/tmp/test.log")
    sv.add_substitution("$db_name", "mydb")
    sv.add_substitution("&home", "/home/user")
    _state.subvars = sv
    yield sv


@pytest.fixture
def last_command():
    """Set up a mock last_command for .where and banner tests."""
    cmd = SimpleNamespace(
        source="/scripts/test.sql",
        line_no=42,
        command_type="sql",
        command=SimpleNamespace(
            commandline=lambda: "SELECT * FROM orders;",
            statement="SELECT * FROM orders;",
        ),
    )
    _state.last_command = cmd
    yield cmd


# ---------------------------------------------------------------------------
# _use_color
# ---------------------------------------------------------------------------


class TestUseColor:
    def test_no_color_env_disables(self, capture):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert _use_color() is False

    def test_execsql_no_color_env_disables(self, capture):
        with patch.dict(os.environ, {"EXECSQL_NO_COLOR": "1"}):
            assert _use_color() is False

    def test_non_tty_stdout_disables(self, capture):
        # Remove NO_COLOR to avoid early return
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "EXECSQL_NO_COLOR")}
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "stdout", new=io.StringIO()):
            assert _use_color() is False


# ---------------------------------------------------------------------------
# _c (color wrapper)
# ---------------------------------------------------------------------------


class TestColorWrapper:
    def test_no_color_returns_plain(self):
        with patch("execsql.debug.repl._use_color", return_value=False):
            assert _c("\033[31m", "hello") == "hello"

    def test_with_color_wraps_text(self):
        with patch("execsql.debug.repl._use_color", return_value=True):
            result = _c("\033[31m", "hello")
            assert result.startswith("\033[31m")
            assert "hello" in result
            assert result.endswith("\033[0m")


# ---------------------------------------------------------------------------
# _format_help
# ---------------------------------------------------------------------------


class TestFormatHelp:
    def test_contains_all_commands(self, capture):
        with patch("execsql.debug.repl._use_color", return_value=False):
            text = _format_help()
            assert ".continue" in text
            assert ".abort" in text
            assert ".vars" in text
            assert ".next" in text
            assert ".where" in text
            assert ".stack" in text
            assert ".set" in text
            assert ".help" in text

    def test_contains_non_command_section(self, capture):
        with patch("execsql.debug.repl._use_color", return_value=False):
            text = _format_help()
            assert "SELECT" in text
            assert "varname" in text


# ---------------------------------------------------------------------------
# _print_var
# ---------------------------------------------------------------------------


class TestPrintVar:
    def test_known_variable(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_var("logfile")
        assert "/tmp/test.log" in capture.getvalue()

    def test_system_var_with_sigil(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_var("$db_name")
        assert "mydb" in capture.getvalue()

    def test_sigil_stripped_fallback(self, capture, subvars):
        """If $logfile isn't found, try stripping the $ and looking up 'logfile'."""
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_var("$logfile")
        assert "/tmp/test.log" in capture.getvalue()

    def test_undefined_variable(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_var("nonexistent")
        assert "undefined" in capture.getvalue()

    def test_no_subvars_initialized(self, capture):
        _state.subvars = None
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_var("foo")
        assert "not initialised" in capture.getvalue()


# ---------------------------------------------------------------------------
# _set_var
# ---------------------------------------------------------------------------


class TestSetVar:
    def test_sets_variable(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _set_var("myvar", "myvalue")
        assert subvars.varvalue("myvar") == "myvalue"
        assert "myvar" in capture.getvalue()
        assert "myvalue" in capture.getvalue()

    def test_updates_existing(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _set_var("logfile", "new.log")
        assert subvars.varvalue("logfile") == "new.log"

    def test_no_subvars(self, capture):
        _state.subvars = None
        with patch("execsql.debug.repl._use_color", return_value=False):
            _set_var("foo", "bar")
        assert "not initialised" in capture.getvalue()


# ---------------------------------------------------------------------------
# _print_where
# ---------------------------------------------------------------------------


class TestPrintWhere:
    def test_with_last_command(self, capture, last_command):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_where()
        out = capture.getvalue()
        assert "test.sql" in out
        assert "42" in out
        assert "SELECT * FROM orders" in out

    def test_no_last_command(self, capture):
        _state.last_command = None
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_where()
        assert "unknown" in capture.getvalue()


# ---------------------------------------------------------------------------
# _print_stack
# ---------------------------------------------------------------------------


class TestPrintStack:
    def test_empty_stack(self, capture):
        _state.commandliststack = []
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_stack()
        assert "empty" in capture.getvalue()

    def test_populated_stack(self, capture):
        cl1 = SimpleNamespace(listname="main.sql", cmdptr=5)
        cl2 = SimpleNamespace(listname="include.sql", cmdptr=2)
        _state.commandliststack = [cl1, cl2]
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_stack()
        out = capture.getvalue()
        assert "main.sql" in out
        assert "include.sql" in out
        assert "depth" in out


# ---------------------------------------------------------------------------
# _print_all_vars
# ---------------------------------------------------------------------------


class TestPrintAllVars:
    def test_groups_variables(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_all_vars()
        out = capture.getvalue()
        assert "User" in out
        assert "logfile" in out
        assert "System" in out
        assert "$db_name" in out
        # Environment vars should NOT appear without include_env
        assert "&home" not in out

    def test_include_env(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_all_vars(include_env=True)
        out = capture.getvalue()
        assert "&home" in out

    def test_no_subvars(self, capture):
        _state.subvars = None
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_all_vars()
        assert "no substitution variables" in capture.getvalue().lower()

    def test_empty_subvars(self, capture):
        _state.subvars = SubVarSet()
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_all_vars()
        assert "no" in capture.getvalue().lower()


# ---------------------------------------------------------------------------
# _enable_step_mode
# ---------------------------------------------------------------------------


class TestEnableStepMode:
    def test_sets_flag(self):
        _state.step_mode = False
        _enable_step_mode()
        assert _state.step_mode is True


# ---------------------------------------------------------------------------
# _run_sql
# ---------------------------------------------------------------------------


class TestRunSql:
    def test_no_dbs(self, capture):
        _state.dbs = None
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT 1;")
        assert "no database" in capture.getvalue()

    def test_successful_query(self, capture):
        mock_db = MagicMock()
        mock_db.select_data.return_value = (["id", "name"], [(1, "Alice"), (2, "Bob")])
        pool = MagicMock()
        pool.current.return_value = mock_db
        _state.dbs = pool
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT * FROM people;")
        out = capture.getvalue()
        assert "Alice" in out
        assert "Bob" in out
        assert "2 rows" in out

    def test_single_row(self, capture):
        mock_db = MagicMock()
        mock_db.select_data.return_value = (["val"], [(42,)])
        pool = MagicMock()
        pool.current.return_value = mock_db
        _state.dbs = pool
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT 42;")
        out = capture.getvalue()
        assert "42" in out
        assert "1 row" in out

    def test_null_values(self, capture):
        mock_db = MagicMock()
        mock_db.select_data.return_value = (["col"], [(None,)])
        pool = MagicMock()
        pool.current.return_value = mock_db
        _state.dbs = pool
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT NULL;")
        assert "NULL" in capture.getvalue()

    def test_query_error(self, capture):
        mock_db = MagicMock()
        mock_db.select_data.side_effect = Exception("table not found")
        pool = MagicMock()
        pool.current.return_value = mock_db
        _state.dbs = pool
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT * FROM missing;")
        assert "SQL error" in capture.getvalue()

    def test_no_columns_returned(self, capture):
        mock_db = MagicMock()
        mock_db.select_data.return_value = ([], [])
        pool = MagicMock()
        pool.current.return_value = mock_db
        _state.dbs = pool
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT;")
        assert "no columns" in capture.getvalue()


# ---------------------------------------------------------------------------
# _handle_dot_command
# ---------------------------------------------------------------------------


class TestHandleDotCommand:
    def test_abort_raises_system_exit(self, capture):
        with pytest.raises(SystemExit):
            _handle_dot_command(".abort")

    def test_quit_raises_system_exit(self, capture):
        with pytest.raises(SystemExit):
            _handle_dot_command(".q")

    def test_help(self, capture):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".help")
        assert ".continue" in capture.getvalue()

    def test_help_shortcut(self, capture):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".h")
        assert ".continue" in capture.getvalue()

    def test_unknown_command(self, capture):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".foobar")
        assert "Unknown command" in capture.getvalue()

    def test_next_enables_step(self, capture):
        _state.step_mode = False
        _handle_dot_command(".next")
        assert _state.step_mode is True

    def test_next_shortcut(self, capture):
        _state.step_mode = False
        _handle_dot_command(".n")
        assert _state.step_mode is True

    def test_set_var(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".set myvar hello")
        assert subvars.varvalue("myvar") == "hello"

    def test_set_shortcut(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".s myvar world")
        assert subvars.varvalue("myvar") == "world"

    def test_set_no_args(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".set")
        assert "Usage" in capture.getvalue()

    def test_set_shortcut_no_args(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".s")
        assert "Usage" in capture.getvalue()

    def test_vars(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".vars")
        assert "logfile" in capture.getvalue()

    def test_vars_all(self, capture, subvars):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".vars all")
        assert "&home" in capture.getvalue()

    def test_where(self, capture, last_command):
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".where")
        assert "test.sql" in capture.getvalue()

    def test_stack(self, capture):
        _state.commandliststack = []
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".stack")
        assert "empty" in capture.getvalue()


# ---------------------------------------------------------------------------
# x_breakpoint — public entry point
# ---------------------------------------------------------------------------


class TestXBreakpoint:
    def test_skipped_when_not_tty(self, capture):
        """BREAKPOINT is silently skipped when stdin is not a TTY."""
        with patch.object(sys.stdin, "isatty", return_value=False):
            x_breakpoint()  # should not block

    def test_calls_repl_when_tty(self, capture):
        """When stdin is a TTY, x_breakpoint enters the REPL."""
        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("execsql.debug.repl._debug_repl") as mock_repl,
        ):
            x_breakpoint()
            mock_repl.assert_called_once()


# ---------------------------------------------------------------------------
# _debug_repl — integration-level tests with simulated stdin
# ---------------------------------------------------------------------------


class TestDebugReplIntegration:
    def test_continue_exits(self, capture, last_command):
        with (
            patch("builtins.input", side_effect=[".continue"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()

    def test_shortcut_c_exits(self, capture, last_command):
        with patch("builtins.input", side_effect=[".c"]), patch("execsql.debug.repl._use_color", return_value=False):
            _debug_repl()

    def test_eof_exits(self, capture, last_command):
        with patch("builtins.input", side_effect=EOFError), patch("execsql.debug.repl._use_color", return_value=False):
            _debug_repl()

    def test_keyboard_interrupt_exits(self, capture, last_command):
        with (
            patch("builtins.input", side_effect=KeyboardInterrupt),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()

    def test_empty_input_ignored(self, capture, last_command):
        with (
            patch("builtins.input", side_effect=["", "  ", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()

    def test_variable_lookup_then_continue(self, capture, last_command, subvars):
        with (
            patch("builtins.input", side_effect=["logfile", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        assert "/tmp/test.log" in capture.getvalue()

    def test_sql_query_then_continue(self, capture, last_command):
        mock_db = MagicMock()
        mock_db.select_data.return_value = (["x"], [(1,)])
        pool = MagicMock()
        pool.current.return_value = mock_db
        _state.dbs = pool
        with (
            patch("builtins.input", side_effect=["SELECT 1;", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        assert "1" in capture.getvalue()

    def test_abort_raises(self, capture, last_command):
        with (
            patch("builtins.input", side_effect=[".abort"]),
            patch("execsql.debug.repl._use_color", return_value=False),
            pytest.raises(SystemExit),
        ):
            _debug_repl()

    def test_step_mode_banner(self, capture, last_command):
        with patch("builtins.input", side_effect=[".c"]), patch("execsql.debug.repl._use_color", return_value=False):
            _debug_repl(step=True)
        assert "Step" in capture.getvalue()

    def test_breakpoint_banner(self, capture, last_command):
        with patch("builtins.input", side_effect=[".c"]), patch("execsql.debug.repl._use_color", return_value=False):
            _debug_repl(step=False)
        assert "Breakpoint" in capture.getvalue()

    def test_next_sets_step_mode(self, capture, last_command):
        _state.step_mode = False
        with patch("builtins.input", side_effect=[".next"]), patch("execsql.debug.repl._use_color", return_value=False):
            _debug_repl()
        assert _state.step_mode is True

    def test_no_last_command(self, capture):
        _state.last_command = None
        with patch("builtins.input", side_effect=[".c"]), patch("execsql.debug.repl._use_color", return_value=False):
            _debug_repl()
        assert "Breakpoint" in capture.getvalue()
