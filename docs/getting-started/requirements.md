# Requirements

*execsql* requires Python 3.10 or later.

*execsql* uses third-party Python libraries to communicate with different database and spreadsheet software. Only those libraries that are needed, based on the database type and [metacommands](../reference/metacommands.md#metacommands) in use, must be installed.

The easiest way to install the required libraries is to name the matching [extras](installation.md#extras) when installing `execsql2`, for example `uv tool install "execsql2[postgres,duckdb,formats]"`. The [Installation](installation.md#installation) page lists every extra and how to add one to an existing install.

## Libraries by Database/Format { #libraries }

The specific libraries installed by each extra are:

### Database support tiers { #support-tiers }

execsql2 ships nine DBMS adapters, but they are not all verified to the same
standard. The tier tells you which ones have actually been run.

| Tier            | Databases                                                | What it means                                                                                                                                                                                       |
| --------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Supported**   | PostgreSQL, MySQL/MariaDB, MS SQL Server, SQLite, DuckDB | Exercised against a live server (or a real database file) on every CI run. A regression blocks the release, and bugs are fixed.                                                                     |
| **Best effort** | MS Access, Firebird, Oracle, ODBC DSN                    | Carried forward from the upstream monolith and not exercised in CI. The code is present and may work; nothing proves it still does. Issues and pull requests are welcome, but no guarantee is made. |

Opening a best-effort connection writes one informational line to stderr, once
per DBMS per run:

```
Note: Firebird support is best-effort — it is not verified in CI and may break.
Set support_tier_notice=No in the [interface] section of execsql.conf to silence this.
```

It goes to stderr rather than stdout, so it cannot corrupt piped query output.
To turn it off, set [`support_tier_notice`](../reference/configuration.md#support_tier_notice)
to `No`.

No adapter is deprecated or scheduled for removal. The tiers describe what is
verified, not what is wanted — a best-effort adapter moves up when it gains
tests that run against something real.

### Database drivers

| Database / Format | Extra      | Library                                                         |
| ----------------- | ---------- | --------------------------------------------------------------- |
| PostgreSQL        | `postgres` | [psycopg[binary]](https://pypi.org/project/psycopg/) (psycopg3) |
| MySQL / MariaDB   | `mysql`    | [pymysql](https://pypi.org/project/PyMySQL/)                    |
| MS SQL Server     | `mssql`    | [pyodbc](https://pypi.org/project/pyodbc/)                      |
| DuckDB            | `duckdb`   | [duckdb](https://pypi.org/project/duckdb/)                      |
| Firebird          | `firebird` | [firebird-driver](https://pypi.org/project/firebird-driver/)    |
| Oracle            | `oracle`   | [oracledb](https://pypi.org/project/oracledb/)                  |
| ODBC DSN          | `odbc`     | [pyodbc](https://pypi.org/project/pyodbc/)                      |
| SQLite            | —          | Built-in (`sqlite3` standard library)                           |

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

Required for the SQL-formatting pass of `execsql format`. Without this extra, `execsql format` still normalizes metacommand indentation and keyword casing (use `--no-sql` or import scripts without SQL); the SQL pretty-printing pass calls [sqlglot](https://sqlglot.com/) and raises `ModuleNotFoundError` if it isn't installed.

| Feature                               | Library                                      |
| ------------------------------------- | -------------------------------------------- |
| SQL reformatting via `execsql format` | [sqlglot](https://pypi.org/project/sqlglot/) |

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
uv tool install "execsql2[mssql]" --with pywin32
pipx install "execsql2[mssql]" --preinstall pywin32
```

### Oracle thin vs thick mode

[oracledb](https://pypi.org/project/oracledb/) defaults to **thin** mode (pure Python, no client libraries required) and works out of the box for most workloads. Switch to **thick** mode by installing the Oracle Instant Client (or a full Oracle client) on the host and calling `oracledb.init_oracle_client()` at startup. Thick mode is required for features the thin driver doesn't implement (Advanced Queuing, some XML features, legacy networking options). See the [oracledb docs](https://python-oracledb.readthedocs.io/en/latest/user_guide/initialization.html) for the full feature matrix.

### Firebird client library

[firebird-driver](https://pypi.org/project/firebird-driver/) is the Python bindings; the actual Firebird C client library (`fbclient.dll` on Windows, `libfbclient.so` on Linux, `libfbclient.dylib` on macOS) is loaded at runtime. Install it via your Firebird server distribution or the standalone [Firebird ODBC / client packages](https://firebirdsql.org/en/firebird-client-installer/), and make sure it's on the OS loader path (`PATH` on Windows, `LD_LIBRARY_PATH` on Linux, `DYLD_LIBRARY_PATH` on macOS) before invoking execsql.
