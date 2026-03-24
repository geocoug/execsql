"""Unit tests for execsql metacommand handlers in metacommands/connect.py.

Tests the handler functions directly with mocked database connections.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_dbs():
    """Install a mock DatabasePool on _state and return it."""
    mock_dbs = MagicMock()
    mock_dbs.aliases.return_value = ["initial", "testdb"]
    mock_dbs.current_alias.return_value = "initial"
    _state.dbs = mock_dbs
    return mock_dbs


def _setup_exec_log():
    """Install a mock exec_log on _state."""
    mock_log = MagicMock()
    _state.exec_log = mock_log
    return mock_log


def _setup_status():
    """Install a mock status on _state."""
    mock_status = MagicMock()
    mock_status.batch.uses_db.return_value = False
    _state.status = mock_status
    return mock_status


# ---------------------------------------------------------------------------
# Tests for x_connect_sqlite
# ---------------------------------------------------------------------------


class TestXConnectSQLite:
    """Tests for the CONNECT SQLITE metacommand handler."""

    def test_connect_sqlite_new_creates_db(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        db_path = str(tmp_path / "test.db")
        mock_dbs = _setup_dbs()
        _setup_exec_log()
        _setup_status()

        with patch("execsql.metacommands.connect.SQLiteDatabase") as MockSQLiteDB:
            mock_db_instance = MagicMock()
            MockSQLiteDB.return_value = mock_db_instance

            x_connect_sqlite(
                filename=db_path,
                db_alias="mydb",
                new="NEW",
                metacommandline="CONNECT SQLITE ...",
            )

            MockSQLiteDB.assert_called_once_with(db_path)
            mock_dbs.add.assert_called_once_with("mydb", mock_db_instance)

    def test_connect_sqlite_missing_file_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        db_path = str(tmp_path / "nonexistent.db")
        _setup_dbs()

        with pytest.raises(ErrInfo):
            x_connect_sqlite(
                filename=db_path,
                db_alias="mydb",
                new=None,
                metacommandline="CONNECT SQLITE ...",
            )


# ---------------------------------------------------------------------------
# Tests for x_connect_duckdb
# ---------------------------------------------------------------------------


class TestXConnectDuckDB:
    """Tests for the CONNECT DUCKDB metacommand handler."""

    def test_connect_duckdb_new_creates_db(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_duckdb

        db_path = str(tmp_path / "test.duckdb")
        mock_dbs = _setup_dbs()

        with patch("execsql.metacommands.connect.DuckDBDatabase") as MockDuckDB:
            mock_db_instance = MagicMock()
            MockDuckDB.return_value = mock_db_instance

            x_connect_duckdb(
                filename=db_path,
                db_alias="dkdb",
                new="NEW",
                metacommandline="CONNECT DUCKDB ...",
            )

            MockDuckDB.assert_called_once_with(db_path)
            mock_dbs.add.assert_called_once_with("dkdb", mock_db_instance)

    def test_connect_duckdb_missing_file_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_duckdb

        db_path = str(tmp_path / "nonexistent.duckdb")
        _setup_dbs()

        with pytest.raises(ErrInfo):
            x_connect_duckdb(
                filename=db_path,
                db_alias="dkdb",
                new=None,
                metacommandline="CONNECT DUCKDB ...",
            )


# ---------------------------------------------------------------------------
# Tests for x_connect_pg
# ---------------------------------------------------------------------------


class TestXConnectPg:
    """Tests for the CONNECT POSTGRESQL metacommand handler."""

    def test_connect_pg_basic(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        mock_dbs = _setup_dbs()

        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPgDB:
            mock_db_instance = MagicMock()
            MockPgDB.return_value = mock_db_instance

            x_connect_pg(
                server="localhost",
                db_name="testdb",
                user="admin",
                db_alias="pgdb",
                need_pwd=None,
                port=None,
                new=None,
                password=None,
                encoding=None,
            )

            MockPgDB.assert_called_once_with(
                "localhost",
                "testdb",
                "admin",
                need_passwd=None,
                port=None,
                new_db=False,
                password=None,
            )
            mock_dbs.add.assert_called_once_with("pgdb", mock_db_instance)

    def test_connect_pg_with_port_and_encoding(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        _setup_dbs()

        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPgDB:
            mock_db_instance = MagicMock()
            MockPgDB.return_value = mock_db_instance

            x_connect_pg(
                server="dbhost",
                db_name="mydb",
                user="user1",
                db_alias="pg2",
                need_pwd="true",
                port="5433",
                new=None,
                password="secret",
                encoding="latin1",
            )

            MockPgDB.assert_called_once_with(
                "dbhost",
                "mydb",
                "user1",
                need_passwd=True,
                port=5433,
                new_db=False,
                encoding="latin1",
                password="secret",
            )


# ---------------------------------------------------------------------------
# Tests for x_use
# ---------------------------------------------------------------------------


class TestXUse:
    """Tests for the USE DATABASE metacommand handler."""

    def test_use_switches_database(self, minimal_conf):
        from execsql.metacommands.connect import x_use

        mock_dbs = _setup_dbs()
        mock_log = _setup_exec_log()

        mock_db = MagicMock()
        mock_db.type = MagicMock()
        mock_db.type.dbms_id = "postgresql"
        mock_db.name.return_value = "testdb"
        mock_db.server_name = "localhost"
        mock_dbs.aliased_as.return_value = mock_db
        mock_dbs.current.return_value = mock_db

        mock_sv = MagicMock()
        _state.subvars = mock_sv

        x_use(db_alias="testdb", metacommandline="USE DATABASE testdb")

        mock_dbs.make_current.assert_called_once_with("testdb")
        mock_log.log_db_connect.assert_called_once()
        # Should set substitution variables
        assert mock_sv.add_substitution.call_count == 3

    def test_use_unknown_alias_raises(self, minimal_conf):
        from execsql.metacommands.connect import x_use

        mock_dbs = _setup_dbs()
        mock_dbs.aliases.return_value = ["initial"]

        with pytest.raises(ErrInfo):
            x_use(db_alias="nosuch", metacommandline="USE DATABASE nosuch")


# ---------------------------------------------------------------------------
# Tests for x_disconnect
# ---------------------------------------------------------------------------


class TestXDisconnect:
    """Tests for the CLOSE DATABASE metacommand handler."""

    def test_disconnect_by_alias(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        mock_dbs = _setup_dbs()
        _setup_exec_log()
        _setup_status()

        x_disconnect(alias="testdb")

        mock_dbs.disconnect.assert_called_once_with("testdb")

    def test_disconnect_initial_raises(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        _setup_dbs()
        _setup_exec_log()
        _setup_status()

        with pytest.raises(ErrInfo):
            x_disconnect(alias="initial")

    def test_disconnect_current_switches_to_initial(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        mock_dbs = _setup_dbs()
        mock_dbs.current_alias.return_value = "testdb"
        _setup_exec_log()
        _setup_status()

        x_disconnect(alias="testdb")

        mock_dbs.make_current.assert_called_once_with("initial")
        mock_dbs.disconnect.assert_called_once_with("testdb")

    def test_disconnect_db_in_batch_raises(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        _setup_dbs()
        _setup_exec_log()
        mock_status = _setup_status()
        mock_status.batch.uses_db.return_value = True

        with pytest.raises(ErrInfo):
            x_disconnect(alias="testdb")


# ---------------------------------------------------------------------------
# Tests for x_daoflushdelay
# ---------------------------------------------------------------------------


class TestXDaoFlushDelay:
    """Tests for the DAO FLUSH DELAY metacommand handler."""

    def test_valid_delay(self, minimal_conf):
        from execsql.metacommands.connect import x_daoflushdelay

        x_daoflushdelay(secs="10.0")
        assert minimal_conf.dao_flush_delay_secs == 10.0

    def test_minimum_delay(self, minimal_conf):
        from execsql.metacommands.connect import x_daoflushdelay

        x_daoflushdelay(secs="5.0")
        assert minimal_conf.dao_flush_delay_secs == 5.0

    def test_delay_too_small_raises(self, minimal_conf):
        from execsql.metacommands.connect import x_daoflushdelay

        with pytest.raises(ErrInfo):
            x_daoflushdelay(secs="4.9")
