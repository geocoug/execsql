"""Console dimensions must reach the real Tk model and widget lifecycle."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from execsql import state
from execsql.metacommands.system import x_consoleheight, x_consolewidth
from execsql.utils import gui


@pytest.fixture(autouse=True)
def sizing_state(monkeypatch):
    monkeypatch.setattr(gui, "_console_width", 100)
    monkeypatch.setattr(gui, "_console_height", 25)
    monkeypatch.setattr(gui, "_console_running", False)


@pytest.fixture
def tk_console(monkeypatch):
    pytest.importorskip("tkinter")
    from execsql.gui import desktop
    from tests.gui.test_desktop_dialogs import _install_fake_tk, _mk_widget

    tk, ttk, scrolledtext = _install_fake_tk()
    monkeypatch.setattr(desktop, "tk", tk)
    monkeypatch.setattr(desktop, "ttk", ttk)
    monkeypatch.setattr(desktop, "scrolledtext", scrolledtext)
    root = _mk_widget()
    backend = desktop.TkinterBackend()
    backend._root = root
    monkeypatch.setattr(gui, "_active_backend", backend)
    monkeypatch.setattr(gui, "enable_gui", lambda: None)
    monkeypatch.setattr(state, "output", Mock())
    state.conf.gui_console_width = 140
    state.conf.gui_console_height = 40
    yield SimpleNamespace(backend=backend, text=scrolledtext.ScrolledText, root=root)
    backend.stop()


def test_configured_size_reaches_new_console(tk_console):
    gui.gui_console_on()
    console = tk_console.backend._console
    assert (console._width, console._height) == (140, 40)
    assert tk_console.text.call_args.kwargs["width"] == 140
    assert tk_console.text.call_args.kwargs["height"] == 40
    assert gui.gui_console_width() == 140
    assert gui.gui_console_height() == 40


@pytest.mark.parametrize("start_first", [False, True])
def test_commands_resize_actual_console_and_persist_across_off_on(tk_console, start_first):
    if start_first:
        gui.gui_console_on()
        console = tk_console.backend._console
        console._win.geometry.reset_mock()
    x_consolewidth(width="160")
    x_consoleheight(height="45")
    if start_first:
        assert (console._width, console._height) == (160, 45)
        assert console._text.configure.call_args.kwargs == {"width": 160, "height": 45}
        assert console._win.geometry.called
    else:
        assert tk_console.backend._console is None
    gui.gui_console_on()
    assert (tk_console.backend._console._width, tk_console.backend._console._height) == (160, 45)
    gui.gui_console_off()
    gui.gui_console_on()
    console = tk_console.backend._console
    assert (console._width, console._height) == (160, 45)
    assert tk_console.text.call_args.kwargs["width"] == 160
    assert tk_console.text.call_args.kwargs["height"] == 45


def test_resize_hidden_console_preserves_visibility_and_reopens_size(tk_console):
    gui.gui_console_on()
    console = tk_console.backend._console
    gui.gui_console_hide()
    console._win.deiconify.reset_mock()
    x_consolewidth(width="125")
    x_consoleheight(height="32")
    assert (console._width, console._height) == (125, 32)
    console._win.deiconify.assert_not_called()
    console._on_close()
    gui.gui_console_on()
    assert tk_console.text.call_args.kwargs["width"] == 125
    assert tk_console.text.call_args.kwargs["height"] == 32


def test_command_before_backend_exists_is_kept_for_on(tk_console, monkeypatch):
    monkeypatch.setattr(gui, "_active_backend", None)
    x_consolewidth(width="130")
    x_consoleheight(height="33")
    monkeypatch.setattr(gui, "_active_backend", tk_console.backend)
    gui.gui_console_on()
    assert tk_console.text.call_args.kwargs["width"] == 130
    assert tk_console.text.call_args.kwargs["height"] == 33


def test_new_runtime_config_overrides_prior_console_dimensions(tk_console):
    x_consolewidth(width="170")
    x_consoleheight(height="48")
    state.conf.gui_console_width = 100
    state.conf.gui_console_height = 25
    gui.gui_console_on()
    assert (tk_console.backend._console._width, tk_console.backend._console._height) == (100, 25)


@pytest.mark.parametrize("backend_name", ["console", "textual"])
def test_terminal_backends_store_settings_without_resizing_terminal(monkeypatch, capsys, backend_name):
    if backend_name == "textual":
        pytest.importorskip("textual")
        from execsql.gui.tui import TextualBackend

        backend = TextualBackend()
    else:
        from execsql.gui.console import ConsoleBackend

        backend = ConsoleBackend()
    monkeypatch.setattr(gui, "_active_backend", backend)
    x_consolewidth(width="160")
    x_consoleheight(height="45")
    assert gui.gui_console_width() == 160
    assert gui.gui_console_height() == 45
    assert capsys.readouterr() == ("", "")


def test_script_size_commands_reach_actual_backend_lifecycle(tk_console, monkeypatch):
    from execsql import run
    from execsql.gui.desktop import ConsoleWindow

    starts = []
    original = ConsoleWindow.start

    def record(console):
        original(console)
        starts.append((console._width, console._height))

    monkeypatch.setattr(ConsoleWindow, "start", record)
    result = run(
        sql="""-- !x! CONSOLE WIDTH 135
-- !x! CONSOLE HEIGHT 35
-- !x! CONSOLE ON
-- !x! CONSOLE WIDTH 145
-- !x! CONSOLE HEIGHT 38
-- !x! CONSOLE OFF
-- !x! CONSOLE ON
-- !x! CONSOLE OFF
""",
        dsn="sqlite:///:memory:",
    )
    assert result.success, result.errors
    assert starts == [(135, 35), (145, 38)]


def test_native_tk_resizing_preserves_position_visibility_and_off_on():
    import subprocess
    import sys

    pytest.importorskip("tkinter")
    script = """
import faulthandler
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock
from execsql import state
from execsql.gui.desktop import TkinterBackend
from execsql.metacommands.system import x_consolewidth, x_consoleheight
from execsql.utils import gui
faulthandler.dump_traceback_later(8)
try:
    root = tk.Tk()
except tk.TclError as exc:
    print('TK_UNAVAILABLE:', exc)
    raise SystemExit(77)
root.withdraw()
state.conf = SimpleNamespace(gui_console_width=100, gui_console_height=25)
state.output = Mock()
backend = TkinterBackend()
backend._root = root
gui._active_backend = backend
try:
    # Settle geometry without entering a nested native input event loop.
    backend.console_on()
    console = backend._console
    win = console._win
    root.update_idletasks()
    assert (int(console._text.cget('width')), int(console._text.cget('height'))) == (100,25)
    initial = (win.winfo_width(),win.winfo_height())
    win.geometry('300x200+200+140')
    root.update_idletasks()
    position = (win.winfo_x(),win.winfo_y())
    x_consolewidth(width='120')
    x_consoleheight(height='30')
    root.update_idletasks()
    assert (int(console._text.cget('width')),int(console._text.cget('height'))) == (120,30)
    assert win.winfo_width() > initial[0]
    assert win.winfo_height() > initial[1]
    assert (win.winfo_x(),win.winfo_y()) == position
    backend.console_hide()
    root.update_idletasks()
    x_consolewidth(width='80')
    x_consoleheight(height='20')
    root.update_idletasks()
    assert win.state() == 'withdrawn'
    backend.console_show()
    root.update_idletasks()
    assert win.winfo_width() < initial[0]
    assert win.winfo_height() < initial[1]
    backend.console_off()
    backend.console_on()
    root.update_idletasks()
    assert (int(backend._console._text.cget('width')),int(backend._console._text.cget('height'))) == (80,20)
finally:
    backend.stop()
faulthandler.cancel_dump_traceback_later()
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=10)
    if completed.returncode == 77 and "TK_UNAVAILABLE:" in completed.stdout:
        pytest.skip(completed.stdout.strip())
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_configuration_file_dimensions_reach_console(tk_console, tmp_path, monkeypatch):
    from execsql.config import ConfigData

    (tmp_path / "execsql.conf").write_text("[interface]\nconsole_width=150\nconsole_height=42\n")
    monkeypatch.setattr(state, "conf", ConfigData(str(tmp_path), None))
    gui.gui_console_on()
    assert tk_console.text.call_args.kwargs["width"] == 150
    assert tk_console.text.call_args.kwargs["height"] == 42


@pytest.mark.parametrize("dimension, value", [("width", 125), ("height", 35)])
def test_sizing_without_runtime_configuration_is_retained(monkeypatch, dimension, value):
    monkeypatch.setattr(state, "conf", None)
    monkeypatch.setattr(gui, "_active_backend", None)
    setting = gui.gui_console_width if dimension == "width" else gui.gui_console_height
    assert setting(value) == value
    assert setting() == value
