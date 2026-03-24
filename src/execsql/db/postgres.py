from __future__ import annotations

"""
PostgreSQL database adapter for execsql.

Implements :class:`PostgresDatabase`, the most feature-complete adapter,
supporting schema-qualified tables, server-side ``COPY``, ``LISTEN``/
``NOTIFY``, and ``psycopg2``-level connection options.  Corresponds to
``-t p`` on the CLI.
"""

import re
from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import get_password
from execsql.utils.strings import encodings_match
import execsql.state as _state


DEFAULT_CONNECT_TIMEOUT = 30  # seconds


class PostgresDatabase(Database):
    def __init__(
        self,
        server_name: str,
        db_name: str,
        user_name: str | None,
        need_passwd: bool = False,
        port: int | None = 5432,
        new_db: bool = False,
        encoding: str | None = "UTF8",
        password: str | None = None,
        connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        try:
            import psycopg2  # noqa: F401
        except Exception:
            fatal_error(
                "The psycopg2 module is required to connect to PostgreSQL.   See http://initd.org/psycopg/",
            )
        from execsql.types import dbt_postgres

        self.type = dbt_postgres
        self.server_name = server_name
        self.db_name = db_name
        self.user = user_name
        self.need_passwd = need_passwd
        self.password = password
        self.port = port if port else 5432
        self.new_db = new_db
        self.encoding = encoding or "UTF8"
        self.encode_commands = False
        self.paramstr = "%s"
        self.connect_timeout = connect_timeout
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return (
            f"PostgresDatabase({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.new_db!r}, {self.encoding!r})"
        )

    def open_db(self) -> None:
        import psycopg2

        def db_conn(db: PostgresDatabase, db_name: str):
            try:
                if db.user and db.password:
                    return psycopg2.connect(
                        host=str(db.server_name),
                        database=str(db_name),
                        port=db.port,
                        user=db.user,
                        password=db.password,
                        connect_timeout=db.connect_timeout,
                    )
                else:
                    return psycopg2.connect(
                        host=str(db.server_name),
                        database=db_name,
                        port=db.port,
                        connect_timeout=db.connect_timeout,
                    )
            except Exception:
                msg = (
                    f"Failed to open PostgreSQL database {self.db_name} on {self.server_name}; "
                    "check server and database name, and validity of credentials"
                )
                raise ErrInfo(type="exception", exception_msg=exception_desc(), other_msg=msg)

        def create_db(db: PostgresDatabase) -> None:
            conn = db_conn(db, "postgres")
            conn.autocommit = True
            curs = conn.cursor()
            curs.execute(f"create database {db.db_name} encoding '{db.encoding}';")
            conn.close()

        if self.conn is None:
            try:
                if self.user and self.need_passwd and not self.password:
                    self.password = get_password(
                        "PostgreSQL",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                    )
                if self.new_db:
                    create_db(self)
                self.conn = db_conn(self, self.db_name)
            except SystemExit:
                # If the user canceled the password prompt.
                raise
            except ErrInfo:
                raise
            except Exception:
                msg = f"Failed to open PostgreSQL database {self.db_name} on {self.server_name}"
                raise ErrInfo(type="exception", exception_msg=exception_desc(), other_msg=msg)
            # (Re)set the encoding to match the database.
            self.encoding = self.conn.encoding

    def exec_cmd(self, querycommand: str) -> None:
        # The querycommand must be a stored function (/procedure)
        curs = self.cursor()
        cmd = f"select {querycommand}()"
        try:
            curs.execute(cmd)
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            self.rollback()
            raise

    def role_exists(self, rolename: str) -> bool:
        curs = self.cursor()
        curs.execute("select rolname from pg_roles where rolname = %s;", (rolename,))
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        if schema_name is not None:
            params: list = [table_name]
            schema_clause = ""
            if schema_name:
                schema_clause = " and table_schema=%s"
                params.append(schema_name)
            sql = f"select table_name from information_schema.tables where table_name = %s{schema_clause};"
        else:
            params = [table_name]
            sql = """select table_name from information_schema.tables where table_name = %s and
\t         table_schema in (select nspname from pg_namespace where oid = pg_my_temp_schema()
                     union
                     select trim(unnest(string_to_array(replace(setting, '"$user"', CURRENT_USER), ',')))
                     from pg_settings where name = 'search_path');"""
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

    def view_exists(self, view_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        if schema_name is not None:
            params: list = [view_name]
            schema_clause = ""
            if schema_name:
                schema_clause = " and table_schema=%s"
                params.append(schema_name)
            sql = f"select table_name from information_schema.views where table_name = %s{schema_clause};"
        else:
            params = [view_name]
            sql = """select table_name from information_schema.views where table_name = %s and
\t         table_schema in (select nspname from pg_namespace where oid = pg_my_temp_schema()
                     union
                     select trim(unnest(string_to_array(replace(setting, '"$user"', CURRENT_USER), ',')))
                     from pg_settings where name = 'search_path');"""
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

    def vacuum(self, argstring: str) -> None:
        self.commit()
        self.conn.set_session(autocommit=True)
        self.conn.cursor().execute(f"VACUUM {argstring};")
        self.conn.set_session(autocommit=False)

    def import_tabular_file(
        self,
        schema_name: str | None,
        table_name: str,
        csv_file_obj: Any,
        skipheader: bool,
    ) -> None:
        # Import a file to a table.  Columns must be compatible.
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        if not self.table_exists(table_name, schema_name):
            raise ErrInfo(
                type="error",
                other_msg=(
                    f"Table doesn't exist for import of file to table {sq_name}; "
                    "check that capitalization is consistent."
                ),
            )
        csv_file_obj.evaluate_line_format()
        # Create a comma-delimited list of column names in the input file.
        table_cols = self.table_columns(table_name, schema_name)
        data_table_cols = [d.lower() for d in table_cols]
        csv_hdrs = csv_file_obj.column_headers()
        csv_file_cols = [ch.lower().strip() for ch in csv_hdrs]
        if _state.conf.import_common_cols_only:
            import_cols = [col for col in csv_file_cols if col in data_table_cols]
        else:
            unmatched_cols = list(set(csv_file_cols) - set(data_table_cols))
            if len(unmatched_cols) > 0:
                raise ErrInfo(
                    type="error",
                    other_msg=(
                        f"The input file {csv_file_obj.csvfname} has the following columns "
                        f"that are not in table {sq_name}: {', '.join(unmatched_cols)}"
                    ),
                )
            import_cols = csv_file_cols
        import_cols = [self.type.quoted(col) for col in import_cols]
        csv_file_cols_q = [self.type.quoted(col) for col in csv_file_cols]
        input_col_list = ",".join(import_cols)
        # If encodings match, use copy_expert.
        # If encodings don't match, and the file encoding isn't recognized by CSV, read as CSV.
        enc_xlates = {
            "cp1252": "win1252",
            "windows1252": "win1252",
            "windows-1252": "win1252",
            "windows_1252": "win1252",
            "iso8859-1": "win1252",
            "iso-8859-1": "win1252",
            "iso8859_1": "win1252",
            "iso_8859_1": "win1252",
            "iso88591": "win1252",
            "utf-8": "utf8",
            "latin-1": "latin1",
            "latin_1": "latin1",
        }
        input_enc = csv_file_obj.encoding.lower()
        if input_enc in enc_xlates:
            input_enc = enc_xlates[input_enc]
        if (
            encodings_match(input_enc, self.encoding)
            and data_table_cols == csv_file_cols
            and _state.conf.empty_strings
            and _state.conf.empty_rows
            and not _state.conf.del_empty_cols
            and not _state.conf.create_col_hdrs
            and not _state.conf.trim_strings
            and not _state.conf.replace_newlines
        ):
            # Use Postgres' COPY FROM method via psycopg2's copy_expert() method.
            curs = self.cursor()
            rf = csv_file_obj.open("rt")
            if skipheader:
                next(rf)
            # Copy_from() requires a delimiter, but if there is none, feed it an
            # ASCII unit separator, which, if it had been used for its intended purpose,
            # should have been identified as the delimiter, so presumably it has not been used.
            delim = csv_file_obj.delimiter if csv_file_obj.delimiter else chr(31)
            copy_cmd = f"copy {sq_name} ({input_col_list}) from stdin with (format csv, null '', delimiter '{delim}'"
            if csv_file_obj.quotechar:
                copy_cmd = copy_cmd + f", quote '{csv_file_obj.quotechar}'"
            copy_cmd = copy_cmd + ")"
            _state.exec_log.log_status_info(
                f"IMPORTing {csv_file_obj.csvfname} using Postgres' fast file reading routine",
            )
            try:
                curs.copy_expert(copy_cmd, rf, _state.conf.import_buffer)
            except ErrInfo:
                raise
            except Exception:
                self.rollback()
                raise ErrInfo(
                    type="exception",
                    exception_msg=exception_desc(),
                    other_msg=f"Can't import from file to table {sq_name}",
                )
        else:
            data_indexes = [csv_file_cols_q.index(col) for col in import_cols]
            paramspec = ",".join(["%s"] * len(import_cols))
            sql_template = f"insert into {sq_name} ({input_col_list}) values ({paramspec});"
            f = csv_file_obj.reader()
            if skipheader:
                next(f)
            curs = self.cursor()
            eof = False
            total_rows = 0
            while True:
                b: list = []
                for _j in range(_state.conf.import_row_buffer):
                    try:
                        line = next(f)
                    except StopIteration:
                        eof = True
                    else:
                        if len(line) > len(csv_file_cols):
                            extra_err = True
                            if _state.conf.del_empty_cols:
                                any_non_empty = False
                                for cno in range(len(csv_file_cols), len(line)):
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
                                line = line[: len(csv_file_cols)]
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
                            # Pad short line with nulls
                            line.extend([None] * (len(import_cols) - len(line)))
                            linedata = [line[ix] for ix in data_indexes]
                            add_line = True
                            if not _state.conf.empty_rows:
                                add_line = not all(c is None for c in linedata)
                            if add_line:
                                b.append(linedata)
                if len(b) > 0:
                    try:
                        curs.executemany(sql_template, b)
                    except ErrInfo:
                        raise
                    except Exception:
                        self.rollback()
                        raise ErrInfo(
                            type="db",
                            command_text=sql_template,
                            exception_msg=exception_desc(),
                            other_msg=f"Can't load data into table {sq_name} of {self.name()} from line {{{line}}}",
                        )
                    total_rows += len(b)
                    interval = _state.conf.import_progress_interval
                    if _state.exec_log and interval > 0 and total_rows % interval == 0:
                        _state.exec_log.log_status_info(
                            f"IMPORT into {sq_name}: {total_rows} rows imported so far.",
                        )
                if eof:
                    break
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
        import psycopg2

        with open(file_name, "rb") as f:
            filedata = f.read()
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        sql = f"insert into {sq_name} ({column_name}) values ({self.paramsubs(1)});"
        self.cursor().execute(sql, (psycopg2.Binary(filedata),))
