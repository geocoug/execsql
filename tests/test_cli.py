"""Tests for the CLI interface in execsql.cli (Typer/Rich)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from execsql.cli import app

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
        combined = result.output + (result.stderr or "")
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
