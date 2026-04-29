# Importers

## Base infrastructure

`import_data_table()` is the shared back-end called by every importer. It handles column header cleaning, `CREATE TABLE` (when requested), and bulk-insertion via `db.populate_table()`. Format-specific importers only need to parse their file into headers and rows, then call `import_data_table()`.

If you are adding support for a new file format, start with the [Adding Importers](../dev/adding_importers.md) guide.

::: execsql.importers.base

## Format readers

Each module below implements one or more import formats.

::: execsql.importers.csv

::: execsql.importers.json

::: execsql.importers.ods

::: execsql.importers.xls

::: execsql.importers.feather
