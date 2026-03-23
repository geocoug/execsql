# Installation

*execsql2* is available on [PyPI](https://pypi.org/project/execsql2/).

It can be installed with:

```
pip install execsql2
```

Or with [uv](https://docs.astral.sh/uv/):

```
uv add execsql2
```

This installs the `execsql2` command-line tool.

To install with optional database driver dependencies:

```
pip install "execsql2[postgres]"    # PostgreSQL
pip install "execsql2[mysql]"       # MySQL / MariaDB
pip install "execsql2[duckdb]"      # DuckDB
pip install "execsql2[mssql]"       # MS SQL Server / ODBC
pip install "execsql2[all]"         # All optional drivers
```

In addition to the *execsql* program itself, additional Python libraries may need to be installed to use *execsql* with specific types of DBMSs and spreadsheets. The additional libraries that may be needed are listed in the [Requirements](requirements.md#requirements) section.
