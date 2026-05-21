"""Extended structural coverage for execsql.gui.tui and execsql.gui.desktop.

These tests focus on the *backend* methods and the *sync queue* classes
(``_TextualSyncQueue`` / ``_TkinterSyncQueue``) — code paths that don't
require a real Textual Pilot or Tk display to exercise.

For each backend:
- The ``show_*`` dispatchers are exercised by patching the underlying
  ``_run`` / ``_run_dialog`` helper, so we cover all 13 dispatcher
  branches without instantiating any real dialog.
- The console lifecycle methods (``console_on/off/status/progress/save``)
  are exercised by attaching a MagicMock console.
- The sync queue ``put()`` paths are exercised end-to-end with a fake
  spec + return queue: QUERY_CONSOLE, unknown gui_type, runtime exception,
  cancellation→SystemExit, and the happy path.
"""

from __future__ import annotations

import queue as _stdlib_queue
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSpec:
    """Minimal stand-in for execsql.utils.gui.GuiSpec."""

    def __init__(self, gui_type: str, args: dict | None = None) -> None:
        self.gui_type = gui_type
        self.args = args or {}
        self.return_queue = _stdlib_queue.Queue()


# ---------------------------------------------------------------------------
# TextualBackend show_* dispatchers (gui/tui.py)
# ---------------------------------------------------------------------------


class TestTextualBackendShowMethods:
    """Patch _run so we don't actually launch a Textual app."""

    @pytest.fixture
    def backend(self):
        textual_mod = pytest.importorskip("textual")  # noqa: F841
        from execsql.gui.tui import TextualBackend

        return TextualBackend()

    @pytest.mark.parametrize(
        "method,screen_attr",
        [
            ("show_halt", "MsgScreen"),
            ("show_msg", "MsgScreen"),
            ("show_pause", "PauseScreen"),
            ("show_display", "DisplayScreen"),
            ("show_entry_form", "EntryFormScreen"),
            ("show_compare", "CompareScreen"),
            ("show_select_rows", "SelectRowsScreen"),
            ("show_select_sub", "SelectSubScreen"),
            ("show_action", "ActionScreen"),
            ("show_map", "MapScreen"),
            ("show_open_file", "OpenFileScreen"),
            ("show_save_file", "SaveFileScreen"),
            ("show_directory", "DirectoryScreen"),
            ("show_credentials", "CredentialsScreen"),
            ("show_connect", "ConnectScreen"),
        ],
    )
    def test_show_method_delegates_to_run(self, backend, method, screen_attr) -> None:
        import execsql.gui.tui as tui_mod

        with patch.object(backend, "_run", return_value={"button": 1}) as mock_run:
            args = {"message": "x"}
            result = getattr(backend, method)(args)
        mock_run.assert_called_once()
        called_screen = mock_run.call_args[0][0]
        assert called_screen is getattr(tui_mod, screen_attr)
        assert result == {"button": 1}

    def test_run_returns_empty_dict_when_app_returns_none(self, backend) -> None:
        from execsql.gui.tui import MsgScreen

        with patch("execsql.gui.tui._SingleDialogApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            out = backend._run(MsgScreen, {"message": "x"})
        assert out == {}

    def test_query_console_returns_running_flag(self, backend) -> None:
        backend._console_running = True
        assert backend.query_console({}) == {"console_running": True}

    def test_console_on_off(self, backend) -> None:
        backend.console_on()
        assert backend._console_running is True
        # console_off requires _state.output reset; install a mock
        import execsql.state as _state

        _state.output = MagicMock()
        backend.console_off()
        assert backend._console_running is False
        _state.output.reset.assert_called_once()

    def test_console_status_delegates(self, backend) -> None:
        backend._console_app = MagicMock()
        backend.console_status("hello")
        backend._console_app.set_status.assert_called_once_with("hello")

    def test_console_progress_with_total(self, backend) -> None:
        backend._console_app = MagicMock()
        backend.console_progress(25, total=100)
        backend._console_app.set_progress.assert_called_once_with(25.0)

    def test_console_progress_no_total(self, backend) -> None:
        backend._console_app = MagicMock()
        backend.console_progress(50)
        backend._console_app.set_progress.assert_called_once_with(50)

    def test_console_save_delegates(self, backend) -> None:
        backend._console_app = MagicMock()
        backend.console_save("/tmp/out.txt", append=True)
        backend._console_app.save.assert_called_once_with("/tmp/out.txt", True)

    def test_console_hide_noop(self, backend) -> None:
        backend.console_hide()  # noop

    def test_console_show_noop(self, backend) -> None:
        backend.console_show()  # noop

    def test_console_wait_user_noop(self, backend) -> None:
        backend.console_wait_user("done")  # noop

    def test_console_methods_without_app_noop(self, backend) -> None:
        backend._console_app = None
        backend.console_status("x")
        backend.console_progress(5, 10)
        backend.console_save("/tmp")


# ---------------------------------------------------------------------------
# _TextualSyncQueue / _ConsoleDialogQueue (gui/tui.py)
# ---------------------------------------------------------------------------


class TestTextualSyncQueue:
    @pytest.fixture
    def queue(self):
        pytest.importorskip("textual")
        from execsql.gui.tui import _TextualSyncQueue

        return _TextualSyncQueue()

    def test_put_none_is_noop(self, queue) -> None:
        queue.put(None)  # must not raise

    def test_query_console_responds_immediately(self, queue) -> None:
        from execsql.utils.gui import QUERY_CONSOLE

        spec = _FakeSpec(QUERY_CONSOLE)
        queue.put(spec)
        resp = spec.return_queue.get_nowait()
        assert resp == {"console_running": False}

    def test_unknown_type_returns_error(self, queue) -> None:
        spec = _FakeSpec("bogus_kind")
        queue.put(spec)
        resp = spec.return_queue.get_nowait()
        assert "error" in resp
        assert resp["button"] is None

    def test_exception_in_run_returns_error(self, queue) -> None:
        spec = _FakeSpec("msg", {"message": "hi"})
        with patch("execsql.gui.tui._SingleDialogApp") as mock_app:
            mock_app.return_value.run.side_effect = RuntimeError("boom")
            queue.put(spec)
        resp = spec.return_queue.get_nowait()
        assert "error" in resp
        assert "boom" in resp["error"]

    def test_cancelled_result_raises_system_exit(self, queue) -> None:
        spec = _FakeSpec("msg", {"message": "hi"})
        with patch("execsql.gui.tui._SingleDialogApp") as mock_app:
            mock_app.return_value.run.return_value = {"cancelled": True}
            with pytest.raises(SystemExit) as exc:
                queue.put(spec)
        assert exc.value.code == 2

    def test_happy_path_puts_result(self, queue) -> None:
        spec = _FakeSpec("msg", {"message": "hi"})
        with patch("execsql.gui.tui._SingleDialogApp") as mock_app:
            mock_app.return_value.run.return_value = {"button": 1}
            queue.put(spec)
        assert spec.return_queue.get_nowait() == {"button": 1}

    def test_get_methods_raise_empty(self, queue) -> None:
        with pytest.raises(_stdlib_queue.Empty):
            queue.get_nowait()
        with pytest.raises(_stdlib_queue.Empty):
            queue.get()


class TestConsoleDialogQueue:
    @pytest.fixture
    def cdq(self):
        pytest.importorskip("textual")
        from execsql.gui.tui import _ConsoleDialogQueue

        return _ConsoleDialogQueue()

    def test_put_get(self, cdq) -> None:
        spec = _FakeSpec("msg")
        cdq.put(spec)
        assert cdq.get_nowait() is spec

    def test_put_none_skipped(self, cdq) -> None:
        cdq.put(None)
        with pytest.raises(_stdlib_queue.Empty):
            cdq.get_nowait()

    def test_get_blocking(self, cdq) -> None:
        spec = _FakeSpec("msg")
        cdq.put(spec)
        assert cdq.get(block=True, timeout=0.1) is spec


# ---------------------------------------------------------------------------
# TkinterBackend show_* dispatchers (gui/desktop.py)
# ---------------------------------------------------------------------------


class TestTkinterBackendShowMethods:
    """Patch _run_dialog so we don't actually open real Tk windows."""

    @pytest.fixture
    def backend(self):
        # Skip if tkinter is unavailable on this platform
        pytest.importorskip("tkinter")
        from execsql.gui.desktop import TkinterBackend

        b = TkinterBackend()
        # Don't actually call start() — we never need a real root.
        return b

    @pytest.mark.parametrize(
        "method,dialog_attr",
        [
            ("show_halt", "MsgDialog"),
            ("show_msg", "MsgDialog"),
            ("show_pause", "PauseDialog"),
            ("show_display", "DisplayDialog"),
            ("show_entry_form", "EntryFormDialog"),
            ("show_compare", "CompareDialog"),
            ("show_select_rows", "SelectRowsDialog"),
            ("show_select_sub", "SelectSubDialog"),
            ("show_action", "ActionDialog"),
            ("show_map", "MapDialog"),
            ("show_credentials", "CredentialsDialog"),
            ("show_connect", "ConnectDialog"),
        ],
    )
    def test_show_method_delegates(self, backend, method, dialog_attr) -> None:
        import execsql.gui.desktop as desk_mod

        with patch.object(backend, "_run_dialog", return_value={"button": 1}) as mock_run:
            result = getattr(backend, method)({"message": "x"})
        mock_run.assert_called_once()
        called_class = mock_run.call_args[0][0]
        assert called_class is getattr(desk_mod, dialog_attr)
        assert result == {"button": 1}

    def test_show_open_file(self, backend) -> None:
        with (
            patch.object(backend, "_root_or_raise", return_value=MagicMock()),
            patch("execsql.gui.desktop.filedialog") as fd,
        ):
            fd.askopenfilename.return_value = "/tmp/a.csv"
            result = backend.show_open_file({"working_dir": "/tmp"})
        assert result == {"filename": "/tmp/a.csv"}

    def test_show_open_file_cancel(self, backend) -> None:
        with (
            patch.object(backend, "_root_or_raise", return_value=MagicMock()),
            patch("execsql.gui.desktop.filedialog") as fd,
        ):
            fd.askopenfilename.return_value = ""
            result = backend.show_open_file({})
        assert result == {"filename": None}

    def test_show_save_file(self, backend) -> None:
        with (
            patch.object(backend, "_root_or_raise", return_value=MagicMock()),
            patch("execsql.gui.desktop.filedialog") as fd,
        ):
            fd.asksaveasfilename.return_value = "/tmp/save.csv"
            result = backend.show_save_file({"working_dir": "/tmp"})
        assert result == {"filename": "/tmp/save.csv"}

    def test_show_directory(self, backend) -> None:
        with (
            patch.object(backend, "_root_or_raise", return_value=MagicMock()),
            patch("execsql.gui.desktop.filedialog") as fd,
        ):
            fd.askdirectory.return_value = "/tmp/sub"
            result = backend.show_directory({"working_dir": "/tmp"})
        assert result == {"directory": "/tmp/sub"}

    def test_query_console_no_console(self, backend) -> None:
        backend._console = None
        assert backend.query_console({}) == {"console_running": False}

    def test_query_console_running(self, backend) -> None:
        console = MagicMock()
        console.is_running.return_value = True
        backend._console = console
        assert backend.query_console({}) == {"console_running": True}

    def test_console_status_delegates(self, backend) -> None:
        backend._console = MagicMock()
        backend.console_status("running")
        backend._console.set_status.assert_called_once_with("running")

    def test_console_progress_with_total(self, backend) -> None:
        backend._console = MagicMock()
        backend.console_progress(50, 100)
        backend._console.set_progress.assert_called_once_with(50.0)

    def test_console_progress_no_total(self, backend) -> None:
        backend._console = MagicMock()
        backend.console_progress(75)
        backend._console.set_progress.assert_called_once_with(75)

    def test_console_save_delegates(self, backend) -> None:
        backend._console = MagicMock()
        backend.console_save("/tmp/log.txt", append=False)
        backend._console.save.assert_called_once_with("/tmp/log.txt", False)

    def test_console_hide_with_window(self, backend) -> None:
        console = MagicMock()
        win = MagicMock()
        console._win = win
        backend._console = console
        backend.console_hide()
        win.withdraw.assert_called_once()

    def test_console_show_with_window(self, backend) -> None:
        console = MagicMock()
        win = MagicMock()
        console._win = win
        backend._console = console
        backend.console_show()
        win.deiconify.assert_called_once()

    def test_console_methods_without_console_noop(self, backend) -> None:
        backend._console = None
        backend.console_status("x")
        backend.console_progress(1, 2)
        backend.console_save("/tmp")
        backend.console_hide()
        backend.console_show()


# ---------------------------------------------------------------------------
# _TkinterSyncQueue (gui/desktop.py)
# ---------------------------------------------------------------------------


class TestTkinterSyncQueue:
    @pytest.fixture
    def queue(self):
        pytest.importorskip("tkinter")
        from execsql.gui.desktop import _TkinterSyncQueue

        backend = MagicMock()
        backend._root = None
        backend.query_console.return_value = {"console_running": False}
        return _TkinterSyncQueue(backend), backend

    def test_put_none_is_noop(self, queue) -> None:
        q, _ = queue
        q.put(None)

    def test_query_console_routes_to_backend(self, queue) -> None:
        from execsql.utils.gui import QUERY_CONSOLE

        q, backend = queue
        spec = _FakeSpec(QUERY_CONSOLE)
        q.put(spec)
        assert spec.return_queue.get_nowait() == {"console_running": False}
        backend.query_console.assert_called_once()

    def test_dispatch_success_returns_result(self, queue) -> None:
        q, backend = queue
        backend.dispatch.return_value = {"button": 1}
        spec = _FakeSpec("msg", {"message": "hi"})
        q.put(spec)
        assert spec.return_queue.get_nowait() == {"button": 1}

    def test_exception_in_dispatch_returns_error(self, queue) -> None:
        # Use "openfile" — not in _EXIT_ON_CANCEL — so the None-button error
        # result doesn't trip the cancel-halt SystemExit branch.
        q, backend = queue
        backend.dispatch.side_effect = RuntimeError("boom")
        spec = _FakeSpec("openfile", {})
        q.put(spec)
        resp = spec.return_queue.get_nowait()
        assert "error" in resp and "boom" in resp["error"]

    def test_cancel_triggers_system_exit(self, queue) -> None:
        q, backend = queue
        backend.dispatch.return_value = {"button": None}
        spec = _FakeSpec("msg", {"message": "hi"})
        with pytest.raises(SystemExit) as exc:
            q.put(spec)
        assert exc.value.code == 2

    def test_no_exit_for_filedialog_cancel(self, queue) -> None:
        """File/directory dialogs return button=None on cancel but should not exit."""
        q, backend = queue
        backend.dispatch.return_value = {"filename": None, "button": None}
        spec = _FakeSpec("openfile", {})
        q.put(spec)  # must not raise
        assert spec.return_queue.get_nowait()["filename"] is None

    def test_root_update_swallows_exception(self, queue) -> None:
        q, backend = queue
        backend.dispatch.return_value = {"button": 1}
        root = MagicMock()
        root.update.side_effect = RuntimeError("loop torn down")
        backend._root = root
        spec = _FakeSpec("msg", {"message": "hi"})
        q.put(spec)  # error swallowed
        assert spec.return_queue.get_nowait() == {"button": 1}

    def test_get_methods_raise_empty(self, queue) -> None:
        import queue as _q

        q, _ = queue
        with pytest.raises(_q.Empty):
            q.get_nowait()
        with pytest.raises(_q.Empty):
            q.get()


# ---------------------------------------------------------------------------
# Helper functions in tui.py / desktop.py
# ---------------------------------------------------------------------------


class TestRowCountText:
    def test_zero_rows(self):
        pytest.importorskip("textual")
        from execsql.gui.tui import _row_count_text as tui_rc

        assert "0" in tui_rc(0)
        assert "row" in tui_rc(0).lower()

    def test_one_row_singular(self):
        pytest.importorskip("textual")
        from execsql.gui.tui import _row_count_text as tui_rc

        out = tui_rc(1)
        assert "1" in out

    def test_many_rows(self):
        pytest.importorskip("textual")
        from execsql.gui.tui import _row_count_text as tui_rc

        assert "42" in tui_rc(42)

    def test_desktop_row_count(self):
        pytest.importorskip("tkinter")
        from execsql.gui.desktop import _row_count_text as desk_rc

        assert "0" in desk_rc(0)
        assert "5" in desk_rc(5)
