"""The CLI surface — every command, option and hidden alias — as a reviewed contract.

The CLI is a public API: shell scripts, cron entries and CI steps depend on
its spellings. These tests pin the whole surface so that adding, renaming,
hiding or removing anything is a deliberate change that shows up in review as
an edit to ``SURFACE`` below, together with a CHANGELOG entry and, where it
departs from upstream, docs/about/divergence.md.

They read Click's command objects rather than rendered help text, so they
hold across the supported Typer/Click range, including the ``typer-floor``
CI job; help wording and layout are free to change.
"""

from __future__ import annotations

import sqlite3

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from execsql.cli import app

#: Global options, and per command: the argument metavars, the options shown
#: in help, and the hidden spellings that still work. Each option is its
#: spellings, shortest first.
GLOBAL_OPTIONS = {"--version", "-o --online-help"}

SURFACE: dict[str, dict[str, object]] = {
    "run": {
        "arguments": ["[SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]]"],
        "options": {
            "--config",
            "--debug",
            "--dry-run",
            "--dsn --connection-string",
            "--gui-framework",
            "--manifest",
            "--no-rm-file",
            "--no-serve",
            "--no-system-cmd",
            "--output-dir",
            "--parse-tree",
            "--profile",
            "--profile-limit",
            "--progress",
            "--var",
            "--ping",
            "-a --assign-arg",
            "-b --boolean-int",
            "-c --command",
            "-d --directories",
            "-e --database-encoding",
            "-f --script-encoding",
            "-g --output-encoding",
            "-i --import-encoding",
            "-l --user-logfile",
            "-n --new-db",
            "-p --port",
            "-s --scan-lines",
            "-t --type",
            "-u --user",
            "-v --visible-prompts",
            "-w --no-passwd",
            "-z --import-buffer",
        },
        "hidden": {
            # Flags that became commands, kept working (docs/about/divergence.md).
            "--dump-keywords",
            "--init-config",
            "--list-plugins",
            "-m --metacommands",
            "-y --encodings",
            # Removed; declared only to refuse it with a pointer to `execsql lint`.
            "--lint",
            # The global options again: upstream accepted them anywhere.
            "--version",
            "-o --online-help",
        },
    },
    "format": {
        "arguments": ["FILE_OR_DIR..."],
        "options": {
            "--check",
            "--config",
            "--diff",
            "--indent",
            "--leading-comma --no-leading-comma",
            "--rewrite-sql --no-rewrite-sql",
            "--sql --no-sql",
            "-f --script-encoding",
            "-i --in-place",
        },
        "hidden": {"--encoding"},
    },
    "lint": {
        "arguments": ["FILE_OR_DIR..."],
        "options": {
            "--config",
            "--ignore",
            "--output-format",
            "--select",
            "--statistics",
            "--strict --no-strict",
            "-f --script-encoding",
        },
        "hidden": set(),
    },
    "config": {
        "arguments": ["[SQL_SCRIPT]"],
        "options": {"--config", "--init", "--output-format", "--validate"},
        "hidden": set(),
    },
    "list": {"arguments": [], "options": set(), "hidden": set()},
    "init": {
        "arguments": ["[DIR]"],
        "options": {"--force", "--no-config", "--no-pre-commit", "--no-script", "--script"},
        "hidden": set(),
    },
}

#: ``execsql list`` is a group: one command per reference list.
LIST_COMMANDS = {name: {"--output-format"} for name in ("metacommands", "encodings", "plugins", "keywords")}


def _spellings(param) -> str:
    return " ".join(sorted([*param.opts, *param.secondary_opts], key=lambda o: (len(o), o)))


def _options(command, *, hidden: bool) -> set[str]:
    return {
        _spellings(p)
        for p in command.params
        if p.param_type_name == "option" and p.name != "help" and bool(getattr(p, "hidden", False)) is hidden
    }


@pytest.fixture(scope="module")
def group():
    return get_command(app)


class TestSurface:
    def test_global_options(self, group):
        assert _options(group, hidden=False) == GLOBAL_OPTIONS

    def test_listed_commands_in_help_order(self, group):
        listed = [name for name in group.list_commands(None) if not group.commands[name].hidden]
        assert listed == list(SURFACE)

    def test_list_commands(self, group):
        lists = group.commands["list"]
        assert list(lists.list_commands(None)) == list(LIST_COMMANDS)
        for name, options in LIST_COMMANDS.items():
            assert _options(lists.commands[name], hidden=False) == options
            assert _options(lists.commands[name], hidden=True) == set()

    def test_no_hidden_commands(self, group):
        assert [name for name, cmd in group.commands.items() if cmd.hidden] == []

    @pytest.mark.parametrize("name", list(SURFACE))
    def test_arguments(self, group, name):
        command = group.commands[name]
        assert [p.metavar for p in command.params if p.param_type_name == "argument"] == SURFACE[name]["arguments"]

    @pytest.mark.parametrize("name", list(SURFACE))
    def test_visible_options(self, group, name):
        assert _options(group.commands[name], hidden=False) == SURFACE[name]["options"]

    @pytest.mark.parametrize("name", list(SURFACE))
    def test_hidden_options(self, group, name):
        assert _options(group.commands[name], hidden=True) == SURFACE[name]["hidden"]

    @pytest.mark.parametrize("name", list(SURFACE))
    def test_every_command_answers_short_help(self, group, name):
        assert "-h" in group.commands[name].context_settings.get("help_option_names", ["-h", "--help"])


# ---------------------------------------------------------------------------
# Exit codes: 0 success, 1 the task failed or found problems, 2 bad command line
# ---------------------------------------------------------------------------


@pytest.fixture
def files(tmp_path, monkeypatch):
    """A clean script, a script with a lint error, an unformatted script and a database."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "clean.sql").write_text("-- !x! WRITE 'hi'\n")
    (tmp_path / "broken.sql").write_text("-- !x! IF (true)\n")
    (tmp_path / "messy.sql").write_text("-- !x! write 'hi'\n")
    (tmp_path / "warned.sql").write_text('-- !x! WRITE "!!nope!!"\n')
    sqlite3.connect(tmp_path / "db.sqlite").close()
    return tmp_path


EXIT_CODES = [
    # format
    (["format", "--no-sql", "--check", "clean.sql"], 0),
    (["format", "--no-sql", "--check", "messy.sql"], 1),
    (["format", "--no-sql", "--diff", "messy.sql"], 1),
    (["format", "--bogus", "clean.sql"], 2),
    (["format"], 2),
    # lint
    (["lint", "clean.sql"], 0),
    (["lint", "broken.sql"], 1),
    (["lint", "--strict", "warned.sql"], 1),
    (["lint", "--select", "Z9", "clean.sql"], 2),
    (["lint"], 2),
    # list
    (["list", "keywords"], 0),
    (["list", "tables"], 2),
    (["list"], 2),
    # config
    (["config"], 0),
    (["config", "--config", "missing.conf"], 2),
    (["config", "missing.sql"], 2),
    # run keeps upstream's codes: a missing script is a failed task, and
    # unknown options are not rejected (upstream let them through). The
    # removed --lint is a usage error and runs nothing.
    (["run", "missing.sql"], 1),
    (["run", "--ping", "-t", "l", "db.sqlite"], 0),
    (["run", "--ping", "-t", "l", "missing.sqlite"], 1),
    (["run", "--lint", "clean.sql"], 2),
]


@pytest.mark.parametrize(("args", "code"), EXIT_CODES, ids=[" ".join(a) for a, _ in EXIT_CODES])
def test_exit_code(files, args, code):
    assert CliRunner().invoke(app, args).exit_code == code
