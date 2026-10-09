"""The config and list commands, and the run flags they replace (-m, -y, --list-plugins, --dump-keywords, --init-config)."""

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
    def test_help_lists_the_commands_in_order(self):
        out = _invoke("--help").output
        section = out[out.index("Commands:") :]
        names = [line.split()[0] for line in section.splitlines()[1:] if line.strip()]
        assert names == ["run", "format", "lint", "config", "list", "init"]

    def test_ping_is_listed_in_run_help(self):
        assert "--ping" in _invoke("run", "--help").output

    @pytest.mark.parametrize(
        "flag",
        ["--lint", "--init-config", "--metacommands", "--encodings", "--dump-keywords", "--list-plugins"],
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
        # Through `run`, which prints no deprecation warning into the output.
        via_alias = _invoke("run", alias)
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

    def test_unknown_list_is_a_usage_error(self):
        assert _invoke("list", "tables").exit_code == 2

    def test_bare_list_prints_its_help_and_exits_2(self):
        result = _invoke("list")
        assert result.exit_code == 2
        assert "metacommands" in result.output


# ---------------------------------------------------------------------------
# config, and the --init-config alias
# ---------------------------------------------------------------------------


class TestConfig:
    def test_init_prints_the_template(self):
        out = _invoke("config", "--init").output
        assert "[connect]" in out

    def test_init_config_alias_matches(self):
        assert _invoke("run", "--init-config").output == _invoke("config", "--init").output

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

    def test_connects_and_reports(self, db, isolated):
        result = _invoke("--ping", "-t", "l", str(db))
        assert result.exit_code == 0
        assert "Connected" in result.output

    def test_dsn(self, db, isolated):
        assert _invoke("--ping", "--dsn", f"sqlite:///{db}").exit_code == 0

    def test_missing_database_fails_and_is_not_created(self, tmp_path, isolated):
        missing = tmp_path / "missing.db"
        assert _invoke("--ping", "-t", "l", str(missing)).exit_code == 1
        assert not missing.exists()

    def test_new_db_creates(self, tmp_path, isolated):
        created = tmp_path / "created.db"
        assert _invoke("--ping", "-t", "l", "-n", str(created)).exit_code == 0
        assert created.exists()


# ---------------------------------------------------------------------------
# format and lint input: stdin, --script-encoding, --config
# ---------------------------------------------------------------------------

LATIN1_SCRIPT = "-- caf\xe9\nselect 1;\n".encode("latin-1")


class TestFormatInput:
    def test_stdin_to_stdout(self):
        result = runner.invoke(app, ["format", "--no-sql", "-"], input="-- !x! write 'hi'\n")
        assert result.exit_code == 0
        assert result.output == "-- !x! WRITE 'hi'\n"

    def test_stdin_check(self):
        assert runner.invoke(app, ["format", "--no-sql", "--check", "-"], input="-- !x! write 'hi'\n").exit_code == 1
        assert runner.invoke(app, ["format", "--no-sql", "--check", "-"], input="-- !x! WRITE 'hi'\n").exit_code == 0

    def test_stdin_cannot_be_formatted_in_place(self):
        assert runner.invoke(app, ["format", "-i", "-"], input="select 1;\n").exit_code == 2

    def test_stdin_cannot_be_mixed_with_paths(self, tmp_path):
        (tmp_path / "a.sql").write_text("select 1;\n")
        assert runner.invoke(app, ["format", "-", str(tmp_path / "a.sql")], input="").exit_code == 2

    def test_script_encoding(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        assert runner.invoke(app, ["format", "--no-sql", "--check", str(path)]).exit_code == 1
        assert runner.invoke(app, ["format", "--no-sql", "--check", "-f", "latin1", str(path)]).exit_code == 0

    def test_decode_error_names_the_option(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        result = runner.invoke(app, ["format", "--no-sql", str(path)])
        assert "--script-encoding" in result.output

    def test_old_encoding_option_still_works_and_is_hidden(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        assert runner.invoke(app, ["format", "--no-sql", "--check", "--encoding", "latin1", str(path)]).exit_code == 0
        assert "--encoding" not in runner.invoke(app, ["format", "--help"]).output

    def test_encoding_from_config(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        (isolated / "execsql.conf").write_text("[encoding]\nscript = latin1\n")
        assert runner.invoke(app, ["format", "--no-sql", "--check", str(path)]).exit_code == 0

    def test_encoding_from_config_option(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        conf = tmp_path / "ci.conf"
        conf.write_text("[encoding]\nscript = latin1\n")
        assert runner.invoke(app, ["format", "--no-sql", "--check", "--config", str(conf), str(path)]).exit_code == 0

    def test_script_encoding_beats_config(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        (isolated / "execsql.conf").write_text("[encoding]\nscript = latin1\n")
        assert runner.invoke(app, ["format", "--no-sql", "--check", "-f", "utf-8", str(path)]).exit_code == 1

    def test_missing_config_file_is_a_usage_error(self, tmp_path):
        (tmp_path / "a.sql").write_text("select 1;\n")
        assert runner.invoke(app, ["format", "--config", "nope.conf", str(tmp_path / "a.sql")]).exit_code == 2


class TestLintInput:
    def test_stdin(self):
        result = runner.invoke(app, ["lint", "-", "--output-format", "json"], input='-- !x! write "!!nope!!"\n')
        assert result.exit_code == 0
        issues = json.loads(result.output)
        assert [(i["file"], i["code"]) for i in issues] == [("<stdin>", "V001")]

    def test_unknown_metacommands_fail_the_lint(self):
        script = "-- !x! FROBNICATE now\n-- !x! EXPORT nosuch TOO x.csv AS CSV\n"
        result = runner.invoke(app, ["lint", "-", "--output-format", "json"], input=script)
        assert result.exit_code == 1
        assert [(i["line"], i["code"]) for i in json.loads(result.output)] == [(1, "P003"), (2, "P003")]

    def test_a_script_that_does_not_parse_still_gets_metacommand_checks(self):
        script = "-- !x! IF(True)\n-- !x! iff(True)\n-- !x! ENDIF\n-- !x! ENDIF\n"
        result = runner.invoke(app, ["lint", "-", "--output-format", "json"], input=script)
        assert result.exit_code == 1
        assert [(i["line"], i["code"]) for i in json.loads(result.output)] == [(2, "P003"), (4, "P001")]

    def test_empty_stdin_is_labelled_stdin(self):
        issues = json.loads(runner.invoke(app, ["lint", "-", "--output-format", "json"], input="").output)
        assert [(i["file"], i["code"]) for i in issues] == [("<stdin>", "S001")]

    def test_stdin_cannot_be_mixed_with_paths(self, tmp_path):
        (tmp_path / "a.sql").write_text("select 1;\n")
        assert runner.invoke(app, ["lint", "-", str(tmp_path / "a.sql")], input="").exit_code == 2

    def test_undecodable_script_is_a_parse_error(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        result = runner.invoke(app, ["lint", str(path), "--output-format", "json"])
        assert result.exit_code == 1
        (issue,) = json.loads(result.output)
        assert issue["code"] == "P001"
        assert "--script-encoding" in issue["message"]

    def test_script_encoding(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        assert runner.invoke(app, ["lint", "-f", "latin1", str(path)]).exit_code == 0

    def test_encoding_from_config(self, tmp_path, isolated):
        path = tmp_path / "latin.sql"
        path.write_bytes(LATIN1_SCRIPT)
        (isolated / "execsql.conf").write_text("[encoding]\nscript = latin1\n")
        assert runner.invoke(app, ["lint", str(path)]).exit_code == 0

    def test_script_directory_config_is_not_read(self, tmp_path, isolated):
        """format and lint read config once, from where they run — not per script."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "execsql.conf").write_text("[encoding]\nscript = latin1\n")
        (sub / "latin.sql").write_bytes(LATIN1_SCRIPT)
        assert runner.invoke(app, ["lint", str(sub / "latin.sql")]).exit_code == 1
        assert (
            runner.invoke(app, ["lint", "--config", str(sub / "execsql.conf"), str(sub / "latin.sql")]).exit_code == 0
        )

    def test_missing_config_file_is_a_usage_error(self, tmp_path):
        (tmp_path / "a.sql").write_text("select 1;\n")
        assert runner.invoke(app, ["lint", "--config", "nope.conf", str(tmp_path / "a.sql")]).exit_code == 2


# ---------------------------------------------------------------------------
# [format] and [lint] config sections
# ---------------------------------------------------------------------------

UNFORMATTED = "-- !x! if (true)\n-- !x! write 'hi'\n-- !x! endif\n"


class TestFormatWithoutSqlglot:
    def test_a_clean_error_names_the_extra(self, tmp_path, isolated):
        from unittest.mock import patch

        script = tmp_path / "s.sql"
        script.write_text("select 1;\n", encoding="utf-8")
        with patch("execsql.format._require_sqlglot", side_effect=ImportError("execsql format requires sqlglot")):
            result = _invoke("format", "--sql", "--check", str(script))
        assert result.exit_code == 1
        assert "execsql format requires sqlglot" in result.output
        assert "Traceback" not in result.output

    def test_no_sql_does_not_need_it(self, tmp_path, isolated):
        from unittest.mock import patch

        script = tmp_path / "s.sql"
        script.write_text("select 1;\n", encoding="utf-8")
        with patch("execsql.format._require_sqlglot", side_effect=ImportError("missing")):
            assert _invoke("format", "--no-sql", "--check", str(script)).exit_code == 0


class TestFormatConfig:
    def _format(self, work, *args):
        (work / "s.sql").write_text(UNFORMATTED)
        return runner.invoke(app, ["format", *args, "s.sql"]).output

    def test_defaults_without_config(self, isolated):
        assert "\n    -- !x! WRITE" in self._format(isolated, "--no-sql")

    def test_indent_from_config(self, isolated):
        (isolated / "execsql.conf").write_text("[format]\nindent = 2\nsql = no\n")
        assert "\n  -- !x! WRITE" in self._format(isolated)

    def test_flag_beats_config(self, isolated):
        (isolated / "execsql.conf").write_text("[format]\nindent = 2\nsql = no\n")
        assert "\n        -- !x! WRITE" in self._format(isolated, "--indent", "8")

    def test_sql_from_config_and_overridden_by_flag(self, isolated):
        (isolated / "s.sql").write_text("select a,b from t;\n")
        (isolated / "execsql.conf").write_text("[format]\nsql = no\n")
        assert runner.invoke(app, ["format", "s.sql"]).output == "select a,b from t;\n"
        pytest.importorskip("sqlglot")
        assert runner.invoke(app, ["format", "--sql", "s.sql"]).output != "select a,b from t;\n"

    def test_leading_comma_from_config_and_turned_off_by_flag(self, isolated):
        pytest.importorskip("sqlglot")
        (isolated / "s.sql").write_text("select a, b from t;\n")
        (isolated / "execsql.conf").write_text("[format]\nleading_comma = yes\n")
        with_config = runner.invoke(app, ["format", "s.sql"]).output
        overridden = runner.invoke(app, ["format", "--no-leading-comma", "s.sql"]).output
        assert "\n    , b" in with_config
        assert "\n    , b" not in overridden

    def test_rewrite_sql_from_config_and_turned_off_by_flag(self, isolated):
        pytest.importorskip("sqlglot")
        (isolated / "s.sql").write_text("select x::int from t;\n")
        assert runner.invoke(app, ["format", "s.sql"]).output == "select x::int from t;\n"  # kept as written
        (isolated / "execsql.conf").write_text("[format]\nrewrite_sql = yes\n")
        assert "CAST(x AS INT)" in runner.invoke(app, ["format", "s.sql"]).output
        assert runner.invoke(app, ["format", "--no-rewrite-sql", "s.sql"]).output == "select x::int from t;\n"

    def test_config_option_file(self, isolated, tmp_path):
        conf = tmp_path / "ci.conf"
        conf.write_text("[format]\nindent = 2\nsql = no\n")
        assert "\n  -- !x! WRITE" in self._format(isolated, "--config", str(conf))


class TestLintConfig:
    SCRIPT = '-- !x! sub unused 1\n-- !x! write "!!nope!!"\n'

    def _codes(self, work, *args):
        (work / "s.sql").write_text(self.SCRIPT)
        out = runner.invoke(app, ["lint", *args, "s.sql", "--output-format", "json"]).output
        return sorted(i["code"] for i in json.loads(out))

    def test_all_rules_without_config(self, isolated):
        assert self._codes(isolated) == ["V001", "V002"]

    def test_ignore_from_config(self, isolated):
        (isolated / "execsql.conf").write_text("[lint]\nignore = V002\n")
        assert self._codes(isolated) == ["V001"]

    def test_select_from_config(self, isolated):
        (isolated / "execsql.conf").write_text("[lint]\nselect = V002\n")
        assert self._codes(isolated) == ["V002"]

    def test_flag_replaces_config(self, isolated):
        (isolated / "execsql.conf").write_text("[lint]\nignore = V002\n")
        assert self._codes(isolated, "--ignore", "V001") == ["V002"]

    def test_unknown_code_in_config_is_a_usage_error(self, isolated):
        (isolated / "execsql.conf").write_text("[lint]\nselect = Z9\n")
        (isolated / "s.sql").write_text(self.SCRIPT)
        result = runner.invoke(app, ["lint", "s.sql"])
        assert result.exit_code == 2
        assert "[lint] in config" in result.output

    def test_config_lists_the_sections(self, isolated):
        data = json.loads(runner.invoke(app, ["config", "--output-format", "json"]).output)
        keys = {(o["section"], o["key"]): o["default"] for o in data["options"]}
        assert keys[("format", "indent")] == 4
        assert keys[("format", "sql")] is True
        assert keys[("lint", "select")] is None


# ---------------------------------------------------------------------------
# format --diff and lint --strict
# ---------------------------------------------------------------------------


class TestFormatDiff:
    def test_diff_of_a_file_that_would_change(self, isolated):
        (isolated / "a.sql").write_text(UNFORMATTED)
        result = runner.invoke(app, ["format", "--no-sql", "--diff", "a.sql"])
        assert result.exit_code == 1
        assert "--- a.sql\n+++ a.sql\n" in result.output
        assert "-  -- !x! if (true)" not in result.output  # removed lines are the originals
        assert "--- !x! if (true)\n" in result.output
        assert "+-- !x! IF (true)\n" in result.output
        assert (isolated / "a.sql").read_text() == UNFORMATTED  # nothing written

    def test_no_diff_when_already_formatted(self, isolated):
        (isolated / "b.sql").write_text("-- !x! WRITE 'ok'\n")
        result = runner.invoke(app, ["format", "--no-sql", "--diff", "b.sql"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_stdin(self):
        result = runner.invoke(app, ["format", "--no-sql", "--diff", "-"], input=UNFORMATTED)
        assert result.exit_code == 1
        assert "--- <stdin>\n+++ <stdin>\n" in result.output

    def test_cannot_combine_with_in_place(self, isolated):
        (isolated / "a.sql").write_text(UNFORMATTED)
        assert runner.invoke(app, ["format", "--diff", "-i", "a.sql"]).exit_code == 2
        assert (isolated / "a.sql").read_text() == UNFORMATTED


class TestLintStrict:
    WARNING_ONLY = '-- !x! write "!!nope!!"\n'

    def _exit(self, work, *args):
        (work / "w.sql").write_text(self.WARNING_ONLY)
        return runner.invoke(app, ["lint", *args, "w.sql"]).exit_code

    def test_warnings_alone_pass_by_default(self, isolated):
        assert self._exit(isolated) == 0

    def test_strict_fails_on_warnings(self, isolated):
        assert self._exit(isolated, "--strict") == 1

    def test_strict_with_json_and_statistics(self, isolated):
        assert self._exit(isolated, "--strict", "--output-format", "json") == 1
        assert self._exit(isolated, "--strict", "--statistics") == 1

    def test_strict_from_config_and_turned_off_by_flag(self, isolated):
        (isolated / "execsql.conf").write_text("[lint]\nstrict = yes\n")
        assert self._exit(isolated) == 1
        assert self._exit(isolated, "--no-strict") == 0

    def test_a_clean_script_passes_strict(self, isolated):
        (isolated / "ok.sql").write_text("select 1;\n")
        assert runner.invoke(app, ["lint", "--strict", "ok.sql"]).exit_code == 0


# ---------------------------------------------------------------------------
# run --var NAME=VALUE
# ---------------------------------------------------------------------------


class TestRunVar:
    def _run(self, work, script: str, *args: str):
        import os
        import subprocess
        import sys

        (work / "v.sql").write_text(script)
        env = {**os.environ, "HOME": str(work), "USERPROFILE": str(work), "NO_COLOR": "1"}
        cmd = [sys.executable, "-m", "execsql", "run", "v.sql", "-tl", "db.sqlite", "-n", *args]
        return subprocess.run(cmd, cwd=work, capture_output=True, text=True, env=env)

    def test_sets_a_named_variable(self, isolated):
        result = self._run(isolated, '-- !x! write "region=!!region!!"\n', "--var", "region=west")
        assert result.returncode == 0, result.stderr
        assert "region=west" in result.stdout

    def test_wins_over_config_variables(self, isolated):
        (isolated / "execsql.conf").write_text("[variables]\nregion = north\n")
        result = self._run(isolated, '-- !x! write "region=!!region!!"\n', "--var", "region=west")
        assert "region=west" in result.stdout

    def test_a_sub_in_the_script_can_reassign_it(self, isolated):
        script = '-- !x! sub region east\n-- !x! write "region=!!region!!"\n'
        assert "region=east" in self._run(isolated, script, "--var", "region=west").stdout

    def test_works_with_assign_arg(self, isolated):
        script = '-- !x! write "!!region!! !!$ARG_1!!"\n'
        assert "west 2026-09" in self._run(isolated, script, "--var", "region=west", "-a", "2026-09").stdout

    def test_value_may_contain_equals(self, isolated):
        assert "q=a=b" in self._run(isolated, '-- !x! write "q=!!q!!"\n', "--var", "q=a=b").stdout

    def test_value_is_redacted_in_the_log(self, isolated):
        self._run(isolated, "select 1;\n", "--var", "token=s3cret-value")
        log = (isolated / "execsql.log").read_text()
        assert "token set to {***}" in log
        assert "s3cret-value" not in log

    @pytest.mark.parametrize("bad", ["region", "$region=x", "&home=x", "my-var=x", "=x"])
    def test_invalid_is_a_usage_error(self, isolated, bad):
        (isolated / "v.sql").write_text("select 1;\n")
        assert runner.invoke(app, ["run", "v.sql", "-tl", "db.sqlite", "--var", bad]).exit_code == 2
