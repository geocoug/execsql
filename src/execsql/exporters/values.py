from __future__ import annotations

"""
SQL INSERT VALUES export for execsql.

Provides :func:`write_query_to_values`, which serializes a query result
set as a series of SQL ``INSERT INTO … VALUES (…)`` statements, suitable
for loading data into a database from a plain SQL file.
"""

from typing import Any

import execsql.state as _state
from execsql.exporters.zip import ZipWriter
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["export_values", "write_query_to_values"]


def export_values(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    conf = _state.conf
    if outfile.lower() == "stdout":
        f = _state.output
    else:
        if zipfile is None:
            filewriter_close(outfile)
            from execsql.utils.fileio import EncodedFile

            ef = EncodedFile(outfile, conf.output_encoding)
            if append:
                f = ef.open("at")
            else:
                f = ef.open("wt")
        else:
            f = ZipWriter(zipfile, outfile, append)
    try:
        if desc is not None:
            f.write(f"-- {desc}\n")
        f.write(f"INSERT INTO !!target_table!!\n    ({', '.join(hdrs)})\n")
        f.write("VALUES\n")
        firstrow = True
        for r in rows:
            if firstrow:
                firstrow = False
            else:
                f.write(",\n")
            quoted_row = [
                f"'{v.replace(chr(39), chr(39) * 2)}'" if isinstance(v, str) else str(v) if v is not None else "NULL"
                for v in r
            ]
            f.write(f"    ({', '.join(quoted_row)})")
        f.write("\n    ;\n")
    finally:
        if outfile.lower() != "stdout":
            f.close()


def write_query_to_values(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    export_values(outfile, hdrs, rows, append, desc, zipfile=zipfile)
