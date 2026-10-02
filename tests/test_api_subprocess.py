"""``execsql.run()`` called from a real program, not from inside pytest.

In-process tests cannot see what happens to the caller's own program.  Under
the ``spawn`` start method (the default on macOS and Windows) any child process
re-imports the caller's ``__main__``; a script without an
``if __name__ == "__main__":`` guard then ran its SQL a second time.  These
tests run small caller scripts with a fresh interpreter, forcing ``spawn`` so
Linux behaves like macOS and Windows.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import textwrap

import pytest

_BODY = """
import multiprocessing
import sys

import execsql

multiprocessing.set_start_method("spawn", force=True)  # what macOS and Windows use
db, out = sys.argv[1], sys.argv[2]
result = execsql.run(
    sql=f'create table if not exists t (x integer);\\ninsert into t values (1);\\n-- !x! WRITE "hello" TO {out}\\n',
    dsn=f"sqlite:///{db}",
    new_db=True,
)
print("success", result.success, flush=True)
"""


def _guarded(body: str) -> str:
    return "def main():\n" + textwrap.indent(body, "    ") + '\n\nif __name__ == "__main__":\n    main()\n'


@pytest.mark.parametrize("script", [_BODY, _guarded(_BODY)], ids=["unguarded", "guarded"])
def test_a_caller_script_runs_its_sql_exactly_once(tmp_path, script):
    caller = tmp_path / "caller.py"
    caller.write_text(script)
    db, out = tmp_path / "ins.db", tmp_path / "out.txt"

    proc = subprocess.run(
        [sys.executable, str(caller), str(db), str(out)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("success True") == 1, proc.stdout + proc.stderr
    with sqlite3.connect(db) as conn:
        assert conn.execute("select count(*) from t").fetchone()[0] == 1
    assert out.read_text() == "hello\n"


def test_run_starts_no_child_process(tmp_path, monkeypatch):
    from multiprocessing.process import BaseProcess

    from execsql import api

    started = []
    monkeypatch.setattr(BaseProcess, "start", lambda self: started.append(self))
    result = api.run(
        sql=f'-- !x! WRITE "hello" TO {tmp_path / "out.txt"}\nselect 1;\n',
        dsn=f"sqlite:///{tmp_path / 'api.db'}",
        new_db=True,
    )
    assert result.success, result.errors
    assert started == []
    assert (tmp_path / "out.txt").read_text() == "hello\n"
