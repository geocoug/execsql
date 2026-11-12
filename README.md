> [!NOTE]
> ***execsql2* is a maintained fork of [execsql](https://execsql.readthedocs.io/)**, originally authored by R.Dreas Nielsen and no longer actively maintained upstream. The monolith has been refactored into a modular package with deliberate [CLI, configuration and script-behavior changes](https://execsql2.readthedocs.io/en/stable/about/divergence/); review them when migrating from upstream. Maintained by [Caleb Grant](https://github.com/geocoug) and distributed on PyPI as [`execsql2`](https://pypi.org/project/execsql2/). Report issues at [github.com/geocoug/execsql/issues](https://github.com/geocoug/execsql/issues).

<div align="center">

<img src="https://execsql2.readthedocs.io/en/stable/images/execsql_logo_01.png" alt="execsql logo">

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

## Overview

*execsql* is a toolchain for SQL scripts: **write** them with editor support, **format** them consistently, **lint** them without a database, and **run** them against nine DBMSs.

Scripts are ordinary SQL plus metacommands embedded in comments (`-- !x!`), which add importing and exporting data, copying between databases, conditional execution, looping, substitution variables, and interactive prompts. Other SQL tools (`psql`, `sqlcmd`, your editor) ignore the metacommand comments. Scripts that depend on those commands or on variable substitution need execsql to perform their intended work.

| Command                                    | What it does                                                                                                                                                          | Needs a database? |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| `execsql format`                           | Normalize keywords, indentation, and SQL layout                                                                                                                       | No                |
| `execsql lint`                             | Static analysis: structure, unknown metacommands, variables, targets                                                                                                  | No                |
| `execsql run`                              | Run the script against PostgreSQL, MySQL, SQLite, DuckDB, …                                                                                                           | Yes               |
| `execsql config`                           | Show every config option, its value, and the file that set it                                                                                                         | No                |
| `execsql list`                             | Reference lists, or database metadata with `list schema`                                                                                                              | Only `schema`     |
| `execsql init`                             | Set up a project: config file, a script with a header, pre-commit hooks                                                                                               | No                |
| `execsql lsp`                              | [Language server](https://execsql2.readthedocs.io/en/stable/guides/editors/): lint findings, completion, hover, navigation, quick fixes and formatting in your editor | No                |
| [VS Code extension](extras/vscode-execsql) | Highlighting plus everything `execsql lsp` provides                                                                                                                   | No                |

`format` and `lint` take files or directories.

> [!WARNING]
> The original positional form, `execsql script.sql myserver mydb`, still works
> but is deprecated: it prints a warning and stops working in execsql2 3.0. Use
> `execsql run script.sql myserver mydb`.

## Quick start: no database required

`format` and `lint` work on a bare `.sql` file, with no server and no config. Try them first:

```bash
uv tool install "execsql2[formatter]"     # or: pipx install "execsql2[formatter]"

execsql format --check scripts/   # is it formatted?
execsql format -i scripts/        # format it
execsql lint scripts/             # find problems before they cost you a run
```

`lint` reports unmatched blocks, misspelled or malformed metacommands and conditions, undefined and unused substitution variables, unreachable branches, and `INCLUDE`/`SCRIPT` targets that do not exist: the failures that otherwise surface halfway through a run against a live database:

```text
$ execsql lint load_data.sql
load_data.sql
  1  warning  V002  variable !!site_cd!! is never used
  2  warning  I001  INCLUDE file does not exist: common/setup.sql
  3  warning  V001  undefined variable !!site_code!!

Found 3 issues in 1 file: 3 warnings (1 file checked)
```

`V002` and `V001` together point at a typo: `site_cd` is defined and `site_code` is used. Every issue has a rule code for `--select` and `--ignore`; `--output-format concise` prints one `path:line` line per issue and `json` feeds CI tools. The [lint rules](https://execsql2.readthedocs.io/en/stable/reference/lint/) page explains each one.

`execsql format` also runs as a [pre-commit hook](#formatting-scripts), so formatting is enforced without anyone remembering to run it.

## Example

This complete SQLite example needs no server, GUI or extras. Save as `hello.sql`:

```sql
create table sales (product text, quantity integer);
insert into sales values ('book', 2), ('book', 3), ('pen', 4);
-- !x! ASSERT ROW_COUNT_EQ(sales, 3) "Expected three input rows"
-- !x! EXPORT QUERY <<select product, sum(quantity) as quantity from sales group by product order by product;>> TO totals.csv AS CSV
```

```sh
execsql run --dsn sqlite:///:memory: hello.sql
```

It creates `totals.csv` with `book,5` and `pen,4` beneath a header, and writes `execsql.log`. The database is in memory; each run replaces the CSV. [Your first script](https://execsql2.readthedocs.io/en/stable/getting-started/first-script/) extends this into a CSV import/export workflow with expected output.

## Installation

```bash
uv tool install execsql2                  # core: SQLite works with no extras
uv tool install "execsql2[postgres]"      # with a driver: postgres, mysql, mssql, duckdb, firebird, oracle, odbc
uv tool install "execsql2[all]"           # everything: all drivers plus all feature extras
```

`pipx install` takes the same arguments. Quote the name when it has extras
(zsh reports `no matches found` otherwise). To call execsql from Python code,
add it to that project instead: `uv add "execsql2[postgres]"` or
`pip install "execsql2[postgres]"` in its virtual environment.

Feature extras cover spreadsheet and Parquet/Feather formats, keyring authentication, PostgreSQL upsert, and more. See the [installation guide](https://execsql2.readthedocs.io/en/stable/getting-started/installation/) for the full list.

## Usage

```text
execsql run    [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
execsql format [--check | -i] [--indent N] FILE_OR_DIR...
execsql lint   [OPTIONS] FILE_OR_DIR...
execsql config [SQL_SCRIPT] [--init] [--config FILE]
execsql list   metacommands|encodings|plugins|keywords
execsql list schema --dsn URL [--schema NAME] [--table NAME]
execsql init   [DIR] [--script NAME] [--no-script] [--no-config] [--no-pre-commit]
execsql lsp    [--check] [--log-level LEVEL] [--log-file PATH]
```

Examples:

```bash
execsql run -tp script.sql myserver mydb        # PostgreSQL
execsql run -tm script.sql myserver mydb        # MySQL / MariaDB
execsql run -ts script.sql myserver mydb        # SQL Server
execsql run -tl script.sql mydb.sqlite          # SQLite
execsql run -tk script.sql mydb.duckdb          # DuckDB
execsql run -to script.sql myserver myservice   # Oracle
execsql run script.sql                          # read connection from config file
```

### Supported Databases

| Flag | Database        | Support                                         |
| ---- | --------------- | ----------------------------------------------- |
| `p`  | PostgreSQL      | Supported: verified against a live server in CI |
| `m`  | MySQL / MariaDB | Supported: verified against a live server in CI |
| `s`  | MS SQL Server   | Supported: verified against a live server in CI |
| `l`  | SQLite          | Supported: verified against real files in CI    |
| `k`  | DuckDB          | Supported: verified against real files in CI    |
| `a`  | MS Access       | Best effort: conditional Windows CI checks      |
| `f`  | Firebird        | Best effort: not verified in CI                 |
| `o`  | Oracle          | Best effort: not verified in CI                 |
| `d`  | ODBC DSN        | Best effort: not verified in CI                 |

**Supported** adapters have required real-database checks in CI. Access remains **best effort**: its Windows checks run when the engine installs and do not gate release builds. Firebird, Oracle and ODBC DSN have no required real-driver CI coverage. See the [support table](https://execsql2.readthedocs.io/en/stable/getting-started/requirements/#support-tiers) for requirements and the notice setting.

### Common options

| Flag                                              | Description                                                                |
| ------------------------------------------------- | -------------------------------------------------------------------------- |
| `-t {p,m,s,l,k,a,f,o,d}`                          | Database type                                                              |
| `-u USER`                                         | Database username                                                          |
| `-p PORT`                                         | Server port                                                                |
| `--dsn URL`                                       | Connection string (e.g. `postgresql://user:pass@host/db`)                  |
| `-n`                                              | Create a new SQLite, DuckDB or PostgreSQL database if it does not exist    |
| `-c SCRIPT`                                       | Execute inline SQL or metacommand string                                   |
| `-a VALUE`                                        | Set substitution variable `$ARG_x`                                         |
| `--var NAME=VALUE`                                | Set the substitution variable `!!NAME!!`                                   |
| `-v {0,1,2,3}`                                    | GUI level (0=none, 1=password/PAUSE, 2=+HALT and DB selection, 3=console)  |
| `--config FILE`                                   | Load an explicit config file                                               |
| `--dry-run`                                       | Parse the script and report commands without executing                     |
| `--manifest FILE`                                 | Write a JSON record of the run: files read and written, statements, errors |
| `--debug`                                         | Start in step-through debug mode (REPL pauses before each stmt)            |
| `--no-system-cmd` / `--no-rm-file` / `--no-serve` | Disable the `SYSTEM_CMD` / `RM_FILE` / `SERVE` metacommands                |

See the [full options reference](https://execsql2.readthedocs.io/en/stable/getting-started/syntax/#options) or run `execsql run --help` for the complete list, `execsql run --ping` to test a connection, `execsql config` to see which config files set what, and `execsql list metacommands` for all metacommands.

## Features

**Data movement**

- Import data from CSV, TSV, JSON, Excel, OpenDocument, Feather, or Parquet files into a database table.
- Export query results in 20+ formats including CSV, TSV, JSON, JSON Lines, YAML, XML, HTML, Markdown, LaTeX, XLSX, OpenDocument, Feather, Parquet, HDF5, DuckDB, SQLite, plain text, and Jinja2 templates.
- Copy data between databases, including across different DBMS types.

**Script logic**

- Conditionally execute SQL and metacommands using `IF`/`ELSE`/`ENDIF` based on data values, DBMS type, or user input.
- Loop over blocks of SQL and metacommands using `LOOP`/`ENDLOOP`; include or chain scripts with `INCLUDE` and `SCRIPT`.
- Use substitution variables (`SUB`, `$ARG_x`, built-in variables like `$date_tag`) to parameterize scripts.
- Validate data with `ASSERT`: halt the script with a clear error message if a condition is false (ideal for CI pipelines).

**Interaction & observability**

- Display query results in a GUI dialog; optionally prompt the user to select a row, enter a value, or submit a form.
- Write status messages or tabular output to the console or a file during execution.
- Automatically log each run, recording databases used, scripts executed, and user responses.

**Extensibility**

- Extend with custom metacommands, exporters, and importers via the plugin system.

## Library API

Install `execsql2` in your Python project, then call `run`:

```python
from execsql import run

result = run(
    sql="CREATE TABLE t (id INTEGER);\nINSERT INTO t VALUES (1);",
    dsn="sqlite:///:memory:",
)
result.raise_on_error()
print(result.success)  # True
```

The [Python API guide](https://execsql2.readthedocs.io/en/stable/api/) covers script files, variables, supplied connections, result/error handling and setup exceptions. Each call uses its own runtime context; the caller manages a supplied connection's lifetime.

## Formatting Scripts

The `execsql format` command normalizes execsql script files: it uppercases metacommand keywords, corrects block indentation, and optionally reformats SQL via `sqlglot`. The metacommand / indent / keyword reformatting is built into `execsql2`; SQL reformatting requires the `[formatter]` extra (or pass `--no-sql` to skip it):

```bash
# Install with the SQL-reformatting extra
uv tool install "execsql2[formatter]"

# Format files in place
execsql format --in-place scripts/

# Check formatting without writing (useful in CI)
execsql format --check scripts/

# Run the formatter without sqlglot: keyword/indent normalization only
execsql format --no-sql --in-place scripts/
```

`execsql format` and `execsql lint` are also available as [pre-commit](https://pre-commit.com/) hooks. The format hook id is unchanged, so existing configs keep working:

```yaml
repos:
  - repo: https://github.com/geocoug/execsql
    rev: v2.40.0
    hooks:
      - id: execsql-format
      - id: execsql-lint
```

The format hook rewrites `*.sql` files in place by default; the lint hook fails the commit when a script has a lint error. See the [formatter documentation](https://execsql2.readthedocs.io/en/stable/guides/formatter/) for `--check`, `--indent`, and other options.

## VS Code

Install the language server, then download the extension separately:

```sh
uv tool install "execsql2[lsp]"
execsql lsp --check
curl -fL --output execsql-syntax.vsix \
  https://github.com/geocoug/execsql/releases/latest/download/execsql-syntax.vsix
code --install-extension ./execsql-syntax.vsix
```

Run the download and install commands in the same directory. The last command reads a local file; it fails with `ENOENT` if the file is missing. Alternatively, download the VSIX from the [current release](https://github.com/geocoug/execsql/releases/latest), then use VS Code's **Extensions → … → Install from VSIX…**.

If you use other extras, retain them in the install command, for example `"execsql2[postgres,lsp]"`. See [VS Code setup and troubleshooting](https://execsql2.readthedocs.io/en/stable/guides/editors/vscode/) or [other editor setup](https://execsql2.readthedocs.io/en/stable/guides/editors/).

## Schema discovery

Inspect a table without running a script or reading its rows:

```sh
execsql list schema --dsn sqlite:///project.sqlite --schema main --table samples
```

Python callers can use `execsql.inspect_schema()` with a connection URL or an
existing execsql adapter. See [schema discovery](https://execsql2.readthedocs.io/en/stable/reference/schema/)
for the versioned JSON contract and adapter coverage.

## Templates

The `templates/` directory in this repository includes ready-to-use execsql scripts, tested against live databases in CI; see the [Templates documentation](https://execsql2.readthedocs.io/en/stable/templates/). (`execsql config --init` writes an annotated configuration file.)

- **Upsert scripts** (`md_upsert.sql`, `ss_upsert.sql`): Perform merge/upsert operations on multiple tables simultaneously, respecting foreign key order, for MySQL/MariaDB and SQL Server. On PostgreSQL, use the [`PG_UPSERT`](https://execsql2.readthedocs.io/en/stable/reference/metacommands/#pg_upsert) metacommand.
- **Comparison scripts** (`pg_compare.sql`, `md_compare.sql`, `ss_compare.sql`): Compare staging and base tables across multiple dimensions.
- **Glossary scripts** (`pg_glossary.sql`, `md_glossary.sql`, `ss_glossary.sql`): Produce a glossary of column names and definitions to accompany a database export.
- **`script_template.sql`**: A framework for new scripts with sections for configuration, logging, and error reporting.

## Documentation

Full documentation, including a complete metacommand reference and examples grouped by task, is at [execsql2.readthedocs.io](https://execsql2.readthedocs.io/). Development priorities and proposed features are in the [roadmap](https://github.com/geocoug/execsql/blob/main/ROADMAP.md).

## Copyright and License

Copyright (c) 2007-2025 R.Dreas Nielsen

Copyright (c) 2026-present Caleb Grant

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the [GNU General Public License](http://www.gnu.org/licenses/) for more details.
