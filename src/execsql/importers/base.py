from __future__ import annotations

"""
Shared data-import utilities for execsql.

Provides :func:`import_data_table`, the common back-end used by all
importer sub-modules.  Given a :class:`~execsql.models.DataTable` and a
:class:`~execsql.db.base.Database`, it generates and executes a
``CREATE TABLE`` statement and inserts all rows using the column type
information inferred during scanning.
"""

import os
import re
from typing import Any, List, Optional

from execsql.exceptions import ErrInfo
from execsql.db.base import Database
import execsql.state as _state


def import_data_table(
    db: Database,
    schemaname: Optional[str],
    tablename: str,
    is_new: Any,
    hdrs: List[str],
    data: List[Any],
) -> None:
    from execsql.utils.errors import exception_info

    conf = _state.conf
    if any([x is None or len(x.strip()) == 0 for x in hdrs]):
        if conf.del_empty_cols:
            blanks = [i for i in range(len(hdrs)) if hdrs[i] is None or len(hdrs[i].strip()) == 0]
            while len(blanks) > 0:
                b = blanks.pop()
                del hdrs[b]
                for r in range(len(data)):
                    del data[r][b]
        else:
            if conf.create_col_hdrs:
                for i in range(len(hdrs)):
                    if hdrs[i] is None or len(hdrs[i]) == 0:
                        hdrs[i] = f"Col{i + 1}"
            else:
                raise ErrInfo(type="error", other_msg="The input data has missing column headers.")
    if conf.clean_col_hdrs:
        from execsql.utils.strings import clean_words

        hdrs = clean_words(hdrs)
    if conf.trim_col_hdrs != "none":
        from execsql.utils.strings import trim_words

        hdrs = trim_words(hdrs, conf.trim_col_hdrs)
    if conf.fold_col_hdrs != "no":
        from execsql.utils.strings import fold_words

        hdrs = fold_words(hdrs, conf.fold_col_hdrs)
    if conf.dedup_col_hdrs:
        from execsql.utils.strings import dedup_words

        hdrs = dedup_words(hdrs)

    def get_ts():
        if not get_ts.tablespec:
            from execsql.models import DataTable

            get_ts.tablespec = DataTable(hdrs, data)
        return get_ts.tablespec

    get_ts.tablespec = None

    exec_log = _state.exec_log
    dbt_firebird = _state.dbt_firebird

    if is_new:
        if is_new == 2:
            tblspec = db.schema_qualified_table_name(schemaname, tablename)
            try:
                db.drop_table(tblspec)
            except Exception:
                exec_log.log_status_info(f"Could not drop existing table ({tblspec}) for IMPORT metacommand")
        sql = get_ts().create_table(db.type, schemaname, tablename)
        try:
            db.execute(sql)
            # Don't commit here; commit will be done after populating the table
            # ...except for Firebird.
            if db.type == dbt_firebird:
                db.conn.commit()
        except Exception:
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_info(),
                other_msg=f"Could not create new table ({tablename}) for IMPORT metacommand",
            )
    table_cols = db.table_columns(tablename, schemaname)
    if conf.import_common_cols_only:
        import_cols = [col for col in hdrs if col.lower() in [tc.lower() for tc in table_cols]]
    else:
        src_extra_cols = [col for col in hdrs if col.lower() not in [tc.lower() for tc in table_cols]]
        if len(src_extra_cols) > 0:
            raise ErrInfo(
                type="error",
                other_msg=f"The input data table has the following columns that are not in table {tablename}: {', '.join(src_extra_cols)}.",
            )
        import_cols = hdrs
    try:
        db.populate_table(schemaname, tablename, data, import_cols, get_ts)
        db.commit()
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo("db", "Call to populate_table when importing data", exception_msg=exception_info())
