from __future__ import annotations

"""
Oracle database adapter for execsql.

Implements :class:`OracleDatabase`, which connects to Oracle databases
via the ``oracledb`` driver (python-oracledb).  Corresponds to ``-t o``
on the CLI.
"""

from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import clear_stored_password, get_password, password_from_keyring
import execsql.state as _state


class OracleDatabase(Database):
    def __init__(
        self,
        server_name: str,
        db_name: str,
        user_name: str | None,
        need_passwd: bool = False,
        port: int | None = 1521,
        encoding: str | None = "UTF8",
        password: str | None = None,
    ) -> None:
        try:
            import cx_Oracle  # noqa: F401
        except Exception:
            fatal_error(
                "The cx-Oracle module is required to connect to Oracle.   See https://pypi.org/project/cx-Oracle/",
            )
        from execsql.types import dbt_oracle

        self.type = dbt_oracle
        self.server_name = server_name
        self.db_name = db_name
        self.user = user_name
        self.need_passwd = need_passwd
        self.password = password
        self.port = port if port else 1521
        self.encoding = encoding or "UTF8"
        self.encode_commands = False
        self.paramstr = ":1"
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return (
            f"OracleDatabase({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.encoding!r})"
        )

    def open_db(self) -> None:
        import cx_Oracle

        def db_conn(db: OracleDatabase, db_name: str):
            dsn = cx_Oracle.makedsn(db.server_name, db.port, service_name=db_name)
            if db.user and db.password:
                return cx_Oracle.connect(user=db.user, password=db.password, dsn=dsn)
            else:
                return cx_Oracle.connect(dsn=dsn)

        if self.conn is None:
            try:
                if self.user and self.need_passwd and not self.password:
                    self.password = get_password(
                        "Oracle",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                    )
                try:
                    self.conn = db_conn(self, self.db_name)
                except Exception:
                    if not password_from_keyring():
                        raise
                    clear_stored_password("Oracle", self.db_name, self.user, self.server_name)
                    self.password = get_password(
                        "Oracle",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                        skip_keyring=True,
                        other_msg="(stored credential failed — enter current password)",
                    )
                    self.conn = db_conn(self, self.db_name)
            except SystemExit:
                # If the user canceled the password prompt.
                raise
            except ErrInfo:
                raise
            except Exception as e:
                msg = f"Failed to open Oracle database {self.db_name} on {self.server_name}"
                raise ErrInfo(type="exception", exception_msg=exception_desc(), other_msg=msg) from e

    def execute(self, sql: Any, paramlist: list | None = None) -> None:
        # Strip any semicolon off the end and pass to the parent method.
        if sql[-1:] == ";":
            super().execute(sql[:-1], paramlist)
        else:
            super().execute(sql, paramlist)

    def select_data(self, sql: str) -> tuple[list[str], list]:
        if sql[-1:] == ";":
            return super().select_data(sql[:-1])
        else:
            return super().select_data(sql)

    def select_rowsource(self, sql: str) -> Any:
        if sql[-1:] == ";":
            return super().select_rowsource(sql[:-1])
        else:
            return super().select_rowsource(sql)

    def select_rowdict(self, sql: str) -> Any:
        if sql[-1:] == ";":
            return super().select_rowdict(sql[:-1])
        else:
            return super().select_rowdict(sql)

    def schema_exists(self, schema_name: str) -> bool:
        from execsql.exceptions import DatabaseNotImplementedError

        raise DatabaseNotImplementedError(self.name(), "schema_exists")

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        params = {"tname": table_name}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner = :owner"
            params["owner"] = schema_name
        sql = f"select table_name from sys.all_tables where table_name = :tname{owner_clause}"
        try:
            curs.execute(sql, params)
        except ErrInfo:
            raise
        except Exception as e:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of table {table_name} in {self.name()}",
            ) from e
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
        params = {"tname": table_name, "cname": column_name}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner = :owner"
            params["owner"] = schema_name
        sql = f"select column_name from all_tab_columns where table_name=:tname{owner_clause} and column_name=:cname"
        try:
            curs.execute(sql, params)
        except ErrInfo:
            raise
        except Exception as e:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of column {column_name} in table {table_name} of {self.name()}",
            ) from e
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def table_columns(self, table_name: str, schema_name: str | None = None) -> list[str]:
        curs = self.cursor()
        params = {"tname": table_name}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner=:owner"
            params["owner"] = schema_name
        sql = f"select column_name from all_tab_columns where table_name=:tname{owner_clause} order by column_id"
        try:
            curs.execute(sql, params)
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
        rows = curs.fetchall()
        curs.close()
        return [row[0] for row in rows]

    def view_exists(self, view_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        params = {"vname": view_name}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner = :owner"
            params["owner"] = schema_name
        sql = f"select view_name from sys.all_views where view_name = :vname{owner_clause}"
        try:
            curs.execute(sql, params)
        except ErrInfo:
            raise
        except Exception as e:
            self.rollback()
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of view {view_name} in {self.name()}",
            ) from e
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def role_exists(self, rolename: str) -> bool:
        curs = self.cursor()
        curs.execute(
            "select role from dba_roles where role = :rname union "
            " select username from all_users where username = :rname",
            {"rname": rolename},
        )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def drop_table(self, tablename: str) -> None:
        tablename = self.type.quoted(tablename)
        self.execute(f"drop table {tablename} cascade constraints")

    def paramsubs(self, paramcount: int) -> str:
        return ",".join(":" + str(d) for d in range(1, paramcount + 1))

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
