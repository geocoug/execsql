from __future__ import annotations

"""
XML export for execsql.

Provides :func:`write_query_to_xml`, which serializes a query result set
to a well-formed XML file with one element per row and column values as
child elements or attributes.
"""

import io
import os
import re
from typing import Any, Optional, List

import execsql.state as _state
from execsql.exporters.zip import ZipWriter


def write_query_to_xml(
    select_stmt: str,
    tablename: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: Optional[str] = None,
    zipfile: Optional[str] = None,
) -> None:
    conf = _state.conf
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except _state.ErrInfo:
        raise
    except:
        raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())
    if zipfile is None:
        _state.filewriter_close(outfile)
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
    uhdrs = [str(h) for h in hdrs]
    for row in rows:
        f.write("  <row>\n")
        for i, col in enumerate(hdrs):
            f.write(f"    <{col}>{row[i]}</{col}>\n")
        f.write("  </row>\n")
    f.write(f"</{tablename}>\n")
    f.close()
