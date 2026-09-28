"""Subcommand dispatch, and the legacy invocation it must never disturb.

``execsql script.sql server db`` has been the invocation since upstream
v1.130.1.  It is in shell scripts, cron entries, and every page of the
documentation, so the central assertion here is not that the new verbs work —
it is that no existing command line changed meaning when they were added.
"""

from __future__ import annotations

import pytest

from execsql.cli.dispatch import VERBS, route

# Every legacy shape the documentation shows, plus the bare and flag-only
# forms.  All of these must reach the runner with argv untouched.
LEGACY_INVOCATIONS = [
    ["execsql", "script.sql"],
    ["execsql", "script.sql", "myserver", "mydb"],
    ["execsql", "-tp", "script.sql", "myserver", "mydb"],
    ["execsql", "-tm", "script.sql", "myserver", "mydb"],
    ["execsql", "-tl", "script.sql", "mydb.sqlite"],
    ["execsql", "-tk", "script.sql", "mydb.duckdb"],
    ["execsql", "--dsn", "postgresql://u:p@h/db", "script.sql"],
    ["execsql", "--lint", "script.sql"],
    ["execsql", "--dry-run", "script.sql"],
    ["execsql", "--ping"],
    ["execsql", "-c", "select 1;"],
    ["execsql", "--version"],
    ["execsql", "--help"],
    ["execsql"],
]


class TestLegacyFormIsUntouched:
    @pytest.mark.parametrize("argv", LEGACY_INVOCATIONS, ids=lambda a: " ".join(a[1:]) or "<bare>")
    def test_routes_to_legacy(self, argv):
        target, _ = route(argv)
        assert target == "legacy", f"{' '.join(argv)} changed meaning"

    @pytest.mark.parametrize("argv", LEGACY_INVOCATIONS, ids=lambda a: " ".join(a[1:]) or "<bare>")
    def test_arguments_arrive_unchanged(self, argv):
        """The runner parser must see exactly what the user typed."""
        _, rest = route(argv)
        assert rest == argv[1:]


class TestVerbsSelectSubcommands:
    @pytest.mark.parametrize(
        "head,expected",
        [("run", "run"), ("format", "format"), ("fmt", "format"), ("lint", "lint")],
    )
    def test_verb_routes(self, head, expected):
        target, rest = route(["execsql", head, "scripts/"])
        assert target == expected
        assert rest == ["scripts/"]

    def test_fmt_is_an_alias_for_format(self):
        assert route(["execsql", "fmt", "-i", "x/"]) == route(["execsql", "format", "-i", "x/"])

    def test_run_strips_only_the_verb(self):
        _, rest = route(["execsql", "run", "-tp", "s.sql", "srv", "db"])
        assert rest == ["-tp", "s.sql", "srv", "db"]


class TestAFileAlwaysWinsOverAVerb:
    """A script named after a verb must still run.

    This is the only way adding subcommands could change an existing command
    line's meaning, so it is resolved in favour of the file.
    """

    @pytest.mark.parametrize("name", VERBS)
    def test_existing_file_shadows_the_verb(self, name, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / name).write_text("select 1;", encoding="utf-8")
        target, rest = route(["execsql", name, "myserver", "mydb"])
        assert target == "legacy"
        assert rest == [name, "myserver", "mydb"]

    @pytest.mark.parametrize("name", VERBS)
    def test_verb_wins_when_no_such_file(self, name, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target, _ = route(["execsql", name, "scripts/"])
        assert target != "legacy"

    def test_a_dotted_name_was_never_ambiguous(self, tmp_path, monkeypatch):
        """``lint.sql`` is a path, not a verb, whether or not it exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "lint.sql").write_text("select 1;", encoding="utf-8")
        target, rest = route(["execsql", "lint.sql"])
        assert target == "legacy"
        assert rest == ["lint.sql"]


class TestLintSubcommandWalksDirectories:
    """The capability ``--lint`` never had.

    ``--lint`` lints the one script you were about to run.  Linting a library
    is the whole point of the linter, so the subcommand takes directories.
    """

    def _library(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "ok.sql").write_text("-- !x! SUB a 1\nselect '!!a!!';\n", encoding="utf-8")
        (tmp_path / "sub" / "bad.sql").write_text("select '!!never_set!!';\n", encoding="utf-8")
        return tmp_path

    def test_every_file_is_visited(self, tmp_path, capsys):
        from execsql.cli.dispatch import lint_paths

        lint_paths([str(self._library(tmp_path))])
        assert "bad.sql" in capsys.readouterr().out

    def test_a_nested_directory_is_searched(self, tmp_path, capsys):
        from execsql.cli.dispatch import lint_paths

        lint_paths([str(self._library(tmp_path))])
        out = capsys.readouterr().out
        assert "never_set" in out, "a script in a subdirectory was not linted"

    def test_a_clean_library_says_so(self, tmp_path, capsys):
        from execsql.cli.dispatch import lint_paths

        (tmp_path / "ok.sql").write_text("-- !x! SUB a 1\nselect '!!a!!';\n", encoding="utf-8")
        assert lint_paths([str(tmp_path)]) == 0
        assert "no issues" in capsys.readouterr().out

    def test_no_sql_files_is_an_error(self, tmp_path):
        from execsql.cli.dispatch import lint_paths

        assert lint_paths([str(tmp_path)]) == 1

    def test_a_parse_error_is_reported_not_raised(self, tmp_path, capsys):
        """An unparsable script is a lint finding, not a crash."""
        from execsql.cli.dispatch import lint_paths

        (tmp_path / "broken.sql").write_text("-- !x! IF(1=1)\nselect 1;\n", encoding="utf-8")
        assert lint_paths([str(tmp_path)]) == 1
        assert "broken.sql" in capsys.readouterr().out
