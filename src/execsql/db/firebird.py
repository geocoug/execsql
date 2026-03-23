from __future__ import annotations

"""
Firebird database adapter for execsql.

Implements :class:`FirebirdDatabase`, which connects to Firebird databases
via the ``firebird-driver`` package.  Corresponds to ``-t f`` on the CLI.
"""

from typing import List, Optional

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import get_password
import execsql.state as _state


class FirebirdDatabase(Database):
    def __init__(
        self,
        server_name: str,
        db_name: str,
        user_name: Optional[str],
        need_passwd: bool = False,
        port: Optional[int] = 3050,
        encoding: Optional[str] = "latin1",
        password: Optional[str] = None,
    ) -> None:
        try:
            import fdb as firebird_lib  # noqa: F401
        except Exception:
            fatal_error(
                "The fdb module is required to connect to MySQL.   See https://pypi.python.org/pypi/fdb/",
            )
        from execsql.types import dbt_firebird

        self.type = dbt_firebird
        self.server_name = str(server_name)
        self.db_name = str(db_name)
        self.user = str(user_name)
        self.need_passwd = need_passwd
        self.password = password
        self.port = 3050 if not port else port
        self.encoding = encoding or "latin1"
        self.encode_commands = True
        self.paramstr = "?"
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return (
            f"FirebirdDatabase({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.encoding!r})"
        )

    def open_db(self) -> None:
        import fdb as firebird_lib

        def db_conn():
            if self.user and self.password:
                return firebird_lib.connect(
                    host=self.server_name,
                    database=self.db_name,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    charset=self.encoding,
                )
            else:
                return firebird_lib.connect(
                    host=self.server_name,
                    database=self.db_name,
                    port=self.port,
                    charset=self.encoding,
                )

        if self.conn is None:
            try:
                if self.user and self.need_passwd and not self.password:
                    self.password = get_password(
                        "Firebird",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                    )
                self.conn = db_conn()
            except SystemExit:
                # If the user canceled the password prompt.
                raise
            except ErrInfo:
                raise
            except Exception:
                msg = f"Failed to open Firebird database {self.db_name} on {self.server_name}"
                raise ErrInfo(type="exception", exception_msg=exception_desc(), other_msg=msg)

    def exec_cmd(self, querycommand: str) -> None:
        # The querycommand must be a stored function (/procedure)
        curs = self.cursor()
        cmd = f"execute procedure {querycommand};"
        try:
            curs.execute(cmd)
        except Exception:
            self.rollback()
            raise
        _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)

    def table_exists(self, table_name: str, schema_name: Optional[str] = None) -> bool:
        curs = self.cursor()
        sql = (
            f"SELECT RDB$RELATION_NAME FROM RDB$RELATIONS "
            f"WHERE RDB$SYSTEM_FLAG=0 AND RDB$VIEW_BLR IS NULL "
            f"AND RDB$RELATION_NAME='{table_name.upper()}';"
        )
        try:
            curs.execute(sql)
        except ErrInfo:
            raise
        except Exception:
            e = ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of Firebird table {table_name}",
            )
            try:
                self.rollback()
            except Exception:
                pass
            raise e
        rows = curs.fetchall()
        self.conn.commit()
        curs.close()
        return len(rows) > 0

    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema_name: Optional[str] = None,
    ) -> bool:
        curs = self.cursor()
        sql = f"select first 1 {column_name} from {table_name};"
        try:
            curs.execute(sql)
        except Exception:
            return False
        return True

    def table_columns(self, table_name: str, schema_name: Optional[str] = None) -> List[str]:
        curs = self.cursor()
        sql = f"select first 1 * from {table_name};"
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

    def view_exists(self, view_name: str, schema_name: Optional[str] = None) -> bool:
        curs = self.cursor()
        sql = f"select distinct rdb$view_name from rdb$view_relations where rdb$view_name = '{view_name}';"
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
                other_msg=f"Failed test for existence of Firebird view {view_name}",
            )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def schema_exists(self, schema_name: str) -> bool:
        return False

    def role_exists(self, rolename: str) -> bool:
        curs = self.cursor()
        curs.execute(
            f"SELECT DISTINCT USER FROM RDB$USER_PRIVILEGES WHERE USER = '{rolename}' union "
            f" SELECT DISTINCT RDB$ROLE_NAME FROM RDB$ROLES WHERE RDB$ROLE_NAME = '{rolename}';",
        )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def drop_table(self, tablename: str) -> None:
        # Firebird will thrown an error if there are foreign keys into the table.
        tablename = self.type.quoted(tablename)
        self.execute(f"DROP TABLE {tablename};")
        self.conn.commit()
