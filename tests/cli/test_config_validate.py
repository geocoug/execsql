"""``execsql config --validate``: every problem in every config file a run reads."""

from __future__ import annotations

import json
import sys

import pytest
from typer.testing import CliRunner

from execsql.cli import app
from execsql.config import ConfigData
from execsql.config_validation import known_options, validate_config
from execsql.exceptions import ConfigError
from execsql.script.variables import SubVarSet

runner = CliRunner()


@pytest.fixture
def work(tmp_path, monkeypatch):
    """A working directory and home with no execsql.conf in either."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


def _validate(*args: str):
    result = runner.invoke(app, ["config", "--validate", "--output-format", "json", *args])
    return result.exit_code, json.loads(result.output)


def _problems(work, text: str) -> list[tuple[int | None, str, str]]:
    (work / "execsql.conf").write_text(text)
    _code, data = _validate()
    return [(p["line"], p["severity"], p["message"]) for p in data["problems"]]


class TestFiles:
    def test_no_config_files(self, work):
        result = runner.invoke(app, ["config", "--validate"])
        assert result.exit_code == 0
        assert "No config files found." in result.output

    def test_clean_file(self, work):
        (work / "execsql.conf").write_text("[connect]\nserver = db.example\ndb_type = p\n")
        result = runner.invoke(app, ["config", "--validate"])
        assert result.exit_code == 0
        assert "No problems found (1 config file checked)." in result.output

    def test_script_directory_file_is_checked(self, work):
        sub = work / "sub"
        sub.mkdir()
        (sub / "execsql.conf").write_text("[connect]\ndb_type = q\n")
        (sub / "etl.sql").write_text("")
        assert _validate()[1]["files_checked"] == []
        code, data = _validate(str(sub / "etl.sql"))
        assert code == 1
        assert data["files_checked"] == [str(sub / "execsql.conf")]

    def test_config_option_file_is_checked(self, work):
        extra = work / "ci.conf"
        extra.write_text("[connect]\ndb_type = q\n")
        code, data = _validate("--config", str(extra))
        assert code == 1
        assert data["problems"][0]["file"] == str(extra)

    def test_chained_file_is_checked(self, work):
        chained = work / "shared.conf"
        chained.write_text("[connect]\ndb_type = q\n")
        (work / "execsql.conf").write_text(f"[config]\nconfig_file = {chained}\n")
        code, data = _validate()
        assert code == 1
        assert data["files_checked"] == [str(work / "execsql.conf"), str(chained)]
        assert data["problems"][0]["file"] == str(chained)

    def test_missing_chained_file_is_a_warning(self, work):
        problems = _problems(work, "[config]\nconfig_file = /no/such/place.conf\n")
        assert problems == [(2, "warning", "config_file = /no/such/place.conf: no such file; a run skips it")]

    @pytest.mark.skipif(sys.platform == "win32", reason="checks a non-Windows host")
    def test_another_platforms_chain_key_is_not_checked(self, work):
        assert _problems(work, "[config]\nwin_config_file = C:\\nowhere\\execsql.conf\n") == []


class TestUnknownNames:
    def test_misspelled_key(self, work):
        assert _problems(work, "[connect]\nsever = db.example\n") == [
            (2, "warning", "unknown key 'sever' in [connect]; did you mean 'server'?"),
        ]

    def test_unknown_key_without_a_near_match(self, work):
        assert _problems(work, "[connect]\nflavour = mint\n") == [
            (2, "warning", "unknown key 'flavour' in [connect]; a run ignores it"),
        ]

    def test_key_in_the_wrong_section(self, work):
        assert _problems(work, "[interface]\nscan_lines = 5\n") == [
            (2, "warning", "scan_lines belongs in [input], not [interface]"),
        ]

    def test_misspelled_section(self, work):
        assert _problems(work, "[conect]\nserver = a\n") == [
            (1, "warning", "unknown section [conect]; did you mean [connect]?"),
        ]

    def test_section_names_are_case_sensitive(self, work):
        """A run reads [connect]; [Connect] is silently ignored, so say so."""
        assert _problems(work, "[Connect]\nserver = a\n") == [
            (1, "warning", "unknown section [Connect]; did you mean [connect]?"),
        ]

    def test_free_form_sections_accept_any_key(self, work):
        assert _problems(work, "[variables]\nregion = west\n") == []

    def test_warnings_alone_exit_zero(self, work):
        (work / "execsql.conf").write_text("[connect]\nsever = a\n")
        assert _validate()[0] == 0


class TestValues:
    def test_invalid_value(self, work):
        assert _problems(work, "[connect]\nserver = a\ndb_type = q\n") == [
            (3, "error", "db_type = q: Invalid database type: q"),
        ]

    def test_every_error_is_reported_not_just_the_first(self, work):
        problems = _problems(work, "[connect]\ndb_type = q\nport = abc\n[interface]\ngui_level = 9\n")
        assert [(line, severity) for line, severity, _ in problems] == [(2, "error"), (3, "error"), (5, "error")]

    def test_missing_required_include(self, work):
        missing = work / "no" / "such" / "file.sql"
        problems = _problems(work, f"[include_required]\n1 = {missing}\n")
        # A run resolves the path, so the message names the resolved file
        # (on Windows, with a drive letter).
        assert problems == [
            (2, "error", f"1 = {missing}: Required include file {missing.resolve()} does not exist."),
        ]

    def test_include_keys_must_be_numbers(self, work):
        (work / "a.sql").write_text("")
        problems = _problems(work, f"[include_optional]\nfirst = {work / 'a.sql'}\n")
        assert problems == [
            (2, "error", f"first = {work / 'a.sql'}: keys in [include_optional] must be numbers, not 'first'"),
        ]

    def test_invalid_variable_name(self, work):
        problems = _problems(work, "[variables]\nbad name = 1\n")
        assert [(line, severity) for line, severity, _ in problems] == [(2, "error")]

    def test_bare_percent(self, work):
        assert _problems(work, "[connect]\nserver = 50%\n") == [(2, "error", "server: a literal % must be written %%")]

    def test_escaped_percent_is_fine(self, work):
        assert _problems(work, "[connect]\nserver = 50%%\n") == []

    @pytest.mark.parametrize(
        ("section", "key", "value"),
        [
            ("connect", "db_type", "p"),
            ("connect", "db_type", "q"),
            ("connect", "port", "5432"),
            ("connect", "port", "abc"),
            ("connect", "new_db", "yes"),
            ("connect", "new_db", "maybe"),
            ("interface", "gui_level", "2"),
            ("interface", "gui_level", "9"),
            ("interface", "gui_framework", "textual"),
            ("interface", "gui_framework", "qt"),
            ("config", "dao_flush_delay_secs", "10"),
            ("config", "dao_flush_delay_secs", "1"),
            ("email", "email_format", "html"),
            ("email", "email_format", "rtf"),
            ("encoding", "script", "latin1"),
        ],
    )
    def test_validation_agrees_with_a_run(self, work, section, key, value):
        """--validate reports an error exactly when loading the config for a run fails."""
        (work / "execsql.conf").write_text(f"[{section}]\n{key} = {value}\n")
        try:
            ConfigData(str(work), SubVarSet())
        except ConfigError:
            run_fails = True
        else:
            run_fails = False
        _files, problems = validate_config(str(work), SubVarSet())
        assert any(p.severity == "error" for p in problems) is run_fails


class TestUnreadableFiles:
    def test_no_section_header(self, work):
        assert _problems(work, "server = a\n") == [
            (1, "error", "a section header such as [connect] must come before the first option"),
        ]

    def test_duplicate_key(self, work):
        assert _problems(work, "[connect]\nserver = a\nserver = b\n") == [
            (3, "error", "server is set twice in [connect]"),
        ]

    def test_duplicate_section(self, work):
        assert _problems(work, "[connect]\nserver = a\n[connect]\nport = 1\n") == [
            (3, "error", "[connect] appears twice"),
        ]


class TestCommand:
    def test_text_output(self, work):
        (work / "execsql.conf").write_text("[connect]\nsever = a\ndb_type = q\n")
        result = runner.invoke(app, ["config", "--validate"])
        assert result.exit_code == 1
        out = " ".join(result.output.split())
        assert "2 warning unknown key 'sever' in [connect]; did you mean 'server'?" in out
        assert "3 error db_type = q: Invalid database type: q" in out
        assert "Found 2 problems in 1 file: 1 error, 1 warning (1 config file checked)" in out

    def test_json_shape(self, work):
        (work / "execsql.conf").write_text("[connect]\nsever = a\n")
        _code, data = _validate()
        assert data == {
            "files_checked": [str(work / "execsql.conf")],
            "problems": [
                {
                    "file": str(work / "execsql.conf"),
                    "line": 2,
                    "severity": "warning",
                    "message": "unknown key 'sever' in [connect]; did you mean 'server'?",
                },
            ],
        }

    def test_init_and_validate_cannot_be_combined(self):
        assert runner.invoke(app, ["config", "--init", "--validate"]).exit_code == 2


def test_known_options_cover_every_registered_key():
    known = known_options()
    for section, key, _attr in ConfigData._option_keys:
        assert key in known[section]
    assert {"config_file", "linux_config_file", "macos_config_file", "win_config_file"} <= known["config"]
