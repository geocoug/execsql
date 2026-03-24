from __future__ import annotations

"""
MySQL / MariaDB database adapter for execsql.

Implements :class:`MySQLDatabase`, which connects to MySQL and MariaDB
servers via ``pymysql``.  Corresponds to ``-t m`` on the CLI.
"""

import re
from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import get_password
import execsql.state as _state


class MySQLDatabase(Database):
    def __init__(
        self,
        server_name: str,
        db_name: str,
        user_name: str | None,
        need_passwd: bool = False,
        port: int | None = 3306,
        encoding: str | None = "latin1",
        password: str | None = None,
    ) -> None:
        try:
            import pymysql as mysql_lib  # noqa: F401
        except Exception:
            fatal_error(
                "The pymysql module is required to connect to MySQL.   See https://pypi.python.org/pypi/PyMySQL",
            )
        from execsql.types import dbt_mysql

        self.type = dbt_mysql
        self.server_name = str(server_name)
        self.db_name = str(db_name)
        self.user = str(user_name)
        self.need_passwd = need_passwd
        self.password = password
        self.port = port if port else 3306
        self.encoding = encoding or "latin1"
        self.encode_commands = True
        self.paramstr = "%s"
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return (
            f"MySQLDatabase({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.encoding!r})"
        )

    def open_db(self) -> None:
        import pymysql as mysql_lib

        def db_conn():
            if self.user and self.password:
                return mysql_lib.connect(
                    host=self.server_name,
                    database=self.db_name,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    charset=self.encoding,
                    local_infile=True,
                )
            else:
                return mysql_lib.connect(
                    host=self.server_name,
                    database=self.db_name,
                    port=self.port,
                    charset=self.encoding,
                    local_infile=True,
                )

        if self.conn is None:
            try:
                if self.user and self.need_passwd and not self.password:
                    self.password = get_password(
                        "MySQL",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                    )
                self.conn = db_conn()
                self.execute("set session sql_mode='ANSI';")
            except SystemExit:
                # If the user canceled the password prompt.
                raise
            except ErrInfo:
                raise
            except Exception:
                msg = f"Failed to open MySQL database {self.db_name} on {self.server_name}"
                raise ErrInfo(type="exception", exception_msg=exception_desc(), other_msg=msg)

    def exec_cmd(self, querycommand: str) -> None:
        # The querycommand must be a stored function (/procedure)
        curs = self.cursor()
        cmd = f"call {querycommand}();"
        try:
            curs.execute(cmd)
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            self.rollback()
            raise

    def schema_exists(self, schema_name: str) -> bool:
        return False

    def role_exists(self, rolename: str) -> bool:
        curs = self.cursor()
        curs.execute(
            f"select distinct user as role from mysql.user where user = '{rolename}'"
            f" union select distinct role_name as role from information_schema.applicable_roles"
            f" where role_name = '{rolename}'",
        )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

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
        csv_file_cols = csv_file_obj.column_headers()
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
        input_col_list = ",".join(import_cols)
        if (
            data_table_cols == csv_file_cols
            and _state.conf.empty_strings
            and _state.conf.empty_rows
            and not _state.conf.del_empty_cols
            and not _state.conf.create_col_hdrs
            and not _state.conf.trim_strings
            and not _state.conf.replace_newlines
        ):
            import_sql = f"load data local infile '{csv_file_obj.csvfname}' into table {sq_name}"
            if csv_file_obj.encoding:
                import_sql = f"{import_sql} character set {csv_file_obj.encoding}"
            if csv_file_obj.delimiter or csv_file_obj.quotechar:
                import_sql = import_sql + " columns"
                if csv_file_obj.delimiter:
                    import_sql = f"{import_sql} terminated by '{csv_file_obj.delimiter}'"
                if csv_file_obj.quotechar:
                    import_sql = f"{import_sql} optionally enclosed by '{csv_file_obj.quotechar}'"
            import_sql = f"{import_sql} ignore {1 + csv_file_obj.junk_header_lines} lines"
            import_sql = f"{import_sql} ({input_col_list});"
            _state.exec_log.log_status_info(
                f"IMPORTing {csv_file_obj.csvfname} using the DBMS' fast file reading routine",
            )
            self.execute(import_sql)
        else:
            data_indexes = [csv_file_cols.index(col) for col in import_cols]
            paramspec = ",".join(["%s"] * len(import_cols))
            sql_template = f"insert into {sq_name} ({input_col_list}) values ({paramspec});"
            f = csv_file_obj.reader()
            if skipheader:
                next(f)
            curs = self.cursor()
            eof = False
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
                            other_msg=f"Import from file into table {sq_name}, line {{{line}}}",
                        )
                if eof:
                    break
