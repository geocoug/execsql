from __future__ import annotations

"""
Oracle database adapter for execsql.

Implements :class:`OracleDatabase`, which connects to Oracle databases
via the ``oracledb`` driver (python-oracledb).  Corresponds to ``-t o``
on the CLI.
"""

import re
from typing import Any

from execsql.db.base import Database
from execsql.db.tiers import SupportTier
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.auth import (
    clear_stored_password,
    get_password,
    is_login_failure,
    password_from_keyring,
    remember_password,
)
import execsql.state as _state

__all__ = ["OracleDatabase"]


def _oracle_driver() -> Any:
    """The Oracle driver module: python-oracledb, or else the legacy cx_Oracle.

    ``execsql2[oracle]`` installs oracledb.  cx_Oracle, the driver it replaced
    (same ``makedsn`` / ``connect`` calls), is used only when it is the one
    installed.  ``None`` if neither is.
    """
    try:
        import oracledb

        return oracledb
    except ImportError:
        pass
    try:
        import cx_Oracle

        return cx_Oracle
    except ImportError:
        return None


class OracleDatabase(Database):
    """Oracle adapter using the python-oracledb driver."""

    #: Oracle commits every DDL statement at once, together with everything
    #: before it, including CREATE GLOBAL TEMPORARY TABLE.
    implicit_commit_rx = re.compile(
        r"(?:CREATE|ALTER|DROP)\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+TEMPORARY\s+|UNIQUE\s+|BITMAP\s+)?\w+"
        r"|TRUNCATE\s+\w+|RENAME\b|GRANT\b|REVOKE\b|COMMENT\s+ON\b|(?:NO)?AUDIT\b|ANALYZE\b|PURGE\b|FLASHBACK\b",
        re.I,
    )

    #: No Oracle server runs in CI; this adapter has no tests.
    support_tier = SupportTier.BEST_EFFORT
    support_tier_name = "Oracle"

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
        if _oracle_driver() is None:
            fatal_error(
                'The oracledb module is required to connect to Oracle. Install it with: pip install "execsql2[oracle]"',
            )
        from execsql.types import dbt_oracle

        super().__init__(
            server_name=server_name,
            db_name=db_name,
            user_name=user_name,
            need_passwd=need_passwd,
            port=port if port else 1521,
        )
        self.type = dbt_oracle
        self.password = password
        self.encoding = encoding or "UTF8"
        self.encode_commands = False
        self.paramstr = ":1"
        self.open_db()
        self.password = None  # Clear cleartext password after successful connection

    def __repr__(self) -> str:
        return (
            f"OracleDatabase({self.server_name!r}, {self.db_name!r}, {self.user!r}, "
            f"{self.need_passwd!r}, {self.port!r}, {self.encoding!r})"
        )

    def open_db(self) -> None:
        """Open a connection to the Oracle database."""
        driver = _oracle_driver()

        def db_conn(db: OracleDatabase, db_name: str):
            dsn = driver.makedsn(db.server_name, db.port, service_name=db_name)
            if db.user and db.password:
                return driver.connect(user=db.user, password=db.password, dsn=dsn)
            else:
                return driver.connect(dsn=dsn)

        if self.conn is None:
            try:
                if self.user and self.need_passwd and not self.password:
                    self.password = get_password(
                        "Oracle",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                        port=self.port,
                    )
                try:
                    self.conn = db_conn(self, self.db_name)
                except Exception as e:
                    # Only a rejected password means the stored one is stale;
                    # a timeout or a missing database leaves it alone.
                    if not (password_from_keyring() and is_login_failure(e)):
                        raise
                    clear_stored_password("Oracle", self.db_name, self.user, self.server_name, port=self.port)
                    self.password = get_password(
                        "Oracle",
                        self.db_name,
                        self.user,
                        server_name=self.server_name,
                        port=self.port,
                        skip_keyring=True,
                        other_msg="(stored credential failed — enter current password)",
                    )
                    self.conn = db_conn(self, self.db_name)
                remember_password("Oracle", self.db_name, self.user, self.server_name, port=self.port)
            except SystemExit:
                # If the user canceled the password prompt.
                raise
            except ErrInfo:
                raise
            except Exception as e:
                msg = f"Failed to open Oracle database {self.db_name} on {self.server_name}"
                raise ErrInfo(type="exception", exception_msg=exception_desc(), other_msg=msg) from e

    def execute(self, sql: Any, paramlist: list | None = None, *, fetch: bool = False) -> tuple[list[str], list] | None:
        """Execute a SQL command, stripping any trailing semicolon for Oracle."""
        # Strip any semicolon off the end and pass to the parent method.
        if sql[-1:] == ";":
            return super().execute(sql[:-1], paramlist, fetch=fetch)
        return super().execute(sql, paramlist, fetch=fetch)

    def select_data(self, sql: str) -> tuple[list[str], list]:
        """Return column names and all rows from a SELECT statement."""
        if sql[-1:] == ";":
            return super().select_data(sql[:-1])
        else:
            return super().select_data(sql)

    def select_rowsource(self, sql: str) -> Any:
        """Return column names and an iterable that yields rows one at a time."""
        if sql[-1:] == ";":
            return super().select_rowsource(sql[:-1])
        else:
            return super().select_rowsource(sql)

    def select_rowdict(self, sql: str) -> Any:
        """Return column names and an iterable that yields rows as dictionaries."""
        if sql[-1:] == ";":
            return super().select_rowdict(sql[:-1])
        else:
            return super().select_rowdict(sql)

    def schema_exists(self, schema_name: str) -> bool:
        """Raise DatabaseNotImplementedError; schema_exists is not supported for Oracle."""
        from execsql.exceptions import DatabaseNotImplementedError

        raise DatabaseNotImplementedError(self.name(), "schema_exists")

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        """Return True if the named table exists in the Oracle database."""
        # Oracle folds unquoted identifiers to uppercase; normalise so a lookup
        # of "mytable" finds the catalog entry for MYTABLE.
        params = {"tname": table_name.upper()}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner = :owner"
            params["owner"] = schema_name.upper()
        sql = f"select table_name from sys.all_tables where table_name = :tname{owner_clause}"
        with self._cursor() as curs:
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
        return len(rows) > 0

    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema_name: str | None = None,
    ) -> bool:
        """Return True if the named column exists in the given Oracle table."""
        # Oracle folds unquoted identifiers to uppercase.
        params = {"tname": table_name.upper(), "cname": column_name.upper()}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner = :owner"
            params["owner"] = schema_name.upper()
        sql = f"select column_name from all_tab_columns where table_name=:tname{owner_clause} and column_name=:cname"
        with self._cursor() as curs:
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
        return len(rows) > 0

    def table_columns(self, table_name: str, schema_name: str | None = None) -> list[str]:
        """Return a list of column names for the given Oracle table."""
        # Oracle folds unquoted identifiers to uppercase.
        params = {"tname": table_name.upper()}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner=:owner"
            params["owner"] = schema_name.upper()
        sql = f"select column_name from all_tab_columns where table_name=:tname{owner_clause} order by column_id"
        with self._cursor() as curs:
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
        return [row[0] for row in rows]

    def view_exists(self, view_name: str, schema_name: str | None = None) -> bool:
        """Return True if the named view exists in the Oracle database."""
        # Oracle folds unquoted identifiers to uppercase.
        params = {"vname": view_name.upper()}
        owner_clause = ""
        if schema_name:
            owner_clause = " and owner = :owner"
            params["owner"] = schema_name.upper()
        sql = f"select view_name from sys.all_views where view_name = :vname{owner_clause}"
        with self._cursor() as curs:
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
        return len(rows) > 0

    def role_exists(self, rolename: str) -> bool:
        """Return True if the named role or user exists in the Oracle database.

        ``dba_roles`` is restricted to DBA accounts and would raise
        ``ORA-00942: table or view does not exist`` for non-DBA users; we
        try it first and fall back to ``session_roles`` (always readable
        for the current session) if the catalog isn't accessible.
        """
        # Oracle folds unquoted identifiers to uppercase in the catalog.
        params = {"rname": rolename.upper()}
        with self._cursor() as curs:
            try:
                curs.execute(
                    "select role from dba_roles where role = :rname union "
                    " select username from all_users where username = :rname",
                    params,
                )
            except Exception:
                # Non-DBA fallback: enumerate session roles + users we can see.
                self.rollback()
                curs.execute(
                    "select role from session_roles where role = :rname union "
                    " select username from all_users where username = :rname",
                    params,
                )
            rows = curs.fetchall()
        return len(rows) > 0

    def drop_table(self, tablename: str) -> None:
        """Drop *tablename* (schema-qualified and quoted by the caller) with cascade constraints."""
        self.execute(f"drop table {tablename} cascade constraints")

    def paramsubs(self, paramcount: int) -> str:
        """Return Oracle-style positional parameter placeholders (:1, :2, ...)."""
        return ",".join(":" + str(d) for d in range(1, paramcount + 1))

    def exec_cmd(self, querycommand: str) -> None:
        """Execute a stored function by name."""
        # The querycommand must be a stored function (/procedure)
        with self._cursor() as curs:
            cmd = f"select {self.quote_identifier(querycommand)}()"
            try:
                curs.execute(cmd)
                _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
            except Exception:
                self.rollback()
                raise
