# Requirements

The execsql program uses third-party [Python](http://www.python.org/) libraries to communicate with different database and spreadsheet software. These libraries must be installed to use those programs with execsql. Only those libraries that are needed, based on the command line arguments and [metacommands](metacommands.md#metacommands) that are used, must be installed. The libraries required for each database or spreadsheet application are:

> - PostgreSQL: [psycopg2](https://pypi.org/project/psycopg2/).
> - MariaDB or MySQL: [pymysql](https://pypi.org/project/PyMySQL/).
> - SQL Server: [pyodbc](https://pypi.org/project/pyodbc/).
> - DuckDB: [duckdb](https://pypi.org/project/duckdb/). Version 0.8.1 or later.
> - MS-Access: [pyodbc](https://pypi.org/project/pyodbc/) and [pywin32](https://pypi.org/project/pywin32/).
> - Firebird: [fdb](https://pypi.org/project/fdb/).
> - Oracle: [cx-Oracle](https://pypi.org/project/cx-Oracle/).
> - DSN data source: [pyodbc](https://pypi.org/project/pyodbc/).
> - [OpenDocument](http://www.opendocumentformat.org/) spreadsheets: [odfpy](https://pypi.org/project/odfpy/).
> - Excel spreadsheets (read only): [xlrd](https://pypi.org/project/xlrd) for .xls files and [openpyxl](https://pypi.org/project/openpyxl/) for .xlsx files.

Connections to SQLite databases are made using Python's standard library, so no additional software is needed.

To use the [Jinja](http://jinja.pocoo.org/) template processor with the [EXPORT](metacommands.md#export) metacommand, the `Jinja2` package must be installed (or install `execsql2[jinja]`).

If data are to be [imported](metacommands.md#import) from the [Parquet](https://parquet.apache.org/) file format, the [pandas](https://pypi.org/project/pandas/) library and either the *pyarrow* or *fastparquet* Python packages must also be installed.

If data are to be [exported](metacommands.md#export) to the feather file format, the [pandas](https://pypi.org/project/pandas/) and [pyarrow](https://pypi.org/project/pyarrow/) Python packages must also be installed.

If data are to be [exported](metacommands.md#export) to the HDF5 file format, the [tables](https://pypi.org/project/tables/) library must be installed.

All of the additional Python packages that may be needed can be installed with [pip](https://pip.pypa.io/en/stable/).

To use MS-Access, SQL Server, or a DSN data source, an appropriate ODBC driver needs to be installed as well (e.g., the [Database Engine 2010 Redistributable](https://www.microsoft.com/en-US/download/details.aspx?id=13255) for MS-Access).
