"""``ALIAS_DEFINED``, ``aliased_as`` and ``disconnect`` match the alias case-insensitively.

``CONNECT … AS B`` stores the alias lowercased (``DatabasePool.add``), and
``USE B`` / ``USE b`` both find it.  ``ALIAS_DEFINED`` compared the alias as
written, and ``DatabasePool.aliased_as()`` / ``disconnect()`` took the alias
as given, so the same connection spelled differently was reported undefined
and ``DISCONNECT FROM B`` silently left ``b`` open.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import execsql.state as _state
from execsql.db.base import Database, DatabasePool
from execsql.exceptions import ErrInfo
from execsql.metacommands.conditions import xf_aliasdefined


class FakeDatabase(Database):
    """Minimal Database subclass for testing DatabasePool without a driver."""

    def __init__(self, server=None, db=None):
        super().__init__(server_name=server, db_name=db)
        self.type = SimpleNamespace(dbms_id="fake")
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
    p.add("initial", FakeDatabase(server="s", db="t.db"))
    p.add("b", FakeDatabase(server="s", db="b.db"))
    _state.dbs = p
    yield p
    _state.dbs = None


class TestAliasDefinedCase:
    def test_lowercase_alias_defined(self, pool):
        assert xf_aliasdefined(alias="b") is True

    def test_uppercase_spelling_also_defined(self, pool):
        assert xf_aliasdefined(alias="B") is True

    def test_mixed_case_spelling_also_defined(self, pool):
        p = DatabasePool()
        p.add("AbC", FakeDatabase(server="s", db="x.db"))
        _state.dbs = p
        try:
            assert xf_aliasdefined(alias="aBc") is True
        finally:
            _state.dbs = None

    def test_unknown_alias_not_defined(self, pool):
        assert xf_aliasdefined(alias="nope") is False


class TestAliasedAsCase:
    def test_uppercase_finds_lowercased_alias(self, pool):
        assert pool.aliased_as("B") is pool.pool["b"]

    def test_lowercase_still_works(self, pool):
        assert pool.aliased_as("b") is pool.pool["b"]

    def test_unknown_alias_raises(self, pool):
        with pytest.raises(KeyError):
            pool.aliased_as("nope")


class TestDisconnectCase:
    def test_uppercase_disconnect_closes_lowercased_alias(self, pool):
        db = pool.pool["b"]
        pool.disconnect("B")
        assert "b" not in pool.pool
        assert db.closed

    def test_lowercase_disconnect_still_works(self, pool):
        pool.disconnect("b")
        assert "b" not in pool.pool

    def test_disconnect_unknown_alias_is_a_noop(self, pool):
        pool.disconnect("nope")
        assert "b" in pool.pool

    def test_disconnect_current_database_refused(self, pool):
        with pytest.raises(ErrInfo):
            pool.disconnect("initial")
        assert "initial" in pool.pool
        assert "b" in pool.pool


class TestXDisconnectCurrentCase:
    """``DISCONNECT FROM B`` on the *current* database must switch away first.

    With case-insensitive matching in the pool, an uppercase spelling of the
    current alias would otherwise delete the entry the pool still points at.
    """

    def test_uppercase_disconnect_of_current_switches_to_initial(self, pool):
        from unittest.mock import MagicMock

        from execsql.metacommands.connect import x_disconnect

        _state.status = MagicMock()
        _state.status.batch.uses_db.return_value = False
        _state.exec_log = MagicMock()
        try:
            pool.make_current("b")
            x_disconnect(alias="B")
            assert "b" not in pool.pool
            assert pool.current_alias() == "initial"
            assert pool.pool["initial"].closed is False
        finally:
            _state.status = None
            _state.exec_log = None

    def test_lowercase_disconnect_of_current_switches_to_initial(self, pool):
        from unittest.mock import MagicMock

        from execsql.metacommands.connect import x_disconnect

        _state.status = MagicMock()
        _state.status.batch.uses_db.return_value = False
        _state.exec_log = MagicMock()
        try:
            pool.make_current("b")
            x_disconnect(alias="b")
            assert "b" not in pool.pool
            assert pool.current_alias() == "initial"
        finally:
            _state.status = None
            _state.exec_log = None
