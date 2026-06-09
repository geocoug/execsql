# Requirements

*execsql* requires Python 3.10 or later.

*execsql* uses third-party Python libraries to communicate with different database and spreadsheet software. Only those libraries that are needed, based on the database type and [metacommands](../reference/metacommands.md#metacommands) in use, must be installed.

The easiest way to install the required libraries is to use the optional dependency extras provided by the `execsql2` package:

```sh
# Database drivers
pip install "execsql2[postgres]"    # PostgreSQL
pip install "execsql2[mysql]"       # MySQL / MariaDB
pip install "execsql2[mssql]"       # MS SQL Server (pyodbc)
pip install "execsql2[duckdb]"      # DuckDB
pip install "execsql2[firebird]"    # Firebird
pip install "execsql2[oracle]"      # Oracle
pip install "execsql2[odbc]"        # ODBC DSN (pyodbc)

# Feature bundles
pip install "execsql2[formats]"     # ODS, Excel, Jinja2, Feather, Parquet, HDF5
pip install "execsql2[formatter]"   # SQL pass for execsql-format (sqlglot)
pip install "execsql2[upsert]"      # PG_UPSERT metacommand (pg-upsert)
pip install "execsql2[map]"         # PROMPT MAP widget (tkintermapview)
pip install "execsql2[auth]"        # OS keyring integration (desktop / native)
pip install "execsql2[auth-plaintext]"  # Headless keyring (plaintext file backend)
pip install "execsql2[auth-encrypted]"  # Headless keyring (encrypted file backend)

# Convenience
pip install "execsql2[all-db]"      # All database drivers
pip install "execsql2[all]"         # Everything (all-db + formats + formatter + auth + upsert + map)
```

Multiple extras can be combined: `pip install "execsql2[postgres,duckdb,formats]"`.

## Libraries by Database/Format { #libraries }

The specific libraries installed by each extra are:

### Database drivers

| Database / Format | Extra      | Library                                                      |
| ----------------- | ---------- | ------------------------------------------------------------ |
| PostgreSQL        | `postgres` | [psycopg2-binary](https://pypi.org/project/psycopg2-binary/) |
| MySQL / MariaDB   | `mysql`    | [pymysql](https://pypi.org/project/PyMySQL/)                 |
| MS SQL Server     | `mssql`    | [pyodbc](https://pypi.org/project/pyodbc/)                   |
| DuckDB            | `duckdb`   | [duckdb](https://pypi.org/project/duckdb/)                   |
| Firebird          | `firebird` | [firebird-driver](https://pypi.org/project/firebird-driver/) |
| Oracle            | `oracle`   | [oracledb](https://pypi.org/project/oracledb/)               |
| ODBC DSN          | `odbc`     | [pyodbc](https://pypi.org/project/pyodbc/)                   |
| SQLite            | —          | Built-in (`sqlite3` standard library)                        |

### `formats` bundle

| Format                                                             | Library                                                                                                 |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| [OpenDocument](http://www.opendocumentformat.org/) spreadsheets    | [odfpy](https://pypi.org/project/odfpy/)                                                                |
| Excel spreadsheets (read only)                                     | [xlrd](https://pypi.org/project/xlrd) (.xls) and [openpyxl](https://pypi.org/project/openpyxl/) (.xlsx) |
| [Jinja2](https://jinja.palletsprojects.com/) templates             | [Jinja2](https://pypi.org/project/Jinja2/)                                                              |
| [Feather](https://arrow.apache.org/docs/python/feather.html) files | [polars](https://pypi.org/project/polars/)                                                              |
| [Parquet](https://parquet.apache.org/) files                       | [polars](https://pypi.org/project/polars/)                                                              |
| [HDF5](https://www.hdfgroup.org/solutions/hdf5/) files             | [tables](https://pypi.org/project/tables/)                                                              |

### `formatter` extra

Required for the SQL-formatting pass of the `execsql-format` CLI. Without this extra, `execsql-format` still normalizes metacommand indentation and keyword casing (use `--no-sql` or import scripts without SQL); the SQL pretty-printing pass calls [sqlglot](https://sqlglot.com/) and raises `ModuleNotFoundError` if it isn't installed.

| Feature                               | Library                                      |
| ------------------------------------- | -------------------------------------------- |
| SQL reformatting via `execsql-format` | [sqlglot](https://pypi.org/project/sqlglot/) |

### `upsert` extra

| Feature                                   | Library                                          |
| ----------------------------------------- | ------------------------------------------------ |
| `PG_UPSERT` PostgreSQL upsert metacommand | [pg-upsert](https://pypi.org/project/pg-upsert/) |

### `map` extra

| Feature                               | Library                                                    |
| ------------------------------------- | ---------------------------------------------------------- |
| `PROMPT MAP` lat/lon selection widget | [tkintermapview](https://pypi.org/project/tkintermapview/) |

### `auth` bundle

| Feature              | Library                                      |
| -------------------- | -------------------------------------------- |
| OS keyring / secrets | [keyring](https://pypi.org/project/keyring/) |

The `auth-plaintext` and `auth-encrypted` variants add a fallback keyring backend for headless Linux: `auth-plaintext` adds [keyrings.alt](https://pypi.org/project/keyrings.alt/) (plaintext file storage — **secrets are not encrypted at rest**), and `auth-encrypted` adds `keyrings.alt` plus [pycryptodome](https://pypi.org/project/pycryptodome/) for an encrypted file backend. See [Keyring Platform Setup](../reference/security.md#keyring_setup).

Connections to SQLite databases use Python's standard library and require no additional packages.

## Additional System Requirements { #system_requirements }

To use MS Access, SQL Server, or an ODBC DSN, an appropriate ODBC driver must be installed on the system (e.g., the [Microsoft Access Database Engine](https://www.microsoft.com/en-US/download/details.aspx?id=13255) for MS Access, or the [ODBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)).

### MS Access on Windows

In addition to the ODBC engine above, the MS Access adapter also needs [pywin32](https://pypi.org/project/pywin32/) to read certain Access-specific value types via the COM bridge. It is not declared in the `[mssql]` or any `execsql2` extra (the package is Windows-only and would noise up non-Windows installs); install it explicitly when you set up the rest of your Access stack:

```sh
pip install "execsql2[mssql]" pywin32
```

### Oracle thin vs thick mode

[oracledb](https://pypi.org/project/oracledb/) defaults to **thin** mode (pure Python, no client libraries required) and works out of the box for most workloads. Switch to **thick** mode by installing the Oracle Instant Client (or a full Oracle client) on the host and calling `oracledb.init_oracle_client()` at startup. Thick mode is required for features the thin driver doesn't implement (Advanced Queuing, some XML features, legacy networking options). See the [oracledb docs](https://python-oracledb.readthedocs.io/en/latest/user_guide/initialization.html) for the full feature matrix.

### Firebird client library

[firebird-driver](https://pypi.org/project/firebird-driver/) is the Python bindings; the actual Firebird C client library (`fbclient.dll` on Windows, `libfbclient.so` on Linux, `libfbclient.dylib` on macOS) is loaded at runtime. Install it via your Firebird server distribution or the standalone [Firebird ODBC / client packages](https://firebirdsql.org/en/firebird-client-installer/), and make sure it's on the OS loader path (`PATH` on Windows, `LD_LIBRARY_PATH` on Linux, `DYLD_LIBRARY_PATH` on macOS) before invoking execsql.
