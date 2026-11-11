"""GUI backend dispatch and the terminal fallback's manager loop.

``execsql.utils.gui.enable_gui()`` selects a backend by configured framework::

    tkinter -> TkinterBackend -> TextualBackend -> ConsoleBackend
    textual -> TextualBackend -> ConsoleBackend

Native Tk and ordinary Textual dialogs use synchronous queue adapters that run
in the calling thread. Only the ConsoleBackend fallback starts
``gui_manager_loop()`` on a daemon manager thread. The persistent Textual CLI
console instead runs its UI on the main thread and its script on a worker,
with ``_ConsoleDialogQueue`` carrying modal requests and responses.

Every request contains a return queue. Script-side consumers receive checked
results through ``get_gui_response()`` and own error/cancellation policy. See
``docs/dev/architecture.md`` for execution modes and shutdown ownership.
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
