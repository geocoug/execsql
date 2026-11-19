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
the manifest lists only their names. A password or decrypted value that reaches
a path, a connection target or an error message is written as ``***``, as are
common secret shapes (a URL's password, ``password=...``, API tokens). ``-a`` and
``--var`` values, which the log also masks, are kept: they are usually part of
the paths the manifest exists to report.

One recorder is active per run; :func:`current` returns it, or ``None`` when
no manifest was asked for, so the executor's hooks cost one check. Writing the
manifest ends the recording, so a later run in the same process starts clean.
"""

from __future__ import annotations

import atexit
import datetime
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from execsql import __version__
from execsql.exceptions import ScriptParseError

__all__ = ["RunManifest", "check_writable", "current", "start"]


def current() -> RunManifest | None:
    """The active run's manifest recorder, or ``None`` when ``--manifest`` was not given.

    Held on the run's :class:`~execsql.state.RuntimeContext`, so a library
    ``execsql.run()`` in the same process never records into a CLI manifest.
    """
    import execsql.state as _state

    return _state.manifest


def check_writable(path: str) -> str | None:
    """Why a manifest cannot be written to *path*, or ``None`` if it can.

    Checked before a run starts, so a bad ``--manifest`` path fails before any
    SQL runs rather than after.
    """
    target = Path(path)
    if target.is_dir():
        return f"{path} is a directory"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        os.close(fd)
        os.unlink(probe)
    except OSError as exc:
        return exc.strerror or str(exc)
    return None


def start(path: str, script: str | None, variables: list[str]) -> RunManifest:
    """Begin recording a run; the manifest is written to *path* when it ends.

    If nothing else writes it (``exit_now`` on an error, the end of a run), an
    ``atexit`` fallback does.
    """
    import execsql.state as _state

    manifest = RunManifest(path, script, variables)
    _state.manifest = manifest
    atexit.register(manifest.finish, None)
    return manifest


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _masked(value: Any) -> Any:
    """*value* with the run's passwords and common secret shapes replaced by ``***`` in every string it holds.

    ``-a`` / ``--var`` values are left in place; times, counts and line numbers are not strings.
    """
    from execsql.utils.fileio import redact

    if isinstance(value, str):
        return redact(value, arguments=False)
    if isinstance(value, list):
        return [_masked(item) for item in value]
    if isinstance(value, dict):
        return {key: _masked(item) for key, item in value.items()}
    return value


class RunManifest:
    """Collects what one run does and writes it as JSON when the run ends."""

    def __init__(self, path: str, script: str | None, variables: list[str]) -> None:
        self.path = Path(path)
        self.script = script or "<inline>"
        self.run_id: str | None = None
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
        self._commands: list[dict[str, Any]] = []
        self._queued_writes: dict[int, list[Any]] = {}

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

    @contextmanager
    def command(self, command: str, source: str, line: int, metacommandlist: Any) -> Iterator[None]:
        """Count an attempt and retain provenance for asynchronous writes, including nested commands."""
        hit = metacommandlist.get_match(command)
        words = command.split(None, 1)
        by = (hit[0].description if hit else None) or (words[0].upper() if words else "METACOMMAND")
        self.metacommands += 1
        self._commands.append({"source": source, "line": line, "by": by, "queued": {}})
        try:
            yield
        finally:
            self._commands.pop()

    def queued_write(self, path: str, text: str) -> str:
        """Keep a queued write only if the worker confirms it wrote and flushed the original text."""
        from execsql.utils.fileio import _TrackedWrite

        receipt = _TrackedWrite(text)
        context = (
            self._commands[-1] if self._commands else {"source": self.script, "line": None, "by": "WRITE", "queued": {}}
        )
        entry = context["queued"].get(path)
        if entry is None:
            entry = {key: context[key] for key in ("source", "line", "by")}
            entry["path"] = path
            context["queued"][path] = entry
            self.writes.append(entry)
            self._queued_writes[id(entry)] = []
        self._queued_writes[id(entry)].append(receipt.receipt)
        return receipt

    def record_write(self, path: str, source: str, line: int | None, by: str) -> None:
        """Record a synchronous write after it has succeeded, including a deferred halt handler."""
        self.writes.append({"source": source, "line": line, "by": by, "path": path})

    def record_read(self, path: str, source: str, line: int | None, by: str) -> None:
        self.reads.append({"source": source, "line": line, "by": by, "path": path})

    def record_metacommand(
        self,
        command: str,
        source: str,
        line: int,
        metacommandlist: Any,
        *,
        count: bool = True,
    ) -> None:
        """Count a metacommand that ran, and record the files and connections it touched.

        *command* is the text after substitution, so paths are the ones used.
        """
        from execsql.metacommands.effects import effects

        if count:
            self.metacommands += 1
        hit = metacommandlist.get_match(command)
        if hit is None:
            return
        mc, m = hit
        if mc.exec_fn.__name__ in (
            "x_error_halt_write",
            "x_cancel_halt_write",
            "x_error_halt_email",
            "x_cancel_halt_email",
        ):
            return  # Deferred specs record file effects only when they actually run.
        by = mc.description or command.split(None, 1)[0].upper()
        for effect in effects(mc.exec_fn.__name__, m.groupdict()):
            if (
                effect.role == "write"
                and effect.target == "stdout"
                and mc.exec_fn.__name__ in ("x_write_create_table", "x_writescript")
            ):
                continue
            if effect.role == "write" and self._commands and self._commands[-1]["queued"]:
                continue  # The worker's receipt determines whether this write succeeded.
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

    def add_error(self, error: Any) -> None:
        """Record *error* (an :class:`ErrInfo`) in the manifest's ``errors``."""
        # str(ErrInfo) is its concise message; errmsg() is the multi-line
        # console block with a timestamp, which a reader of JSON does not want.
        self.errors.append(
            {
                "message": " ".join(str(error).split()),
                "type": getattr(error, "type", None),
                "source": error.source if isinstance(error, ScriptParseError) else getattr(error, "script_file", None),
                "line": error.line if isinstance(error, ScriptParseError) else getattr(error, "script_line_no", None),
                "command": getattr(error, "cmd", None) or getattr(error, "command", None),
            },
        )

    def finish(self, exit_status: int | None, error: Any = None) -> None:
        """Write the manifest once. Later calls (the atexit fallback) do nothing."""
        if self.written:
            return
        if error is not None:
            self.add_error(error)
        finished = _now()
        data = {
            "execsql_version": __version__,
            "run_id": self.run_id,
            "script": _masked(self.script),
            "started": self.started.isoformat(timespec="seconds"),
            "finished": finished.isoformat(timespec="seconds"),
            "duration_s": round((finished - self.started).total_seconds(), 3),
            "exit_status": exit_status,
            "config_files": _masked(self.config_files),
            "database": _masked(self.database),
            "variables": self.variables,
            "statements": {"sql": self.sql_statements, "metacommands": self.metacommands},
            "files_read": _masked(self.reads),
            "files_written": _masked(
                [
                    entry
                    for entry in self.writes
                    if id(entry) not in self._queued_writes
                    or any(receipt.written for receipt in self._queued_writes[id(entry)])
                ],
            ),
            "files_deleted": _masked(self.deletes),
            "connections": _masked(self.connections),
            "errors": _masked(self.errors),
        }
        self.written = True
        import execsql.state as _state

        if _state.manifest is self:
            _state.manifest = None
        atexit.unregister(self.finish)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Write beside the target and rename, so a reader never sees half a file.
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
                f.write("\n")
            os.replace(tmp, self.path)
        except OSError as exc:
            # The run itself is over; report the lost manifest without a traceback.
            sys.stderr.write(f"execsql: could not write --manifest {self.path}: {exc.strerror or exc}\n")
