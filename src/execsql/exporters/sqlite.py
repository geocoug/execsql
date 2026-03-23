from __future__ import annotations

"""
SQLite database export for execsql.

Provides :func:`write_query_to_sqlite`, which writes a query result set
to a table in an SQLite database file.  Used by ``EXPORT … FORMAT sqlite``.
"""

import math
import os
from typing import Any, List, Optional

from execsql.exceptions import ErrInfo
import execsql.state as _state


def export_sqlite(
    outfile: str,
    hdrs: List[str],
    rows: Any,
    append: bool,
    tablename: str,
) -> None:
    import sqlite3

    from execsql.models import DataTable
    from execsql.utils.errors import exception_info

    chunksize = 10000
    pre_exist = os.path.isfile(outfile)
    sdb = sqlite3.connect(outfile)
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
    dbt_sqlite = _state.dbt_sqlite
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
    sdb.close()


def write_query_to_sqlite(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool,
    tablename: str,
) -> None:
    from execsql.utils.errors import exception_info

    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo("db", select_stmt, exception_msg=exception_info())
    export_sqlite(outfile, hdrs, rows, append, tablename)
