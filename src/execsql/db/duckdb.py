from __future__ import annotations

"""
DuckDB database adapter for execsql.

Implements :class:`DuckDBDatabase`, which connects to DuckDB in-process
analytics databases via the ``duckdb`` package.  Corresponds to ``-t k``
on the CLI.
"""

import re
from pathlib import Path
from typing import Any

from execsql.db.base import Database, statement_start
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
import execsql.state as _state

__all__ = ["DuckDBDatabase"]

# Statements that return rows; any other statement DuckDB answers with a
# one-column "Count" result (rows inserted, updated or deleted).
_QUERY_RX = re.compile(r"(?:SELECT|WITH|VALUES|FROM|TABLE|SHOW|DESCRIBE|SUMMARIZE|EXPLAIN|PRAGMA|CALL)\b|\(", re.I)

# A statement that opens a transaction, or one that ends it.
_TRANSACTION_RX = re.compile(r"(?P<begin>BEGIN|START\s+TRANSACTION)\b|(?P<end>COMMIT|END|ROLLBACK|ABORT)\b", re.I)


class _SharedCursor:
    """The connection, used as a cursor so a statement joins its open transaction.

    A DuckDB cursor is a separate connection with a transaction of its own,
    and closing it rolls that transaction back.  ``close()`` therefore leaves
    the connection open.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def close(self) -> None:
        pass


class DuckDBDatabase(Database):
    """DuckDB in-process analytics adapter using the duckdb package.

    The duckdb driver commits each statement unless a transaction was begun,
    and has no way to ask whether one is open, so this adapter begins one
    itself while statements are held (AUTOCOMMIT OFF, BEGIN BATCH) and keeps
    track of it.  While it is open, every statement runs on the connection
    itself rather than on a cursor (see :class:`_SharedCursor`).
    """

    #: A transaction this adapter or a script's own BEGIN opened, not yet ended.
    in_transaction: bool = False

    def __init__(self, DuckDB_fn: str) -> None:
        try:
            import duckdb  # noqa: F401
        except Exception:
            fatal_error("The duckdb module is required.")
        from execsql.types import dbt_duckdb

        super().__init__(
            server_name=None,
            db_name=DuckDB_fn,
            user_name=None,
            need_passwd=False,
            encoding="UTF-8",
        )
        self.type = dbt_duckdb
        self.catalog_name = Path(DuckDB_fn).stem
        self.open_db()

    def __repr__(self) -> str:
        return f"DuckDBDatabase({self.db_name!r})"

    def cursor(self) -> Any:
        """A cursor, or while a transaction is open, the connection itself."""
        if self.conn is None:
            self.open_db()
        if self.in_transaction:
            return _SharedCursor(self.conn)
        return self.conn.cursor()

    def begin_transaction(self) -> None:
        """Open a transaction if none is open."""
        if self.conn is None:
            self.open_db()
        if not self.in_transaction:
            # A second BEGIN would abort the open transaction, hence the tracking.
            self.conn.execute("BEGIN TRANSACTION")
            self.in_transaction = True

    def execute(self, sql: Any, paramlist: list | None = None, *, fetch: bool = False) -> tuple[list[str], list] | None:
        """Execute *sql*, noting a transaction the statement itself begins or ends.

        The driver's ``rowcount`` is always -1: DuckDB answers an INSERT,
        UPDATE or DELETE with a one-column ``Count`` result instead, which is
        read here to set ``$LAST_ROWCOUNT`` as other drivers do.
        """
        text = " ".join(sql) if type(sql) in (tuple, list) else sql
        start = statement_start(text)
        m = _TRANSACTION_RX.match(start)
        if m and m.group("begin"):
            self.in_transaction = True  # so the BEGIN itself runs on the connection
        query = bool(_QUERY_RX.match(start))
        result = super().execute(sql, paramlist, fetch=fetch or not query)
        if m and m.group("end"):
            self.in_transaction = False
        if not query and result is not None and result[0] == ["Count"]:
            rows = result[1]
            if _state.subvars is not None:
                _state.subvars.add_substitution("$LAST_ROWCOUNT", rows[0][0] if rows else -1)
            return None
        return result if fetch else None

    def commit(self) -> None:
        """Commit the open transaction if autocommit is enabled."""
        super().commit()
        if self.autocommit:
            self.in_transaction = False

    def rollback(self) -> None:
        """Roll back the open transaction."""
        super().rollback()
        self.in_transaction = False

    def close(self) -> None:
        """Close the connection; an open transaction is rolled back."""
        super().close()
        self.in_transaction = False

    def open_db(self) -> None:
        """Open a connection to the DuckDB database file."""
        import duckdb

        if self.conn is None:
            try:
                self.conn = duckdb.connect(self.db_name, read_only=False)
            except ErrInfo:
                raise
            except Exception as e:
                raise ErrInfo(
                    type="exception",
                    exception_msg=exception_desc(),
                    other_msg=f"Can't open DuckDB database {self.db_name}",
                ) from e

    def exec_cmd(self, querycommand: str) -> None:
        """Execute a query command as a view selection, since DuckDB lacks stored procedures."""
        # DuckDB does not support stored functions, so the querycommand
        # is treated as (and therefore must be) a view.
        with self._cursor() as curs:
            cmd = f"select * from {self.quote_identifier(querycommand)};"
            try:
                curs.execute(cmd)
                _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
            except Exception:
                self.rollback()
                raise

    def view_exists(self, view_name: str, schema_name: str | None = None) -> bool:
        """Return True if the named view exists in the DuckDB database."""
        # DuckDB information_schema has no 'views' table; views are listed in 'tables'
        return self.table_exists(view_name)

    def schema_exists(self, schema_name: str) -> bool:
        """Return True if the named schema exists in the current DuckDB catalog."""
        # In DuckDB, the 'schemata' view is not limited to the current database.
        with self._cursor() as curs:
            curs.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = ? and catalog_name = ?;",
                (schema_name, self.catalog_name),
            )
            rows = curs.fetchall()
        return len(rows) > 0
