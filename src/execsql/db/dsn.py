from __future__ import annotations

"""
Generic ODBC DSN database adapter for execsql.

Implements :class:`DsnDatabase`, which connects to any data source
registered as an ODBC DSN via ``pyodbc``.  Corresponds to ``-t d`` on
the CLI.
"""

import io
from typing import Optional

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import get_password
import execsql.state as _state


class DsnDatabase(Database):
    # There's no telling what is actually connected to a DSN, so this uses
    # generic Database methods almost exclusively.  Only 'exec_cmd()' is
    # overridden, and that uses the method for SQL Server because the DAO
    # methods used for Access may not be appropriate for whatever is actually
    # connected to the DSN.

    def __init__(
        self,
        dsn_name: str,
        user_name: Optional[str],
        need_passwd: bool = False,
        encoding: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        try:
            import pyodbc  # noqa: F401
        except Exception:
            fatal_error("The pyodbc module is required.  See http://github.com/mkleehammer/pyodbc")
        from execsql.types import dbt_dsn

        self.type = dbt_dsn
        self.server_name = None
        self.db_name = dsn_name
        self.user = user_name
        self.need_passwd = need_passwd
        self.password = password
        self.port = None
        self.encoding = encoding
        self.encode_commands = True
        self.paramstr = "?"
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return f"DsnDatabase({self.db_name!r}, {self.user!r}, {self.need_passwd!r}, {self.port!r}, {self.encoding!r})"

    def open_db(self) -> None:
        # Open an ODBC connection using a DSN.
        import pyodbc

        if self.conn is not None:
            self.conn.close()
            self.conn = None
        if self.need_passwd and self.user and self.password is None:
            self.password = get_password("DSN", self.db_name, self.user)
        cs = "DSN=%s;"
        try:
            if self.need_passwd:
                self.conn = pyodbc.connect(
                    f"{cs % self.db_name} Uid={self.user}; Pwd={self.password};",
                )
            else:
                self.conn = pyodbc.connect(cs % self.db_name)
        except Exception:
            excdesc = exception_desc()
            if "Optional feature not implemented" in excdesc:
                try:
                    if self.need_passwd:
                        self.conn = pyodbc.connect(
                            f"{cs % self.db_name} Uid={self.user}; Pwd={self.password};",
                            autocommit=True,
                        )
                    else:
                        self.conn = pyodbc.connect(cs % self.db_name, autocommit=True)
                except Exception:
                    raise ErrInfo(
                        type="exception",
                        exception_msg=exception_desc(),
                        other_msg=f"Can't open DSN database {self.db_name} using ODBC",
                    )
            else:
                raise ErrInfo(
                    type="exception",
                    exception_msg=excdesc,
                    other_msg=f"Can't open DSN database {self.db_name} using ODBC",
                )

    def exec_cmd(self, querycommand: str) -> None:
        # The querycommand must be a stored procedure
        curs = self.cursor()
        cmd = f"execute {querycommand};"
        try:
            curs.execute(cmd.encode(self.encoding))
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            self.rollback()
            raise

    def import_entire_file(
        self,
        schema_name: Optional[str],
        table_name: str,
        column_name: str,
        file_name: str,
    ) -> None:
        import pyodbc

        with io.open(file_name, "rb") as f:
            filedata = f.read()
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        sql = f"insert into {sq_name} ({column_name}) values ({self.paramsubs(1)});"
        self.cursor().execute(sql, (pyodbc.Binary(filedata),))
