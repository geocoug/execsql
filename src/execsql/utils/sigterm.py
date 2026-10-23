from __future__ import annotations

"""
SIGTERM handling for the ``execsql`` command.

:func:`terminate` is the handler the console entry point installs: it ends
the run through ``SystemExit`` (exit status 143), so exit handlers run and
the log is written.  :func:`sigterm_held` holds a SIGTERM back for the few
lines where raising would leave something behind — while ``SYSTEM_CMD``
starts its command, ``Popen`` has forked the child but not yet returned it,
so nothing could stop the child — and acts on it as the block ends.

The library API (``execsql.run()``) does not install the handler, so there
:func:`sigterm_held` holds nothing back.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

#: Depth of nested :func:`sigterm_held` blocks.
_held = 0
#: The signal number of a SIGTERM that arrived while held.
_pending: int | None = None


def terminate(signum: int, _frame: Any) -> None:
    """Record a ``terminated`` exit and raise ``SystemExit(128 + signum)``.

    Inside a :func:`sigterm_held` block the signal is only noted; the block's
    end acts on it.
    """
    global _pending
    if _held:
        _pending = signum
        return
    _exit(signum)


def _exit(signum: int) -> None:
    import execsql.state as _state

    if _state.exec_log is not None:
        _state.exec_log.log_exit_terminated()
    raise SystemExit(128 + signum)


@contextmanager
def sigterm_held() -> Iterator[None]:
    """Hold back a SIGTERM until the block ends, then end the run with it.

    Keep the block short: a run asked to stop waits for it.  An exception
    the block raises gives way to the held SIGTERM.
    """
    global _held, _pending
    _held += 1
    try:
        yield
    finally:
        _held -= 1
        if not _held and _pending is not None:
            signum, _pending = _pending, None
            _exit(signum)
