from __future__ import annotations

"""
HTML and CGI-HTML export for execsql.

Provides :func:`write_query_to_html` (standalone HTML table) and
:func:`write_query_to_cgi_html` (CGI-wrapped HTML table fragment),
both of which serialize a query result set to an HTML file with optional
CSS styling.
"""

import datetime
import getpass
import html as html_mod
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.exporters.zip import ZipWriter
from execsql.exceptions import ErrInfo
from execsql.script import current_script_line
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close


def export_html(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool = False,
    querytext: str | None = None,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    conf = _state.conf

    def write_table(f):
        f.write("<table>\n")
        if desc is not None:
            f.write(f"<caption>{desc}</caption>\n")
        f.write("<thead><tr>")
        for h in hdrs:
            f.write(f"<th>{html_mod.escape(str(h))}</th>")
        f.write("</tr></thead>\n<tbody>\n")
        for r in rows:
            f.write("<tr>")
            for v in r:
                f.write(f"<td>{html_mod.escape(str(v)) if v else ''}</td>")
            f.write("</tr>\n")
        f.write("</tbody>\n</table>\n")

    script, lno = current_script_line()
    # If not append, write a complete HTML document with header and table.
    # If append and the file does not exist, write just the table.
    # If append and the file exists, R/W up to the </body> tag, write the table, write the remainder of the input.
    if zipfile or not append:
        if zipfile is None:
            if outfile.lower() == "stdout":
                f = sys.stdout
            else:
                filewriter_close(outfile)
                from execsql.utils.fileio import EncodedFile

                ef = EncodedFile(outfile, conf.output_encoding)
                f = ef.open("wt")
        else:
            f = ZipWriter(zipfile, outfile, append)
        try:
            f.write('<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8" />\n')
            if querytext:
                descrip = f"Source: [{querytext}] with database {_state.dbs.current().name()} in script {str(Path(script).resolve())}, line {lno}"
            else:
                descrip = (
                    f"From database {_state.dbs.current().name()} in script {str(Path(script).resolve())}, line {lno}"
                )
            f.write(f'<meta name="description" content="{descrip}" />\n')
            datecontent = datetime.datetime.now().strftime("%Y-%m-%d")
            f.write(f'<meta name="created" content="{datecontent}" />\n')
            f.write(f'<meta name="revised" content="{datecontent}" />\n')
            f.write(f'<meta name="author" content="{getpass.getuser()}" />\n')
            f.write("<title>Data Table</title>\n")
            if conf.css_file or conf.css_styles:
                if conf.css_file:
                    f.write(f'<link rel="stylesheet" type="text/css" href="{conf.css_file}">')
                if conf.css_styles:
                    f.write(f'<style type="text/css">\n{conf.css_styles}\n</style>')
            else:
                f.write('<style type="text/css">\n')
                f.write(
                    'table {font-family: "Liberation Mono", "DejaVu Sans Mono", "Bitstream Vera Sans Mono", "Lucida Console", "Courier New", Courier, fixed; '
                    + "border-top: 3px solid #814324; border-bottom: 3px solid #814324; "
                    + "border-left: 2px solid #814324; border-right: 2px solid #814324; "
                    + "border-collapse: collapse; }\n",
                )
                f.write("td {text-align: left; padding 0 10px; border-right: 1px dotted #814324; }\n")
                f.write(
                    "th {padding: 2px 10px; text-align: center; border-bottom: 1px solid #814324; border-right: 1px dotted #814324;}\n",
                )
                f.write("tr.hdr {font-weight: bold;}\n")
                f.write("thead tr {border-bottom: 1px solid #814324; background-color: #F3F1E2; }\n")
                f.write("tbody tr { border-bottom: 1px dotted #814324; }\n")
                f.write("</style>")
            f.write("\n</head>\n<body>\n")
            write_table(f)
            f.write("</body>\n</html>\n")
        finally:
            if outfile.lower() != "stdout":
                f.close()
    elif not zipfile and append:
        if outfile.lower() == "stdout":
            f = sys.stdout
            write_table(f)
        elif not Path(outfile).is_file():
            from execsql.utils.fileio import EncodedFile

            ef = EncodedFile(outfile, conf.output_encoding)
            f = ef.open("wt")
            try:
                write_table(f)
            finally:
                f.close()
        else:
            filewriter_close(outfile)
            from execsql.utils.fileio import EncodedFile

            ef = EncodedFile(outfile, conf.output_encoding)
            f = ef.open("rt")
            tempf, tempfname = tempfile.mkstemp(text=True)
            os.close(tempf)  # Close the fd from mkstemp; EncodedFile opens its own handle
            tf = EncodedFile(tempfname, conf.output_encoding)
            t = tf.open("wt")
            try:
                remainder = ""
                for line in f:
                    bodypos = line.lower().find("</body>")
                    if bodypos > -1:
                        t.write(line[0:bodypos])
                        t.write("\n")
                        remainder = line[bodypos:]
                        break
                    else:
                        t.write(line)
                t.write("\n")
                write_table(t)
                t.write(remainder)
                for line in f:
                    t.write(line)
            finally:
                t.close()
                f.close()
            os.unlink(outfile)
            os.rename(tempfname, outfile)


def export_cgi_html(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool = False,
    querytext: str | None = None,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    conf = _state.conf

    def write_table(f):
        f.write("<table>\n")
        if desc is not None:
            f.write(f"<caption>{desc}</caption>\n")
        f.write("<thead><tr>")
        for h in hdrs:
            f.write(f"<th>{html_mod.escape(str(h))}</th>")
        f.write("</tr></thead>\n<tbody>\n")
        for r in rows:
            f.write("<tr>")
            for v in r:
                f.write(f"<td>{html_mod.escape(str(v)) if v else ''}</td>")
            f.write("</tr>\n")
        f.write("</tbody>\n</table>\n")

    script, lno = current_script_line()
    if zipfile or not append or (append and not Path(outfile).is_file()):
        if zipfile is None:
            if outfile.lower() == "stdout":
                f = sys.stdout
            else:
                filewriter_close(outfile)
                from execsql.utils.fileio import EncodedFile

                ef = EncodedFile(outfile, conf.output_encoding)
                f = ef.open("wt")
        else:
            f = ZipWriter(zipfile, outfile, append)
        try:
            f.write("Content-Type: text/html\n\n")
            write_table(f)
        finally:
            if outfile.lower() != "stdout":
                f.close()
    else:
        if outfile == "stdout":
            f = sys.stdout
        else:
            from execsql.utils.fileio import EncodedFile

            ef = EncodedFile(outfile, conf.output_encoding)
            f = ef.open("a")
        try:
            write_table(f)
        finally:
            if outfile.lower() != "stdout":
                f.close()


def write_query_to_html(
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
    export_html(outfile, hdrs, rows, append, select_stmt, desc, zipfile=zipfile)


def write_query_to_cgi_html(
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
    export_cgi_html(outfile, hdrs, rows, append, select_stmt, desc, zipfile=zipfile)
