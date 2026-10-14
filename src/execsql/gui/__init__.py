"""The GUI manager thread for execsql.

Usage
-----
Call ``enable_gui()`` (via ``execsql.utils.gui``) to initialise the backend
and start the manager thread.  All dialog requests are then placed on
``_state.gui_manager_queue`` as ``GuiSpec`` objects and dispatched by
``gui_manager_loop()``.

``enable_gui()`` picks the backend by framework, not by level:

    framework "tkinter" → TkinterBackend → TextualBackend → ConsoleBackend
    framework "textual" → TextualBackend → ConsoleBackend
"""

from __future__ import annotations

import queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execsql.gui.base import GuiBackend

__all__ = ["gui_manager_loop"]


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
