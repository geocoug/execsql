# Exporters

## Base infrastructure

`ExportRecord`, `ExportMetadata`, and `WriteSpec` are the data structures that flow through the export pipeline. `ExportMetadata` accumulates records for every EXPORT call in a script run; `WriteSpec` captures per-file encoding and path configuration. These support export bookkeeping and output configuration; individual writers do not all consume the same objects. See [Adding Exporters](../dev/adding_exporters.md) for a step-by-step guide.

::: execsql.exporters.base

::: execsql.exporters.protocol

## Format writers

Each module below implements one or more output formats. Many writers receive SQL and a Database instance and stream rows via `db.select_rowsource()`. Others receive already-fetched headers/rows (for example Parquet), or multiple queries for a workbook. Consult each signature and the central `_dispatch_format()` call site; output/append/ZIP support is format-specific. See [Adding Exporters](../dev/adding_exporters.md) to add a new format.

::: execsql.exporters.delimited

::: execsql.exporters.json

::: execsql.exporters.xml

::: execsql.exporters.html

::: execsql.exporters.pretty

::: execsql.exporters.raw

::: execsql.exporters.values

::: execsql.exporters.templates

::: execsql.exporters.latex

::: execsql.exporters.markdown

::: execsql.exporters.ods

::: execsql.exporters.xls

::: execsql.exporters.xlsx

::: execsql.exporters.yaml

::: execsql.exporters.feather

::: execsql.exporters.parquet

::: execsql.exporters.sqlite

::: execsql.exporters.duckdb

::: execsql.exporters.zip
