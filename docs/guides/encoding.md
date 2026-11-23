# Character Encoding { #encoding }

[Command-line options](../getting-started/syntax.md#syntax) and [configuration file](../reference/configuration.md#configuration) settings allow specification of the encoding used in the database, the encoding used to read the script file and imported data files, and the encoding used to write output text. The encoding of data files to be imported can also be specified with the [IMPORT](../reference/metacommands.md#import) metacommand. Database encoding can also be specified with the [CONNECT](../reference/metacommands.md#connect) metacommand. Specification of appropriate encoding will eliminate errors that would otherwise result from the presence of characters in an encoding that is not compatible with the database.

PostgreSQL reads the encoding of an existing database from the server. When creating a database, it accepts a PostgreSQL encoding name. SQLite and DuckDB use the encoding determined by their own adapters.

If no encodings are specified, the following default encodings are used:

> - Script file: utf8
> - Firebird: latin1
> - MySQL and MariaDB: utf8mb4
> - SQL Server: latin1
> - Access: windows_1252
> - DSN: None
> - Output: utf8
> - Import: utf8

If a UTF byte order mark (BOM) is found at the start of the script file or at the start of a data file to be [IMPORTed](../reference/metacommands.md#import), the encoding indicated by the BOM will be taken as definitive regardless of any configuration options that may be used.

There is no default encoding for a DSN connection because the actual data source used is unknown, and because some ODBC drivers may return results in Unicode. If no encoding is specified, the ODBC driver must return result in Unicode or some compatible format (e.g., ASCII).

Use `execsql list encodings` to see the standard-library text codecs and aliases available in the installed Python. Add `--output-format json` for a JSON array. Invalid script, import and output codec names in command-line options or configuration files stop the run before any script statements execute. Database encoding names depend on the backend. For example, MySQL and MariaDB accept `utf8mb4` as a connection charset.

For Excel to recognize UTF-8 when it opens an exported CSV directly, use `--output-encoding utf-8-sig` or set `output = utf-8-sig` under `[encoding]` in `execsql.conf`. The CSV starts with a UTF-8 BOM.

The log file is always written in UTF-8.
