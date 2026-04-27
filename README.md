> [!NOTE]
> **This is a maintained fork of [execsql](https://execsql.readthedocs.io/).**
> The original monolith has been fully refactored into a modular package.
> The CLI and configuration are backwards-compatible with upstream v1.130.1.
> Report issues at [github.com/geocoug/execsql/issues](https://github.com/geocoug/execsql/issues).

<div align="center">

<img src="https://execsql2.readthedocs.io/en/latest/images/execsql_logo_01.png" alt="execsql logo">

*Multi-DBMS SQL script processor.*

</div>

<div align="center">

[![CI/CD](https://github.com/geocoug/execsql/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/geocoug/execsql/actions/workflows/ci-cd.yml)
[![codecov](https://codecov.io/gh/geocoug/execsql/graph/badge.svg)](https://codecov.io/gh/geocoug/execsql)
[![Docs](https://readthedocs.org/projects/execsql2/badge/)](https://execsql2.readthedocs.io/)
[![PyPI](https://img.shields.io/pypi/v/execsql2)](https://pypi.org/project/execsql2/)
[![Python](https://img.shields.io/pypi/pyversions/execsql2)](https://pypi.org/project/execsql2/)
[![License](https://img.shields.io/pypi/l/execsql2)](https://pypi.org/project/execsql2/)
[![Downloads](https://pepy.tech/badge/execsql2/month)](https://pepy.tech/project/execsql2)

</div>

# Fork

*execsql2* is a maintained fork of [execsql](https://execsql.readthedocs.io/) originally authored by R.Dreas Nielsen. The upstream project is no longer actively maintained. This fork is maintained by [Caleb Grant](https://github.com/geocoug) and is distributed on PyPI as `execsql2`. Complete documentation is at [execsql2.readthedocs.io](https://execsql2.readthedocs.io/).

# Overview

*execsql* runs SQL scripts against PostgreSQL, MySQL/MariaDB, SQLite, DuckDB, MS-SQL-Server, MS-Access, Firebird, Oracle, or an ODBC DSN. In addition to standard SQL, it supports a set of metacommands (embedded in SQL comments) for importing and exporting data, copying data between databases, conditional execution, looping, substitution variables, and interactive prompts. Because metacommands live in SQL comments, scripts remain valid SQL and are ignored by other tools such as `psql` or `sqlcmd`.

# Installation

```bash
pip install execsql2
```

Optional extras install database drivers and feature bundles:

```bash
# Database drivers
pip install execsql2[postgres]    # PostgreSQL (psycopg2-binary)
pip install execsql2[mysql]       # MySQL / MariaDB (pymysql)
pip install execsql2[mssql]       # SQL Server (pyodbc)
pip install execsql2[duckdb]      # DuckDB
pip install execsql2[firebird]    # Firebird (firebird-driver)
pip install execsql2[oracle]      # Oracle (oracledb)
pip install execsql2[odbc]        # ODBC DSN (pyodbc)

# Feature bundles
pip install execsql2[formats]    # ODS, Excel, Jinja2, Feather, Parquet, HDF5
pip install execsql2[auth]            # OS keyring integration
pip install execsql2[auth-plaintext]  # Keyring + plaintext file backend (headless Linux)
pip install execsql2[auth-encrypted]  # Keyring + encrypted file backend (headless Linux)

# Convenience
pip install execsql2[all-db]     # All database drivers
pip install execsql2[all]        # Everything
```

SQLite connections use Python's standard library and require no additional packages.

# Usage

```text
execsql [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
```

Examples:

```bash
execsql -tp script.sql myserver mydb        # PostgreSQL
execsql -tm script.sql myserver mydb        # MySQL / MariaDB
execsql -ts script.sql myserver mydb        # SQL Server
execsql -tl script.sql mydb.sqlite          # SQLite
execsql -tk script.sql mydb.duckdb          # DuckDB
execsql -to script.sql myserver myservice   # Oracle
execsql script.sql                          # read connection from config file
```

## Supported Databases

| Flag | Database        |
| ---- | --------------- |
| `p`  | PostgreSQL      |
| `m`  | MySQL / MariaDB |
| `s`  | MS SQL Server   |
| `l`  | SQLite          |
| `k`  | DuckDB          |
| `a`  | MS Access       |
| `f`  | Firebird        |
| `o`  | Oracle          |
| `d`  | ODBC DSN        |

## Options

| Flag                                | Description                                                     |
| ----------------------------------- | --------------------------------------------------------------- |
| `-t {p,m,s,l,k,a,f,o,d}`            | Database type                                                   |
| `-u USER`                           | Database username                                               |
| `-p PORT`                           | Server port                                                     |
| `-a VALUE`                          | Set substitution variable `$ARG_x`                              |
| `-c SCRIPT`                         | Execute inline SQL or metacommand string                        |
| `-d`                                | Auto-create export directories                                  |
| `-f ENCODING`                       | Script file encoding (default: UTF-8)                           |
| `-l`                                | Write run log to `~/execsql.log`                                |
| `-m`                                | List metacommands and exit                                      |
| `-n`                                | Create a new SQLite or PostgreSQL database if it does not exist |
| `-v {0,1,2,3}`                      | GUI level (0=none, 1=password, 2=selection, 3=full)             |
| `-w`                                | Skip password prompt when a username is supplied                |
| `--dsn URL`                         | Connection string (e.g. `postgresql://user:pass@host/db`)       |
| `--output-dir DIR`                  | Default base directory for EXPORT output files                  |
| `--dry-run`                         | Parse the script and report commands without executing          |
| `--lint`                            | Static analysis: check structure and warn on issues (no DB)     |
| `--ping`                            | Test database connectivity and exit                             |
| `--profile`                         | Show per-statement timing summary after execution               |
| `--progress`                        | Show a progress bar for long-running IMPORT operations          |
| `--config FILE`                     | Load an explicit config file (highest priority after CLI args)  |
| `--debug`                           | Start in step-through debug mode (REPL pauses before each stmt) |
| `--dump-keywords`                   | Print metacommand keywords as JSON and exit                     |
| `--gui-framework {tkinter,textual}` | GUI framework for interactive prompts                           |

Run `execsql --help` for the full option list, or `execsql -m` to list all metacommands.

# Features

- Import data from CSV, TSV, JSON, Excel, OpenDocument, Feather, or Parquet files into a database table.
- Export query results in 20+ formats including CSV, TSV, JSON, YAML, XML, HTML, Markdown, LaTeX, XLSX, OpenDocument, Feather, Parquet, HDF5, DuckDB, SQLite, plain text, and Jinja2 templates.
- Copy data between databases, including across different DBMS types.
- Conditionally execute SQL and metacommands using `IF`/`ELSE`/`ENDIF` based on data values, DBMS type, or user input.
- Validate data with `ASSERT` — halt the script with a clear error message if a condition is false (ideal for CI pipelines).
- Loop over blocks of SQL and metacommands using `LOOP`/`ENDLOOP`.
- Use substitution variables (`SUB`, `$ARG_x`, built-in variables like `$date_tag`) to parameterize scripts.
- Include or chain scripts with `INCLUDE` and `SCRIPT`.
- Display query results in a GUI dialog; optionally prompt the user to select a row, enter a value, or submit a form.
- Write status messages or tabular output to the console or a file during execution.
- Automatically log each run, recording databases used, scripts executed, and user responses.

# An Illustration

The following script demonstrates metacommands and substitution variables. Lines prefixed with `-- !x!` are metacommands; identifiers wrapped in `!!` are substitution variables.

```sql
-- ==== Configuration ====
-- Put the (date-tagged) logfile name in the 'inputfile' substitution variable.
-- !x! SUB inputfile logs/errors_!!$date_tag!!
-- Ensure that the export directory will be created if necessary.
-- !x! CONFIG MAKE_EXPORT_DIRS Yes

-- ==== Display Fatal Errors ====
-- !x! IF(file_exists(!!inputfile!!))
    -- Import the data to a staging table.
    -- !x! IMPORT TO REPLACEMENT staging.errorlog FROM !!inputfile!!
    -- Create a view to display only fatal errors.
    create temporary view fatals as
        select user, run_time, process
        from   staging.errorlog
        where  severity = 'FATAL';
    -- !x! IF(HASROWS(fatals))
        -- Export the fatal errors to a dated report.
        -- !x! EXPORT fatals TO reports/error_report_!!$date_tag!! AS CSV
        -- Also display it to the user in a GUI.
        -- !x! PROMPT MESSAGE "Fatal errors in !!inputfile!!:" DISPLAY fatals
    -- !x! ELSE
        -- !x! WRITE "There are no fatal errors."
    -- !x! ENDIF
-- !x! ELSE
    -- !x! WRITE "There is no error log."
-- !x! ENDIF
drop table if exists staging.errorlog cascade;
```

The `PROMPT` metacommand produces a GUI display of the data:

![PROMPT display of 'fatals' view](https://execsql2.readthedocs.io/en/latest/images/fatals.png)

# Formatting Scripts

The `execsql-format` command normalizes execsql script files: it uppercases metacommand keywords, corrects block indentation, and optionally reformats SQL via sqlglot. It is installed automatically with the `execsql2` package.

```bash
# Format files in place
execsql-format --in-place scripts/

# Check formatting without writing (useful in CI)
execsql-format --check scripts/
```

`execsql-format` is also available as a [pre-commit](https://pre-commit.com/) hook:

```yaml
repos:
  - repo: https://github.com/geocoug/execsql
    rev: v2.11.0
    hooks:
      - id: execsql-format
        args: [--in-place]
```

See the [formatter documentation](https://execsql2.readthedocs.io/en/latest/guides/formatter/) for all options.

# VS Code Syntax Highlighting

A VS Code extension for execsql syntax highlighting is included in [`extras/vscode-execsql`](extras/vscode-execsql). It injects a TextMate grammar into `.sql` files, adding highlighting for `-- !x!` metacommand markers, keywords (control flow, block, action, directive), variable substitutions (`!!var!!`, `!{var}!`), built-in functions, export formats, and config options — all layered on top of standard SQL highlighting.

To install, symlink the extension folder into your VS Code extensions directory:

```sh
ln -s /path/to/execsql/extras/vscode-execsql ~/.vscode/extensions/execsql-syntax
```

See the [extension README](extras/vscode-execsql/README.md) for Windows instructions, color customization, and troubleshooting.

# Templates

The `templates/` directory in this repository includes ready-to-use execsql scripts:

- **Upsert scripts** (`pg_upsert.sql`, `md_upsert.sql`, `ss_upsert.sql`): Perform merge/upsert operations on multiple tables simultaneously, respecting foreign key order, for PostgreSQL, MySQL/MariaDB, and SQL Server.
- **Comparison scripts** (`pg_compare.sql`, `md_compare.sql`, `ss_compare.sql`): Compare staging and base tables across multiple dimensions.
- **Glossary scripts** (`pg_glossary.sql`, `md_glossary.sql`, `ss_glossary.sql`): Produce a glossary of column names and definitions to accompany a database export.
- **`script_template.sql`**: A framework for new scripts with sections for configuration, logging, and error reporting.
- **`execsql.conf`**: An annotated configuration file covering all available settings.

# Documentation

Full documentation, including a complete metacommand reference and 30+ examples, is at [execsql2.readthedocs.io](https://execsql2.readthedocs.io/).

# Copyright and License

Copyright (c) 2007-2025 R.Dreas Nielsen
Copyright (c) 2026-present Caleb Grant

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the [GNU General Public License](http://www.gnu.org/licenses/) for more details.
