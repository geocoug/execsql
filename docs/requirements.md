# Requirements

*execsql* requires Python 3.10 or later.

*execsql* uses third-party Python libraries to communicate with different database and spreadsheet software. Only those libraries that are needed, based on the database type and [metacommands](metacommands.md#metacommands) in use, must be installed.

The easiest way to install the required libraries is to use the optional dependency extras provided by the `execsql2` package:

```bash
pip install "execsql2[postgres]"    # PostgreSQL
pip install "execsql2[mysql]"       # MySQL / MariaDB
pip install "execsql2[mssql]"       # MS SQL Server (pyodbc)
pip install "execsql2[duckdb]"      # DuckDB
pip install "execsql2[firebird]"    # Firebird
pip install "execsql2[oracle]"      # Oracle
pip install "execsql2[odbc]"        # ODBC DSN (pyodbc)
pip install "execsql2[ods]"         # OpenDocument spreadsheets
pip install "execsql2[excel]"       # Excel read support
pip install "execsql2[jinja]"       # Jinja2 template export
pip install "execsql2[feather]"     # Feather import/export
pip install "execsql2[hdf5]"        # HDF5 export
pip install "execsql2[all]"         # All optional drivers
```

Multiple extras can be combined: `pip install "execsql2[postgres,duckdb,jinja]"`.

## Libraries by Database/Format { #libraries }

The specific libraries installed by each extra are:

| Database / Format                                                  | Extra      | Library                                                                                                 |
| ------------------------------------------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------- |
| PostgreSQL                                                         | `postgres` | [psycopg2-binary](https://pypi.org/project/psycopg2-binary/)                                            |
| MySQL / MariaDB                                                    | `mysql`    | [pymysql](https://pypi.org/project/PyMySQL/)                                                            |
| MS SQL Server                                                      | `mssql`    | [pyodbc](https://pypi.org/project/pyodbc/)                                                              |
| DuckDB                                                             | `duckdb`   | [duckdb](https://pypi.org/project/duckdb/)                                                              |
| Firebird                                                           | `firebird` | [firebird-driver](https://pypi.org/project/firebird-driver/)                                            |
| Oracle                                                             | `oracle`   | [oracledb](https://pypi.org/project/oracledb/)                                                          |
| ODBC DSN                                                           | `odbc`     | [pyodbc](https://pypi.org/project/pyodbc/)                                                              |
| SQLite                                                             | —          | Built-in (`sqlite3` standard library)                                                                   |
| [OpenDocument](http://www.opendocumentformat.org/) spreadsheets    | `ods`      | [odfpy](https://pypi.org/project/odfpy/)                                                                |
| Excel spreadsheets (read only)                                     | `excel`    | [xlrd](https://pypi.org/project/xlrd) (.xls) and [openpyxl](https://pypi.org/project/openpyxl/) (.xlsx) |
| [Jinja2](https://jinja.palletsprojects.com/) templates             | `jinja`    | [Jinja2](https://pypi.org/project/Jinja2/)                                                              |
| [Feather](https://arrow.apache.org/docs/python/feather.html) files | `feather`  | [polars](https://pypi.org/project/polars/)                                                              |
| [HDF5](https://www.hdfgroup.org/solutions/hdf5/) files             | `hdf5`     | [tables](https://pypi.org/project/tables/)                                                              |

Connections to SQLite databases use Python's standard library and require no additional packages.

## Additional System Requirements { #system_requirements }

To use MS Access, SQL Server, or an ODBC DSN, an appropriate ODBC driver must be installed on the system (e.g., the [Microsoft Access Database Engine](https://www.microsoft.com/en-US/download/details.aspx?id=13255) for MS Access, or the [ODBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)).

If data are to be [imported](metacommands.md#import) from the [Parquet](https://parquet.apache.org/) file format, the [pandas](https://pypi.org/project/pandas/) library and either the *pyarrow* or *fastparquet* Python package must be installed.
