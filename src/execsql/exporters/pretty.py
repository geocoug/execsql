from __future__ import annotations

"""
Pretty-printed text table export for execsql.

Provides :func:`prettyprint_query` and :func:`prettyprint_rowset`, which
format a query result set as a fixed-width human-readable text table
(column-aligned, with a header row and separator).
"""

from typing import Any

import execsql.state as _state
from execsql.exporters.zip import ZipWriter
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["prettyprint_query", "prettyprint_rowset"]


def prettyprint_rowset(
    colhdrs: list[str],
    rows: Any,
    output_dest: str,
    append: bool = False,
    and_val: str = "",
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    # Adapted from the pp() function by Aaron Watters,
    # posted to gadfly-rdbms@egroups.com 1999-01-18.
    def as_ucode(s):
        if s is None:
            return and_val
        if isinstance(s, str):
            return s
        if type(s) in (type(memoryview(b"")), bytes, bytearray):
            return f"Binary data ({len(s)} bytes)"
        else:
            if isinstance(s, bytes):
                return s.decode(_state.dbs.current().encoding)
        return str(s)

    if not isinstance(rows, list):
        try:
            rows = list(rows)
        except Exception as e:
            raise ErrInfo(
                "exception",
                exception_msg=exception_desc(),
                other_msg="Can't create a list in memory of the data to be displayed as formatted text.",
            ) from e
    rcols = range(len(colhdrs))
    rrows = range(len(rows))
    colwidths = [max(0, len(colhdrs[j]), *(len(as_ucode(rows[i][j])) for i in rrows)) for j in rcols]
    names = " " + " | ".join([colhdrs[j].ljust(colwidths[j]) for j in rcols])
    sep = "|".join(["-" * (colwidths[j] + 2) for j in rcols])
    rows = [names, sep] + [
        " "
        + " | ".join(
            [as_ucode(rows[i][j]).ljust(colwidths[j]) for j in rcols],
        )
        for i in rrows
    ]
    if output_dest == "stdout":
        ofile = _state.output
        margin = "    "
    else:
        margin = " "
        if zipfile is None:
            from execsql.utils.fileio import EncodedFile

            filewriter_close(output_dest)
            if append:
                ofile = EncodedFile(output_dest, _state.conf.output_encoding).open("a")
            else:
                ofile = EncodedFile(output_dest, _state.conf.output_encoding).open("w")
        else:
            ofile = ZipWriter(zipfile, output_dest, append)
    try:
        if desc is not None:
            ofile.write(f"{desc}\n")
        for row in rows:
            ln = f"{margin}{row}\n"
            ofile.write(ln)
    finally:
        if output_dest != "stdout":
            ofile.close()
    return None


def prettyprint_query(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    and_val: str = "",
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    _state.status.sql_error = False
    names, rows = db.select_data(select_stmt)
    prettyprint_rowset(names, rows, outfile, append, and_val, desc, zipfile=zipfile)
