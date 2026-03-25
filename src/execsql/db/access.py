from __future__ import annotations

"""
MS Access database adapter for execsql.

Implements :class:`AccessDatabase`, which connects to ``.mdb`` and
``.accdb`` files using DAO via ``win32com`` (primary) or ``pyodbc``
(fallback) on Windows.  Corresponds to ``-t a`` on the CLI.
"""

import datetime
import re
import time
from pathlib import Path
from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import clear_stored_password, get_password, password_from_keyring
import execsql.state as _state


class AccessDatabase(Database):
    # Regex for the 'create temporary view' SQL extension
    temp_rx = re.compile(
        r"^\s*create(?:\s+or\s+replace)?(\s+temp(?:orary)?)?\s+(?:(view|query))\s+(\w+) as\s+",
        re.I,
    )
    # Connection strings are a tuple, where the first part is the connection string and the second part is
    # a flag indicating whether this driver uses Jet 4.
    connection_strings = (
        ("DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;ExtendedAnsiSQL=1;", True),
        ("DRIVER={Microsoft Access Driver (*.mdb)};DBQ=%s;", False),
        ("Provider=Microsoft.ACE.OLEDB.15.0; Data Source=%s;", True),
        ("Provider=Microsoft.ACE.OLEDB.12.0; Data Source=%s;", True),
    )

    def __init__(
        self,
        Access_fn: str,
        need_passwd: bool = False,
        user_name: str | None = None,
        encoding: str | None = None,
        password: str | None = None,
    ) -> None:
        try:
            import win32com.client  # noqa: F401 – imported for side-effects / availability check
        except Exception:
            fatal_error("The win32com module is required.  See http://sourceforge.net/projects/pywin32/")
        try:
            import pyodbc  # noqa: F401
        except Exception:
            fatal_error("The pyodbc module is required.  See http://github.com/mkleehammer/pyodbc")
        from execsql.types import dbt_access

        self.type = dbt_access
        self.server_name = None
        self.db_name = Access_fn
        # The following assignment is tentative and may be changed when the connection is made.
        self.jet4 = len(Access_fn) > 6 and Access_fn.lower()[-6:] == ".accdb"
        self.user = user_name
        self.need_passwd = need_passwd
        self.password = password
        # Encoding is only applicable to Jet < 4.0: non-accdb databases.
        self.encoding = encoding or "windows-1252"
        self.encode_commands = True
        self.dao_conn = None
        self.conn = None  # ODBC connection
        self.paramstr = "?"
        self.dt_cast = dict(Database.dt_cast)
        self.dt_cast[datetime.date] = self.as_datetime
        self.dt_cast[datetime.datetime] = self.as_datetime
        self.dt_cast[int] = self.int_or_bool
        self.last_dao_time = 0.0
        self.temp_query_names: list[str] = []
        self.autocommit = True
        # Create the DAO connection
        self.open_dao()
        # Create the ODBC connection
        self.open_db()

    def __repr__(self) -> str:
        return f"AccessDatabase({self.db_name}, {self.encoding})"

    def open_db(self) -> None:
        # Open an ODBC connection.
        import pyodbc

        if self.conn is not None:
            self.conn.close()
            self.conn = None
        if self.need_passwd and self.user and self.password is None:
            self.password = get_password("MS-Access", self.db_name, self.user)

        def _try_odbc_drivers():
            db_name = str(Path(self.db_name).resolve())
            for cs, jet4flag in self.connection_strings:
                if self.need_passwd:
                    connstr = f"{cs % db_name} Uid={self.user}; Pwd={self.password};"
                else:
                    connstr = cs % db_name
                try:
                    self.conn = pyodbc.connect(connstr)
                except Exception:
                    _state.exec_log.log_status_info(f"Could not connect via ODBC using: {connstr}")
                else:
                    _state.exec_log.log_status_info(f"Connected via ODBC using: {connstr}")
                    self.jet4 = jet4flag
                    return True
            return False

        if not _try_odbc_drivers() and password_from_keyring():
            clear_stored_password("MS-Access", self.db_name, self.user)
            self.password = get_password(
                "MS-Access",
                self.db_name,
                self.user,
                skip_keyring=True,
                other_msg="(stored credential failed — enter current password)",
            )
            _try_odbc_drivers()

        if not self.conn:
            raise ErrInfo(
                type="error",
                other_msg=f"Can't open Access database {self.db_name} using ODBC",
            )

    def open_dao(self) -> None:
        import win32com.client

        if self.dao_conn is not None:
            self.dao_conn.Close()
            self.dao_conn = None
        if self.need_passwd and self.user and self.password is None:
            self.password = get_password("MS-Access", self.db_name, self.user)
        dao_engines = ("DAO.DBEngine.120", "DAO.DBEngine.36")

        def _try_dao_engines():
            for engine in dao_engines:
                try:
                    daoEngine = win32com.client.Dispatch(engine)
                    if self.need_passwd:
                        self.dao_conn = daoEngine.OpenDatabase(
                            self.db_name,
                            False,
                            False,
                            f"MS Access;UID={self.user};PWD={self.password};",
                        )
                    else:
                        self.dao_conn = daoEngine.OpenDatabase(self.db_name)
                except Exception:
                    _state.exec_log.log_status_info(f"Could not connect via DAO using: {engine}")
                else:
                    _state.exec_log.log_status_info(f"Connected via DAO using: {engine}")
                    return True
            return False

        if not _try_dao_engines() and password_from_keyring():
            clear_stored_password("MS-Access", self.db_name, self.user)
            self.password = get_password(
                "MS-Access",
                self.db_name,
                self.user,
                skip_keyring=True,
                other_msg="(stored credential failed — enter current password)",
            )
            _try_dao_engines()

        if not self.dao_conn:
            raise ErrInfo(
                type="error",
                other_msg=(
                    f"Can't open Access database {self.db_name} using any of the following "
                    f"DAO engines: {', '.join(dao_engines)}."
                ),
            )

    def exec_dao(self, querystring: str) -> None:
        # Execute a query using DAO.
        if self.dao_conn is None:
            self.open_dao()
        self.dao_conn.Execute(querystring)
        self.last_dao_time = time.time()

    def close(self) -> None:
        if self.dao_conn:
            for qn in self.temp_query_names:
                try:
                    self.dao_conn.QueryDefs.Delete(qn)
                    self.last_dao_time = time.time()
                except Exception:
                    pass  # Best-effort cleanup of temporary DAO query defs.
            self.dao_conn = None
        if self.conn:
            self.conn.close()
            self.conn = None

    def dao_flush_check(self) -> None:
        if time.time() - self.last_dao_time < 5.0:
            time.sleep(5 - (time.time() - self.last_dao_time))

    def execute(self, sqlcmd: Any, paramlist: list | None = None) -> None:
        # A shortcut to self.cursor().execute() that handles encoding and that
        # ensures that at least 5 seconds have passed since the last DAO command,
        # to allow Jet's read buffer to be flushed (see https://support.microsoft.com/en-us/kb/225048).
        # This also handles the 'CREATE TEMPORARY QUERY' extension to Access.
        # For Access, commands in a tuple (batch) are executed singly.
        def exec1(sql: str, paramlist: list | None) -> None:
            tqd = self.temp_rx.match(sql)
            if tqd:
                qn = tqd.group(3)
                qsql = sql[tqd.end() :]
                if self.dao_conn is None:
                    self.open_dao()
                try:
                    self.dao_conn.QueryDefs.Delete(qn)
                except Exception:
                    # If we can't delete it because it doesn't exist, that's fine.
                    pass
                self.dao_conn.CreateQueryDef(qn, qsql)
                self.last_dao_time = time.time()
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None
                if tqd.group(1) and tqd.group(1).strip().lower()[:4] == "temp" and qn not in self.temp_query_names:
                    self.temp_query_names.append(qn)
            else:
                self.dao_flush_check()
                curs = self.cursor()
                if self.jet4:
                    encoded_sql = str(sql)
                else:
                    encoded_sql = str(sql).encode(self.encoding)
                if paramlist is None:
                    curs.execute(encoded_sql)
                else:
                    curs.execute(encoded_sql, paramlist)
                _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)

        if type(sqlcmd) in (list, tuple):
            for sql in sqlcmd:
                exec1(sql, paramlist)
        else:
            exec1(sqlcmd, paramlist)

    def exec_cmd(self, querycommand: str) -> None:
        self.exec_dao(querycommand)

    def select_data(self, sql: str) -> tuple[list[str], list]:
        # Returns the results of the sql select statement.
        # The Access driver returns data as unicode, so no decoding is necessary.
        self.dao_flush_check()
        curs = self.cursor()
        curs.execute(sql)
        rows = curs.fetchall()
        return [d[0] for d in curs.description], rows

    def select_rowsource(self, sql: str) -> tuple[list[str], Any]:
        # Return 1) a list of column names, and 2) an iterable that yields rows.
        self.dao_flush_check()
        curs = self.cursor()
        curs.execute(sql)
        _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        return [d[0] for d in curs.description], iter(curs.fetchone, None)

    def select_rowdict(self, sql: str) -> tuple[list[str], Any]:
        # Return an iterable that yields dictionaries of row data.
        self.dao_flush_check()
        curs = self.cursor()
        curs.execute(sql)
        _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        headers = [d[0] for d in curs.description]

        def dict_row() -> dict | None:
            row = curs.fetchone()
            if row:
                if self.encoding:
                    r = [c.decode(self.encoding) if isinstance(c, bytes) else c for c in row]
                else:
                    r = row
                return dict(zip(headers, r))
            else:
                return None

        return headers, iter(dict_row, None)

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        self.dao_flush_check()
        curs = self.cursor()
        try:
            sql = f"select Name from MSysObjects where Name='{table_name}' And Type In (1,4,6);"
            curs.execute(sql)
        except ErrInfo:
            raise
        except Exception:
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failure on test for existence of Access table {table_name}",
            )
        rows = curs.fetchall()
        return len(rows) > 0

    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema_name: str | None = None,
    ) -> bool:
        self.dao_flush_check()
        curs = self.cursor()
        sql = f"select top 1 {column_name} from {table_name};"
        try:
            curs.execute(sql)
        except Exception:
            return False
        return True

    def table_columns(self, table_name: str, schema_name: str | None = None) -> list[str]:
        self.dao_flush_check()
        curs = self.cursor()
        curs.execute(f"select top 1 * from {table_name};")
        return [d[0] for d in curs.description]

    def view_exists(self, view_name: str, schema_name: str | None = None) -> bool:
        self.dao_flush_check()
        curs = self.cursor()
        try:
            sql = f"select Name from MSysObjects where Name='{view_name}' And Type = 5;"
            curs.execute(sql)
        except ErrInfo:
            raise
        except Exception:
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Test for existence of Access view/query {view_name}",
            )
        rows = curs.fetchall()
        return len(rows) > 0

    def schema_exists(self, schema_name: str) -> bool:
        return False

    def drop_table(self, tablename: str) -> None:
        self.dao_flush_check()
        tablename = self.type.quoted(tablename)
        self.execute(f"drop table {tablename};")

    def as_datetime(self, val: Any) -> datetime.datetime | None:
        from execsql.types import DT_Timestamp, DT_Date, DT_Time, DataTypeError

        if val is None or (isinstance(val, _state.stringtypes) and len(val) == 0):
            return None
        if isinstance(val, (datetime.date, datetime.datetime, datetime.time)):
            return val
        else:
            try:
                v = DT_Timestamp().from_data(val)
            except DataTypeError:
                try:
                    v = DT_Date().from_data(val)
                except DataTypeError:
                    # If this generates an exception, let it go up to get caught.
                    v = DT_Time().from_data(val)
                    n = datetime.datetime.now()
                    v = datetime.datetime(
                        n.year,
                        n.month,
                        n.day,
                        v.hour,
                        v.minute,
                        v.second,
                        v.microsecond,
                    )
            except Exception:
                raise
            return v

    def int_or_bool(self, val: Any) -> int | None:
        # Because Booleans are stored as integers in Access (at least, if execsql
        # creates the table), we have to recognize Boolean values as legitimate
        # integers.
        from execsql.types import DT_Boolean

        if val is None or (isinstance(val, _state.stringtypes) and len(val) == 0):
            return None
        try:
            v = int(val)
        except Exception:
            try:
                b = DT_Boolean().from_data(val)
            except Exception:
                # Re-trigger the exception on conversion to int
                v = int(val)
            if b is None:
                return None
            return 1 if b else 0
        return v

    def import_entire_file(
        self,
        schema_name: str | None,
        table_name: str,
        column_name: str,
        file_name: str,
    ) -> None:
        import pyodbc

        with open(file_name, "rb") as f:
            filedata = f.read()
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        sql = f"insert into {sq_name} ({column_name}) values ({self.paramsubs(1)});"
        self.cursor().execute(sql, (pyodbc.Binary(filedata),))
