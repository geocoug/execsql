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

__all__ = ["import_feather", "import_parquet"]


def import_feather(
    db: Database,
    schemaname: str | None,
    tablename: str,
    filename: str,
    is_new: Any,
) -> None:
    """Import an Apache Arrow Feather (IPC) file into a database table."""
    from execsql.utils.errors import exception_desc

    try:
        import polars as pl
    except Exception as e:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg="The polars Python library must be installed to import data from the Feather format.",
        ) from e
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
    """Import a Parquet file into a database table."""
    from execsql.utils.errors import exception_desc

    try:
        import polars as pl
    except Exception as e:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg="The polars Python library must be installed to import data from the Parquet format.",
        ) from e
    df = pl.read_parquet(filename)
    hdrs = df.columns
    data = [list(row) for row in df.rows()]
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
