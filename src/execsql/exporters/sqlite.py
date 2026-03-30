from __future__ import annotations

"""
SQLite database export for execsql.

Provides :func:`write_query_to_sqlite`, which writes a query result set
to a table in an SQLite database file.  Used by ``EXPORT … FORMAT sqlite``.
"""

import math
from pathlib import Path
from typing import Any

from execsql.exceptions import ErrInfo
from execsql.types import dbt_sqlite

__all__ = ["export_sqlite", "write_query_to_sqlite"]


def export_sqlite(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool,
    tablename: str,
) -> None:
    """Write pre-fetched rows to a table in an SQLite database file, creating it if necessary."""
    import sqlite3

    from execsql.models import DataTable

    chunksize = 10000
    pre_exist = Path(outfile).is_file()
    sdb = sqlite3.connect(outfile)
    try:
        if pre_exist:
            curs = sdb.cursor()
            res = curs.execute(
                f"select name from sqlite_master where type='table' and name='{tablename}';",
            )
            rv = res.fetchone()
            if not (rv is None or rv[0] == 0):
                if append:
                    raise ErrInfo(type="error", other_msg=f"The table {tablename} already exists in {outfile}.")
                else:
                    curs.execute(f"drop table {tablename};")
            curs.close()
        # Construct and run the CREATE TABLE statement
        rowdata = list(rows)
        tablespec = DataTable(hdrs, rowdata)
        sql = tablespec.create_table(dbt_sqlite, schemaname=None, tablename=tablename)
        curs = sdb.cursor()
        curs.execute(sql)
        # Export all rows of data
        columns = [dbt_sqlite.quoted(col) for col in hdrs]
        colspec = ",".join(columns)
        paramspec = ",".join(("?",) * len(columns))
        sql = f"insert into {tablename} ({colspec}) values ({paramspec});"
        n_chunks = math.ceil(len(rowdata) / chunksize)
        for i in range(n_chunks):
            start = i * chunksize
            end = start + chunksize
            curs.executemany(sql, rowdata[start:end])
        sdb.commit()
        curs.close()
    finally:
        sdb.close()


def write_query_to_sqlite(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool,
    tablename: str,
) -> None:
    """Execute a SELECT and write the result set to a named table in an SQLite database."""
    from execsql.utils.errors import exception_desc

    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    export_sqlite(outfile, hdrs, rows, append, tablename)
