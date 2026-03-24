from __future__ import annotations

"""
Feather and Parquet import for execsql.

Provides :func:`import_feather` (Apache Arrow Feather v2 / Arrow IPC via
``polars``) and :func:`import_parquet` (Parquet format via ``polars``),
used by ``IMPORT … FORMAT feather`` and ``FORMAT parquet``.
"""

from typing import Any

from execsql.exceptions import ErrInfo
from execsql.db.base import Database
from execsql.importers.base import import_data_table


def import_feather(
    db: Database,
    schemaname: str | None,
    tablename: str,
    filename: str,
    is_new: Any,
) -> None:
    from execsql.utils.errors import exception_info

    try:
        import polars as pl
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_info(),
            other_msg="The polars Python library must be installed to import data from the Feather format.",
        )
    df = pl.read_ipc(filename)
    hdrs = df.columns
    data = [list(row) for row in df.rows()]
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)


def import_parquet(
    db: Database,
    schemaname: str | None,
    tablename: str,
    filename: str,
    is_new: Any,
) -> None:
    from execsql.utils.errors import exception_info

    try:
        import polars as pl
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_info(),
            other_msg="The polars Python library must be installed to import data from the Parquet format.",
        )
    df = pl.read_parquet(filename)
    hdrs = df.columns
    data = [list(row) for row in df.rows()]
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
