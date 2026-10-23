from __future__ import annotations

"""
SIGTERM handling for the ``execsql`` command.

:func:`terminate` is the handler the console entry point installs: it stops
the commands ``SYSTEM_CMD`` is waiting on, then ends the run through
``SystemExit`` (exit status 143), so exit handlers run and the log is
written.  :func:`command` starts such a command; :func:`sigterm_held` holds
a SIGTERM back for the few lines where raising would leave something
behind, and acts on it as the block ends.

Python runs signal handlers on the main thread only, between bytecodes.  A
hold therefore counts only on the main thread: a SIGTERM raised there in the
middle of ``Popen()`` (which forks the command before it returns) would
leave the command running with nothing to stop it.  Another thread, such as
the Textual console's script thread, is never interrupted by the handler,
so it needs no hold; it takes the lock that the handler also takes before
stopping the commands.

The library API (``execsql.run()``) does not install the handler, so there
:func:`sigterm_held` holds nothing back.
"""

import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

#: Depth of nested :func:`sigterm_held` blocks on the main thread.
_held = 0
#: The signal number of a SIGTERM that arrived while held.
_pending: int | None = None
#: Set once a SIGTERM is being acted on; later ones are ignored.
_exiting = False
#: Commands started by :func:`command` and not yet stopped or finished.
_commands: list[subprocess.Popen] = []
#: Guards ``_commands`` and the start of each command.
_commands_lock = threading.Lock()


def terminate(signum: int, _frame: Any) -> None:
    """Kill the running commands, record a ``terminated`` exit and raise ``SystemExit(128 + signum)``.

    Inside a :func:`sigterm_held` block the signal is only noted; the block's
    end acts on it.
    """
    global _pending
    if _exiting:
        return
    if _held:
        _pending = signum
        return
    _exit(signum)


def _exit(signum: int) -> None:
    global _exiting, _pending
    import execsql.state as _state

    # The run ends once, however many SIGTERMs arrive: a second one re-entering
    # this handler would wait forever on the lock below, or log a second exit.
    _exiting = True
    _pending = None
    with _commands_lock:
        for proc in _commands:
            # Kill only: the handler may have interrupted Popen.wait() on this
            # command, which holds a lock a second wait() would block on
            # forever.  The command() block reaps it as SystemExit unwinds.
            proc.kill()
    if _state.exec_log is not None:
        _state.exec_log.log_exit_terminated()
    raise SystemExit(128 + signum)


def _stop(proc: subprocess.Popen) -> None:
    """Kill *proc* unless it has finished, and reap it."""
    proc.kill()
    proc.wait()


@contextmanager
def sigterm_held() -> Iterator[None]:
    """Hold back a SIGTERM until the block ends, then end the run with it.

    Keep the block short: a run asked to stop waits for it.  An exception
    the block raises gives way to the held SIGTERM.  Off the main thread it
    holds nothing, since the handler never interrupts that thread.
    """
    global _held, _pending
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    _held += 1
    try:
        yield
    finally:
        _held -= 1
        if not _held and _pending is not None:
            _exit(_pending)


@contextmanager
def command(args: list[str]) -> Iterator[subprocess.Popen]:
    """Start *args* as a command that is stopped when the block ends or the run is terminated.

    Leaving the block, however it is left (the command finished, a timeout,
    Ctrl-C, a SIGTERM), kills the command if it is still running and reaps
    it.  A SIGTERM at any point after the command starts kills it before the
    run's ``SystemExit`` is raised, so no gap is left between the moment it
    lands and the block's end.
    """
    proc = None
    try:
        with sigterm_held(), _commands_lock:
            proc = subprocess.Popen(args)
            _commands.append(proc)
        yield proc
    finally:
        if proc is not None:
            with sigterm_held(), _commands_lock:
                _commands.remove(proc)
                _stop(proc)
