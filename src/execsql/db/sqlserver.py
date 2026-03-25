from __future__ import annotations

"""
SQL Server database adapter for execsql.

Implements :class:`SqlServerDatabase`, which connects to Microsoft SQL
Server via ``pyodbc``.  Corresponds to ``-t s`` on the CLI.
"""


from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import fatal_error
from execsql.utils.auth import clear_stored_password, get_password, password_from_keyring
import execsql.state as _state


class SqlServerDatabase(Database):
    def __init__(
        self,
        server_name: str,
        db_name: str,
        user_name: str | None,
        need_passwd: bool = False,
        port: int | None = 1433,
        encoding: str | None = "latin1",
        password: str | None = None,
    ) -> None:
        try:
            import pyodbc  # noqa: F401
        except Exception:
            fatal_error("The pyodbc module is required.  See http://github.com/mkleehammer/pyodbc")
        from execsql.types import dbt_sqlserver

        self.type = dbt_sqlserver
        self.server_name = server_name
        self.db_name = db_name
        self.user = user_name
        self.need_passwd = need_passwd
        self.password = password
        self.port = port if port else 1433
        self.encoding = encoding or "latin1"  # Default on installation of SQL Server
        self.encode_commands = True
        self.paramstr = "?"
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return (
            f"SqlServerDatabase({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.encoding!r})"
        )

    def open_db(self) -> None:
        import pyodbc

        if self.conn is None:
            if self.user and self.need_passwd and not self.password:
                self.password = get_password(
                    "SQL Server",
                    self.db_name,
                    self.user,
                    server_name=self.server_name,
                )
            # Use pyodbc to connect.  Try different driver versions from newest to oldest.
            ssdrivers = (
                "ODBC Driver 17 for SQL Server",
                "ODBC Driver 13.1 for SQL Server",
                "ODBC Driver 13 for SQL Server",
                "ODBC Driver 11 for SQL Server",
                "SQL Server Native Client 11.0",
                "SQL Server Native Client 10.0",
                "SQL Native Client",
                "SQL Server",
            )

            def _try_drivers():
                for drv in ssdrivers:
                    if self.user:
                        if self.password:
                            connstr = (
                                f"DRIVER={{{drv}}};SERVER={self.server_name};MARS_Connection=Yes; "
                                f"DATABASE={self.db_name};Uid={self.user};Pwd={self.password}"
                            )
                        else:
                            connstr = (
                                f"DRIVER={{{drv}}};SERVER={self.server_name};MARS_Connection=Yes; "
                                f"DATABASE={self.db_name};Uid={self.user}"
                            )
                    else:
                        connstr = (
                            f"DRIVER={{{drv}}};SERVER={self.server_name};MARS_Connection=Yes; "
                            f"DATABASE={self.db_name};Trusted_Connection=yes"
                        )
                    try:
                        self.conn = pyodbc.connect(connstr)
                    except Exception:
                        _state.exec_log.log_status_info(f"Could not connect using: {connstr}")
                    else:
                        _state.exec_log.log_status_info(f"Connected using: {connstr}")
                        return True
                return False

            if not _try_drivers() and password_from_keyring():
                # Stored credential is stale — clear it and re-prompt.
                clear_stored_password("SQL Server", self.db_name, self.user, self.server_name)
                self.password = get_password(
                    "SQL Server",
                    self.db_name,
                    self.user,
                    server_name=self.server_name,
                    skip_keyring=True,
                    other_msg="(stored credential failed — enter current password)",
                )
                _try_drivers()

            if not self.conn:
                raise ErrInfo(
                    type="error",
                    other_msg=f"Can't open SQL Server database {self.db_name} on {self.server_name}",
                )
            curs = self.conn.cursor()
            curs.execute("SET IMPLICIT_TRANSACTIONS OFF;")
            curs.execute("SET ANSI_NULLS ON;")
            curs.execute("SET ANSI_PADDING ON;")
            curs.execute("SET ANSI_WARNINGS ON;")
            curs.execute("SET QUOTED_IDENTIFIER ON;")
            self.conn.commit()

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

    def schema_exists(self, schema_name: str) -> bool:
        curs = self.cursor()
        curs.execute(f"select * from sys.schemas where name = '{schema_name}';")
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def role_exists(self, rolename: str) -> bool:
        curs = self.cursor()
        curs.execute(
            f"select name from sys.database_principals where type in ('R', 'S') and name = '{rolename}';",
        )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def drop_table(self, tablename: str) -> None:
        # SQL Server and Firebird will throw an error if there are foreign keys to the table.
        tablename = self.type.quoted(tablename)
        self.execute(f"drop table {tablename};")

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
