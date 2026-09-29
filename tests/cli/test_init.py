"""``execsql init``: a config file, a script with a header, and the pre-commit hooks."""

from __future__ import annotations

import datetime

import pytest
from typer.testing import CliRunner

from execsql import __version__
from execsql.cli import app
from execsql.cli.commands.init import pre_commit_snippet, script_header

runner = CliRunner()


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _init(*args: str):
    return runner.invoke(app, ["init", *args])


class TestFreshProject:
    def test_creates_the_three_files(self, work):
        result = _init("proj")
        assert result.exit_code == 0
        assert sorted(p.name for p in (work / "proj").iterdir()) == [
            ".pre-commit-config.yaml",
            "execsql.conf",
            "main.sql",
        ]

    def test_config_is_the_template(self, work):
        _init("proj")
        assert runner.invoke(app, ["config", "--init"]).output == (work / "proj" / "execsql.conf").read_text()

    def test_script_has_a_header_with_name_and_date(self, work):
        _init("proj")
        text = (work / "proj" / "main.sql").read_text()
        assert text.startswith("-- main.sql\n")
        assert f"{datetime.date.today().isoformat()}  Created." in text
        assert "-- PURPOSE" in text and "-- HISTORY" in text

    def test_pre_commit_config_has_both_hooks_at_this_version(self, work):
        _init("proj")
        assert (work / "proj" / ".pre-commit-config.yaml").read_text() == "repos:\n" + pre_commit_snippet()
        assert f"rev: v{__version__}" in pre_commit_snippet()

    def test_created_script_passes_the_hooks_it_installs(self, work):
        """A new project must not fail its own format and lint hooks."""
        _init("proj")
        script = str(work / "proj" / "main.sql")
        assert runner.invoke(app, ["format", "--check", "--no-sql", script]).exit_code == 0
        assert runner.invoke(app, ["lint", "--strict", script]).exit_code == 0

    def test_current_directory_by_default(self, work):
        assert _init().exit_code == 0
        assert (work / "execsql.conf").is_file()


class TestOptions:
    def test_script_name_gets_sql_suffix_and_parent_dirs(self, work):
        _init("proj", "--script", "scripts/load")
        assert (work / "proj" / "scripts" / "load.sql").read_text().startswith("-- load.sql\n")

    def test_no_flags(self, work):
        _init("proj", "--no-config", "--no-pre-commit", "--script", "load.sql")
        assert sorted(p.name for p in (work / "proj").iterdir()) == ["load.sql"]
        _init("other", "--no-script")
        assert not (work / "other" / "main.sql").exists()

    def test_nothing_to_do(self, work):
        result = _init("proj", "--no-config", "--no-script", "--no-pre-commit")
        assert result.exit_code == 0
        assert "Nothing to do" in result.output


class TestExistingFiles:
    def test_existing_files_are_skipped(self, work):
        _init("proj")
        (work / "proj" / "main.sql").write_text("select 1;\n")
        result = _init("proj")
        assert (work / "proj" / "main.sql").read_text() == "select 1;\n"
        assert "exists; --force to overwrite" in result.output
        assert "already has the execsql hooks" in result.output

    def test_force_overwrites_config_and_script_but_not_pre_commit(self, work):
        _init("proj")
        (work / "proj" / "main.sql").write_text("select 1;\n")
        (work / "proj" / ".pre-commit-config.yaml").write_text("# mine\nrepos: []\n")
        result = _init("proj", "--force")
        assert (work / "proj" / "main.sql").read_text() == script_header("main.sql")
        assert "overwrote" in result.output
        assert (work / "proj" / ".pre-commit-config.yaml").read_text().startswith("# mine\n")

    def test_hooks_appended_with_the_files_indentation(self, work):
        existing = "# project hooks\nrepos:\n- repo: https://github.com/pre-commit/pre-commit-hooks\n  rev: v5.0.0\n  hooks:\n  - id: trailing-whitespace\n"
        (work / ".pre-commit-config.yaml").write_text(existing)
        result = _init("--no-config", "--no-script")
        assert "added" in result.output
        assert (work / ".pre-commit-config.yaml").read_text() == existing + pre_commit_snippet("")

    def test_repos_not_last_is_left_alone_and_the_snippet_printed(self, work):
        existing = "repos:\n  - repo: local\n    hooks: []\nci:\n  autofix_prs: false\n"
        (work / ".pre-commit-config.yaml").write_text(existing)
        result = _init("--no-config", "--no-script")
        assert (work / ".pre-commit-config.yaml").read_text() == existing
        assert "add by hand" in result.output
        assert "execsql-lint" in result.output
