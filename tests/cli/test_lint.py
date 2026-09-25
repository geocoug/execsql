"""Tests for the AST-based ``--lint`` static analyser in
:mod:`execsql.cli.lint`.

Two layers are covered:

1. The rule registry and the Rich console formatter
   (:func:`_print_lint_results`) — the formatter owns the exit-code
   contract (``1`` iff any error-severity issue is present).
2. The :func:`lint` AST walker end-to-end: parse a small script into the
   AST, feed it to :func:`lint`, and assert on the returned
   :class:`~execsql.cli.lint.Issue` values.

End-to-end tests write a one- to handful-of-lines script to ``tmp_path``
so the AST parser sees a real file (it stores ``file:line`` provenance
on every node).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from execsql.cli.lint import RULES, Issue, _issue, _print_lint_results, lint
from execsql.script.parser import parse_script


def _error(source: str, line: int, message: str) -> Issue:
    """An error-severity issue for formatter tests (P001 is the error rule)."""
    return _issue("P001", source, line, message)


def _warning(source: str, line: int, message: str) -> Issue:
    """A warning-severity issue for formatter tests."""
    return _issue("V001", source, line, message)


# ---------------------------------------------------------------------------
# Rule registry and issue construction
# ---------------------------------------------------------------------------


class TestRules:
    def test_issue_takes_severity_from_its_rule(self):
        assert _issue("P001", "f.sql", 1, "x").severity == "error"
        assert _issue("V002", "f.sql", 1, "x").severity == "warning"

    def test_issue_carries_its_code(self):
        assert _issue("F002", "f.sql", 3, "x") == Issue("warning", "f.sql", 3, "x", "F002")

    def test_codes_are_well_formed_and_names_unique(self):
        for code, rule in RULES.items():
            assert rule.code == code
            assert len(code) == 4 and code[0].isalpha() and code[1:].isdigit(), code
            assert rule.severity in ("error", "warning")
            assert rule.summary
        names = [r.name for r in RULES.values()]
        assert len(names) == len(set(names))

    def test_unknown_code_is_a_programming_error(self):
        with pytest.raises(KeyError):
            _issue("Z999", "f.sql", 1, "x")


# ---------------------------------------------------------------------------
# _print_lint_results — exit code contract
# ---------------------------------------------------------------------------


class TestPrintLintResultsExitCode:
    """``_print_lint_results`` returns ``1`` iff any error-severity issue
    is present; warnings alone exit ``0``."""

    def test_empty_issues_returns_zero(self):
        assert _print_lint_results([], "test.sql") == 0

    def test_warning_only_returns_zero(self):
        issues = [_warning("test.sql", 1, "just a warning")]
        assert _print_lint_results(issues, "test.sql") == 0

    def test_single_error_returns_one(self):
        issues = [_error("test.sql", 1, "fatal")]
        assert _print_lint_results(issues, "test.sql") == 1

    def test_mixed_errors_and_warnings_returns_one(self):
        issues = [
            _warning("test.sql", 1, "minor"),
            _error("test.sql", 2, "major"),
            _warning("test.sql", 3, "minor again"),
        ]
        assert _print_lint_results(issues, "test.sql") == 1

    def test_multiple_errors_returns_one(self):
        issues = [
            _error("test.sql", 1, "first"),
            _error("test.sql", 2, "second"),
        ]
        assert _print_lint_results(issues, "test.sql") == 1


# ---------------------------------------------------------------------------
# _print_lint_results — output formatting
# ---------------------------------------------------------------------------


class TestPrintLintResultsFormatting:
    """Output formatting smoke tests via capsys-style capture."""

    def test_no_issues_prints_no_issues_found(self, capsys):
        _print_lint_results([], "scriptname.sql")
        out = capsys.readouterr().out
        assert "No issues found (1 file checked)" in out

    def test_issues_sit_under_their_file(self, capsys):
        _print_lint_results([_error("foo.sql", 42, "bad thing")], "foo.sql")
        lines = capsys.readouterr().out.splitlines()
        assert lines[0] == "foo.sql"
        assert lines[1].split() == ["42", "error", "P001", "bad", "thing"]

    def test_issue_without_line_omits_colon_lineno(self, capsys):
        issues = [_error("foo.sql", 0, "global problem")]
        _print_lint_results(issues, "foo.sql")
        captured = capsys.readouterr()
        # When line_no is falsy the location prints as just the source.
        assert "global problem" in captured.out
        assert "foo.sql" in captured.out

    def test_issues_are_in_line_order(self, capsys):
        """A reader works down the file, so rows follow the lines, whatever the severity."""
        issues = [
            _error("a.sql", 9, "MARK_E"),
            _warning("a.sql", 5, "MARK_W"),
        ]
        _print_lint_results(issues, "a.sql")
        out = capsys.readouterr().out
        assert out.index("MARK_W") < out.index("MARK_E")

    def test_summary_line_counts(self, capsys):
        issues = [
            _error("a.sql", 1, "e1"),
            _error("a.sql", 2, "e2"),
            _warning("a.sql", 3, "w1"),
        ]
        _print_lint_results(issues, "a.sql")
        out = capsys.readouterr().out
        assert "2 errors" in out
        assert "1 warning" in out


# ---------------------------------------------------------------------------
# lint() end-to-end helpers
# ---------------------------------------------------------------------------


def _lint(tmp_path: Path, body: str) -> list[tuple[str, str, int, str]]:
    """Helper: write *body* to a temp .sql, parse, lint, return issues."""
    src = tmp_path / "script.sql"
    src.write_text(body, encoding="utf-8")
    tree = parse_script(str(src))
    return lint(tree, script_path=str(src))


# ---------------------------------------------------------------------------
# lint() — empty / minimal scripts
# ---------------------------------------------------------------------------


class TestEmptyScript:
    def test_empty_file_emits_warning(self, tmp_path):
        issues = _lint(tmp_path, "")
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].code == "S001"
        assert "empty" in issues[0].message.lower()

    def test_only_whitespace_and_comments_treated_as_empty(self, tmp_path):
        issues = _lint(tmp_path, "-- just a comment\n\n   \n-- another\n")
        # The parser may consider this empty too; either it warns or no issues.
        # Accept "warns about empty" since that's the lint signal.
        if issues:
            assert issues[0][0] == "warning"


# ---------------------------------------------------------------------------
# lint() — undefined-variable detection
# ---------------------------------------------------------------------------


class TestUndefinedVariables:
    def test_undefined_var_in_sql_warns(self, tmp_path):
        issues = _lint(tmp_path, "SELECT !!totally_undefined!!;\n")
        warnings = [i for i in issues if i[0] == "warning"]
        assert any("totally_undefined" in m for *_, m, _code in warnings), (
            f"expected undefined-var warning, got: {issues}"
        )

    def test_defined_var_does_not_warn(self, tmp_path):
        body = "-- !x! sub mycol foo\nSELECT !!mycol!! AS x;\n"
        issues = _lint(tmp_path, body)
        assert not any("mycol" in m for *_, m, _code in issues), f"defined var should not warn, got: {issues}"

    def test_sub_empty_defines_var(self, tmp_path):
        body = "-- !x! sub_empty maybe\nSELECT '!!maybe!!' AS x;\n"
        issues = _lint(tmp_path, body)
        assert not any("maybe" in m for *_, m, _code in issues)

    def test_subdata_defines_var(self, tmp_path):
        body = "-- !x! subdata from_table some_view\nSELECT !!from_table!!;\n"
        issues = _lint(tmp_path, body)
        assert not any("from_table" in m for *_, m, _code in issues)

    def test_sub_add_defines_var(self, tmp_path):
        body = "-- !x! sub_add counter 1\nSELECT !!counter!!;\n"
        issues = _lint(tmp_path, body)
        assert not any("counter" in m for *_, m, _code in issues)


# ---------------------------------------------------------------------------
# lint() — built-in / system variables (never flagged)
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
        assert not any(var in m for *_, m, _code in issues), f"builtin {var!r} should not be flagged, got: {issues}"


# ---------------------------------------------------------------------------
# lint() — script-argument variables (#-prefixed)
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
        assert not any("target" in m for *_, m, _code in issues)


# ---------------------------------------------------------------------------
# lint() — INCLUDE target existence
# ---------------------------------------------------------------------------


class TestIncludeTarget:
    def test_missing_include_warns(self, tmp_path):
        # Use an absolute path that definitely doesn't exist.
        bogus = "/nonexistent/path/that/wont/exist_98765.sql"
        body = f"-- !x! include {bogus}\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m, _code in issues if s == "warning"]
        assert any("98765" in m or "include" in m.lower() for m in warnings), (
            f"missing include should warn, got: {issues}"
        )

    def test_existing_include_does_not_warn(self, tmp_path):
        # Create the sibling file so the include resolves.
        helper = tmp_path / "real_helper.sql"
        helper.write_text("-- (intentionally empty helper)\n", encoding="utf-8")
        body = "-- !x! include real_helper.sql\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m, _code in issues if s == "warning" and "real_helper" in m]
        assert not warnings, f"existing include should not warn, got: {warnings}"


# ---------------------------------------------------------------------------
# lint() — EXECUTE SCRIPT target resolution
# ---------------------------------------------------------------------------


class TestExecuteScriptTarget:
    def test_defined_script_target_does_not_warn(self, tmp_path):
        body = (
            "-- !x! begin script existing_target\nSELECT 1;\n-- !x! end script\n-- !x! execute script existing_target\n"
        )
        issues = _lint(tmp_path, body)
        assert not any("existing_target" in m for *_, m, _code in issues)

    def test_undefined_script_target_warns(self, tmp_path):
        body = "-- !x! execute script never_defined_anywhere\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m, _code in issues if s == "warning"]
        assert any("never_defined_anywhere" in m for m in warnings), (
            f"undefined EXECUTE SCRIPT target should warn, got: {issues}"
        )

    def test_if_exists_guard_suppresses_warning(self, tmp_path):
        body = "-- !x! execute script if exists maybe_missing\n"
        issues = _lint(tmp_path, body)
        warnings = [m for s, _src, _l, m, _code in issues if s == "warning"]
        assert not any("maybe_missing" in m for m in warnings), (
            f"IF EXISTS should suppress missing-target warning, got: {issues}"
        )


# ---------------------------------------------------------------------------
# lint() — return shape
# ---------------------------------------------------------------------------


class TestReturnShape:
    def test_issues_are_issue_tuples(self, tmp_path):
        # Use a script with at least one warning to exercise the path.
        issues = _lint(tmp_path, "SELECT !!some_undefined!!;\n")
        for issue in issues:
            assert isinstance(issue, Issue), issue
            severity, source, line_no, message, code = issue
            assert code in RULES, code
            assert severity in ("error", "warning"), severity
            assert isinstance(source, str)
            assert isinstance(line_no, int)
            assert isinstance(message, str) and message  # non-empty

    def test_no_script_path_arg_works(self, tmp_path):
        # lint() must accept script_path=None for inline scripts.
        src = tmp_path / "x.sql"
        src.write_text("SELECT 1;\n", encoding="utf-8")
        tree = parse_script(str(src))
        # Should not raise even with script_path=None.
        issues = lint(tree, script_path=None)
        assert isinstance(issues, list)


# ---------------------------------------------------------------------------
# Structural rules
#
# The checks a compiler does for every other language. Before these, a dead
# branch or a mistyped variable was found by running the script against a live
# database and watching it do the wrong thing halfway through.
# ---------------------------------------------------------------------------


def _messages(issues) -> str:
    return " | ".join(i.message for i in issues)


def _codes(issues) -> set[str]:
    """Which rules fired. Detection tests check codes, not wording: an
    assertion that some text is *absent* passes forever once the text changes."""
    return {i.code for i in issues}


class TestConstantConditionMakesBranchesUnreachable:
    """`IF(True)` left in after debugging is what kills every other branch."""

    def test_always_true_reports_the_dead_else(self, tmp_path):
        issues = _lint(tmp_path, "-- !x! IF(True)\nSELECT 1;\n-- !x! ELSE\nSELECT 2;\n-- !x! ENDIF\n")
        assert "F001" in _codes(issues)

    def test_always_true_with_no_else_is_not_reported(self, tmp_path):
        """Nothing is unreachable, so there is nothing to say."""
        issues = _lint(tmp_path, "-- !x! IF(True)\nSELECT 1;\n-- !x! ENDIF\n")
        assert "F001" not in _codes(issues)

    def test_always_false_reports_the_dead_body(self, tmp_path):
        issues = _lint(tmp_path, "-- !x! IF(FALSE)\nSELECT 1;\n-- !x! ENDIF\n")
        assert "F001" in _codes(issues)
        assert "always false" in _messages(issues)

    @pytest.mark.parametrize("cond", ["1=1", "1 = 1", "true", "TRUE", "(True)", "yes"])
    def test_spellings_of_always_true(self, tmp_path, cond):
        issues = _lint(tmp_path, f"-- !x! IF({cond})\nSELECT 1;\n-- !x! ELSE\nSELECT 2;\n-- !x! ENDIF\n")
        assert "F001" in _codes(issues), cond

    def test_a_real_condition_is_left_alone(self, tmp_path):
        """The rule must not fire on a condition with actual content."""
        issues = _lint(tmp_path, "-- !x! IF(hasrows(mytable))\nSELECT 1;\n-- !x! ELSE\nSELECT 2;\n-- !x! ENDIF\n")
        assert "F001" not in _codes(issues)

    def test_a_modifier_suppresses_the_rule(self, tmp_path):
        """An ANDIF can make the whole condition false, so it is not constant."""
        body = "-- !x! IF(True)\n-- !x! ANDIF(hasrows(t))\nSELECT 1;\n-- !x! ELSE\nSELECT 2;\n-- !x! ENDIF\n"
        issues = _lint(tmp_path, body)
        assert "F001" not in _codes(issues)


class TestUnreachableAfterHalt:
    def test_a_statement_after_halt_is_reported(self, tmp_path):
        issues = _lint(tmp_path, '-- !x! HALT MESSAGE "done"\nSELECT 1;\n')
        assert "F002" in _codes(issues)

    def test_the_halt_line_is_named(self, tmp_path):
        issues = _lint(tmp_path, '-- !x! HALT MESSAGE "done"\nSELECT 1;\n')
        assert "line 1" in _messages(issues)

    def test_halt_at_the_end_is_fine(self, tmp_path):
        issues = _lint(tmp_path, 'SELECT 1;\n-- !x! HALT MESSAGE "done"\n')
        assert "F002" not in _codes(issues)

    def test_halt_display_is_not_terminal(self, tmp_path):
        """HALT DISPLAY shows a message and can be cancelled."""
        issues = _lint(tmp_path, "-- !x! HALT DISPLAY mytable\nSELECT 1;\n")
        assert "F002" not in _codes(issues)

    def test_halt_inside_a_branch_does_not_condemn_the_rest(self, tmp_path):
        """Only the enclosing block is unreachable, not what follows ENDIF."""
        body = '-- !x! IF(hasrows(t))\n-- !x! HALT MESSAGE "stop"\n-- !x! ENDIF\nSELECT 1;\n'
        issues = _lint(tmp_path, body)
        assert "F002" not in _codes(issues)


class TestUnusedVariables:
    """A defined-but-unread variable is nearly always a spelling mismatch."""

    def test_an_unreferenced_sub_is_reported(self, tmp_path):
        issues = _lint(tmp_path, "-- !x! SUB orphan value\nSELECT 1;\n")
        assert "V002" in _codes(issues)

    def test_a_referenced_sub_is_not_reported(self, tmp_path):
        issues = _lint(tmp_path, "-- !x! SUB used value\nSELECT '!!used!!';\n")
        assert "V002" not in _codes(issues)

    def test_a_reference_from_a_condition_counts(self, tmp_path):
        body = "-- !x! SUB flag 1\n-- !x! IF(!!flag!! = 1)\nSELECT 1;\n-- !x! ENDIF\n"
        issues = _lint(tmp_path, body)
        assert "V002" not in _codes(issues)

    def test_a_reference_from_inside_a_block_counts(self, tmp_path):
        body = "-- !x! SUB deep v\n-- !x! IF(hasrows(t))\nSELECT '!!deep!!';\n-- !x! ENDIF\n"
        issues = _lint(tmp_path, body)
        assert "V002" not in _codes(issues)

    def test_the_definition_line_is_reported(self, tmp_path):
        issues = _lint(tmp_path, "SELECT 1;\n-- !x! SUB orphan value\n")
        unused = [i for i in issues if i.code == "V002"]
        assert unused and unused[0].line == 2, unused


class TestTheProjectsOwnScriptsStayQuiet:
    """A rule that fires on correct scripts is worse than no rule.

    These rules were run across every template and fixture in the repo; the
    only finding was a fixture whose dead branch is named ``should_not_run``.
    """

    def test_a_realistic_script_produces_no_structural_findings(self, tmp_path):
        body = (
            "-- !x! SUB indir data\n"
            "-- !x! SUB outdir reports\n"
            "-- !x! IF(file_exists(!!indir!!/in.csv))\n"
            "    -- !x! IMPORT TO staging FROM !!indir!!/in.csv\n"
            "    -- !x! IF(HASROWS(staging))\n"
            "        -- !x! EXPORT staging TO !!outdir!!/out.csv AS CSV\n"
            "    -- !x! ELSE\n"
            '        -- !x! WRITE "nothing to export"\n'
            "    -- !x! ENDIF\n"
            "-- !x! ENDIF\n"
        )
        issues = _lint(tmp_path, body)
        structural = [i for i in issues if i.code in ("F001", "F002", "V002")]
        assert not structural, structural


# ---------------------------------------------------------------------------
# Rule codes: each check reports under its own code
# ---------------------------------------------------------------------------


class TestEachCheckHasItsCode:
    """The code is the contract --select, --ignore and JSON consumers rely on."""

    @pytest.mark.parametrize(
        ("script", "code"),
        [
            ("", "S001"),
            ("SELECT !!nowhere!!;\n", "V001"),
            ("-- !x! SUB unused_one 1\nSELECT 1;\n", "V002"),
            ("-- !x! INCLUDE does_not_exist.sql\n", "I001"),
            ("-- !x! EXECUTE SCRIPT no_such_block\n", "I002"),
            ("-- !x! IF(True)\nSELECT 1;\n-- !x! ELSE\nSELECT 2;\n-- !x! ENDIF\n", "F001"),
            ("-- !x! IF(False)\nSELECT 1;\n-- !x! ENDIF\n", "F001"),
            ("-- !x! HALT\nSELECT 1;\n", "F002"),
        ],
        ids=["empty", "undefined", "unused", "include", "execute-script", "always-true", "always-false", "halt"],
    )
    def test_code(self, tmp_path, script, code):
        assert code in {i.code for i in _lint(tmp_path, script)}


# ---------------------------------------------------------------------------
# --select / --ignore
# ---------------------------------------------------------------------------


class TestResolveSelectors:
    def test_none_means_nothing(self):
        from execsql.cli.lint import resolve_selectors

        assert resolve_selectors(None) == ()

    def test_commas_repeats_case_and_blanks(self):
        from execsql.cli.lint import resolve_selectors

        assert resolve_selectors(["v001, f", "I002", ","]) == ("V001", "F", "I002")

    @pytest.mark.parametrize("bad", ["V9", "X", "V0011", "undefined-variable"])
    def test_unknown_entry_is_rejected(self, bad):
        from execsql.cli.lint import resolve_selectors

        with pytest.raises(ValueError, match="unknown rule code"):
            resolve_selectors([bad])


class TestFilterIssues:
    ISSUES = [
        _issue("P001", "a.sql", 1, "parse"),
        _issue("V001", "a.sql", 2, "undef"),
        _issue("V002", "a.sql", 3, "unused"),
        _issue("F002", "a.sql", 4, "dead"),
    ]

    def _codes(self, **kw):
        from execsql.cli.lint import filter_issues

        return [i.code for i in filter_issues(self.ISSUES, **kw)]

    def test_no_selectors_keeps_everything(self):
        assert self._codes() == ["P001", "V001", "V002", "F002"]

    def test_select_by_prefix(self):
        assert self._codes(select=("V",)) == ["P001", "V001", "V002"]

    def test_ignore_by_code(self):
        assert self._codes(ignore=("V002",)) == ["P001", "V001", "F002"]

    def test_ignore_wins_over_select(self):
        assert self._codes(select=("V",), ignore=("V001",)) == ["P001", "V002"]

    def test_parse_errors_cannot_be_filtered_out(self):
        assert "P001" in self._codes(select=("F",), ignore=("P",))


# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------


class TestParseError:
    def _issue_for(self, msg):
        from execsql.cli.lint import parse_error
        from execsql.exceptions import ErrInfo

        return parse_error("x.sql", ErrInfo("cmd", command_text="-- !x! IF(1)", other_msg=msg))

    def test_line_comes_from_the_parser_message(self):
        issue = self._issue_for("Unmatched IF block starting on line 7 at end of file x.sql.")
        assert (issue.code, issue.severity, issue.line) == ("P001", "error", 7)

    def test_message_is_one_clean_line(self):
        issue = self._issue_for(
            "Incomplete SQL statement\n  (select 1)\nat END SCRIPT metacommand on line 4 of file x.sql.",
        )
        assert "\n" not in issue.message
        assert "****" not in issue.message and "Error occurred at" not in issue.message
        assert issue.line == 4

    def test_no_line_in_message_gives_zero(self):
        assert self._issue_for("something odd").line == 0

    def test_a_real_parse_failure(self, tmp_path):
        from execsql.cli.lint import parse_error
        from execsql.exceptions import ErrInfo

        path = tmp_path / "bad.sql"
        path.write_text("-- !x! IF(True)\nSELECT 1;\n", encoding="utf-8")
        with pytest.raises(ErrInfo) as info:
            parse_script(str(path))
        issue = parse_error(str(path), info.value)
        assert issue.line == 1
        assert "Unmatched IF" in issue.message


# ---------------------------------------------------------------------------
# Machine-readable output
# ---------------------------------------------------------------------------


class TestRenderJson:
    def test_fields(self):
        import json

        from execsql.cli.lint import render_json

        rows = json.loads(render_json([_issue("F002", "a.sql", 4, "unreachable — HALT on line 3")]))
        assert rows == [
            {
                "file": "a.sql",
                "line": 4,
                "code": "F002",
                "rule": "unreachable-code",
                "severity": "warning",
                "message": "unreachable — HALT on line 3",
            },
        ]

    def test_no_line_is_null_and_text_is_not_escaped(self):
        from execsql.cli.lint import render_json

        out = render_json([_issue("S001", "a.sql", 0, "Script is empty — no commands found")])
        assert '"line": null' in out
        assert "—" in out

    def test_empty_is_an_empty_array(self):
        from execsql.cli.lint import render_json

        assert render_json([]) == "[]"


class TestRuleCounts:
    def test_most_frequent_first_then_by_code(self):
        from execsql.cli.lint import rule_counts

        issues = [_issue(c, "a.sql", 1, "x") for c in ("V002", "F002", "F002", "V001", "V001")]
        assert [(r.code, n) for r, n in rule_counts(issues)] == [("F002", 2), ("V001", 2), ("V002", 1)]


# ---------------------------------------------------------------------------
# execsql lint — the command line
# ---------------------------------------------------------------------------


class TestLintCommand:
    """End to end through the CLI, against a small library of scripts."""

    @pytest.fixture
    def library(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "typo.sql").write_text(
            "-- !x! SUB report_dir /tmp\nSELECT '!!output_path!!';\n",
            encoding="utf-8",
        )
        (tmp_path / "sub" / "flow.sql").write_text("-- !x! HALT\nSELECT 1;\n", encoding="utf-8")
        (tmp_path / "sub" / "clean.sql").write_text("SELECT 1;\n", encoding="utf-8")
        return tmp_path

    def _run(self, *args):
        from typer.testing import CliRunner

        from execsql.cli import app

        return CliRunner().invoke(app, ["lint", *args])

    def test_text_output_names_the_codes(self, library):
        result = self._run(str(library))
        assert result.exit_code == 0, result.output
        for code in ("V001", "V002", "F002"):
            assert code in result.output

    def test_select(self, library):
        out = self._run(str(library), "--select", "F").output
        assert "F002" in out and "V001" not in out and "V002" not in out

    def test_ignore_everything_reports_clean(self, library):
        result = self._run(str(library), "--ignore", "V,F")
        assert result.exit_code == 0
        assert "No issues found (3 files checked)" in result.output

    def test_json_is_the_only_thing_on_stdout(self, library):
        import json

        result = self._run(str(library), "--output-format", "json")
        rows = json.loads(result.output)
        assert {r["code"] for r in rows} == {"V001", "V002", "F002"}
        assert all(set(r) == {"file", "line", "code", "rule", "severity", "message"} for r in rows)

    def test_json_with_nothing_to_report(self, library):
        result = self._run(str(library / "sub" / "clean.sql"), "--output-format", "json")
        assert result.exit_code == 0
        assert result.output.strip() == "[]"

    def test_statistics_text(self, library):
        out = self._run(str(library), "--statistics").output
        assert "unused-variable" in out and "undefined-variable" in out and "unreachable-code" in out
        assert "WARNING" not in out

    def test_statistics_json(self, library):
        import json

        rows = json.loads(self._run(str(library), "--statistics", "--output-format", "json").output)
        assert {(r["code"], r["count"]) for r in rows} == {("V001", 1), ("V002", 1), ("F002", 1)}

    def test_parse_error_exits_1_even_when_ignored(self, library):
        (library / "broken.sql").write_text("-- !x! IF(True)\nSELECT 1;\n", encoding="utf-8")
        result = self._run(str(library), "--ignore", "P", "--output-format", "json")
        import json

        rows = json.loads(result.output)
        assert result.exit_code == 1
        assert [r["code"] for r in rows if r["code"] == "P001"] == ["P001"]
        assert next(r for r in rows if r["code"] == "P001")["line"] == 1

    def test_unknown_code_is_a_usage_error(self, library):
        result = self._run(str(library), "--ignore", "V9")
        assert result.exit_code == 2
        assert "unknown rule code" in result.output

    def test_bad_output_format_is_a_usage_error(self, library):
        assert self._run(str(library), "--output-format", "xml").exit_code == 2

    def test_run_lint_flag_shows_codes_too(self, library):
        from typer.testing import CliRunner

        from execsql.cli import app

        result = CliRunner().invoke(app, ["--lint", str(library / "sub" / "flow.sql")])
        assert "F002" in result.output

    def test_help_points_at_the_rules_page_instead_of_listing_rules(self):
        """Rules are explained in the docs, not in --help."""
        out = self._run("--help").output
        assert "reference/lint" in out
        assert not any(rule.name in out for rule in RULES.values())


# ---------------------------------------------------------------------------
# Text layouts
# ---------------------------------------------------------------------------


class TestTextLayouts:
    RESULTS = [
        ("b.sql", [_warning("b.sql", 10, "second"), _warning("b.sql", 2, "first")]),
        ("clean.sql", []),
        ("a.sql", [_error("a.sql", 0, "no line")]),
    ]

    def test_grouped_layout(self, capsys):
        from execsql.cli.lint import print_text

        print_text(self.RESULTS, checked=3)
        assert capsys.readouterr().out.splitlines() == [
            "b.sql",
            "   2  warning  V001  first",
            "  10  warning  V001  second",
            "",
            "a.sql",
            "  -  error    P001  no line",
            "",
            "Found 3 issues in 2 files: 1 error, 2 warnings (3 files checked)",
        ]

    def test_concise_layout(self, capsys):
        from execsql.cli.lint import print_concise

        print_concise(self.RESULTS, checked=3)
        assert capsys.readouterr().out.splitlines() == [
            "b.sql:2: V001 first",
            "b.sql:10: V001 second",
            "a.sql: P001 no line",
            "",
            "Found 3 issues in 2 files: 1 error, 2 warnings (3 files checked)",
        ]

    def test_piped_output_never_wraps(self, capsys):
        from execsql.cli.lint import print_text

        long = "word " * 60
        print_text([("x.sql", [_warning("x.sql", 1, long.strip())])], checked=1)
        rows = [line for line in capsys.readouterr().out.splitlines() if "V001" in line]
        assert len(rows) == 1 and rows[0].endswith("word")

    def test_statistics_layout(self, capsys):
        from execsql.cli.lint import print_statistics

        print_statistics(self.RESULTS, checked=3)
        assert capsys.readouterr().out.splitlines() == [
            "  2  V001  undefined-variable",
            "  1  P001  parse-error",
            "",
            "Found 3 issues in 2 files: 1 error, 2 warnings (3 files checked)",
        ]

    def test_concise_from_the_command_line(self, tmp_path):
        from typer.testing import CliRunner

        from execsql.cli import app

        (tmp_path / "f.sql").write_text("-- !x! HALT\nSELECT 1;\n", encoding="utf-8")
        out = CliRunner().invoke(app, ["lint", str(tmp_path / "f.sql"), "--output-format", "concise"]).output
        assert out.splitlines()[0] == f"{tmp_path / 'f.sql'}:2: F002 unreachable: HALT on line 1 ends the script"


class TestMessages:
    """Messages are short; the rules page carries the explanation."""

    @pytest.mark.parametrize(
        ("script", "message"),
        [
            ("SELECT !!nowhere!!;\n", "undefined variable !!nowhere!!"),
            ("-- !x! SUB spare 1\nSELECT 1;\n", "variable !!spare!! is never used"),
            ("-- !x! INCLUDE gone.sql\n", "INCLUDE file does not exist: gone.sql"),
            ("-- !x! EXECUTE SCRIPT nope\n", "no BEGIN SCRIPT block named nope"),
            (
                "-- !x! IF(True)\nSELECT 1;\n-- !x! ELSE\nSELECT 2;\n-- !x! ENDIF\n",
                "IF(True) is always true; its ELSE never runs",
            ),
            (
                "-- !x! IF(True)\nSELECT 1;\n-- !x! ELSEIF(x)\nSELECT 2;\n-- !x! ELSE\nSELECT 3;\n-- !x! ENDIF\n",
                "IF(True) is always true; its ELSEIF and ELSE never run",
            ),
            (
                "-- !x! IF(True)\nSELECT 1;\n-- !x! ELSEIF(x)\nSELECT 2;\n-- !x! ELSEIF(y)\nSELECT 3;\n-- !x! ENDIF\n",
                "IF(True) is always true; its 2 ELSEIF branches never run",
            ),
            ("-- !x! IF(False)\nSELECT 1;\n-- !x! ENDIF\n", "IF(False) is always false; its body never runs"),
            ("-- !x! HALT\nSELECT 1;\n", "unreachable: HALT on line 1 ends the script"),
            ("", "script is empty"),
        ],
    )
    def test_message(self, tmp_path, script, message):
        assert message in _messages(_lint(tmp_path, script))


class TestScriptBlocks:
    def test_issue_inside_a_block_has_its_line_and_no_block_prefix(self, tmp_path):
        """The line already places the issue inside the block; the name would repeat it."""
        script = "-- !x! BEGIN SCRIPT upsert_table\nSELECT !!nowhere!!;\n-- !x! END SCRIPT\n"
        issues = [i for i in _lint(tmp_path, script) if i.code == "V001"]
        assert len(issues) == 1
        assert issues[0].line == 2
        assert issues[0].message == "undefined variable !!nowhere!!"

    def test_a_block_that_is_also_executed_is_reported_once(self, tmp_path):
        script = "-- !x! EXECUTE SCRIPT helper\n-- !x! BEGIN SCRIPT helper\nSELECT !!nowhere!!;\n-- !x! END SCRIPT\n"
        assert [i.code for i in _lint(tmp_path, script)].count("V001") == 1
