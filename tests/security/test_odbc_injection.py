"""ODBC DSN attribute-injection regression test for B06.

Covers audit finding F005 (`db/dsn.py:73-83`): the f-string connection
string allowed a malicious password value to inject ODBC attributes
(CWE-91 — connection-string injection). After the fix, every user-
supplied value is brace-quoted with ``{…}`` and embedded ``}``
doubled, so injected ``;`` separators land inside a quoted literal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# pyodbc is not installed on every CI runner; skip cleanly when absent.
pytest.importorskip("pyodbc")


@pytest.fixture
def fake_pyodbc(monkeypatch):
    """Replace pyodbc.connect with a recorder; return the recorder."""
    import pyodbc

    fake = MagicMock()
    fake.return_value = MagicMock()  # the returned connection
    monkeypatch.setattr(pyodbc, "connect", fake)
    return fake


def _make_db(db_name: str, user: str | None = None, password: str | None = None, need_pwd: bool = False):
    """Construct a DsnDatabase without triggering open_db()."""
    from execsql.db.dsn import DsnDatabase

    db = DsnDatabase.__new__(DsnDatabase)
    db.db_name = db_name
    db.user = user
    db.password = password
    db.need_passwd = need_pwd
    db.port = None
    db.encoding = None
    db.conn = None
    db.curs = None
    return db


def _split_odbc_attrs(connstr: str) -> list[tuple[str, str]]:
    """Parse an ODBC connection string into (name, value) pairs, honouring
    ``{…}`` brace-quoting and ``}}`` escapes within braces.

    Used by the assertions below to verify that injected ``;`` inside a
    value never escapes the brace literal to become a top-level attribute.
    """
    out: list[tuple[str, str]] = []
    i = 0
    n = len(connstr)
    while i < n:
        # Find the next '=' (attribute name terminator) outside braces
        eq = connstr.find("=", i)
        if eq == -1:
            break
        name = connstr[i:eq]
        # Parse value: either ``{…}`` (with ``}}`` escapes) or up to next ``;``
        j = eq + 1
        if j < n and connstr[j] == "{":
            # Brace-quoted value
            k = j + 1
            while k < n:
                if connstr[k] == "}":
                    if k + 1 < n and connstr[k + 1] == "}":
                        k += 2  # escaped }}
                    else:
                        break  # closing brace
                else:
                    k += 1
            value = connstr[j + 1 : k].replace("}}", "}")
            i = k + 1
            if i < n and connstr[i] == ";":
                i += 1
        else:
            semi = connstr.find(";", j)
            if semi == -1:
                semi = n
            value = connstr[j:semi]
            i = semi + 1
        out.append((name, value))
    return out


class TestOdbcConnstrInjection:
    def test_password_with_semicolon_is_quoted(self, fake_pyodbc):
        """A password containing ``;Driver=…`` must not append a Driver attribute."""
        db = _make_db("mydsn", user="alice", password="pwd;Driver={Evil};", need_pwd=True)
        db.open_db()
        connstr = fake_pyodbc.call_args[0][0]
        attrs = dict(_split_odbc_attrs(connstr))
        # Exactly three top-level attributes — no injected Driver=… or extra PWD=
        assert set(attrs.keys()) == {"DSN", "UID", "PWD"}
        assert "Driver" not in attrs
        # The password value round-trips intact (semicolons stayed inside the brace literal).
        assert attrs["PWD"] == "pwd;Driver={Evil};"

    def test_brace_in_password_is_escaped(self, fake_pyodbc):
        """A password containing ``}`` is escaped to ``}}`` so the brace literal terminates correctly."""
        db = _make_db("mydsn", user="alice", password="pa}ss", need_pwd=True)
        db.open_db()
        connstr = fake_pyodbc.call_args[0][0]
        attrs = dict(_split_odbc_attrs(connstr))
        assert attrs["PWD"] == "pa}ss"

    def test_dsn_name_with_special_chars_is_quoted(self, fake_pyodbc):
        """The DSN name itself is brace-quoted even when innocuous."""
        db = _make_db("my;dsn=hijack", user=None, password=None, need_pwd=False)
        db.open_db()
        connstr = fake_pyodbc.call_args[0][0]
        attrs = dict(_split_odbc_attrs(connstr))
        assert attrs == {"DSN": "my;dsn=hijack"}

    def test_user_with_semicolon_is_quoted(self, fake_pyodbc):
        """A user containing ``;`` cannot inject extra attributes."""
        db = _make_db("mydsn", user="alice;Pwd=hacked", password="real", need_pwd=True)
        db.open_db()
        connstr = fake_pyodbc.call_args[0][0]
        attrs = dict(_split_odbc_attrs(connstr))
        # Exactly one PWD top-level attribute — the injected ``Pwd=hacked`` lives inside UID.
        assert attrs["UID"] == "alice;Pwd=hacked"
        assert attrs["PWD"] == "real"
        # No injected attributes leaked at top level.
        assert set(attrs.keys()) == {"DSN", "UID", "PWD"}

    def test_no_password_path(self, fake_pyodbc):
        """When need_passwd is False, no UID/PWD attributes are emitted."""
        db = _make_db("mydsn", need_pwd=False)
        db.open_db()
        connstr = fake_pyodbc.call_args[0][0]
        assert connstr == "DSN={mydsn};"
