"""SQL Server and Access ODBC connection strings: quoted values, the port, a masked log.

An ODBC connection string is ``;``-separated ``KEY=value`` attributes.  A
password with a ``;`` was written as is, so the driver saw the password end
early (the login failed) and the log masking, which stopped at the first
``;``, wrote the rest of the password to the log.  SQL Server also left the
port out of the string, so ``-p 14330`` connected to the default instance
on 1433 with the credentials meant for 14330.

``pyodbc`` is replaced by a stub that records each connection string, so
these run without a driver or a server.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.db.odbc import connection_string, loggable, odbc_value

PASSWORD = "Tr0ub4dor;horse{battery}"


@pytest.fixture
def connstrs(monkeypatch):
    """Install a stub pyodbc; return the list of connection strings it was given."""
    seen: list[str] = []

    def connect(connstr, **kwargs):
        seen.append(connstr)
        return MagicMock()

    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(connect=connect))
    return seen


@pytest.fixture
def log_lines(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(_state, "exec_log", types.SimpleNamespace(log_status_info=lines.append))
    return lines


class TestOdbcValue:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("plain", "plain"),
            ("a;b", "{a;b}"),
            ("{lead", "{{lead}"),
            ("a;b}c", "{a;b}}c}"),
            ("mid}brace", "mid}brace"),
            (14330, "14330"),
        ],
    )
    def test_quotes_only_values_that_need_it(self, value, expected):
        assert odbc_value(value) == expected

    def test_connection_string_and_its_log_form(self):
        attributes = [("SERVER", "h"), ("Uid", "u"), ("Pwd", PASSWORD)]
        assert connection_string("D", attributes) == "DRIVER={D};SERVER=h;Uid=u;Pwd={Tr0ub4dor;horse{battery}}};"
        assert loggable("D", attributes) == "DRIVER={D};SERVER=h;Uid=u;Pwd=***;"


class TestSqlServer:
    def _connect(self, **kwargs):
        from execsql.db.sqlserver import SqlServerDatabase

        return SqlServerDatabase("dbhost", "db", "u", need_passwd=True, password=PASSWORD, **kwargs)

    def test_password_is_one_quoted_attribute(self, connstrs, log_lines):
        self._connect()
        assert "Pwd={Tr0ub4dor;horse{battery}}};" in connstrs[0]

    def test_no_part_of_the_password_is_logged(self, connstrs, log_lines):
        self._connect()
        logged = "\n".join(log_lines)
        assert "Pwd=***;" in logged
        assert "horse" not in logged
        assert "Tr0ub4dor" not in logged

    def test_a_given_port_is_used(self, connstrs, log_lines):
        self._connect(port=14330)
        assert "SERVER=dbhost,14330;" in connstrs[0]

    def test_no_port_keeps_the_server_name_alone(self, connstrs, log_lines):
        # A named instance (host\\instance) is found through SQL Server
        # Browser; adding the default port would bypass it.
        from execsql.db.sqlserver import SqlServerDatabase

        db = SqlServerDatabase("dbhost\\inst", "db", "u", need_passwd=True, password="p")
        assert "SERVER=dbhost\\inst;" in connstrs[0]
        assert db.port == 1433

    def test_a_port_already_in_the_server_name_is_not_added_twice(self, connstrs, log_lines):
        from execsql.db.sqlserver import SqlServerDatabase

        SqlServerDatabase("dbhost,14330", "db", "u", need_passwd=True, password="p", port=14330)
        assert "SERVER=dbhost,14330;" in connstrs[0]

    def test_database_name_cannot_add_attributes(self, connstrs, log_lines):
        from execsql.db.sqlserver import SqlServerDatabase

        SqlServerDatabase("dbhost", "db;Trusted_Connection=yes", "u", need_passwd=True, password="p")
        assert "DATABASE={db;Trusted_Connection=yes};" in connstrs[0]


class TestAccess:
    def _open(self, user="u", password=PASSWORD, db_name="C:/data/x.accdb"):
        from execsql.db.access import AccessDatabase

        db = AccessDatabase.__new__(AccessDatabase)
        db.db_name = db_name
        db.need_passwd = True
        db.user = user
        db.password = password
        db.conn = None
        db.open_db()
        return db

    def test_password_is_one_quoted_attribute(self, connstrs, log_lines):
        self._open()
        assert "Pwd={Tr0ub4dor;horse{battery}}};" in connstrs[0]

    def test_no_part_of_the_password_is_logged(self, connstrs, log_lines):
        self._open()
        logged = "\n".join(log_lines)
        assert "Pwd=***;" in logged
        assert "horse" not in logged
        assert "Tr0ub4dor" not in logged

    def test_file_path_with_a_semicolon_is_quoted(self, connstrs, log_lines, tmp_path):
        path = tmp_path / "a;b.accdb"
        self._open(db_name=str(path))
        assert f"DBQ={{{path.resolve()}}};" in connstrs[0]
