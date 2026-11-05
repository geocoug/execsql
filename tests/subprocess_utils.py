"""CLI subprocess diagnostics shared by whole-script test harnesses."""

from __future__ import annotations

import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import Any


def run_with_traceback(command: list[str], *, timeout: float, **kwargs: Any) -> subprocess.CompletedProcess:
    """Capture a stalled CLI's stacks without changing its stdout or stderr."""
    # Keep diagnostics outside the script directory: the corpus inventories
    # every output file there, and successful scripts may outlast the watchdog.
    with tempfile.TemporaryDirectory(prefix="execsql-test-trace-") as directory:
        trace = Path(directory) / "stacks.txt"
        if command[1:3] == ["-m", "execsql"]:
            # Install before importing execsql to cover import and exit hangs.
            # Keep the stream alive until interpreter shutdown, just as stderr
            # would be. runpy preserves the normal -m entrypoint and arguments.
            bootstrap = (
                "import atexit, faulthandler, runpy, sys; "
                f"_trace_file = open({str(trace)!r}, 'w'); "
                f"faulthandler.dump_traceback_later({timeout / 2!r}, repeat=True, file=_trace_file); "
                "atexit.register(faulthandler.cancel_dump_traceback_later); "
                "sys.argv = ['execsql', *sys.argv[1:]]; "
                "runpy.run_module('execsql', run_name='__main__')"
            )
            command = [command[0], "-c", bootstrap, *command[3:]]
        try:
            result = subprocess.run(command, timeout=timeout, **kwargs)
        except subprocess.TimeoutExpired as exc:

            def readable(output):
                return output.decode("utf-8", "replace") if isinstance(output, bytes) else output or ""

            stacks = trace.read_text("utf-8", errors="replace") if trace.exists() else "No child stack captured."
            raise AssertionError(
                f"CLI exceeded {timeout}s.\nSTDOUT:\n{readable(exc.stdout)}\nSTDERR:\n{readable(exc.stderr)}"
                f"\nCHILD STACKS:\n{stacks}",
            ) from exc
        if trace.exists() and trace.stat().st_size:
            warnings.warn(
                f"Slow CLI completed within {timeout}s (exit {result.returncode}).\n"
                + trace.read_text("utf-8", errors="replace"),
                RuntimeWarning,
                stacklevel=2,
            )
        return result
