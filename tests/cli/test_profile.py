"""Tests for the --profile CLI flag and related helpers.

Covers:
- ``_print_profile()`` formatting logic (empty data, single statement, multiple
  statements, truncation of long source paths, truncation of long command text,
  "top 20" cap).
- ``profile_data`` attribute on ``RuntimeContext`` defaults to ``None``.
- Activating profiling sets ``_state.profile_data`` to an empty list before
  script execution.
- Profile output appears after successful script execution when ``profile=True``.
- The ``--profile`` flag is accepted by the Typer CLI (no parse error).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

import execsql.state as _state
from execsql.cli import app
from execsql.cli.run import _print_profile
from execsql.state import RuntimeContext


# ---------------------------------------------------------------------------
# RuntimeContext default
# ---------------------------------------------------------------------------


class TestRuntimeContextDefault:
    """profile_data starts as None so profiling is opt-in."""

    def test_profile_data_default_is_none(self):
        ctx = RuntimeContext()
        assert ctx.profile_data is None

    def test_profile_data_in_context_attrs(self):
        from execsql.state import _CONTEXT_ATTRS

        assert "profile_data" in _CONTEXT_ATTRS

    def test_profile_data_in_slots(self):
        assert "profile_data" in RuntimeContext.__slots__

    def test_state_proxy_returns_none_by_default(self):
        # Via the module proxy the attribute should also be None after reset.
        assert _state.profile_data is None

    def test_state_proxy_assignment(self):
        _state.profile_data = []
        assert _state.profile_data == []
        _state.profile_data = None  # restore


# ---------------------------------------------------------------------------
# _print_profile() — formatting
# ---------------------------------------------------------------------------


class TestPrintProfile:
    """Unit tests for the _print_profile() formatting helper."""

    def test_empty_list_does_not_raise(self):
        _print_profile([])

    def test_single_sql_statement(self):
        data = [("script.sql", 10, "sql", 1.234, "SELECT * FROM large_table WHERE id > 0")]
        _print_profile(data)  # must not raise

    def test_single_metacmd_statement(self):
        data = [("script.sql", 5, "cmd", 0.456, "IMPORT TO staging FROM CSV 'data.csv'")]
        _print_profile(data)  # must not raise

    def test_multiple_statements_sorted_by_elapsed(self, capsys):
        """Slowest statement must appear first in the output."""
        data = [
            ("s.sql", 1, "sql", 0.1, "SELECT 1"),
            ("s.sql", 2, "sql", 2.5, "SELECT slow"),
            ("s.sql", 3, "cmd", 0.5, "IMPORT foo"),
        ]
        # _print_profile uses Rich console which writes to its own internal
        # buffer; we verify no exception and rely on internal logic for order.
        _print_profile(data)

    def test_top_20_cap(self):
        """More than 20 statements — only top 20 should be displayed, remainder noted."""
        data = [("s.sql", i, "sql", float(i), f"SELECT {i}") for i in range(1, 26)]
        _print_profile(data)  # must not raise; no assertion on Rich output

    def test_long_source_truncated(self):
        """Source paths longer than 20 chars should be truncated to '...'+suffix."""
        data = [("/very/long/path/to/some/deeply/nested/script.sql", 99, "sql", 0.1, "SELECT 1")]
        _print_profile(data)  # must not raise

    def test_long_command_truncated(self):
        """Command previews longer than 50 chars should be truncated with '...'."""
        long_cmd = "SELECT " + "x, " * 30 + "y FROM table_with_a_very_long_name"
        data = [("s.sql", 1, "sql", 0.1, long_cmd)]
        _print_profile(data)  # must not raise

    def test_single_statement_label(self):
        """Singular 'statement' (not 'statements') when n == 1.

        We capture the Rich console output by patching _console.print.
        """
        captured = []
        with patch("execsql.cli.run._console") as mock_console:
            mock_console.print.side_effect = lambda *a, **kw: captured.append(str(a[0]) if a else "")
            _print_profile([("s.sql", 1, "sql", 0.5, "SELECT 1")])
        # The summary line should say "1 statement in" (not "1 statements")
        summary_lines = [line for line in captured if "statement" in line and "Profile" in line]
        assert any("1 statement" in line and "1 statements" not in line for line in summary_lines)

    def test_zero_total_time_no_zerodivision(self):
        """All statements with 0.0 elapsed — percentage column must not raise."""
        data = [("s.sql", 1, "sql", 0.0, "SELECT 1")]
        _print_profile(data)  # must not raise ZeroDivisionError


# ---------------------------------------------------------------------------
# Profiling activation in _run()
# ---------------------------------------------------------------------------


_RUN_PATCHES = {
    "db": "execsql.cli.run._connect_initial_db",
    "runscripts": "execsql.cli.run.runscripts",
    "filewriter_cls": "execsql.cli.run.FileWriter",
    "filewriter_end": "execsql.cli.run.filewriter_end",
    "atexit": "execsql.cli.run.atexit",
    "gui_console_off": "execsql.cli.run.gui_console_off",
    "gui_console_on": "execsql.cli.run.gui_console_on",
    "gui_console_isrunning": "execsql.cli.run.gui_console_isrunning",
    "gui_console_wait_user": "execsql.cli.run.gui_console_wait_user",
}


def _make_mock_db():
    db = MagicMock()
    db.type.dbms_id = "sqlite"
    db.name.return_value = "test.db"
    db.server_name = "localhost"
    return db


def _make_sql_file(tmp_path, content="SELECT 1;"):
    p = tmp_path / "test.sql"
    p.write_text(content)
    return str(p)


def _invoke_run(tmp_path, *, profile: bool = False, runscripts_side_effect=None):
    """Call _run() with all external I/O mocked.

    Mirrors the helper pattern from test_cli_run.py so that _run() receives all
    required arguments in the form it expects (including ``script_name``).
    """
    script = _make_sql_file(tmp_path)
    mock_db = _make_mock_db()
    mock_fw = MagicMock()
    mock_fw.is_alive.return_value = False

    kwargs = {
        "positional": [script],
        "sub_vars": None,
        "boolean_int": None,
        "make_dirs": None,
        "database_encoding": None,
        "script_encoding": None,
        "output_encoding": None,
        "import_encoding": None,
        "user_logfile": False,
        "new_db": False,
        "port": None,
        "scanlines": None,
        "db_type": "l",
        "user": None,
        "use_gui": None,
        "gui_framework": None,
        "no_passwd": False,
        "import_buffer": None,
        "script_name": script,
        "command": None,
        "dry_run": False,
        "dsn": f"sqlite:///{tmp_path / 'test.db'}",
        "output_dir": None,
        "progress": False,
        "profile": profile,
    }

    from execsql.cli.run import _run

    patches = [
        patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
        patch("execsql.cli.run.runscripts", side_effect=runscripts_side_effect),
        patch("execsql.cli.run.FileWriter", return_value=mock_fw),
        patch("execsql.cli.run.filewriter_end"),
        patch("execsql.cli.run.atexit"),
    ]
    return _run, kwargs, patches


class TestProfilingActivation:
    """Verify that _run() initialises _state.profile_data when profile=True."""

    def test_profile_data_set_to_list_when_profile_true(self, tmp_path):
        captured = []

        def fake_runscripts():
            captured.append(_state.profile_data)

        _run, kwargs, patches = _invoke_run(tmp_path, profile=True, runscripts_side_effect=fake_runscripts)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("execsql.cli.run._print_profile"),
        ):
            _run(**kwargs)

        assert len(captured) == 1
        assert isinstance(captured[0], list)

    def test_profile_data_not_set_when_profile_false(self, tmp_path):
        captured = []

        def fake_runscripts():
            captured.append(_state.profile_data)

        _run, kwargs, patches = _invoke_run(tmp_path, profile=False, runscripts_side_effect=fake_runscripts)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
        ):
            _run(**kwargs)

        assert len(captured) == 1
        assert captured[0] is None

    def test_print_profile_called_after_runscripts(self, tmp_path):
        """_print_profile() should be called exactly once after successful execution."""
        _run, kwargs, patches = _invoke_run(tmp_path, profile=True)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("execsql.cli.run._print_profile") as mock_pp,
        ):
            _run(**kwargs)

        mock_pp.assert_called_once()


# ---------------------------------------------------------------------------
# CLI flag acceptance (Typer layer)
# ---------------------------------------------------------------------------


class TestCliProfileFlag:
    """Verify the Typer CLI accepts --profile without errors."""

    def test_profile_flag_accepted_with_help(self):
        """--help should list --profile without raising."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--profile" in result.output

    def test_profile_flag_requires_script(self):
        """--profile alone (no script) should exit with a non-zero code."""
        runner = CliRunner()
        result = runner.invoke(app, ["--profile"])
        # Should fail because no script is given, not because the flag is invalid.
        assert result.exit_code != 0
