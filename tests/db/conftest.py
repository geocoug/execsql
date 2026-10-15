"""Fixtures shared by the database adapter tests."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_drivers(monkeypatch):
    """Stand-in driver modules, installed for each test and removed after it.

    The adapters import their drivers inside the methods that use them, so
    the stand-ins are needed only while a test runs; installed for the whole
    session they would also replace a real driver that later tests use.
    """
    oracledb = types.ModuleType("oracledb")
    oracledb.connect = MagicMock()
    oracledb.makedsn = MagicMock(return_value="fake_dsn")
    pyodbc = types.ModuleType("pyodbc")
    pyodbc.connect = MagicMock()
    pyodbc.Binary = MagicMock(side_effect=lambda d: d)
    firebird = types.ModuleType("firebird")
    firebird_driver = types.ModuleType("firebird.driver")
    firebird_driver.connect = MagicMock()
    firebird.driver = firebird_driver
    win32com = types.ModuleType("win32com")
    win32com_client = types.ModuleType("win32com.client")
    win32com_client.Dispatch = MagicMock()
    win32com.client = win32com_client
    for name, module in {
        "oracledb": oracledb,
        "pyodbc": pyodbc,
        "firebird": firebird,
        "firebird.driver": firebird_driver,
        "win32com": win32com,
        "win32com.client": win32com_client,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
