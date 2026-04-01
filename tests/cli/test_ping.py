"""Tests for the --ping CLI flag.

Strategy
--------
- Tests that verify the full `_run()` path use SQLite (no server required).
- Tests that verify CLI-layer behaviour (early exit, option parsing) use the
  Typer CliRunner against the real ``app`` object.
- The ``autouse`` ``minimal_conf`` fixture from conftest.py handles state reset.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from execsql.cli import app
from execsql.cli.run import _ping_db, _run

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

_RUN_PATCHES = {
    "filewriter_cls": "execsql.cli.run.FileWriter",
    "filewriter_end": "execsql.cli.run.filewriter_end",
    "gui_console_off": "execsql.cli.run.gui_console_off",
    "gui_console_on": "execsql.cli.run.gui_console_on",
    "gui_console_isrunning": "execsql.cli.run.gui_console_isrunning",
    "gui_console_wait_user": "execsql.cli.run.gui_console_wait_user",
}


def _apply_patches(extra: dict | None = None):
    """Return a context-manager stack that applies the common _run patches."""
    import contextlib

    targets = {**_RUN_PATCHES, **(extra or {})}
    stack = contextlib.ExitStack()
    mocks: dict[str, MagicMock] = {}
    for key, target in targets.items():
        mocks[key] = stack.enter_context(patch(target, MagicMock()))
    # filewriter mock: make is_alive() return True so a new one is never started
    mocks["filewriter_cls"].return_value.is_alive.return_value = True
    return stack, mocks


def _run_ping(dsn: str, db_type: str = "l") -> None:
    """Helper: call _run() in --ping mode."""
    _run(
        positional=[],
        sub_vars=None,
        boolean_int=None,
        make_dirs=None,
        database_encoding=None,
        script_encoding=None,
        output_encoding=None,
        import_encoding=None,
        user_logfile=False,
        new_db=False,
        port=None,
        scanlines=None,
        db_type=db_type,
        user=None,
        use_gui=None,
        script_name=None,
        command=None,
        dry_run=False,
        dsn=dsn,
        output_dir=None,
        progress=False,
        profile=False,
        ping=True,
    )


# ---------------------------------------------------------------------------
# Unit tests for _ping_db()
# ---------------------------------------------------------------------------


class TestPingDbHelper:
    """Unit-test _ping_db() in isolation using a mock database object."""

    def _make_db(self, dbms_id="SQLite", db_name="/tmp/test.db", server_name=None, port=None):
        db = MagicMock()
        db.type.dbms_id = dbms_id
        db.db_name = db_name
        db.server_name = server_name
        db.port = port
        return db

    def test_exits_zero_on_success(self):
        """_ping_db raises SystemExit(0) after a successful connection."""
        db = self._make_db()
        mock_curs = MagicMock()
        mock_curs.fetchone.return_value = ("3.40.1",)
        db.cursor.return_value = mock_curs

        with pytest.raises(SystemExit) as exc_info:
            _ping_db(db)

        assert exc_info.value.code == 0

    def test_output_contains_connected(self, capsys):
        """The success message contains 'Connected'."""
        db = self._make_db()
        mock_curs = MagicMock()
        mock_curs.fetchone.return_value = ("3.40.1",)
        db.cursor.return_value = mock_curs

        with pytest.raises(SystemExit):
            _ping_db(db)

        captured = capsys.readouterr()
        assert "Connected" in captured.out

    def test_output_contains_dbms_name(self, capsys):
        """The success message includes the DBMS identifier."""
        db = self._make_db(dbms_id="PostgreSQL")
        mock_curs = MagicMock()
        mock_curs.fetchone.return_value = ("PostgreSQL 15.2 on x86_64-pc-linux-gnu",)
        db.cursor.return_value = mock_curs

        with pytest.raises(SystemExit):
            _ping_db(db)

        captured = capsys.readouterr()
        assert "PostgreSQL" in captured.out

    def test_version_query_failure_still_exits_zero(self, capsys):
        """If all version queries fail, _ping_db still exits 0 (connection ok)."""
        db = self._make_db()
        db.cursor.side_effect = Exception("no such function")

        with pytest.raises(SystemExit) as exc_info:
            _ping_db(db)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Connected" in captured.out

    def test_server_location_format(self, capsys):
        """Server-based DBs show host/db in the output."""
        db = self._make_db(dbms_id="PostgreSQL", db_name="mydb", server_name="pghost", port=5432)
        mock_curs = MagicMock()
        mock_curs.fetchone.return_value = ("PostgreSQL 15.2",)
        db.cursor.return_value = mock_curs

        with pytest.raises(SystemExit):
            _ping_db(db)

        captured = capsys.readouterr()
        assert "pghost" in captured.out
        assert "mydb" in captured.out

    def test_file_location_format(self, capsys):
        """File-based DBs show the file path in the output."""
        db = self._make_db(dbms_id="SQLite", db_name="/data/test.db", server_name=None)
        mock_curs = MagicMock()
        mock_curs.fetchone.return_value = ("3.40.1",)
        db.cursor.return_value = mock_curs

        with pytest.raises(SystemExit):
            _ping_db(db)

        captured = capsys.readouterr()
        assert "/data/test.db" in captured.out

    def test_db_close_called(self):
        """_ping_db closes the connection before exiting."""
        db = self._make_db()
        mock_curs = MagicMock()
        mock_curs.fetchone.return_value = ("3.40.1",)
        db.cursor.return_value = mock_curs

        with pytest.raises(SystemExit):
            _ping_db(db)

        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Integration tests using real SQLite (no server required)
# ---------------------------------------------------------------------------


class TestPingWithSQLite:
    """End-to-end tests that invoke _run() with a real SQLite database."""

    def test_ping_existing_db_exits_zero(self, tmp_path):
        """--ping against an existing SQLite DB exits with code 0."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        stack, _mocks = _apply_patches()
        with stack, pytest.raises(SystemExit) as exc_info:
            _run_ping(dsn=f"sqlite:///{db_file}")

        assert exc_info.value.code == 0

    def test_ping_output_contains_sqlite(self, tmp_path, capsys):
        """--ping output mentions SQLite."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        stack, _mocks = _apply_patches()
        with stack, pytest.raises(SystemExit):
            _run_ping(dsn=f"sqlite:///{db_file}")

        captured = capsys.readouterr()
        assert "Connected" in captured.out
        # SQLite DBMS id should appear
        assert "SQLite" in captured.out or "sqlite" in captured.out.lower()

    def test_ping_does_not_require_script_file(self, tmp_path):
        """--ping succeeds without any script file argument."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        stack, _mocks = _apply_patches()
        # Should exit 0, NOT raise an error about missing script
        with stack, pytest.raises(SystemExit) as exc_info:
            _run_ping(dsn=f"sqlite:///{db_file}")

        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# CLI layer tests (Typer / CliRunner)
# ---------------------------------------------------------------------------


class TestPingCLILayer:
    """Tests for the --ping flag at the Typer CLI layer."""

    def test_ping_does_not_need_script_positional(self, tmp_path):
        """``execsql --ping --dsn sqlite:///<f>`` works without a script positional.

        We verify that _run() is called with ``ping=True`` by capturing the
        call args.  The patch target is ``execsql.cli._run`` (the name imported
        into the CLI namespace) rather than ``execsql.cli.run._run``.
        """
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        captured_kwargs: dict = {}

        def _capture(*args, **kwargs):
            captured_kwargs.update(kwargs)
            raise SystemExit(0)

        with patch("execsql.cli._run", side_effect=_capture):
            result = runner.invoke(app, ["--ping", "--dsn", f"sqlite:///{db_file}"], catch_exceptions=False)

        assert result.exit_code == 0
        assert captured_kwargs.get("ping") is True

    def test_ping_flag_accepted(self, tmp_path):
        """The --ping flag is accepted by the CLI without an error about unknown option."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        with patch("execsql.cli._run", side_effect=SystemExit(0)):
            result = runner.invoke(app, ["--ping", "--dsn", f"sqlite:///{db_file}"])

        # A 2 exit code would mean "no such option" from Typer
        assert result.exit_code != 2, f"Unexpected exit code 2: {result.output}"

    def test_ping_script_file_not_required(self, tmp_path):
        """The CLI should NOT reject --ping just because no script file was given."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        with patch("execsql.cli._run", side_effect=SystemExit(0)):
            result = runner.invoke(app, ["--ping", "--dsn", f"sqlite:///{db_file}"])

        # "No SQL script file specified" error should NOT appear
        assert "No SQL script file" not in result.output

    def test_ping_e2e_sqlite(self, tmp_path):
        """Full end-to-end: --ping against a real SQLite DB via the app runner."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        with (
            patch("execsql.cli.run.FileWriter") as mock_fw_cls,
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.gui_console_on"),
            patch("execsql.cli.run.gui_console_isrunning", return_value=False),
            patch("execsql.cli.run.gui_console_off"),
            patch("execsql.cli.run.gui_console_wait_user"),
        ):
            mock_fw_cls.return_value.is_alive.return_value = True

            result = runner.invoke(
                app,
                ["--ping", "--dsn", f"sqlite:///{db_file}"],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "Connected" in result.output
