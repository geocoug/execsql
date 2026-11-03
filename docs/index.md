# A Multi-DBMS SQL Script Processor

[![execsql logo](images/execsql_logo_01.png)](https://pypi.org/project/execsql2/)

**execsql2** is a command-line tool for turning SQL scripts into repeatable data workflows. Use SQL to transform your data, with commands for loading files, checking results, moving data between databases and producing reports in the same script.

The Python package is **execsql2**; its command and importable module are **execsql**. It works with PostgreSQL, MySQL/MariaDB, SQL Server, SQLite, DuckDB, Firebird, MS Access, Oracle and ODBC DSNs. See [database support and requirements](getting-started/requirements.md#support-tiers) for drivers and support tiers.

## Why use execsql?

**Keep the workflow beside the SQL.** An import, a transformation, a validation check and an export can live in one readable, version-controlled file. You can run it from your terminal, schedule it or call it from another program, without writing a separate application to coordinate those steps.

**Use the same scripting tools across databases.** Variables, conditions, loops, file operations and prompts use the same metacommands on every supported backend. Your SQL still needs to match the database's dialect, but you can reuse the surrounding workflow and branch where databases differ.

**Make routine work repeatable and inspectable.** Parameterize a script for different inputs, stop when a validation fails, split shared work into reusable scripts and keep a log of each run. Add prompts and data displays when a person needs to choose a file or review results.

<a id="capabilities"></a>

## What can you do with it?

- **Load and validate data:** import CSV, JSON or spreadsheets, transform records with SQL, and use `ASSERT` to check assumptions before continuing. Start with the [CSV-to-SQLite walkthrough](getting-started/first-script.md).
- **Move data between systems:** connect to multiple databases and copy tables or query results between them, including different DBMSs. See [data movement and validation examples](guides/examples/data-movement.md).
- **Produce deliverables:** export tables and queries to CSV, XLSX, JSON, Parquet, HTML and other formats, or use templates for custom reports. See [reports and external commands](guides/examples/reports.md). Some formats require [optional extras](getting-started/installation.md#extras).
- **Automate recurring jobs:** use variables, conditions, loops and named scripts for repeatable loads, checks and exports. See [control-flow examples](guides/examples/control-flow.md) and [transaction behavior](guides/usage.md#autocommit) before changing persistent data.
- **Build interactive SQL tools:** ask for input, select files and display results for review. See [interactive tools and debugging](guides/examples/interactive.md) for examples and GUI/TUI requirements.

## How scripts work

Write ordinary SQL and add metacommands in comments beginning with `-- !x!`. execsql runs the SQL against your database and handles the metacommands itself. Other SQL tools ignore those comments; scripts that depend on them or on variable substitution need execsql to perform their intended work.

The toolchain also helps before you run a script: **`execsql format`** formats SQL and metacommands, **`execsql lint`** checks scripts without a database, and the [language server](guides/editors.md) brings diagnostics, completion, navigation and formatting into your editor. Formatting and linting can also run in pre-commit or CI.

<a id="getting-started"></a>

## Start here

[Your first script](getting-started/first-script.md) supplies a CSV file, a SQLite script, exact commands and expected results. No server or account is needed.

```sh
uv tool install execsql2
execsql --help
```

<a id="documentation-guide"></a>
<a id="major-features-and-reference"></a>
<a id="tips-and-guidance"></a>
<a id="examples"></a>

## Choose a task

| Task                                          | Read                                                                                                |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Install or add database/format support        | [Installation and extras](getting-started/installation.md)                                          |
| Find a CLI subcommand or option               | [Commands](reference/cli/index.md)                                                                  |
| Write scripts with variables and metacommands | [Metacommands](reference/metacommands.md), [substitution variables](reference/substitution_vars.md) |
| Understand commits, errors and rollback       | [Transaction behavior](guides/usage.md#autocommit)                                                  |
| Find a worked recipe                          | [Examples by task](guides/examples.md), [script templates](templates/index.md)                      |
| Set up VS Code or another editor              | [Editor setup](guides/editors.md)                                                                   |
| Call execsql from Python                      | [Library API](api/index.md)                                                                         |

## About the package

execsql2 is a maintained fork of execsql 1.130.1, originally written by R.Dreas Nielsen, and is maintained by [Caleb Grant](https://github.com/geocoug). Migrating users should read [changes from upstream](about/divergence.md); deliberate differences and deprecations are documented there. [Release notes](about/change_log.md) describe changes between execsql2 versions.

The package is available on [PyPI](https://pypi.org/project/execsql2/), with source code and issue tracking on [GitHub](https://github.com/geocoug/execsql).
