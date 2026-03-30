"""
Base export infrastructure — metadata tracking and write specifications.

Provides:

- :class:`ExportRecord` — records details of a single export operation
  (query name, output file, optional zip file, description, script
  location, database info).
- :class:`ExportMetadata` — collection of :class:`ExportRecord` objects;
  can write itself as a JSON metadata file.
- :class:`WriteSpec` — specification for a deferred write operation
  (message text, file path, encoding) used by halt/cancel hooks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.script import current_script_line
from execsql.utils.errors import file_size_date
from execsql.utils.gui import ConsoleUIError

__all__ = ["WriteSpec", "ExportRecord", "ExportMetadata"]


class ExportRecord:
    """Records the details of a single EXPORT operation for metadata tracking.

    Captures the query name, output file path, optional zip file, user
    description, originating script location, and database connection info.
    """

    def __init__(
        self,
        queryname: str,
        outfile: str,
        zipfile: str | None = None,
        description: str | None = None,
    ) -> None:
        self.exported = False
        # Record is a list of: table_or_query_name, filename, zipfilename, file_path, user_description, script_name,
        # script_path, script_line_no, script_datetime, database_name, database_server, user_name.
        if zipfile is not None:
            fpath, zfname = str(Path(zipfile).resolve().parent), Path(zipfile).resolve().name
            fname = outfile
        else:
            fpath, fname = str(Path(outfile).resolve().parent), Path(outfile).resolve().name
            zfname = None
        import getpass

        script, lno = current_script_line()
        if script and Path(script).is_file():
            spath, sname = str(Path(script).resolve().parent), Path(script).resolve().name
            _, sdt = file_size_date(script)
        else:
            spath, sname = "", script or "<inline>"
            _, sdt = 0, ""
        db = _state.dbs.current()
        svr = db.server_name
        dbn = db.db_name
        usr = db.user if db.user is not None else getpass.getuser()
        self.record = [queryname, fname, zfname, fpath, description, sname, spath, lno, sdt, dbn, svr, usr]


class ExportMetadata:
    """Collection of :class:`ExportRecord` objects; can write itself as JSON.

    Accumulates export records during a script run and provides them to the
    EXPORT METADATA metacommand for serialisation.
    """

    colhdrs = [
        "query",
        "filename",
        "zipfilename",
        "file_path",
        "description",
        "script",
        "script_path",
        "script_line",
        "script_date",
        "database",
        "server",
        "username",
    ]

    def __init__(self) -> None:
        self.recordlist: list[ExportRecord] = []

    def add(self, exp_record: ExportRecord) -> None:
        self.recordlist.append(exp_record)

    def get(self):
        recs = [er.record for er in self.recordlist if not er.exported]
        for er in self.recordlist:
            er.exported = True
        return self.colhdrs, recs

    def get_all(self):
        recs = [er.record for er in self.recordlist]
        for er in self.recordlist:
            er.exported = True
        return self.colhdrs, recs


class WriteSpec:
    """Specification for a deferred WRITE operation used by halt/cancel hooks.

    Stores a message, optional destination file, tee flag, and repeatability
    setting. Resolved and executed later by the hook machinery.
    """

    def __repr__(self) -> str:
        return f"WriteSpec({self.msg}, {self.outfile}, {self.tee})"

    def __init__(self, message: str, dest: str | None = None, tee: Any = None, repeatable: bool = False) -> None:
        # Inputs
        # message: Text to write.  May contain substitution variable references.
        # dest: The to which the text should be written.  If omitted, the message
        # is written to the console.
        # tee: Write to the console as well as to the specified file.  The argument
        # is coerced to a Boolean.
        # repeatable: Can the message be written more than once?
        # Actions
        # Stores the arguments as properties for later use.
        self.msg = message
        self.outfile = dest
        self.tee = bool(tee)
        self.repeatable = bool(repeatable)
        self.written = False

    def write(self) -> None:
        # Writes the message per the specifications given to '__init__()'.  Substitution
        # variables are processed.
        # Inputs: no inputs.
        # Return value: None.
        conf = _state.conf
        subvars = _state.subvars
        if self.repeatable or not self.written:
            self.written = True
            msg = _state.commandliststack[-1].localvars.substitute_all(self.msg)
            msg = subvars.substitute_all(msg)
            if self.outfile:
                from execsql.utils.fileio import EncodedFile

                ef = EncodedFile(self.outfile, conf.output_encoding)
                fh = ef.open("a")
                try:
                    fh.write(msg)
                finally:
                    fh.close()
            if (not self.outfile) or self.tee:
                try:
                    _state.output.write(msg.encode(conf.output_encoding))
                except ConsoleUIError as e:
                    _state.output.reset()
                    _state.exec_log.log_status_info(
                        f"Console UI write failed (message {{{e.value}}}); output reset to stdout.",
                    )
                    _state.output.write(msg.encode(conf.output_encoding))
            if conf.tee_write_log:
                _state.exec_log.log_user_msg(msg)
        return None
