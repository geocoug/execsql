from __future__ import annotations

"""
Firebird database adapter for execsql.

Implements :class:`FirebirdDatabase`, which connects to Firebird databases
via the ``firebird-driver`` package.  Corresponds to ``-t f`` on the CLI.
"""


from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import clear_stored_password, get_password, password_from_keyring
import execsql.state as _state

__all__ = ["FirebirdDatabase"]


class FirebirdDatabase(Database):
    def __init__(
        self,
        server_name: str,
        db_name: str,
        user_name: str | None,
        need_passwd: bool = False,
        port: int | None = 3050,
        encoding: str | None = "latin1",
        password: str | None = None,
    ) -> None:
        try:
            import fdb as firebird_lib  # noqa: F401
        except Exception:
            fatal_error(
                "The fdb module is required to connect to Firebird.   See https://pypi.python.org/pypi/fdb/",
            )
        from execsql.types import dbt_firebird

        self.type = dbt_firebird
        self.server_name = str(server_name)
        self.db_name = str(db_name)
        self.user = str(user_name)
        self.need_passwd = need_passwd
        self.password = password
        self.port = port if port else 3050
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
                try:
                    self.conn = db_conn()
                except Exception:
                    if not password_from_keyring():
                        raise
                    clear_stored_password("Firebird", self.db_name, self.user, self.server_name)
                    self.password = get_password(
                        "Firebird",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                        skip_keyring=True,
                        other_msg="(stored credential failed — enter current password)",
                    )
                    self.conn = db_conn()
            except SystemExit:
                # If the user canceled the password prompt.
                raise
            except ErrInfo:
                raise
            except Exception as e:
                msg = f"Failed to open Firebird database {self.db_name} on {self.server_name}"
                raise ErrInfo(type="exception", exception_msg=exception_desc(), other_msg=msg) from e

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

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        sql = (
            "SELECT RDB$RELATION_NAME FROM RDB$RELATIONS "
            "WHERE RDB$SYSTEM_FLAG=0 AND RDB$VIEW_BLR IS NULL "
            "AND RDB$RELATION_NAME=?;"
        )
        try:
            curs.execute(sql, (table_name.upper(),))
        except ErrInfo:
            raise
        except Exception as e:
            try:
                self.rollback()
            except Exception:
                pass  # Rollback is best-effort after a failed query.
            raise ErrInfo(
                type="db",
                command_text=sql,
                exception_msg=exception_desc(),
                other_msg=f"Failed test for existence of Firebird table {table_name}",
            ) from e
        rows = curs.fetchall()
        self.conn.commit()
        curs.close()
        return len(rows) > 0

    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema_name: str | None = None,
    ) -> bool:
        curs = self.cursor()
        quoted_col = self.quote_identifier(column_name)
        quoted_tbl = self.quote_identifier(table_name)
        sql = f"select first 1 {quoted_col} from {quoted_tbl};"
        try:
            curs.execute(sql)
        except Exception:
            return False
        return True

    def table_columns(self, table_name: str, schema_name: str | None = None) -> list[str]:
        curs = self.cursor()
        quoted_tbl = self.quote_identifier(table_name)
        sql = f"select first 1 * from {quoted_tbl};"
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

    def view_exists(self, view_name: str, schema_name: str | None = None) -> bool:
        curs = self.cursor()
        sql = "select distinct rdb$view_name from rdb$view_relations where rdb$view_name = ?;"
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
                other_msg=f"Failed test for existence of Firebird view {view_name}",
            ) from e
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def schema_exists(self, schema_name: str) -> bool:
        return False

    def role_exists(self, rolename: str) -> bool:
        curs = self.cursor()
        curs.execute(
            "SELECT DISTINCT USER FROM RDB$USER_PRIVILEGES WHERE USER = ? union "
            " SELECT DISTINCT RDB$ROLE_NAME FROM RDB$ROLES WHERE RDB$ROLE_NAME = ?;",
            (rolename, rolename),
        )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0

    def drop_table(self, tablename: str) -> None:
        # Firebird will thrown an error if there are foreign keys into the table.
        tablename = self.type.quoted(tablename)
        self.execute(f"DROP TABLE {tablename};")
        self.conn.commit()
