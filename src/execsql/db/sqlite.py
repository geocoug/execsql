from __future__ import annotations

"""
SQLite database adapter for execsql.

Implements :class:`SQLiteDatabase`, which connects to SQLite database
files via the Python standard library ``sqlite3`` module.  Corresponds to
``-t l`` on the CLI.
"""

import datetime
import re
from decimal import Decimal
from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
import execsql.state as _state

__all__ = ["SQLiteDatabase"]

DEFAULT_CONNECT_TIMEOUT = 30  # seconds


class SQLiteDatabase(Database):
    """SQLite adapter using the Python standard-library sqlite3 module."""

    def __init__(self, SQLite_fn: str, timeout: float = DEFAULT_CONNECT_TIMEOUT) -> None:
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
        self.timeout = timeout
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return f"SQLiteDatabase({self.db_name!r})"

    def open_db(self) -> None:
        """Open a connection to the SQLite database file."""
        import sqlite3

        if self.conn is None:
            try:
                self.conn = sqlite3.connect(self.db_name, timeout=self.timeout)
            except ErrInfo:
                raise
            except Exception as e:
                raise ErrInfo(
                    type="exception",
                    exception_msg=exception_desc(),
                    other_msg=f"Can't open SQLite database {self.db_name}",
                ) from e
        pragma_cols, pragma_data = self.select_data("pragma encoding;")
        self.encoding = pragma_data[0][0]

    def exec_cmd(self, querycommand: str) -> None:
        """Execute a query command as a view selection, since SQLite lacks stored procedures."""
        # SQLite does not support stored functions or views, so the querycommand
        # is treated as (and therefore must be) a view.
        with self._cursor() as curs:
            cmd = f"select * from {querycommand};"
            try:
                curs.execute(cmd)
                _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
            except Exception:
                self.rollback()
                raise

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        """Return True if the named table exists in the SQLite database."""
        with self._cursor() as curs:
            sql = "select name from sqlite_master where type='table' and name=?;"
            try:
                curs.execute(sql, (table_name,))
            except ErrInfo:
                raise
            except Exception as e:
                self.rollback()
                raise ErrInfo(
                    type="db",
                    command_text=sql,
                    exception_msg=exception_desc(),
                    other_msg=f'Failed test for existence of SQLite table "{table_name}";',
                ) from e
            rows = curs.fetchall()
        return len(rows) > 0

    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema_name: str | None = None,
    ) -> bool:
        """Return True if the named column exists in the given SQLite table."""
        cols = self.table_columns(table_name, schema_name)
        return column_name in cols

    def table_columns(self, table_name: str, schema_name: str | None = None) -> list[str]:
        """Return a list of column names for the given SQLite table."""
        with self._cursor() as curs:
            quoted_tbl = self.quote_identifier(table_name)
            sql = f"select * from {quoted_tbl} where 1=0;"
            try:
                curs.execute(sql)
            except ErrInfo:
                raise
            except Exception as e:
                self.rollback()
                raise ErrInfo(
                    type="db",
                    command_text=sql,
                    exception_msg=exception_desc(),
                    other_msg=f"Failed to get column names for table {table_name} of {self.name()}",
                ) from e
            return [d[0] for d in curs.description]

    def view_exists(self, view_name: str) -> bool:
        """Return True if the named view exists in the SQLite database."""
        with self._cursor() as curs:
            sql = "select name from sqlite_master where type='view' and name=?;"
            try:
                curs.execute(sql, (view_name,))
            except ErrInfo:
                raise
            except Exception as e:
                self.rollback()
                raise ErrInfo(
                    type="db",
                    command_text=sql,
                    exception_msg=exception_desc(),
                    other_msg=f'Failed test for existence of SQLite view "{view_name}";',
                ) from e
            rows = curs.fetchall()
        return len(rows) > 0

    def schema_exists(self, schema_name: str) -> bool:
        """Return False; SQLite does not support schemas."""
        return False

    def drop_table(self, tablename: str) -> None:
        """Drop the named table from the SQLite database if it exists."""
        tablename = self.type.quoted(tablename)
        self.execute(f"drop table if exists {tablename};")

    def populate_table(
        self,
        schema_name: str | None,
        table_name: str,
        rowsource: Any,
        column_list: list[str],
        tablespec_src: Any,
    ) -> None:
        """Populate a SQLite table from a row source generator."""
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
        total_rows = 0
        for datalineno, line in enumerate(rowsource):
            # Skip empty rows.
            if not (len(line) == 1 and line[0] is None):
                if len(line) < len(columns):
                    raise ErrInfo(
                        type="error",
                        other_msg=f"Too few values on data line {datalineno} of input.",
                    )
                if _state.conf.trim_strings or _state.conf.replace_newlines or not _state.conf.empty_strings:
                    for i in range(len(line)):
                        if line[i] is not None and isinstance(line[i], _state.stringtypes):
                            if _state.conf.trim_strings:
                                line[i] = line[i].strip()
                            if _state.conf.replace_newlines:
                                line[i] = re.sub(r"[\s\t]*[\r\n]+[\s\t]*", " ", line[i])
                            if not _state.conf.empty_strings and line[i].strip() == "":
                                line[i] = None
                linedata = [line[ix] for ix in data_indexes]
                # Convert datetime, time, and Decimal values to strings.
                for i in range(len(linedata)):
                    if type(linedata[i]) in (datetime.datetime, datetime.time, Decimal):
                        linedata[i] = str(linedata[i])
                add_line = True
                if not _state.conf.empty_rows:
                    add_line = not all(c is None for c in linedata)
                if add_line:
                    try:
                        curs.execute(sql, linedata)
                    except ErrInfo:
                        raise
                    except Exception as e:
                        self.rollback()
                        raise ErrInfo(
                            type="db",
                            command_text=sql,
                            exception_msg=exception_desc(),
                            other_msg=f"Can't load data into table {sq_name} from line {{{line}}}",
                        ) from e
                    total_rows += 1
                    interval = getattr(_state.conf, "import_progress_interval", 0)
                    if _state.exec_log and interval > 0 and total_rows % interval == 0:
                        _state.exec_log.log_status_info(
                            f"IMPORT into {sq_name}: {total_rows} rows imported so far.",
                        )
        if _state.exec_log:
            _state.exec_log.log_status_info(
                f"IMPORT into {sq_name} complete: {total_rows} rows imported.",
            )

    def import_entire_file(
        self,
        schema_name: str | None,
        table_name: str,
        column_name: str,
        file_name: str,
    ) -> None:
        """Import an entire binary file into a single column of a table."""
        import sqlite3

        with open(file_name, "rb") as f:
            filedata = f.read()
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        quoted_col = self.quote_identifier(column_name)
        sql = f"insert into {sq_name} ({quoted_col}) values ({self.paramsubs(1)});"
        self.cursor().execute(sql, (sqlite3.Binary(filedata),))
