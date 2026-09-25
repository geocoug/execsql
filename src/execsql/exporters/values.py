from __future__ import annotations

"""
SQL INSERT VALUES export for execsql.

Provides :func:`write_query_to_values`, which serializes a query result
set as a series of SQL ``INSERT INTO … VALUES (…)`` statements, suitable
for loading data into a database from a plain SQL file.
"""

import decimal
from typing import Any

import execsql.state as _state
from execsql.exporters.zip import ZipWriter
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["export_values", "write_query_to_values"]


def _sql_literal(value: Any) -> str:
    """Render a value as a SQL literal for an INSERT ... VALUES list.

    Only numbers are emitted bare.  Everything else is quoted, with embedded
    single quotes doubled — the SQL standard escape.

    Quoting is the safe default rather than the exception.  Previously anything
    that was not a string went out through ``str()`` unquoted, so a date became
    ``2026-09-24``, which SQL reads as arithmetic: PostgreSQL inserted 1993 and
    reported no error at all.  A timestamp, carrying a space, was a syntax
    error instead.  Any type this function has not been taught about is safer
    quoted than bare.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        # Checked before int — bool is a subclass of it.
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float | decimal.Decimal):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def export_values(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    """Write pre-fetched rows as SQL INSERT … VALUES statements to a file or ZIP archive."""
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
            quoted_row = [_sql_literal(v) for v in r]
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
    """Execute a SELECT and write the result set as SQL INSERT … VALUES statements."""
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    export_values(outfile, hdrs, rows, append, desc, zipfile=zipfile)
