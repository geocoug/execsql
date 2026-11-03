# Importers

## Base infrastructure

`import_data_table()` is the shared back-end used by many row-based importers. CSV also has a separate file-oriented loading path. It handles column header cleaning, `CREATE TABLE` (when requested), and bulk-insertion via `db.populate_table()`. A reader using this back-end supplies headers and materialized rows; it also owns format validation and resource cleanup. Existing-target conversions use target column types, while NEW/REPLACEMENT infer types.

If you are adding support for a new file format, start with the [Adding Importers](../dev/adding_importers.md) guide.

::: execsql.importers.base

## Format readers

Each module below implements one or more import formats.

::: execsql.importers.csv

::: execsql.importers.json

::: execsql.importers.ods

::: execsql.importers.xls

::: execsql.importers.feather
