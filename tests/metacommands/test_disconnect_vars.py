"""A ``DISCONNECT`` of the current database updates the ``$CURRENT_*`` variables.

``x_disconnect`` calls ``make_current("initial")`` but left ``$CURRENT_DATABASE``,
``$CURRENT_DBMS`` and ``$DB_SERVER`` pointing at the database it just closed, and
the log's connection record untouched. ``x_use`` sets all three; the updates are
shared, so the variables always name the database in use.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.db.base import Database, DatabasePool
from execsql.exceptions import ErrInfo
from execsql.metacommands.connect import x_disconnect, x_use


class FakeDatabase(Database):
    """Minimal Database subclass for testing DatabasePool without a driver."""

    def __init__(self, server=None, db=None, dbms="fake"):
        super().__init__(server_name=server, db_name=db)
        self.type = SimpleNamespace(dbms_id=dbms)
        self.closed = False

    def open_db(self):
        pass

    def exec_cmd(self, querycommand):
        pass

    def close(self):
        self.closed = True

    def rollback(self):
        pass


@pytest.fixture
def pool():
    p = DatabasePool()
    p.add("initial", FakeDatabase(server="srv0", db="t.db", dbms="SQLite"))
    p.add("c", FakeDatabase(server="srv1", db="c.db", dbms="Postgres"))
    _state.dbs = p
    _state.subvars = MagicMock()
    _state.status = MagicMock()
    _state.status.batch.uses_db.return_value = False
    _state.exec_log = MagicMock()
    yield p
    _state.dbs = None
    _state.subvars = None
    _state.status = None
    _state.exec_log = None


def _set_vars(calls):
    return {args[0]: args[1] for args, _ in calls}


class TestUseSetsVars:
    def test_use_sets_current_database_vars(self, pool):
        x_use(db_alias="c", metacommandline="USE c")
        assert _state.dbs.current_alias() == "c"
        vars_set = _set_vars(_state.subvars.add_substitution.call_args_list)
        assert vars_set["$CURRENT_DBMS"] == "Postgres"
        assert vars_set["$CURRENT_DATABASE"] == "Postgres(server srv1; database c.db)"
        assert vars_set["$DB_SERVER"] == "srv1"


class TestDisconnectUpdatesVars:
    def test_disconnect_switches_vars_to_initial(self, pool):
        x_use(db_alias="c", metacommandline="USE c")
        _state.subvars.add_substitution.reset_mock()
        x_disconnect(alias=None)
        assert _state.dbs.current_alias() == "initial"
        assert "c" not in _state.dbs.aliases()
        vars_set = _set_vars(_state.subvars.add_substitution.call_args_list)
        assert vars_set["$CURRENT_DBMS"] == "SQLite"
        assert vars_set["$CURRENT_DATABASE"] == "SQLite(server srv0; database t.db)"
        assert vars_set["$DB_SERVER"] == "srv0"

    def test_disconnect_logs_the_connection_record(self, pool):
        x_use(db_alias="c", metacommandline="USE c")
        _state.exec_log.log_db_connect.reset_mock()
        x_disconnect(alias=None)
        _state.exec_log.log_db_connect.assert_called_once_with(_state.dbs.pool["initial"])

    def test_disconnect_of_non_current_leaves_vars(self, pool):
        # The current database is 'initial'; disconnecting another alias
        # must not touch the variables.
        x_disconnect(alias="c")
        _state.subvars.add_substitution.assert_not_called()
        assert _state.dbs.current_alias() == "initial"
        assert "c" not in _state.dbs.aliases()

    def test_disconnect_refuses_initial(self, pool):
        with pytest.raises(ErrInfo):
            x_disconnect(alias=None)
