"""Extended coverage for execsql.utils.gui — targets the gaps left by
test_backends.py.  Focuses on:

- ``_apply_connect_result`` for every db_type branch
- ``gui_connect`` GUI-routed path
- ``gui_credentials`` GUI-routed path
- ``gui_console_*`` delegations to the active backend
- ``gui_console_width/height`` setters
- ``pause`` TTY path (timeout, enter, esc) via patched termios/tty/signal
- Module-level helpers: ``_clear_progress_line``, ``GuiSpec``, ``ActionSpec``,
  ``EntrySpec`` (already partially covered, fills small gaps)
"""

from __future__ import annotations

import queue as _queue
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
import execsql.utils.gui as _gui
from execsql.utils.gui import (
    ActionSpec,
    ConsoleUIError,
    EntrySpec,
    GuiSpec,
    _apply_connect_result,
    _clear_progress_line,
    gui_connect,
    gui_console_height,
    gui_console_hide,
    gui_console_off,
    gui_console_on,
    gui_console_progress,
    gui_console_save,
    gui_console_show,
    gui_console_status,
    gui_console_wait_user,
    gui_console_width,
    gui_credentials,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_backend():
    """Save/restore _gui._active_backend across each test."""
    prev = _gui._active_backend
    yield
    _gui._active_backend = prev


@pytest.fixture
def fake_backend():
    """Install a MagicMock as _active_backend for the duration of the test."""
    prev = _gui._active_backend
    backend = MagicMock()
    _gui._active_backend = backend
    yield backend
    _gui._active_backend = prev


def _make_responder(response: dict) -> object:
    """Return a fake gui_manager_queue whose .put() unblocks the spec's return queue."""

    class _Q:
        def __init__(self) -> None:
            self.specs: list = []

        def put(self, spec) -> None:
            self.specs.append(spec)
            spec.return_queue.put(response)

    return _Q()


# ---------------------------------------------------------------------------
# Data-carrier classes — small constructor gaps
# ---------------------------------------------------------------------------


class TestDataCarriers:
    def test_guispec_attributes(self) -> None:
        q = _queue.Queue()
        spec = GuiSpec("display", {"a": 1}, q)
        assert spec.gui_type == "display"
        assert spec.args == {"a": 1}
        assert spec.return_queue is q

    def test_action_spec_defaults(self) -> None:
        a = ActionSpec("label", "prompt", "scriptname")
        assert a.label == "label"
        assert a.script == "scriptname"
        assert a.data_required is False

    def test_entry_spec_full(self) -> None:
        e = EntrySpec(
            "var",
            "label",
            required=True,
            initial_value="x",
            default_width=10,
            default_height=2,
            lookup_list=["a", "b"],
            form_column=1,
            validation_regex="^[a-z]+$",
            validation_key_regex=r"\w",
            entry_type="textarea",
        )
        assert e.name == "var"  # alias
        assert e.lookup_list == ["a", "b"]
        assert e.validation_regex == "^[a-z]+$"
        assert e.entry_type == "textarea"
        assert e.value is None

    def test_entry_spec_default_lookup_is_empty_list(self) -> None:
        e = EntrySpec("v", "l")
        assert e.lookup_list == []


# ---------------------------------------------------------------------------
# gui_console_* — delegate to active backend
# ---------------------------------------------------------------------------


class TestConsoleDelegations:
    def test_hide_calls_backend(self, fake_backend) -> None:
        gui_console_hide()
        fake_backend.console_hide.assert_called_once()

    def test_show_calls_backend(self, fake_backend) -> None:
        gui_console_show()
        fake_backend.console_show.assert_called_once()

    def test_progress_calls_backend(self, fake_backend) -> None:
        gui_console_progress(5, 10)
        fake_backend.console_progress.assert_called_once_with(5, 10)

    def test_save_calls_backend(self, fake_backend) -> None:
        gui_console_save("/tmp/out.txt", append=True)
        fake_backend.console_save.assert_called_once_with("/tmp/out.txt", True)

    def test_status_calls_backend(self, fake_backend) -> None:
        gui_console_status("running")
        fake_backend.console_status.assert_called_once_with("running")

    def test_wait_user_calls_backend(self, fake_backend) -> None:
        gui_console_wait_user("done")
        fake_backend.console_wait_user.assert_called_once_with("done")

    def test_wait_user_no_backend_with_message_prints(self, reset_backend, capsys) -> None:
        _gui._active_backend = None
        gui_console_wait_user("hello")
        assert "hello" in capsys.readouterr().err

    def test_wait_user_no_backend_no_message_is_silent(self, reset_backend, capsys) -> None:
        _gui._active_backend = None
        gui_console_wait_user("")
        assert capsys.readouterr().err == ""

    def test_hide_no_backend_is_noop(self, reset_backend) -> None:
        _gui._active_backend = None
        gui_console_hide()  # should not raise

    def test_show_no_backend_is_noop(self, reset_backend) -> None:
        _gui._active_backend = None
        gui_console_show()  # should not raise

    def test_progress_no_backend_is_noop(self, reset_backend) -> None:
        _gui._active_backend = None
        gui_console_progress(1, 2)

    def test_save_no_backend_is_noop(self, reset_backend) -> None:
        _gui._active_backend = None
        gui_console_save("/tmp/x")

    def test_status_no_backend_is_noop(self, reset_backend) -> None:
        _gui._active_backend = None
        gui_console_status("m")


# ---------------------------------------------------------------------------
# gui_console_width / gui_console_height — setter/getter logic
# ---------------------------------------------------------------------------


class TestConsoleWidthHeight:
    def test_width_getter_default(self) -> None:
        assert isinstance(gui_console_width(), int)

    def test_width_set_without_gui_console(self) -> None:
        prev = _gui._console_width
        try:
            _state.gui_console = None
            gui_console_width(100)
            assert gui_console_width() == 100
        finally:
            _gui._console_width = prev

    def test_width_set_with_gui_console_set_width(self) -> None:
        prev = _gui._console_width
        try:
            mock_console = MagicMock()
            _state.gui_console = mock_console
            gui_console_width(120)
            mock_console.set_width.assert_called_once_with(120)
        finally:
            _gui._console_width = prev
            _state.gui_console = None

    def test_height_set_without_gui_console(self) -> None:
        prev = _gui._console_height
        try:
            _state.gui_console = None
            gui_console_height(40)
            assert gui_console_height() == 40
        finally:
            _gui._console_height = prev

    def test_height_set_with_gui_console_set_height(self) -> None:
        prev = _gui._console_height
        try:
            mock_console = MagicMock()
            _state.gui_console = mock_console
            gui_console_height(50)
            mock_console.set_height.assert_called_once_with(50)
        finally:
            _gui._console_height = prev
            _state.gui_console = None


# ---------------------------------------------------------------------------
# gui_console_on/off — exercised when no backend is installed
# ---------------------------------------------------------------------------


class TestConsoleOnOff:
    def test_on_off_without_backend(self, reset_backend) -> None:
        # Patch enable_gui so it doesn't actually start a backend.
        _gui._active_backend = None
        with patch("execsql.utils.gui.enable_gui"):
            gui_console_on()
            assert _gui._console_running is True
            gui_console_off()
            assert _gui._console_running is False


# ---------------------------------------------------------------------------
# gui_connect — GUI-routed branch + ConsoleUIError fallback
# ---------------------------------------------------------------------------


class TestGuiConnect:
    def test_headless_raises(self) -> None:
        _state.conf = SimpleNamespace(gui_level=0)
        with pytest.raises(ConsoleUIError):
            gui_connect("alias", "msg")

    def test_no_conf_raises(self) -> None:
        _state.conf = None
        with pytest.raises(ConsoleUIError):
            gui_connect("alias", "msg")

    def test_gui_level_cancelled_raises(self) -> None:
        _state.conf = SimpleNamespace(gui_level=1, gui_framework="tkinter")
        _state.gui_manager_queue = _make_responder({"db_type": None})
        with patch("execsql.utils.gui.enable_gui"), pytest.raises(ConsoleUIError):
            gui_connect("alias", "msg")

    def test_gui_level_sqlite_branch(self) -> None:
        _state.conf = SimpleNamespace(gui_level=1, gui_framework="tkinter")
        _state.gui_manager_queue = _make_responder(
            {
                "db_type": "l",
                "db_file": ":memory:",
                "database": None,
            },
        )
        pool = MagicMock()
        _state.dbs = pool
        with patch("execsql.utils.gui.enable_gui"):
            gui_connect("a", "m")
        pool.add.assert_called_once()
        assert pool.add.call_args[0][0] == "a"


# ---------------------------------------------------------------------------
# _apply_connect_result — every db_type branch
# ---------------------------------------------------------------------------


class TestApplyConnectResult:
    def setup_method(self) -> None:
        self.pool = MagicMock()
        _state.dbs = self.pool

    def _apply(self, db_type, **kwargs) -> None:
        result = {
            "db_type": db_type,
            "server": "s",
            "database": "d",
            "db_file": "f.db",
            "username": "u",
            **kwargs,
        }
        with (
            patch("execsql.db.factory.db_Postgres") as pg,
            patch("execsql.db.factory.db_SqlServer") as ss,
            patch("execsql.db.factory.db_SQLite") as sl,
            patch("execsql.db.factory.db_MySQL") as ms,
            patch("execsql.db.factory.db_DuckDB") as dk,
            patch("execsql.db.factory.db_Oracle") as orc,
            patch("execsql.db.factory.db_Firebird") as fb,
            patch("execsql.db.factory.db_Access") as ac,
            patch("execsql.db.factory.db_Dsn") as dsn,
        ):
            _apply_connect_result("alias", result)
        return SimpleNamespace(
            pg=pg,
            ss=ss,
            sl=sl,
            ms=ms,
            dk=dk,
            orc=orc,
            fb=fb,
            ac=ac,
            dsn=dsn,
        )

    def test_postgres(self) -> None:
        m = self._apply("p")
        m.pg.assert_called_once()

    def test_sqlserver(self) -> None:
        m = self._apply("s")
        m.ss.assert_called_once()

    def test_sqlite(self) -> None:
        m = self._apply("l")
        m.sl.assert_called_once()

    def test_mysql(self) -> None:
        m = self._apply("m")
        m.ms.assert_called_once()

    def test_duckdb(self) -> None:
        m = self._apply("k")
        m.dk.assert_called_once()

    def test_oracle(self) -> None:
        m = self._apply("o")
        m.orc.assert_called_once()

    def test_firebird(self) -> None:
        m = self._apply("f")
        m.fb.assert_called_once()

    def test_access(self) -> None:
        m = self._apply("a")
        m.ac.assert_called_once()

    def test_dsn(self) -> None:
        m = self._apply("d")
        m.dsn.assert_called_once()

    def test_unknown_raises(self) -> None:
        with pytest.raises(ConsoleUIError):
            self._apply("Z")


# ---------------------------------------------------------------------------
# gui_credentials — GUI-routed branch
# ---------------------------------------------------------------------------


class TestGuiCredentialsRouted:
    def test_routed_through_queue(self) -> None:
        _state.conf = SimpleNamespace(gui_level=2)
        thread = MagicMock()
        thread.is_alive.return_value = True
        _state.gui_manager_thread = thread
        _state.gui_manager_queue = _make_responder(
            {
                "username": "bob",
                "password": "hunter2",
            },
        )
        subvars = MagicMock()
        _state.subvars = subvars

        gui_credentials(message="login", username="$U", pwtext="$P")

        # Two add_substitution calls expected
        recorded = [c[0] for c in subvars.add_substitution.call_args_list]
        assert ("$U", "bob") in recorded
        assert ("$P", "hunter2") in recorded


# ---------------------------------------------------------------------------
# pause — TTY path with patched termios/tty/signal
# ---------------------------------------------------------------------------


class TestPauseTtyPath:
    def _setup_tty(self, char_iter):
        """Set up patches so pause() takes the POSIX TTY branch."""
        ctx = []
        # stdin must look like a real TTY
        ctx.append(patch.object(sys.stdin, "isatty", return_value=True))
        ctx.append(patch.object(sys.stdin, "fileno", return_value=0, create=True))
        ctx.append(patch("execsql.utils.gui.sys.platform", "linux"))
        ctx.append(patch("termios.tcgetattr", return_value=[0] * 7))
        ctx.append(patch("termios.tcsetattr"))
        ctx.append(patch("tty.setraw"))
        ctx.append(patch("signal.signal"))
        ctx.append(patch("signal.setitimer"))

        # Stdin reads — produce successive single chars from char_iter
        char_iter = iter(char_iter)
        ctx.append(patch.object(sys.stdin, "read", side_effect=lambda n=1: next(char_iter)))
        return ctx

    def test_tty_enter_returns_zero(self) -> None:
        pytest.importorskip("termios")
        if sys.platform == "win32":
            pytest.skip("termios/tty TTY path is POSIX-only")
        patches = self._setup_tty(["\r"])
        for p in patches:
            p.start()
        try:
            rv = _gui.pause("hello")
            assert rv == 0
        finally:
            for p in patches:
                p.stop()

    def test_tty_esc_returns_one(self) -> None:
        pytest.importorskip("termios")
        patches = self._setup_tty(["\x1b"])
        for p in patches:
            p.start()
        try:
            rv = _gui.pause("hello")
            assert rv == 1
        finally:
            for p in patches:
                p.stop()


# ---------------------------------------------------------------------------
# _clear_progress_line — pure side-effect helper
# ---------------------------------------------------------------------------


class TestClearProgressLine:
    def test_writes_clear_sequence(self, capsys) -> None:
        _clear_progress_line()
        out = capsys.readouterr().out
        # Should contain a carriage return and blank padding
        assert "\r" in out
