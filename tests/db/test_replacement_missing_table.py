"""TO REPLACEMENT creates the table when there is none to replace, on every DBMS.

SQL Server, Oracle, Firebird and Access have no DROP TABLE IF EXISTS, so
their drop of a missing table failed and IMPORT/COPY ... TO REPLACEMENT
stopped on the first run.  ``drop_table_for_replacement`` accepts that
failure only when the table is confirmed absent.
"""

from __future__ import annotations

import pytest

from execsql.db.base import Database


class _Db(Database):
    """A Database whose drop fails the way SQL Server's does, with a settable table list."""

    def __init__(self, tables, exists_raises=False):
        self.tables = set(tables)
        self.exists_raises = exists_raises
        self.dropped = []

    def open_db(self):  # pragma: no cover - not used
        pass

    def exec_cmd(self, querycommand):  # pragma: no cover - not used
        pass

    def schema_qualified_table_name(self, schema_name, table_name):
        return f"{schema_name}.{table_name}" if schema_name else table_name

    def drop_table(self, tablename):
        if tablename not in self.tables:
            raise RuntimeError(f"Cannot drop the table '{tablename}', because it does not exist (3701)")
        self.dropped.append(tablename)

    def table_exists_where_created(self, table_name, schema_name=None):
        if self.exists_raises:
            raise RuntimeError("cannot read the catalog")
        return self.schema_qualified_table_name(schema_name, table_name) in self.tables


def test_an_existing_table_is_dropped():
    db = _Db({"s.t"})
    db.drop_table_for_replacement("s", "t")
    assert db.dropped == ["s.t"]


def test_a_missing_table_is_not_an_error():
    _Db(set()).drop_table_for_replacement("s", "t")


def test_a_drop_that_fails_on_an_existing_table_still_fails():
    db = _Db({"s.t"})
    db.drop_table = lambda name: (_ for _ in ()).throw(RuntimeError("referenced by a foreign key"))
    with pytest.raises(RuntimeError, match="foreign key"):
        db.drop_table_for_replacement("s", "t")


def test_when_existence_cannot_be_checked_the_drop_error_stands():
    with pytest.raises(RuntimeError, match="3701"):
        _Db(set(), exists_raises=True).drop_table_for_replacement("s", "t")
