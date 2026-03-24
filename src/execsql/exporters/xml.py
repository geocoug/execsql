from __future__ import annotations

"""
XML export for execsql.

Provides :func:`write_query_to_xml`, which serializes a query result set
to a well-formed XML file with one element per row and column values as
child elements or attributes.
"""

from typing import Any

import execsql.state as _state
from execsql.exporters.zip import ZipWriter
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close


def write_query_to_xml(
    select_stmt: str,
    tablename: str,
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
    except Exception:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc())
    if zipfile is None:
        filewriter_close(outfile)
        from execsql.utils.fileio import EncodedFile

        ef = EncodedFile(outfile, conf.output_encoding)
        if append:
            f = ef.open("at")
            f.write(",\n")
        else:
            f = ef.open("wt")
            f.write(f"<?xml version='1.0' encoding='{conf.output_encoding}'?>\n")
    else:
        f = ZipWriter(zipfile, outfile, append)
        f.write(f"<?xml version='1.0' encoding='{conf.output_encoding}'?>\n")
    if desc is not None:
        f.write(f"<!--{desc}-->\n")
    f.write(f"<{tablename}>\n")
    str_hdrs = [str(h) for h in hdrs]
    for row in rows:
        f.write("  <row>\n")
        for i, col in enumerate(str_hdrs):
            f.write(f"    <{col}>{row[i]}</{col}>\n")
        f.write("  </row>\n")
    f.write(f"</{tablename}>\n")
    f.close()
