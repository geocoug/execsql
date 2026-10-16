"""Each pyodbc connection execsql opens is a new database session.

With pyodbc's connection pooling on, closing a connection hands its session
back to the ODBC driver manager, and unixODBC gives it unchanged to the next
connection to the same server: temp tables and ``SET`` options from one
``CONNECT`` or ``execsql.run()`` were still there in the next.  The adapters
turn pooling off before they connect.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from execsql.db.access import AccessDatabase
from execsql.db.dsn import DsnDatabase
from execsql.db.sqlserver import SqlServerDatabase

pytestmark = pytest.mark.usefixtures("fake_drivers")


def _pooling_at_connect() -> list[object]:
    """Make pyodbc.connect record the pooling setting it was called under."""
    pyodbc = sys.modules["pyodbc"]
    pyodbc.pooling = True  # pyodbc's default
    seen: list[object] = []

    def connect(*_args, **_kwargs):
        seen.append(pyodbc.pooling)
        return MagicMock()

    pyodbc.connect = connect
    return seen


def test_sql_server_connects_without_pooling():
    seen = _pooling_at_connect()
    SqlServerDatabase("host", "db", "sa", port=1433, password="pw")
    assert seen == [False]


def test_dsn_connects_without_pooling():
    seen = _pooling_at_connect()
    DsnDatabase("MYDSN", None, need_passwd=False, encoding="utf-8")
    assert seen == [False]


def test_access_connects_without_pooling(tmp_path):
    seen = _pooling_at_connect()
    with patch.object(AccessDatabase, "open_dao", return_value=None):
        AccessDatabase(str(tmp_path / "data.accdb"))
    assert seen == [False]
