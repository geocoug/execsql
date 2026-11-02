from __future__ import annotations

"""
SQLite database export for execsql.

Provides :func:`write_query_to_sqlite`, which writes a query result set
to a table in an SQLite database file.  Used by ``EXPORT … FORMAT sqlite``.
"""

from decimal import Decimal
from typing import Any

from execsql.exceptions import ErrInfo
from execsql.types import dbt_sqlite

_SQLITE_SAFE = (int, float, str, bytes)

__all__ = ["export_sqlite", "write_query_to_sqlite"]


def _affinity(declaration: str) -> str:
    """Return SQLite's affinity, observing its ordered type-name rules."""
    name = declaration.upper()
    if "INT" in name:
        return "INTEGER"
    if any(part in name for part in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if not name or "BLOB" in name:
        return "BLOB"
    if any(part in name for part in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _exact_number(value: Decimal, affinity: str) -> int | float:
    """Bind a Decimal only if its numeric readback retains the source value."""
    if value.is_nan():
        raise ValueError("NaN has no SQLite numeric representation")
    if value.is_infinite():
        return float(value)
    if -(2**63) <= value <= 2**63 - 1 and value == value.to_integral_value():
        number = int(value)
        if affinity == "REAL" and Decimal(repr(float(number))) != value:
            raise ValueError("the integer is not exactly representable in a SQLite REAL")
        return number
    result = float(value)
    if Decimal(repr(result)) != value:
        raise ValueError("the decimal cannot be read back without losing digits")
    return result


def export_sqlite(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool,
    tablename: str,
) -> None:
    """Export rows, rejecting lossy decimals before opening the destination.

    Numeric Decimal values must read back equal to their source; spelling and
    scale are not retained. Text columns retain their string representation.
    Replacement DDL and inserts share a transaction, restored on any failure.
    APPEND still refuses an existing table.
    """
    import sqlite3

    from execsql.models import DataTable

    rowdata = list(rows)
    # Non-finite Decimals cannot pass the general-purpose integer scanner.
    # A fractional placeholder preserves numeric inference without changing data.
    scanrows = (
        tuple(Decimal("0.5") if isinstance(v, Decimal) and not v.is_finite() else v for v in row) for row in rowdata
    )
    tablespec = DataTable(hdrs, scanrows, infer_strings=False)
    create_sql = tablespec.create_table(dbt_sqlite, schemaname=None, tablename=tablename)
    qtable = dbt_sqlite.quoted(tablename)
    # Let SQLite expose the generated declarations, including quoted identifiers.
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute(create_sql)
        affinities = [_affinity(col[2]) for col in probe.execute(f"PRAGMA table_info({qtable})")]
        converted = []
        for row in rowdata:
            bound: list[Any] = []
            for i, value in enumerate(row):
                if isinstance(value, Decimal) and i < len(affinities) and affinities[i] not in ("TEXT", "BLOB"):
                    try:
                        number = _exact_number(value, affinities[i])
                        if value.is_finite():
                            # Preserve the previous stored value too: SQLite's text
                            # parser can round differently from Python's conversion.
                            cast_type = "REAL" if affinities[i] == "REAL" else "NUMERIC"
                            previous = probe.execute(f"SELECT CAST(? AS {cast_type})", (str(value),)).fetchone()[0]
                            if Decimal(repr(previous)) != value:
                                raise ValueError("SQLite's numeric conversion loses source digits")
                        bound.append(number)
                    except ValueError as exc:
                        raise ErrInfo(
                            type="error",
                            other_msg=(
                                f"Can't export column {hdrs[i]} to SQLite table {tablename}: {value} "
                                f"cannot be stored without losing digits. Nothing was written. "
                                "To preserve the exact text, export CAST(column AS VARCHAR)."
                            ),
                        ) from exc
                else:
                    bound.append(value if value is None or isinstance(value, _SQLITE_SAFE) else str(value))
            converted.append(tuple(bound))
    finally:
        probe.close()

    sdb = sqlite3.connect(outfile, isolation_level=None)
    try:
        sdb.execute("BEGIN")
        exists = sdb.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tablename,)).fetchone()
        if exists is not None:
            if append:
                raise ErrInfo(type="error", other_msg=f"The table {tablename} already exists in {outfile}.")
            sdb.execute(f"DROP TABLE {qtable}")
        sdb.execute(create_sql)
        columns = ",".join(dbt_sqlite.quoted(col) for col in hdrs)
        parameters = ",".join("?" for _ in hdrs)
        insert_sql = f"INSERT INTO {qtable} ({columns}) VALUES ({parameters})"
        chunksize = 10000
        for start in range(0, len(converted), chunksize):
            sdb.executemany(insert_sql, converted[start : start + chunksize])
        sdb.commit()
    finally:
        # close() rolls back an open transaction, including on BaseException.
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
