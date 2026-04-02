"""Unit tests for the BREAKPOINT metacommand and its debug REPL.

Covers:
- x_breakpoint is a no-op when sys.stdin is not a TTY
- '.continue' / '.c' resumes execution
- '.abort' / '.q' raises SystemExit(1)
- '.vars' prints grouped substitution variables
- variable name prints its value (bare or sigil-prefixed)
- '.help' prints help text
- '.stack' prints command-list stack info
- SQL ending with ';' executes and pretty-prints results
- '.next' / '.n' enables step_mode and returns
- Unknown dot-command prints an error message
- Unknown bare word checks variable lookup before erroring
- EOF (Ctrl-D) resumes execution
- KeyboardInterrupt (Ctrl-C) resumes execution
- _write falls back to stdout when _state.output is None
- step_mode in engine triggers _debug_repl after a statement
- ANSI color helpers (_c, _use_color, _write_rule)
- _debug_repl(step=True) shows "Step" label
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.debug.repl import (
    _WHERE_TRUNCATE,
    _c,
    _CYAN,
    _DIM,
    _debug_repl,
    _enable_step_mode,
    _print_all_vars,
    _print_stack,
    _print_var,
    _print_where,
    _run_sql,
    _set_var,
    _use_color,
    _write,
    _write_rule,
    x_breakpoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_subvars(items: dict[str, str] | None = None) -> MagicMock:
    """Return a mock SubVarSet with the given variable dict."""
    sv = MagicMock()
    sv.substitutions = list((items or {}).items())
    sv.varvalue = lambda name: (items or {}).get(name.lower())
    return sv


def _make_output() -> MagicMock:
    """Return a mock WriteHooks object."""
    out = MagicMock()
    out.write = MagicMock()
    return out


# ---------------------------------------------------------------------------
# x_breakpoint — TTY gate
# ---------------------------------------------------------------------------


class TestXBreakpointTtyGate:
    """x_breakpoint is skipped silently when stdin is not a TTY."""

    def test_skipped_when_not_tty(self) -> None:
        with (
            patch.object(sys.stdin, "isatty", return_value=False),
            patch("execsql.debug.repl._debug_repl") as mock_repl,
        ):
            result = x_breakpoint()
        assert result is None
        mock_repl.assert_not_called()

    def test_calls_repl_when_tty(self) -> None:
        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("execsql.debug.repl._debug_repl") as mock_repl,
        ):
            x_breakpoint()
        mock_repl.assert_called_once()


# ---------------------------------------------------------------------------
# _debug_repl — dot-prefixed flow control commands
# ---------------------------------------------------------------------------


class TestDebugReplContinue:
    """'.continue' and '.c' resume execution immediately."""

    def test_continue_returns(self) -> None:
        with (
            patch("builtins.input", side_effect=[".continue"]),
            patch("execsql.debug.repl._write"),
        ):
            _debug_repl()  # should return normally

    def test_c_returns(self) -> None:
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch("execsql.debug.repl._write"),
        ):
            _debug_repl()

    def test_continue_case_insensitive(self) -> None:
        with (
            patch("builtins.input", side_effect=[".CONTINUE"]),
            patch("execsql.debug.repl._write"),
        ):
            _debug_repl()


class TestDebugReplAbort:
    """'.abort', '.q' raise SystemExit(1)."""

    @pytest.mark.parametrize("cmd", [".abort", ".q", ".quit", ".ABORT", ".Q"])
    def test_abort_raises_system_exit(self, cmd: str) -> None:
        with (
            patch("builtins.input", side_effect=[cmd]),
            patch("execsql.debug.repl._write"),
            pytest.raises(SystemExit) as exc_info,
        ):
            _debug_repl()
        assert exc_info.value.code == 1


class TestDebugReplEOFAndInterrupt:
    """EOF and KeyboardInterrupt both resume execution."""

    def test_eof_resumes(self) -> None:
        with (
            patch("builtins.input", side_effect=EOFError),
            patch("execsql.debug.repl._write"),
        ):
            _debug_repl()  # should return normally

    def test_keyboard_interrupt_resumes(self) -> None:
        with (
            patch("builtins.input", side_effect=KeyboardInterrupt),
            patch("execsql.debug.repl._write"),
        ):
            _debug_repl()


class TestDebugReplEmptyLine:
    """Empty input is ignored; loop continues until another command."""

    def test_empty_then_continue(self) -> None:
        with (
            patch("builtins.input", side_effect=["", "  ", ".c"]),
            patch("execsql.debug.repl._write"),
        ):
            _debug_repl()


# ---------------------------------------------------------------------------
# _debug_repl — dot-prefixed informational commands
# ---------------------------------------------------------------------------


class TestDebugReplHelp:
    """'.help' writes the help text."""

    def test_help_writes_text(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".help", ".c"]),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert ".continue" in combined
        assert ".abort" in combined
        assert ".vars" in combined
        assert ".stack" in combined


class TestDebugReplUnknownDotCommand:
    """Unknown dot-commands produce an error message."""

    def test_unknown_dot_command_prints_error(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".frobnicator", ".c"]),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "Unknown command" in combined
        assert ".frobnicator" in combined


class TestDebugReplVariableLookup:
    """Bare words that aren't dot-commands or SQL are treated as variable lookups."""

    def test_known_var_prints_value(self) -> None:
        sv = _make_subvars({"logfile": "testing.log"})
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=["logfile", ".c"]),
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "testing.log" in combined

    def test_unknown_bare_word_shows_undefined(self) -> None:
        sv = _make_subvars({})
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=["nonexistent", ".c"]),
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "undefined" in combined

    def test_sigil_prefixed_var(self) -> None:
        sv = _make_subvars({"$arg_1": "hello"})
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=["$ARG_1", ".c"]),
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "hello" in combined


# ---------------------------------------------------------------------------
# _print_all_vars
# ---------------------------------------------------------------------------


class TestPrintAllVars:
    """_print_all_vars lists variables grouped by type."""

    def test_no_subvars_reports_none(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "subvars", None),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_all_vars()
        assert any("no substitution" in s for s in written)

    def test_empty_subvars_reports_none(self) -> None:
        sv = _make_subvars({})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_all_vars()
        assert any("no substitution" in s for s in written)

    def test_lists_variables(self) -> None:
        sv = _make_subvars({"$foo": "bar", "$baz": "qux"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_all_vars()
        combined = "".join(written)
        assert "$foo" in combined
        assert "bar" in combined
        # Group label is now "System ($)" (shortened from "System variables ($)")
        assert "System ($)" in combined

    def test_env_vars_hidden_by_default(self) -> None:
        sv = _make_subvars({"&home": "/Users/me", "myvar": "val"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_all_vars()
        combined = "".join(written)
        assert "myvar" in combined
        assert "&home" not in combined

    def test_env_vars_shown_with_include_env(self) -> None:
        sv = _make_subvars({"&home": "/Users/me", "myvar": "val"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_all_vars(include_env=True)
        combined = "".join(written)
        assert "&home" in combined
        # Group label is now "Environment (&)" (shortened from "Environment variables (&)")
        assert "Environment (&)" in combined


# ---------------------------------------------------------------------------
# _print_var
# ---------------------------------------------------------------------------


class TestPrintVar:
    """_print_var prints a single variable's value."""

    def test_undefined_variable(self) -> None:
        sv = _make_subvars({"$known": "value"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_var("$unknown")
        assert any("undefined" in s for s in written)

    def test_defined_variable(self) -> None:
        sv = _make_subvars({"$myvar": "hello"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_var("$myvar")
        combined = "".join(written)
        assert "$myvar" in combined
        assert "hello" in combined

    def test_sigil_stripped_fallback(self) -> None:
        sv = _make_subvars({"logfile": "test.log"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_var("$logfile")
        combined = "".join(written)
        assert "test.log" in combined

    def test_no_subvars_initialised(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "subvars", None),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_var("$anything")
        assert any("not initialised" in s for s in written)


# ---------------------------------------------------------------------------
# _print_stack
# ---------------------------------------------------------------------------


class TestPrintStack:
    """_print_stack shows the command-list stack."""

    def test_empty_stack(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "commandliststack", []),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_stack()
        assert any("empty" in s for s in written)

    def test_nonempty_stack(self) -> None:
        fake_cmdlist = MagicMock()
        fake_cmdlist.listname = "my_script.sql"
        fake_cmdlist.cmdptr = 5
        written: list[str] = []
        with (
            patch.object(_state, "commandliststack", [fake_cmdlist]),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_stack()
        combined = "".join(written)
        assert "my_script.sql" in combined
        assert "5" in combined


# ---------------------------------------------------------------------------
# _run_sql
# ---------------------------------------------------------------------------


class TestRunSql:
    """_run_sql executes SQL and pretty-prints results."""

    def test_no_db_connection(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "dbs", None),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _run_sql("SELECT 1;")
        assert any("no database connection" in s for s in written)

    def test_sql_error(self) -> None:
        db = MagicMock()
        db.select_data.side_effect = Exception("syntax error")
        dbs = MagicMock()
        dbs.current.return_value = db
        written: list[str] = []
        with (
            patch.object(_state, "dbs", dbs),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _run_sql("INVALID;")
        assert any("SQL error" in s for s in written)
        assert any("syntax error" in s for s in written)

    def test_pretty_print_results(self) -> None:
        db = MagicMock()
        db.select_data.return_value = (["id", "name"], [[1, "Alice"], [2, "Bob"]])
        dbs = MagicMock()
        dbs.current.return_value = db
        written: list[str] = []
        with (
            patch.object(_state, "dbs", dbs),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _run_sql("SELECT id, name FROM users;")
        combined = "".join(written)
        assert "id" in combined
        assert "name" in combined
        assert "Alice" in combined
        assert "Bob" in combined
        assert "2 rows" in combined

    def test_single_row_label(self) -> None:
        db = MagicMock()
        db.select_data.return_value = (["val"], [[42]])
        dbs = MagicMock()
        dbs.current.return_value = db
        written: list[str] = []
        with (
            patch.object(_state, "dbs", dbs),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _run_sql("SELECT 42;")
        combined = "".join(written)
        assert "1 row" in combined
        assert "1 rows" not in combined

    def test_null_value_displayed(self) -> None:
        db = MagicMock()
        db.select_data.return_value = (["col"], [[None]])
        dbs = MagicMock()
        dbs.current.return_value = db
        written: list[str] = []
        with (
            patch.object(_state, "dbs", dbs),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _run_sql("SELECT NULL;")
        combined = "".join(written)
        assert "NULL" in combined

    def test_sql_executed_from_repl(self) -> None:
        db = MagicMock()
        db.select_data.return_value = (["n"], [[7]])
        dbs = MagicMock()
        dbs.current.return_value = db
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=["SELECT 7;", ".c"]),
            patch.object(_state, "dbs", dbs),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        db.select_data.assert_called_once_with("SELECT 7;")


# ---------------------------------------------------------------------------
# step mode
# ---------------------------------------------------------------------------


class TestStepMode:
    """'.next' / '.n' enable step_mode and return from the REPL."""

    @pytest.mark.parametrize("cmd", [".next", ".n", ".NEXT", ".N"])
    def test_next_enables_step_mode_and_returns(self, cmd: str) -> None:
        with (
            patch("builtins.input", side_effect=[cmd]),
            patch("execsql.debug.repl._write"),
            patch("execsql.debug.repl._enable_step_mode") as mock_enable,
        ):
            _debug_repl()
        mock_enable.assert_called_once()

    def test_enable_step_mode_sets_flag(self) -> None:
        original = _state.step_mode
        try:
            _state.step_mode = False
            _enable_step_mode()
            assert _state.step_mode is True
        finally:
            _state.step_mode = original


# ---------------------------------------------------------------------------
# _print_where
# ---------------------------------------------------------------------------


def _make_script_cmd(
    source: str = "myscript.sql",
    line_no: int = 42,
    command_type: str = "sql",
    cmdline: str = "SELECT 1;",
) -> MagicMock:
    """Return a mock ScriptCmd."""
    cmd = MagicMock()
    cmd.source = source
    cmd.line_no = line_no
    cmd.command_type = command_type
    cmd.command.commandline.return_value = cmdline
    return cmd


class TestPrintWhere:
    """_print_where displays the current script location and upcoming statement."""

    def test_none_last_command_shows_unknown(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "last_command", None),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_where()
        combined = "".join(written)
        assert "position unknown" in combined

    def test_shows_filename_and_line(self) -> None:
        lc = _make_script_cmd(source="/path/to/myscript.sql", line_no=42, command_type="sql", cmdline="SELECT 1;")
        written: list[str] = []
        with (
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_where()
        combined = "".join(written)
        # Only filename, not the full path
        assert "myscript.sql" in combined
        assert "/path/to/" not in combined
        assert "42" in combined
        assert "(sql)" in combined

    def test_shows_command_text(self) -> None:
        lc = _make_script_cmd(cmdline="SELECT * FROM customers WHERE active = 1;")
        written: list[str] = []
        with (
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_where()
        combined = "".join(written)
        assert "SELECT * FROM customers WHERE active = 1;" in combined
        # The new layout uses a rule + type tag; no arrow character
        assert "\u2192" not in combined

    def test_long_command_text_truncated(self) -> None:
        long_sql = "SELECT " + "a, " * 60 + "b FROM t;"  # well over 120 chars
        lc = _make_script_cmd(cmdline=long_sql)
        written: list[str] = []
        with (
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_where()
        combined = "".join(written)
        # The arrow line should contain truncation indicator
        assert "..." in combined
        # Full long SQL should NOT appear verbatim
        assert long_sql not in combined

    def test_command_text_at_exact_limit_not_truncated(self) -> None:
        exact_sql = "x" * _WHERE_TRUNCATE
        lc = _make_script_cmd(cmdline=exact_sql)
        written: list[str] = []
        with (
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_where()
        combined = "".join(written)
        assert "..." not in combined
        assert exact_sql in combined

    def test_metacommand_type_shown(self) -> None:
        lc = _make_script_cmd(command_type="cmd", cmdline="-- !x! BREAKPOINT")
        written: list[str] = []
        with (
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _print_where()
        combined = "".join(written)
        assert "(cmd)" in combined


class TestDebugReplWhereBanner:
    """The entry banner includes location info; _print_where is NOT called separately on entry."""

    def test_banner_includes_location(self) -> None:
        lc = _make_script_cmd(source="my_script.sql", line_no=7)
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        # Location appears in the rule label
        assert "my_script.sql:7" in combined
        # Label word appears (color is off in tests — not a TTY)
        assert "Breakpoint" in combined

    def test_banner_shows_unknown_when_no_last_command(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch.object(_state, "last_command", None),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        # When there is no last_command the rule label contains only "Breakpoint"
        # and the location line is absent; the help hint is still shown
        assert "Breakpoint" in combined
        # "(position unknown)" is no longer part of the banner — it was removed
        # in the new layout (the rule simply omits location info)
        assert "my_script.sql" not in combined

    def test_step_label_shown_when_step_true(self) -> None:
        """_debug_repl(step=True) shows 'Step' instead of 'Breakpoint'."""
        lc = _make_script_cmd(source="my_script.sql", line_no=9)
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl(step=True)
        combined = "".join(written)
        assert "Step" in combined
        assert "Breakpoint" not in combined

    def test_breakpoint_label_shown_when_step_false(self) -> None:
        """_debug_repl(step=False) (default) shows 'Breakpoint'."""
        lc = _make_script_cmd(source="my_script.sql", line_no=9)
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl(step=False)
        combined = "".join(written)
        assert "Breakpoint" in combined
        assert "Step" not in combined

    def test_print_where_not_called_on_entry(self) -> None:
        """_print_where is no longer called separately on REPL entry.

        The new layout builds the location rule inline in _debug_repl.
        """
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch("execsql.debug.repl._write"),
            patch("execsql.debug.repl._print_where") as mock_where,
            patch.object(_state, "last_command", None),
        ):
            _debug_repl()
        mock_where.assert_not_called()


class TestDebugReplWhereCommand:
    """.where / .w dot-commands dispatch to _print_where."""

    @pytest.mark.parametrize("cmd", [".where", ".w", ".WHERE", ".W"])
    def test_where_command_calls_print_where(self, cmd: str) -> None:
        with (
            patch("builtins.input", side_effect=[cmd, ".c"]),
            patch("execsql.debug.repl._write"),
            patch("execsql.debug.repl._print_where") as mock_where,
            patch.object(_state, "last_command", None),
        ):
            _debug_repl()
        # Called once by the .where command (no longer called automatically on entry)
        assert mock_where.call_count == 1

    def test_where_in_help_text(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".help", ".c"]),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert ".where" in combined


# ---------------------------------------------------------------------------
# _write fallback
# ---------------------------------------------------------------------------


class TestWriteFallback:
    """_write falls back to sys.stdout when _state.output is None."""

    def test_falls_back_to_stdout(self, capsys) -> None:
        with patch.object(_state, "output", None):
            _write("hello stdout\n")
        captured = capsys.readouterr()
        assert "hello stdout" in captured.out

    def test_uses_state_output_when_set(self) -> None:
        out = _make_output()
        with patch.object(_state, "output", out):
            _write("hello output\n")
        out.write.assert_called_once_with("hello output\n")


# ---------------------------------------------------------------------------
# _set_var and .set / .s dispatch
# ---------------------------------------------------------------------------


class TestSetVar:
    """_set_var sets a substitution variable via subvars.add_substitution."""

    def test_set_var_calls_add_substitution(self) -> None:
        sv = MagicMock()
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _set_var("myvar", "hello")
        sv.add_substitution.assert_called_once_with("myvar", "hello")
        assert any("myvar" in s and "hello" in s for s in written)

    def test_set_var_subvars_none_prints_error(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "subvars", None),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _set_var("anyvar", "anyval")
        combined = "".join(written)
        assert "Error" in combined or "error" in combined

    def test_set_var_empty_value(self) -> None:
        sv = MagicMock()
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _set_var("myvar", "")
        sv.add_substitution.assert_called_once_with("myvar", "")


class TestSetDotCommand:
    """.set VAR VAL and .s VAR VAL dispatch to _set_var."""

    def test_set_command_dispatches(self) -> None:
        with (
            patch("builtins.input", side_effect=[".set foo bar", ".c"]),
            patch("execsql.debug.repl._write"),
            patch("execsql.debug.repl._set_var") as mock_set,
        ):
            _debug_repl()
        mock_set.assert_called_once_with("foo", "bar")

    def test_set_shorthand_dispatches(self) -> None:
        with (
            patch("builtins.input", side_effect=[".s foo bar", ".c"]),
            patch("execsql.debug.repl._write"),
            patch("execsql.debug.repl._set_var") as mock_set,
        ):
            _debug_repl()
        mock_set.assert_called_once_with("foo", "bar")

    def test_set_no_args_prints_usage(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".set", ".c"]),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "Usage" in combined or "usage" in combined

    def test_s_no_args_prints_usage(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".s", ".c"]),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "Usage" in combined or "usage" in combined

    def test_set_multiword_value(self) -> None:
        """Value can contain spaces — everything after varname is the value."""
        with (
            patch("builtins.input", side_effect=[".set myvar hello world", ".c"]),
            patch("execsql.debug.repl._write"),
            patch("execsql.debug.repl._set_var") as mock_set,
        ):
            _debug_repl()
        mock_set.assert_called_once_with("myvar", "hello world")

    def test_stack_not_confused_with_s_shorthand(self) -> None:
        """.stack must not be matched by the .s shorthand handler."""
        with (
            patch("builtins.input", side_effect=[".stack", ".c"]),
            patch("execsql.debug.repl._write"),
            patch("execsql.debug.repl._print_stack") as mock_stack,
            patch("execsql.debug.repl._set_var") as mock_set,
        ):
            _debug_repl()
        mock_stack.assert_called_once()
        mock_set.assert_not_called()

    def test_set_in_help_text(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".help", ".c"]),
            patch("execsql.debug.repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert ".set" in combined


# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------


class TestUseColor:
    """_use_color() returns False for non-TTY output and when env vars are set."""

    def test_false_when_no_color_env(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert _use_color() is False

    def test_false_when_execsql_no_color_env(self) -> None:
        with patch.dict(os.environ, {"EXECSQL_NO_COLOR": "1"}):
            assert _use_color() is False

    def test_false_when_stdout_not_tty(self) -> None:
        # In the test runner stdout is not a TTY
        with (
            patch.object(_state, "output", None),
            patch.object(sys.stdout, "isatty", return_value=False),
        ):
            assert _use_color() is False

    def test_true_when_stdout_is_tty_and_no_env(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "EXECSQL_NO_COLOR")}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(_state, "output", None),
            patch.object(sys.stdout, "isatty", return_value=True),
        ):
            assert _use_color() is True

    def test_false_when_state_output_not_tty(self) -> None:
        out = MagicMock()
        out.isatty = MagicMock(return_value=False)
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "EXECSQL_NO_COLOR")}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(_state, "output", out),
        ):
            assert _use_color() is False

    def test_true_when_state_output_is_tty(self) -> None:
        out = MagicMock()
        out.isatty = MagicMock(return_value=True)
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "EXECSQL_NO_COLOR")}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(_state, "output", out),
        ):
            assert _use_color() is True


class TestColorHelper:
    """_c() wraps text in ANSI codes when color is on, returns plain text when off."""

    def test_plain_when_color_off(self) -> None:
        with patch("execsql.debug.repl._use_color", return_value=False):
            result = _c(_CYAN, "hello")
        assert result == "hello"
        assert "\033[" not in result

    def test_ansi_wrapped_when_color_on(self) -> None:
        with patch("execsql.debug.repl._use_color", return_value=True):
            result = _c(_CYAN, "hello")
        assert "\033[" in result
        assert "hello" in result

    def test_reset_appended_when_color_on(self) -> None:
        with patch("execsql.debug.repl._use_color", return_value=True):
            result = _c(_DIM, "text")
        assert result.endswith("\033[0m")


class TestWriteRule:
    """_write_rule() outputs a line containing the label and dashes."""

    def test_rule_contains_label(self) -> None:
        written: list[str] = []
        with patch("execsql.debug.repl._write", side_effect=written.append):
            _write_rule(" Hello ")
        combined = "".join(written)
        assert "Hello" in combined
        assert combined.endswith("\n")

    def test_rule_contains_dashes(self) -> None:
        written: list[str] = []
        with patch("execsql.debug.repl._write", side_effect=written.append):
            _write_rule(" X ")
        combined = "".join(written)
        # At minimum the suffix of 40 dashes should be visible (color is off in tests)
        assert "─" * 5 in combined


class TestColorInOutput:
    """Verify ANSI codes appear in output when color is explicitly enabled."""

    def test_ansi_in_entry_banner_when_color_on(self) -> None:
        lc = _make_script_cmd(source="test.sql", line_no=1)
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
            patch("execsql.debug.repl._use_color", return_value=True),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "\033[" in combined

    def test_no_ansi_in_entry_banner_when_color_off(self) -> None:
        lc = _make_script_cmd(source="test.sql", line_no=1)
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=[".c"]),
            patch.object(_state, "last_command", lc),
            patch("execsql.debug.repl._write", side_effect=written.append),
            patch("execsql.debug.repl._use_color", return_value=False),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "\033[" not in combined
