# Metacommands

## Dispatch table

The `DISPATCH_TABLE` (a `MetaCommandList`) maps metacommand regex patterns to
their handler functions. It is populated when this module is first imported
and consumed by `script.MetacommandStmt.run()` via `_state.metacommandlist`.

::: execsql.metacommands

## Handler modules

::: execsql.metacommands.connect

::: execsql.metacommands.conditions

::: execsql.metacommands.control

::: execsql.metacommands.data

::: execsql.metacommands.io

::: execsql.metacommands.system

::: execsql.metacommands.script_ext

::: execsql.metacommands.debug
