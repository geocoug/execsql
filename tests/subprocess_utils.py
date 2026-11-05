"""CLI subprocess diagnostics shared by whole-script test harnesses."""

from __future__ import annotations

import subprocess
from typing import Any


def run_with_traceback(command: list[str], *, timeout: float, **kwargs: Any) -> subprocess.CompletedProcess:
    """Capture a stalled CLI's stacks before the existing test timeout expires."""
    if command[1:3] == ["-m", "execsql"]:
        # Install the watchdog before importing execsql, so import hangs and
        # interpreter shutdown are visible too. runpy preserves -m behavior.
        bootstrap = (
            "import faulthandler, runpy, sys; "
            f"faulthandler.dump_traceback_later({timeout / 2!r}, repeat=True); "
            "sys.argv = ['execsql', *sys.argv[1:]]; "
            "runpy.run_module('execsql', run_name='__main__')"
        )
        command = [command[0], "-c", bootstrap, *command[3:]]
    try:
        return subprocess.run(command, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as exc:

        def readable(output):
            return output.decode("utf-8", "replace") if isinstance(output, bytes) else output or ""

        raise AssertionError(
            f"CLI exceeded {timeout}s.\nSTDOUT:\n{readable(exc.stdout)}\nSTDERR:\n{readable(exc.stderr)}",
        ) from exc
