"""Shared helpers for integration tests.

Each backend-specific test module provides its own ``_write_conf`` and
verification helpers.  The helpers here are backend-agnostic.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def write_script(tmp_path, sql_text, name="test_script.sql"):
    """Write a .sql script file into *tmp_path*."""
    script = tmp_path / name
    script.write_text(textwrap.dedent(sql_text))
    return script


def run_execsql(tmp_path, script_path, extra_args=None, timeout=30):
    """Run execsql on the given script via subprocess.

    Returns the completed process.  The working directory is set to *tmp_path*
    so that execsql.conf is picked up automatically.
    """
    cmd = [sys.executable, "-m", "execsql", str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
