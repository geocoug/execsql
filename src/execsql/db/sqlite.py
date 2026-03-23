from __future__ import annotations

"""
SQLite database adapter for execsql.

Implements :class:`SQLiteDatabase`, which connects to SQLite database
files via the Python standard library ``sqlite3`` module.  Corresponds to
``-t l`` on the CLI.
"""

import datetime
import io
import re
from decimal import Decimal
from typing import Any, List, Optional

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
import execsql.state as _state


class SQLiteDatabase(Database):
    def __init__(self, SQLite_fn: str) -> None:
        try:
            import sqlite3  # noqa: F401
        except Exception:
            fatal_error("The sqlite3 module is required.")
        from execsql.types import dbt_sqlite

        self.type = dbt_sqlite
        self.server_name = None
        self.db_name = SQLite_fn
        self.user = None
        self.need_passwd = False
        self.encoding = "UTF-8"
        self.encode_commands = False
        self.paramstr = "?"
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return f"SQLiteDatabase({self.db_name!r})"

    def open_db(self) -> None:
        import sqlite3

        if self.conn is None:
            try:
                self.conn = sqlite3.connect(self.db_name)
            except ErrInfo:
                raise
            except Exception:
                raise ErrInfo(
                    type="exception",
                    exception_msg=exception_desc(),
                    other_msg=f"Can't open SQLite database {self.db_name}",
                )
        pragma_cols, pragma_data = self.select_data("pragma encoding;")
        self.encoding = pragma_data[0][0]

    def exec_cmd(self, querycommand: str) -> None:
        # SQLite does not support stored functions or views, so the querycommand
        # is treated as (and therefore must be) a view.
        curs = self.cursor()
        cmd = f"select * from {querycommand};"
        try:
            curs.execute(cmd.encode(self.encoding))
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            self.rollback()
            raise

    def table_exists(self, table_name: str, schema_name: Optional[str] = None) -> bool:
        curs = self.cursor()
        sql = f"select name from sqlite_master where type='table' and name='{table_name}';"
        try:
            curs.execute(sql)
        except ErrInfo:
            raise
        except Exception:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f'Failed test for existence of SQLite table "{table_name}";',
            )
        rows = curs.fetchall()
        return len(rows) > 0

    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema_name: Optional[str] = None,
    ) -> bool:
        curs = self.cursor()
        sql = f"select {column_name} from {table_name} limit 1;"
        try:
            curs.execute(sql)
        except Exception:
            return False
        return True

    def table_columns(self, table_name: str, schema_name: Optional[str] = None) -> List[str]:
        curs = self.cursor()
        sql = f"select * from {table_name} where 1=0;"
        try:
            curs.execute(sql)
        except ErrInfo:
            raise
        except Exception:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed to get column names for table {table_name} of {self.name()}",
            )
        return [d[0] for d in curs.description]

    def view_exists(self, view_name: str) -> bool:
        curs = self.cursor()
        sql = f"select name from sqlite_master where type='view' and name='{view_name}';"
        try:
            curs.execute(sql)
        except ErrInfo:
            raise
        except Exception:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f'Failed test for existence of SQLite view "{view_name}";',
            )
        rows = curs.fetchall()
        return len(rows) > 0

    def schema_exists(self, schema_name: str) -> bool:
        return False

    def drop_table(self, tablename: str) -> None:
        tablename = self.type.quoted(tablename)
        self.execute(f"drop table if exists {tablename};")

    def populate_table(
        self,
        schema_name: Optional[str],
        table_name: str,
        rowsource: Any,
        column_list: List[str],
        tablespec_src: Any,
    ) -> None:
        # The rowsource argument must be a generator yielding a list of values for the columns of the table.
        # The column_list argument must an iterable containing column names in the same order as produced by the rowsource.
        sq_name = self.schema_qualified_table_name(None, table_name)
        # Check specified column names.
        tablespec = tablespec_src()
        ts_colnames = [col.name for col in tablespec.cols]
        src_missing_cols = [col for col in column_list if col not in ts_colnames]
        if len(src_missing_cols) > 0:
            raise ErrInfo(
                type="error",
                other_msg=f"Data source is missing the following columns: {', '.join(src_missing_cols)}.",
            )
        # Get column indexes for selected column names.
        columns = column_list
        data_indexes = [ts_colnames.index(col) for col in columns]
        # Construct prepared SQL statement
        colspec = ",".join([self.type.quoted(c) for c in columns])
        paramspec = ",".join(["?" for c in columns])
        sql = f"insert into {sq_name} ({colspec}) values ({paramspec});"
        curs = self.cursor()
        for datalineno, line in enumerate(rowsource):
            # Skip empty rows.
            if not (len(line) == 1 and line[0] is None):
                if len(line) < len(columns):
                    raise ErrInfo(
                        type="error",
                        other_msg=f"Too few values on data line {datalineno} of input.",
                    )
                linedata = [line[ix] for ix in data_indexes]
                if _state.conf.trim_strings or _state.conf.replace_newlines or not _state.conf.empty_strings:
                    for i in range(len(line)):
                        if line[i] is not None and isinstance(line[i], _state.stringtypes):
                            if _state.conf.trim_strings:
                                line[i] = line[i].strip()
                            if _state.conf.replace_newlines:
                                line[i] = re.sub(r"[\s\t]*[\r\n]+[\s\t]*", " ", line[i])
                            if not _state.conf.empty_strings:
                                if line[i].strip() == "":
                                    line[i] = None
                # Convert datetime, time, and Decimal values to strings.
                for i in range(len(linedata)):
                    if type(linedata[i]) in (datetime.datetime, datetime.time, Decimal):
                        linedata[i] = str(linedata[i])
                add_line = True
                if not _state.conf.empty_rows:
                    add_line = not all([c is None for c in linedata])
                if add_line:
                    try:
                        curs.execute(sql, linedata)
                    except ErrInfo:
                        raise
                    except Exception:
                        self.rollback()
                        raise ErrInfo(
                            type="db",
                            command_text=sql,
                            exception_msg=exception_desc(),
                            other_msg=f"Can't load data into table {sq_name} from line {{{line}}}",
                        )

    def import_entire_file(
        self,
        schema_name: Optional[str],
        table_name: str,
        column_name: str,
        file_name: str,
    ) -> None:
        import sqlite3

        with io.open(file_name, "rb") as f:
            filedata = f.read()
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        sql = f"insert into {sq_name} ({column_name}) values ({self.paramsubs(1)});"
        self.cursor().execute(sql, (sqlite3.Binary(filedata),))
