from __future__ import annotations

"""
JSON export for execsql.

Provides :func:`write_query_to_json` (standard JSON array of objects) and
:func:`write_query_to_json_ts` (JSON with a top-level timestamp wrapper),
both of which serialize a query result set to a file or stream.
"""

import json
from typing import Any

import execsql.state as _state
from execsql.exporters.zip import ZipWriter
from execsql.exceptions import ErrInfo
from execsql.models import DataTable
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["write_query_to_json", "write_query_to_json_ts"]


def write_query_to_json(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:

    conf = _state.conf
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    if zipfile is None:
        filewriter_close(outfile)
        from execsql.utils.fileio import EncodedFile

        ef = EncodedFile(outfile, conf.output_encoding)
        if append:
            f = ef.open("at")
            f.write(",\n")
        else:
            f = ef.open("wt")
    else:
        f = ZipWriter(zipfile, outfile, append)
    try:
        f.write("[")
        uhdrs = [str(h) for h in hdrs]
        first = True
        for row in rows:
            if first:
                f.write("\n")
            else:
                f.write(",\n")
            first = False
            dictdata = dict(zip(uhdrs, [str(v) if isinstance(v, str) else v for v in row]))
            jsondata = json.dumps(dictdata, separators=(",", ":"), default=str)
            f.write(str(jsondata))
        f.write("\n]\n")
    finally:
        f.close()


def write_query_to_json_ts(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    write_types: bool = True,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:

    conf = _state.conf
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    max_col_idx = len(hdrs) - 1
    if zipfile is None:
        filewriter_close(outfile)
        from execsql.utils.fileio import EncodedFile

        ef = EncodedFile(outfile, conf.output_encoding)
        if append:
            f = ef.open("at")
            f.write(",\n")
        else:
            f = ef.open("wt")
    else:
        f = ZipWriter(zipfile, outfile, append)
    try:
        f.write("{\n")
        if desc is not None:
            escaped_desc = json.dumps(desc)
            f.write(f'  "description": {escaped_desc},\n')
        f.write('  "fields": [\n')
        if write_types:
            # Scan the data to determine data types.
            tbl_desc = DataTable(hdrs, rows)
            # Write the column descriptions to the header.
            # Iterate over hdrs instead of tbl_desc.cols to preserve column order.
            for i, h in enumerate(hdrs):
                qcomma = "," if i < max_col_idx else ""
                c = [col for col in tbl_desc.cols if col.name == h][0]
                f.write(
                    f'    {{\n      "name": "{c.name}",\n      "title": "{c.name.capitalize().replace("_", " ")}",\n      "type": "{_state.to_json_type[c.dt[1]]}"\n    }}{qcomma}\n',
                )
        else:
            # Write the column descriptions to the header.
            for i, h in enumerate(hdrs):
                qcomma = "," if i < max_col_idx else ""
                f.write(
                    f'    {{\n      "name": "{h}",\n      "title": "{h.capitalize().replace("_", " ")}"\n    }}{qcomma}\n',
                )
        f.write("  ]\n}\n")
    finally:
        f.close()
