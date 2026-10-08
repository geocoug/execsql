"""The Oracle adapter uses python-oracledb, the driver ``execsql2[oracle]`` installs.

The adapter imported ``cx_Oracle``, the legacy driver that oracledb replaced
and that ships no wheels for Python 3.12+, so a documented install could not
connect at all.  The mocked adapter tests injected a fake ``cx_Oracle`` and
never noticed.  ``cx_Oracle`` is still used if it is the only driver
installed.
"""

from __future__ import annotations

import importlib.metadata
import socket
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from execsql.exceptions import ErrInfo


def _fake_driver(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.makedsn = MagicMock(return_value=f"{name}-dsn")
    mod.connect = MagicMock(return_value=MagicMock())
    return mod


def _open(**kwargs):
    from execsql.db.oracle import OracleDatabase

    return OracleDatabase("orasrv", "orcl", "scott", port=1521, password="tiger", **kwargs)


def test_connects_with_oracledb():
    oracledb = _fake_driver("oracledb")
    with patch.dict(sys.modules, {"oracledb": oracledb, "cx_Oracle": None}):
        _open()
    oracledb.makedsn.assert_called_once_with("orasrv", 1521, service_name="orcl")
    oracledb.connect.assert_called_once_with(user="scott", password="tiger", dsn="oracledb-dsn")


def test_falls_back_to_cx_oracle_when_it_is_the_only_driver():
    cx_oracle = _fake_driver("cx_Oracle")
    with patch.dict(sys.modules, {"oracledb": None, "cx_Oracle": cx_oracle}):
        _open()
    cx_oracle.connect.assert_called_once_with(user="scott", password="tiger", dsn="cx_Oracle-dsn")


def test_no_driver_points_at_the_oracle_extra():
    def stop(msg):
        raise RuntimeError(msg)

    with (
        patch.dict(sys.modules, {"oracledb": None, "cx_Oracle": None}),
        patch("execsql.db.oracle.fatal_error", side_effect=stop),
        pytest.raises(RuntimeError) as exc_info,
    ):
        _open()
    assert "oracledb" in str(exc_info.value)
    assert "execsql2[oracle]" in str(exc_info.value)


def test_installed_oracledb_gets_as_far_as_the_network():
    """Unmocked: with the real driver, a refused connection is a connect error, not a missing module."""
    # Ask the installed packages, not sys.modules: without the driver, other
    # test modules leave a stand-in oracledb there, and importorskip accepts it.
    try:
        importlib.metadata.version("oracledb")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("oracledb is not installed")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
    from execsql.db.oracle import OracleDatabase

    with pytest.raises(ErrInfo) as exc_info:
        OracleDatabase("127.0.0.1", "orcl", "scott", port=closed_port, password="tiger")
    assert "Failed to open Oracle database orcl" in exc_info.value.errmsg()
