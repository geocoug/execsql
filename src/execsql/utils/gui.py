"""GUI subsystem for execsql.

This module provides:
  - The full public API expected by the rest of the codebase via _state.gui_*
  - No-op / console-fallback implementations for all GUI operations when
    running in headless / non-GUI mode (gui_level == 0).
  - A pluggable backend system: Textual (TUI), Tkinter (desktop), or Console.

Backend selection is driven by conf.gui_framework (orthogonal to gui_level):
    "tkinter" → TkinterBackend → TextualBackend → ConsoleBackend
    "textual"  → TextualBackend → ConsoleBackend

gui_level controls *when* GUI is used; gui_framework controls *which* technology.

All functions that need state access import execsql.state lazily inside
their bodies to avoid circular imports.
"""

from __future__ import annotations

import sys
from typing import Any, cast

__all__ = [
    # Constants
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
    # Data-carrier classes
    "GuiSpec",
    "get_gui_response",
    "ConsoleUIError",
    "ActionSpec",
    "EntrySpec",
    # Console lifecycle
    "gui_console_isrunning",
    "enable_gui",
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
    # Database connection GUI
    "gui_connect",
    "gui_credentials",
    # Interactive prompts
    "get_yn",
    "get_yn_win",
    "pause",
    "pause_win",
]

# ---------------------------------------------------------------------------
# GUI command constants — used to identify request types in the GUI queue.
# ---------------------------------------------------------------------------

GUI_HALT = "halt"
GUI_MSG = "msg"
GUI_PAUSE = "pause"
GUI_DISPLAY = "display"
GUI_ENTRY = "entry"
GUI_COMPARE = "compare"
GUI_SELECTROWS = "selectrows"
GUI_SELECTSUB = "selectsub"
GUI_ACTION = "action"
GUI_MAP = "map"
GUI_OPENFILE = "openfile"
GUI_SAVEFILE = "savefile"
GUI_DIRECTORY = "directory"
QUERY_CONSOLE = "query_console"
# Additional constants used by gui_credentials / gui_connect
GUI_CREDENTIALS = "credentials"
GUI_CONNECT = "connect"


# ---------------------------------------------------------------------------
# Data-carrier classes
# ---------------------------------------------------------------------------


class GuiSpec:
    """A GUI request passed through the active queue adapter."""

    def __init__(self, gui_type: str, args: dict, return_queue: Any) -> None:
        self.gui_type = gui_type
        self.args = args
        self.return_queue = return_queue


class ConsoleUIError(Exception):
    """Raised when a GUI / console UI operation fails."""


def get_gui_response(return_queue: Any, gui_type: str) -> dict:
    """Receive a GUI result on the script thread, raising transport errors.

    Console shutdown raises KeyboardInterrupt here on the worker thread so
    its transaction cleanup finishes before the UI closes.
    Cancellation supplies the dialog's empty result fields and records
    DIALOG_CANCELED. The calling handler owns CANCEL_HALT and its cleanup.
    """
    result = return_queue.get(block=True)
    if not isinstance(result, dict):
        raise ConsoleUIError(f"Invalid response from {gui_type} dialog.")
    if result.get("interrupted"):
        raise KeyboardInterrupt
    if "error" in result:
        raise ConsoleUIError(f"GUI {gui_type} failed: {result['error']}")
    empty_fields: dict[str, Any] = {"button": None}
    if gui_type in (GUI_DISPLAY, GUI_ENTRY):
        empty_fields["return_value"] = None
    elif gui_type in (GUI_SELECTSUB, GUI_ACTION):
        empty_fields["row"] = None
    elif gui_type == GUI_SELECTROWS:
        empty_fields["rows"] = None
    elif gui_type == GUI_PAUSE:
        empty_fields["quit"] = True
    elif gui_type in (GUI_OPENFILE, GUI_SAVEFILE):
        empty_fields["filename"] = None
    elif gui_type == GUI_DIRECTORY:
        empty_fields["directory"] = None
    elif gui_type == GUI_CREDENTIALS:
        empty_fields.update(username="", password="")
    elif gui_type == GUI_CONNECT:
        empty_fields["db_type"] = None

    cancelled = not result or result.get("cancelled") or ("button" in result and result["button"] is None)
    if gui_type in (GUI_OPENFILE, GUI_SAVEFILE):
        cancelled = cancelled or result.get("filename") is None
    elif gui_type == GUI_DIRECTORY:
        cancelled = cancelled or result.get("directory") is None
    elif gui_type == GUI_PAUSE:
        cancelled = cancelled or result.get("quit", False)
    elif gui_type == GUI_CONNECT:
        cancelled = cancelled or result.get("db_type") is None
    if cancelled:
        result = {**result, **empty_fields, "cancelled": True}

    import execsql.state as _state

    if gui_type != QUERY_CONSOLE and _state.status is not None:
        _state.status.dialog_canceled = bool(cancelled)
    return result


class ActionSpec:
    """Specification for a PROMPT ACTION dialog button.

    Parameters
    ----------
    label:
        Text shown on the button.
    prompt:
        Description shown alongside the button.
    script:
        Name of the script to execute when the button is clicked.
    data_required:
        If True the button is only active when a data row is selected.
    """

    def __init__(
        self,
        label: str,
        prompt: str,
        script: str,
        data_required: bool = False,
    ) -> None:
        self.label = label
        self.prompt = prompt
        self.script = script
        self.data_required = data_required


class EntrySpec:
    """Specification for a PROMPT ENTRY_FORM field.

    Parameters
    ----------
    varname:
        Substitution variable name (also accessible as ``.name``).
    label:
        Prompt text shown to the left of the input widget.
    required:
        If True the form cannot be submitted without a value.
    initial_value:
        Pre-populated value.
    default_width:
        Preferred widget width in characters.
    default_height:
        Preferred widget height in lines (for multi-line inputs).
    lookup_list:
        Allowed values for dropdown / combobox entry types.
    form_column:
        Column index (1-based) when the form uses a multi-column layout.
    validation_regex:
        Full-field validation pattern (applied on submit).
    validation_key_regex:
        Per-keystroke validation pattern.
    entry_type:
        Widget type: ``"text"`` (default), ``"checkbox"``, ``"dropdown"``,
        ``"select"``, or ``"textarea"``.
    """

    def __init__(
        self,
        varname: str,
        label: str,
        required: bool = False,
        initial_value: str | None = None,
        default_width: int | None = None,
        default_height: int | None = None,
        lookup_list: list | None = None,
        form_column: int | None = None,
        validation_regex: str | None = None,
        validation_key_regex: str | None = None,
        entry_type: str | None = None,
    ) -> None:
        self.varname = varname
        self.name = varname  # alias used by prompt.py result processing
        self.label = label
        self.required = required
        self.initial_value = initial_value
        self.default_width = default_width
        self.default_height = default_height
        self.lookup_list: list = lookup_list or []
        self.form_column = form_column
        self.validation_regex = validation_regex
        self.validation_key_regex = validation_key_regex
        self.entry_type = entry_type
        self.value: str | None = None  # populated by the backend after user input


# ---------------------------------------------------------------------------
# Console state (module-level, mutated by the functions below)
# ---------------------------------------------------------------------------

_console_running: bool = False
_console_width: int = 100
_console_height: int = 25
_dialog_canceled: bool = False

# Active backend (set by enable_gui(); None before first call)
_active_backend: Any = None


# ---------------------------------------------------------------------------
# Console lifecycle
# ---------------------------------------------------------------------------


def gui_console_isrunning() -> bool:
    """Return True if the GUI console is currently active.

    Delegates to the active backend when available so that the flag stays
    correct even when the user closes the console window directly (e.g.
    clicking the Tkinter window's close button).
    """
    if _active_backend is not None:
        return cast(bool, _active_backend.query_console({}).get("console_running", False))
    return _console_running


def enable_gui() -> None:
    """Ensure the GUI subsystem has a synchronous queue or manager thread.

    This is idempotent — subsequent calls return immediately if already set up.

    Backend selection is based solely on ``conf.gui_framework`` (default
    ``"tkinter"``), not on ``gui_level``.  The level controls *when* callers
    invoke this function; the framework controls *which* backend is used.

    - ``"tkinter"`` → TkinterBackend (sync, main-thread) → TextualBackend →
      ConsoleBackend (thread-based fallback)
    - ``"textual"``  → TextualBackend (sync, main-thread) → ConsoleBackend
    """
    global _active_backend

    import execsql.state as _state

    # Already initialised — nothing to do.
    if _active_backend is not None:
        return
    backend: Any

    framework = _state.conf.gui_framework if _state.conf else "tkinter"

    # Native macOS Tk uses Aqua; other POSIX desktops require a display server.
    import os as _os
    import threading

    headless_posix = (
        _os.name == "posix"
        and sys.platform != "darwin"
        and not _os.environ.get("DISPLAY")
        and not _os.environ.get("WAYLAND_DISPLAY")
    )
    fallback_reason = None
    if framework == "tkinter" and headless_posix:
        fallback_reason = "Tkinter has no DISPLAY or WAYLAND_DISPLAY"
    elif (
        framework == "tkinter"
        and sys.platform == "darwin"
        and threading.current_thread() is not threading.main_thread()
    ):
        fallback_reason = "Tkinter on macOS requires the main thread"

    # --- Tkinter sync path --------------------------------------------------
    # Tkinter must run on the main thread (required on macOS).  Use a sync
    # queue that dispatches dialogs directly in the calling thread instead of
    # routing through a background manager thread.
    if framework == "tkinter" and fallback_reason is None:
        try:
            from execsql.gui.desktop import TkinterBackend, _TkinterSyncQueue

            backend = TkinterBackend()
            backend.start()
            _active_backend = backend
            _state.gui_manager_queue = _TkinterSyncQueue(backend)
            return
        except Exception as exc:
            fallback_reason = f"Tkinter startup failed: {exc}"

    # --- Textual sync path --------------------------------------------------
    # Each dialog runs as a short-lived Textual App in the main thread.
    # gui_manager_queue is replaced with _TextualSyncQueue so that put() runs
    # the dialog synchronously — no manager thread is needed.
    try:
        from execsql.gui.tui import TextualBackend, _TextualSyncQueue

        _active_backend = TextualBackend()
        _state.gui_manager_queue = _TextualSyncQueue()
        if fallback_reason:
            print(f"GUI fallback: {fallback_reason}; using Textual.", file=sys.stderr)
        return
    except ImportError as exc:
        reason = f"Textual unavailable: {exc}"
        fallback_reason = f"{fallback_reason}; {reason}" if fallback_reason else reason

    # --- Thread-based manager path (ConsoleBackend fallback) ----------------
    if _state.gui_manager_thread is not None and _state.gui_manager_thread.is_alive():
        return

    import queue as _queue
    import threading
    from execsql.gui import gui_manager_loop
    from execsql.gui.console import ConsoleBackend

    backend = ConsoleBackend()
    _active_backend = backend
    print(f"GUI fallback: {fallback_reason}; using console prompts.", file=sys.stderr)

    _state.gui_manager_queue = _queue.Queue()
    t = threading.Thread(
        target=gui_manager_loop,
        args=(_state.gui_manager_queue, backend),
        daemon=True,
        name="execsql-gui-manager",
    )
    t.start()
    _state.gui_manager_thread = t


def gui_console_on() -> None:
    """Start the GUI console."""
    global _console_running
    _console_running = True
    enable_gui()
    if _active_backend is not None:
        _active_backend.console_on()


def gui_console_off() -> None:
    """Stop the GUI console."""
    global _console_running
    _console_running = False
    if _active_backend is not None:
        _active_backend.console_off()


def gui_console_hide() -> None:
    """Hide the GUI console window."""
    if _active_backend is not None:
        _active_backend.console_hide()


def gui_console_show() -> None:
    """Show the GUI console window."""
    if _active_backend is not None:
        _active_backend.console_show()


def gui_console_progress(num: float, total: float | None = None) -> None:
    """Update the progress indicator in the console."""
    if _active_backend is not None:
        _active_backend.console_progress(num, total)


def gui_console_save(outfile: str, append: bool = False) -> None:
    """Save the console contents to a file."""
    if _active_backend is not None:
        _active_backend.console_save(outfile, append)


def gui_console_status(message: str) -> None:
    """Set the status bar message in the console."""
    if _active_backend is not None:
        _active_backend.console_status(message)


def gui_console_wait_user(message: str = "") -> None:
    """Block until the user dismisses the console.

    In headless mode, prints the message and returns immediately.
    """
    if _active_backend is not None:
        _active_backend.console_wait_user(message)
    elif message:
        print(message, file=sys.stderr)


def gui_console_width(width: int | None = None) -> int:
    """Get/set the configured character width, resizing the active native console.

    A setting made before CONSOLE ON is retained. Terminal backends do not resize
    their host window. The runtime configuration takes precedence over fallback
    values from calls made without a configuration.
    """
    import execsql.state as _state

    global _console_width
    if width is not None:
        _console_width = int(width)
        if _state.conf is not None:
            _state.conf.gui_console_width = _console_width
        if _active_backend is not None:
            _active_backend.console_resize(_console_width, gui_console_height())
    return int(getattr(_state.conf, "gui_console_width", _console_width))


def gui_console_height(height: int | None = None) -> int:
    """Get/set configured text lines, retaining the size across native OFF/ON.

    Terminal backends store the setting without changing their host window.
    """
    import execsql.state as _state

    global _console_height
    if height is not None:
        _console_height = int(height)
        if _state.conf is not None:
            _state.conf.gui_console_height = _console_height
        if _active_backend is not None:
            _active_backend.console_resize(gui_console_width(), _console_height)
    return int(getattr(_state.conf, "gui_console_height", _console_height))


# ---------------------------------------------------------------------------
# Database connection GUI
# ---------------------------------------------------------------------------


def gui_connect(
    alias: str,
    message: str,
    help_url: str | None = None,
    cmd: str | None = None,
) -> None:
    """Prompt the user to select a database connection.

    Initializes the configured backend and routes through its queue when
    gui_level > 0; otherwise raises ConsoleUIError.
    """
    import queue as _queue

    import execsql.state as _state

    gui_level = _state.conf.gui_level if _state.conf else 0
    if gui_level > 0:
        enable_gui()
        return_queue: _queue.Queue = _queue.Queue()
        gui_args = {"alias": alias, "message": message, "help_url": help_url}
        _state.gui_manager_queue.put(GuiSpec(GUI_CONNECT, gui_args, return_queue))
        result = get_gui_response(return_queue, GUI_CONNECT)
        db_type = result.get("db_type")
        if db_type is None:
            raise ConsoleUIError(
                f"Database connection cancelled for alias '{alias}'.",
            )
        # Apply the selected connection to the database pool
        _apply_connect_result(alias, result)
    else:
        raise ConsoleUIError(
            f"Cannot prompt for database connection (alias '{alias}') in headless mode. "
            "Specify the database in the configuration file or on the command line.",
        )


def _apply_connect_result(alias: str, result: dict) -> None:
    """Create a database connection from the result of a connect dialog."""
    import execsql.state as _state
    from execsql.db.factory import (
        db_Access,
        db_DuckDB,
        db_Dsn,
        db_Firebird,
        db_MySQL,
        db_Oracle,
        db_Postgres,
        db_SQLite,
        db_SqlServer,
    )

    from execsql.gui.base import connection_result
    from execsql.utils.fileio import register_secret

    try:
        inputs = connection_result(
            result.get("db_type", "l"),
            result.get("server") or "",
            (result.get("db_file") or result.get("database") or "")
            if result.get("db_type") in ("l", "k", "a")
            else result.get("database") or "",
            result.get("username") or "",
            result.get("password") or "",
            result.get("port"),
            result.get("encoding") or "",
        )
    except ValueError as exc:
        raise ConsoleUIError(str(exc)) from exc
    db_type = inputs["db_type"]
    database = inputs["database"] or ""
    db_file = inputs["db_file"] or ""
    server = inputs["server"] or ""
    password = inputs["password"]
    if password:
        register_secret(password)
    auth: dict[str, Any] = {
        "user": inputs["username"],
        "pw_needed": bool(password),
        "password": password,
        "encoding": inputs["encoding"],
    }
    network = dict(**auth, port=inputs["port"])
    db: Any
    if db_type == "p":
        db = db_Postgres(server, database, **network)
    elif db_type == "s":
        db = db_SqlServer(server, database, **network)
    elif db_type == "l":
        db = db_SQLite(db_file)
    elif db_type == "m":
        db = db_MySQL(server, database, **network)
    elif db_type == "k":
        db = db_DuckDB(db_file)
    elif db_type == "o":
        db = db_Oracle(server, database, **network)
    elif db_type == "f":
        db = db_Firebird(server, database, **network)
    elif db_type == "a":
        db = db_Access(db_file)
    elif db_type == "d":
        db = db_Dsn(database, **auth)
    else:
        raise ConsoleUIError(f"Unknown database type from connect dialog: {db_type!r}")

    _state.dbs.add(alias, db)


def gui_credentials(
    message: str = "",
    username: str | None = None,
    pwtext: str | None = None,
    cmd: str | None = None,
) -> None:
    """Prompt the user for credentials.

    Initializes the configured GUI transport when gui_level > 0; level zero
    uses terminal input. Cancellation follows CANCEL_HALT without assigning
    empty credentials over existing values when halting is off.

    Parameters
    ----------
    message:
        Optional explanatory text to display.
    username:
        Substitution variable name for the username result (e.g. ``"$USER"``).
    pwtext:
        Substitution variable name for the password result (e.g. ``"$PASS"``).
    cmd:
        The originating metacommand line (for logging only).
    """
    import getpass as _getpass
    import queue as _queue

    import execsql.state as _state

    gui_level = _state.conf.gui_level if _state.conf else 0
    if gui_level > 0:
        enable_gui()
        return_queue: _queue.Queue = _queue.Queue()
        gui_args = {"message": message}
        _state.gui_manager_queue.put(GuiSpec(GUI_CREDENTIALS, gui_args, return_queue))
        result = get_gui_response(return_queue, GUI_CREDENTIALS)
        if result.get("cancelled"):
            if _state.status.cancel_halt:
                from execsql.script import current_script_line
                from execsql.utils.errors import exit_now

                for name in (username, pwtext):
                    if name:
                        _state.subvars.remove_substitution(name)
                _state.exec_log.log_exit_halt(*current_script_line(), msg="Quit from prompt for credentials.")
                exit_now(2, None)
            return
        uname = result.get("username", "")
        passwd = result.get("password", "")
    else:
        if message:
            print(message, file=sys.stderr)
        uname = input("Username: ")
        passwd = _getpass.getpass(f"Password for {uname}: ")

    if username:
        _state.subvars.add_substitution(username, uname)
    if pwtext:
        _state.subvars.add_substitution(pwtext, passwd)
        from execsql.utils.fileio import register_secret

        register_secret(passwd)


# ---------------------------------------------------------------------------
# Interactive prompts — console fallbacks (always available)
# ---------------------------------------------------------------------------


def get_yn(prompt: str) -> str:
    """Prompt for a yes/no answer on the terminal.

    Returns:
        ``"y"`` or ``"n"``, or ``chr(27)`` (ESC) if the user aborts via EOF
        (Ctrl-D / piped stdin closed). Matches the upstream v1.130.1
        ``get_yn`` character contract expected by callers such as ``x_ask``.
    """
    while True:
        try:
            answer = input(f"{prompt} [y/n]: ").strip().lower()
        except EOFError:
            return chr(27)
        if answer in ("y", "yes"):
            return "y"
        if answer in ("n", "no"):
            return "n"
        print("Please enter y or n.", file=sys.stderr)


def get_yn_win(prompt: str) -> str:
    """GUI yes/no dialog — falls back to terminal in headless mode."""
    return get_yn(prompt)


def _clear_progress_line() -> None:
    """Erase the SIGALRM progress bar line and move to the next line."""
    # \r returns to column 0, the spaces overwrite the bar, then \n advances.
    sys.stdout.write("\r" + " " * 50 + "\r\n")
    sys.stdout.flush()


def pause(
    text: str,
    action: str | None = None,
    countdown: float | None = None,
    timeunit: str | None = None,
) -> int:
    """Display a pause message and wait for the user (POSIX).

    Returns 0 (user continued), 1 (user quit/ESC), or 2 (timed out).

    Uses raw-mode terminal reading so that single keypresses (Enter, Esc)
    are detected without requiring the user to press Enter first.  When
    *countdown* is set, a SIGALRM-based progress bar is displayed via
    :class:`~execsql.utils.timer.TimerHandler`.

    Note: *countdown* is expected in **seconds** — the caller (``x_pause``)
    has already converted minutes to seconds, so *timeunit* is not used here.
    """
    print(f"\n{text}", file=sys.stderr)

    # When stdin is not a real TTY (pytest, piped input, etc.) or the
    # platform lacks POSIX terminal APIs (Windows), fall back to simple
    # blocking behaviour.
    if sys.platform == "win32" or not hasattr(sys.stdin, "fileno") or not sys.stdin.isatty():
        if countdown is not None and action is not None:
            import time

            time.sleep(float(countdown))
            return 2
        try:
            input("Press Enter to continue...")
        except EOFError:
            pass
        return 0

    # POSIX-only imports — guarded by the isatty() check above so this
    # function can still be called safely on Windows (falls back above).
    import signal
    import termios
    import tty

    from execsql.exceptions import ExecSqlTimeoutError
    from execsql.utils.timer import TimerHandler

    if countdown is None or action is None:
        sys.stderr.write("Press Enter to continue, Esc to quit...\n")
        sys.stderr.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    timer_handler: TimerHandler | None = None
    old_alarm: Any = signal.SIG_DFL

    try:
        tty.setraw(fd)

        if countdown is not None and action is not None:
            seconds = float(countdown)
            timer_handler = TimerHandler(seconds)
            old_alarm = signal.signal(signal.SIGALRM, timer_handler.alarm_handler)
            signal.setitimer(signal.ITIMER_REAL, 0.01, 0.01)

        has_bar = countdown is not None and action is not None

        while True:
            try:
                ch = sys.stdin.read(1)
            except ExecSqlTimeoutError:
                # TimerHandler raised — countdown expired.
                _clear_progress_line()
                return 2  # timed out
            if ch in ("\r", "\n"):
                if has_bar:
                    _clear_progress_line()
                return 0  # user continued
            if ch == "\x1b":
                if has_bar:
                    _clear_progress_line()
                return 1  # user quit (ESC)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if timer_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_alarm)


def pause_win(
    text: str,
    action: str | None = None,
    countdown: float | None = None,
    timeunit: str | None = None,
) -> int:
    """Display a pause message and wait for the user (Windows).

    Returns 0 (user continued), 1 (user quit/ESC), or 2 (timed out).

    Uses ``msvcrt.kbhit()``/``msvcrt.getwch()`` for non-blocking single-char
    reads with a polling loop that renders a text-mode progress bar when
    *countdown* is set.  Falls back to :func:`pause` on non-Windows platforms.

    Note: *countdown* is expected in **seconds** — the caller (``x_pause``)
    has already converted minutes to seconds, so *timeunit* is not used here.
    """
    try:
        import msvcrt

        msvcrt_mod: Any = msvcrt
    except ImportError:
        # Not on Windows — delegate to the POSIX implementation.
        return pause(text, action=action, countdown=countdown, timeunit=timeunit)

    import time

    print(f"\n{text}", file=sys.stderr)

    if countdown is not None and action is not None:
        seconds = float(countdown)
        start = time.time()
        bar_len = 30
        while True:
            elapsed = time.time() - start
            remaining = max(0.0, seconds - elapsed)
            if remaining <= 0:
                _clear_progress_line()
                return 2  # timed out
            bar_left = int(round(bar_len * remaining / seconds, 0))
            sys.stdout.write(
                "{:8.1f}  |{}{}|\r".format(remaining, "+" * bar_left, "-" * (bar_len - bar_left)),
            )
            sys.stdout.flush()
            if msvcrt_mod.kbhit():
                ch = msvcrt_mod.getwch()
                if ch in ("\r", "\n"):
                    _clear_progress_line()
                    return 0
                if ch == "\x1b":
                    _clear_progress_line()
                    return 1
            time.sleep(0.01)
    else:
        sys.stderr.write("Press Enter to continue, Esc to quit...\n")
        sys.stderr.flush()
        while True:
            if msvcrt_mod.kbhit():
                ch = msvcrt_mod.getwch()
                if ch in ("\r", "\n"):
                    return 0
                if ch == "\x1b":
                    return 1
            time.sleep(0.01)
