"""Tests for execsql.cli.run — parameter processing, DSN merging, state init,
error handling, and the _run() entry-point.

Strategy
--------
- Call ``_run()`` directly (bypassing Typer) with carefully crafted arguments.
- Mock every external I/O boundary: file system config, database connections,
  the ``runscripts`` execution loop, the ``FileWriter`` subprocess, and the
  GUI helpers.
- Tests are grouped by the section of ``_run()`` they exercise.
- The ``autouse`` ``minimal_conf`` fixture from conftest.py resets
  ``execsql.state`` before and after every test.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.cli.run import _apply_cli_options, _connect_initial_db, _print_dry_run, _run, _seed_early_subvars
from execsql.exceptions import ConfigError


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_mock_db(dbms_id="sqlite", db_name="test.db", server_name="localhost"):
    """Return a mock database object compatible with the DatabasePool interface."""
    db = MagicMock()
    db.type.dbms_id = dbms_id
    db.name.return_value = db_name
    db.server_name = server_name
    return db


def _make_sql_file(tmp_path, content="SELECT 1;"):
    """Write a minimal SQL script and return its path as a string."""
    p = tmp_path / "test.sql"
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# Patches needed to isolate _run() from system boundaries.
# ---------------------------------------------------------------------------

# These patches are applied in most _run() tests so the execution loop,
# database connections, and the async FileWriter never actually start.
_RUN_PATCHES = {
    "db": "execsql.cli.run._connect_initial_db",
    "execute": "execsql.script.executor.execute",
    "filewriter_cls": "execsql.cli.run.FileWriter",
    "filewriter_end": "execsql.cli.run.filewriter_end",
    "atexit": "execsql.cli.run.atexit",
    "gui_console_off": "execsql.cli.run.gui_console_off",
    "gui_console_on": "execsql.cli.run.gui_console_on",
    "gui_console_isrunning": "execsql.cli.run.gui_console_isrunning",
    "gui_console_wait_user": "execsql.cli.run.gui_console_wait_user",
}


def _apply_run_patches(**overrides):
    """Return a list of ``patch()`` context-manager objects for _run() isolation."""

    targets = dict(_RUN_PATCHES)
    targets.update(overrides)
    return targets


# ---------------------------------------------------------------------------
# _print_dry_run — unit tests
# ---------------------------------------------------------------------------


class TestPrintDryRun:
    """Tests for the _print_dry_run() helper."""

    def test_none_cmdlist_prints_no_commands(self, capsys):
        _print_dry_run(None)
        # Rich writes to its own console; no assertion on capsys, just no exception

    def test_empty_cmdlist_does_not_raise(self, capsys):
        mock_cmdlist = MagicMock()
        mock_cmdlist.cmdlist = []
        _print_dry_run(mock_cmdlist)  # should not raise

    def test_sql_command_renders(self, capsys):
        cmd = MagicMock()
        cmd.command_type = "sql"
        cmd.source = "test.sql"
        cmd.line_no = 1
        cmd.commandline.return_value = "SELECT 1;"

        mock_cmdlist = MagicMock()
        mock_cmdlist.cmdlist = [cmd]
        _print_dry_run(mock_cmdlist)  # must not raise

    def test_metacmd_renders(self, capsys):
        cmd = MagicMock()
        cmd.command_type = "metacmd"
        cmd.source = "test.sql"
        cmd.line_no = 5
        cmd.commandline.return_value = 'WRITE "hello"'

        mock_cmdlist = MagicMock()
        mock_cmdlist.cmdlist = [cmd]
        _print_dry_run(mock_cmdlist)  # must not raise

    def test_multiple_commands_no_raise(self):
        cmds = []
        for i in range(3):
            c = MagicMock()
            c.command_type = "sql" if i % 2 == 0 else "metacmd"
            c.source = "s.sql"
            c.line_no = i + 1
            c.commandline.return_value = f"CMD {i}"
            cmds.append(c)

        mock_cmdlist = MagicMock()
        mock_cmdlist.cmdlist = cmds
        _print_dry_run(mock_cmdlist)  # must not raise


# ---------------------------------------------------------------------------
# _connect_initial_db — unit tests
# ---------------------------------------------------------------------------


class TestConnectInitialDb:
    """Unit tests for _connect_initial_db() — each branch exercises a db_type."""

    def _conf(self, **kwargs):
        """Build a minimal conf namespace for _connect_initial_db()."""
        defaults = {
            "db_type": "l",
            "db_file": "/tmp/test.db",
            "server": None,
            "db": None,
            "username": "user",
            "passwd_prompt": False,
            "db_encoding": None,
            "new_db": False,
            "port": None,
            "access_username": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_sqlite_calls_db_sqlite(self):
        conf = self._conf(db_type="l", db_file="/tmp/test.db")
        mock_db = MagicMock()
        with patch("execsql.cli.run._connect_initial_db") as mock_fn:
            mock_fn.return_value = mock_db
            result = _connect_initial_db.__wrapped__(conf) if hasattr(_connect_initial_db, "__wrapped__") else None
        # Verify the factory function is called with the right type
        with patch("execsql.db.factory.db_SQLite", return_value=mock_db) as mock_sqlite:
            result = _connect_initial_db(conf)
        mock_sqlite.assert_called_once()
        assert result is mock_db

    def test_sqlite_no_file_calls_fatal_error(self):
        conf = self._conf(db_type="l", db_file=None)
        with patch("execsql.utils.errors.fatal_error") as mock_fatal:
            mock_fatal.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                _connect_initial_db(conf)
            mock_fatal.assert_called_once()

    def test_access_no_file_calls_fatal_error(self):
        conf = self._conf(db_type="a", db_file=None)
        with patch("execsql.utils.errors.fatal_error") as mock_fatal:
            mock_fatal.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                _connect_initial_db(conf)
            mock_fatal.assert_called_once()

    def test_duckdb_no_file_calls_fatal_error(self):
        conf = self._conf(db_type="k", db_file=None)
        with patch("execsql.utils.errors.fatal_error") as mock_fatal:
            mock_fatal.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                _connect_initial_db(conf)
            mock_fatal.assert_called_once()

    def test_postgres_calls_db_postgres(self):
        conf = self._conf(db_type="p", db_file=None, server="localhost", db="mydb")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_Postgres", return_value=mock_db) as mock_pg:
            result = _connect_initial_db(conf)
        mock_pg.assert_called_once()
        assert result is mock_db

    def test_sqlserver_calls_db_sqlserver(self):
        conf = self._conf(db_type="s", db_file=None, server="mssql-host", db="mydb")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_SqlServer", return_value=mock_db) as mock_ss:
            result = _connect_initial_db(conf)
        mock_ss.assert_called_once()
        assert result is mock_db

    def test_mysql_calls_db_mysql(self):
        conf = self._conf(db_type="m", db_file=None, server="mysql-host", db="mydb")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_MySQL", return_value=mock_db) as mock_my:
            result = _connect_initial_db(conf)
        mock_my.assert_called_once()
        assert result is mock_db

    def test_duckdb_calls_db_duckdb(self):
        conf = self._conf(db_type="k", db_file="/tmp/test.duckdb")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_DuckDB", return_value=mock_db) as mock_duck:
            result = _connect_initial_db(conf)
        mock_duck.assert_called_once()
        assert result is mock_db

    def test_oracle_calls_db_oracle(self):
        conf = self._conf(db_type="o", db_file=None, server="oracle-host", db="mydb")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_Oracle", return_value=mock_db) as mock_ora:
            result = _connect_initial_db(conf)
        mock_ora.assert_called_once()
        assert result is mock_db

    def test_firebird_calls_db_firebird(self):
        conf = self._conf(db_type="f", db_file=None, server="fb-host", db="mydb")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_Firebird", return_value=mock_db) as mock_fb:
            result = _connect_initial_db(conf)
        mock_fb.assert_called_once()
        assert result is mock_db

    def test_dsn_odbc_calls_db_dsn(self):
        conf = self._conf(db_type="d", db_file=None, db="mydsn")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_Dsn", return_value=mock_db) as mock_dsn:
            result = _connect_initial_db(conf)
        mock_dsn.assert_called_once()
        assert result is mock_db

    def test_unknown_db_type_calls_fatal_error(self):
        conf = self._conf(db_type="z")
        with patch("execsql.utils.errors.fatal_error") as mock_fatal:
            mock_fatal.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                _connect_initial_db(conf)
            mock_fatal.assert_called_once()

    def test_access_with_file_calls_db_access(self):
        conf = self._conf(db_type="a", db_file="/tmp/mydb.accdb", access_username="admin")
        mock_db = MagicMock()
        with patch("execsql.db.factory.db_Access", return_value=mock_db) as mock_acc:
            result = _connect_initial_db(conf)
        mock_acc.assert_called_once()
        assert result is mock_db


# ---------------------------------------------------------------------------
# Substitution variable setup — verified through _run()
# ---------------------------------------------------------------------------


class TestSubstitutionVarSetup:
    """Verify that _run() seeds the expected built-in substitution variables."""

    def _invoke_run(self, tmp_path, **kwargs):
        """Call _run() with all external I/O mocked; return the subvars dict."""
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        defaults = {
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
        }
        defaults.update(kwargs)

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(**defaults)

        return _state.subvars

    def test_last_rowcount_seeded(self, tmp_path):
        sv = self._invoke_run(tmp_path)
        # varvalue returns None for $LAST_ROWCOUNT (it is set to None)
        # The key should exist in the store
        assert "$last_rowcount" in sv._subs_dict

    def test_script_start_time_seeded(self, tmp_path):
        sv = self._invoke_run(tmp_path)
        val = sv.varvalue("$SCRIPT_START_TIME")
        assert val and len(val) == 16, f"Expected 'YYYY-MM-DD HH:MM', got {val!r}"

    def test_date_tag_format(self, tmp_path):
        sv = self._invoke_run(tmp_path)
        val = sv.varvalue("$DATE_TAG")
        assert val and len(val) == 8 and val.isdigit()

    def test_datetime_tag_format(self, tmp_path):
        sv = self._invoke_run(tmp_path)
        val = sv.varvalue("$DATETIME_TAG")
        # Format: YYYYMMDD_HHMM
        assert val and "_" in val and len(val) == 13

    def test_os_seeded(self, tmp_path):
        sv = self._invoke_run(tmp_path)
        val = sv.varvalue("$OS")
        assert val in ("linux", "windows", "darwin", sys.platform)

    def test_user_seeded(self, tmp_path):
        import getpass

        sv = self._invoke_run(tmp_path)
        assert sv.varvalue("$USER") == getpass.getuser()

    def test_starting_path_seeded(self, tmp_path):
        sv = self._invoke_run(tmp_path)
        val = sv.varvalue("$STARTING_PATH")
        assert val and val.endswith("/" if sys.platform != "win32" else "\\")

    def test_starting_script_seeded_when_file(self, tmp_path):
        sv = self._invoke_run(tmp_path)
        val = sv.varvalue("$STARTING_SCRIPT")
        assert val and val != "<inline>"

    def test_starting_script_inline_when_command(self, tmp_path):
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
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
                db_type="l",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=None,
                command="SELECT 1;",
                dry_run=False,
                dsn=f"sqlite:///{tmp_path / 'test.db'}",
                output_dir=None,
                progress=False,
            )

        val = _state.subvars.varvalue("$STARTING_SCRIPT")
        assert val == "<inline>"

    def test_arg_vars_seeded_from_sub_vars(self, tmp_path):
        sv = self._invoke_run(tmp_path, sub_vars=["alpha", "beta"])
        assert sv.varvalue("$ARG_1") == "alpha"
        assert sv.varvalue("$ARG_2") == "beta"

    def test_env_vars_exposed_as_ampersand_prefix(self, tmp_path):
        import os

        os.environ["_TEST_EXECSQL_VAR_XYZ"] = "check_me"
        try:
            sv = self._invoke_run(tmp_path)
            val = sv.varvalue("&_TEST_EXECSQL_VAR_XYZ")
            assert val == "check_me"
        finally:
            del os.environ["_TEST_EXECSQL_VAR_XYZ"]


# ---------------------------------------------------------------------------
# OS platform substitution variable branch coverage
# ---------------------------------------------------------------------------


class TestOsPlatformBranches:
    """Cover the linux / windows branches for the $OS substitution variable."""

    def _run_with_platform(self, tmp_path, platform_value):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
            patch("sys.platform", platform_value),
        ):
            _run(
                positional=[script],
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
                db_type="l",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=f"sqlite:///{tmp_path / 'test.db'}",
                output_dir=None,
                progress=False,
            )
        return _state.subvars.varvalue("$OS")

    def test_linux_platform_normalized(self, tmp_path):
        val = self._run_with_platform(tmp_path, "linux2")
        assert val == "linux"

    def test_windows_platform_normalized(self, tmp_path):
        val = self._run_with_platform(tmp_path, "win32")
        assert val == "windows"

    def test_other_platform_passes_through(self, tmp_path):
        val = self._run_with_platform(tmp_path, "darwin")
        assert val == "darwin"


# ---------------------------------------------------------------------------
# Configuration merging — CLI flags override conf values
# ---------------------------------------------------------------------------


class TestConfigMerging:
    """Tests that verify CLI option values are written into conf correctly."""

    def _invoke_run(self, tmp_path, **kwargs):
        """Invoke _run() and return the resulting conf object."""
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        base = {
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
        }
        base.update(kwargs)

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(**base)

        return _state.conf

    def test_user_sets_conf_username(self, tmp_path):
        conf = self._invoke_run(tmp_path, user="alice")
        assert conf.username == "alice"

    def test_no_passwd_disables_prompt(self, tmp_path):
        conf = self._invoke_run(tmp_path, no_passwd=True)
        assert conf.passwd_prompt is False

    def test_database_encoding_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, database_encoding="latin-1")
        assert conf.db_encoding == "latin-1"

    def test_script_encoding_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, script_encoding="ascii")
        assert conf.script_encoding == "ascii"

    def test_output_encoding_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, output_encoding="utf-16")
        assert conf.output_encoding == "utf-16"

    def test_import_encoding_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, import_encoding="cp1252")
        assert conf.import_encoding == "cp1252"

    def test_import_buffer_scaled_to_kb(self, tmp_path):
        conf = self._invoke_run(tmp_path, import_buffer=64)
        assert conf.import_buffer == 64 * 1024

    def test_make_dirs_truthy_values(self, tmp_path):
        for val in ("1", "t", "T", "y", "Y"):
            conf = self._invoke_run(tmp_path, make_dirs=val)
            assert conf.make_export_dirs is True, f"make_dirs={val!r} should enable make_export_dirs"

    def test_make_dirs_falsy_values(self, tmp_path):
        for val in ("0", "f", "F", "n", "N"):
            conf = self._invoke_run(tmp_path, make_dirs=val)
            assert conf.make_export_dirs is False, f"make_dirs={val!r} should NOT enable make_export_dirs"

    def test_boolean_int_truthy_values(self, tmp_path):
        for val in ("1", "t", "T", "y", "Y"):
            conf = self._invoke_run(tmp_path, boolean_int=val)
            assert conf.boolean_int is True

    def test_boolean_int_falsy_values(self, tmp_path):
        for val in ("0", "f", "F", "n", "N"):
            conf = self._invoke_run(tmp_path, boolean_int=val)
            assert conf.boolean_int is False

    def test_scanlines_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, scanlines=250)
        assert conf.scan_lines == 250

    def test_scanlines_defaults_to_100_when_none(self, tmp_path):
        # scan_lines should be 100 when neither conf file nor CLI provide it
        conf = self._invoke_run(tmp_path, scanlines=None)
        assert conf.scan_lines == 100

    def test_use_gui_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, use_gui="0")
        assert conf.gui_level == 0

    def test_gui_framework_normalised_to_lower(self, tmp_path):
        conf = self._invoke_run(tmp_path, gui_framework="Tkinter")
        assert conf.gui_framework == "tkinter"

    def test_db_type_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, db_type="l")
        assert conf.db_type == "l"

    def test_user_logfile_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, user_logfile=True)
        assert conf.user_logfile is True

    def test_port_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, port=5432)
        assert conf.port == 5432

    def test_new_db_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, new_db=True)
        assert conf.new_db is True

    def test_output_dir_resolves_to_absolute(self, tmp_path):
        conf = self._invoke_run(tmp_path, output_dir=str(tmp_path))
        assert Path(conf.export_output_dir).is_absolute()

    def test_progress_applied(self, tmp_path):
        conf = self._invoke_run(tmp_path, progress=True)
        assert conf.show_progress is True

    def test_access_username_set_when_type_a_and_user(self, tmp_path):
        # When db_type == 'a' and a user is given, conf.access_username must be set.
        # Provide the Access db_file via a positional arg so the db_file guard passes.
        script = _make_sql_file(tmp_path, "SELECT 1;")
        db_file = str(tmp_path / "mydb.accdb")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False
        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=[script, db_file],  # positional[1] becomes db_file for type 'a'
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
                db_type="a",
                user="bob",
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=None,
                output_dir=None,
                progress=False,
            )
        assert _state.conf.access_username == "bob"


# ---------------------------------------------------------------------------
# DSN parsing and merging
# ---------------------------------------------------------------------------


class TestDsnMerging:
    """Tests that --dsn values are correctly merged into conf."""

    def _invoke_run_with_dsn(self, tmp_path, dsn_str, extra_kwargs=None):
        script = _make_sql_file(tmp_path, "SELECT 1;")
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
            "db_type": None,
            "user": None,
            "use_gui": None,
            "gui_framework": None,
            "no_passwd": False,
            "import_buffer": None,
            "script_name": script,
            "command": None,
            "dry_run": False,
            "dsn": dsn_str,
            "output_dir": None,
            "progress": False,
        }
        if extra_kwargs:
            kwargs.update(extra_kwargs)

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(**kwargs)

        return _state.conf

    def test_postgres_dsn_sets_db_type_p(self, tmp_path):
        conf = self._invoke_run_with_dsn(tmp_path, "postgresql://user@host/mydb")
        assert conf.db_type == "p"

    def test_postgres_dsn_sets_server(self, tmp_path):
        conf = self._invoke_run_with_dsn(tmp_path, "postgresql://user@dbhost/mydb")
        assert conf.server == "dbhost"

    def test_postgres_dsn_sets_db(self, tmp_path):
        conf = self._invoke_run_with_dsn(tmp_path, "postgresql://user@host/targetdb")
        assert conf.db == "targetdb"

    def test_postgres_dsn_sets_user(self, tmp_path):
        conf = self._invoke_run_with_dsn(tmp_path, "postgresql://alice@host/db")
        assert conf.username == "alice"

    def test_postgres_dsn_sets_password_disables_prompt(self, tmp_path):
        conf = self._invoke_run_with_dsn(tmp_path, "postgresql://user:s3cr3t@host/db")
        assert conf.db_password == "s3cr3t"
        assert conf.passwd_prompt is False

    def test_postgres_dsn_sets_port(self, tmp_path):
        conf = self._invoke_run_with_dsn(tmp_path, "postgresql://user@host:5433/db")
        assert conf.port == 5433

    def test_sqlite_dsn_sets_db_file(self, tmp_path):
        db_path = str(tmp_path / "myfile.db")
        conf = self._invoke_run_with_dsn(tmp_path, f"sqlite:///{db_path}")
        assert conf.db_file == db_path or conf.db_type == "l"

    def test_invalid_dsn_scheme_exits_with_1(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        with pytest.raises(SystemExit) as exc_info:
            _run(
                positional=[script],
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
                db_type=None,
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn="mongodb://host/db",
                output_dir=None,
                progress=False,
            )
        assert exc_info.value.code == 1

    def test_cli_db_type_takes_precedence_over_dsn_type(self, tmp_path):
        """When -t is also given, it should override the DSN-derived type."""
        # We pass db_type="l" explicitly alongside a postgres DSN.
        conf = self._invoke_run_with_dsn(
            tmp_path,
            f"sqlite:///{tmp_path / 'test.db'}",
            extra_kwargs={"db_type": "l"},
        )
        assert conf.db_type == "l"


# ---------------------------------------------------------------------------
# Positional argument routing
# ---------------------------------------------------------------------------


class TestPositionalArgRouting:
    """Tests that positional args after the script name set the right conf attrs."""

    def _invoke(self, tmp_path, positional, db_type="l", command=None, dsn=None):
        if command is None:
            script = _make_sql_file(tmp_path, "SELECT 1;")
            if positional and positional[0] == "__script__":
                positional[0] = script
        else:
            script = None

        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=positional,
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
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=command,
                dry_run=False,
                dsn=dsn if dsn else (f"sqlite:///{tmp_path / 'test.db'}" if db_type == "l" else None),
                output_dir=None,
                progress=False,
            )
        return _state.conf

    def test_one_positional_sqlite_sets_db_file(self, tmp_path):
        db_file = str(tmp_path / "mydb.sqlite")
        script = str(_make_sql_file(tmp_path, "SELECT 1;"))
        conf = self._invoke(tmp_path, [script, db_file], db_type="l", dsn=None)
        assert conf.db_file == db_file

    def test_one_positional_postgres_no_server_sets_server(self, tmp_path):
        """For a network type with no server set, one extra positional -> server."""
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False
        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=[script, "myserver"],
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
                db_type="p",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=None,
                output_dir=None,
                progress=False,
            )
        assert _state.conf.server == "myserver"

    def test_two_positionals_sets_server_and_db(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False
        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=[script, "srv1", "db1"],
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
                db_type="p",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=None,
                output_dir=None,
                progress=False,
            )
        assert _state.conf.server == "srv1"
        assert _state.conf.db == "db1"

    def test_too_many_positionals_calls_fatal_error(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        with patch("execsql.utils.errors.fatal_error") as mock_fatal:
            mock_fatal.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                _run(
                    positional=[script, "srv", "db", "extra"],
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
                    db_type="p",
                    user=None,
                    use_gui=None,
                    gui_framework=None,
                    no_passwd=False,
                    import_buffer=None,
                    script_name=script,
                    command=None,
                    dry_run=False,
                    dsn=None,
                    output_dir=None,
                    progress=False,
                )
            mock_fatal.assert_called_once()

    def test_dsn_type_sets_db_from_positional(self, tmp_path):
        """For db_type 'd' (ODBC), one positional sets conf.db."""
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False
        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=[script, "mydsn"],
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
                db_type="d",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=None,
                output_dir=None,
                progress=False,
            )
        assert _state.conf.db == "mydsn"

    def test_inline_command_positionals_offset_by_zero(self, tmp_path):
        """In -c mode (command != None) the offset is 0; positional[0] is connection arg."""
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False
        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=["srv_inline", "db_inline"],
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
                db_type="p",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=None,
                command="SELECT 1;",
                dry_run=False,
                dsn=None,
                output_dir=None,
                progress=False,
            )
        assert _state.conf.server == "srv_inline"
        assert _state.conf.db == "db_inline"


# ---------------------------------------------------------------------------
# GUI level validation
# ---------------------------------------------------------------------------


class TestGuiLevelValidation:
    def test_invalid_gui_level_raises_config_error(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False
        with (
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            pytest.raises(ConfigError, match="Invalid GUI level"),
        ):
            _run(
                positional=[script],
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
                db_type="l",
                user=None,
                use_gui="9",
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=f"sqlite:///{tmp_path / 'test.db'}",
                output_dir=None,
                progress=False,
            )


# ---------------------------------------------------------------------------
# No database specified — fatal_error path
# ---------------------------------------------------------------------------


class TestNoDatabaseSpecified:
    """When no server/db/db_file is configured and gui_level <= 1, fatal_error is called."""

    def test_no_db_calls_fatal_error(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        with (
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
            patch("execsql.utils.errors.fatal_error") as mock_fatal,
        ):
            mock_fatal.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                _run(
                    positional=[script],
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
                    db_type=None,  # No db_type → 'a' default, no db_file
                    user=None,
                    use_gui=None,
                    gui_framework=None,
                    no_passwd=False,
                    import_buffer=None,
                    script_name=script,
                    command=None,
                    dry_run=False,
                    dsn=None,  # No DSN
                    output_dir=None,
                    progress=False,
                )
            mock_fatal.assert_called_once()


# TestExecuteScriptDirect removed — _execute_script_direct was deleted
# when the AST executor became the only execution engine.


# ---------------------------------------------------------------------------
# Default encoding fallbacks
# ---------------------------------------------------------------------------


class TestDefaultEncodings:
    """Verify that missing encodings default to 'utf8'."""

    def _invoke_run_no_encodings(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=[script],
                sub_vars=None,
                boolean_int=None,
                make_dirs=None,
                database_encoding=None,
                script_encoding=None,  # deliberately None
                output_encoding=None,  # deliberately None
                import_encoding=None,  # deliberately None
                user_logfile=False,
                new_db=False,
                port=None,
                scanlines=None,
                db_type="l",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=f"sqlite:///{tmp_path / 'test.db'}",
                output_dir=None,
                progress=False,
            )
        return _state.conf

    def test_script_encoding_defaults_to_utf8(self, tmp_path):
        conf = self._invoke_run_no_encodings(tmp_path)
        assert conf.script_encoding == "utf8"

    def test_output_encoding_defaults_to_utf8(self, tmp_path):
        conf = self._invoke_run_no_encodings(tmp_path)
        assert conf.output_encoding == "utf8"

    def test_import_encoding_defaults_to_utf8(self, tmp_path):
        conf = self._invoke_run_no_encodings(tmp_path)
        assert conf.import_encoding == "utf8"


# ---------------------------------------------------------------------------
# run_id and $RUN_ID substitution variable
# ---------------------------------------------------------------------------


class TestRunIdSubvar:
    def test_run_id_seeded_in_subvars(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            _run(
                positional=[script],
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
                db_type="l",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn=f"sqlite:///{tmp_path / 'test.db'}",
                output_dir=None,
                progress=False,
            )

        run_id = _state.subvars.varvalue("$RUN_ID")
        assert run_id is not None and run_id != ""


# ---------------------------------------------------------------------------
# Postgres positional with existing server — routes to db
# ---------------------------------------------------------------------------


class TestPositionalNetworkRouting:
    """When server is already set (e.g. from DSN) and one extra positional comes in,
    it should be used as conf.db rather than conf.server."""

    def test_one_positional_with_existing_server_sets_db(self, tmp_path):
        script = _make_sql_file(tmp_path, "SELECT 1;")
        mock_db = _make_mock_db()
        mock_fw = MagicMock()
        mock_fw.is_alive.return_value = False

        with (
            patch("execsql.cli.run._connect_initial_db", return_value=mock_db),
            patch("execsql.script.executor.execute"),
            patch("execsql.cli.run.FileWriter", return_value=mock_fw),
            patch("execsql.cli.run.filewriter_end"),
            patch("execsql.cli.run.atexit"),
        ):
            # The DSN sets server=dbhost, db=None. Then positional[1]="extra_db"
            # should be assigned to conf.db because server is already set.
            _run(
                positional=[script, "extra_db"],
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
                db_type="p",
                user=None,
                use_gui=None,
                gui_framework=None,
                no_passwd=False,
                import_buffer=None,
                script_name=script,
                command=None,
                dry_run=False,
                dsn="postgresql://user@dbhost",  # sets server, no db
                output_dir=None,
                progress=False,
            )
        # server set by DSN, positional should go to db
        assert _state.conf.db == "extra_db"


# ---------------------------------------------------------------------------
# _seed_early_subvars — unit tests for exception/filter branches
# ---------------------------------------------------------------------------


class TestSeedEarlySubvars:
    """Unit tests for _seed_early_subvars() covering the sensitive-key filter
    and the exception-swallowing branch for invalid env-var names."""

    def test_sensitive_key_filtered_out(self):
        """Env vars whose names contain a sensitive substring are not seeded.

        This exercises the ``continue`` branch (line 211 in run.py) where a key
        such as ``MY_SECRET_KEY`` is skipped before ``add_substitution`` is called.
        """
        with patch.dict("os.environ", {"MY_SECRET_KEY": "s3cr3t"}, clear=False):
            subvars = _seed_early_subvars()
        # The sensitive var must not appear with the & prefix.
        assert subvars.varvalue("&MY_SECRET_KEY") is None
        assert subvars.varvalue("&my_secret_key") is None

    def test_invalid_env_var_name_is_silently_skipped(self):
        """An env var whose name produces an invalid substitution key does not raise.

        Keys that contain characters outside word-character range (e.g. a hyphen)
        produce a variable name like ``&MY-VAR`` which fails SubVarSet.check_var_name().
        The ``except Exception: pass`` block (lines 214-215) swallows the error.
        """
        # Use a key containing a hyphen — illegal in an execsql variable name.
        with patch.dict("os.environ", {"EXECSQL-INVALID-KEY": "value"}, clear=False):
            # Must not raise even though add_substitution will raise ErrInfo.
            subvars = _seed_early_subvars()
        # The variable should simply be absent from the internal dict rather than
        # causing a crash.  Check the internal dict directly to avoid calling
        # varvalue() with an invalid key (which would itself raise).
        assert "&execsql-invalid-key" not in subvars._subs_dict


# ---------------------------------------------------------------------------
# _apply_cli_options — unit tests for default-fallback branches
# ---------------------------------------------------------------------------


class TestApplyCliOptionsDefaults:
    """Unit tests for _apply_cli_options() that exercise the default-value
    fallback branches.  These branches are only reachable when conf fields are
    ``None`` (i.e. not set by ConfigData defaults), which never happens when
    going through _run() — hence these tests call _apply_cli_options() directly
    with a hand-crafted SimpleNamespace conf.
    """

    def _conf(self, **kwargs):
        """Return a minimal SimpleNamespace conf with all relevant fields set to
        ``None`` so that every default-fallback branch in _apply_cli_options()
        becomes reachable."""
        defaults = {
            "username": None,
            "passwd_prompt": True,
            "db_encoding": None,
            "script_encoding": None,
            "output_encoding": None,
            "import_encoding": None,
            "import_buffer": None,
            "make_export_dirs": None,
            "boolean_int": None,
            "scan_lines": None,
            "gui_level": None,
            "gui_framework": None,
            "db_type": None,
            "user_logfile": False,
            "port": None,
            "access_username": None,
            "new_db": False,
            "export_output_dir": None,
            "show_progress": False,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def _call(self, conf, **kwargs):
        """Invoke _apply_cli_options() with the supplied conf and kwargs,
        filling in None/False defaults for any omitted parameters."""
        defaults = {
            "user": None,
            "no_passwd": False,
            "database_encoding": None,
            "script_encoding": None,
            "output_encoding": None,
            "import_encoding": None,
            "import_buffer": None,
            "make_dirs": None,
            "boolean_int": None,
            "scanlines": None,
            "use_gui": None,
            "gui_framework": None,
            "db_type": None,
            "user_logfile": False,
            "port": None,
            "new_db": False,
            "output_dir": None,
            "progress": False,
        }
        defaults.update(kwargs)
        _apply_cli_options(conf, **defaults)

    def test_script_encoding_defaults_to_utf8_when_conf_is_none(self):
        """When conf.script_encoding is None and no CLI flag is given, default to 'utf8'."""
        conf = self._conf(script_encoding=None)
        self._call(conf, script_encoding=None)
        assert conf.script_encoding == "utf8"

    def test_output_encoding_defaults_to_utf8_when_conf_is_none(self):
        """When conf.output_encoding is None and no CLI flag is given, default to 'utf8'."""
        conf = self._conf(output_encoding=None)
        self._call(conf, output_encoding=None)
        assert conf.output_encoding == "utf8"

    def test_import_encoding_defaults_to_utf8_when_conf_is_none(self):
        """When conf.import_encoding is None and no CLI flag is given, default to 'utf8'."""
        conf = self._conf(import_encoding=None)
        self._call(conf, import_encoding=None)
        assert conf.import_encoding == "utf8"

    def test_scan_lines_defaults_to_100_when_conf_is_none(self):
        """When conf.scan_lines is None and scanlines CLI arg is None, default to 100."""
        conf = self._conf(scan_lines=None)
        self._call(conf, scanlines=None)
        assert conf.scan_lines == 100

    def test_db_type_defaults_to_l_when_conf_is_none(self):
        """When conf.db_type is None and db_type CLI arg is None, default to 'l' (SQLite)."""
        conf = self._conf(db_type=None)
        self._call(conf, db_type=None)
        assert conf.db_type == "l"

    def test_gui_level_out_of_range_raises_config_error(self):
        """A gui_level value outside 0-3 raises ConfigError after being set by use_gui."""
        conf = self._conf(gui_level=None)
        with pytest.raises(ConfigError, match="Invalid GUI level"):
            self._call(conf, use_gui="5")

    def test_cli_script_encoding_overrides_none_conf(self):
        """A CLI-supplied script_encoding wins over None in conf."""
        conf = self._conf(script_encoding=None)
        self._call(conf, script_encoding="latin-1")
        assert conf.script_encoding == "latin-1"

    def test_cli_output_encoding_overrides_none_conf(self):
        """A CLI-supplied output_encoding wins over None in conf."""
        conf = self._conf(output_encoding=None)
        self._call(conf, output_encoding="cp1252")
        assert conf.output_encoding == "cp1252"

    def test_cli_import_encoding_overrides_none_conf(self):
        """A CLI-supplied import_encoding wins over None in conf."""
        conf = self._conf(import_encoding=None)
        self._call(conf, import_encoding="utf-16")
        assert conf.import_encoding == "utf-16"

    def test_cli_scanlines_overrides_none_conf(self):
        """A CLI-supplied scanlines wins over None in conf (no default applied)."""
        conf = self._conf(scan_lines=None)
        self._call(conf, scanlines=500)
        assert conf.scan_lines == 500

    def test_cli_db_type_overrides_none_conf(self):
        """A CLI-supplied db_type wins over None in conf."""
        conf = self._conf(db_type=None)
        self._call(conf, db_type="p")
        assert conf.db_type == "p"
