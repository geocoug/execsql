# Databases

## Base classes

`Database` defines the interface that every DBMS adapter must implement. Concrete adapters in sibling modules (`sqlite.py`, `postgres.py`, `duckdb.py`, etc.) subclass it, set a handful of required instance attributes in `__init__`, and override `open_db()` plus the schema-introspection methods. `DatabasePool` is the dict-like container (exposed as `_state.dbs`) that maps string aliases to open `Database` instances and tracks the active connection.

If you are adding support for a new database, start with the [Adding Database Adapters](../dev/adding_db_adapters.md) guide.

::: execsql.db.base

## Database factory

Convenience constructors used internally to create typed `Database` instances. The CLI calls the appropriate factory function based on the `-t` flag value. Each factory validates its arguments (e.g., checking that a file exists) before constructing and returning the adapter.

::: execsql.db.factory
