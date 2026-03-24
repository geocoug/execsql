# Adding a New Database Adapter

This guide walks through every step required to add support for a new database management system (DBMS) to execsql. The process involves three files: subclass `Database`, write a factory function, and wire the new type into the CLI.

______________________________________________________________________

## Background: How Database Adapters Work

Every DBMS is represented by a concrete subclass of `Database` (defined in `src/execsql/db/base.py`). The `Database` class defines the full interface that the rest of execsql uses to talk to a database — opening connections, running SQL, streaming result sets, importing data, and checking schema objects.

### DatabasePool

`_state.dbs` is a `DatabasePool` instance — a dict-like container that maps string aliases to open `Database` instances and tracks which connection is active. All metacommand handlers call `_state.dbs.current()` to get the active connection; they never instantiate adapters directly.

### Factory functions

Each DBMS adapter is created by a dedicated factory function in `src/execsql/db/factory.py`. Factory functions validate arguments (e.g., file existence for SQLite) and return a fully constructed adapter instance. The CLI calls the appropriate factory function based on the `-t` flag.

______________________________________________________________________

## Step-by-step: Adding a Database Adapter

### Step 1 — Write the adapter class

Create `src/execsql/db/mydb.py`. Start by subclassing `Database` and setting the required instance attributes in `__init__`, then call `self.open_db()` to establish the connection:

```python
# src/execsql/db/mydb.py
from __future__ import annotations

"""
MyDB database adapter for execsql.

Implements :class:`MyDBDatabase`, which connects to MyDB databases.
Corresponds to ``-t y`` on the CLI.
"""

from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc


class MyDBDatabase(Database):
    def __init__(self, db_file: str) -> None:
        try:
            import mydb_driver  # noqa: F401
        except ImportError:
            from execsql.utils.errors import fatal_error
            fatal_error("The mydb_driver package is required for MyDB connections.")

        from execsql.types import dbt_mydb  # register this type (see Step 4)

        self.type = dbt_mydb
        self.server_name = None
        self.db_name = db_file
        self.user = None
        self.need_passwd = False
        self.encoding = "UTF-8"
        self.encode_commands = False
        self.paramstr = "?"      # placeholder style: "?" for most drivers, "%s" for psycopg2
        self.conn = None
        self.autocommit = True
        self.open_db()

    def __repr__(self) -> str:
        return f"MyDBDatabase({self.db_name!r})"

    def open_db(self) -> None:
        import mydb_driver

        if self.conn is None:
            try:
                self.conn = mydb_driver.connect(self.db_name)
            except Exception:
                raise ErrInfo(
                    type="exception",
                    exception_msg=exception_desc(),
                    other_msg=f"Can't open MyDB database {self.db_name}",
                )

    # --- Schema introspection (required) ---

    def table_exists(self, table_name: str, schema_name: str | None = None) -> bool:
        # Query the DBMS catalog for the table. Use parameterized queries.
        curs = self.cursor()
        curs.execute("SELECT name FROM mydb_tables WHERE name = ?", (table_name,))
        return curs.fetchone() is not None

    def column_exists(
        self, table_name: str, column_name: str, schema_name: str | None = None
    ) -> bool:
        cols = self.table_columns(table_name, schema_name)
        return column_name in cols

    def table_columns(self, table_name: str, schema_name: str | None = None) -> list[str]:
        curs = self.cursor()
        curs.execute(f'SELECT * FROM "{table_name}" WHERE 1=0')
        return [d[0] for d in curs.description]

    def view_exists(self, view_name: str) -> bool:
        curs = self.cursor()
        curs.execute("SELECT name FROM mydb_views WHERE name = ?", (view_name,))
        return curs.fetchone() is not None

    def schema_exists(self, schema_name: str) -> bool:
        return False  # set True and implement if the DBMS supports schemas

    def drop_table(self, tablename: str) -> None:
        self.execute(f'DROP TABLE IF EXISTS "{tablename}"')

    # --- Data loading (required for IMPORT support) ---

    def populate_table(
        self,
        schema_name: str | None,
        table_name: str,
        rowsource: Any,
        column_list: list[str],
        tablespec_src: Any,
    ) -> None:
        sq_name = self.schema_qualified_table_name(schema_name, table_name)
        colspec = ", ".join(f'"{c}"' for c in column_list)
        paramspec = ", ".join("?" for _ in column_list)
        sql = f"INSERT INTO {sq_name} ({colspec}) VALUES ({paramspec})"
        curs = self.cursor()
        for row in rowsource:
            if not (len(row) == 1 and row[0] is None):
                curs.execute(sql, row)
```

### Step 2 — Key attributes and methods

These are the instance attributes and methods you must configure correctly:

| Attribute / Method     | Type              | Purpose                                                                           |
| ---------------------- | ----------------- | --------------------------------------------------------------------------------- |
| `self.type`            | `DbType`          | DBMS type token (e.g., `dbt_sqlite`). Controls quoting and type-mapping.          |
| `self.paramstr`        | `str`             | SQL parameter placeholder: `"?"` (most drivers) or `"%s"` (psycopg2, PyMySQL).    |
| `self.encoding`        | `str`             | Database character encoding. Detect from the database on connect if possible.     |
| `self.encode_commands` | `bool`            | `True` if SQL strings should be encoded before passing to the driver.             |
| `self.autocommit`      | `bool`            | `True` means the driver commits automatically; `False` requires explicit commits. |
| `self.conn`            | driver connection | Set in `open_db()`.                                                               |
| `open_db()`            | method            | **Must override.** Establish the connection and assign `self.conn`.               |
| `table_exists()`       | method            | **Must override.** Query the DBMS catalog. Use parameterized queries.             |
| `column_exists()`      | method            | **Must override.** Check column presence.                                         |
| `table_columns()`      | method            | **Must override.** Return column names for a table.                               |
| `view_exists()`        | method            | **Must override.** Check view presence.                                           |
| `schema_exists()`      | method            | **Must override.** Return `False` if schemas are not supported.                   |
| `drop_table()`         | method            | **Must override.** Drop a table (used by IMPORT when creating fresh).             |
| `populate_table()`     | method            | **Must override.** Bulk-load rows from a generator (used by IMPORT).              |
| `exec_cmd()`           | method            | Override if the DBMS can execute stored procedures or views as commands.          |

Methods inherited from `Database` that you get for free include `execute()`, `cursor()`, `close()`, `commit()`, `rollback()`, `select_rowsource()`, `select_data()`, `schema_qualified_table_name()`, `quote_identifier()`, and `paramsubs()`.

### Step 3 — Write the factory function

Open `src/execsql/db/factory.py` and add a factory function:

```python
from execsql.db.mydb import MyDBDatabase


def db_MyDB(mydb_file: str, new_db: bool = False) -> MyDBDatabase:
    """Connect to a MyDB database file.

    Args:
        mydb_file: Path to the `.mydb` database file.
        new_db: If ``True``, create the file if it does not exist.
    """
    from pathlib import Path

    if not new_db and not Path(mydb_file).exists():
        from execsql.utils.errors import fatal_error
        fatal_error(f"MyDB database file not found: {mydb_file}")
    return MyDBDatabase(mydb_file)
```

### Step 4 — Register the type token and wire into the CLI

The CLI maps the `-t` flag value to a factory call. Open `src/execsql/cli.py` and find the `db_type` dispatch block. Add a branch for your new type code (pick an unused single character):

```python
elif db_type == "y":
    db = db_MyDB(database_file, new_db=new_db)
```

You also need to define the `dbt_mydb` type token. Open `src/execsql/types.py` and follow the pattern used for `dbt_sqlite` or `dbt_duckdb`.

### Step 5 — Add tests

Integration tests exercise the full CLI against a temporary database:

```python
# tests/db/test_mydb.py
import pytest
from pathlib import Path
from typer.testing import CliRunner
from execsql.cli import app


@pytest.fixture()
def runner():
    return CliRunner()


class TestMyDBAdapter:
    """MyDB adapter basic operations."""

    def test_create_and_query(self, runner, tmp_path):
        db = tmp_path / "test.mydb"
        script = tmp_path / "test.sql"
        script.write_text(
            "CREATE TABLE t (id INTEGER, val TEXT);\n"
            "INSERT INTO t VALUES (1, 'hello');\n"
        )
        result = runner.invoke(app, ["-ty", str(script), str(db), "-n"])
        assert result.exit_code == 0, result.output
```

______________________________________________________________________

## Checklist

- [ ] `MyDBDatabase` class written in `src/execsql/db/mydb.py`
- [ ] All required methods implemented (`open_db`, `table_exists`, `column_exists`, `table_columns`, `view_exists`, `schema_exists`, `drop_table`, `populate_table`)
- [ ] Factory function `db_MyDB()` added to `src/execsql/db/factory.py`
- [ ] Type token `dbt_mydb` defined in `src/execsql/types.py`
- [ ] CLI dispatch branch added in `src/execsql/cli.py`
- [ ] Integration test added to `tests/db/`
- [ ] `pytest` passes locally
- [ ] New type code added to the `-t` flag table in [Syntax & Options](../syntax.md#db_types)
- [ ] Library dependency added to `pyproject.toml` extras and documented in [Requirements](../requirements.md#libraries)
