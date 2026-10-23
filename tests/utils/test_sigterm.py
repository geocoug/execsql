"""``execsql.utils.sigterm``: the CLI's SIGTERM handler and ``sigterm_held``.

The handler is called directly, so these run on every platform; a real
signal is sent in ``tests/cli/test_sigterm.py``.
"""

from __future__ import annotations

import signal
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
import execsql.utils.sigterm as sigterm
from execsql.utils.sigterm import command, sigterm_held, terminate

#: A command that runs until it is stopped.
SLEEP = [sys.executable, "-c", "import time; time.sleep(60)"]

# tests/conftest.py resets the module's state before each test.


@pytest.fixture
def exec_log():
    _state.exec_log = MagicMock()
    return _state.exec_log


def test_a_sigterm_ends_the_run_at_once(exec_log):
    with pytest.raises(SystemExit) as exc:
        terminate(signal.SIGTERM, None)
    assert exc.value.code == 128 + signal.SIGTERM
    exec_log.log_exit_terminated.assert_called_once_with()


def test_a_held_sigterm_ends_the_run_when_the_block_ends(exec_log):
    done = []
    with pytest.raises(SystemExit) as exc, sigterm_held():
        terminate(signal.SIGTERM, None)
        done.append("rest of the block")
    assert done == ["rest of the block"]
    assert exc.value.code == 128 + signal.SIGTERM
    exec_log.log_exit_terminated.assert_called_once_with()


def test_nested_blocks_act_on_it_when_the_outermost_ends(exec_log):
    done = []
    with pytest.raises(SystemExit), sigterm_held():
        with sigterm_held():
            terminate(signal.SIGTERM, None)
        done.append("after the inner block")
    assert done == ["after the inner block"]


def test_a_held_sigterm_wins_over_the_blocks_exception(exec_log):
    with pytest.raises(SystemExit) as exc, sigterm_held():
        terminate(signal.SIGTERM, None)
        raise FileNotFoundError("no such command")
    assert isinstance(exc.value.__context__, FileNotFoundError)


def test_a_block_without_a_sigterm_changes_nothing(exec_log):
    with sigterm_held():
        pass
    with pytest.raises(ValueError), sigterm_held():
        raise ValueError
    exec_log.log_exit_terminated.assert_not_called()
    with pytest.raises(SystemExit):
        terminate(signal.SIGTERM, None)


def test_a_second_sigterm_ends_the_run_again(exec_log):
    """A second SIGTERM still raises, so it can break out of a shutdown that
    hangs (an exit handler closing a dead connection)."""
    with pytest.raises(SystemExit):
        terminate(signal.SIGTERM, None)
    with pytest.raises(SystemExit):
        terminate(signal.SIGTERM, None)


def test_a_sigterm_held_then_acted_on_is_not_acted_on_again(exec_log):
    """The held SIGTERM is acted on by a second SIGTERM before the block's end
    gets to it; a later block must not find it still pending."""
    sigterm._pending = signal.SIGTERM
    with pytest.raises(SystemExit):
        terminate(signal.SIGTERM, None)
    with sigterm_held():
        pass
    exec_log.log_exit_terminated.assert_called_once_with()


def test_off_the_main_thread_nothing_is_held(exec_log):
    """The handler runs on the main thread, so a hold on another thread (the
    Textual console's script thread) must not keep the main thread running."""
    inside, release = threading.Event(), threading.Event()

    def script_thread():
        with sigterm_held():
            inside.set()
            release.wait(10)

    thread = threading.Thread(target=script_thread)
    thread.start()
    try:
        assert inside.wait(10)
        with pytest.raises(SystemExit):
            terminate(signal.SIGTERM, None)
    finally:
        release.set()
        thread.join(10)
    assert sigterm._pending is None
    exec_log.log_exit_terminated.assert_called_once_with()


def test_a_sigterm_stops_a_running_command_before_the_run_ends(exec_log):
    """Whatever the script is doing when the SIGTERM lands (waiting on the
    command, or handling its timeout), the handler kills and reaps it."""
    with pytest.raises(SystemExit), command(SLEEP) as proc:
        with pytest.raises(SystemExit):
            terminate(signal.SIGTERM, None)
        # Killed already, before the block ends: it ends long before its sleep.
        proc.wait(timeout=10)
    assert sigterm._commands == []


def test_a_command_the_os_will_not_kill_does_not_stop_the_exit(exec_log):
    """Killing a command that runs as another user fails with EPERM; the run
    still ends, and the other commands are still killed."""
    with pytest.raises(SystemExit), command(SLEEP) as first, command(SLEEP) as second:
        with (
            patch.object(first, "kill", side_effect=PermissionError(1, "Operation not permitted")),
            pytest.raises(SystemExit) as exc,
        ):
            terminate(signal.SIGTERM, None)
        assert exc.value.code == 128 + signal.SIGTERM
        exec_log.log_exit_terminated.assert_called_once_with()
        second.wait(timeout=10)
        first.kill()


def test_a_script_thread_stops_when_the_run_is_terminated(exec_log):
    """The Textual console runs the script on another thread, which the
    handler does not interrupt: its command is killed, and the thread ends
    there instead of running the rest of the script, or another command."""
    started, outcome = threading.Event(), []

    def script_thread():
        try:
            with command(SLEEP) as proc:
                started.set()
                proc.communicate()
            outcome.append("carried on after the command")
            with command(SLEEP):
                outcome.append("started another command")
        except SystemExit as e:
            outcome.append(e.code)

    thread = threading.Thread(target=script_thread)
    thread.start()
    assert started.wait(10)
    with pytest.raises(SystemExit):
        terminate(signal.SIGTERM, None)
    thread.join(10)
    assert not thread.is_alive()
    assert outcome == [128 + signal.SIGTERM]
    assert sigterm._commands == []


def test_no_command_starts_after_the_run_is_terminated(exec_log):
    sigterm._terminated = signal.SIGTERM
    with patch("subprocess.Popen") as popen, pytest.raises(SystemExit), command(SLEEP):
        pass
    popen.assert_not_called()


def test_leaving_the_block_stops_the_command():
    with pytest.raises(KeyboardInterrupt), command(SLEEP) as proc:
        raise KeyboardInterrupt
    assert proc.returncode is not None
    assert sigterm._commands == []


def test_a_finished_command_is_left_as_it_ended():
    with command([sys.executable, "-c", "raise SystemExit(3)"]) as proc:
        proc.communicate()
    assert proc.returncode == 3
    assert sigterm._commands == []
