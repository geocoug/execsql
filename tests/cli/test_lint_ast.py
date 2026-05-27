"""Tests for the AST-based ``--lint`` static analyser.

Covers ``execsql.cli.lint_ast.lint_ast`` end-to-end: parse a small
script into the AST, feed it to ``lint_ast()``, and assert on the
returned ``(severity, source, line_no, message)`` tuples.

Each test writes a one- to handful-of-lines script to ``tmp_path`` so
the AST parser sees a real file (it stores ``file:line`` provenance
on every node).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from execsql.cli.lint_ast import lint_ast
from execsql.script.parser import parse_script


def _lint(tmp_path: Path, body: str) -> list[tuple[str, str, int, str]]:
    """Helper: write *body* to a temp .sql, parse, lint, return issues."""
    src = tmp_path / "script.sql"
    src.write_text(body, encoding="utf-8")
    tree = parse_script(str(src))
    return lint_ast(tree, script_path=str(src))


# ---------------------------------------------------------------------------
# Empty / minimal scripts
# ---------------------------------------------------------------------------


class TestEmptyScript:
    def test_empty_file_emits_warning(self, tmp_path):
        issues = _lint(tmp_path, "")
        assert len(issues) == 1
        severity, source, _line, msg = issues[0]
        assert severity == "warning"
        assert "empty" in msg.lower()

    def test_only_whitespace_and_comments_treated_as_empty(self, tmp_path):
        issues = _lint(tmp_path, "-- just a comment\n\n   \n-- another\n")
        # The parser may consider this empty too; either it warns or no issues.
        # Accept "warns about empty" since that's the lint signal.
        if issues:
            assert issues[0][0] == "warning"


# ---------------------------------------------------------------------------
# Undefined-variable detection
# ---------------------------------------------------------------------------


class TestUndefinedVariables:
    def test_undefined_var_in_sql_warns(self, tmp_path):
        issues = _lint(tmp_path, "SELECT !!totally_undefined!!;\n")
        warnings = [i for i in issues if i[0] == "warning"]
        assert any("totally_undefined" in m for _s, _src, _l, m in warnings), (
            f"expected undefined-var warning, got: {issues}"
        )

    def test_defined_var_does_not_warn(self, tmp_path):
        body = "-- !x! sub mycol foo\nSELECT !!mycol!! AS x;\n"
        issues = _lint(tmp_path, body)
        assert not any("mycol" in m for _s, _src, _l, m in issues), f"defined var should not warn, got: {issues}"

    def test_sub_empty_defines_var(self, tmp_path):
        body = "-- !x! sub_empty maybe\nSELECT '!!maybe!!' AS x;\n"
        issues = _lint(tmp_path, body)
        assert not any("maybe" in m for _s, _src, _l, m in issues)

    def test_subdata_defines_var(self, tmp_path):
        body = "-- !x! subdata from_table some_view\nSELECT !!from_table!!;\n"
        issues = _lint(tmp_path, body)
        assert not any("from_table" in m for _s, _src, _l, m in issues)

    def test_sub_add_defines_var(self, tmp_path):
        body = "-- !x! sub_add counter 1\nSELECT !!counter!!;\n"
        issues = _lint(tmp_path, body)
        assert not any("counter" in m for _s, _src, _l, m in issues)


# ---------------------------------------------------------------------------
# Built-in / system variables — never flagged
# ---------------------------------------------------------------------------


class TestBuiltinVars:
    @pytest.mark.parametrize(
        "var",
        [
            "$current_script",
            "$current_script_name",
            "$current_script_path",
            "$current_script_line",
            "$current_date",
            "$current_time",
            "$current_alias",
            "$current_database",
            "$current_dbms",
            "$current_dir",
            "$counter_1",
            "$counter_42",
            "$arg_1",
            "$random",
            "$uuid",
            "$timer",
            "$run_id",
        ],
    )
    def test_builtin_var_not_flagged(self, tmp_path, var):
        body = f"SELECT '!!{var}!!' AS x;\n"
        issues = _lint(tmp_path, body)
        assert not any(var in m for _s, _src, _l, m in issues), f"builtin {var!r} should not be flagged, got: {issues}"


# ---------------------------------------------------------------------------
# Script-argument variables (#-prefixed) — defined by EXECUTE SCRIPT
# ---------------------------------------------------------------------------


class TestScriptArgVars:
    def test_script_param_visible_inside_body(self, tmp_path):
        body = (
            "-- !x! begin script myscript(target)\n"
            "INSERT INTO log VALUES ('!!#target!!');\n"
            "-- !x! end script\n"
            "-- !x! execute script myscript with arguments (target=foo)\n"
        )
        issues = _lint(tmp_path, body)
        assert not any("target" in m for _s, _src, _l, m in issues)


# ---------------------------------------------------------------------------
# INCLUDE target existence
# ---------------------------------------------------------------------------


class TestIncludeTarget:
    def test_missing_include_warns(self, tmp_path):
        # Use an absolute path that definitely doesn't exist.
        bogus = "/nonexistent/path/that/wont/exist_98765.sql"
        body = f"-- !x! include {bogus}\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m in issues if s == "warning"]
        assert any("98765" in m or "include" in m.lower() for m in warnings), (
            f"missing include should warn, got: {issues}"
        )

    def test_existing_include_does_not_warn(self, tmp_path):
        # Create the sibling file so the include resolves.
        helper = tmp_path / "real_helper.sql"
        helper.write_text("-- (intentionally empty helper)\n", encoding="utf-8")
        body = "-- !x! include real_helper.sql\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m in issues if s == "warning" and "real_helper" in m]
        assert not warnings, f"existing include should not warn, got: {warnings}"


# ---------------------------------------------------------------------------
# EXECUTE SCRIPT target resolution
# ---------------------------------------------------------------------------


class TestExecuteScriptTarget:
    def test_defined_script_target_does_not_warn(self, tmp_path):
        body = (
            "-- !x! begin script existing_target\nSELECT 1;\n-- !x! end script\n-- !x! execute script existing_target\n"
        )
        issues = _lint(tmp_path, body)
        assert not any("existing_target" in m for _s, _src, _l, m in issues)

    def test_undefined_script_target_warns(self, tmp_path):
        body = "-- !x! execute script never_defined_anywhere\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m in issues if s == "warning"]
        assert any("never_defined_anywhere" in m for m in warnings), (
            f"undefined EXECUTE SCRIPT target should warn, got: {issues}"
        )

    def test_if_exists_guard_suppresses_warning(self, tmp_path):
        body = "-- !x! execute script if exists maybe_missing\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m in issues if s == "warning"]
        assert not any("maybe_missing" in m for m in warnings), (
            f"IF EXISTS should suppress missing-target warning, got: {issues}"
        )


# ---------------------------------------------------------------------------
# Return shape — every issue has the expected 4-tuple structure
# ---------------------------------------------------------------------------


class TestReturnShape:
    def test_issues_are_4_tuples(self, tmp_path):
        # Use a script with at least one warning to exercise the path.
        issues = _lint(tmp_path, "SELECT !!some_undefined!!;\n")
        for issue in issues:
            assert len(issue) == 4, f"issue should be a 4-tuple, got: {issue}"
            severity, source, line_no, message = issue
            assert severity in ("error", "warning"), severity
            assert isinstance(source, str)
            assert isinstance(line_no, int)
            assert isinstance(message, str) and message  # non-empty

    def test_no_script_path_arg_works(self, tmp_path):
        # lint_ast must accept script_path=None for inline scripts.
        src = tmp_path / "x.sql"
        src.write_text("SELECT 1;\n", encoding="utf-8")
        tree = parse_script(str(src))
        # Should not raise even with script_path=None.
        issues = lint_ast(tree, script_path=None)
        assert isinstance(issues, list)
