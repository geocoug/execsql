"""The ping, config and list commands, and the run flags they replace.

Each hidden alias on ``run`` must produce what its command produces: the
aliases exist so old invocations keep working, and they only keep working if
they cannot drift from the command they point at.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from execsql.cli import app
from execsql.config import ConfigData

runner = CliRunner()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A working directory and home with no execsql.conf in either."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


def _invoke(*args: str):
    return runner.invoke(app, list(args))


# ---------------------------------------------------------------------------
# Command set
# ---------------------------------------------------------------------------


class TestCommandSet:
    def test_help_lists_the_six_commands_in_order(self):
        out = _invoke("--help").output
        section = out[out.index("Commands:") :]
        names = [line.split()[0] for line in section.splitlines()[1:] if line.strip()]
        assert names == ["run", "format", "lint", "ping", "config", "list"]

    @pytest.mark.parametrize(
        "flag",
        ["--lint", "--ping", "--init-config", "--metacommands", "--encodings", "--dump-keywords", "--list-plugins"],
    )
    def test_moved_flags_are_hidden_from_run_help(self, flag):
        assert flag not in _invoke("run", "--help").output


# ---------------------------------------------------------------------------
# list, and the -m / -y / --list-plugins / --dump-keywords aliases
# ---------------------------------------------------------------------------


class TestList:
    @pytest.mark.parametrize(
        ("alias", "thing", "fmt"),
        [
            ("-m", "metacommands", "text"),
            ("--metacommands", "metacommands", "text"),
            ("-y", "encodings", "text"),
            ("--encodings", "encodings", "text"),
            ("--list-plugins", "plugins", "text"),
            ("--dump-keywords", "keywords", "json"),
        ],
    )
    def test_alias_prints_what_the_command_prints(self, alias, thing, fmt):
        via_alias = _invoke(alias)
        via_command = _invoke("list", thing, "--output-format", fmt)
        assert via_alias.exit_code == via_command.exit_code == 0
        assert via_alias.output == via_command.output

    def test_keywords_json_keeps_the_dump_keywords_shape(self):
        data = json.loads(_invoke("list", "keywords", "--output-format", "json").output)
        assert set(data) == {
            "metacommands",
            "conditions",
            "config_options",
            "export_formats",
            "database_types",
            "variable_patterns",
        }

    def test_keywords_text_is_readable_not_json(self):
        out = _invoke("list", "keywords").output
        assert "Conditions" in out
        assert not out.lstrip().startswith("{")

    def test_metacommands_json(self):
        rows = json.loads(_invoke("list", "metacommands", "--output-format", "json").output)
        assert {"name": "EXPORT", "syntax": "<queryname> TO <format> <filename> ..."} in rows

    def test_encodings_json(self):
        names = json.loads(_invoke("list", "encodings", "--output-format", "json").output)
        assert "latin1" in names
        assert names == sorted(names)

    def test_plugins_json(self):
        data = json.loads(_invoke("list", "plugins", "--output-format", "json").output)
        assert set(data) == {"metacommands", "exporters", "importers"}

    def test_unknown_thing_is_a_usage_error(self):
        assert _invoke("list", "tables").exit_code == 2

    def test_thing_is_required(self):
        assert _invoke("list").exit_code == 2


# ---------------------------------------------------------------------------
# config, and the --init-config alias
# ---------------------------------------------------------------------------


class TestConfig:
    def test_init_prints_the_template(self):
        out = _invoke("config", "--init").output
        assert "[connect]" in out

    def test_init_config_alias_matches(self):
        assert _invoke("--init-config").output == _invoke("config", "--init").output

    def test_no_files_means_every_option_is_default(self, isolated):
        data = json.loads(_invoke("config", "--output-format", "json").output)
        assert data["files_read"] == []
        assert all(opt["source"] is None for opt in data["options"])
        db_type = next(o for o in data["options"] if o["key"] == "db_type")
        assert db_type["value"] == db_type["default"] == "l"

    def test_reports_the_file_that_set_each_value(self, isolated):
        (isolated / "execsql.conf").write_text("[connect]\nserver = db.example\ndb_type = p\n")
        data = json.loads(_invoke("config", "--output-format", "json").output)
        by_key = {o["key"]: o for o in data["options"]}
        assert by_key["server"]["value"] == "db.example"
        assert by_key["server"]["source"] == str(isolated / "execsql.conf")
        assert by_key["db_type"] == {
            "section": "connect",
            "key": "db_type",
            "type": "enum",
            "value": "p",
            "default": "l",
            "source": str(isolated / "execsql.conf"),
        }
        assert by_key["port"]["source"] is None

    def test_script_directory_config_is_read(self, isolated):
        sub = isolated / "sub"
        sub.mkdir()
        (sub / "execsql.conf").write_text("[encoding]\nscript = latin1\n")
        (sub / "etl.sql").write_text("")
        without = json.loads(_invoke("config", "--output-format", "json").output)
        with_script = json.loads(_invoke("config", str(sub / "etl.sql"), "--output-format", "json").output)
        assert without["files_read"] == []
        assert with_script["files_read"] == [str(sub / "execsql.conf")]

    def test_config_option_is_read_last(self, isolated):
        (isolated / "execsql.conf").write_text("[encoding]\nscript = latin1\n")
        extra = isolated / "extra.conf"
        extra.write_text("[encoding]\nscript = cp1252\n")
        data = json.loads(_invoke("config", "--config", str(extra), "--output-format", "json").output)
        script = next(o for o in data["options"] if o["section"] == "encoding" and o["key"] == "script")
        assert script["value"] == "cp1252"
        assert script["source"] == str(extra)

    def test_passwords_are_masked(self, isolated):
        (isolated / "execsql.conf").write_text("[email]\npassword = hunter2\n")
        result = _invoke("config", "--output-format", "json")
        assert "hunter2" not in result.output
        password = next(o for o in json.loads(result.output)["options"] if o["key"] == "password")
        assert password["value"] == "***"
        assert "hunter2" not in _invoke("config").output

    def test_text_output_lists_each_section_once(self, isolated):
        out = _invoke("config").output
        headers = [line.strip() for line in out.splitlines() if line.strip().startswith("[")]
        assert len(headers) == len(set(headers))
        assert "[connect]" in headers

    def test_missing_config_file_is_a_usage_error(self, isolated):
        assert _invoke("config", "--config", "nope.conf").exit_code == 2

    def test_missing_script_is_a_usage_error(self, isolated):
        assert _invoke("config", "nope.sql").exit_code == 2


class TestConfigSources:
    """``ConfigData.sources`` and ``defaults``, which ``execsql config`` reports."""

    def test_either_spelling_of_an_aliased_key_is_attributed(self, isolated):
        (isolated / "execsql.conf").write_text("[connect]\ndb = warehouse\n")
        conf = ConfigData(str(isolated), None)  # type: ignore[arg-type]
        assert conf.db == "warehouse"
        assert conf.sources["db"] == str(isolated / "execsql.conf")

    def test_later_file_wins_the_source(self, isolated):
        (isolated / "execsql.conf").write_text("[connect]\nport = 1\n")
        extra = isolated / "extra.conf"
        extra.write_text("[connect]\nport = 2\n")
        conf = ConfigData(str(isolated), None, config_file=str(extra))  # type: ignore[arg-type]
        assert conf.port == 2
        assert conf.sources["port"] == str(extra)

    def test_defaults_are_captured_before_any_file(self, isolated):
        (isolated / "execsql.conf").write_text("[input]\nscan_lines = 7\n")
        conf = ConfigData(str(isolated), None)  # type: ignore[arg-type]
        assert conf.scan_lines == 7
        assert conf.defaults["scan_lines"] == 100


# ---------------------------------------------------------------------------
# ping, and the --ping alias
# ---------------------------------------------------------------------------


class TestPing:
    @pytest.fixture
    def db(self, tmp_path):
        path = tmp_path / "ping.db"
        sqlite3.connect(path).close()
        return path

    def test_text(self, db, isolated):
        result = _invoke("ping", "-t", "l", str(db))
        assert result.exit_code == 0
        assert "Connected" in result.output

    def test_json(self, db, isolated):
        result = _invoke("ping", "-t", "l", str(db), "--output-format", "json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dbms"] == "SQLite"
        assert data["location"] == str(db)
        assert data["version"]

    def test_dsn(self, db, isolated):
        assert _invoke("ping", "--dsn", f"sqlite:///{db}").exit_code == 0

    def test_missing_database_fails_and_is_not_created(self, tmp_path, isolated):
        missing = tmp_path / "missing.db"
        result = _invoke("ping", "-t", "l", str(missing))
        assert result.exit_code == 1
        assert not missing.exists()

    def test_new_db_option_is_refused(self, tmp_path, isolated):
        missing = tmp_path / "missing.db"
        assert _invoke("ping", "-t", "l", "-n", str(missing)).exit_code == 2
        assert not missing.exists()

    def test_new_db_in_config_does_not_create(self, tmp_path, isolated):
        (isolated / "execsql.conf").write_text("[connect]\nnew_db = yes\n")
        missing = tmp_path / "missing.db"
        assert _invoke("ping", "-t", "l", str(missing)).exit_code == 1
        assert not missing.exists()

    def test_ping_alias_still_creates_with_new_db(self, tmp_path, isolated):
        """The --ping alias keeps its original behavior, -n included."""
        created = tmp_path / "created.db"
        assert _invoke("--ping", "-t", "l", "-n", str(created)).exit_code == 0
        assert created.exists()

    def test_bad_type_is_a_usage_error(self, isolated):
        assert _invoke("ping", "-t", "z", "x.db").exit_code == 2

    def test_missing_config_file_is_a_usage_error(self, isolated):
        assert _invoke("ping", "--config", "nope.conf", "x.db").exit_code == 2
