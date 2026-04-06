"""Tests for the --lint static analysis feature.

Tests exercise :func:`execsql.cli.lint._lint_script` directly as well as the
Typer CLI layer via the CliRunner.
"""

from __future__ import annotations

import textwrap
from unittest.mock import MagicMock


from execsql.cli.lint import _lint_script, _print_lint_results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metacmd(stmt: str, source: str = "test.sql", line_no: int = 1) -> MagicMock:
    """Return a mock ScriptCmd representing a metacommand."""
    cmd = MagicMock()
    cmd.command_type = "cmd"
    cmd.source = source
    cmd.line_no = line_no
    cmd.command = MagicMock()
    cmd.command.statement = stmt
    return cmd


def _make_sql(stmt: str, source: str = "test.sql", line_no: int = 1) -> MagicMock:
    """Return a mock ScriptCmd representing a SQL statement."""
    cmd = MagicMock()
    cmd.command_type = "sql"
    cmd.source = source
    cmd.line_no = line_no
    cmd.command = MagicMock()
    cmd.command.statement = stmt
    return cmd


def _make_cmdlist(cmds: list) -> MagicMock:
    """Return a mock CommandList containing *cmds*."""
    cl = MagicMock()
    cl.cmdlist = cmds
    return cl


# ---------------------------------------------------------------------------
# Empty script
# ---------------------------------------------------------------------------


class TestEmptyScript:
    def test_none_cmdlist_returns_warning(self):
        issues = _lint_script(None)
        assert issues
        sevs = [s for s, *_ in issues]
        assert "warning" in sevs
        assert not any(s == "error" for s in sevs)

    def test_empty_cmdlist_returns_warning(self):
        cl = _make_cmdlist([])
        issues = _lint_script(cl)
        sevs = [s for s, *_ in issues]
        assert "warning" in sevs
        assert not any(s == "error" for s in sevs)

    def test_empty_cmdlist_exit_code_zero(self):
        issues = _lint_script(_make_cmdlist([]))
        code = _print_lint_results(issues, "test.sql")
        assert code == 0


# ---------------------------------------------------------------------------
# IF / ENDIF matching
# ---------------------------------------------------------------------------


class TestIfEndif:
    def test_matched_if_endif_no_issues(self):
        cmds = [
            _make_metacmd("IF (IS_TRUE x)", line_no=1),
            _make_sql("SELECT 1;", line_no=2),
            _make_metacmd("ENDIF", line_no=3),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_unmatched_if_reports_error(self):
        cmds = [
            _make_metacmd("IF (IS_TRUE x)", line_no=1),
            _make_sql("SELECT 1;", line_no=2),
            # Missing ENDIF
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [(s, msg) for s, _, _, msg in issues if s == "error"]
        assert errors
        assert any("IF" in msg for _, msg in errors)

    def test_endif_without_if_reports_error(self):
        cmds = [
            _make_metacmd("ENDIF", line_no=1),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors
        assert any("ENDIF" in msg for msg in errors)

    def test_nested_if_matched(self):
        cmds = [
            _make_metacmd("IF (IS_TRUE x)", line_no=1),
            _make_metacmd("IF (IS_TRUE y)", line_no=2),
            _make_metacmd("ENDIF", line_no=3),
            _make_metacmd("ENDIF", line_no=4),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_nested_if_one_missing_endif_error(self):
        cmds = [
            _make_metacmd("IF (IS_TRUE x)", line_no=1),
            _make_metacmd("IF (IS_TRUE y)", line_no=2),
            _make_metacmd("ENDIF", line_no=3),
            # Missing second ENDIF
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors

    def test_inline_if_does_not_open_block(self):
        # IF(...) { cmd } is a single-line form — should NOT require ENDIF
        cmds = [
            _make_metacmd("IF (IS_TRUE x) { HALT }", line_no=1),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_else_without_if_reports_error(self):
        cmds = [_make_metacmd("ELSE", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors

    def test_elseif_without_if_reports_error(self):
        cmds = [_make_metacmd("ELSEIF (IS_TRUE y)", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors

    def test_clean_script_exit_code_zero(self):
        cmds = [
            _make_metacmd("IF (IS_TRUE x)", line_no=1),
            _make_metacmd("ENDIF", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        code = _print_lint_results(issues, "test.sql")
        assert code == 0

    def test_error_script_exit_code_one(self):
        cmds = [_make_metacmd("IF (IS_TRUE x)", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        code = _print_lint_results(issues, "test.sql")
        assert code == 1


# ---------------------------------------------------------------------------
# LOOP / END LOOP matching
# ---------------------------------------------------------------------------


class TestLoopEndloop:
    def test_matched_loop_end_loop_no_issues(self):
        cmds = [
            _make_metacmd("LOOP WHILE (IS_TRUE x)", line_no=1),
            _make_sql("SELECT 1;", line_no=2),
            _make_metacmd("END LOOP", line_no=3),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_unmatched_loop_reports_error(self):
        cmds = [
            _make_metacmd("LOOP UNTIL (IS_FALSE x)", line_no=1),
            _make_sql("SELECT 1;", line_no=2),
            # Missing END LOOP
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors
        assert any("LOOP" in msg for msg in errors)

    def test_end_loop_without_loop_reports_error(self):
        cmds = [_make_metacmd("END LOOP", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors
        assert any("END LOOP" in msg for msg in errors)

    def test_nested_loop_matched(self):
        cmds = [
            _make_metacmd("LOOP WHILE (IS_TRUE x)", line_no=1),
            _make_metacmd("LOOP UNTIL (IS_FALSE y)", line_no=2),
            _make_metacmd("END LOOP", line_no=3),
            _make_metacmd("END LOOP", line_no=4),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues


# ---------------------------------------------------------------------------
# BEGIN BATCH / END BATCH matching
# ---------------------------------------------------------------------------


class TestBatchMatching:
    def test_matched_begin_end_batch_no_issues(self):
        cmds = [
            _make_metacmd("BEGIN BATCH", line_no=1),
            _make_sql("INSERT INTO t VALUES (1);", line_no=2),
            _make_metacmd("END BATCH", line_no=3),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_unmatched_begin_batch_reports_error(self):
        cmds = [
            _make_metacmd("BEGIN BATCH", line_no=1),
            # Missing END BATCH
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors
        assert any("BEGIN BATCH" in msg for msg in errors)

    def test_end_batch_without_begin_batch_reports_error(self):
        cmds = [_make_metacmd("END BATCH", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert errors


# ---------------------------------------------------------------------------
# Undefined variable references
# ---------------------------------------------------------------------------


class TestUndefinedVariables:
    def test_builtin_vars_discovered(self):
        """_BUILTIN_VARS should be populated by scanning the source."""
        from execsql.cli.lint import _BUILTIN_VARS

        assert len(_BUILTIN_VARS) > 0
        for expected in ("USER", "CURRENT_SCRIPT", "LAST_ROWCOUNT", "PATHSEP"):
            assert expected in _BUILTIN_VARS, f"{expected} missing from _BUILTIN_VARS"

    def test_builtin_var_no_warning(self):
        cmds = [_make_metacmd("WRITE !!$USER!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_user_defined_var_no_warning(self):
        cmds = [
            _make_metacmd("SUB myvar hello", line_no=1),
            _make_metacmd("WRITE !!myvar!!", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_forward_reference_no_warning(self):
        """Variables referenced before their SUB definition should not warn."""
        cmds = [
            _make_metacmd("WRITE !!myvar!!", line_no=1),
            _make_metacmd("SUB myvar hello", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        warnings = [msg for s, _, _, msg in issues if s == "warning" and "myvar" in msg]
        assert not warnings

    def test_undefined_var_raises_warning(self):
        cmds = [_make_metacmd("WRITE !!$UNDEFINED_CUSTOM_VAR!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        warnings = [msg for s, _, _, msg in issues if s == "warning"]
        assert warnings
        assert any("UNDEFINED_CUSTOM_VAR" in msg for msg in warnings)

    def test_arg_var_no_warning(self):
        """$ARG_N variables are set via -a; should not produce a warning."""
        cmds = [_make_metacmd("WRITE !!$ARG_1!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_counter_var_no_warning(self):
        """$COUNTER_N variables are managed by CounterVars."""
        cmds = [_make_metacmd("WRITE !!$COUNTER_1!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_env_var_no_warning(self):
        """&-prefix variables are environment variables — always available."""
        cmds = [_make_metacmd("WRITE !!&HOME!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_undefined_var_in_sql_raises_warning(self):
        cmds = [_make_sql("SELECT !!$CUSTOM_UNDEF!!;", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        warnings = [msg for s, _, _, msg in issues if s == "warning"]
        assert warnings

    def test_undefined_var_is_warning_not_error(self):
        """Undefined variables should be warnings (not errors) — could come from config."""
        cmds = [_make_metacmd("WRITE !!$DEFINITELY_NOT_DEFINED!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        # No errors — only warnings
        assert not any(s == "error" for s, *_ in issues)
        assert any(s == "warning" for s, *_ in issues)

    def test_undefined_var_warning_only_exit_code_zero(self):
        cmds = [_make_metacmd("WRITE !!$UNDEF_CUSTOM!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        code = _print_lint_results(issues, "test.sql")
        assert code == 0


# ---------------------------------------------------------------------------
# INCLUDE file existence
# ---------------------------------------------------------------------------


class TestIncludeFileExistence:
    def test_existing_include_no_warning(self, tmp_path):
        inc_file = tmp_path / "sub.sql"
        inc_file.write_text("SELECT 1;")
        script_path = str(tmp_path / "main.sql")
        cmds = [_make_metacmd(f"INCLUDE {inc_file.name}", source=script_path, line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds), script_path=script_path)
        assert not issues

    def test_missing_include_reports_warning(self, tmp_path):
        script_path = str(tmp_path / "main.sql")
        cmds = [_make_metacmd("INCLUDE does_not_exist.sql", source=script_path, line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds), script_path=script_path)
        warnings = [msg for s, _, _, msg in issues if s == "warning"]
        assert warnings
        assert any("does_not_exist.sql" in msg for msg in warnings)

    def test_include_if_exists_never_warns(self, tmp_path):
        """INCLUDE IF EXISTS should never produce a missing-file warning."""
        script_path = str(tmp_path / "main.sql")
        cmds = [_make_metacmd("INCLUDE IF EXISTS does_not_exist.sql", source=script_path, line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds), script_path=script_path)
        assert not any(s == "warning" and "does_not_exist.sql" in msg for s, _, _, msg in issues)

    def test_include_with_variable_path_skipped(self, tmp_path):
        """Paths containing !!VAR!! tokens should not be checked."""
        script_path = str(tmp_path / "main.sql")
        cmds = [_make_metacmd("INCLUDE !!$SCRIPT_DIR!!sub.sql", source=script_path, line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds), script_path=script_path)
        # No missing-file warning — path contains a variable
        assert not any(s == "warning" and "INCLUDE target" in msg for s, _, _, msg in issues)

    def test_missing_include_is_warning_not_error(self, tmp_path):
        script_path = str(tmp_path / "main.sql")
        cmds = [_make_metacmd("INCLUDE missing.sql", source=script_path, line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds), script_path=script_path)
        assert not any(s == "error" for s, *_ in issues)
        assert any(s == "warning" for s, *_ in issues)


# ---------------------------------------------------------------------------
# Mixed scenarios
# ---------------------------------------------------------------------------


class TestMixedScenarios:
    def test_clean_script_no_issues(self):
        cmds = [
            _make_metacmd("SUB myvar hello", line_no=1),
            _make_metacmd("IF (IS_TRUE x)", line_no=2),
            _make_sql("SELECT !!myvar!!;", line_no=3),
            _make_metacmd("ENDIF", line_no=4),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_multiple_errors_all_reported(self):
        cmds = [
            _make_metacmd("IF (IS_TRUE x)", line_no=1),  # unclosed IF
            _make_metacmd("BEGIN BATCH", line_no=2),  # unclosed BEGIN BATCH
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        errors = [msg for s, _, _, msg in issues if s == "error"]
        assert len(errors) >= 2

    def test_warnings_alone_exit_code_zero(self):
        cmds = [_make_metacmd("WRITE !!$SOME_CUSTOM_UNDEF!!", line_no=1)]
        issues = _lint_script(_make_cmdlist(cmds))
        code = _print_lint_results(issues, "test.sql")
        assert code == 0

    def test_errors_alone_exit_code_one(self):
        cmds = [_make_metacmd("ENDIF", line_no=1)]  # ENDIF without IF
        issues = _lint_script(_make_cmdlist(cmds))
        code = _print_lint_results(issues, "test.sql")
        assert code == 1

    def test_errors_and_warnings_exit_code_one(self):
        cmds = [
            _make_metacmd("ENDIF", line_no=1),  # error
            _make_metacmd("WRITE !!$CUSTOM_UNDEF!!", line_no=2),  # warning
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        code = _print_lint_results(issues, "test.sql")
        assert code == 1


# ---------------------------------------------------------------------------
# SUB-family variable definitions
# ---------------------------------------------------------------------------


class TestSubFamilyVariables:
    """SUB_EMPTY, SUB_ADD, SUB_APPEND, and SUBDATA should register variables."""

    def test_sub_empty_defines_var(self):
        cmds = [
            _make_metacmd("SUB_EMPTY myvar", line_no=1),
            _make_metacmd("WRITE !!myvar!!", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_sub_add_defines_var(self):
        cmds = [
            _make_metacmd("SUB_ADD counter 1", line_no=1),
            _make_metacmd("WRITE !!counter!!", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_sub_append_defines_var(self):
        cmds = [
            _make_metacmd("SUB_APPEND mylist value", line_no=1),
            _make_metacmd("WRITE !!mylist!!", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_subdata_defines_var(self):
        cmds = [
            _make_metacmd("SUBDATA myresult some_view", line_no=1),
            _make_metacmd("WRITE !!myresult!!", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues

    def test_sub_ini_reads_ini_file(self, tmp_path):
        """SUB_INI should read the INI file and register section keys."""
        ini = tmp_path / "config.ini"
        ini.write_text("[vars]\nmy_setting = hello\nother_val = world\n")
        script_path = str(tmp_path / "main.sql")
        cmds = [
            _make_metacmd(f"SUB_INI {ini.name} SECTION vars", source=script_path, line_no=1),
            _make_metacmd("WRITE !!my_setting!!", source=script_path, line_no=2),
            _make_metacmd("WRITE !!other_val!!", source=script_path, line_no=3),
        ]
        issues = _lint_script(_make_cmdlist(cmds), script_path=script_path)
        assert not issues

    def test_sub_ini_missing_file_no_crash(self):
        """SUB_INI with a missing INI file should not crash."""
        cmds = [
            _make_metacmd("SUB_INI missing.conf SECTION vars", line_no=1),
            _make_metacmd("WRITE !!unknown!!", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        warnings = [msg for s, _, _, msg in issues if s == "warning" and "unknown" in msg]
        assert warnings  # still warns since file doesn't exist

    def test_sub_ini_with_file_keyword(self, tmp_path):
        """SUB_INI FILE <path> SECTION <sect> form should work."""
        ini = tmp_path / "db.conf"
        ini.write_text("[run]\nrun_no = 5\n")
        script_path = str(tmp_path / "main.sql")
        cmds = [
            _make_metacmd(f"SUB_INI FILE {ini.name} SECTION run", source=script_path, line_no=1),
            _make_metacmd("WRITE !!run_no!!", source=script_path, line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds), script_path=script_path)
        assert not issues

    def test_sub_empty_with_prefix_defines_var(self):
        """Variables with + or ~ prefix should still be tracked."""
        cmds = [
            _make_metacmd("SUB_EMPTY +myvar", line_no=1),
            _make_metacmd("WRITE !!myvar!!", line_no=2),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        assert not issues


# ---------------------------------------------------------------------------
# EXECUTE SCRIPT flow analysis
# ---------------------------------------------------------------------------


class TestExecuteScriptFlow:
    """EXECUTE SCRIPT should descend into named script blocks."""

    def _setup_savedscripts(self, script_cmds):
        """Set up _state.savedscripts with a mock script block."""
        import execsql.state as _state

        saved_cl = _make_cmdlist(script_cmds)
        original = getattr(_state, "savedscripts", {}).copy()
        _state.savedscripts = {"myscript": saved_cl}
        return original

    def _restore_savedscripts(self, original):
        import execsql.state as _state

        _state.savedscripts = original

    def test_execute_script_propagates_vars(self):
        """Variables defined in a script block should be visible after EXECUTE SCRIPT."""
        script_cmds = [
            _make_metacmd("SUB run_tag 001", source="test.sql", line_no=10),
        ]
        original = self._setup_savedscripts(script_cmds)
        try:
            cmds = [
                _make_metacmd("EXECUTE SCRIPT myscript", line_no=1),
                _make_metacmd("WRITE !!run_tag!!", line_no=2),
            ]
            issues = _lint_script(_make_cmdlist(cmds))
            warnings = [msg for s, _, _, msg in issues if s == "warning" and "run_tag" in msg]
            assert not warnings
        finally:
            self._restore_savedscripts(original)

    def test_execute_script_unknown_target_warns(self):
        """EXECUTE SCRIPT targeting an unknown block should warn."""
        cmds = [
            _make_metacmd("EXECUTE SCRIPT nonexistent", line_no=1),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        warnings = [msg for s, _, _, msg in issues if s == "warning" and "nonexistent" in msg]
        assert warnings

    def test_execute_script_if_exists_unknown_no_warning(self):
        """EXECUTE SCRIPT IF EXISTS targeting unknown block should not warn."""
        cmds = [
            _make_metacmd("EXECUTE SCRIPT IF EXISTS nonexistent", line_no=1),
        ]
        issues = _lint_script(_make_cmdlist(cmds))
        warnings = [msg for s, _, _, msg in issues if s == "warning" and "nonexistent" in msg]
        assert not warnings

    def test_execute_script_structural_issues_reported(self):
        """Structural issues in the script block should be reported."""
        script_cmds = [
            _make_metacmd("IF (IS_TRUE x)", source="test.sql", line_no=10),
            # Missing ENDIF
        ]
        original = self._setup_savedscripts(script_cmds)
        try:
            cmds = [
                _make_metacmd("EXECUTE SCRIPT myscript", line_no=1),
            ]
            issues = _lint_script(_make_cmdlist(cmds))
            errors = [msg for s, _, _, msg in issues if s == "error"]
            assert errors
            assert any("myscript" in msg for msg in errors)
        finally:
            self._restore_savedscripts(original)

    def test_exec_script_shorthand(self):
        """EXEC SCRIPT (shorthand) should also work."""
        script_cmds = [
            _make_metacmd("SUB myvar hello", source="test.sql", line_no=10),
        ]
        original = self._setup_savedscripts(script_cmds)
        try:
            cmds = [
                _make_metacmd("EXEC SCRIPT myscript", line_no=1),
                _make_metacmd("WRITE !!myvar!!", line_no=2),
            ]
            issues = _lint_script(_make_cmdlist(cmds))
            warnings = [msg for s, _, _, msg in issues if s == "warning" and "myvar" in msg]
            assert not warnings
        finally:
            self._restore_savedscripts(original)

    def test_run_script_alias(self):
        """RUN SCRIPT should also work."""
        script_cmds = [
            _make_metacmd("SUB myvar hello", source="test.sql", line_no=10),
        ]
        original = self._setup_savedscripts(script_cmds)
        try:
            cmds = [
                _make_metacmd("RUN SCRIPT myscript", line_no=1),
                _make_metacmd("WRITE !!myvar!!", line_no=2),
            ]
            issues = _lint_script(_make_cmdlist(cmds))
            warnings = [msg for s, _, _, msg in issues if s == "warning" and "myvar" in msg]
            assert not warnings
        finally:
            self._restore_savedscripts(original)

    def test_circular_script_reference_no_infinite_loop(self):
        """Circular EXECUTE SCRIPT references should not cause infinite recursion."""
        import execsql.state as _state

        # Script A executes script B, script B executes script A
        script_a_cmds = [
            _make_metacmd("EXECUTE SCRIPT script_b", source="test.sql", line_no=10),
        ]
        script_b_cmds = [
            _make_metacmd("EXECUTE SCRIPT script_a", source="test.sql", line_no=20),
        ]
        original = getattr(_state, "savedscripts", {}).copy()
        _state.savedscripts = {
            "script_a": _make_cmdlist(script_a_cmds),
            "script_b": _make_cmdlist(script_b_cmds),
        }
        try:
            cmds = [
                _make_metacmd("EXECUTE SCRIPT script_a", line_no=1),
            ]
            # Should not raise RecursionError
            issues = _lint_script(_make_cmdlist(cmds))
            assert isinstance(issues, list)
        finally:
            _state.savedscripts = original


# ---------------------------------------------------------------------------
# CLI integration (Typer runner)
# ---------------------------------------------------------------------------


class TestLintCli:
    """Integration tests that drive the full CLI layer with --lint."""

    def test_lint_clean_script_exits_zero(self, tmp_path):
        """A syntactically valid script should exit 0."""
        from typer.testing import CliRunner

        from execsql.cli import app

        script = tmp_path / "clean.sql"
        script.write_text(
            textwrap.dedent(
                """\
                -- !x! IF (IS_TRUE 1)
                SELECT 1;
                -- !x! ENDIF
                """,
            ),
        )
        result = CliRunner().invoke(app, ["--lint", str(script)], catch_exceptions=False)
        assert result.exit_code == 0

    def test_lint_unmatched_if_exits_one(self, tmp_path):
        """An unclosed IF block should cause --lint to exit 1."""
        from typer.testing import CliRunner

        from execsql.cli import app

        script = tmp_path / "bad.sql"
        script.write_text(
            textwrap.dedent(
                """\
                -- !x! IF (IS_TRUE 1)
                SELECT 1;
                -- Missing ENDIF
                """,
            ),
        )
        result = CliRunner().invoke(app, ["--lint", str(script)], catch_exceptions=False)
        assert result.exit_code == 1
        assert "IF" in result.output or "error" in result.output.lower()

    def test_lint_missing_include_exits_zero(self, tmp_path):
        """Missing INCLUDE file is a warning, not an error — should exit 0."""
        from typer.testing import CliRunner

        from execsql.cli import app

        script = tmp_path / "inc.sql"
        script.write_text("-- !x! INCLUDE missing_file.sql\n")
        result = CliRunner().invoke(app, ["--lint", str(script)], catch_exceptions=False)
        assert result.exit_code == 0

    def test_lint_output_contains_label(self, tmp_path):
        """The lint output header should mention the script name."""
        from typer.testing import CliRunner

        from execsql.cli import app

        script = tmp_path / "myscript.sql"
        script.write_text("SELECT 1;\n")
        result = CliRunner().invoke(app, ["--lint", str(script)], catch_exceptions=False)
        assert "myscript.sql" in result.output or "Lint" in result.output

    def test_lint_empty_script_exits_zero(self, tmp_path):
        """An empty (comment-only) script should warn but exit 0."""
        from typer.testing import CliRunner

        from execsql.cli import app

        script = tmp_path / "empty.sql"
        script.write_text("-- just a comment\n")
        result = CliRunner().invoke(app, ["--lint", str(script)], catch_exceptions=False)
        assert result.exit_code == 0

    def test_lint_execute_script_propagates_vars(self, tmp_path):
        """Variables set in a script block should not warn after EXECUTE SCRIPT."""
        from typer.testing import CliRunner

        from execsql.cli import app

        script = tmp_path / "main.sql"
        script.write_text(
            textwrap.dedent(
                """\
                -- !x! sub myvar SomeValue
                -- !x! execute script set_vars
                -- !x! write "!!run_tag!!"
                -- !x! write "Done"

                -- !x! begin script set_vars
                    -- !x! sub run_tag 001
                -- !x! end script set_vars
                """,
            ),
        )
        result = CliRunner().invoke(app, ["--lint", str(script)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "run_tag" not in result.output
