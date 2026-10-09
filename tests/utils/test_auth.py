"""
Tests for execsql.utils.auth — keyring integration and password helpers.

Covers the keyring lookup/store helpers and the service name builder.
Actual get_password() prompting is not tested (requires interactive input).
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

from execsql.utils.auth import (
    _keyring_delete,
    _keyring_get,
    _keyring_set,
    _keyring_service,
    clear_stored_password,
    password_from_keyring,
)
import execsql.utils.auth as auth_mod


class TestKeyringService:
    def test_with_server_the_name_includes_the_port(self):
        assert _keyring_service("PostgreSQL", "mydb", "pghost") == "execsql/PostgreSQL/pghost:5432/mydb"
        assert _keyring_service("PostgreSQL", "mydb", "pghost", 15432) == "execsql/PostgreSQL/pghost:15432/mydb"

    def test_without_server(self):
        result = _keyring_service("SQLite", "mydb", None)
        assert result == "execsql/SQLite/local/mydb"

    def test_different_dbms(self):
        result = _keyring_service("MySQL", "prod", "db.example.com")
        assert result == "execsql/MySQL/db.example.com:3306/prod"


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


class TestKeyringDelete:
    def test_returns_false_when_keyring_not_installed(self):
        with patch.dict("sys.modules", {"keyring": None}):
            assert _keyring_delete("svc", "user") is False

    def test_returns_false_on_exception(self):
        mock_kr = _make_mock_keyring()
        mock_kr.delete_password.side_effect = Exception("backend unavailable")
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            assert _keyring_delete("svc", "user") is False

    def test_returns_true_on_success(self):
        mock_kr = _make_mock_keyring()
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            assert _keyring_delete("svc", "user") is True
            mock_kr.delete_password.assert_called_once_with("svc", "user")


class TestPasswordFromKeyring:
    def test_a_new_login_starts_false(self):
        auth_mod._login.from_keyring = True
        auth_mod.begin_login()
        assert password_from_keyring() is False

    def test_reflects_this_login(self):
        auth_mod._login.from_keyring = True
        assert password_from_keyring() is True
        auth_mod.begin_login()

    def test_another_thread_has_its_own_answer(self):
        import threading

        auth_mod._login.from_keyring = True
        seen = []
        t = threading.Thread(target=lambda: seen.append(password_from_keyring()))
        t.start()
        t.join(5)
        assert seen == [False]
        auth_mod.begin_login()


class TestClearStoredPassword:
    def test_delegates_to_keyring_delete(self):
        mock_kr = _make_mock_keyring()
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            result = clear_stored_password("PostgreSQL", "mydb", "pguser", "pghost")
            assert result is True
            # The current name, and the pre-port name a default-port connection may have used.
            assert [c.args for c in mock_kr.delete_password.call_args_list] == [
                ("execsql/PostgreSQL/pghost:5432/mydb", "pguser"),
                ("execsql/PostgreSQL/pghost/mydb", "pguser"),
            ]

    def test_a_non_default_port_leaves_the_pre_port_entry_alone(self):
        mock_kr = _make_mock_keyring()
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            clear_stored_password("PostgreSQL", "mydb", "pguser", "pghost", port=15432)
            mock_kr.delete_password.assert_called_once_with("execsql/PostgreSQL/pghost:15432/mydb", "pguser")

    def test_without_server(self):
        mock_kr = _make_mock_keyring()
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            clear_stored_password("DSN", "mydsn", "user")
            mock_kr.delete_password.assert_called_once_with(
                "execsql/DSN/local/mydsn",
                "user",
            )
