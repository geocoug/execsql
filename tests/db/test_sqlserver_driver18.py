"""SQL Server connects with ODBC Driver 18, and trusts a self-signed certificate only when told to.

Driver 18 (Microsoft's current driver) encrypts the connection and verifies
the server's certificate by default.  The adapter keeps that default; the
``[connect] trust_server_certificate`` setting, or
``?trust_server_certificate=yes`` on an ``mssql://`` URL, accepts a
certificate the client cannot verify (a self-signed one on a test or
internal server).

``pyodbc`` is a stub that records each connection string.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.cli.dsn import _parse_connection_string
from execsql.exceptions import ConfigError


@pytest.fixture
def connstrs(monkeypatch):
    seen: list[str] = []

    def connect(connstr, **kwargs):
        seen.append(connstr)
        return MagicMock()

    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(connect=connect))
    monkeypatch.setattr(_state, "exec_log", None)
    return seen


def _connect(**kwargs):
    from execsql.db.sqlserver import SqlServerDatabase

    return SqlServerDatabase("dbhost", "db", "u", need_passwd=True, password="p", **kwargs)


def test_driver_18_is_tried_first(connstrs):
    _connect()
    assert connstrs[0].startswith("DRIVER={ODBC Driver 18 for SQL Server};")


def test_the_certificate_is_verified_by_default(connstrs, monkeypatch):
    monkeypatch.setattr(_state, "conf", types.SimpleNamespace(trust_server_certificate=False))
    _connect()
    assert "TrustServerCertificate" not in connstrs[0]


def test_trust_server_certificate_accepts_a_self_signed_one(connstrs):
    _connect(trust_server_certificate=True)
    assert "TrustServerCertificate=yes;" in connstrs[0]


def test_the_config_setting_covers_connections_without_the_argument(connstrs, monkeypatch):
    # CONNECT TO SQLSERVER(...) passes no such argument; the setting applies.
    monkeypatch.setattr(_state, "conf", types.SimpleNamespace(trust_server_certificate=True))
    _connect()
    assert "TrustServerCertificate=yes;" in connstrs[0]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("yes", True), ("TRUE", True), ("1", True), ("no", False), ("0", False)],
)
def test_the_dsn_parameter(value, expected):
    parsed = _parse_connection_string(f"mssql://u:p@host:1433/db?trust_server_certificate={value}")
    assert parsed["trust_server_certificate"] is expected
    assert parsed["db"] == "db"


def test_without_the_dsn_parameter_the_setting_decides():
    assert _parse_connection_string("mssql://u:p@host/db")["trust_server_certificate"] is None


@pytest.mark.parametrize(
    "dsn",
    [
        "mssql://host/db?trust_server_certificat=yes",  # a misspelling is not silently ignored
        "postgresql://host/db?sslmode=require",  # execsql never read this either
        "postgresql://host/db?trust_server_certificate=yes",  # SQL Server only
        "mssql://host/db?trust_server_certificate=maybe",
    ],
)
def test_other_parameters_are_errors(dsn):
    with pytest.raises(ConfigError):
        _parse_connection_string(dsn)


def test_the_config_file_setting(tmp_path):
    from execsql.config import ConfigData

    (tmp_path / "execsql.conf").write_text("[connect]\ntrust_server_certificate = Yes\n")
    assert ConfigData(str(tmp_path), {}).trust_server_certificate is True
    assert ConfigData(str(tmp_path / "missing"), {}).trust_server_certificate is False
