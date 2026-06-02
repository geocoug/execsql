# Installation

*execsql2* is available on [PyPI](https://pypi.org/project/execsql2/).

It can be installed with:

```sh
pip install execsql2
```

Or with [uv](https://docs.astral.sh/uv/):

```sh
uv add execsql2
```

This installs the `execsql2` command-line tool.

To install with optional dependencies:

```sh
pip install "execsql2[postgres]"          # PostgreSQL
pip install "execsql2[mysql]"             # MySQL / MariaDB
pip install "execsql2[duckdb]"            # DuckDB
pip install "execsql2[mssql]"             # MS SQL Server (pyodbc)
pip install "execsql2[odbc]"              # Generic ODBC DSN (pyodbc)
pip install "execsql2[firebird]"          # Firebird
pip install "execsql2[oracle]"            # Oracle
pip install "execsql2[formats]"           # ODS, Excel, Jinja2, Feather/Parquet, HDF5, YAML
pip install "execsql2[formatter]"         # SQL pass for execsql-format (sqlglot)
pip install "execsql2[auth]"              # OS keyring integration (desktop/native)
pip install "execsql2[auth-plaintext]"    # Headless keyring (plaintext file backend)
pip install "execsql2[auth-encrypted]"    # Headless keyring (encrypted file backend)
pip install "execsql2[upsert]"            # PG_UPSERT metacommand (pg-upsert)
pip install "execsql2[map]"               # PROMPT MAP widget (tkintermapview)
pip install "execsql2[all-db]"            # All database drivers
pip install "execsql2[all]"               # Everything (all-db + formats + formatter + auth + upsert + map)
```

In addition to the *execsql* program itself, additional Python libraries may need to be installed to use *execsql* with specific types of DBMSs and spreadsheets. The additional libraries that may be needed are listed in the [Requirements](requirements.md#requirements) section.

!!! tip "Keyring on headless Linux"

    If you install `execsql2[auth]` on a headless Linux server (no desktop environment), the keyring backend needs manual configuration. See [Keyring Platform Setup](../reference/security.md#keyring_setup) for instructions.
