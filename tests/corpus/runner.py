"""Run one corpus case under a given execsql and collect what the script compatibility contract covers.

A case is a directory under ``tests/corpus/cases/`` holding ``script.sql``
and any files the script reads.  It is copied to an empty working
directory and run as ``execsql -t l -n script.sql t.db`` there, with
``HOME`` (and on Windows ``USERPROFILE`` and ``APPDATA``) pointed at an
empty directory so no user configuration file is read.  What comes back:

- ``exit``: the exit status.
- ``stdout`` / ``stderr``: the console output.
- ``files``: every file the run left in the working directory except the
  database, the copied inputs and ``execsql.log``, as text, as its tables
  (an SQLite database a script created), or as base64 (other binary content).
- ``tables``: every table in ``t.db``: its columns with their declared
  types, and its rows in insertion order, each value as ``[typeof, repr]``
  so a ``1`` stored as text differs from a ``1`` stored as an integer.

Variable values are compared through files: a case ``WRITE``s the
variables it checks, because upstream has no way to read them after a run.
The working directory's path is replaced with ``<DIR>`` everywhere, and
the time in ``Error occurred at …`` with ``<TIME>``, and upstream's
`` in …/execsql.py on line N of execsql.`` (a place in its own source) is
dropped, so results recorded on
one machine at one time compare on another.  Line endings are compared as
``\n``: the results were recorded on a POSIX system, and on Windows both
programs write text files with ``\r\n``.  Standard input is empty, so a
prompt cannot wait for an answer.

``execsql.log`` is left out: its records carry timestamps and a run id,
and the log format is not something a script reads.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

CORPUS = Path(__file__).resolve().parent
CASES = CORPUS / "cases"
RESULTS = CORPUS / "results"

DB_NAME = "t.db"
_SQLITE_HEADER = b"SQLite format 3\x00"
# Error reports end with the time they happened.
_ERROR_TIME = re.compile(r"Error occurred at \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\.")
# Upstream adds where in its own source an exception was raised.
_UPSTREAM_SOURCE = re.compile(r" in \S*execsql\.py on line \d+ of execsql\.")
_SKIPPED_FILES = {DB_NAME, "execsql.log"}


def case_names() -> list[str]:
    return sorted(p.name for p in CASES.iterdir() if (p / "script.sql").is_file())


def run_case(case: str, command: list[str], workdir: Path, *, timeout: int = 30) -> dict[str, Any]:
    """Run *case* with *command* (the execsql to call, without its arguments) in the empty *workdir*."""
    source = CASES / case
    shutil.copytree(source, workdir, dirs_exist_ok=True)
    inputs = {p.relative_to(workdir) for p in workdir.rglob("*") if p.is_file()}
    home = workdir.parent / f"{workdir.name}-home"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("EXECSQL")}
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "PYTHONIOENCODING": "utf-8",
        },
    )
    proc = subprocess.run(
        [*command, "-t", "l", "-n", "script.sql", DB_NAME],
        cwd=workdir,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
    )
    names = [str(workdir), os.path.realpath(workdir)]

    def clean(text: str) -> str:
        for name in sorted(set(names), key=len, reverse=True):
            text = text.replace(name, "<DIR>")
        text = text.replace("\r\n", "\n")
        return _UPSTREAM_SOURCE.sub("", _ERROR_TIME.sub("Error occurred at <TIME>.", text))

    files: dict[str, Any] = {}
    for path in sorted(workdir.rglob("*")):
        rel = path.relative_to(workdir)
        if not path.is_file() or rel in inputs or str(rel) in _SKIPPED_FILES:
            continue
        data = path.read_bytes()
        if data.startswith(_SQLITE_HEADER):
            # Compared by content: the file's bytes depend on the SQLite build.
            files[rel.as_posix()] = {"sqlite": _tables(path)}
            continue
        try:
            files[rel.as_posix()] = clean(data.decode("utf-8"))
        except UnicodeDecodeError:
            files[rel.as_posix()] = {"base64": base64.b64encode(data).decode("ascii")}
    return {
        "exit": proc.returncode,
        "stdout": clean(proc.stdout.decode("utf-8", "replace")),
        "stderr": clean(proc.stderr.decode("utf-8", "replace")),
        "files": files,
        "tables": _tables(workdir / DB_NAME),
    }


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _tables(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {}
    con = sqlite3.connect(db_path)
    try:
        names = [r[0] for r in con.execute("select name from sqlite_master where type = 'table' order by name")]
        tables: dict[str, Any] = {}
        for name in names:
            quoted = _quote(name)
            columns = [[r[1], r[2]] for r in con.execute(f"pragma table_info({quoted})")]
            select = ", ".join(f"typeof({_quote(c)}), {_quote(c)}" for c, _ in columns)
            rows = []
            for r in con.execute(f"select {select} from {quoted} order by rowid"):
                rows.append([[r[i], repr(r[i + 1])] for i in range(0, len(r), 2)])
            tables[name] = {"columns": columns, "rows": rows}
        return tables
    finally:
        con.close()
