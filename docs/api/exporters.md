# Exporters

## Base infrastructure

`ExportRecord`, `ExportMetadata`, and `WriteSpec` are the data structures that flow through the export pipeline. `ExportMetadata` accumulates records for every EXPORT call in a script run; `WriteSpec` captures per-file encoding and path configuration. These are used internally by all format writers — you only need to understand them if you are writing a new exporter. See [Adding Exporters](../dev/adding_exporters.md) for a step-by-step guide.

::: execsql.exporters.base

## Format writers

Each module below implements one or more output formats. Every writer follows the same signature: receive a SQL `select_stmt` string and a `Database` instance, stream rows via `db.select_rowsource()`, and write to a file or zip. See [Adding Exporters](../dev/adding_exporters.md) to add a new format.

::: execsql.exporters.delimited

::: execsql.exporters.json

::: execsql.exporters.xml

::: execsql.exporters.html

::: execsql.exporters.pretty

::: execsql.exporters.raw

::: execsql.exporters.values

::: execsql.exporters.templates

::: execsql.exporters.latex

::: execsql.exporters.ods

::: execsql.exporters.xls

::: execsql.exporters.feather

::: execsql.exporters.parquet

::: execsql.exporters.sqlite

::: execsql.exporters.duckdb

::: execsql.exporters.zip
