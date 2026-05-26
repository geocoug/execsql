"""B10/F069 regression: MySQL identifier-existence checks must honour
the server-level ``@@lower_case_table_names`` (``LCTN``) variable.

* ``LCTN = 0`` (Linux default): names are case-sensitive; the helper
  passes the input through unchanged.
* ``LCTN = 1`` (Windows/macOS default): names are lowercased on
  storage; the helper folds the input to lowercase so a query like
  ``table_exists("MyTable")`` matches a row stored as ``mytable``.
* ``LCTN = 2``: stored as-created but compared case-insensitively;
  same lowercase folding applies.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("pymysql")


def _make_mysql():
    """Construct a MySQLDatabase without triggering open_db()."""
    from execsql.db.mysql import MySQLDatabase

    db = MySQLDatabase.__new__(MySQLDatabase)
    # Minimal attributes the base methods reference.
    db.paramstr = "%s"
    db.conn = None
    return db


@pytest.mark.parametrize(
    "lctn,name,expected",
    [
        (0, "MyTable", "MyTable"),
        (1, "MyTable", "mytable"),
        (2, "MyTable", "mytable"),
        (0, "MIXED_Schema", "MIXED_Schema"),
        (1, "MIXED_Schema", "mixed_schema"),
        (1, None, None),
    ],
)
def test_fold_identifier(lctn, name, expected):
    db = _make_mysql()
    db._cached_lctn = lctn
    assert db._fold_identifier(name) == expected


def test_lower_case_table_names_cached():
    """``_lower_case_table_names`` should query the server once and cache."""
    db = _make_mysql()
    db.select_data = MagicMock(return_value=(["v"], [(1,)]))
    assert db._lower_case_table_names() == 1
    assert db._lower_case_table_names() == 1
    # Only one round-trip to the server, even after repeated calls.
    assert db.select_data.call_count == 1


def test_lower_case_table_names_falls_back_to_zero_on_error():
    db = _make_mysql()
    db.select_data = MagicMock(side_effect=RuntimeError("server gone"))
    assert db._lower_case_table_names() == 0


def test_table_exists_folds_when_case_insensitive():
    """LCTN=1: table_exists("MyTable") queries with table_name='mytable'."""
    db = _make_mysql()
    db._cached_lctn = 1
    captured = {}

    def fake_super_table_exists(self, table_name, schema_name=None):
        captured["table_name"] = table_name
        captured["schema_name"] = schema_name
        return True

    from execsql.db.base import Database

    with patch.object(Database, "table_exists", fake_super_table_exists):
        assert db.table_exists("MyTable", "MyDB") is True
    assert captured == {"table_name": "mytable", "schema_name": "mydb"}


def test_table_exists_passes_through_when_case_sensitive():
    """LCTN=0: table_exists("MyTable") queries with table_name='MyTable'."""
    db = _make_mysql()
    db._cached_lctn = 0
    captured = {}

    def fake_super_table_exists(self, table_name, schema_name=None):
        captured["table_name"] = table_name
        captured["schema_name"] = schema_name
        return False

    from execsql.db.base import Database

    with patch.object(Database, "table_exists", fake_super_table_exists):
        db.table_exists("MyTable", "MyDB")
    assert captured == {"table_name": "MyTable", "schema_name": "MyDB"}


def test_column_view_exists_also_fold():
    """column_exists and view_exists fold identifiers via the same helper.

    MySQL.schema_exists pre-dates this work and always returns False
    (MySQL conflates schema with database), so case-folding it would
    be a no-op anyway — only the three table-level checks are tested.
    """
    db = _make_mysql()
    db._cached_lctn = 1

    from execsql.db.base import Database

    with patch.object(Database, "view_exists", lambda self, v, s=None: (v, s)) as _:
        assert db.view_exists("MyView", "MySchema") == ("myview", "myschema")
    with patch.object(Database, "column_exists", lambda self, t, c, s=None: (t, c, s)) as _:
        assert db.column_exists("MyTable", "MyCol", "MySchema") == ("mytable", "mycol", "myschema")
