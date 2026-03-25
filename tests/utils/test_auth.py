"""
Tests for execsql.utils.auth — keyring integration and password helpers.

Covers the keyring lookup/store helpers and the service name builder.
Actual get_password() prompting is not tested (requires interactive input).
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

from execsql.utils.auth import _keyring_get, _keyring_set, _keyring_service


class TestKeyringService:
    def test_with_server(self):
        result = _keyring_service("PostgreSQL", "mydb", "pghost")
        assert result == "execsql/PostgreSQL/pghost/mydb"

    def test_without_server(self):
        result = _keyring_service("SQLite", "mydb", None)
        assert result == "execsql/SQLite/local/mydb"

    def test_different_dbms(self):
        result = _keyring_service("MySQL", "prod", "db.example.com")
        assert result == "execsql/MySQL/db.example.com/prod"


def _make_mock_keyring(**overrides):
    """Create a fake keyring module with mock get/set/delete_password."""
    mod = types.ModuleType("keyring")
    mod.get_password = MagicMock(return_value=None)
    mod.set_password = MagicMock(return_value=None)
    mod.delete_password = MagicMock(return_value=None)
    for k, v in overrides.items():
        setattr(getattr(mod, k), "return_value", v) if not callable(v) else setattr(getattr(mod, k), "side_effect", v)
    return mod


class TestKeyringGet:
    def test_returns_none_when_keyring_not_installed(self):
        with patch.dict("sys.modules", {"keyring": None}):
            assert _keyring_get("svc", "user") is None

    def test_returns_none_on_exception(self):
        mock_kr = _make_mock_keyring()
        mock_kr.get_password.side_effect = Exception("backend unavailable")
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            assert _keyring_get("svc", "user") is None

    def test_returns_password_when_found(self):
        mock_kr = _make_mock_keyring()
        mock_kr.get_password.return_value = "secret123"
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            assert _keyring_get("svc", "user") == "secret123"

    def test_returns_none_when_not_found(self):
        mock_kr = _make_mock_keyring()
        mock_kr.get_password.return_value = None
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            assert _keyring_get("svc", "user") is None


class TestKeyringSet:
    def test_returns_false_when_keyring_not_installed(self):
        with patch.dict("sys.modules", {"keyring": None}):
            assert _keyring_set("svc", "user", "pass") is False

    def test_returns_false_on_exception(self):
        mock_kr = _make_mock_keyring()
        mock_kr.set_password.side_effect = Exception("backend unavailable")
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            assert _keyring_set("svc", "user", "pass") is False

    def test_returns_true_on_success(self):
        mock_kr = _make_mock_keyring()
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            assert _keyring_set("svc", "user", "pass") is True
            mock_kr.set_password.assert_called_once_with("svc", "user", "pass")
