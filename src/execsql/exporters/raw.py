from __future__ import annotations

"""
Raw and base64 binary export for execsql.

Provides :func:`write_query_raw` (writes raw binary column data to a
file) and :func:`write_query_b64` (writes base64-encoded column data),
used by the ``EXPORT … FORMAT raw`` and ``FORMAT b64`` metacommand
variants.
"""

import base64
from typing import Any

from execsql.exporters.zip import ZipWriter
from execsql.utils.fileio import filewriter_close

__all__ = ["write_query_raw", "write_query_b64"]


def write_query_raw(
    outfile: str,
    rowsource: Any,
    db_encoding: str,
    append: bool = False,
    zipfile: str | None = None,
) -> None:
    """Write raw binary column data from a row source directly to a file or ZIP archive."""
    if zipfile is None:
        filewriter_close(outfile)
        mode = "wb" if not append else "ab"
        with open(outfile, mode) as of:
            for row in rowsource:
                for col in row:
                    if isinstance(col, bytearray):
                        of.write(col)
                    else:
                        if isinstance(col, str):
                            of.write(bytes(col, db_encoding))
                        else:
                            of.write(bytes(str(col), db_encoding))
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
    """Decode base64 column data from a row source and write the raw bytes to a file or ZIP archive."""
    if zipfile is None:
        filewriter_close(outfile)
        mode = "wb" if not append else "ab"
        with open(outfile, mode) as of:
            for row in rowsource:
                for col in row:
                    of.write(base64.standard_b64decode(col))
    else:
        of = ZipWriter(zipfile, outfile, append)
        try:
            for row in rowsource:
                for col in row:
                    of.write(base64.standard_b64decode(col))
        finally:
            of.close()
