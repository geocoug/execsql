"""Unit tests for the BREAKPOINT metacommand and its debug REPL.

Covers:
- x_breakpoint is a no-op when sys.stdin is not a TTY
- 'continue' / 'c' resumes execution
- 'abort' / 'q' / 'quit' raises SystemExit(1)
- 'vars' prints all substitution variables
- '$VARNAME' prints a specific variable value
- 'help' prints help text
- 'stack' prints command-list stack info
- SQL ending with ';' executes and pretty-prints results
- 'next' / 'n' enables step_mode and returns
- Unknown command prints an error message
- EOF (Ctrl-D) resumes execution
- KeyboardInterrupt (Ctrl-C) resumes execution
- _write falls back to stdout when _state.output is None
- step_mode in engine triggers _debug_repl after a statement
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.metacommands.debug_repl import (
    _debug_repl,
    _enable_step_mode,
    _print_all_vars,
    _print_stack,
    _print_var,
    _run_sql,
    _write,
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
            patch("execsql.metacommands.debug_repl._debug_repl") as mock_repl,
        ):
            result = x_breakpoint()
        assert result is None
        mock_repl.assert_not_called()

    def test_calls_repl_when_tty(self) -> None:
        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("execsql.metacommands.debug_repl._debug_repl") as mock_repl,
        ):
            x_breakpoint()
        mock_repl.assert_called_once()


# ---------------------------------------------------------------------------
# _debug_repl — flow control commands
# ---------------------------------------------------------------------------


class TestDebugReplContinue:
    """'continue' and 'c' resume execution immediately."""

    def test_continue_returns(self) -> None:
        with (
            patch("builtins.input", side_effect=["continue"]),
            patch("execsql.metacommands.debug_repl._write"),
        ):
            _debug_repl()  # should return normally

    def test_c_returns(self) -> None:
        with (
            patch("builtins.input", side_effect=["c"]),
            patch("execsql.metacommands.debug_repl._write"),
        ):
            _debug_repl()

    def test_continue_case_insensitive(self) -> None:
        with (
            patch("builtins.input", side_effect=["CONTINUE"]),
            patch("execsql.metacommands.debug_repl._write"),
        ):
            _debug_repl()


class TestDebugReplAbort:
    """'abort', 'q', and 'quit' raise SystemExit(1)."""

    @pytest.mark.parametrize("cmd", ["abort", "q", "quit", "ABORT", "Q"])
    def test_abort_raises_system_exit(self, cmd: str) -> None:
        with (
            patch("builtins.input", side_effect=[cmd]),
            patch("execsql.metacommands.debug_repl._write"),
            pytest.raises(SystemExit) as exc_info,
        ):
            _debug_repl()
        assert exc_info.value.code == 1


class TestDebugReplEOFAndInterrupt:
    """EOF and KeyboardInterrupt both resume execution."""

    def test_eof_resumes(self) -> None:
        with (
            patch("builtins.input", side_effect=EOFError),
            patch("execsql.metacommands.debug_repl._write"),
        ):
            _debug_repl()  # should return normally

    def test_keyboard_interrupt_resumes(self) -> None:
        with (
            patch("builtins.input", side_effect=KeyboardInterrupt),
            patch("execsql.metacommands.debug_repl._write"),
        ):
            _debug_repl()


class TestDebugReplEmptyLine:
    """Empty input is ignored; loop continues until another command."""

    def test_empty_then_continue(self) -> None:
        with (
            patch("builtins.input", side_effect=["", "  ", "c"]),
            patch("execsql.metacommands.debug_repl._write"),
        ):
            _debug_repl()


# ---------------------------------------------------------------------------
# _debug_repl — informational commands
# ---------------------------------------------------------------------------


class TestDebugReplHelp:
    """'help' writes the help text."""

    def test_help_writes_text(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=["help", "c"]),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "continue" in combined
        assert "abort" in combined
        assert "vars" in combined
        assert "stack" in combined


class TestDebugReplUnknownCommand:
    """Unknown commands produce an error message."""

    def test_unknown_command_prints_error(self) -> None:
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=["frobnicator", "c"]),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "Unknown command" in combined
        assert "frobnicator" in combined


# ---------------------------------------------------------------------------
# _print_all_vars
# ---------------------------------------------------------------------------


class TestPrintAllVars:
    """_print_all_vars lists variables or reports that none exist."""

    def test_no_subvars_reports_none(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "subvars", None),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _print_all_vars()
        assert any("no substitution" in s for s in written)

    def test_empty_subvars_reports_none(self) -> None:
        sv = _make_subvars({})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _print_all_vars()
        assert any("no substitution" in s for s in written)

    def test_lists_variables(self) -> None:
        sv = _make_subvars({"$foo": "bar", "$baz": "qux"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _print_all_vars()
        combined = "".join(written)
        assert "$foo" in combined
        assert "bar" in combined
        assert "$baz" in combined
        assert "qux" in combined


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
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _print_var("$unknown")
        assert any("undefined" in s for s in written)

    def test_defined_variable(self) -> None:
        sv = _make_subvars({"$myvar": "hello"})
        written: list[str] = []
        with (
            patch.object(_state, "subvars", sv),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _print_var("$myvar")
        combined = "".join(written)
        assert "$myvar" in combined
        assert "hello" in combined

    def test_no_subvars_initialised(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "subvars", None),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _print_var("$anything")
        assert any("not initialised" in s for s in written)

    def test_var_printed_from_repl(self) -> None:
        sv = _make_subvars({"$x": "42"})
        written: list[str] = []
        with (
            patch("builtins.input", side_effect=["$x", "c"]),
            patch.object(_state, "subvars", sv),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _debug_repl()
        combined = "".join(written)
        assert "42" in combined


# ---------------------------------------------------------------------------
# _print_stack
# ---------------------------------------------------------------------------


class TestPrintStack:
    """_print_stack shows the command-list stack."""

    def test_empty_stack(self) -> None:
        written: list[str] = []
        with (
            patch.object(_state, "commandliststack", []),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
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
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
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
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
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
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
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
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
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
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
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
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
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
            patch("builtins.input", side_effect=["SELECT 7;", "c"]),
            patch.object(_state, "dbs", dbs),
            patch("execsql.metacommands.debug_repl._write", side_effect=written.append),
        ):
            _debug_repl()
        db.select_data.assert_called_once_with("SELECT 7;")


# ---------------------------------------------------------------------------
# step mode
# ---------------------------------------------------------------------------


class TestStepMode:
    """'next' / 'n' enable step_mode and return from the REPL."""

    @pytest.mark.parametrize("cmd", ["next", "n", "NEXT", "N"])
    def test_next_enables_step_mode_and_returns(self, cmd: str) -> None:
        # We cannot use patch.object to observe the final value after it restores.
        # Instead, mock _enable_step_mode and check it was called.
        with (
            patch("builtins.input", side_effect=[cmd]),
            patch("execsql.metacommands.debug_repl._write"),
            patch("execsql.metacommands.debug_repl._enable_step_mode") as mock_enable,
        ):
            _debug_repl()
        mock_enable.assert_called_once()

    def test_enable_step_mode_sets_flag(self) -> None:
        # Save and restore manually so we don't rely on patch.object's restore.
        original = _state.step_mode
        try:
            _state.step_mode = False
            _enable_step_mode()
            assert _state.step_mode is True
        finally:
            _state.step_mode = original


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
