from __future__ import annotations

"""
SIGTERM handling for the ``execsql`` command.

:func:`terminate` is the handler the console entry point installs: it kills
the commands ``SYSTEM_CMD`` is waiting on, then ends the run through
``SystemExit`` (exit status 143), so exit handlers run and the log is
written.  :func:`command` starts such a command; :func:`sigterm_held` holds
a SIGTERM back for the few lines where raising would leave something
behind, and acts on it as the block ends.

Python runs signal handlers on the main thread only, between bytecodes.  A
hold therefore counts only on the main thread: a SIGTERM raised there in the
middle of ``Popen()`` (which forks the command before it returns) would
leave the command running with nothing to stop it.  The Textual console runs
the script on another thread, which the handler never interrupts; that
thread stops at its next command instead (see :func:`command`).

The library API (``execsql.run()``) does not install the handler, so there
:func:`sigterm_held` holds nothing back and :func:`command` only stops its
command when the block is left.
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
#: The signal number of the SIGTERM that ended the run.
_terminated: int | None = None
#: Commands started by :func:`command` and not yet stopped or finished.
_commands: list[subprocess.Popen] = []


def terminate(signum: int, _frame: Any) -> None:
    """Kill the running commands, record a ``terminated`` exit and raise ``SystemExit(128 + signum)``.

    Inside a :func:`sigterm_held` block the signal is only noted; the block's
    end acts on it.
    """
    global _pending
    if _held:
        _pending = signum
        return
    _exit(signum)


def _exit(signum: int) -> None:
    global _pending, _terminated
    import execsql.state as _state

    _pending = None
    # Set before the commands are listed: a command another thread appends
    # after the listing is stopped by that thread, which then sees this.
    _terminated = signum
    for proc in list(_commands):
        # Kill only: the handler may have interrupted Popen.wait() on this
        # command, which holds a lock a second wait() would block on forever.
        # The command() block reaps it as it is left.
        _kill(proc)
    if _state.exec_log is not None:
        _state.exec_log.log_exit_terminated()
    raise SystemExit(128 + signum)


def _kill(proc: subprocess.Popen) -> bool:
    """Kill *proc* unless it has finished; False if the OS refuses (a command running as another user)."""
    try:
        proc.kill()
    except OSError:
        return False
    return True


def _stop(proc: subprocess.Popen) -> None:
    """Kill *proc* unless it has finished, and reap it."""
    if _kill(proc):
        proc.wait()


def _end_if_terminated() -> None:
    """Raise the run's ``SystemExit`` once a SIGTERM has ended it (for a thread the handler does not interrupt)."""
    if _terminated is not None:
        raise SystemExit(128 + _terminated)


@contextmanager
def sigterm_held() -> Iterator[None]:
    """Hold back a SIGTERM until the block ends, then end the run with it.

    Keep the block short: a run asked to stop waits for it.  An exception
    the block raises gives way to the held SIGTERM.  Off the main thread it
    holds nothing, since the handler never interrupts that thread.
    """
    global _held
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
    run's ``SystemExit`` is raised.  On a thread other than the main one,
    which the handler does not interrupt, the block raises that
    ``SystemExit`` itself once the SIGTERM has ended the run, and no command
    starts after it.
    """
    proc = None
    try:
        _end_if_terminated()
        with sigterm_held():
            proc = subprocess.Popen(args)
            _commands.append(proc)
        # A SIGTERM handled on the main thread while this thread started the
        # command may have listed the commands before this one was added.
        _end_if_terminated()
        yield proc
    finally:
        if proc is not None:
            with sigterm_held():
                # Ctrl-C can land between Popen() returning and the append.
                if proc in _commands:
                    _commands.remove(proc)
                _stop(proc)
        _end_if_terminated()
