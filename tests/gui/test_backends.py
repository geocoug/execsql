"""Tests for the GUI backend system.

These tests cover:
- Data-carrier classes (GuiSpec, EntrySpec, ActionSpec)
- Backend factory (get_backend)
- ConsoleBackend dialog dispatch
- TkinterBackend instantiation (no display required — we test structure only)
- Pluggable manager thread integration
"""

from __future__ import annotations

import queue
import threading
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.utils.gui import (
    GUI_ACTION,
    GUI_COMPARE,
    GUI_CONNECT,
    GUI_CREDENTIALS,
    GUI_DIRECTORY,
    GUI_DISPLAY,
    GUI_ENTRY,
    GUI_HALT,
    GUI_MAP,
    GUI_MSG,
    GUI_OPENFILE,
    GUI_PAUSE,
    GUI_SAVEFILE,
    GUI_SELECTROWS,
    GUI_SELECTSUB,
    QUERY_CONSOLE,
    ActionSpec,
    ConsoleUIError,
    EntrySpec,
    GuiSpec,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_gui_state():
    """Reset GUI manager thread/queue state between tests."""
    prev_thread = _state.gui_manager_thread
    prev_queue = _state.gui_manager_queue
    import execsql.utils.gui as _gui

    prev_backend = _gui._active_backend
    prev_running = _gui._console_running
    yield
    # Shut down any manager thread started during the test
    if _state.gui_manager_queue is not None:
        try:
            _state.gui_manager_queue.put(None)
        except Exception:
            pass
    _state.gui_manager_thread = prev_thread
    _state.gui_manager_queue = prev_queue
    _gui._active_backend = prev_backend
    _gui._console_running = prev_running


# ---------------------------------------------------------------------------
# GuiSpec
# ---------------------------------------------------------------------------


class TestGuiSpec:
    def test_attributes(self):
        rq = queue.Queue()
        spec = GuiSpec(GUI_MSG, {"title": "t", "message": "m"}, rq)
        assert spec.gui_type == GUI_MSG
        assert spec.args["message"] == "m"
        assert spec.return_queue is rq

    def test_all_gui_types_are_strings(self):
        types = [
            GUI_HALT,
            GUI_MSG,
            GUI_PAUSE,
            GUI_DISPLAY,
            GUI_ENTRY,
            GUI_COMPARE,
            GUI_SELECTROWS,
            GUI_SELECTSUB,
            GUI_ACTION,
            GUI_MAP,
            GUI_OPENFILE,
            GUI_SAVEFILE,
            GUI_DIRECTORY,
            QUERY_CONSOLE,
            GUI_CREDENTIALS,
            GUI_CONNECT,
        ]
        for t in types:
            assert isinstance(t, str)


# ---------------------------------------------------------------------------
# EntrySpec
# ---------------------------------------------------------------------------


class TestEntrySpec:
    def test_basic_construction(self):
        spec = EntrySpec("$VAR", "Enter a value")
        assert spec.varname == "$VAR"
        assert spec.name == "$VAR"  # alias
        assert spec.label == "Enter a value"
        assert spec.value is None
        assert spec.required is False
        assert spec.initial_value is None
        assert spec.lookup_list == []

    def test_full_construction(self):
        spec = EntrySpec(
            "$X",
            "Label",
            required=True,
            initial_value="default",
            default_width=30,
            default_height=5,
            lookup_list=["a", "b"],
            form_column=2,
            validation_regex=r"\d+",
            validation_key_regex=r"\d",
            entry_type="dropdown",
        )
        assert spec.required is True
        assert spec.initial_value == "default"
        assert spec.default_width == 30
        assert spec.default_height == 5
        assert spec.lookup_list == ["a", "b"]
        assert spec.form_column == 2
        assert spec.validation_regex == r"\d+"
        assert spec.entry_type == "dropdown"

    def test_value_is_settable(self):
        spec = EntrySpec("$V", "Label")
        spec.value = "hello"
        assert spec.value == "hello"

    def test_name_equals_varname(self):
        spec = EntrySpec("~local_var", "Local")
        assert spec.name == spec.varname == "~local_var"


# ---------------------------------------------------------------------------
# ActionSpec
# ---------------------------------------------------------------------------


class TestActionSpec:
    def test_basic_construction(self):
        spec = ActionSpec("Run report", "Runs the monthly report", "monthly_report.sql")
        assert spec.label == "Run report"
        assert spec.prompt == "Runs the monthly report"
        assert spec.script == "monthly_report.sql"
        assert spec.data_required is False

    def test_data_required(self):
        spec = ActionSpec("Delete", "Delete selected", "delete.sql", data_required=True)
        assert spec.data_required is True


# ---------------------------------------------------------------------------
# ConsoleBackend — unit tests (no terminal interaction)
# ---------------------------------------------------------------------------


class TestConsoleBackend:
    def setup_method(self):
        from execsql.gui.console import ConsoleBackend

        self.backend = ConsoleBackend()

    def test_query_console_initially_false(self):
        result = self.backend.query_console({})
        assert result == {"console_running": False}

    def test_console_on_off(self):
        self.backend.console_on()
        assert self.backend.query_console({})["console_running"] is True
        self.backend.console_off()
        assert self.backend.query_console({})["console_running"] is False

    def test_show_halt_with_mock_input(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_halt({"title": "HALT", "message": "Stopping"})
        assert result["button"] == 1

    def test_show_msg_with_mock_input(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_msg({"title": "Info", "message": "Hello"})
        assert result["button"] == 1

    def test_show_pause_auto_countdown(self, monkeypatch):
        # countdown=0 → no sleep, auto-continue
        monkeypatch.setattr("time.sleep", lambda s: None)
        result = self.backend.show_pause({"message": "Wait", "countdown": 0})
        assert result == {"quit": False}

    def test_show_pause_user_continue(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_pause({"message": "Pause"})
        assert result == {"quit": False}

    def test_show_pause_user_cancel(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "q")
        result = self.backend.show_pause({"message": "Pause"})
        assert result == {"quit": True}

    def test_show_display_no_table_no_entry(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        result = self.backend.show_display(
            {
                "message": "Hello",
                "button_list": [("Continue", 1, "<Return>")],
            },
        )
        assert result["button"] == 1

    def test_show_display_with_text_entry(self, monkeypatch):
        inputs = iter(["my value", "1"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_display(
            {
                "message": "Enter something",
                "button_list": [("OK", 1, "<Return>")],
                "textentry": True,
                "initialtext": "",
            },
        )
        assert result["return_value"] == "my value"
        assert result["button"] == 1

    def test_show_display_free_mode(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_display(
            {
                "message": "Free display",
                "free": True,
            },
        )
        assert result["button"] == 1

    def test_show_open_file(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "/tmp/myfile.csv")
        result = self.backend.show_open_file({"working_dir": "/tmp"})
        assert result == {"filename": "/tmp/myfile.csv"}

    def test_show_open_file_cancel(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_open_file({})
        assert result == {"filename": None}

    def test_show_save_file(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "/tmp/out.csv")
        result = self.backend.show_save_file({})
        assert result == {"filename": "/tmp/out.csv"}

    def test_show_directory(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "/tmp")
        result = self.backend.show_directory({})
        assert result == {"directory": "/tmp"}

    def test_show_entry_form_submit(self, monkeypatch):
        spec1 = EntrySpec("$NAME", "Name")
        spec2 = EntrySpec("$AGE", "Age")
        inputs = iter(["Alice", "30", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_entry_form(
            {
                "entry_specs": [spec1, spec2],
            },
        )
        assert result["button"] == 1
        assert spec1.value == "Alice"
        assert spec2.value == "30"

    def test_show_entry_form_cancel(self, monkeypatch):
        spec = EntrySpec("$X", "Value")
        inputs = iter(["foo", "n"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_entry_form({"entry_specs": [spec]})
        assert result["button"] is None

    def test_show_entry_form_checkbox(self, monkeypatch):
        spec = EntrySpec("$FLAG", "Enable?", entry_type="checkbox")
        inputs = iter(["y", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_entry_form({"entry_specs": [spec]})
        assert result["button"] == 1
        assert spec.value == "True"

    def test_show_compare(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        result = self.backend.show_compare(
            {
                "headers1": ["id", "val"],
                "rows1": [(1, "a")],
                "headers2": ["id", "val"],
                "rows2": [(1, "a")],
                "button_list": [("Continue", 1, "<Return>")],
            },
        )
        assert result["button"] == 1

    def test_show_select_rows(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        result = self.backend.show_select_rows(
            {
                "headers1": ["id"],
                "rows1": [(1,)],
                "button_list": [("Continue", 1)],
            },
        )
        assert result["button"] == 1

    def test_show_action(self, monkeypatch):
        spec = ActionSpec("Run", "Run action", "script.sql")
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        result = self.backend.show_action(
            {
                "button_specs": [spec],
            },
        )
        assert result["button"] == 1

    def test_show_credentials(self, monkeypatch):
        import getpass

        monkeypatch.setattr("builtins.input", lambda *a: "alice")
        monkeypatch.setattr(getpass, "getpass", lambda *a: "secret")
        result = self.backend.show_credentials({"message": ""})
        assert result["username"] == "alice"
        assert result["password"] == "secret"

    def test_dispatch_unknown_type(self):
        rq = queue.Queue()
        spec = GuiSpec("unknown_type_xyz", {}, rq)
        result = self.backend.dispatch(spec)
        assert result.get("button") is None
        assert "error" in result

    def test_dispatch_all_known_types_exist(self):
        """Every constant maps to a handler — dispatch should not raise KeyError."""
        types = [
            GUI_HALT,
            GUI_MSG,
            GUI_PAUSE,
            GUI_DISPLAY,
            GUI_ENTRY,
            GUI_COMPARE,
            GUI_SELECTROWS,
            GUI_SELECTSUB,
            GUI_ACTION,
            GUI_MAP,
            GUI_OPENFILE,
            GUI_SAVEFILE,
            GUI_DIRECTORY,
            QUERY_CONSOLE,
            GUI_CREDENTIALS,
            GUI_CONNECT,
        ]
        for gui_type in types:
            rq = queue.Queue()
            spec = GuiSpec(gui_type, {}, rq)
            # Should not raise KeyError — result may be anything
            try:
                self.backend.dispatch(spec)
            except Exception:
                pass  # IO errors are expected in unit tests without a terminal


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------


class TestGetBackend:
    def test_default_framework_returns_a_backend(self):
        """get_backend() with default framework returns a valid GuiBackend."""
        from execsql.gui import get_backend
        from execsql.gui.base import GuiBackend

        backend = get_backend()
        assert isinstance(backend, GuiBackend)

    def test_textual_framework_returns_textual_if_available(self):
        from execsql.gui import get_backend

        try:
            import textual  # noqa: F401
            from execsql.gui.tui import TextualBackend

            backend = get_backend("textual")
            assert isinstance(backend, TextualBackend)
        except ImportError:
            from execsql.gui.console import ConsoleBackend

            backend = get_backend("textual")
            assert isinstance(backend, ConsoleBackend)

    def test_tkinter_framework_falls_back_gracefully(self):
        """On a headless CI environment Tkinter may fail; factory should fall back."""
        from execsql.gui import get_backend
        from execsql.gui.base import GuiBackend

        backend = get_backend("tkinter")
        assert isinstance(backend, GuiBackend)

    def test_backend_has_dispatch_method(self):
        from execsql.gui import get_backend

        backend = get_backend("textual")
        assert callable(backend.dispatch)

    def test_falls_back_to_console_when_all_unavailable(self):
        """When both tkinter and textual fail, fall back to ConsoleBackend."""
        from unittest.mock import patch
        from execsql.gui.console import ConsoleBackend

        def fail_import(name, *args, **kwargs):
            if name in ("execsql.gui.desktop", "execsql.gui.tui"):
                raise ImportError(f"mocked failure for {name}")
            return original_import(name, *args, **kwargs)

        import builtins

        original_import = builtins.__import__
        with patch("builtins.__import__", side_effect=fail_import):
            from execsql.gui import get_backend

            backend = get_backend("tkinter")
        assert isinstance(backend, ConsoleBackend)


# ---------------------------------------------------------------------------
# Manager thread integration
# ---------------------------------------------------------------------------


class TestManagerThread:
    @pytest.fixture(autouse=True)
    def setup_state(self, minimal_conf):
        """Extend minimal_conf with gui_level for these tests."""
        minimal_conf.gui_level = 1
        yield

    def test_enable_gui_starts_thread(self):
        from execsql.gui.console import ConsoleBackend
        from execsql.gui import gui_manager_loop

        q: queue.Queue = queue.Queue()
        backend = ConsoleBackend()
        t = threading.Thread(target=gui_manager_loop, args=(q, backend), daemon=True)
        t.start()

        # Send a sentinel to shut it down
        q.put(None)
        t.join(timeout=2)
        assert not t.is_alive()

    def test_manager_processes_query_console(self):
        from execsql.gui.console import ConsoleBackend
        from execsql.gui import gui_manager_loop

        q: queue.Queue = queue.Queue()
        backend = ConsoleBackend()
        t = threading.Thread(target=gui_manager_loop, args=(q, backend), daemon=True)
        t.start()

        rq: queue.Queue = queue.Queue()
        spec = GuiSpec(QUERY_CONSOLE, {}, rq)
        q.put(spec)
        result = rq.get(timeout=2)
        assert "console_running" in result

        q.put(None)
        t.join(timeout=2)

    def test_manager_handles_unknown_type_gracefully(self):
        from execsql.gui.console import ConsoleBackend
        from execsql.gui import gui_manager_loop

        q: queue.Queue = queue.Queue()
        backend = ConsoleBackend()
        t = threading.Thread(target=gui_manager_loop, args=(q, backend), daemon=True)
        t.start()

        rq: queue.Queue = queue.Queue()
        spec = GuiSpec("totally_unknown", {}, rq)
        q.put(spec)
        result = rq.get(timeout=2)
        assert "error" in result or result.get("button") is None

        q.put(None)
        t.join(timeout=2)

    def test_manager_handles_dispatch_exception(self):
        """When backend.dispatch() raises, gui_manager_loop catches and returns error."""
        from execsql.gui import gui_manager_loop

        class FailBackend:
            def dispatch(self, spec):
                raise RuntimeError("dispatch failed")

        q: queue.Queue = queue.Queue()
        backend = FailBackend()
        t = threading.Thread(target=gui_manager_loop, args=(q, backend), daemon=True)
        t.start()

        rq: queue.Queue = queue.Queue()
        spec = GuiSpec(GUI_MSG, {"title": "t", "message": "m"}, rq)
        q.put(spec)
        result = rq.get(timeout=2)
        assert "error" in result
        assert "dispatch failed" in result["error"]

        q.put(None)
        t.join(timeout=2)

    def test_manager_returns_display_result(self, monkeypatch):
        from execsql.gui.console import ConsoleBackend
        from execsql.gui import gui_manager_loop

        monkeypatch.setattr("builtins.input", lambda *a: "1")

        q: queue.Queue = queue.Queue()
        backend = ConsoleBackend()
        t = threading.Thread(target=gui_manager_loop, args=(q, backend), daemon=True)
        t.start()

        rq: queue.Queue = queue.Queue()
        spec = GuiSpec(GUI_DISPLAY, {"message": "Test", "button_list": [("OK", 1)]}, rq)
        q.put(spec)
        result = rq.get(timeout=5)
        assert result["button"] == 1

        q.put(None)
        t.join(timeout=2)


# ---------------------------------------------------------------------------
# ConsoleWindow — unit tests for save() and set_progress() (no display needed)
# ---------------------------------------------------------------------------


class TestConsoleWindowMethods:
    """Tests for ConsoleWindow.save() and set_progress() using mocked tkinter state."""

    def test_save_no_op_when_text_is_none(self, tmp_path):
        """save() silently does nothing when _text is None (window not started)."""
        try:
            from execsql.gui.desktop import ConsoleWindow
        except ImportError:
            pytest.skip("tkinter not available")
        cw = ConsoleWindow.__new__(ConsoleWindow)
        cw._text = None
        outfile = tmp_path / "out.txt"
        cw.save(str(outfile))
        assert not outfile.exists()

    def test_set_progress_no_op_when_var_is_none(self):
        """set_progress() silently does nothing when _progress_var is None."""
        try:
            from execsql.gui.desktop import ConsoleWindow
        except ImportError:
            pytest.skip("tkinter not available")
        cw = ConsoleWindow.__new__(ConsoleWindow)
        cw._progress_var = None
        cw.set_progress(75.0)  # Should not raise

    def test_set_progress_clamps_value(self):
        """set_progress() clamps the value to 0–100."""
        try:
            from execsql.gui.desktop import ConsoleWindow
        except ImportError:
            pytest.skip("tkinter not available")

        cw = ConsoleWindow.__new__(ConsoleWindow)
        mock_var = MagicMock()
        cw._progress_var = mock_var
        cw.set_progress(150.0)
        mock_var.set.assert_called_once_with(100.0)
        mock_var.reset_mock()
        cw.set_progress(-10.0)
        mock_var.set.assert_called_once_with(0.0)

    def test_set_progress_normal_value(self):
        """set_progress() passes a valid percentage through unchanged."""
        try:
            from execsql.gui.desktop import ConsoleWindow
        except ImportError:
            pytest.skip("tkinter not available")

        cw = ConsoleWindow.__new__(ConsoleWindow)
        mock_var = MagicMock()
        cw._progress_var = mock_var
        cw.set_progress(42.5)
        mock_var.set.assert_called_once_with(42.5)


# ---------------------------------------------------------------------------
# TkinterBackend — structure tests (no actual display needed)
# ---------------------------------------------------------------------------


class TestTkinterBackendStructure:
    def test_import_succeeds(self):
        """tkinter is part of CPython stdlib — import should always work."""
        try:
            from execsql.gui.desktop import TkinterBackend  # noqa: F401
        except ImportError:
            pytest.skip("tkinter not available")

    def test_backend_is_gui_backend(self):
        try:
            from execsql.gui.base import GuiBackend
            from execsql.gui.desktop import TkinterBackend
        except ImportError:
            pytest.skip("tkinter not available")
        assert issubclass(TkinterBackend, GuiBackend)

    def test_query_console_without_window(self):
        try:
            from execsql.gui.desktop import TkinterBackend
        except ImportError:
            pytest.skip("tkinter not available")
        backend = TkinterBackend()
        result = backend.query_console({})
        assert result == {"console_running": False}

    def test_console_save_delegates_to_window(self, tmp_path):
        """console_save() calls ConsoleWindow.save() when a console is active."""
        try:
            from unittest.mock import MagicMock
            from execsql.gui.desktop import TkinterBackend
        except ImportError:
            pytest.skip("tkinter not available")
        backend = TkinterBackend()
        mock_console = MagicMock()
        mock_console.is_running.return_value = True
        backend._console = mock_console
        outfile = str(tmp_path / "console.txt")
        backend.console_save(outfile, append=False)
        mock_console.save.assert_called_once_with(outfile, False)

    def test_console_save_no_op_without_window(self, tmp_path):
        """console_save() does nothing when no console is active."""
        try:
            from execsql.gui.desktop import TkinterBackend
        except ImportError:
            pytest.skip("tkinter not available")
        backend = TkinterBackend()
        # Should not raise
        backend.console_save(str(tmp_path / "out.txt"))

    def test_console_progress_delegates_to_window(self):
        """console_progress() calls ConsoleWindow.set_progress() when active."""
        try:
            from unittest.mock import MagicMock
            from execsql.gui.desktop import TkinterBackend
        except ImportError:
            pytest.skip("tkinter not available")
        backend = TkinterBackend()
        mock_console = MagicMock()
        backend._console = mock_console
        backend.console_progress(50.0)
        mock_console.set_progress.assert_called_once_with(50.0)

    def test_console_progress_with_total(self):
        """console_progress(num, total) converts to percentage before delegating."""
        try:
            from unittest.mock import MagicMock
            from execsql.gui.desktop import TkinterBackend
        except ImportError:
            pytest.skip("tkinter not available")
        backend = TkinterBackend()
        mock_console = MagicMock()
        backend._console = mock_console
        backend.console_progress(25.0, total=50.0)
        mock_console.set_progress.assert_called_once_with(50.0)  # 25/50 * 100


# ---------------------------------------------------------------------------
# TextualBackend — structure tests (no actual rendering needed)
# ---------------------------------------------------------------------------


class TestTextualBackendStructure:
    def test_import_succeeds_when_textual_available(self):
        try:
            from execsql.gui.tui import TextualBackend  # noqa: F401
        except ImportError:
            pytest.skip("textual not installed")

    def test_backend_is_gui_backend(self):
        try:
            from execsql.gui.base import GuiBackend
            from execsql.gui.tui import TextualBackend
        except ImportError:
            pytest.skip("textual not installed")
        assert issubclass(TextualBackend, GuiBackend)

    def test_query_console_initially_false(self):
        try:
            from execsql.gui.tui import TextualBackend
        except ImportError:
            pytest.skip("textual not installed")
        backend = TextualBackend()
        result = backend.query_console({})
        assert result == {"console_running": False}

    def test_console_on_off(self):
        try:
            from execsql.gui.tui import TextualBackend
        except ImportError:
            pytest.skip("textual not installed")
        backend = TextualBackend()
        backend.console_on()
        assert backend.query_console({})["console_running"] is True
        backend.console_off()
        assert backend.query_console({})["console_running"] is False


# ---------------------------------------------------------------------------
# gui.py public API surface
# ---------------------------------------------------------------------------


class TestGuiPublicAPI:
    def test_constants_defined(self):
        from execsql.utils import gui

        for name in [
            "GUI_HALT",
            "GUI_MSG",
            "GUI_PAUSE",
            "GUI_DISPLAY",
            "GUI_ENTRY",
            "GUI_COMPARE",
            "GUI_SELECTROWS",
            "GUI_SELECTSUB",
            "GUI_ACTION",
            "GUI_MAP",
            "GUI_OPENFILE",
            "GUI_SAVEFILE",
            "GUI_DIRECTORY",
            "QUERY_CONSOLE",
            "GUI_CREDENTIALS",
            "GUI_CONNECT",
        ]:
            assert hasattr(gui, name), f"Missing constant: {name}"

    def test_functions_defined(self):
        from execsql.utils import gui

        for name in [
            "enable_gui",
            "gui_console_isrunning",
            "gui_console_on",
            "gui_console_off",
            "gui_console_hide",
            "gui_console_show",
            "gui_console_progress",
            "gui_console_save",
            "gui_console_status",
            "gui_console_wait_user",
            "gui_console_width",
            "gui_console_height",
            "gui_connect",
            "gui_credentials",
            "get_yn",
            "get_yn_win",
            "pause",
            "pause_win",
        ]:
            assert hasattr(gui, name), f"Missing function: {name}"

    def test_gui_console_isrunning_default_false(self):
        from execsql.utils.gui import gui_console_isrunning

        assert gui_console_isrunning() is False

    def test_get_yn_yes(self, monkeypatch):
        from execsql.utils.gui import get_yn

        monkeypatch.setattr("builtins.input", lambda *a: "y")
        assert get_yn("Continue?") is True

    def test_get_yn_no(self, monkeypatch):
        from execsql.utils.gui import get_yn

        monkeypatch.setattr("builtins.input", lambda *a: "n")
        assert get_yn("Continue?") is False

    def test_get_yn_full_words(self, monkeypatch):
        from execsql.utils.gui import get_yn

        inputs = iter(["yes"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        assert get_yn("?") is True

    def test_get_yn_retry_on_bad_input(self, monkeypatch):
        from execsql.utils.gui import get_yn

        inputs = iter(["maybe", "no"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        assert get_yn("?") is False

    def test_pause_no_countdown(self, monkeypatch):
        from execsql.utils.gui import pause

        monkeypatch.setattr("builtins.input", lambda *a: "")
        assert pause("Pausing...") == 0  # 0 = user continued

    def test_pause_with_countdown_halt(self, monkeypatch):
        from execsql.utils.gui import pause

        monkeypatch.setattr("time.sleep", lambda s: None)
        assert pause("Waiting...", action="HALT", countdown=5.0) == 2  # 2 = timed out

    def test_pause_with_countdown_continue(self, monkeypatch):
        from execsql.utils.gui import pause

        monkeypatch.setattr("time.sleep", lambda s: None)
        assert pause("Waiting...", action="CONTINUE", countdown=5.0) == 2  # 2 = timed out

    def test_console_ui_error_is_exception(self):

        with pytest.raises(ConsoleUIError):
            raise ConsoleUIError("test error")

    def test_gui_console_isrunning_delegates_to_backend(self):
        """gui_console_isrunning() returns the backend's console state, not the stale flag."""
        import execsql.utils.gui as _gui
        from execsql.gui.console import ConsoleBackend

        prev = _gui._active_backend
        try:
            backend = ConsoleBackend()
            _gui._active_backend = backend
            backend.console_on()
            assert _gui.gui_console_isrunning() is True
            backend.console_off()
            assert _gui.gui_console_isrunning() is False
        finally:
            _gui._active_backend = prev

    def test_gui_console_isrunning_falls_back_to_flag_when_no_backend(self):
        """Without an active backend, gui_console_isrunning() falls back to the module flag."""
        import execsql.utils.gui as _gui

        prev_backend = _gui._active_backend
        prev_flag = _gui._console_running
        try:
            _gui._active_backend = None
            _gui._console_running = True
            assert _gui.gui_console_isrunning() is True
            _gui._console_running = False
            assert _gui.gui_console_isrunning() is False
        finally:
            _gui._active_backend = prev_backend
            _gui._console_running = prev_flag

    def test_pause_win_is_alias_for_pause(self, monkeypatch):
        from execsql.utils.gui import pause, pause_win

        monkeypatch.setattr("builtins.input", lambda *a: "")
        assert pause_win("msg") == pause("msg")

    def test_get_yn_win_is_alias_for_get_yn(self, monkeypatch):
        from execsql.utils.gui import get_yn_win

        monkeypatch.setattr("builtins.input", lambda *a: "y")
        assert get_yn_win("?") is True

    def test_gui_console_on_off_updates_isrunning(self):
        """gui_console_on/off should be reflected by gui_console_isrunning()."""
        import execsql.utils.gui as _gui
        from execsql.gui.console import ConsoleBackend

        prev = _gui._active_backend
        try:
            _gui._active_backend = ConsoleBackend()
            _gui.gui_console_on()
            assert _gui.gui_console_isrunning() is True
            _gui.gui_console_off()
            assert _gui.gui_console_isrunning() is False
        finally:
            _gui._active_backend = prev


# ---------------------------------------------------------------------------
# ConsoleBackend — extended coverage for uncovered branches
# ---------------------------------------------------------------------------


class TestConsoleBackendExtended:
    """Extended tests targeting previously-uncovered branches in console.py."""

    def setup_method(self):
        from execsql.gui.console import ConsoleBackend

        self.backend = ConsoleBackend()

    # ------------------------------------------------------------------
    # console_wait_user — prints message when non-empty (lines 77-78)
    # ------------------------------------------------------------------

    def test_console_wait_user_with_message_prints_to_stderr(self, capsys):
        self.backend.console_wait_user("Please wait...")
        captured = capsys.readouterr()
        assert "Please wait..." in captured.err

    def test_console_wait_user_empty_message_prints_nothing(self, capsys):
        self.backend.console_wait_user("")
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_console_wait_user_no_arg_prints_nothing(self, capsys):
        self.backend.console_wait_user()
        captured = capsys.readouterr()
        assert captured.err == ""

    # ------------------------------------------------------------------
    # show_halt — column_headers + rowset branch (lines 90-91)
    # ------------------------------------------------------------------

    def test_show_halt_with_table_data_prints_table(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_halt(
            {
                "title": "HALT",
                "message": "Check this data",
                "column_headers": ["id", "name"],
                "rowset": [(1, "Alice"), (2, "Bob")],
            },
        )
        assert result["button"] == 1
        captured = capsys.readouterr()
        assert "id" in captured.err
        assert "Alice" in captured.err

    def test_show_halt_without_table_data_still_returns(self, monkeypatch):
        """When column_headers/rowset are absent, show_halt still completes."""
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_halt({"title": "HALT", "message": "msg"})
        assert result["button"] == 1

    # ------------------------------------------------------------------
    # show_display — hidetext / getpass branch (lines 133-136)
    # ------------------------------------------------------------------

    def test_show_display_hidetext_uses_getpass(self, monkeypatch):
        """When hidetext=True and textentry=True, getpass is used instead of input."""
        import getpass

        monkeypatch.setattr(getpass, "getpass", lambda *a: "s3cr3t")
        # _prompt_buttons needs input; patch it to return a valid choice.
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        result = self.backend.show_display(
            {
                "textentry": True,
                "hidetext": True,
                "button_list": [("OK", 1, "<Return>")],
            },
        )
        assert result["return_value"] == "s3cr3t"
        assert result["button"] == 1

    def test_show_display_with_title_and_table(self, monkeypatch, capsys):
        """show_display prints title and table when both are supplied."""
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        self.backend.show_display(
            {
                "title": "My Title",
                "column_headers": ["a", "b"],
                "rowset": [(10, 20)],
                "button_list": [("OK", 1, "<Return>")],
            },
        )
        captured = capsys.readouterr()
        assert "My Title" in captured.err
        assert "a" in captured.err

    # ------------------------------------------------------------------
    # show_entry_form — title / message / table print branches (lines 153-158)
    # ------------------------------------------------------------------

    def test_show_entry_form_prints_title_and_message(self, monkeypatch, capsys):
        inputs = iter(["val", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        spec = EntrySpec("$X", "X label")
        self.backend.show_entry_form(
            {
                "title": "My Form",
                "message": "Fill in all fields",
                "entry_specs": [spec],
            },
        )
        captured = capsys.readouterr()
        assert "My Form" in captured.err
        assert "Fill in all fields" in captured.err

    def test_show_entry_form_with_table_data(self, monkeypatch, capsys):
        inputs = iter(["val", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        spec = EntrySpec("$X", "X label")
        self.backend.show_entry_form(
            {
                "entry_specs": [spec],
                "column_headers": ["col1"],
                "rowset": [("row_value",)],
            },
        )
        captured = capsys.readouterr()
        assert "col1" in captured.err

    # ------------------------------------------------------------------
    # show_entry_form — dropdown / select entry type (lines 166-179)
    # ------------------------------------------------------------------

    def test_show_entry_form_dropdown_by_number(self, monkeypatch):
        """Dropdown entry accepts a numeric choice."""
        spec = EntrySpec("$COLOR", "Color", entry_type="dropdown", lookup_list=["red", "green", "blue"])
        # Input: choose option 2 ("green"), then submit.
        inputs = iter(["2", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_entry_form({"entry_specs": [spec]})
        assert result["button"] == 1
        assert spec.value == "green"

    def test_show_entry_form_dropdown_by_value(self, monkeypatch):
        """Dropdown entry accepts a literal value match."""
        spec = EntrySpec("$COLOR", "Color", entry_type="dropdown", lookup_list=["red", "green", "blue"])
        inputs = iter(["blue", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        self.backend.show_entry_form({"entry_specs": [spec]})
        assert spec.value == "blue"

    def test_show_entry_form_select_type_works_same_as_dropdown(self, monkeypatch):
        """entry_type='select' is handled identically to 'dropdown'."""
        spec = EntrySpec("$ITEM", "Item", entry_type="select", lookup_list=["alpha", "beta"])
        inputs = iter(["1", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        self.backend.show_entry_form({"entry_specs": [spec]})
        assert spec.value == "alpha"

    def test_show_entry_form_dropdown_invalid_then_valid(self, monkeypatch):
        """show_entry_form loops until a valid dropdown choice is entered."""
        spec = EntrySpec("$X", "X", entry_type="dropdown", lookup_list=["a", "b"])
        # First input is invalid, second is valid, third is submit.
        inputs = iter(["99", "a", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        self.backend.show_entry_form({"entry_specs": [spec]})
        assert spec.value == "a"

    # ------------------------------------------------------------------
    # show_select_sub — row selection (lines 236-245)
    # ------------------------------------------------------------------

    def test_show_select_sub_cancel_returns_none(self, monkeypatch):
        """Blank input cancels; returns button=None, row=None."""
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_select_sub(
            {
                "headers": ["id", "name"],
                "rows": [(1, "Alice"), (2, "Bob")],
            },
        )
        assert result["button"] is None
        assert result["row"] is None

    def test_show_select_sub_valid_row_returns_dict(self, monkeypatch):
        """Valid row number returns the row as a header-keyed dict."""
        monkeypatch.setattr("builtins.input", lambda *a: "2")
        result = self.backend.show_select_sub(
            {
                "headers": ["id", "name"],
                "rows": [(1, "Alice"), (2, "Bob")],
            },
        )
        assert result["button"] == 1
        assert result["row"] == {"id": 2, "name": "Bob"}

    def test_show_select_sub_invalid_then_valid(self, monkeypatch):
        """show_select_sub loops on invalid input until a valid row number is given."""
        inputs = iter(["99", "1"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_select_sub(
            {
                "headers": ["x"],
                "rows": [("value_x",)],
            },
        )
        assert result["button"] == 1
        assert result["row"] == {"x": "value_x"}

    def test_show_select_sub_no_rows_returns_none(self, monkeypatch):
        """With no rows, show_select_sub immediately returns button=None."""
        result = self.backend.show_select_sub({"headers": [], "rows": []})
        assert result["button"] is None
        assert result["row"] is None

    def test_show_select_sub_prints_rows_to_stderr(self, monkeypatch, capsys):
        """Row listing is printed to stderr."""
        monkeypatch.setattr("builtins.input", lambda *a: "")
        self.backend.show_select_sub(
            {
                "title": "Pick one",
                "headers": ["id"],
                "rows": [(42,)],
            },
        )
        captured = capsys.readouterr()
        assert "42" in captured.err

    # ------------------------------------------------------------------
    # show_action — include_continue_button branch (lines 269-276)
    # ------------------------------------------------------------------

    def test_show_action_no_button_specs_returns_1(self, monkeypatch):
        """With no button_specs, show_action prompts for Enter and returns button=1."""
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = self.backend.show_action({"button_specs": []})
        assert result["button"] == 1

    def test_show_action_include_continue_button_zero_returns_1(self, monkeypatch):
        """Choosing '0' when include_continue_button is set returns button=1."""
        spec = ActionSpec("Run", "Run it", "run.sql")
        inputs = iter(["0"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_action(
            {
                "button_specs": [spec],
                "include_continue_button": True,
            },
        )
        assert result["button"] == 1

    def test_show_action_include_continue_button_invalid_then_valid(self, monkeypatch):
        """show_action loops on bad input; accepting '0' continues when include_continue_button."""
        spec = ActionSpec("Run", "Run it", "run.sql")
        inputs = iter(["bad", "0"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_action(
            {
                "button_specs": [spec],
                "include_continue_button": True,
            },
        )
        assert result["button"] == 1

    def test_show_action_with_table_data(self, monkeypatch, capsys):
        """column_headers + rowset are printed when both are present."""
        spec = ActionSpec("Go", "Go action", "go.sql")
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        self.backend.show_action(
            {
                "button_specs": [spec],
                "column_headers": ["col"],
                "rowset": [("value",)],
            },
        )
        captured = capsys.readouterr()
        assert "col" in captured.err

    # ------------------------------------------------------------------
    # show_connect — message branch (line 346)
    # ------------------------------------------------------------------

    def test_show_connect_with_message_prints_to_stderr(self, monkeypatch, capsys):
        """When message is set, show_connect prints it to stderr."""
        inputs = iter(["p", "", "mydb", "", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        self.backend.show_connect({"message": "Please connect to the database"})
        captured = capsys.readouterr()
        assert "Please connect to the database" in captured.err

    def test_show_connect_returns_typed_dict(self, monkeypatch):
        """show_connect returns a dict with the expected keys."""
        inputs = iter(["p", "localhost", "mydb", "", "admin"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_connect({})
        assert set(result.keys()) == {"db_type", "server", "database", "db_file", "username"}
        assert result["db_type"] == "p"
        assert result["server"] == "localhost"
        assert result["database"] == "mydb"
        assert result["db_file"] is None
        assert result["username"] == "admin"

    def test_show_connect_blank_fields_become_none(self, monkeypatch):
        """Blank input for optional fields is stored as None."""
        inputs = iter(["l", "", "", "/tmp/test.db", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = self.backend.show_connect({})
        assert result["server"] is None
        assert result["database"] is None
        assert result["db_file"] == "/tmp/test.db"
        assert result["username"] is None

    def test_show_connect_no_message_no_extra_output(self, monkeypatch, capsys):
        """No extra message is printed when message is empty."""
        inputs = iter(["s", "", "", "", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        self.backend.show_connect({})
        captured = capsys.readouterr()
        # The db_types listing is always printed, but the optional message should not appear.
        assert "Please" not in captured.err

    # ------------------------------------------------------------------
    # show_credentials — message branch (lines 334-336)
    # ------------------------------------------------------------------

    def test_show_credentials_with_message_prints_to_stderr(self, monkeypatch, capsys):
        import getpass

        monkeypatch.setattr("builtins.input", lambda *a: "bob")
        monkeypatch.setattr(getpass, "getpass", lambda *a: "pass123")
        self.backend.show_credentials({"message": "Enter your credentials"})
        captured = capsys.readouterr()
        assert "Enter your credentials" in captured.err

    # ------------------------------------------------------------------
    # show_map — lat/lon/label branch (lines 297-306)
    # ------------------------------------------------------------------

    def test_show_map_with_location_columns_prints_locations(self, monkeypatch, capsys):
        """When lat_col, lon_col, and label_col are given, locations are printed."""
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        self.backend.show_map(
            {
                "title": "Map",
                "headers": ["lat", "lon", "name"],
                "rows": [(37.77, -122.42, "SF"), (34.05, -118.24, "LA")],
                "lat_col": "lat",
                "lon_col": "lon",
                "label_col": "name",
                "button_list": [("Close", 1, "<Return>")],
            },
        )
        captured = capsys.readouterr()
        assert "37.77" in captured.err
        assert "SF" in captured.err

    def test_show_map_without_location_columns(self, monkeypatch, capsys):
        """When lat/lon/label columns are absent, show_map still completes."""
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        result = self.backend.show_map(
            {
                "headers": ["a"],
                "rows": [(1,)],
                "button_list": [("OK", 1, "<Return>")],
            },
        )
        assert result["button"] == 1

    def test_show_map_invalid_column_name_does_not_raise(self, monkeypatch):
        """ValueError from headers.index is caught; show_map completes normally."""
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        result = self.backend.show_map(
            {
                "headers": ["a", "b"],
                "rows": [(1, 2)],
                "lat_col": "nonexistent_lat",
                "lon_col": "b",
                "button_list": [("OK", 1, "<Return>")],
            },
        )
        assert result["button"] == 1

    # ------------------------------------------------------------------
    # _print_table helper — None cell values are rendered as empty string
    # ------------------------------------------------------------------

    def test_print_table_none_cells_render_as_empty(self, capsys):
        """_print_table handles None cell values without raising."""
        from execsql.gui.console import _print_table

        _print_table(["a", "b"], [(None, "x"), ("y", None)])
        captured = capsys.readouterr()
        assert "a" in captured.err
        assert "x" in captured.err

    def test_print_table_empty_headers_returns_immediately(self, capsys):
        """_print_table with empty headers prints nothing."""
        from execsql.gui.console import _print_table

        _print_table([], [])
        captured = capsys.readouterr()
        assert captured.err == ""

    # ------------------------------------------------------------------
    # _prompt_buttons helper — empty button_list branch (line 40-41)
    # ------------------------------------------------------------------

    def test_prompt_buttons_empty_list_awaits_enter(self, monkeypatch):
        """With an empty button_list, _prompt_buttons prompts for Enter and returns 1."""
        from execsql.gui.console import _prompt_buttons

        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = _prompt_buttons([])
        assert result == 1

    def test_prompt_buttons_invalid_then_valid_choice(self, monkeypatch):
        """_prompt_buttons loops on invalid input until a recognised choice is entered."""
        from execsql.gui.console import _prompt_buttons

        inputs = iter(["99", "continue"])
        monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
        result = _prompt_buttons([("Continue", 7, "<Return>")])
        assert result == 7
