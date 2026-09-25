"""Subcommand dispatch, and the legacy invocation it must never disturb.

``execsql script.sql server db`` has been the invocation since upstream
v1.130.1.  It is in shell scripts, cron entries, and every page of the
documentation, so the central assertion here is not that the new verbs work —
it is that no existing command line changed meaning when they were added.
"""

from __future__ import annotations

import re

import pytest

from execsql.cli.dispatch import COMMANDS, GLOBAL_FLAGS, normalize

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
    """Every documented invocation must still reach the runner, unchanged.

    ``normalize`` inserts ``run``; the arguments after it must be exactly what
    the user typed, in the same order.
    """

    @pytest.mark.parametrize("argv", LEGACY_INVOCATIONS, ids=lambda a: " ".join(a[1:]) or "<bare>")
    def test_routes_to_run(self, argv):
        out = normalize(argv[1:])
        if not argv[1:] or argv[1] in GLOBAL_FLAGS:
            return  # bare execsql and --help are answered by the app itself
        assert out[0] == "run", f"{' '.join(argv)} no longer runs the script"

    @pytest.mark.parametrize("argv", LEGACY_INVOCATIONS, ids=lambda a: " ".join(a[1:]) or "<bare>")
    def test_arguments_arrive_unchanged(self, argv):
        out = normalize(argv[1:])
        tail = out[1:] if out and out[0] == "run" else out
        assert tail == argv[1:]

    def test_help_is_answered_by_the_app(self):
        """``execsql --help`` must list the commands, not run a script."""
        assert normalize(["--help"]) == ["--help"]

    @pytest.mark.parametrize("flag", ["-m", "--encodings", "--init-config"])
    def test_run_options_get_the_verb(self, flag):
        """These are declared on run, so they need the verb in front."""
        assert normalize([flag]) == ["run", flag]

    @pytest.mark.parametrize("flag", ["--version", "--online-help", "-o"])
    def test_app_options_do_not(self, flag):
        """These are declared on the app itself and must reach it directly."""
        assert normalize([flag]) == [flag]


class TestCommandsAreLeftAlone:
    @pytest.mark.parametrize("head", ["run", "format", "fmt", "lint"])
    def test_a_command_is_not_prefixed(self, head):
        assert normalize([head, "scripts/"]) == [head, "scripts/"]

    def test_run_keeps_its_arguments(self):
        assert normalize(["run", "-tp", "s.sql", "srv", "db"]) == ["run", "-tp", "s.sql", "srv", "db"]


class TestAFileAlwaysWinsOverACommand:
    """A script named after a command must still run.

    This is the only way adding commands could change an existing command
    line's meaning, so it is resolved in favour of the file.
    """

    @pytest.mark.parametrize("name", COMMANDS)
    def test_existing_file_shadows_the_command(self, name, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / name).write_text("select 1;", encoding="utf-8")
        assert normalize([name, "myserver", "mydb"]) == ["run", name, "myserver", "mydb"]

    @pytest.mark.parametrize("name", COMMANDS)
    def test_command_wins_when_no_such_file(self, name, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert normalize([name, "scripts/"])[0] == name

    def test_a_dotted_name_was_never_ambiguous(self, tmp_path, monkeypatch):
        """``lint.sql`` is a path, not a command, whether or not it exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "lint.sql").write_text("select 1;", encoding="utf-8")
        assert normalize(["lint.sql"]) == ["run", "lint.sql"]


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


class TestTheCommandListIsRendered:
    """``execsql --help`` must show a Commands panel, like any grouped CLI.

    A Typer app carrying one command has no list to render, which is what
    made the commands invisible when they were dispatched by hand.
    """

    def _help(self):
        import subprocess
        import sys

        code = "import sys; from execsql.cli.dispatch import dispatch; sys.argv=['execsql','--help']; dispatch()"
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout

    def test_a_commands_section_exists(self):
        assert "Commands" in self._help()

    @pytest.mark.parametrize("name", ["run", "format", "lint"])
    def test_each_command_is_listed(self, name):
        assert name in self._help()

    def test_the_alias_is_not_listed_twice(self):
        """fmt is hidden so the list shows one spelling of the formatter."""
        assert self._help().count("fmt") == 0


class TestHelpIsDiscoverable:
    """The commands have to be findable, which is the point of having them.

    Both of these were shipped broken: ``execsql --help`` listed no commands,
    so the toolchain was invisible to anyone who did not read the README, and
    ``execsql lint --help`` crashed because the verb had no argument parser
    and read ``--help`` as a file name.
    """

    def _cli(self, *args):
        """Invoke the console entry point the way a user does."""
        import subprocess
        import sys

        code = "import sys; from execsql.cli.dispatch import dispatch; sys.argv=['execsql', *sys.argv[1:]]; dispatch()"
        return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True)

    def test_main_help_lists_the_commands(self):
        out = self._cli("--help").stdout
        for verb in ("run", "format", "lint"):
            assert verb in out, f"{verb} missing from execsql --help"

    def test_main_help_says_the_bare_form_still_works(self):
        assert "no command" in self._cli("--help").stdout.lower()

    def test_lint_help_does_not_crash(self):
        result = self._cli("lint", "--help")
        assert "Traceback" not in result.stderr, result.stderr
        assert result.returncode == 0

    def test_lint_help_names_the_subcommand(self):
        assert "execsql lint" in self._cli("lint", "--help").stdout

    def test_format_help_does_not_crash(self):
        result = self._cli("format", "--help")
        assert "Traceback" not in result.stderr, result.stderr
        assert result.returncode == 0

    def test_lint_with_no_arguments_shows_help_rather_than_failing(self):
        result = self._cli("lint")
        assert "Traceback" not in result.stderr, result.stderr


class TestHelpColor:
    """Help is colored on a terminal and nowhere else.

    The styling is ANSI wrapped around text the plain renderer already
    produced, so the strongest check is that stripping the codes gives back
    exactly the uncolored help: same words, same columns, same wrapping.
    """

    ANSI = re.compile(r"\x1b\[[0-9;]*m")
    PAGES = [["--help"], ["run", "--help"], ["format", "--help"], ["lint", "--help"]]

    @pytest.fixture(autouse=True)
    def _color_allowed(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("EXECSQL_NO_COLOR", raising=False)

    def _help(self, args, *, color):
        from typer.testing import CliRunner

        from execsql.cli import app

        result = CliRunner().invoke(app, args, color=color)
        assert result.exit_code == 0, result.output
        return result.output

    @pytest.mark.parametrize("args", PAGES, ids=" ".join)
    def test_help_is_colored_on_a_terminal(self, args):
        assert self.ANSI.search(self._help(args, color=True))

    @pytest.mark.parametrize("args", PAGES, ids=" ".join)
    def test_color_changes_nothing_but_color(self, args):
        colored = self._help(args, color=True)
        assert self.ANSI.sub("", colored) == self._help(args, color=False)

    @pytest.mark.parametrize("variable", ["NO_COLOR", "EXECSQL_NO_COLOR"])
    def test_no_color_variables_turn_it_off(self, monkeypatch, variable):
        monkeypatch.setenv(variable, "1")
        assert not self.ANSI.search(self._help(["--help"], color=True))

    def test_piped_help_has_no_escape_codes(self):
        """A real pipe, not the test runner's stand-in for one."""
        import subprocess
        import sys

        code = "import sys; from execsql.cli.dispatch import dispatch; sys.argv=['execsql', '--help']; dispatch()"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout
        assert "Commands:" in out
        assert "\x1b[" not in out

    def test_hidden_alias_stays_hidden(self):
        assert "fmt" not in self.ANSI.sub("", self._help(["--help"], color=True))


class TestUsageLines:
    """The usage line is the same whatever Typer is installed.

    Typer 0.27 started decorating argument metavars (``{FILE_OR_DIR}`` for a
    required argument, ``[...]`` around an optional one), so these lines
    changed with a dependency upgrade. They are drawn from the metavar as
    written, and the variadic arguments say so with ``...``. Wrapping depends
    on the Click version and terminal width, so whitespace is normalized.
    """

    @pytest.mark.parametrize(
        ("command", "usage"),
        [
            ("lint", "Usage: execsql lint [OPTIONS] FILE_OR_DIR..."),
            ("format", "Usage: execsql format [OPTIONS] FILE_OR_DIR..."),
            ("run", "Usage: execsql run [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]"),
        ],
    )
    def test_usage_line(self, command, usage):
        from typer.testing import CliRunner

        from execsql.cli import app

        output = CliRunner().invoke(app, [command, "--help"]).output
        assert " ".join(output.split("\n\n", 1)[0].split()) == usage
