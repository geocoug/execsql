# Databases

## Base classes

The `Database` abstract base class defines the interface every DBMS adapter
must implement. `DatabasePool` is the dict-like container that maps aliases
to open connections and tracks the currently active one.

::: execsql.db.base

## Database factory

Convenience constructors used internally to create typed `Database` instances.

::: execsql.db.factory
