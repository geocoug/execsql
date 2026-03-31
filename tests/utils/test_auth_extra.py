"""Additional tests for execsql.utils.auth — get_password interactive paths."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# GUI manager thread detection path (lines 143-151)
#
# Strategy: set _state.gui_manager_thread to a truthy value to enter the block.
# The code creates a new queue.Queue(), calls gui_manager_queue.put(GuiSpec(...)),
# then blocks on return_queue.get(block=True).
#
# We patch queue.Queue globally (not via execsql.utils.auth because queue is
# imported inside the function body and not bound to the module's namespace).
# The pre-loaded queue makes get() return immediately.
# ---------------------------------------------------------------------------


class TestGetPasswordGuiManagerThreadDetection:
    """Test the block that queries whether a GUI console is running (lines 143-151)."""

    def test_gui_manager_thread_none_skips_queue(self, minimal_conf):
        """When gui_manager_thread is None the console-check block is skipped."""
        mock_manager_queue = MagicMock()

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            patch.object(_state, "gui_manager_queue", mock_manager_queue),
            patch("execsql.utils.auth.getpass.getpass", return_value="direct_pass"),
        ):
            result = get_password("SQLite", "test.db", "admin")
            assert result == "direct_pass"
            mock_manager_queue.put.assert_not_called()

    def test_gui_manager_thread_guispec_import_error_falls_back(self, minimal_conf):
        """If the GuiSpec import raises (gui blocked), the except clause runs and getpass is used."""
        import queue as _q

        pre_loaded = _q.Queue()
        pre_loaded.put({"console_running": True})

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", MagicMock()),
            patch.object(_state, "gui_manager_queue", MagicMock()),
            # Patch the global queue.Queue so get() returns immediately.
            patch("queue.Queue", return_value=pre_loaded),
            # Block the gui module import so GuiSpec raises ImportError.
            patch.dict("sys.modules", {"execsql.utils.gui": None}),
            patch("execsql.utils.auth.getpass.getpass", return_value="fallback_pass"),
        ):
            result = get_password("SQLite", "test.db", "admin")
            assert result == "fallback_pass"

    def test_gui_manager_queue_put_raises_falls_back(self, minimal_conf):
        """An exception on gui_manager_queue.put() is caught; getpass is used."""
        mock_bad_queue = MagicMock()
        mock_bad_queue.put.side_effect = Exception("bad queue")

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", MagicMock()),
            patch.object(_state, "gui_manager_queue", mock_bad_queue),
            patch("execsql.utils.auth.getpass.getpass", return_value="safe_pass"),
        ):
            result = get_password("SQLite", "test.db", "admin")
            assert result == "safe_pass"

    def test_gui_manager_thread_console_not_running_uses_getpass(self, minimal_conf):
        """console_running=False is read from the queue; use_gui stays False → getpass."""
        import queue as _q

        pre_loaded = _q.Queue()
        pre_loaded.put({"console_running": False})

        # Use the real gui module so GuiSpec and QUERY_CONSOLE are importable.
        # gui_manager_queue.put() is a MagicMock no-op; the real return_queue
        # (pre_loaded) already has the response so get() returns immediately.
        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", MagicMock()),
            patch.object(_state, "gui_manager_queue", MagicMock()),
            patch("queue.Queue", return_value=pre_loaded),
            patch("execsql.utils.auth.getpass.getpass", return_value="terminal_pass"),
        ):
            result = get_password("SQLite", "test.db", "admin")
            assert result == "terminal_pass"


# ---------------------------------------------------------------------------
# GUI dialog path via conf.gui_level > 0 (lines 154-184)
#
# Strategy: enter the GUI branch via conf.gui_level > 0 (gui_manager_thread=None
# so the first detection block is always skipped).
#
# To avoid blocking on return_queue.get(block=True) at line 171:
#   - Patch queue.Queue globally to return a pre-loaded queue.
#   - Mock gui_manager_queue.put to be a no-op.
#   - Mock enable_gui, GuiSpec, GUI_DISPLAY from execsql.utils.gui.
#
# The "import failure" tests block execsql.utils.gui in sys.modules → the
# except branch at line 182 runs → getpass is the fallback.
# ---------------------------------------------------------------------------


class TestGetPasswordGuiDialog:
    """Test the GUI dialog branch (lines 154-184)."""

    def test_gui_level_zero_uses_getpass_directly(self, minimal_conf):
        """gui_level == 0 (default) goes straight to the else-branch getpass."""
        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            patch("execsql.utils.auth.getpass.getpass", return_value="plain_pass"),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == "plain_pass"

    def test_gui_level_positive_import_failure_falls_back_to_getpass(self, minimal_conf):
        """When gui_level > 0 but gui import fails, the except branch at 182 runs."""
        minimal_conf.gui_level = 1

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            # Block the gui module so the import inside the try block raises.
            patch.dict("sys.modules", {"execsql.utils.gui": None}),
            patch("execsql.utils.auth.getpass.getpass", return_value="gui_import_fail"),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == "gui_import_fail"

    def test_gui_dialog_success_path(self, minimal_conf):
        """Full GUI success: button=1 and a typed password are returned."""
        minimal_conf.gui_level = 1

        import queue as _q

        dialog_rq = _q.Queue()
        dialog_rq.put({"button": 1, "return_value": "gui_typed_pass"})

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            patch.object(_state, "gui_manager_queue", MagicMock()),
            # All queue.Queue() calls return the same pre-loaded queue.
            patch("queue.Queue", return_value=dialog_rq),
            patch("execsql.utils.gui.enable_gui", MagicMock(), create=True),
            patch("execsql.utils.gui.GuiSpec", MagicMock(return_value=MagicMock()), create=True),
            patch("execsql.utils.gui.GUI_DISPLAY", "display", create=True),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == "gui_typed_pass"
            assert _state.upass == "gui_typed_pass"

    def test_gui_dialog_cancel_halt_calls_exit_now(self, minimal_conf):
        """button=0 + cancel_halt=True triggers exit_now(2, None)."""
        from types import SimpleNamespace

        minimal_conf.gui_level = 1

        import queue as _q

        dialog_rq = _q.Queue()
        dialog_rq.put({"button": 0, "return_value": ""})

        mock_status = SimpleNamespace(cancel_halt=True)

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            patch.object(_state, "gui_manager_queue", MagicMock()),
            patch.object(_state, "status", mock_status),
            patch.object(_state, "exec_log", None),
            patch("queue.Queue", return_value=dialog_rq),
            patch("execsql.utils.gui.enable_gui", MagicMock(), create=True),
            patch("execsql.utils.gui.GuiSpec", MagicMock(return_value=MagicMock()), create=True),
            patch("execsql.utils.gui.GUI_DISPLAY", "display", create=True),
        ):
            mock_exit_now = MagicMock(side_effect=SystemExit(2))
            with (
                patch("execsql.utils.errors.exit_now", mock_exit_now),
                pytest.raises(SystemExit),
            ):
                get_password("PostgreSQL", "mydb", "user1")
            mock_exit_now.assert_called_once_with(2, None)

    def test_gui_dialog_cancel_halt_with_exec_log(self, minimal_conf):
        """exec_log.log_exit_halt is called before exit_now when exec_log is set."""
        from types import SimpleNamespace

        minimal_conf.gui_level = 1

        import queue as _q

        dialog_rq = _q.Queue()
        dialog_rq.put({"button": 0, "return_value": ""})

        mock_status = SimpleNamespace(cancel_halt=True)
        mock_exec_log = MagicMock()

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            patch.object(_state, "gui_manager_queue", MagicMock()),
            patch.object(_state, "status", mock_status),
            patch.object(_state, "exec_log", mock_exec_log),
            patch("queue.Queue", return_value=dialog_rq),
            patch("execsql.utils.gui.enable_gui", MagicMock(), create=True),
            patch("execsql.utils.gui.GuiSpec", MagicMock(return_value=MagicMock()), create=True),
            patch("execsql.utils.gui.GUI_DISPLAY", "display", create=True),
        ):
            mock_exit_now = MagicMock(side_effect=SystemExit(2))
            with (
                patch("execsql.utils.errors.exit_now", mock_exit_now),
                pytest.raises(SystemExit),
            ):
                get_password("PostgreSQL", "mydb", "user1")
            mock_exec_log.log_exit_halt.assert_called_once()

    def test_gui_dialog_cancel_no_cancel_halt_returns_empty_password(self, minimal_conf):
        """button=0 but cancel_halt=False → empty password returned without exit."""
        from types import SimpleNamespace

        minimal_conf.gui_level = 1

        import queue as _q

        dialog_rq = _q.Queue()
        dialog_rq.put({"button": 0, "return_value": ""})

        mock_status = SimpleNamespace(cancel_halt=False)

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            patch.object(_state, "gui_manager_queue", MagicMock()),
            patch.object(_state, "status", mock_status),
            patch("queue.Queue", return_value=dialog_rq),
            patch("execsql.utils.gui.enable_gui", MagicMock(), create=True),
            patch("execsql.utils.gui.GuiSpec", MagicMock(return_value=MagicMock()), create=True),
            patch("execsql.utils.gui.GUI_DISPLAY", "display", create=True),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == ""

    def test_gui_dialog_exception_falls_back_to_getpass(self, minimal_conf):
        """An exception inside the GUI try block (line 157) triggers getpass fallback."""
        minimal_conf.gui_level = 1

        with (
            patch.dict("sys.modules", {"keyring": None}),
            patch.object(_state, "gui_manager_thread", None),
            # enable_gui raises → the except at line 182 runs.
            patch("execsql.utils.gui.enable_gui", side_effect=RuntimeError("no display"), create=True),
            patch("execsql.utils.auth.getpass.getpass", return_value="fallback_from_exc"),
        ):
            result = get_password("PostgreSQL", "mydb", "user1")
            assert result == "fallback_from_exc"
