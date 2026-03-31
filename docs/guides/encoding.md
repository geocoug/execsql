# Character Encoding

[Command-line options](../getting-started/syntax.md#syntax) and [configuration file](../reference/configuration.md#configuration) settings allow specification of the encoding used in the database, the encoding used to read the script file and imported data files, and the encoding used to write output text. The encoding of data files to be imported can also be specified with the [IMPORT](../reference/metacommands.md#import) metacommand. Database encoding can also be specified with the [CONNECT](../reference/metacommands.md#connect) metacommand. Specification of appropriate encoding will eliminate errors that would otherwise result from the presence of characters in an encoding that is not compatible with the database.

For Postgres and SQLite, the database encoding used is determined by interrogating the database itself, and any database encoding specified on the command line or in a configuration file is ignored.

If no encodings are specified, the following default encodings are used:

> - Script file: utf8
> - Firebird: latin1
> - MySQL and MariaDB: latin1
> - SQL Server: latin1
> - Access: windows_1252
> - DSN: None
> - Output: utf8
> - Import: utf8

If a UTF byte order mark (BOM) is found at the start of the script file or at the start of a data file to be [IMPORTed](../reference/metacommands.md#import), the encoding indicated by the BOM will be taken as definitive regardless of any configuration options that may be used.

There is no default encoding for a DSN connection because the actual data source used is unknown, and because some ODBC drivers may return results in Unicode. If no encoding is specified, the ODBC driver must return result in Unicode or some compatible format (e.g., ASCII).

The "-y" command-line option will display all of the encoding names that execsql recognizes. There are some aliases for the displayed encoding names that can also be used, if you know them. The encoding names used by each DBMS may differ from this list.

The log file is always written in UTF-8.
