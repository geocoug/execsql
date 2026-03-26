"""Additional tests for execsql.utils.auth — get_password interactive paths."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import execsql.state as _state
import execsql.utils.auth as auth_mod
from execsql.utils.auth import get_password


class TestGetPasswordKeyringHit:
    def test_returns_stored_password(self, minimal_conf):
        mock_kr = types.ModuleType("keyring")
        mock_kr.get_password = MagicMock(return_value="stored_pass")
        mock_kr.set_password = MagicMock()
        mock_kr.delete_password = MagicMock()

        with patch.dict("sys.modules", {"keyring": mock_kr}):
            result = get_password("PostgreSQL", "mydb", "user1", "localhost")
            assert result == "stored_pass"
            assert auth_mod._last_from_keyring is True
            assert _state.upass == "stored_pass"

    def test_skip_keyring_bypasses_lookup(self, minimal_conf):
        mock_kr = types.ModuleType("keyring")
        mock_kr.get_password = MagicMock(return_value="stored_pass")
        mock_kr.set_password = MagicMock()
        mock_kr.delete_password = MagicMock()

        with (
            patch.dict("sys.modules", {"keyring": mock_kr}),
            patch("execsql.utils.auth.getpass.getpass", return_value="typed_pass"),
        ):
            result = get_password("PostgreSQL", "mydb", "user1", skip_keyring=True)
            assert result == "typed_pass"
            mock_kr.get_password.assert_not_called()


class TestGetPasswordInteractive:
    def test_prompts_with_getpass(self, minimal_conf):
        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch("execsql.utils.auth.getpass.getpass", return_value="my_password") as mock_gp,
        ):
            result = get_password("SQLite", "test.db", "admin")
            assert result == "my_password"
            assert _state.upass == "my_password"
            mock_gp.assert_called_once()

    def test_prompt_includes_server_name(self, minimal_conf):
        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch("execsql.utils.auth.getpass.getpass", return_value="pw") as mock_gp,
        ):
            get_password("PostgreSQL", "mydb", "user1", "pghost.example.com")
            prompt = mock_gp.call_args[0][0]
            assert "pghost.example.com" in prompt

    def test_prompt_includes_other_msg(self, minimal_conf):
        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch("execsql.utils.auth.getpass.getpass", return_value="pw") as mock_gp,
        ):
            get_password("PostgreSQL", "mydb", "user1", other_msg="Extra info")
            prompt = mock_gp.call_args[0][0]
            assert "Extra info" in prompt

    def test_stores_in_keyring_after_prompt(self, minimal_conf):
        mock_kr = types.ModuleType("keyring")
        mock_kr.get_password = MagicMock(return_value=None)
        mock_kr.set_password = MagicMock()
        mock_kr.delete_password = MagicMock()

        with (
            patch.dict("sys.modules", {"keyring": mock_kr}),
            patch("execsql.utils.auth.getpass.getpass", return_value="new_pass"),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == "new_pass"
            mock_kr.set_password.assert_called_once()

    def test_empty_password_not_stored_in_keyring(self, minimal_conf):
        mock_kr = types.ModuleType("keyring")
        mock_kr.get_password = MagicMock(return_value=None)
        mock_kr.set_password = MagicMock()
        mock_kr.delete_password = MagicMock()

        with (
            patch.dict("sys.modules", {"keyring": mock_kr}),
            patch("execsql.utils.auth.getpass.getpass", return_value=""),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == ""
            mock_kr.set_password.assert_not_called()

    def test_use_keyring_false_skips_lookup(self, minimal_conf):
        minimal_conf.use_keyring = False
        mock_kr = types.ModuleType("keyring")
        mock_kr.get_password = MagicMock(return_value="stored")
        mock_kr.set_password = MagicMock()
        mock_kr.delete_password = MagicMock()

        with (
            patch.dict("sys.modules", {"keyring": mock_kr}),
            patch("execsql.utils.auth.getpass.getpass", return_value="typed"),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == "typed"
            mock_kr.get_password.assert_not_called()
