# Metacommands

## Dispatch table

The `DISPATCH_TABLE` (a `MetaCommandList`) maps metacommand regex patterns to their handler functions. It is populated when this module is first imported and consumed by `script.MetacommandStmt.run()` via `_state.metacommandlist`.

If you are adding a new metacommand, start with the [Adding Metacommands](../dev/adding_metacommands.md) guide.

::: execsql.metacommands

## Handler modules

::: execsql.metacommands.connect

::: execsql.metacommands.conditions

::: execsql.metacommands.control

::: execsql.metacommands.data

::: execsql.metacommands.io

::: execsql.metacommands.prompt

::: execsql.metacommands.system

::: execsql.metacommands.script_ext

::: execsql.metacommands.debug
