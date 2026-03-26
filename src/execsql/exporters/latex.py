from __future__ import annotations

"""
LaTeX table export for execsql.

Provides :func:`write_query_to_latex`, which serializes a query result
set to a LaTeX ``tabular`` environment suitable for inclusion in a
``.tex`` document.
"""

import os
import tempfile
from pathlib import Path
from typing import Any

from execsql.exceptions import ErrInfo
from execsql.exporters.zip import WriteableZipfile
import execsql.state as _state


def export_latex(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool = False,
    querytext: str | None = None,
    desc: str | None = None,
    zipfile: Any | None = None,
) -> None:
    from execsql.utils.fileio import EncodedFile

    def write_table(f: Any) -> None:
        f.write("\\begin{center}\n")
        f.write("  \\begin{table}[h]\n")
        if desc is not None:
            f.write(f"  \\caption{{{desc}}}\n")
        f.write(f"  \\begin{{tabular}} {{{' l' * len(hdrs)} }}\n")
        f.write("  \\hline\n")
        f.write("  " + " & ".join([h.replace("_", r"\_") for h in hdrs]) + " \\\\\n")
        f.write("  \\hline\n")
        for r in rows:
            f.write("  " + " & ".join([str(c).replace("_", r"\_") for c in r]) + " \\\\\n")
        f.write("  \\hline\n")
        f.write("  \\end{tabular}\n")
        f.write("  \\end{table}\n")
        f.write("\\end{center}\n")

    conf = _state.conf
    # If not append, write a complete LaTeX document with header and table.
    # If append and the file does not exist, write just the table.
    # If append and the file exists, R/W up to the \end{document} tag, write the table, write the remainder of the input.
    if zipfile or not append:
        if outfile.lower() == "stdout":
            import sys

            f = sys.stdout
        else:
            if zipfile is None:
                ef = EncodedFile(outfile, conf.output_encoding)
                f = ef.open("wt")
            else:
                f = WriteableZipfile(zipfile).open(outfile, append)
        try:
            f.write("\\documentclass{article}\n")
            f.write("\\begin{document}\n")
            write_table(f)
            f.write("\\end{document}\n")
        finally:
            if outfile.lower() != "stdout":
                f.close()
    else:
        if outfile.lower() == "stdout" or not Path(outfile).is_file():
            if outfile.lower() == "stdout":
                import sys

                f = sys.stdout
            else:
                ef = EncodedFile(outfile, conf.output_encoding)
                f = ef.open("wt")
            try:
                write_table(f)
            finally:
                if outfile.lower() != "stdout":
                    f.close()
        else:
            ef = EncodedFile(outfile, conf.output_encoding)
            f = ef.open("rt")
            tempf, tempfname = tempfile.mkstemp(text=True)
            os.close(tempf)  # Close the fd from mkstemp; EncodedFile opens its own handle
            tf = EncodedFile(tempfname, conf.output_encoding)
            t = tf.open("wt")
            try:
                remainder = ""
                for line in f:
                    bodypos = line.lower().find("\\end{document}")
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


def write_query_to_latex(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: Any | None = None,
) -> None:
    from execsql.utils.errors import exception_desc

    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    export_latex(outfile, hdrs, rows, append, select_stmt, desc, zipfile=zipfile)
