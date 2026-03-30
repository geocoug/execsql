from __future__ import annotations
from execsql.exceptions import ErrInfo

"""
Apache Feather and HDF5 export for execsql.

Provides :func:`write_query_to_feather` (Apache Arrow Feather v2 format
via ``pyarrow``) and :func:`write_query_to_hdf5` (HDF5 via ``pandas``
and ``tables``).  Used by ``EXPORT … FORMAT feather`` and
``FORMAT hdf5``.  Both packages are optional dependencies.
"""

from typing import Any

import execsql.state as _state
from execsql.models import DataTable
from execsql.types import DT_Boolean, DT_Date, DT_Timestamp, DT_TimestampTZ
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["write_query_to_feather", "write_query_to_hdf5"]


def write_query_to_feather(outfile: str, headers: list[str], rows: Any) -> None:
    """Write a row source as an Apache Arrow Feather v2 file using polars."""
    try:
        import polars as pl
    except ImportError as e:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg="The polars Python package must be installed to export data to the feather format.",
        ) from e
    rows_list = list(rows)
    if rows_list:
        df = pl.DataFrame(rows_list, schema=headers, orient="row")
    else:
        df = pl.DataFrame({h: [] for h in headers})
    filewriter_close(outfile)
    df.write_ipc(outfile)


def write_query_to_hdf5(
    table_name: str,
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
) -> None:
    """Execute a SELECT and write the result set to an HDF5 file using the tables library."""
    try:
        import tables
    except ImportError as e:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg="The tables Python library must be installed to export data to the HDF5 format.",
        ) from e
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e

    def h5type(datatype, size):
        if datatype in (_state.DT_Varchar, _state.DT_Text):
            t = tables.StringCol(size)
            do_cast = False
        elif datatype == _state.DT_Text:
            t = tables.StringCol(_state.conf.hdf5_text_len)
            do_cast = False
        elif datatype in (_state.DT_Integer, _state.DT_Long):
            t = tables.IntCol()
            do_cast = False
        elif datatype in (_state.DT_Float, _state.DT_Decimal):
            t = tables.Float64Col()
            do_cast = False
        elif datatype == DT_Boolean:
            t = tables.BoolCol()
            do_cast = False
        elif datatype in (DT_TimestampTZ, DT_Timestamp, DT_Date, _state.DT_Time):
            t = tables.StringCol(50)
            do_cast = True
        else:
            raise ErrInfo("error", other_msg=f"Invalid data type for export to HDF5: {repr(datatype)}")
        return t, do_cast

    # Create a dictionary of column names with the HDF5 data types
    tbl_desc = DataTable(hdrs, rows)
    h5type_dict = {}
    cast_flags = []
    # Iterate over hdrs instead of tbl_desc.cols to preserve column order.
    for h in hdrs:
        dt = [col for col in tbl_desc.cols if col.name == h][0].dt
        # dt is a tuple of: 0: the column name; 1: the data type class; 2: the maximum length or None if NA; other info.
        h5typ, as_str = h5type(dt[1], dt[2])
        h5type_dict[h] = h5typ
        cast_flags.append(as_str)
    # Open the HDF5 table
    filewriter_close(outfile)
    h5file_mode = "a" if append else "w"
    h5file = tables.open_file(outfile, mode=h5file_mode)
    h5grp = h5file.create_group("/", table_name, title=desc)
    h5tbl = h5file.create_table(h5grp, table_name, h5type_dict)
    # Write the data.
    hdrs, rows = db.select_rowsource(select_stmt)
    for datarow in rows:
        h5row = h5tbl.row
        for i, h in enumerate(hdrs):
            h5row[h] = datarow[i] if not cast_flags[i] else str(datarow[i])
        h5row.append()
    h5tbl.flush()
    h5file.close()
