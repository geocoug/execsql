from __future__ import annotations

"""
GitHub-Flavored Markdown (GFM) pipe table export for execsql.

Provides :func:`write_query_to_markdown`, which serializes a query result
set as a GFM pipe table suitable for inclusion in GitHub README files,
wikis, and any Markdown renderer that supports the pipe-table extension.

Example output::

    | id | name   | score |
    |----|--------|-------|
    | 1  | Alice  | 95.2  |
    | 2  | Bob    | 87.0  |

No optional dependencies — pure Python.
"""

from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.exporters.zip import ZipWriter
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["write_query_to_markdown"]

_PIPE_ESCAPE = str.maketrans({"|": r"\|", "\\": "\\\\"})


def _cell(value: Any) -> str:
    """Render a single cell value as a Markdown-safe string.

    Args:
        value: The cell value from the result set.  ``None`` is rendered as
            an empty string.  Pipe characters are escaped so they do not
            break the table structure.

    Returns:
        A string safe to embed between pipe characters in a GFM table row.
    """
    if value is None:
        return ""
    return str(value).translate(_PIPE_ESCAPE)


def write_query_to_markdown(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    """Execute *select_stmt* and write the result set as a GFM pipe table.

    Writes a GitHub-Flavored Markdown pipe table to *outfile* (or into
    *zipfile* when provided).  Column widths are derived from the widest
    value in each column (including the header), so the table renders
    legibly in plain-text editors as well as in Markdown renderers.

    Args:
        select_stmt: SQL SELECT statement to execute.
        db: Database connection object exposing ``select_rowsource()``.
        outfile: Destination file path, or ``"stdout"`` for console output.
        append: When ``True`` open the file in append mode.  A blank line
            is written before the table so consecutive appended tables are
            visually separated.
        desc: Optional human-readable description.  When provided it is
            written as an HTML comment (``<!-- desc -->``), which is valid
            Markdown and invisible in rendered output.
        zipfile: When set, write into this ZIP archive instead of a plain
            file.  *outfile* becomes the entry name inside the archive.
    """
    conf = _state.conf
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e

    # Materialise the full result set so we can compute column widths in one
    # pass before writing.  GFM tables require consistent column widths for
    # readability; width computation requires seeing all rows first.
    str_hdrs: list[str] = [_cell(h) for h in hdrs]
    str_rows: list[list[str]] = [[_cell(v) for v in row] for row in rows]

    # Minimum separator width is 3 dashes (GFM spec minimum for alignment row).
    col_widths: list[int] = [max(3, len(h)) for h in str_hdrs]
    for row in str_rows:
        for i, cell in enumerate(row):
            if len(cell) > col_widths[i]:
                col_widths[i] = len(cell)

    def _format_row(cells: list[str]) -> str:
        padded = (f" {c:<{col_widths[i]}} " for i, c in enumerate(cells))
        return "|" + "|".join(padded) + "|\n"

    def _format_separator() -> str:
        dashes = (f" {'-' * col_widths[i]} " for i in range(len(str_hdrs)))
        return "|" + "|".join(dashes) + "|\n"

    if zipfile is None:
        filewriter_close(outfile)
        from execsql.utils.fileio import EncodedFile

        ef = EncodedFile(outfile, conf.output_encoding)
        f = ef.open("at" if append else "wt")
    else:
        f = ZipWriter(zipfile, outfile, append)

    try:
        if append:
            # Blank line separates consecutive tables when appending.
            f.write("\n")
        if desc is not None:
            f.write(f"<!-- {desc} -->\n\n")
        f.write(_format_row(str_hdrs))
        f.write(_format_separator())
        for row in str_rows:
            f.write(_format_row(row))
    finally:
        f.close()
