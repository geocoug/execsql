"""Tests for the shared lint result printer in :mod:`execsql.cli.lint`.

The active ``--lint`` static analyser lives in :mod:`execsql.cli.lint_ast`
(see :mod:`tests.cli.test_lint_ast`). This module covers only the small
helpers exposed by ``cli/lint.py``: ``_Issue`` construction and
``_print_lint_results`` console formatting + exit-code contract.
"""

from __future__ import annotations

from execsql.cli.lint import _error, _print_lint_results, _warning


class TestIssueConstructors:
    def test_error_tuple_shape(self):
        issue = _error("file.sql", 12, "boom")
        assert issue == ("error", "file.sql", 12, "boom")

    def test_warning_tuple_shape(self):
        issue = _warning("file.sql", 7, "watch out")
        assert issue == ("warning", "file.sql", 7, "watch out")


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


class TestPrintLintResultsFormatting:
    """Output formatting smoke tests via capsys-style capture."""

    def test_no_issues_prints_no_issues_found(self, capsys):
        _print_lint_results([], "scriptname.sql")
        captured = capsys.readouterr()
        assert "No issues found" in captured.out
        assert "scriptname.sql" in captured.out

    def test_issue_includes_source_and_line(self, capsys):
        issues = [_error("foo.sql", 42, "bad thing")]
        _print_lint_results(issues, "foo.sql")
        captured = capsys.readouterr()
        assert "foo.sql:42" in captured.out
        assert "bad thing" in captured.out

    def test_issue_without_line_omits_colon_lineno(self, capsys):
        issues = [_error("foo.sql", 0, "global problem")]
        _print_lint_results(issues, "foo.sql")
        captured = capsys.readouterr()
        # When line_no is falsy the location prints as just the source.
        assert "global problem" in captured.out
        assert "foo.sql" in captured.out

    def test_errors_sort_before_warnings(self, capsys):
        issues = [
            _warning("a.sql", 5, "MARK_W"),
            _error("a.sql", 9, "MARK_E"),
        ]
        _print_lint_results(issues, "a.sql")
        out = capsys.readouterr().out
        # ERROR row must appear before WARNING row in the output.
        assert out.index("MARK_E") < out.index("MARK_W")

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
