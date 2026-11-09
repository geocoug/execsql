"""Configured GUI backends must respect native desktop/display availability."""

from __future__ import annotations

import builtins
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from execsql import state
from execsql.utils import gui


@pytest.fixture
def backends(monkeypatch):
    pytest.importorskip("tkinter")
    pytest.importorskip("textual")
    from execsql.gui import desktop, tui

    native = Mock(spec=desktop.TkinterBackend)
    textual = Mock(spec=tui.TextualBackend)
    monkeypatch.setattr(desktop, "TkinterBackend", lambda: native)
    monkeypatch.setattr(tui, "TextualBackend", lambda: textual)
    monkeypatch.setattr(gui, "_active_backend", None)
    monkeypatch.setattr(state, "conf", SimpleNamespace(gui_framework="tkinter"))
    monkeypatch.setattr(state, "gui_manager_queue", None)
    monkeypatch.setattr(state, "gui_manager_thread", None)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    return SimpleNamespace(native=native, textual=textual)


@pytest.mark.parametrize(
    "platform, os_name, display, framework, expected",
    [
        ("darwin", "posix", None, "tkinter", "native"),
        ("linux", "posix", None, "tkinter", "textual"),
        ("linux", "posix", "DISPLAY", "tkinter", "native"),
        ("linux", "posix", "WAYLAND_DISPLAY", "tkinter", "native"),
        ("freebsd14", "posix", None, "tkinter", "textual"),
        ("win32", "nt", None, "tkinter", "native"),
        ("darwin", "posix", None, "textual", "textual"),
        ("linux", "posix", None, "textual", "textual"),
    ],
)
def test_platform_selects_expected_transport(
    backends,
    monkeypatch,
    capsys,
    platform,
    os_name,
    display,
    framework,
    expected,
):
    if display:
        monkeypatch.setenv(display, ":test")
    state.conf.gui_framework = framework
    with patch.object(sys, "platform", platform), patch.object(os, "name", os_name):
        gui.enable_gui()
        gui.enable_gui()  # Initializing twice must neither replace the queue nor repeat fallback diagnostics.
    assert gui._active_backend is getattr(backends, expected)
    if expected == "native":
        backends.native.start.assert_called_once_with()
        assert state.gui_manager_queue._backend is backends.native
    else:
        backends.native.start.assert_not_called()
        from execsql.gui.tui import _TextualSyncQueue

        assert isinstance(state.gui_manager_queue, _TextualSyncQueue)
    assert state.gui_manager_thread is None
    output = capsys.readouterr()
    assert output.out == ""
    if framework == "tkinter" and expected == "textual":
        assert "DISPLAY" in output.err and "Textual" in output.err
        assert output.err.count("GUI fallback") == 1
    else:
        assert output.err == ""


@pytest.mark.parametrize("error", [RuntimeError("native startup failed"), ImportError("Tk unavailable")])
def test_real_tk_startup_failure_falls_back_with_reason(backends, capsys, error):
    backends.native.start.side_effect = error
    with patch.object(sys, "platform", "darwin"), patch.object(os, "name", "posix"):
        gui.enable_gui()
    backends.native.start.assert_called_once_with()
    assert gui._active_backend is backends.textual
    output = capsys.readouterr()
    assert str(error) in output.err and "Textual" in output.err


def test_unavailable_textual_uses_manager_fallback(backends, monkeypatch, capsys):
    from execsql.gui.console import ConsoleBackend

    original_import = builtins.__import__

    def without_textual(name, *args, **kwargs):
        if name == "execsql.gui.tui":
            raise ImportError("Textual unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_textual)
    with patch.object(sys, "platform", "linux"), patch.object(os, "name", "posix"):
        gui.enable_gui()
    thread = state.gui_manager_thread
    queue = state.gui_manager_queue
    try:
        assert isinstance(gui._active_backend, ConsoleBackend)
        assert thread is not None and thread.is_alive()
        backends.native.start.assert_not_called()
        output = capsys.readouterr()
        assert "DISPLAY" in output.err and "Textual unavailable" in output.err
        assert "console" in output.err.lower()
    finally:
        if thread:
            queue.put(None)
            thread.join(2)
            assert not thread.is_alive()
