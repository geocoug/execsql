from __future__ import annotations

"""
XML export for execsql.

Provides :func:`write_query_to_xml`, which serializes a query result set
to a well-formed XML file with one element per row and column values as
child elements or attributes.
"""

import re
from typing import Any
from xml.sax.saxutils import escape as xml_escape

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

    def _safe_xml_name(name: str) -> str:
        """Sanitize a string for use as an XML element name."""
        # Replace characters that are invalid in XML names with underscores.
        s = re.sub(r"[^\w.\-]", "_", str(name))
        # XML names must start with a letter or underscore, not a digit or dot.
        if s and not (s[0].isalpha() or s[0] == "_"):
            s = "_" + s
        return s or "_"

    try:
        if desc is not None:
            f.write(f"<!--{desc.replace('--', '- -')}-->\n")
        safe_tablename = _safe_xml_name(tablename)
        f.write(f"<{safe_tablename}>\n")
        str_hdrs = [_safe_xml_name(h) for h in hdrs]
        for row in rows:
            f.write("  <row>\n")
            for i, col in enumerate(str_hdrs):
                f.write(f"    <{col}>{xml_escape(str(row[i]) if row[i] is not None else '')}</{col}>\n")
            f.write("  </row>\n")
        f.write(f"</{safe_tablename}>\n")
    finally:
        f.close()
