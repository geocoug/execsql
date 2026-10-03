"""A database or driver error names the problem on screen; where execsql caught it goes to the log only.

Upstream appended "in <file> on line N of execsql", a line of its own
source, to every such message.  In the package that became a path into the
installed code, often a driver's file paired with a line number from another
file, which says nothing about the script.  The script line is already shown.
"""

from __future__ import annotations

import subprocess
import sys


def test_the_screen_shows_the_error_and_the_log_shows_where_it_was_raised(tmp_path):
    script = tmp_path / "dup.sql"
    script.write_text("create table t (a integer);\ncreate table t (a integer);\n")
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "run", str(script), "--dsn", f"sqlite:///{tmp_path / 't.db'}", "-n"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "table t already exists" in result.stderr
    assert "of execsql" not in result.stderr
    assert ".py" not in result.stderr

    log = (tmp_path / "execsql.log").read_text()
    error_lines = [line for line in log.splitlines() if "table t already exists" in line]
    assert error_lines and all("of execsql" not in line for line in error_lines)
    assert any("Raised at: execsql/" in line for line in error_lines)
