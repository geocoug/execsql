# Metacommands

## Dispatch table

`build_dispatch_table()` (in `execsql.metacommands.dispatch`) populates a `MetaCommandList` with every metacommand regex and its handler. `__init__.py` calls it at import time and exposes the result as `DISPATCH_TABLE`; runtime consumes it via `_state.metacommandlist`.

If you are adding a new metacommand, start with the [Adding Metacommands](../dev/adding_metacommands.md) guide.

::: execsql.metacommands

::: execsql.metacommands.dispatch

## Handler modules

::: execsql.metacommands.connect

::: execsql.metacommands.conditions

::: execsql.metacommands.control

::: execsql.metacommands.data

::: execsql.metacommands.io_export

::: execsql.metacommands.io_import

::: execsql.metacommands.io_write

::: execsql.metacommands.io_fileops

::: execsql.metacommands.io

::: execsql.metacommands.prompt

::: execsql.metacommands.system

::: execsql.metacommands.script_ext

::: execsql.metacommands.upsert

::: execsql.metacommands.debug
