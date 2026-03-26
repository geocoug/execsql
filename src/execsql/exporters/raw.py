from __future__ import annotations

"""
Raw and base64 binary export for execsql.

Provides :func:`write_query_raw` (writes raw binary column data to a
file) and :func:`write_query_b64` (writes base64-encoded column data),
used by the ``EXPORT … FORMAT raw`` and ``FORMAT b64`` metacommand
variants.
"""

from typing import Any

from execsql.exporters.zip import ZipWriter
from execsql.utils.fileio import filewriter_close


def write_query_raw(
    outfile: str,
    rowsource: Any,
    db_encoding: str,
    append: bool = False,
    zipfile: str | None = None,
) -> None:
    if zipfile is None:
        filewriter_close(outfile)
        mode = "wb" if not append else "ab"
        of = open(outfile, mode)  # noqa: SIM115
    else:
        of = ZipWriter(zipfile, outfile, append)
    try:
        for row in rowsource:
            for col in row:
                if isinstance(col, bytearray):
                    of.write(col)
                else:
                    if isinstance(col, str):
                        of.write(bytes(col, db_encoding))
                    else:
                        of.write(bytes(str(col), db_encoding))
    finally:
        of.close()


def write_query_b64(outfile: str, rowsource: Any, append: bool = False, zipfile: str | None = None) -> None:
    global base64
    import base64

    if zipfile is None:
        filewriter_close(outfile)
        mode = "wb" if not append else "ab"
        of = open(outfile, mode)  # noqa: SIM115
    else:
        of = ZipWriter(zipfile, outfile, append)
    try:
        for row in rowsource:
            for col in row:
                of.write(base64.standard_b64decode(col))
    finally:
        of.close()
