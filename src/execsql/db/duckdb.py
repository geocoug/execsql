from __future__ import annotations

"""
DuckDB database adapter for execsql.

Implements :class:`DuckDBDatabase`, which connects to DuckDB in-process
analytics databases via the ``duckdb`` package.  Corresponds to ``-t k``
on the CLI.
"""

from pathlib import Path

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, fatal_error
import execsql.state as _state


class DuckDBDatabase(Database):
    def __init__(self, DuckDB_fn: str) -> None:
        try:
            import duckdb  # noqa: F401
        except Exception:
            fatal_error("The duckdb module is required.")
        from execsql.types import dbt_duckdb

        self.type = dbt_duckdb
        self.server_name = None
        self.db_name = DuckDB_fn
        self.catalog_name = Path(DuckDB_fn).stem
        self.user = None
        self.need_passwd = False
        self.encoding = "UTF-8"
        self.encode_commands = False
        self.paramstr = "?"
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return f"DuckDBDatabase({self.db_name!r})"

    def open_db(self) -> None:
        import duckdb

        if self.conn is None:
            try:
                self.conn = duckdb.connect(self.db_name, read_only=False)
            except ErrInfo:
                raise
            except Exception:
                raise ErrInfo(
                    type="exception",
                    exception_msg=exception_desc(),
                    other_msg=f"Can't open DuckDB database {self.db_name}",
                )

    def exec_cmd(self, querycommand: str) -> None:
        # DuckDB does not support stored functions, so the querycommand
        # is treated as (and therefore must be) a view.
        curs = self.cursor()
        cmd = f"select * from {querycommand};"
        try:
            curs.execute(cmd.encode(self.encoding))
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            self.rollback()
            raise

    def view_exists(self, view_name: str) -> bool:
        # DuckDB information_schema has no 'views' table; views are listed in 'tables'
        return self.table_exists(view_name)

    def schema_exists(self, schema_name: str) -> bool:
        # In DuckDB, the 'schemata' view is not limited to the current database.
        curs = self.cursor()
        curs.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = ? and catalog_name = ?;",
            (schema_name, self.catalog_name),
        )
        rows = curs.fetchall()
        curs.close()
        return len(rows) > 0
