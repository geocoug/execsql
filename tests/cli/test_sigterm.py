"""SIGTERM ends a CLI run the way Ctrl-C does.

Python's default SIGTERM action stops the process without running ``atexit``
handlers, so the buffered ``execsql.log`` (every record of the run) was lost,
no explicit rollback ran, and a running ``SYSTEM_CMD`` was left behind.
CI cancellation, ``timeout``, ``docker stop`` and systemd all send SIGTERM.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX signal delivery")

# The SYSTEM_CMD child records its pid, sends SIGTERM to execsql (its parent)
# and then execs a long sleep in place of the shell, so the recorded pid is
# the process execsql must stop.
_KILL_PARENT = "-- !x! SYSTEM_CMD (sh -c 'echo $$ > child.pid; kill -TERM $PPID; exec sleep 30')\n"


def _run(tmp_path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "s.sql"
    script.write_text(body)
    (tmp_path / "execsql.conf").write_text("[config]\nallow_system_cmd = Yes\n")
    # Output goes to files, not pipes: a child left running would hold a pipe
    # open and make run() wait for it.
    with open(tmp_path / "stdout.txt", "w") as out, open(tmp_path / "stderr.txt", "w") as err:
        return subprocess.run(
            [sys.executable, "-m", "execsql", "run", str(script), "--dsn", f"sqlite:///{tmp_path / 't.db'}", "-n"],
            stdout=out,
            stderr=err,
            cwd=tmp_path,
            timeout=60,
        )


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture(autouse=True)
def _reap_child(tmp_path):
    """Kill a SYSTEM_CMD child that a failing run left behind."""
    yield
    pid_file = tmp_path / "child.pid"
    if pid_file.exists() and _alive(pid := int(pid_file.read_text())):
        os.kill(pid, signal.SIGKILL)


@posix_only
def test_sigterm_exits_143_and_writes_the_log(tmp_path):
    proc = _run(tmp_path, f"create table t (x int);\n{_KILL_PARENT}select 1;\n")
    assert proc.returncode == 143, (tmp_path / "stderr.txt").read_text()
    lines = (tmp_path / "execsql.log").read_text().splitlines()
    assert any(line.startswith("connect\t") for line in lines)
    exits = [line.split("\t") for line in lines if line.startswith("exit\t")]
    assert len(exits) == 1, exits
    assert exits[0][2] == "terminated"


@posix_only
def test_sigterm_keeps_write_output(tmp_path):
    _run(tmp_path, f'-- !x! WRITE "before the signal" TO out.txt\n{_KILL_PARENT}')
    assert (tmp_path / "out.txt").read_text() == "before the signal\n"


@posix_only
def test_sigterm_stops_a_running_system_cmd(tmp_path):
    _run(tmp_path, _KILL_PARENT)
    child = int((tmp_path / "child.pid").read_text())
    deadline = time.monotonic() + 3
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(child)


def test_a_terminated_run_does_not_wait_for_the_gui_console():
    """``gui_wait_on_exit`` holds the console open for the user; a SIGTERM must not."""
    import execsql.state as _state
    from execsql.cli.run import _execute_script_ast

    conf = _state.conf
    conf.gui_wait_on_exit = True
    with (
        patch("execsql.script.executor.execute", side_effect=SystemExit(143)),
        patch("execsql.cli.run.gui_console_isrunning", return_value=True),
        patch("execsql.cli.run.gui_console_wait_user") as wait,
        patch("execsql.cli.run.gui_console_off"),
        patch.object(_state, "exec_log", MagicMock(exit_type="terminated")),
        pytest.raises(SystemExit) as exc,
    ):
        _execute_script_ast(object(), conf)
    assert exc.value.code == 143
    wait.assert_not_called()
