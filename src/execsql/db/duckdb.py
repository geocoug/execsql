from __future__ import annotations

"""
DuckDB database adapter for execsql.

Implements :class:`DuckDBDatabase`, which connects to DuckDB in-process
analytics databases via the ``duckdb`` package.  Corresponds to ``-t k``
on the CLI.
"""

import importlib.util
import re
import sys
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from execsql.db.base import Database, statement_start
from execsql.db.target_types import kind_for_type_name
from execsql.types import DataType
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error, install_hint
import execsql.state as _state

__all__ = ["DuckDBDatabase", "insert_rows"]

# Statements that return rows; any other statement DuckDB answers with a
# one-column "Count" result (rows inserted, updated or deleted).
_QUERY_RX = re.compile(r"(?:SELECT|WITH|VALUES|FROM|TABLE|SHOW|DESCRIBE|SUMMARIZE|EXPLAIN|PRAGMA|CALL)\b|\(", re.I)

# A statement that opens a transaction, or one that ends it.
_TRANSACTION_RX = re.compile(r"(?P<begin>BEGIN|START\s+TRANSACTION)\b|(?P<end>COMMIT|END|ROLLBACK|ABORT)\b", re.I)


# Parameters bound by one INSERT ... VALUES statement in insert_rows(); a
# wide table gets fewer rows per statement.
_PARAMS_PER_STATEMENT = 10_000


@contextmanager
def _pandas_lookup_skipped() -> Iterator[None]:
    """Make DuckDB's check for pandas fail at once while it binds rows.

    The duckdb package asks Python's import system for ``pandas`` twice for
    every row it binds, and when pandas is not installed nothing remembers
    the answer, so each row searches ``sys.path`` again: about three
    quarters of an INSERT's time.  A ``None`` in ``sys.modules`` makes that
    import fail without the search.  It is set only when pandas is not
    installed, so no import that could have succeeded fails, and it is
    removed afterwards.
    """
    if "pandas" in sys.modules or importlib.util.find_spec("pandas") is not None:
        yield
        return
    sys.modules["pandas"] = None  # type: ignore[assignment]
    try:
        yield
    finally:
        if "pandas" in sys.modules and sys.modules["pandas"] is None:
            del sys.modules["pandas"]


def insert_rows(curs: Any, table: str, columns: list[str], rows: list[Any]) -> None:
    """Insert *rows* into *table* with multi-row ``INSERT ... VALUES`` statements.

    *table* is quoted (and schema-qualified as needed); *columns* are the
    quoted column names, in the order of each row's values.  DuckDB's
    ``executemany`` runs one row at a time; binding many rows in one
    statement is several times faster and stores the same values.
    """
    if not rows:
        return
    per_statement = max(1, _PARAMS_PER_STATEMENT // max(1, len(columns)))
    head = f"insert into {table} ({','.join(columns)}) values "
    row_marks = "(" + ",".join("?" * len(columns)) + ")"
    with _pandas_lookup_skipped():
        for start in range(0, len(rows), per_statement):
            chunk = rows[start : start + per_statement]
            curs.execute(head + ",".join([row_marks] * len(chunk)), [value for row in chunk for value in row])


class _SharedCursor:
    """A cursor that runs on the database's one connection.

    A DuckDB cursor is a separate connection: a temporary table created on
    one is invisible to the next, and a cursor's transaction is its own.  So
    every statement runs on the connection itself.  A connection holds one
    pending result, though, and the next statement discards it; COPY reads
    its source twice at once (the rows, and a scan for their types).  So
    before another statement runs, the result this cursor still has to
    deliver is read into memory (:meth:`DuckDBDatabase._take_connection`).
    An EXPORT, which runs nothing else while it reads, still streams.
    """

    def __init__(self, db: DuckDBDatabase) -> None:
        self._db = db
        self._conn = db.conn
        self._buffer: deque[Any] | None = None  # the rest of the result, once read ahead
        self._pending = False  # a result the connection still holds for this cursor
        self.description: Any = None
        self.arraysize = 1000

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def execute(self, sql: Any, params: Any = None) -> _SharedCursor:
        self._db._take_connection(self)
        if params is None:
            self._conn.execute(sql)
        else:
            self._conn.execute(sql, params)
        self.description = self._conn.description
        self._buffer = None
        self._pending = self.description is not None
        return self

    def executemany(self, sql: Any, params: Any) -> _SharedCursor:
        self._db._take_connection(self)
        self._conn.executemany(sql, params)
        self.description = self._conn.description
        self._buffer = None
        self._pending = False
        return self

    def read_ahead(self) -> None:
        """Move the rest of the pending result into memory, freeing the connection."""
        if self._pending:
            self._buffer = deque(self._conn.fetchall())
            self._pending = False

    def fetchmany(self, size: int | None = None) -> list[Any]:
        size = size or self.arraysize
        if self._buffer is not None:
            return [self._buffer.popleft() for _ in range(min(size, len(self._buffer)))]
        if not self._pending:
            return []
        rows: list[Any] = self._conn.fetchmany(size)
        if not rows:
            self._pending = False
        return rows

    def fetchone(self) -> Any:
        rows = self.fetchmany(1)
        return rows[0] if rows else None

    def fetchall(self) -> list[Any]:
        if self._buffer is not None:
            rows, self._buffer = list(self._buffer), deque()
            return rows
        if not self._pending:
            return []
        self._pending = False
        return list(self._conn.fetchall())

    def close(self) -> None:
        """Leave the connection, and any transaction on it, open."""
        self._buffer = None
        self._pending = False
        self._db._release_connection(self)


class DuckDBDatabase(Database):
    """DuckDB in-process analytics adapter using the duckdb package.

    The duckdb driver commits each statement unless a transaction was begun,
    and has no way to ask whether one is open, so this adapter begins one
    itself while statements are held (AUTOCOMMIT OFF, BEGIN BATCH) and keeps
    track of it.  Every statement runs on the connection itself rather than
    on a cursor (see :class:`_SharedCursor`), so it joins that transaction
    and sees the run's temporary tables.
    """

    #: A transaction this adapter or a script's own BEGIN opened, not yet ended.
    in_transaction: bool = False
    #: The cursor whose result the connection holds, if any.
    _holder: _SharedCursor | None = None

    def __init__(self, DuckDB_fn: str) -> None:
        try:
            import duckdb  # noqa: F401
        except Exception:
            fatal_error(f"The duckdb module is required to use DuckDB. {install_hint('duckdb')}")
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

    def current_schema(self) -> str | None:
        return self._query_current_schema("select current_schema()")

    def __repr__(self) -> str:
        return f"DuckDBDatabase({self.db_name!r})"

    def cursor(self) -> Any:
        """A cursor on the database's one connection (see :class:`_SharedCursor`)."""
        if self.conn is None:
            self.open_db()
        return _SharedCursor(self)

    def _take_connection(self, cursor: _SharedCursor | None = None) -> None:
        """Before a statement runs, read ahead the result another cursor has not finished with."""
        holder = self._holder
        if holder is not None and holder is not cursor:
            holder.read_ahead()
        self._holder = cursor

    def _release_connection(self, cursor: _SharedCursor) -> None:
        if self._holder is cursor:
            self._holder = None

    def begin_transaction(self) -> None:
        """Open a transaction if none is open."""
        if self.conn is None:
            self.open_db()
        if not self.in_transaction:
            # A second BEGIN would abort the open transaction, hence the tracking.
            self._take_connection()
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
        try:
            # Reading ahead another cursor's result can raise (DuckDB reports
            # some errors at fetch time); roll back as a failed commit does.
            self._take_connection()
        except BaseException:
            if self.autocommit and self.in_transaction:
                self.rollback()
            raise
        super().commit()
        if self.autocommit:
            self.in_transaction = False

    def rollback(self) -> None:
        """Roll back the open transaction."""
        try:
            self._take_connection()
        except Exception:  # best effort, as the rollback is: a failed transaction may not give up its rows
            self._holder = None
        super().rollback()
        self.in_transaction = False

    def close(self) -> None:
        """Close the connection; an open transaction is rolled back."""
        self._holder = None
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

    def table_exists_where_created(self, table_name: str, schema_name: str | None = None) -> bool:
        """Whether *table_name* exists in the current database (not an ``ATTACH``ed one)."""
        # information_schema.tables lists the tables of every attached database.
        sql = "select table_name from information_schema.tables where table_name = ? and table_catalog = current_database()"
        params: list = [table_name]
        if schema_name:
            sql += " and table_schema = ?"
            params.append(schema_name)
        with self._cursor() as curs:
            curs.execute(sql, params)
            return len(curs.fetchall()) > 0

    def row_inserter(self, curs: Any, table: str, columns: list[str]) -> Callable[[list[list[Any]]], None]:
        """Insert each batch with multi-row ``INSERT ... VALUES`` (:func:`insert_rows`)."""

        def insert(rows: list[list[Any]]) -> None:
            insert_rows(curs, table, columns, rows)

        return insert

    def _described_kind(self, description: Any) -> type[DataType] | None:
        """DuckDB describes a column by its type's name (``DECIMAL(18,3)``, ``TIMESTAMP WITH TIME ZONE``)."""
        return kind_for_type_name(str(description[1]))

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
