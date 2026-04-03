"""Tests for the CLI interface in execsql.cli (Typer/Rich)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from execsql.cli import app
from execsql.cli import _legacy_main

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def invoke(*args: str):
    """Invoke the CLI with the given argument list."""
    return runner.invoke(app, list(args), catch_exceptions=False)


# ---------------------------------------------------------------------------
# Version and info flags
# ---------------------------------------------------------------------------


class TestInfoFlags:
    def test_version_flag(self):
        result = invoke("--version")
        assert result.exit_code == 0
        assert "execsql" in result.output

    def test_metacommands_flag(self):
        result = invoke("-m", "dummy.sql")
        assert result.exit_code == 0
        # Rich table output should contain some known metacommands
        assert "PAUSE" in result.output
        assert "EXPORT" in result.output

    def test_metacommands_long_flag(self):
        result = invoke("--metacommands", "dummy.sql")
        assert result.exit_code == 0
        assert "PAUSE" in result.output

    def test_encodings_flag(self):
        result = invoke("-y", "dummy.sql")
        assert result.exit_code == 0
        # Should list some encoding names
        assert "utf" in result.output.lower() or "ascii" in result.output.lower()

    def test_encodings_long_flag(self):
        result = invoke("--encodings", "dummy.sql")
        assert result.exit_code == 0

    def test_help_flag(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "SQL_SCRIPT" in result.output or "execsql" in result.output


# ---------------------------------------------------------------------------
# Error handling — missing/invalid args
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_no_script_exits_with_error(self):
        result = runner.invoke(app, [], catch_exceptions=False)
        # --no-args-is-help is set, OR we get error exit
        assert result.exit_code != 0 or "Usage" in result.output

    def test_nonexistent_script_exits_1(self, tmp_path):
        result = invoke("nonexistent_script_xyz.sql")
        assert result.exit_code == 1
        assert "does not exist" in result.output or "does not exist" in (result.stderr or "")

    def test_invalid_db_type_exits_nonzero(self, tmp_path):
        script = tmp_path / "s.sql"
        script.write_text("-- nothing")
        result = invoke("-t", "x", str(script))
        assert result.exit_code != 0

    def test_invalid_gui_level_exits_nonzero(self, tmp_path):
        script = tmp_path / "s.sql"
        script.write_text("-- nothing")
        result = invoke("-v", "9", str(script))
        assert result.exit_code != 0

    def test_invalid_boolean_int_exits_nonzero(self, tmp_path):
        script = tmp_path / "s.sql"
        script.write_text("-- nothing")
        result = invoke("-b", "x", str(script))
        assert result.exit_code != 0

    def test_invalid_gui_framework_exits_nonzero(self, tmp_path):
        script = tmp_path / "s.sql"
        script.write_text("-- nothing")
        result = invoke("--gui-framework", "qt", str(script))
        assert result.exit_code != 0

    def test_online_help_flag(self):
        from unittest.mock import patch

        with patch("webbrowser.open") as mock_open:
            result = invoke("-o", "dummy.sql")
        assert result.exit_code == 0
        mock_open.assert_called_once()


# ---------------------------------------------------------------------------
# Named option parsing (verify Typer parses them correctly)
# ---------------------------------------------------------------------------


class TestOptionParsing:
    """Test that named options are accepted without error at the parse stage.

    We use a tmp script file that exists so the 'script does not exist' check
    passes. The test ends at the 'script exists' check since no DB is configured.
    These tests only verify that the option is *accepted*, not that it drives
    the full execution pipeline.
    """

    def _script(self, tmp_path):
        p = tmp_path / "test.sql"
        p.write_text("-- empty")
        return str(p)

    def _parse_exits_cleanly(self, *args):
        """Verify that the given flags are accepted without an argument-parse error.

        Mocks ``_run`` so the test only exercises Typer argument parsing and
        the CLI's own validation, not the full execution pipeline.
        """
        with patch("execsql.cli._run", return_value=None):
            result = runner.invoke(app, list(args), catch_exceptions=False)
        # Exit 0 = clean; exit 1 = CLI validation error (e.g. bad db-type)
        # Exit 2 = Typer arg-parse error — that's the failure we guard against
        return result.exit_code != 2

    def test_type_flag_postgres(self, tmp_path):
        assert self._parse_exits_cleanly("-t", "p", self._script(tmp_path))

    def test_type_flag_sqlite(self, tmp_path):
        assert self._parse_exits_cleanly("-t", "l", self._script(tmp_path))

    def test_type_flag_duckdb(self, tmp_path):
        assert self._parse_exits_cleanly("-t", "k", self._script(tmp_path))

    def test_type_flag_all_valid_choices(self, tmp_path):
        script = self._script(tmp_path)
        for choice in ("a", "d", "p", "s", "l", "m", "k", "o", "f"):
            assert self._parse_exits_cleanly("-t", choice, script), f"Choice {choice!r} was rejected"

    def test_user_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-u", "alice", self._script(tmp_path))

    def test_port_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-p", "5432", self._script(tmp_path))

    def test_scan_lines_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-s", "200", self._script(tmp_path))

    def test_no_passwd_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-w", self._script(tmp_path))

    def test_new_db_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-n", self._script(tmp_path))

    def test_user_logfile_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-l", self._script(tmp_path))

    def test_assign_arg_single(self, tmp_path):
        assert self._parse_exits_cleanly("-a", "foo", self._script(tmp_path))

    def test_assign_arg_multiple(self, tmp_path):
        assert self._parse_exits_cleanly("-a", "foo", "-a", "bar", self._script(tmp_path))

    def test_boolean_int_flag(self, tmp_path):
        for v in ("0", "1", "t", "f", "y", "n"):
            assert self._parse_exits_cleanly("-b", v, self._script(tmp_path))

    def test_gui_level_valid_choices(self, tmp_path):
        script = self._script(tmp_path)
        for v in ("0", "1", "2", "3"):
            assert self._parse_exits_cleanly("-v", v, script)

    def test_import_buffer_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-z", "64", self._script(tmp_path))

    def test_import_encoding_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-i", "utf8", self._script(tmp_path))

    def test_output_encoding_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-g", "utf8", self._script(tmp_path))

    def test_script_encoding_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-f", "utf8", self._script(tmp_path))

    def test_database_encoding_flag(self, tmp_path):
        assert self._parse_exits_cleanly("-e", "utf8", self._script(tmp_path))

    def test_output_dir_flag(self, tmp_path):
        assert self._parse_exits_cleanly("--output-dir", str(tmp_path), self._script(tmp_path))

    def test_dsn_flag(self, tmp_path):
        assert self._parse_exits_cleanly("--dsn", "postgresql://user@host/db", self._script(tmp_path))


# ---------------------------------------------------------------------------
# Positional argument handling
# ---------------------------------------------------------------------------


class TestPositionalArgs:
    def test_script_only_accepted(self, tmp_path):
        script = tmp_path / "s.sql"
        script.write_text("-- empty")
        with patch("execsql.cli._run", return_value=None):
            result = runner.invoke(app, [str(script)], catch_exceptions=False)
        assert result.exit_code != 2

    def test_script_server_db_accepted(self, tmp_path):
        script = tmp_path / "s.sql"
        script.write_text("-- empty")
        with patch("execsql.cli._run", return_value=None):
            result = runner.invoke(app, [str(script), "myserver", "mydb"], catch_exceptions=False)
        assert result.exit_code != 2

    def test_script_dbfile_accepted(self, tmp_path):
        script = tmp_path / "s.sql"
        script.write_text("-- empty")
        with patch("execsql.cli._run", return_value=None):
            result = runner.invoke(app, ["-t", "l", str(script), str(tmp_path / "db.sqlite")], catch_exceptions=False)
        assert result.exit_code != 2


# ---------------------------------------------------------------------------
# Rich output quality
# ---------------------------------------------------------------------------


class TestRichOutput:
    def test_metacommands_output_contains_table_content(self):
        result = invoke("-m", "dummy.sql")
        assert result.exit_code == 0
        # Rich table should render headers and rows
        assert "PAUSE" in result.output
        assert "WRITE" in result.output
        assert "IF" in result.output

    def test_metacommands_output_contains_syntax(self):
        result = invoke("-m", "dummy.sql")
        assert result.exit_code == 0
        # Syntax column content
        assert "ON|OFF" in result.output

    def test_encodings_output_is_multi_column(self):
        result = invoke("-y", "dummy.sql")
        assert result.exit_code == 0
        output_lines = result.output.strip().splitlines()
        assert len(output_lines) > 5, "Expected multiple lines of encodings"

    def test_version_shows_version_number(self):
        from execsql import __version__

        result = invoke("--version")
        assert __version__ in result.output

    def test_nonexistent_file_error_message_is_clear(self):
        result = runner.invoke(app, ["not_a_real_file.sql"], catch_exceptions=False)
        assert result.exit_code == 1
        # CliRunner mixes stderr into stdout by default; .stderr raises ValueError
        try:
            stderr = result.stderr or ""
        except ValueError:
            stderr = ""
        combined = result.output + stderr
        assert "not_a_real_file.sql" in combined or "does not exist" in combined


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


class TestDryRun:
    """Tests for the --dry-run flag.

    --dry-run parses the script and prints the command list without
    connecting to a database or executing anything.
    """

    def test_dry_run_sql_script_exits_zero(self, tmp_path):
        script = tmp_path / "test.sql"
        script.write_text("SELECT 1;\n")
        result = runner.invoke(app, ["--dry-run", str(script)], catch_exceptions=False)
        assert result.exit_code == 0

    def test_dry_run_shows_sql_commands(self, tmp_path):
        script = tmp_path / "test.sql"
        script.write_text("SELECT 1;\nSELECT 2;\n")
        result = runner.invoke(app, ["--dry-run", str(script)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "SQL" in result.output

    def test_dry_run_shows_metacommands(self, tmp_path):
        script = tmp_path / "test.sql"
        script.write_text('-- !x! WRITE "hello"\n')
        result = runner.invoke(app, ["--dry-run", str(script)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "METACMD" in result.output

    def test_dry_run_does_not_require_db_credentials(self, tmp_path):
        """--dry-run must work without specifying any database connection info."""
        script = tmp_path / "test.sql"
        script.write_text("SELECT 1;\n")
        # No -t, no server, no db_file — would normally fail at the connection step
        result = runner.invoke(app, ["--dry-run", str(script)], catch_exceptions=False)
        assert result.exit_code == 0

    def test_dry_run_with_inline_command(self):
        result = runner.invoke(
            app,
            ["--dry-run", "-c", "SELECT 1;"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "SQL" in result.output

    def test_dry_run_shows_header(self, tmp_path):
        script = tmp_path / "test.sql"
        script.write_text("SELECT 1;\n")
        result = runner.invoke(app, ["--dry-run", str(script)], catch_exceptions=False)
        assert "Dry Run" in result.output
        assert "command" in result.output.lower()

    def test_dry_run_empty_script_shows_message(self, tmp_path):
        """A script with only comments produces no commands — print the 'no commands' message."""
        script = tmp_path / "empty.sql"
        script.write_text("-- just a comment\n")
        result = runner.invoke(app, ["--dry-run", str(script)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No commands found" in result.output

    def test_dry_run_with_dsn_populates_db_type(self, tmp_path):
        """--dsn with --dry-run processes the DSN block without connecting to the DB."""
        script = tmp_path / "test.sql"
        script.write_text("SELECT 1;\n")
        result = runner.invoke(
            app,
            ["--dry-run", "--dsn", "postgresql://user@localhost/mydb", str(script)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_dry_run_with_dsn_sqlite(self, tmp_path):
        """--dsn with sqlite:/// and --dry-run sets file-based db_type."""
        script = tmp_path / "test.sql"
        script.write_text("SELECT 1;\n")
        result = runner.invoke(
            app,
            ["--dry-run", "--dsn", "sqlite:///myfile.db", str(script)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_dry_run_dsn_invalid_scheme_exits_one(self, tmp_path):
        """An unrecognised --dsn scheme exits with code 1."""
        script = tmp_path / "test.sql"
        script.write_text("SELECT 1;\n")
        result = runner.invoke(
            app,
            ["--dry-run", "--dsn", "mongodb://host/db", str(script)],
            catch_exceptions=False,
        )
        assert result.exit_code == 1

    def test_dry_run_expands_assign_arg_variables(self, tmp_path):
        """--assign-arg values ($ARG_1, $ARG_2, …) must appear expanded in dry-run output."""
        script = tmp_path / "test.sql"
        # Use !! delimiters — the canonical execsql substitution syntax.
        script.write_text("SELECT * FROM !!$ARG_1!!;\n")
        result = runner.invoke(
            app,
            ["--dry-run", "-a", "my_table", str(script)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "my_table" in result.output
        # Raw token must NOT appear — expansion happened.
        assert "!!$ARG_1!!" not in result.output

    def test_dry_run_expands_multiple_assign_args(self, tmp_path):
        """Multiple --assign-arg values are all expanded in dry-run output."""
        script = tmp_path / "test.sql"
        script.write_text("SELECT !!$ARG_1!!, !!$ARG_2!! FROM dual;\n")
        result = runner.invoke(
            app,
            ["--dry-run", "-a", "col_a", "-a", "col_b", str(script)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "col_a" in result.output
        assert "col_b" in result.output

    def test_dry_run_expands_env_vars(self, tmp_path, monkeypatch):
        """Environment variables exposed as &VAR are expanded in dry-run output."""
        monkeypatch.setenv("DRY_RUN_TEST_VAR", "sentinel_value")
        script = tmp_path / "test.sql"
        script.write_text("SELECT '!!&DRY_RUN_TEST_VAR!!';\n")
        result = runner.invoke(
            app,
            ["--dry-run", str(script)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "sentinel_value" in result.output

    def test_dry_run_unexpanded_token_survives_gracefully(self, tmp_path):
        """An unrecognised substitution token is left as-is (not an error)."""
        script = tmp_path / "test.sql"
        # $UNKNOWN_VAR is not defined — substitute_vars leaves it verbatim.
        script.write_text("SELECT !!$UNKNOWN_XYZ_VAR!!;\n")
        result = runner.invoke(
            app,
            ["--dry-run", str(script)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # The command is still displayed (token is left verbatim, not an error).
        assert "SQL" in result.output


# ---------------------------------------------------------------------------
# _parse_connection_string
# ---------------------------------------------------------------------------


class TestParseConnectionString:
    """Unit tests for _parse_connection_string() helper."""

    @property
    def _fn(self):
        from execsql.cli import _parse_connection_string

        return _parse_connection_string

    def test_postgresql_full_url(self):
        r = self._fn("postgresql://alice:s3cr3t@db.example.com:5432/mydb")
        assert r["db_type"] == "p"
        assert r["server"] == "db.example.com"
        assert r["db"] == "mydb"
        assert r["user"] == "alice"
        assert r["password"] == "s3cr3t"
        assert r["port"] == 5432

    def test_postgres_scheme_alias(self):
        r = self._fn("postgres://host/db")
        assert r["db_type"] == "p"

    def test_mysql_scheme(self):
        r = self._fn("mysql://host/mydb")
        assert r["db_type"] == "m"

    def test_mssql_scheme(self):
        r = self._fn("mssql://host/mydb")
        assert r["db_type"] == "s"

    def test_oracle_scheme(self):
        r = self._fn("oracle://host/mydb")
        assert r["db_type"] == "o"

    def test_firebird_scheme(self):
        r = self._fn("firebird://host/mydb")
        assert r["db_type"] == "f"

    def test_sqlite_file_path(self):
        r = self._fn("sqlite:///path/to/file.db")
        assert r["db_type"] == "l"
        assert r["db_file"] == "path/to/file.db"
        assert r["server"] is None
        assert r["db"] is None

    def test_duckdb_file_path(self):
        r = self._fn("duckdb:///myfile.duckdb")
        assert r["db_type"] == "k"
        assert r["db_file"] == "myfile.duckdb"

    def test_no_password_returns_none(self):
        r = self._fn("postgresql://user@host/db")
        assert r["password"] is None

    def test_no_user_returns_none(self):
        r = self._fn("postgresql://host/db")
        assert r["user"] is None

    def test_no_port_returns_none(self):
        r = self._fn("postgresql://host/db")
        assert r["port"] is None

    def test_unknown_scheme_raises_config_error(self):
        from execsql.exceptions import ConfigError

        with pytest.raises(ConfigError, match="Unrecognised"):
            self._fn("mongodb://host/db")

    def test_no_scheme_raises_config_error(self):
        from execsql.exceptions import ConfigError

        with pytest.raises(ConfigError, match="no scheme"):
            self._fn("notaurl")

    def test_dsn_flag_accepted_by_cli(self, tmp_path):
        """--dsn flag is accepted at parse time without error."""
        script = tmp_path / "s.sql"
        script.write_text("-- empty")
        with patch("execsql.cli._run", return_value=None):
            result = runner.invoke(
                app,
                ["--dsn", "postgresql://user@host/db", str(script)],
                catch_exceptions=False,
            )
        assert result.exit_code != 2, result.output

    def test_connection_string_alias_accepted(self, tmp_path):
        """--connection-string is an alias for --dsn."""
        script = tmp_path / "s.sql"
        script.write_text("-- empty")
        with patch("execsql.cli._run", return_value=None):
            result = runner.invoke(
                app,
                ["--connection-string", "postgresql://user@host/db", str(script)],
                catch_exceptions=False,
            )
        assert result.exit_code != 2, result.output


# ---------------------------------------------------------------------------
# End-to-end CLI tests — real execution, no mocking
# ---------------------------------------------------------------------------


def _write_conf(tmp_path, db_filename="test.db"):
    """Write a minimal execsql.conf for SQLite."""
    conf = tmp_path / "execsql.conf"
    conf.write_text(
        textwrap.dedent(f"""\
        [connect]
        db_type = l
        db_file = {db_filename}
        new_db = yes
        password_prompt = no

        [encoding]
        script = utf-8
        output = utf-8
        import = utf-8
    """),
    )
    return conf


def _run_cli(tmp_path, args, timeout=30):
    """Run execsql CLI via subprocess and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "execsql"] + args,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestEndToEndExecution:
    """Tests that run actual SQL through the CLI — no mocking."""

    def test_inline_command_creates_table(self, tmp_path):
        """The -c flag runs inline SQL that creates a table and inserts data."""
        _write_conf(tmp_path)
        result = _run_cli(
            tmp_path,
            [
                "-c",
                "CREATE TABLE e2e (val TEXT);\\nINSERT INTO e2e VALUES ('works');",
            ],
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT val FROM e2e").fetchall()
        conn.close()
        assert rows == [("works",)]

    def test_dsn_flag_with_sqlite(self, tmp_path):
        """The --dsn flag with a sqlite:// URL connects and executes."""
        db_path = tmp_path / "dsn_test.db"
        script = tmp_path / "test.sql"
        script.write_text(
            "CREATE TABLE dsn_tbl (id INTEGER);\nINSERT INTO dsn_tbl VALUES (42);\n",
        )

        result = _run_cli(
            tmp_path,
            [
                "--dsn",
                f"sqlite:///{db_path}",
                "-n",
                str(script),
            ],
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id FROM dsn_tbl").fetchall()
        conn.close()
        assert rows == [(42,)]

    def test_assign_arg_substitution(self, tmp_path):
        """The -a flag sets $ARG_1 for use in script substitution."""
        _write_conf(tmp_path)
        script = tmp_path / "test.sql"
        script.write_text(
            "CREATE TABLE args (val TEXT);\nINSERT INTO args VALUES ('!!$ARG_1!!');\n",
        )

        result = _run_cli(tmp_path, ["-a", "hello_arg", str(script)])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT val FROM args").fetchall()
        conn.close()
        assert rows == [("hello_arg",)]

    def test_dry_run_does_not_create_db(self, tmp_path):
        """--dry-run parses but does not create the database file."""
        _write_conf(tmp_path, db_filename="should_not_exist.db")
        script = tmp_path / "test.sql"
        script.write_text("CREATE TABLE t (id INTEGER);\n")

        result = _run_cli(tmp_path, ["--dry-run", str(script)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (tmp_path / "should_not_exist.db").exists()

    def test_dump_keywords_json_valid(self, tmp_path):
        """--dump-keywords produces valid JSON with expected top-level keys."""
        import json

        result = _run_cli(tmp_path, ["--dump-keywords"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = json.loads(result.stdout)
        assert "metacommands" in data
        assert "conditions" in data
        assert "database_types" in data

    def test_version_output(self, tmp_path):
        """--version prints the version string."""
        result = _run_cli(tmp_path, ["--version"])
        assert result.returncode == 0
        assert "execsql" in result.stdout.lower() or "." in result.stdout

    def test_nonexistent_script_fails(self, tmp_path):
        """Passing a script that doesn't exist returns non-zero."""
        _write_conf(tmp_path)
        result = _run_cli(tmp_path, ["no_such_file.sql"])
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# --dump-keywords (lines 272-323)
# ---------------------------------------------------------------------------


class TestDumpKeywords:
    """In-process tests for the --dump-keywords early-exit branch.

    These use CliRunner so that every line inside the branch is counted
    for coverage (the subprocess-based test in TestEndToEndExecution does not
    contribute to in-process line coverage).
    """

    def _data(self):
        """Invoke --dump-keywords and return the parsed JSON dict."""
        result = runner.invoke(app, ["--dump-keywords"], catch_exceptions=False)
        assert result.exit_code == 0, f"Non-zero exit: {result.output}"
        return json.loads(result.output)

    def test_exits_zero(self):
        result = runner.invoke(app, ["--dump-keywords"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_output_is_valid_json(self):
        result = runner.invoke(app, ["--dump-keywords"], catch_exceptions=False)
        # Must not raise
        json.loads(result.output)

    def test_top_level_keys_present(self):
        data = self._data()
        expected = {
            "metacommands",
            "conditions",
            "config_options",
            "export_formats",
            "database_types",
            "variable_patterns",
        }
        assert expected == set(data.keys())

    def test_metacommands_has_five_categories(self):
        data = self._data()
        mc = data["metacommands"]
        assert set(mc.keys()) == {"control", "block", "action", "config", "prompt"}

    def test_metacommands_block_contains_begin_end_script(self):
        """BEGIN SCRIPT and END SCRIPT are injected into the block category."""
        data = self._data()
        block = data["metacommands"]["block"]
        assert "BEGIN SCRIPT" in block
        assert "END SCRIPT" in block
        assert "BEGIN SQL" in block
        assert "END SQL" in block

    def test_metacommands_categories_are_sorted_lists(self):
        data = self._data()
        for category, items in data["metacommands"].items():
            assert isinstance(items, list), f"Category {category!r} is not a list"
            assert items == sorted(items), f"Category {category!r} is not sorted"

    def test_conditions_is_sorted_list(self):
        data = self._data()
        conds = data["conditions"]
        assert isinstance(conds, list)
        assert len(conds) > 0
        assert conds == sorted(conds)

    def test_conditions_contains_injected_keywords(self):
        """IS_FALSE, NOT, and OR are injected into the conditions list."""
        data = self._data()
        for kw in ("IS_FALSE", "NOT", "OR"):
            assert kw in data["conditions"], f"{kw!r} missing from conditions"

    def test_config_options_is_sorted_list(self):
        data = self._data()
        opts = data["config_options"]
        assert isinstance(opts, list)
        assert opts == sorted(opts)

    def test_export_formats_has_expected_keys(self):
        data = self._data()
        ef = data["export_formats"]
        assert set(ef.keys()) == {"query", "table", "serve", "metadata", "json_variants", "all"}

    def test_export_formats_all_is_sorted(self):
        data = self._data()
        all_fmts = data["export_formats"]["all"]
        assert isinstance(all_fmts, list)
        assert len(all_fmts) > 0
        assert all_fmts == sorted(all_fmts)

    def test_export_formats_query_is_subset_of_all(self):
        data = self._data()
        ef = data["export_formats"]
        assert set(ef["query"]).issubset(set(ef["all"]))

    def test_export_formats_table_is_subset_of_all(self):
        data = self._data()
        ef = data["export_formats"]
        assert set(ef["table"]).issubset(set(ef["all"]))

    def test_database_types_is_sorted_list(self):
        data = self._data()
        dbtypes = data["database_types"]
        assert isinstance(dbtypes, list)
        assert len(dbtypes) > 0
        assert dbtypes == sorted(dbtypes)

    def test_variable_patterns_has_all_pattern_keys(self):
        data = self._data()
        vp = data["variable_patterns"]
        expected_keys = {
            "system",
            "environment",
            "parameter",
            "column",
            "local",
            "local_alt",
            "regular",
            "deferred",
        }
        assert expected_keys == set(vp.keys())

    def test_variable_patterns_values_are_strings(self):
        data = self._data()
        for key, val in data["variable_patterns"].items():
            assert isinstance(val, str), f"variable_patterns[{key!r}] is not a string"

    def test_variable_patterns_system_uses_bang_syntax(self):
        data = self._data()
        assert data["variable_patterns"]["system"] == "!!$name!!"

    def test_variable_patterns_deferred_uses_brace_syntax(self):
        data = self._data()
        assert data["variable_patterns"]["deferred"] == "!{name}!"

    def test_metacommands_action_is_nonempty(self):
        data = self._data()
        assert len(data["metacommands"]["action"]) > 0

    def test_metacommands_control_is_nonempty(self):
        data = self._data()
        assert len(data["metacommands"]["control"]) > 0


# ---------------------------------------------------------------------------
# _legacy_main() exception handling (lines 414-432)
# ---------------------------------------------------------------------------


class TestLegacyMain:
    """Unit tests for the three exception branches in _legacy_main().

    We mock ``execsql.cli.app`` so that calling _legacy_main() triggers each
    handler without needing a real Typer invocation.
    """

    def test_system_exit_propagates(self):
        """A SystemExit raised inside app() is re-raised unchanged."""
        with patch("execsql.cli.app", side_effect=SystemExit(0)), pytest.raises(SystemExit) as exc_info:
            _legacy_main()
        assert exc_info.value.code == 0

    def test_system_exit_nonzero_propagates(self):
        """A non-zero SystemExit propagates without being caught."""
        with patch("execsql.cli.app", side_effect=SystemExit(3)), pytest.raises(SystemExit) as exc_info:
            _legacy_main()
        assert exc_info.value.code == 3

    def test_errinfo_calls_exit_now(self):
        """An ErrInfo exception is handled by calling exit_now(1, exc)."""
        from execsql.exceptions import ErrInfo

        exc = ErrInfo("error", exception_msg="something went wrong")

        with patch("execsql.cli.app", side_effect=exc), patch("execsql.utils.errors.exit_now") as mock_exit_now:
            # exit_now calls sys.exit internally; stop propagation here
            mock_exit_now.side_effect = SystemExit(1)
            with pytest.raises(SystemExit) as exc_info:
                _legacy_main()
        assert exc_info.value.code == 1
        mock_exit_now.assert_called_once()
        call_args = mock_exit_now.call_args
        assert call_args[0][0] == 1  # exit_status=1
        assert isinstance(call_args[0][1], ErrInfo)

    def test_config_error_calls_sys_exit_with_message(self):
        """A ConfigError exits via sys.exit with a human-readable message."""
        from execsql.exceptions import ConfigError

        exc = ConfigError("bad config value")

        with patch("execsql.cli.app", side_effect=exc), pytest.raises(SystemExit) as exc_info:
            _legacy_main()

        # sys.exit was called with a string message, not just a code
        msg = exc_info.value.code
        assert isinstance(msg, str)
        assert "Configuration error" in msg
        assert "execsql" in msg

    def test_config_error_message_contains_line_number(self):
        """ConfigError exit message includes a line number from the traceback."""
        from execsql.exceptions import ConfigError

        with patch("execsql.cli.app", side_effect=ConfigError("oops")), pytest.raises(SystemExit) as exc_info:
            _legacy_main()

        msg = exc_info.value.code
        # The message format is "Configuration error on line <N> of execsql: <msg>"
        assert "line" in msg
        assert "oops" in msg

    def test_generic_exception_wraps_in_errinfo(self):
        """An unexpected Exception is wrapped in ErrInfo and passed to exit_now."""
        from execsql.exceptions import ErrInfo

        with (
            patch("execsql.cli.app", side_effect=RuntimeError("unexpected failure")),
            patch("execsql.utils.errors.exit_now") as mock_exit_now,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_exit_now.side_effect = SystemExit(1)
            _legacy_main()

        assert exc_info.value.code == 1
        mock_exit_now.assert_called_once()
        call_args = mock_exit_now.call_args
        assert call_args[0][0] == 1
        wrapped = call_args[0][1]
        assert isinstance(wrapped, ErrInfo)

    def test_generic_exception_message_contains_exception_type(self):
        """The ErrInfo wrapping a generic exception includes the exception class name."""
        from execsql.exceptions import ErrInfo as _ErrInfo

        captured = {}

        def capture_exit_now(status, errinfo, *a, **kw):
            captured["errinfo"] = errinfo
            raise SystemExit(status)

        with (
            patch("execsql.cli.app", side_effect=ValueError("bad value")),
            patch("execsql.utils.errors.exit_now", side_effect=capture_exit_now),
            pytest.raises(SystemExit),
        ):
            _legacy_main()

        errinfo = captured["errinfo"]
        assert isinstance(errinfo, _ErrInfo)
        # The exception message includes the exception class name
        assert "ValueError" in (errinfo.exception or "")

    def test_generic_exception_message_contains_argv0(self):
        """The ErrInfo message includes sys.argv[0]'s basename."""
        captured = {}

        def capture_exit_now(status, errinfo, *a, **kw):
            captured["errinfo"] = errinfo
            raise SystemExit(status)

        with (
            patch("execsql.cli.app", side_effect=OSError("disk error")),
            patch("execsql.utils.errors.exit_now", side_effect=capture_exit_now),
            pytest.raises(SystemExit),
        ):
            _legacy_main()

        from pathlib import Path

        expected_name = Path(sys.argv[0]).name
        errinfo = captured["errinfo"]
        assert expected_name in (errinfo.exception or "")
