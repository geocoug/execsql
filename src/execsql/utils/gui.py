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
from typing import Any

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
    """A request sent to the GUI manager thread."""

    def __init__(self, gui_type: str, args: dict, return_queue: Any) -> None:
        self.gui_type = gui_type
        self.args = args
        self.return_queue = return_queue


class ConsoleUIError(Exception):
    """Raised when a GUI / console UI operation fails."""


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
_console_width: int = 80
_console_height: int = 24
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
        return _active_backend.query_console({}).get("console_running", False)
    return _console_running


def enable_gui() -> None:
    """Ensure the GUI subsystem is ready and the manager thread is running.

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

    framework = _state.conf.gui_framework if _state.conf else "tkinter"

    # --- Tkinter sync path --------------------------------------------------
    # Tkinter must run on the main thread (required on macOS).  Use a sync
    # queue that dispatches dialogs directly in the calling thread instead of
    # routing through a background manager thread.
    if framework == "tkinter":
        try:
            from execsql.gui.desktop import TkinterBackend, _TkinterSyncQueue

            backend = TkinterBackend()
            backend.start()
            _active_backend = backend
            _state.gui_manager_queue = _TkinterSyncQueue(backend)
            return
        except (ImportError, RuntimeError, Exception):
            pass  # fall through to Textual

    # --- Textual sync path --------------------------------------------------
    # Each dialog runs as a short-lived Textual App in the main thread.
    # gui_manager_queue is replaced with _TextualSyncQueue so that put() runs
    # the dialog synchronously — no manager thread is needed.
    try:
        from execsql.gui.tui import TextualBackend, _TextualSyncQueue

        _active_backend = TextualBackend()
        _state.gui_manager_queue = _TextualSyncQueue()
        return
    except ImportError:
        pass

    # --- Thread-based manager path (ConsoleBackend fallback) ----------------
    if _state.gui_manager_thread is not None and _state.gui_manager_thread.is_alive():
        return

    import queue as _queue
    import threading
    from execsql.gui import gui_manager_loop
    from execsql.gui.console import ConsoleBackend

    backend = ConsoleBackend()
    _active_backend = backend

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


def gui_console_width() -> int:
    """Return the current console width in characters."""
    return _console_width


def gui_console_height() -> int:
    """Return the current console height in lines."""
    return _console_height


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

    Routes through the GUI manager queue when gui_level > 0 and the manager
    thread is running; otherwise raises ConsoleUIError.
    """
    import queue as _queue

    import execsql.state as _state

    gui_level = _state.conf.gui_level if _state.conf else 0
    if gui_level > 0:
        enable_gui()
        return_queue: _queue.Queue = _queue.Queue()
        gui_args = {"alias": alias, "message": message, "help_url": help_url}
        _state.gui_manager_queue.put(GuiSpec(GUI_CONNECT, gui_args, return_queue))
        result = return_queue.get(block=True)
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

    db_type = result.get("db_type", "l")
    server = result.get("server")
    database = result.get("database")
    db_file = result.get("db_file")
    username = result.get("username")

    if db_type == "p":
        db = db_Postgres(server, database, user=username, pw_needed=True)
    elif db_type == "s":
        db = db_SqlServer(server, database, user=username, pw_needed=True)
    elif db_type == "l":
        db = db_SQLite(db_file or database)
    elif db_type == "m":
        db = db_MySQL(server, database, user=username, pw_needed=True)
    elif db_type == "k":
        db = db_DuckDB(db_file or database)
    elif db_type == "o":
        db = db_Oracle(server, database, user=username, pw_needed=True)
    elif db_type == "f":
        db = db_Firebird(server, database, user=username, pw_needed=True)
    elif db_type == "a":
        db = db_Access(db_file or database)
    elif db_type == "d":
        db = db_Dsn(database, user=username, pw_needed=True)
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

    Routes through the GUI manager queue when gui_level > 0 and the manager
    thread is running; otherwise falls back to the terminal.

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
    import queue as _queue

    import execsql.state as _state
    from execsql.utils.auth import get_password

    gui_level = _state.conf.gui_level if _state.conf else 0
    if gui_level > 0 and _state.gui_manager_thread is not None and _state.gui_manager_thread.is_alive():
        return_queue: _queue.Queue = _queue.Queue()
        gui_args = {"message": message}
        _state.gui_manager_queue.put(GuiSpec(GUI_CREDENTIALS, gui_args, return_queue))
        result = return_queue.get(block=True)
        uname = result.get("username", "")
        passwd = result.get("password", "")
    else:
        if message:
            print(message, file=sys.stderr)
        uname = input("Username: ")
        passwd = get_password(f"Password for {uname}: ")

    if username:
        _state.subvars.add_substitution(username, uname)
    if pwtext:
        _state.subvars.add_substitution(pwtext, passwd)


# ---------------------------------------------------------------------------
# Interactive prompts — console fallbacks (always available)
# ---------------------------------------------------------------------------


def get_yn(prompt: str) -> bool:
    """Prompt for a yes/no answer on the terminal."""
    while True:
        answer = input(f"{prompt} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.", file=sys.stderr)


def get_yn_win(prompt: str) -> bool:
    """GUI yes/no dialog — falls back to terminal in headless mode."""
    return get_yn(prompt)


def pause(
    text: str,
    action: str | None = None,
    countdown: float | None = None,
    timeunit: str | None = None,
) -> int:
    """Display a pause message and wait for the user.

    Returns 0 (user continued), 1 (user quit), or 2 (timed out).
    In headless mode, prints the message and continues immediately unless
    countdown/action is set, in which case it sleeps then returns 2.
    """
    import time

    print(f"\n{text}", file=sys.stderr)
    if countdown is not None and action is not None:
        seconds = float(countdown)
        if timeunit and timeunit.upper() == "MINUTES":
            seconds *= 60
        time.sleep(seconds)
        return 2  # timed out
    else:
        input("Press Enter to continue...")
    return 0


def pause_win(
    text: str,
    action: str | None = None,
    countdown: float | None = None,
    timeunit: str | None = None,
) -> int:
    """GUI pause dialog — falls back to terminal in headless mode."""
    return pause(text, action=action, countdown=countdown, timeunit=timeunit)
