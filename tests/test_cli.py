"""Tests for the CLI interface in execsql.cli (Typer/Rich)."""

from __future__ import annotations
from unittest.mock import patch

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
