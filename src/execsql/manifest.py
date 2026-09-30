"""The run manifest: a JSON record of one ``execsql run``, for ``--manifest FILE``.

The manifest says what a run did — the script, the database, how many
statements ran, the files it read, wrote and deleted, the connections it
opened, and how it ended — in a form an orchestrator or an audit can read
without parsing the log. It is written when the run ends, whether it
succeeded, failed or was cancelled.

Files are recorded as the executor runs each metacommand, after variable
substitution, so paths are the ones actually used. What a metacommand touches
is decided by :mod:`execsql.metacommands.effects`. Variable values and passwords are never written:
the run log hides ``-a`` and ``--var`` values because they can be secrets, and
the manifest lists only their names.

One recorder is active per run; :func:`current` returns it, or ``None`` when
no manifest was asked for, so the executor's hooks cost one check.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from execsql import __version__

__all__ = ["RunManifest", "current", "start"]

_current: RunManifest | None = None


def current() -> RunManifest | None:
    """The active manifest recorder, or ``None`` when ``--manifest`` was not given."""
    return _current


def start(path: str, script: str | None, variables: list[str]) -> RunManifest:
    """Begin recording a run; the manifest is written to *path* when it ends."""
    global _current
    _current = RunManifest(path, script, variables)
    return _current


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class RunManifest:
    """Collects what one run does and writes it as JSON when the run ends."""

    def __init__(self, path: str, script: str | None, variables: list[str]) -> None:
        self.path = Path(path)
        self.script = script or "<inline>"
        self.variables = variables
        self.started = _now()
        self.config_files: list[str] = []
        self.database: dict[str, Any] | None = None
        self.sql_statements = 0
        self.metacommands = 0
        self.reads: list[dict[str, Any]] = []
        self.writes: list[dict[str, Any]] = []
        self.deletes: list[dict[str, Any]] = []
        self.connections: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.written = False

    # -- recording -------------------------------------------------------------

    def set_database(self, db: Any) -> None:
        """Record the initial connection: DBMS, server, database or file, user — no password."""
        self.database = {
            "dbms": db.type.dbms_id if getattr(db, "type", None) else None,
            "server": getattr(db, "server_name", None),
            "database": getattr(db, "db_name", None),
            "user": getattr(db, "user", None),
        }

    def record_sql(self) -> None:
        self.sql_statements += 1

    def record_metacommand(self, command: str, source: str, line: int, metacommandlist: Any) -> None:
        """Count a metacommand that ran, and record the files and connections it touched.

        *command* is the text after substitution, so paths are the ones used.
        """
        from execsql.metacommands.effects import effects

        self.metacommands += 1
        hit = metacommandlist.get_match(command)
        if hit is None:
            return
        mc, m = hit
        by = mc.description or command.split(None, 1)[0].upper()
        for effect in effects(mc.exec_fn.__name__, m.groupdict()):
            entry = {"source": source, "line": line, "by": by}
            if effect.role in ("connect", "use"):
                self.connections.append(
                    {**entry, "by": effect.role.upper(), "target": effect.target, "detail": effect.detail},
                )
            else:
                {"read": self.reads, "write": self.writes, "delete": self.deletes}[effect.role].append(
                    {**entry, "path": effect.target},
                )

    def record_include(self, path: str, source: str, line: int) -> None:
        self.reads.append({"source": source, "line": line, "by": "INCLUDE", "path": path})

    # -- finishing -------------------------------------------------------------

    def finish(self, exit_status: int | None, error: Any = None) -> None:
        """Write the manifest once. Later calls (the atexit fallback) do nothing."""
        if self.written:
            return
        if error is not None:
            # str(ErrInfo) is its concise message; errmsg() is the multi-line
            # console block with a timestamp, which a reader of JSON does not want.
            self.errors.append(
                {
                    "message": " ".join(str(error).split()),
                    "type": getattr(error, "type", None),
                    "source": getattr(error, "script_file", None),
                    "line": getattr(error, "script_line_no", None),
                    "command": getattr(error, "cmd", None) or getattr(error, "command", None),
                },
            )
        finished = _now()
        data = {
            "execsql_version": __version__,
            "script": self.script,
            "started": self.started.isoformat(timespec="seconds"),
            "finished": finished.isoformat(timespec="seconds"),
            "duration_s": round((finished - self.started).total_seconds(), 3),
            "exit_status": exit_status,
            "config_files": self.config_files,
            "database": self.database,
            "variables": self.variables,
            "statements": {"sql": self.sql_statements, "metacommands": self.metacommands},
            "files_read": self.reads,
            "files_written": self.writes,
            "files_deleted": self.deletes,
            "connections": self.connections,
            "errors": self.errors,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target and rename, so a reader never sees half a file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.write("\n")
        os.replace(tmp, self.path)
        self.written = True
