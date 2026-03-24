from __future__ import annotations

"""
Raw and base64 binary export for execsql.

Provides :func:`write_query_raw` (writes raw binary column data to a
file) and :func:`write_query_b64` (writes base64-encoded column data),
used by the ``EXPORT … FORMAT raw`` and ``FORMAT b64`` metacommand
variants.
"""

import io
import os
from typing import Any, Optional

import execsql.state as _state
from execsql.exporters.zip import ZipWriter


def write_query_raw(
    outfile: str,
    rowsource: Any,
    db_encoding: str,
    append: bool = False,
    zipfile: Optional[str] = None,
) -> None:
    if zipfile is None:
        _state.filewriter_close(outfile)
        mode = "wb" if not append else "ab"
        of = io.open(outfile, mode)
    else:
        of = ZipWriter(zipfile, outfile, append)
    for row in rowsource:
        for col in row:
            if isinstance(col, bytearray):
                of.write(col)
            else:
                if isinstance(col, str):
                    of.write(bytes(col, db_encoding))
                else:
                    of.write(bytes(str(col), db_encoding))
    of.close()


def write_query_b64(outfile: str, rowsource: Any, append: bool = False, zipfile: Optional[str] = None) -> None:
    global base64
    import base64

    if zipfile is None:
        _state.filewriter_close(outfile)
        mode = "wb" if not append else "ab"
        of = io.open(outfile, mode)
    else:
        of = ZipWriter(zipfile, outfile, append)
    for row in rowsource:
        for col in row:
            of.write(base64.standard_b64decode(col))
    of.close()
