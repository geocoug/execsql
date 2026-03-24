from __future__ import annotations

"""
CSV and delimited-text import for execsql.

Provides :func:`importtable` (imports a single delimited file into a new
or existing table) and :func:`importfile` (lower-level row iterator over
a delimited file), used by the ``IMPORT`` metacommand with ``FORMAT csv``,
``FORMAT tsv``, and ``FORMAT txt``.
"""

from pathlib import Path
from typing import Any

from execsql.exceptions import ErrInfo
from execsql.db.base import Database
import execsql.state as _state
from execsql.types import dbt_firebird


def importtable(
    db: Database,
    schemaname: str | None,
    tablename: str,
    filename: str,
    is_new: Any,
    skip_header_line: bool = True,
    quotechar: str | None = None,
    delimchar: str | None = None,
    encoding: str | None = None,
    junk_header_lines: int = 0,
) -> None:
    from execsql.utils.errors import exception_info

    conf = _state.conf
    if not Path(filename).is_file():
        raise ErrInfo(type="error", other_msg=f"Non-existent file ({filename}) used with the IMPORT metacommand")
    enc = encoding if encoding else conf.import_encoding

    # Lazy import of CsvFile
    from execsql.exporters.delimited import CsvFile

    inf = CsvFile(filename, enc, junk_header_lines=junk_header_lines)
    if quotechar and delimchar:
        if quotechar == "none":
            quotechar = None
        inf.lineformat(delimchar, quotechar, None)
    if is_new in (1, 2):
        inf.evaluate_column_types()
        sql = inf.create_table(db.type, schemaname, tablename)
        if is_new == 2:
            try:
                db.drop_table(db.schema_qualified_table_name(schemaname, tablename))
            except Exception:
                _state.exec_log.log_status_info(f"Could not drop existing table ({tablename}) for IMPORT metacommand")
                # Don't raise an exception; this may not be a problem because the table may not already exist.
        try:
            db.execute(sql)
            # Don't commit table creation here; the commit will be done after data import
            # ...except for Firebird.  Execute the commit directly via the connection so it is always done.
            if db.type == dbt_firebird:
                db.conn.commit()
        except Exception:
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_info(),
                other_msg=f"Could not create new table ({tablename}) for IMPORT metacommand",
            )
    else:
        if schemaname is not None:
            if not db.table_exists(tablename, schemaname):
                raise ErrInfo(
                    "error",
                    other_msg=f"Non-existent table name ({schemaname}.{tablename}) used with the IMPORT_FILE metacommand",
                )
        else:
            if not db.table_exists(tablename):
                raise ErrInfo(
                    "error",
                    other_msg=f"Non-existent table name ({tablename}) used with the IMPORT_FILE metacommand",
                )
    try:
        db.import_tabular_file(schemaname, tablename, inf, skipheader=True)
        db.commit()
    except ErrInfo:
        raise
    except Exception:
        fq_tablename = db.schema_qualified_table_name(schemaname, tablename)
        raise ErrInfo(
            "exception",
            exception_msg=exception_info(),
            other_msg=f"Can't import tabular file ({filename}) to table ({fq_tablename})",
        )
    inf.close()


def importfile(
    db: Database,
    schemaname: str | None,
    tablename: str,
    columname: str,
    filename: str,
) -> None:
    from execsql.utils.errors import exception_info

    if schemaname is not None:
        if not db.table_exists(tablename, schemaname):
            raise ErrInfo(
                "error",
                other_msg=f"Non-existent table name ({schemaname}.{tablename}) used with the IMPORT_FILE metacommand",
            )
    else:
        if not db.table_exists(tablename):
            raise ErrInfo(
                "error",
                other_msg=f"Non-existent table name ({tablename}) used with the IMPORT_FILE metacommand",
            )
    try:
        db.import_entire_file(schemaname, tablename, columname, filename)
        db.commit()
    except ErrInfo:
        raise
    except Exception:
        fq_tablename = db.schema_qualified_table_name(schemaname, tablename)
        raise ErrInfo(
            "exception",
            exception_msg=exception_info(),
            other_msg=f"Can't import file ({filename}) to table ({fq_tablename})",
        )
