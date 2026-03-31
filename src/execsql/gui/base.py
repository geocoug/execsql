"""Abstract base class for execsql GUI backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

__all__ = ["GuiBackend"]


class GuiBackend(ABC):
    """Abstract base for all GUI backends.

    Each backend implements one method per GuiSpec type.
    ``dispatch()`` routes GuiSpec requests to the appropriate handler.

    Return value conventions:
    - ``show_halt``       → ``{"button": 1}``
    - ``show_msg``        → ``{"button": 1}``
    - ``show_pause``      → ``{"quit": bool}``
    - ``show_display``    → ``{"button": int|None, "return_value": str|None}``
    - ``show_entry_form`` → ``{"button": int|None, "return_value": list[EntrySpec]}``
    - ``show_compare``    → ``{"button": int|None}``
    - ``show_select_rows``→ ``{"button": int|None}``
    - ``show_select_sub`` → ``{"button": int|None, "row": dict|None}``
    - ``show_action``     → ``{"button": int|None}``
    - ``show_map``        → ``{"button": int|None}``
    - ``show_open_file``  → ``{"filename": str|None}``
    - ``show_save_file``  → ``{"filename": str|None}``
    - ``show_directory``  → ``{"directory": str|None}``
    - ``query_console``   → ``{"console_running": bool}``
    - ``show_credentials``→ ``{"username": str, "password": str}``
    - ``show_connect``    → ``{"db_type": str, "server": str, ...}``
    """

    def dispatch(self, spec: Any) -> dict:
        """Dispatch a GuiSpec to the appropriate handler method."""
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
        )

        handlers = {
            GUI_HALT: self.show_halt,
            GUI_MSG: self.show_msg,
            GUI_PAUSE: self.show_pause,
            GUI_DISPLAY: self.show_display,
            GUI_ENTRY: self.show_entry_form,
            GUI_COMPARE: self.show_compare,
            GUI_SELECTROWS: self.show_select_rows,
            GUI_SELECTSUB: self.show_select_sub,
            GUI_ACTION: self.show_action,
            GUI_MAP: self.show_map,
            GUI_OPENFILE: self.show_open_file,
            GUI_SAVEFILE: self.show_save_file,
            GUI_DIRECTORY: self.show_directory,
            QUERY_CONSOLE: self.query_console,
            GUI_CREDENTIALS: self.show_credentials,
            GUI_CONNECT: self.show_connect,
        }
        handler = handlers.get(spec.gui_type)
        if handler is None:
            return {"error": f"Unknown GUI type: {spec.gui_type}", "button": None}
        return handler(spec.args)

    def start(self) -> None:
        """Called when the backend is started. Override for setup."""

    def stop(self) -> None:
        """Called when the backend is stopped. Override for teardown."""

    def console_on(self) -> None:
        """Start the console window (if applicable)."""

    def console_off(self) -> None:
        """Stop the console window (if applicable)."""

    def console_hide(self) -> None:
        """Hide the console window (if applicable)."""

    def console_show(self) -> None:
        """Show the console window (if applicable)."""

    def console_progress(self, num: float, total: float | None = None) -> None:
        """Update the progress indicator."""

    def console_save(self, outfile: str, append: bool = False) -> None:
        """Save console contents to a file."""

    def console_status(self, message: str) -> None:
        """Set the status bar message."""

    def console_wait_user(self, message: str = "") -> None:
        """Block until the user dismisses the console."""

    # ------------------------------------------------------------------
    # Abstract dialog methods — must be implemented by each backend.
    # ------------------------------------------------------------------

    @abstractmethod
    def show_halt(self, args: dict) -> dict:
        """Show a HALT message dialog."""

    @abstractmethod
    def show_msg(self, args: dict) -> dict:
        """Show a message dialog."""

    @abstractmethod
    def show_pause(self, args: dict) -> dict:
        """Show a pause dialog with optional countdown."""

    @abstractmethod
    def show_display(self, args: dict) -> dict:
        """Show a data display / query result dialog."""

    @abstractmethod
    def show_entry_form(self, args: dict) -> dict:
        """Show a multi-field entry form."""

    @abstractmethod
    def show_compare(self, args: dict) -> dict:
        """Show a table comparison dialog."""

    @abstractmethod
    def show_select_rows(self, args: dict) -> dict:
        """Show a row selection dialog."""

    @abstractmethod
    def show_select_sub(self, args: dict) -> dict:
        """Show a single-row selection dialog."""

    @abstractmethod
    def show_action(self, args: dict) -> dict:
        """Show an action button grid dialog."""

    @abstractmethod
    def show_map(self, args: dict) -> dict:
        """Show a map display dialog."""

    @abstractmethod
    def show_open_file(self, args: dict) -> dict:
        """Show a file open dialog."""

    @abstractmethod
    def show_save_file(self, args: dict) -> dict:
        """Show a file save dialog."""

    @abstractmethod
    def show_directory(self, args: dict) -> dict:
        """Show a directory selection dialog."""

    @abstractmethod
    def query_console(self, args: dict) -> dict:
        """Return whether the GUI console is currently running."""

    @abstractmethod
    def show_credentials(self, args: dict) -> dict:
        """Show a credentials (username + password) dialog."""

    @abstractmethod
    def show_connect(self, args: dict) -> dict:
        """Show a database connection selection dialog."""
