from __future__ import annotations

"""
DuckDB database export for execsql.

Provides :func:`write_query_to_duckdb`, which writes a query result set
to a table in a DuckDB database file.  Used by ``EXPORT … FORMAT duckdb``.
Requires the ``execsql2[duckdb]`` extra.
"""

import datetime as _datetime
import decimal as _decimal
import math
from pathlib import Path
from typing import Any

from execsql.exceptions import ErrInfo
from execsql.types import dbt_duckdb

_DUCKDB_SAFE = (int, float, str, bytes, bool, _decimal.Decimal, _datetime.datetime, _datetime.date, _datetime.time)

__all__ = ["export_duckdb", "write_query_to_duckdb"]


def export_duckdb(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool,
    tablename: str,
) -> None:
    """Write pre-fetched rows to a named table in a DuckDB database file."""
    try:
        import duckdb
    except Exception:
        from execsql.utils.errors import fatal_error

        fatal_error("The duckdb module is required to export data in that format.")
        return

    from execsql.models import DataTable

    chunksize = 10000
    # B07a/F026: tablename and catalog are substituted from user input.
    # Identifier-quote the table-name interpolation site and use
    # placeholders for the information_schema literal-value query.
    qtable = dbt_duckdb.quoted(tablename)
    pre_exist = Path(outfile).is_file()
    ddb = duckdb.connect(outfile, read_only=False)
    if pre_exist:
        catalog = Path(outfile).stem
        curs = ddb.cursor()
        res = curs.execute(
            "select count(*) as rows from information_schema.tables where table_catalog = ? and table_name = ?;",
            (catalog, tablename),
        )
        rv = res.fetchone()
        if not (rv is None or rv[0] == 0):
            if append:
                raise ErrInfo(type="error", other_msg=f"The table {tablename} already exists in {outfile}.")
            else:
                curs.execute(f"drop table {qtable};")
        curs.close()
    # Construct and run the CREATE TABLE statement
    rowdata = list(rows)
    tablespec = DataTable(hdrs, rowdata, infer_strings=False)
    rowdata = [tuple(v if (v is None or isinstance(v, _DUCKDB_SAFE)) else str(v) for v in row) for row in rowdata]
    sql = tablespec.create_table(dbt_duckdb, schemaname=None, tablename=tablename)
    curs = ddb.cursor()
    curs.execute(sql)
    # Export all rows of data
    columns = [dbt_duckdb.quoted(col) for col in hdrs]
    colspec = ",".join(columns)
    paramspec = ",".join(("?",) * len(columns))
    sql = f"insert into {qtable} ({colspec}) values ({paramspec});"
    n_chunks = math.ceil(len(rowdata) / chunksize)
    curs.execute("BEGIN TRANSACTION;")
    for i in range(n_chunks):
        start = i * chunksize
        end = start + chunksize
        curs.executemany(sql, rowdata[start:end])
    curs.execute("COMMIT;")
    curs.close()
    ddb.close()


def write_query_to_duckdb(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool,
    tablename: str,
) -> None:
    """Execute a SELECT and write the result set to a named table in a DuckDB database."""
    from execsql.utils.errors import exception_desc

    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    export_duckdb(outfile, hdrs, rows, append, tablename)
