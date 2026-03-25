from __future__ import annotations

"""
Abstract base database class and connection pool.

:class:`Database` defines the interface that every DBMS adapter must
implement: ``open_db()``, ``execute()``, ``cursor()``,
``select_rowsource()``, ``get_table_list()``, etc.  Concrete adapters in
sibling modules subclass it and override these methods for their specific
driver.

:class:`DatabasePool` is a dict-like container that maps string aliases to
open :class:`Database` instances and tracks which connection is currently
active.  It is the canonical ``_state.dbs`` object.
"""

import re
from typing import Any
from collections.abc import Callable, Generator, Iterator

from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc
import execsql.state as _state


class Database:
    """Abstract base class for all database connections."""

    dt_cast: dict[type, Callable] = {}  # populated per-subclass or in __init__

    def __init__(
        self,
        server_name: str | None,
        db_name: str | None,
        user_name: str | None = None,
        need_passwd: bool | None = None,
        port: int | None = None,
        encoding: str | None = None,
    ) -> None:
        self.type = None
        self.server_name = server_name
        self.db_name = db_name
        self.user = user_name
        self.need_passwd = need_passwd
        self.password: str | None = None
        self.port = port
        self.encoding = encoding
        self.encode_commands = True
        self.paramstr = "?"
        self.conn = None
        self.autocommit = True

    def __repr__(self) -> str:
        return (
            f"Database({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.encoding!r})"
        )

    def name(self) -> str:
        if self.server_name:
            return f"{self.type.dbms_id}(server {self.server_name}; database {self.db_name})"
        else:
            return f"{self.type.dbms_id}(file {self.db_name})"

    def open_db(self) -> None:
        from execsql.exceptions import DatabaseNotImplementedError

        raise DatabaseNotImplementedError(self.name(), "open_db")

    def cursor(self):
        if self.conn is None:
            self.open_db()
        return self.conn.cursor()

    def close(self) -> None:
        if self.conn:
            if not self.autocommit:
                _state.exec_log.log_status_info(
                    f"Closing {self.name()} when AUTOCOMMIT is OFF; transactions may not have completed.",
                )
            self.conn.close()
            self.conn = None

    def quote_identifier(self, identifier: str) -> str:
        """Return *identifier* wrapped in double-quotes with any embedded
        double-quotes escaped (standard SQL identifier quoting)."""
        return '"' + identifier.replace('"', '""') + '"'

    def paramsubs(self, paramcount: int) -> str:
        return ",".join((self.paramstr,) * paramcount)

    def execute(self, sql: Any, paramlist: list | None = None) -> None:
        # A shortcut to self.cursor().execute() that handles encoding.
        # Whether or not encoding is needed depends on the DBMS.
        if type(sql) in (tuple, list):
            sql = " ".join(sql)
        try:
            curs = self.cursor()
            if paramlist is None:
                curs.execute(sql)
            else:
                curs.execute(sql, paramlist)
            try:
                # DuckDB does not support the 'rowcount' attribute.
                _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
            except Exception:
                pass  # Non-critical: some drivers lack rowcount support.
        except Exception:
            try:
                self.rollback()
            except Exception:
                pass  # Rollback is best-effort after a failed execute.
            raise

    def exec_cmd(self, querycommand: str) -> None:
        from execsql.exceptions import DatabaseNotImplementedError

        raise DatabaseNotImplementedError(self.name(), "exec_cmd")

    def autocommit_on(self) -> None:
        self.autocommit = True

    def autocommit_off(self) -> None:
        self.autocommit = False

    def commit(self) -> None:
        if self.conn and self.autocommit:
            self.conn.commit()

    def rollback(self) -> None:
        if self.conn:
            try:
                self.conn.rollback()
            except Exception:
                pass  # Best-effort; connection may already be closed.

    def schema_qualified_table_name(self, schema_name: str | None, table_name: str) -> str:
        table_name = self.type.quoted(table_name)
        if schema_name:
            schema_name = self.type.quoted(schema_name)
            return f"{schema_name}.{table_name}"
        return table_name

    def select_data(self, sql: str) -> tuple[list[str], list]:
        # Returns the results of the sql select statement.
        curs = self.cursor()
        try:
            curs.execute(sql)
        except Exception:
            self.rollback()
            raise
        try:
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            pass  # Non-critical: some drivers lack rowcount support.
        rows = curs.fetchall()
        return [d[0] for d in curs.description], rows

    def select_rowsource(self, sql: str) -> tuple[list[str], Generator]:
        # Return 1) a list of column names, and 2) an iterable that yields rows.
        curs = self.cursor()
        try:
            # DuckDB cursors have no 'arraysize' attribute.
            curs.arraysize = _state.conf.export_row_buffer
        except Exception:
            pass  # Non-critical: not all drivers support arraysize.
        try:
            curs.execute(sql)
        except Exception:
            self.rollback()
            raise
        try:
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            pass  # Non-critical: some drivers lack rowcount support.

        def decode_row() -> Generator:
            while True:
                rows = curs.fetchmany()
                if not rows:
                    break
                else:
                    for row in rows:
                        if self.encoding:
                            yield [
                                c.decode(self.encoding, "backslashreplace") if isinstance(c, bytes) else c for c in row
                            ]
                        else:
                            yield row

        return [d[0] for d in curs.description], decode_row()

    def select_rowdict(self, sql: str) -> tuple[list[str], Iterator]:
        # Return an iterable that yields dictionaries of row data
        curs = self.cursor()
        try:
            curs.execute(sql)
        except Exception:
            self.rollback()
            raise
        try:
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            pass  # Non-critical: some drivers lack rowcount support.
        hdrs = [d[0] for d in curs.description]

        def dict_row() -> dict | None:
            row = curs.fetchone()
            if row:
                if self.encoding:
                    r = [c.decode(self.encoding, "backslashreplace") if isinstance(c, bytes) else c for c in row]
                else:
                    r = row
                return dict(zip(hdrs, r))
            else:
                return None

        return hdrs, iter(dict_row, None)

    def schema_exists(self, schema_name: str) -> bool:
        curs = self.cursor()
        sql = f"SELECT schema_name FROM information_schema.schemata WHERE schema_name = {self.paramstr};"
        curs.execute(sql, (schema_name,))
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        params: list = [table_name]
        schema_clause = ""
        if schema_name:
            schema_clause = f" and table_schema={self.paramstr}"
            params.append(schema_name)
        sql = f"select table_name from information_schema.tables where table_name = {self.paramstr}{schema_clause};"
        try:
            curs.execute(sql, params)
        except ErrInfo:
            raise
        except Exception:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of table {table_name} in {self.name()}",
            )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema_name: str | None = None,
    ) -> bool:
        curs = self.cursor()
        params: list = [table_name]
        schema_clause = ""
        if schema_name:
            schema_clause = f" and table_schema={self.paramstr}"
            params.append(schema_name)
        params.append(column_name)
        sql = (
            f"select column_name from information_schema.columns "
            f"where table_name={self.paramstr}{schema_clause} "
            f"and column_name={self.paramstr};"
        )
        try:
            curs.execute(sql, params)
        except ErrInfo:
            raise
        except Exception:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of column {column_name} in table {table_name} of {self.name()}",
            )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def table_columns(self, table_name: str, schema_name: str | None = None) -> list[str]:
        curs = self.cursor()
        params: list = [table_name]
        schema_clause = ""
        if schema_name:
            schema_clause = f" and table_schema={self.paramstr}"
            params.append(schema_name)
        sql = (
            f"select column_name from information_schema.columns "
            f"where table_name={self.paramstr}{schema_clause} "
            f"order by ordinal_position;"
        )
        try:
            curs.execute(sql, params)
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
        rows = curs.fetchall()
        curs.close()
        return [row[0] for row in rows]

    def view_exists(self, view_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        params: list = [view_name]
        schema_clause = ""
        if schema_name:
            schema_clause = f" and table_schema={self.paramstr}"
            params.append(schema_name)
        sql = f"select table_name from information_schema.views where table_name = {self.paramstr}{schema_clause};"
        try:
            curs.execute(sql, params)
        except ErrInfo:
            raise
        except Exception:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of view {view_name} in {self.name()}",
            )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def role_exists(self, rolename: str) -> bool:
        from execsql.exceptions import DatabaseNotImplementedError

        raise DatabaseNotImplementedError(self.name(), "role_exists")

    def drop_table(self, tablename: str) -> None:
        # The 'tablename' argument should be schema-qualified and quoted as necessary.
        self.execute(f"drop table if exists {tablename} cascade;")
        self.commit()

    def populate_table(
        self,
        schema_name: str | None,
        table_name: str,
        rowsource: Any,
        column_list: list[str],
        tablespec_src: Callable,
    ) -> None:
        # The rowsource argument must be a generator yielding a list of values for the columns of the table.
        # The column_list argument must an iterable containing column names.  This may be a subset of
        # the names of columns in the rowsource.
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        # Check that the specified column names are in the input data.
        tablespec = tablespec_src()
        ts_colnames = [col.name for col in tablespec.cols]
        src_missing_cols = [col for col in column_list if col not in ts_colnames]
        if len(src_missing_cols) > 0:
            raise ErrInfo(
                type="error",
                other_msg=f"Data source is missing the following columns: {', '.join(src_missing_cols)}.",
            )
        # Create a list of selected columns in the order in which they appear in the rowsource,
        # and a list of Booleans indicating whether each column in the rowsource should be included.
        sel_cols = [col for col in ts_colnames if col in column_list]
        incl_col = [col in column_list for col in ts_colnames]
        # Type conversion functions for the rowsource.
        type_objs = [col.column_type()[1]() for col in tablespec.cols]
        type_mod_fn = [self.type.dialect[col.column_type()[1]][3] for col in tablespec.cols]
        # Construct INSERT statement.
        columns = [self.type.quoted(col) for col in sel_cols]
        colspec = ",".join(columns)
        paramspec = self.paramsubs(len(columns))
        sql = f"insert into {sq_name} ({colspec}) values ({paramspec});"
        rows = iter(rowsource)
        curs = self.cursor()
        eof = False
        total_rows = 0

        # Optional rich progress bar for long-running imports.
        use_progress = getattr(_state.conf, "show_progress", False)
        progress_ctx = None
        task_id = None
        if use_progress:
            try:
                from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

                progress_ctx = Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]IMPORT[/bold blue] {task.description}"),
                    BarColumn(bar_width=None),
                    TextColumn("[progress.percentage]{task.completed:,} rows"),
                    TimeElapsedColumn(),
                    transient=True,
                )
            except ImportError:
                use_progress = False

        def _import_loop() -> int:
            nonlocal eof, total_rows, task_id
            while True:
                b = []
                for _j in range(_state.conf.import_row_buffer):
                    try:
                        line = next(rows)
                    except StopIteration:
                        eof = True
                    else:
                        if len(line) > len(ts_colnames):
                            extra_err = True
                            if _state.conf.del_empty_cols:
                                any_non_empty = False
                                for cno in range(len(ts_colnames), len(line)):
                                    if not (
                                        line[cno] is None
                                        or (
                                            not _state.conf.empty_strings
                                            and isinstance(line[cno], _state.stringtypes)
                                            and len(line[cno].strip()) == 0
                                        )
                                        and _state.conf.del_empty_cols
                                    ):
                                        any_non_empty = True
                                        break
                                extra_err = any_non_empty
                            if extra_err:
                                raise ErrInfo(
                                    type="error",
                                    other_msg=f"Too many data columns on line {{{line}}}",
                                )
                            else:
                                line = line[: len(ts_colnames)]
                        if not (len(line) == 1 and line[0] is None):
                            if (
                                _state.conf.trim_strings
                                or _state.conf.replace_newlines
                                or not _state.conf.empty_strings
                            ):
                                for i in range(len(line)):
                                    if line[i] is not None and isinstance(
                                        line[i],
                                        _state.stringtypes,
                                    ):
                                        if _state.conf.trim_strings:
                                            line[i] = line[i].strip()
                                        if _state.conf.replace_newlines:
                                            line[i] = re.sub(
                                                r"[\s\t]*[\r\n]+[\s\t]*",
                                                " ",
                                                line[i],
                                            )
                                        if not _state.conf.empty_strings and line[i].strip() == "":
                                            line[i] = None
                            lt = [
                                type_objs[i].from_data(val) if val is not None else None for i, val in enumerate(line)
                            ]
                            lt = [type_mod_fn[i](v) if type_mod_fn[i] else v for i, v in enumerate(lt)]
                            row = []
                            for i, v in enumerate(lt):
                                if incl_col[i]:
                                    row.append(v)
                            add_line = True
                            if not _state.conf.empty_rows:
                                add_line = not all(c is None for c in row)
                            if add_line:
                                b.append(row)
                if len(b) > 0:
                    try:
                        curs.executemany(sql, b)
                    except ErrInfo:
                        raise
                    except Exception:
                        self.rollback()
                        raise ErrInfo(
                            type="db",
                            command_text=sql,
                            exception_msg=exception_desc(),
                            other_msg=f"Can't load data into table {sq_name} of {self.name()} from line {{{line}}}",
                        )
                    total_rows += len(b)
                    if use_progress and progress_ctx is not None and task_id is not None:
                        progress_ctx.update(task_id, completed=total_rows)
                    interval = _state.conf.import_progress_interval
                    if _state.exec_log and interval > 0 and total_rows % interval == 0:
                        _state.exec_log.log_status_info(
                            f"IMPORT into {sq_name}: {total_rows} rows imported so far.",
                        )
                if eof:
                    break
            return total_rows

        if use_progress and progress_ctx is not None:
            with progress_ctx:
                task_id = progress_ctx.add_task(sq_name, total=None)
                _import_loop()
        else:
            _import_loop()

        if _state.exec_log:
            _state.exec_log.log_status_info(
                f"IMPORT into {sq_name} complete: {total_rows} rows imported.",
            )

    def import_tabular_file(
        self,
        schema_name: str | None,
        table_name: str,
        csv_file_obj: Any,
        skipheader: bool,
    ) -> None:
        # Import a text (CSV) file containing tabular data to a table.  Columns must be compatible.
        if not self.table_exists(table_name, schema_name):
            raise ErrInfo(
                type="error",
                other_msg=(
                    f"Table doesn't exist for import of file to table {table_name}; "
                    "check that table name capitalization is consistent with the DBMS's case-folding behavior."
                ),
            )
        csv_cols = csv_file_obj.column_headers()
        table_cols = self.table_columns(table_name, schema_name)
        if _state.conf.import_common_cols_only:
            import_cols = [col for col in csv_cols if col.lower() in [tc.lower() for tc in table_cols]]
        else:
            src_extra_cols = [col for col in csv_cols if col.lower() not in [tc.lower() for tc in table_cols]]
            if len(src_extra_cols) > 0:
                raise ErrInfo(
                    type="error",
                    other_msg=(
                        f"The input file {csv_file_obj.csvfname} has the following columns "
                        f"that are not in table {table_name}: {', '.join(src_extra_cols)}."
                    ),
                )
            import_cols = csv_cols

        def get_ts() -> Any:
            if not get_ts.tablespec:
                get_ts.tablespec = csv_file_obj.data_table_def()
            return get_ts.tablespec

        get_ts.tablespec = None
        f = csv_file_obj.reader()
        next(f)
        self.populate_table(schema_name, table_name, f, import_cols, get_ts)

    def import_entire_file(
        self,
        schema_name: str | None,
        table_name: str,
        column_name: str,
        file_name: str,
    ) -> None:
        with open(file_name, "rb") as f:
            filedata = f.read()
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        sql = f"insert into {sq_name} ({column_name}) values ({self.paramsubs(1)});"
        self.cursor().execute(sql, (filedata,))


class DatabasePool:
    """Maintains a set of database connection objects, each with a name (alias),
    and with the current and initial databases identified."""

    def __init__(self) -> None:
        self.pool: dict[str, Database] = {}
        self.initial_db: str | None = None
        self.current_db: str | None = None
        self.do_rollback: bool = True

    def __repr__(self) -> str:
        return "DatabasePool()"

    def add(self, db_alias: str, db_obj: Database) -> None:
        db_alias = db_alias.lower()
        if db_alias == "initial" and len(self.pool) > 0:
            raise ErrInfo(
                type="error",
                other_msg="You may not use the name 'INITIAL' as a database alias.",
            )
        if len(self.pool) == 0:
            self.initial_db = db_alias
            self.current_db = db_alias
        if db_alias in self.pool:
            # Don't allow reassignment of a database that is used in any batch.
            if _state.status.batch.uses_db(self.pool[db_alias]):
                raise ErrInfo(
                    type="error",
                    other_msg="You may not reassign the alias of a database that is currently used in a batch.",
                )
            _state.exec_log.log_status_info(
                f"Reassigning database alias '{db_alias}' from {self.pool[db_alias].name()} to {db_obj.name()}.",
            )
            self.pool[db_alias].close()
        self.pool[db_alias] = db_obj

    def aliases(self) -> list[str]:
        # Return a list of the currently defined aliases
        return list(self.pool)

    def current(self) -> Database:
        # Return the current db object.
        return self.pool[self.current_db]

    def current_alias(self) -> str:
        # Return the alias of the current db object.
        return self.current_db

    def initial(self) -> Database:
        return self.pool[self.initial_db]

    def aliased_as(self, db_alias: str) -> Database:
        return self.pool[db_alias]

    def make_current(self, db_alias: str) -> None:
        # Change the current database in use.
        db_alias = db_alias.lower()
        if db_alias not in self.pool:
            raise ErrInfo(
                type="error",
                other_msg=f"Database alias '{db_alias}' is unrecognized; cannot use it.",
            )
        self.current_db = db_alias

    def disconnect(self, alias: str) -> None:
        if alias == self.current_db or (alias == "initial" and "initial" in self.pool):
            raise ErrInfo(
                type="error",
                other_msg=f"Database alias {alias} can't be removed or redefined while it is in use.",
            )
        if alias in self.pool:
            self.pool[alias].close()
            del self.pool[alias]

    def closeall(self) -> None:
        for alias, db in self.pool.items():
            nm = db.name()
            try:
                if self.do_rollback:
                    db.rollback()
                db.close()
            except Exception:
                if _state is not None and _state.exec_log is not None:
                    _state.exec_log.log_status_error(
                        f"Can't close database {nm} aliased as {alias}",
                    )
        self.__init__()
