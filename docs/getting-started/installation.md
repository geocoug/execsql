# Installation

*execsql2* is available on [PyPI](https://pypi.org/project/execsql2/). The PyPI
distribution is named `execsql2`; the command it installs is `execsql`.

## Install the command

Install it as a tool, in an environment of its own, with
[uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/). Name the
extras for the databases and features you use (see [below](#extras)):

```sh
uv tool install "execsql2[postgres]"
```

```sh
pipx install "execsql2[postgres]"
```

Either one puts `execsql` on your `PATH`; check with `execsql --version`.
SQLite works with no extras: `uv tool install execsql2`.

Quote the package name whenever it has extras. In zsh, the default shell on
macOS, `execsql2[postgres]` without quotes fails with `no matches found`.

### Adding an extra later

Install again with the full list of extras you want. The new list replaces the
old one, so name the ones you already had:

```sh
uv tool install "execsql2[postgres,duckdb]"
pipx install --force "execsql2[postgres,duckdb]"
```

### Upgrading

```sh
uv tool upgrade execsql2
pipx upgrade execsql2
```

## Use it from Python

To call the [library API](../api/index.md#library-api) (`execsql.run(...)`)
from a project, add it as a dependency of that project instead:

```sh
uv add "execsql2[postgres]"
```

or install it into the project's virtual environment with
`pip install "execsql2[postgres]"`. This also provides the `execsql` command
while that environment is active.

## Extras { #extras }

Combine as many as you need in one install: `"execsql2[postgres,duckdb,formats]"`.

| Extra            | Adds                                                                         |
| ---------------- | ---------------------------------------------------------------------------- |
| `postgres`       | PostgreSQL (psycopg)                                                         |
| `mysql`          | MySQL / MariaDB (pymysql)                                                    |
| `duckdb`         | DuckDB                                                                       |
| `mssql`          | MS SQL Server (pyodbc)                                                       |
| `odbc`           | Generic ODBC DSN (pyodbc)                                                    |
| `firebird`       | Firebird                                                                     |
| `oracle`         | Oracle (oracledb)                                                            |
| `formats`        | ODS, Excel, Jinja2, Feather/Parquet, HDF5, YAML                              |
| `formatter`      | SQL reformatting for `execsql format` (sqlglot)                              |
| `lsp`            | `execsql lsp`, the language server for editors (pygls; includes `formatter`) |
| `auth`           | OS keyring integration (desktop/native)                                      |
| `auth-plaintext` | Headless keyring (plaintext file backend)                                    |
| `auth-encrypted` | Headless keyring (encrypted file backend)                                    |
| `upsert`         | `PG_UPSERT` metacommand (pg-upsert)                                          |
| `map`            | `PROMPT MAP` widget (tkintermapview)                                         |
| `all-db`         | All database drivers                                                         |
| `all`            | Everything (all-db + formats + formatter + auth + upsert + map + lsp)        |

Some databases also need software outside Python, such as an ODBC driver or a
client library. These are listed in the [Requirements](requirements.md#requirements) section.

!!! tip "Keyring on headless Linux"

    If you install the `auth` extra on a headless Linux server (no desktop environment), the keyring backend needs manual configuration. See [Keyring Platform Setup](../reference/security.md#keyring_setup) for instructions.
