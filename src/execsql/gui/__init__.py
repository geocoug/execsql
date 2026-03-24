"""GUI backend factory and manager thread for execsql.

Usage
-----
Call ``enable_gui()`` (via ``execsql.utils.gui``) to initialise the backend
and start the manager thread.  All dialog requests are then placed on
``_state.gui_manager_queue`` as ``GuiSpec`` objects and dispatched by
``gui_manager_loop()``.

Backend selection (framework-based, not level-based):

    framework "tkinter" → TkinterBackend → TextualBackend → ConsoleBackend
    framework "textual" → TextualBackend → ConsoleBackend
"""

from __future__ import annotations

import queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execsql.gui.base import GuiBackend


def get_backend(framework: str = "tkinter") -> GuiBackend:
    """Return the best available backend for *framework*.

    Falls back gracefully if the preferred backend's dependencies are missing.
    """
    if framework == "tkinter":
        try:
            from execsql.gui.desktop import TkinterBackend

            backend = TkinterBackend()
            backend.start()
            return backend
        except (ImportError, RuntimeError, Exception):
            pass

    # Textual path (framework == "textual", or tkinter unavailable)
    try:
        from execsql.gui.tui import TextualBackend

        return TextualBackend()
    except ImportError:
        pass

    from execsql.gui.console import ConsoleBackend

    return ConsoleBackend()


def gui_manager_loop(q: queue.Queue[Any], backend: GuiBackend) -> None:
    """GUI manager thread main loop.

    Reads ``GuiSpec`` objects from *q*, dispatches each to *backend*, and
    puts the result dict back onto ``spec.return_queue``.

    Terminates when it receives ``None`` as a sentinel value.
    """
    while True:
        spec = q.get()
        if spec is None:
            break
        try:
            result = backend.dispatch(spec)
        except Exception as exc:
            result = {"error": str(exc), "button": None}
        spec.return_queue.put(result)
