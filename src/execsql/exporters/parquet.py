from __future__ import annotations

"""
Apache Parquet export for execsql.

Provides :func:`write_query_to_parquet` (Parquet format via ``polars``).
Used by ``EXPORT … FORMAT parquet``.  Polars is an optional dependency.
"""

from typing import Any

from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close


def write_query_to_parquet(outfile: str, headers: list[str], rows: Any) -> None:
    try:
        import polars as pl
    except ImportError:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg="The polars Python package must be installed to export data to the parquet format.",
        )
    rows_list = list(rows)
    if rows_list:
        df = pl.DataFrame(rows_list, schema=headers, orient="row")
    else:
        df = pl.DataFrame({h: [] for h in headers})
    filewriter_close(outfile)
    df.write_parquet(outfile)
