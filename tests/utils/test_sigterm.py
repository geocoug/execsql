"""``execsql.utils.sigterm``: the CLI's SIGTERM handler and ``sigterm_held``.

The handler is called directly, so these run on every platform; a real
signal is sent in ``tests/cli/test_sigterm.py``.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
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
    command, or handling its timeout), the handler kills the command.

    The block's end raises the run's SystemExit again, which would hide a
    failed assertion inside it, so results are checked after it.
    """
    seen = {}
    with pytest.raises(SystemExit), command(SLEEP) as proc:
        try:
            terminate(signal.SIGTERM, None)
        except SystemExit as e:
            seen["code"] = e.code
            # Killed already, before the block ends: it ends long before its sleep.
            seen["ended"] = proc.wait(timeout=10) is not None
    assert seen == {"code": 128 + signal.SIGTERM, "ended": True}
    assert sigterm._commands == []


def test_a_command_the_os_will_not_kill_does_not_stop_the_exit(exec_log):
    """Killing a command that runs as another user fails with EPERM; the run
    still ends, and the other commands are still killed."""
    seen = {}
    with pytest.raises(SystemExit), command(SLEEP) as first, command(SLEEP) as second:
        with patch.object(first, "kill", side_effect=PermissionError(1, "Operation not permitted")):
            try:
                terminate(signal.SIGTERM, None)
            except SystemExit as e:
                seen["code"] = e.code
        seen["second ended"] = second.wait(timeout=10) is not None
    assert seen == {"code": 128 + signal.SIGTERM, "second ended": True}
    exec_log.log_exit_terminated.assert_called_once_with()


def test_a_command_the_os_will_not_kill_is_not_waited_for():
    with (
        patch.object(sigterm, "_kill", return_value=False),
        patch.object(subprocess.Popen, "wait") as wait,
        command(SLEEP) as proc,
    ):
        pass
    wait.assert_not_called()
    assert proc.poll() is None
    proc.kill()
    proc.wait()


def test_a_command_started_as_the_handler_runs_is_killed_by_the_handler(exec_log):
    """The handler runs while the script thread is still inside Popen(), and
    the script thread does not run again (a daemon thread, once the main
    thread exits): the handler waits for the command to be listed and kills
    it itself."""
    forked, resume, outcome, started = threading.Event(), threading.Event(), [], []
    real_popen, real_end_if_terminated = subprocess.Popen, sigterm._end_if_terminated
    checks = 0

    def popen_slowly(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        started.append(proc)
        forked.set()
        time.sleep(0.2)
        return proc

    def end_if_terminated():
        nonlocal checks
        if threading.current_thread() is not threading.main_thread():
            checks += 1
            if checks == 2:  # just after the command is started
                resume.wait(10)
        real_end_if_terminated()

    def script_thread():
        try:
            with command(SLEEP) as proc:
                outcome.append("ran the block")
                proc.communicate()
        except SystemExit as e:
            outcome.append(e.code)

    with (
        patch("subprocess.Popen", popen_slowly),
        patch.object(sigterm, "_end_if_terminated", end_if_terminated),
    ):
        thread = threading.Thread(target=script_thread)
        thread.start()
        try:
            assert forked.wait(10)
            with pytest.raises(SystemExit):
                terminate(signal.SIGTERM, None)
            ended = started[0].wait(timeout=5)
        finally:
            if started[0].poll() is None:
                started[0].kill()
            resume.set()
            thread.join(10)
    assert ended is not None  # ended long before its sleep: killed
    assert outcome == [128 + signal.SIGTERM]
    assert sigterm._commands == []


def test_a_command_being_stopped_stays_listed_until_it_is_killed(exec_log):
    """The script thread is leaving the block, about to kill its command, and
    does not run again: the handler still finds the command and kills it."""
    stopping, resume, started = threading.Event(), threading.Event(), []
    real_kill = sigterm._kill

    def kill(proc):
        if threading.current_thread() is not threading.main_thread():
            stopping.set()
            resume.wait(10)
        return real_kill(proc)

    def script_thread():
        try:
            with command(SLEEP) as proc:
                started.append(proc)
        except SystemExit:
            pass

    with patch.object(sigterm, "_kill", kill):
        thread = threading.Thread(target=script_thread)
        thread.start()
        try:
            assert stopping.wait(10)
            with pytest.raises(SystemExit):
                terminate(signal.SIGTERM, None)
            ended = started[0].wait(timeout=5)
        finally:
            if started[0].poll() is None:
                started[0].kill()
            resume.set()
            thread.join(10)
    assert ended is not None  # ended long before its sleep: killed
    assert sigterm._commands == []


def test_a_sigterm_as_the_block_is_left_waits_for_the_command_to_be_reaped(exec_log):
    """The block's cleanup holds a SIGTERM back, so the command is reaped
    before the run ends, not left half stopped."""
    real_kill = sigterm._kill

    def kill_then_sigterm(proc):
        killed = real_kill(proc)
        if not sigterm._terminated:
            terminate(signal.SIGTERM, None)
        return killed

    with patch.object(sigterm, "_kill", kill_then_sigterm), pytest.raises(SystemExit), command(SLEEP) as proc:
        pass
    assert proc.returncode is not None
    assert sigterm._commands == []


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
