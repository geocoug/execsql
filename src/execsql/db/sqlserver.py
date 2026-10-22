from __future__ import annotations

"""
SQL Server database adapter for execsql.

Implements :class:`SqlServerDatabase`, which connects to Microsoft SQL
Server via ``pyodbc``.  Corresponds to ``-t s`` on the CLI.
"""

from execsql.db.base import Database
from execsql.db.target_types import ColumnKinds, kind_for_type_name
from execsql.db.odbc import connection_string, fresh_sessions, loggable
from execsql.exceptions import ErrInfo
from execsql.utils.errors import fatal_error, install_hint
from execsql.utils.auth import (
    begin_login,
    clear_stored_password,
    get_password,
    is_login_failure,
    password_from_keyring,
    remember_password,
)
import execsql.state as _state

__all__ = ["SqlServerDatabase"]


class SqlServerDatabase(Database):
    """Microsoft SQL Server adapter using pyodbc, trying drivers from newest to oldest."""

    def __init__(
        self,
        server_name: str,
        db_name: str,
        user_name: str | None,
        need_passwd: bool = False,
        port: int | None = None,
        encoding: str | None = "latin1",
        password: str | None = None,
        trust_server_certificate: bool | None = None,
    ) -> None:
        try:
            import pyodbc  # noqa: F401
        except Exception:
            fatal_error(f"The pyodbc module is required to connect to SQL Server. {install_hint('mssql')}")
        from execsql.types import dbt_sqlserver

        super().__init__(
            server_name=server_name,
            db_name=db_name,
            user_name=user_name,
            need_passwd=need_passwd,
            port=port if port else 1433,
        )
        # Only a port that was asked for goes into the connection string: a
        # named instance (``host\instance``) is found through SQL Server
        # Browser, which an explicit port bypasses.
        self.explicit_port = port or None
        # None: the [connect] trust_server_certificate setting, which also
        # covers connections a script opens with CONNECT.
        if trust_server_certificate is None:
            trust_server_certificate = bool(getattr(_state.conf, "trust_server_certificate", False))
        self.trust_server_certificate = trust_server_certificate
        self.type = dbt_sqlserver
        self.password = password
        self.encoding = encoding or "latin1"  # Default on installation of SQL Server
        self.paramstr = "?"
        self.open_db()
        self.password = None  # Clear cleartext password after successful connection

    def current_schema(self) -> str | None:
        return self._query_current_schema("select schema_name()")

    def __repr__(self) -> str:
        return (
            f"SqlServerDatabase({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.encoding!r})"
        )

    def quote_identifier(self, identifier: str) -> str:
        """SQL Server native identifier quoting uses square brackets.

        Override of :meth:`Database.quote_identifier` for B07a/F021: the
        base ANSI ``"…"`` form only works while ``QUOTED_IDENTIFIER`` is
        ``ON`` (the adapter sets this at open_db, but user SQL that
        toggles the session setting would silently break
        execsql-generated DDL). ``]`` inside an identifier is escaped to
        ``]]``.
        """
        return "[" + identifier.replace("]", "]]") + "]"

    def _server_attribute(self) -> str:
        """Return the ``SERVER`` value: ``host,port`` when a port was given."""
        if self.explicit_port and "," not in self.server_name:
            return f"{self.server_name},{self.explicit_port}"
        return str(self.server_name)

    def open_db(self) -> None:
        """Open a connection to the SQL Server database via pyodbc."""
        import pyodbc

        fresh_sessions(pyodbc)

        if self.conn is None:
            begin_login()
            if self.user and self.need_passwd and not self.password:
                self.password = get_password(
                    "SQL Server",
                    self.db_name,
                    self.user,
                    server_name=self.server_name,
                    port=self.port,
                )
            # Use pyodbc to connect.  Try different driver versions from newest to oldest.
            ssdrivers = (
                "ODBC Driver 18 for SQL Server",
                "ODBC Driver 17 for SQL Server",
                "ODBC Driver 13.1 for SQL Server",
                "ODBC Driver 13 for SQL Server",
                "ODBC Driver 11 for SQL Server",
                "SQL Server Native Client 11.0",
                "SQL Server Native Client 10.0",
                "SQL Native Client",
                "SQL Server",
            )

            errors: list[BaseException] = []

            def _try_drivers():
                attributes: list[tuple[str, object]] = [
                    ("SERVER", self._server_attribute()),
                    ("MARS_Connection", "Yes"),
                    ("DATABASE", self.db_name),
                ]
                if self.user:
                    attributes.append(("Uid", self.user))
                    if self.password:
                        attributes.append(("Pwd", self.password))
                else:
                    attributes.append(("Trusted_Connection", "yes"))
                if self.trust_server_certificate:
                    # Driver 18 encrypts and verifies the server's certificate
                    # by default; this accepts a self-signed one.
                    attributes.append(("TrustServerCertificate", "yes"))
                for drv in ssdrivers:
                    connstr = connection_string(drv, attributes)
                    try:
                        # 30 s connect timeout matches the Postgres adapter
                        # default; pyodbc treats `timeout` as the login-and-
                        # query timeout on the connection.
                        self.conn = pyodbc.connect(connstr, timeout=30)
                    except Exception as e:
                        errors.append(e)
                        if _state.exec_log is not None:
                            _state.exec_log.log_status_info(
                                f"Could not connect using: {loggable(drv, attributes)}",
                            )
                    else:
                        if _state.exec_log is not None:
                            _state.exec_log.log_status_info(
                                f"Connected using: {loggable(drv, attributes)}",
                            )
                        return True
                return False

            # Only a rejected password means the stored one is stale; a
            # timeout or a missing database leaves it alone.
            if not _try_drivers() and password_from_keyring() and any(is_login_failure(e) for e in errors):
                clear_stored_password("SQL Server", self.db_name, self.user, self.server_name, port=self.port)
                self.password = get_password(
                    "SQL Server",
                    self.db_name,
                    self.user,
                    server_name=self.server_name,
                    port=self.port,
                    skip_keyring=True,
                    other_msg="(stored credential failed — enter current password)",
                )
                _try_drivers()
            if self.conn:
                remember_password("SQL Server", self.db_name, self.user, self.server_name, port=self.port)

            if not self.conn:
                raise ErrInfo(
                    type="error",
                    other_msg=f"Can't open SQL Server database {self.db_name} on {self.server_name}",
                )
            # B11/F022: ensure the session-setup cursor is closed even
            # if one of the SET statements raises. The previous code
            # left a raw cursor open across pyodbc's connection,
            # leaking a server-side handle for the connection's life.
            curs = self.conn.cursor()
            try:
                curs.execute("SET IMPLICIT_TRANSACTIONS OFF;")
                curs.execute("SET ANSI_NULLS ON;")
                curs.execute("SET ANSI_PADDING ON;")
                curs.execute("SET ANSI_WARNINGS ON;")
                curs.execute("SET QUOTED_IDENTIFIER ON;")
                self.conn.commit()
            finally:
                curs.close()

    def exec_cmd(self, querycommand: str) -> None:
        """Execute a stored procedure by name."""
        # The querycommand must be a stored procedure
        with self._cursor() as curs:
            cmd = f"execute {self.quote_identifier(querycommand)};"
            try:
                curs.execute(cmd)
                _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
            except Exception:
                self.rollback_after_error()
                raise

    def schema_exists(self, schema_name: str) -> bool:
        """Return True if the named schema exists in the SQL Server database."""
        with self._cursor() as curs:
            curs.execute("select * from sys.schemas where name = ?;", (schema_name,))
            rows = curs.fetchall()
        return len(rows) > 0

    def role_exists(self, rolename: str) -> bool:
        """Return True if the named role or principal exists in the SQL Server database."""
        with self._cursor() as curs:
            curs.execute(
                "select name from sys.database_principals where type in ('R', 'S') and name = ?;",
                (rolename,),
            )
            rows = curs.fetchall()
        return len(rows) > 0

    def column_kinds(self, sq_name: str) -> ColumnKinds:
        """The execsql type of each column of *sq_name*, from ``sys.columns``.

        pyodbc describes ``datetimeoffset`` and ``varbinary`` alike, so the
        catalog is read instead.  A table it does not find through
        ``object_id`` (a ``#temp`` table, which lives in tempdb) falls back
        to the driver's description.
        """
        _description, rows = self._column_type_query(
            sq_name,
            "select c.name, type_name(c.system_type_id), c.precision, c.scale from sys.columns c "
            "where c.object_id = object_id(?) order by c.column_id;",
            [sq_name],
        )
        if not rows:
            return super().column_kinds(sq_name)
        return {
            name.lower(): kind_for_type_name(
                f"{type_name}({precision},{scale})" if type_name in ("decimal", "numeric") else type_name,
            )
            for name, type_name, precision, scale in rows
        }

    def drop_table(self, tablename: str) -> None:
        """Drop *tablename*, schema-qualified and quoted by the caller."""
        # SQL Server and Firebird will throw an error if there are foreign keys to the table.
        self.execute(f"drop table {tablename};")

    def import_entire_file(
        self,
        schema_name: str | None,
        table_name: str,
        column_name: str,
        file_name: str,
    ) -> None:
        """Import an entire binary file into a single column of a table."""
        import pyodbc

        with open(file_name, "rb") as f:
            filedata = f.read()
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        quoted_col = self.quote_identifier(column_name)
        sql = f"insert into {sq_name} ({quoted_col}) values ({self.paramsubs(1)});"
        with self._cursor() as curs:
            curs.execute(sql, (pyodbc.Binary(filedata),))
