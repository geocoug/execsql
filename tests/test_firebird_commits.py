"""Firebird catalog checks and mandatory DDL commits honor transaction boundaries (#138)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import execsql.state as state
from execsql.db.base import Database
from execsql.db.firebird import FirebirdDatabase
from execsql.exceptions import ErrInfo
from execsql.types import dbt_firebird


def _database():
    db = object.__new__(FirebirdDatabase)
    Database.__init__(db, "localhost", "test.fdb", "SYSDBA", port=3050, encoding="UTF8")
    db.type = dbt_firebird
    db.conn = MagicMock()
    db.conn.cursor.return_value.fetchall.return_value = [("PROBE",)]
    return db


@pytest.mark.parametrize(("autocommit", "batch"), [(True, False), (True, True), (False, False), (False, True)])
def test_catalog_check_commits_only_when_nothing_is_held(autocommit, batch):
    db = _database()
    db.autocommit = autocommit
    state.status = SimpleNamespace(batch=SimpleNamespace(in_batch=lambda: batch))
    assert db.table_exists("PROBE")
    assert db.conn.commit.call_count == (1 if autocommit and not batch else 0)


@pytest.mark.parametrize("error", [RuntimeError("commit rejected"), KeyboardInterrupt()])
@pytest.mark.parametrize("operation", ["catalog", "drop", "csv", "rows", "copy"])
def test_every_required_commit_rolls_back_before_raising(tmp_path, error, operation):
    db = _database()
    db.conn.commit.side_effect = error
    db.table_exists = MagicMock(return_value=False)
    db.populate_table = MagicMock()
    state.conf.scan_lines = 100
    if operation != "catalog":
        db.autocommit = False  # Mandatory DDL commits still run with AUTOCOMMIT OFF.

    def act():
        if operation == "catalog":
            return FirebirdDatabase.table_exists(db, "PROBE")
        if operation == "drop":
            return db.drop_table("PROBE")
        if operation == "csv":
            from execsql.importers.csv import importtable

            path = tmp_path / "input.csv"
            path.write_text("V\nloaded\n", encoding="utf-8")
            return importtable(db, None, "PROBE", str(path), 1)
        if operation == "rows":
            from execsql.importers.base import import_data_table

            return import_data_table(db, None, "PROBE", 1, ["V"], [["loaded"]])
        from execsql.metacommands.io_fileops import _copy_rows

        source = MagicMock()
        source.select_rowsource.return_value = (["V"], iter([("loaded",)]))
        return _copy_rows(source, db, "select V from SRC", None, "PROBE", "new")

    # The CSV/row importers retain their existing error wrappers.
    with pytest.raises((RuntimeError, ErrInfo) if isinstance(error, Exception) else type(error)):
        act()
    db.conn.rollback.assert_called_once_with()
    db.populate_table.assert_not_called()


@pytest.mark.parametrize("error", [None, RuntimeError("attach failed"), KeyboardInterrupt(), SystemExit(143)])
def test_connection_uses_supported_driver_options_and_cleans_private_configs(monkeypatch, error):
    driver = pytest.importorskip("firebird.driver")
    config = driver.driver_config
    servers, databases = list(config.servers.value), list(config.databases.value)
    defaults = (config.server_defaults.host.value, config.server_defaults.port.value, config.db_defaults.timeout.value)
    seen = []

    # This signature deliberately accepts only firebird-driver's real keywords.
    def connect(database, *, user=None, password=None, charset=None):
        db_config = config.get_database(database)
        server = config.get_server(db_config.server.value)
        seen.append(
            (server.host.value, server.port.value, db_config.database.value, db_config.timeout.value, user, charset),
        )
        if error is not None:
            raise error
        return MagicMock()

    monkeypatch.setattr(driver, "connect", connect)
    if error is None:
        db = FirebirdDatabase("example.test", "/data/test.fdb", "reader", password="test", port=3405, encoding="UTF8")
        assert db.password is None
        db.close()
    else:
        with pytest.raises(ErrInfo if isinstance(error, Exception) else type(error)):
            FirebirdDatabase("example.test", "/data/test.fdb", "reader", password="test", port=3405, encoding="UTF8")
    assert seen == [("example.test", "3405", "/data/test.fdb", 30, "reader", "UTF8")]
    assert config.servers.value == servers
    assert config.databases.value == databases
    assert defaults == (
        config.server_defaults.host.value,
        config.server_defaults.port.value,
        config.db_defaults.timeout.value,
    )
