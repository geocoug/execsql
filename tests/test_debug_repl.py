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
    _reset_color_cache,
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
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        _reset_color_cache()
        yield
        _reset_color_cache()

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
        _state.ast_exec_stack = []
        with patch("execsql.debug.repl._use_color", return_value=False):
            _print_stack()
        assert "empty" in capture.getvalue()

    def test_populated_stack(self, capture):
        from execsql.state import ExecFrame

        f1 = ExecFrame(kind="main", label="<main>", source="main.sql", line=1)
        f2 = ExecFrame(kind="include", label="include.sql", source="/abs/include.sql", line=1)
        _state.ast_exec_stack = [f1, f2]
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


def _wire_mock_cursor(description=None, fetchall=None, rowcount=0, execute_raises=None):
    """Wire ``_state.dbs`` with a MagicMock db whose ``_cursor()`` context
    manager yields a cursor with the given description / fetchall / rowcount.

    Returns (db, cursor) for assertion on calls.
    """
    cursor = MagicMock()
    cursor.description = description
    cursor.rowcount = rowcount
    if fetchall is not None:
        cursor.fetchall.return_value = fetchall
    if execute_raises is not None:
        cursor.execute.side_effect = execute_raises
    db = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    db._cursor.return_value = cm
    pool = MagicMock()
    pool.current.return_value = db
    _state.dbs = pool
    return db, cursor


class TestRunSql:
    def test_no_dbs(self, capture):
        _state.dbs = None
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT 1;")
        assert "no database" in capture.getvalue()

    def test_successful_query(self, capture):
        _wire_mock_cursor(
            description=[("id",), ("name",)],
            fetchall=[(1, "Alice"), (2, "Bob")],
            rowcount=2,
        )
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT * FROM people;")
        out = capture.getvalue()
        assert "Alice" in out
        assert "Bob" in out
        assert "2 rows" in out

    def test_single_row(self, capture):
        _wire_mock_cursor(
            description=[("val",)],
            fetchall=[(42,)],
            rowcount=1,
        )
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT 42;")
        out = capture.getvalue()
        assert "42" in out
        assert "1 row" in out

    def test_null_values(self, capture):
        _wire_mock_cursor(
            description=[("col",)],
            fetchall=[(None,)],
            rowcount=1,
        )
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT NULL;")
        assert "NULL" in capture.getvalue()

    def test_query_error(self, capture):
        _wire_mock_cursor(execute_raises=Exception("table not found"))
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("SELECT * FROM missing;")
        assert "SQL error" in capture.getvalue()

    def test_dml_reports_rowcount(self, capture):
        """DELETE / UPDATE / INSERT report ``(N rows affected)`` instead of choking on a None description.

        Regression: previously _run_sql routed through db.select_data, which assumed
        cursor.description was non-None and crashed with ``'NoneType' object is not
        iterable`` for any DML — the statement had already executed.
        """
        _wire_mock_cursor(description=None, rowcount=3)
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("DELETE FROM test;")
        out = capture.getvalue()
        assert "3 rows affected" in out
        assert "SQL error" not in out
        assert "NoneType" not in out

    def test_dml_single_row_uses_singular(self, capture):
        _wire_mock_cursor(description=None, rowcount=1)
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("UPDATE test SET x = 1 WHERE id = 7;")
        assert "1 row affected" in capture.getvalue()

    def test_ddl_or_transaction_reports_executed(self, capture):
        """DDL / BEGIN / COMMIT / ROLLBACK report ``(statement executed)`` when rowcount is -1 or None."""
        _wire_mock_cursor(description=None, rowcount=-1)
        with patch("execsql.debug.repl._use_color", return_value=False):
            _run_sql("BEGIN;")
        assert "statement executed" in capture.getvalue()


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
        _state.ast_exec_stack = []
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".stack")
        assert "empty" in capture.getvalue()

    def test_scripts_detail_shows_full_path(self, capture):
        """.scripts <name> renders the full source path, not just the basename."""
        from execsql.script.ast import ScriptBlock, SourceSpan

        _state.ast_scripts = {
            "proc": ScriptBlock(
                span=SourceSpan("/home/user/etl/lib/load.sql", 12, 30),
                name="proc",
                param_defs=None,
                doc=None,
            ),
        }
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".scripts proc")
        assert "/home/user/etl/lib/load.sql:12-30" in capture.getvalue()

    def test_scripts_detail_inline_source(self, capture):
        """.scripts <name> for an `execsql -c <command>` script renders <inline>."""
        from execsql.script.ast import ScriptBlock, SourceSpan

        _state.ast_scripts = {
            "proc": ScriptBlock(
                span=SourceSpan("<inline>", 1, 4),
                name="proc",
                param_defs=None,
                doc=None,
            ),
        }
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".scripts proc")
        assert "<inline>:1-4" in capture.getvalue()

    def test_scripts_list_uses_basename(self, capture):
        """.scripts (no name) keeps basename for compact column-aligned output."""
        from execsql.script.ast import ScriptBlock, SourceSpan

        _state.ast_scripts = {
            "proc": ScriptBlock(
                span=SourceSpan("/home/user/etl/lib/load.sql", 12, 30),
                name="proc",
                param_defs=None,
                doc=None,
            ),
        }
        with patch("execsql.debug.repl._use_color", return_value=False):
            _handle_dot_command(".scripts")
        output = capture.getvalue()
        assert "load.sql:12-30" in output
        assert "/home/user/etl/lib/" not in output


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
        _wire_mock_cursor(description=[("x",)], fetchall=[(1,)], rowcount=1)
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

    def test_bad_sql_does_not_exit_repl(self, capture, last_command):
        """Bad SQL prints SQL error and re-prompts — does not escape the REPL.

        Regression for F-REPL-001: previously any exception that escaped a
        REPL action would propagate through x_breakpoint to
        _exec_metacommand, get stamped as ``metacommand_error``, and end
        the session.  After the fix the loop survives bad SQL and the user
        can keep typing.
        """
        _wire_mock_cursor(execute_raises=Exception("table not found"))
        # First input bad SQL with ``;``; second is .c to exit normally.
        with (
            patch("builtins.input", side_effect=["SELECT * FROM missing;", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        out = capture.getvalue()
        assert "SQL error" in out
        assert "table not found" in out

    def test_unexpected_exception_caught_by_outer_handler(self, capture, last_command):
        """An unexpected exception from a REPL helper prints ``Error:`` and re-prompts.

        Regression for F-REPL-001: the outer try/except wrapper makes the
        REPL resilient to bugs in any handler (not just _run_sql).
        """
        # Simulate a buggy dot-command by patching _handle_dot_command to raise.
        with (
            patch("builtins.input", side_effect=[".vars", ".c"]),
            patch("execsql.debug.repl._handle_dot_command", side_effect=[RuntimeError("boom"), None]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        out = capture.getvalue()
        assert "Error:" in out
        assert "boom" in out

    def test_multiline_sql_accumulates_until_semicolon(self, capture, last_command):
        """Multi-line SQL accumulates lines until ``;``, then executes the joined buffer.

        Regression for F-REPL-001 follow-up: typing ``SELECT 7`` then
        ``FROM dual;`` runs ``SELECT 7 FROM dual;`` as one statement rather
        than treating ``SELECT 7`` as a variable lookup.
        """
        _, cursor = _wire_mock_cursor(description=[("x",)], fetchall=[(7,)], rowcount=1)
        with (
            patch("builtins.input", side_effect=["SELECT 7", "FROM dual;", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        cursor.execute.assert_called_once_with("SELECT 7 FROM dual;")
        assert "7" in capture.getvalue()

    def test_multiline_cancel_discards_buffer(self, capture, last_command):
        """``.cancel`` while buffering discards the partial SQL and re-prompts."""
        with (
            patch("builtins.input", side_effect=["SELECT 1", ".cancel", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        assert "input discarded" in capture.getvalue()

    def test_multiline_keyboardinterrupt_discards_buffer(self, capture, last_command):
        """Ctrl-C while buffering clears the buffer; Ctrl-C at the fresh prompt then exits."""
        with (
            patch("builtins.input", side_effect=["SELECT *", KeyboardInterrupt, KeyboardInterrupt]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        assert "input discarded" in capture.getvalue()

    def test_multiline_dotcommand_still_works(self, capture, last_command, subvars):
        """Dot-commands fire even mid-buffer (they can never be valid SQL).

        Practical effect: ``.vars`` mid-SQL-buffer prints variables without
        appending to the buffer.  After the dot command the buffer is intact
        and the next ``;``-terminated input flushes it.
        """
        _, cursor = _wire_mock_cursor(description=[("x",)], fetchall=[(1,)], rowcount=1)
        with (
            patch("builtins.input", side_effect=["SELECT 1", ".vars", "FROM dual;", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        cursor.execute.assert_called_once_with("SELECT 1 FROM dual;")
        # .vars output (logfile is set by the subvars fixture) appears between the buffer lines.
        assert "logfile" in capture.getvalue()

    def test_fresh_prompt_bare_identifier_routes_to_lookup(self, capture, last_command, subvars):
        """Bare ``logfile`` at fresh prompt → variable lookup (not start of SQL buffer)."""
        with (
            patch("builtins.input", side_effect=["logfile", ".c"]),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        assert "/tmp/test.log" in capture.getvalue()
