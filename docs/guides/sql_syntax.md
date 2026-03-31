# SQL Syntax Notes

## ANSI Compatibility

When execsql connects to a SQL Server or MySQL/MariaDB database, it automatically configures the DBMS to expect ANSI-compatible SQL, to allow the use of more standards-compliant, and thus consistent, SQL. In particular, for MySQL/MariaDB, note that the double-quote character, rather than the backtick character, must be used to quote table, schema, and column names, and only the apostrophe can be used to quote character data.

## Implicit Commits

By default, execsql immediately commits all SQL statements. The [AUTOCOMMIT](../reference/metacommands.md#autocommit) metacommand can be used to turn off automatic commits, and the [BATCH](../reference/metacommands.md#batch) metacommand can be used to delay commits until the end of a batch. [IMPORT](../reference/metacommands.md#import) and [COPY](../reference/metacommands.md#copy) are the only metacommands that change data, and they also automatically commit their changes when complete (unless [AUTOCOMMIT](../reference/metacommands.md#autocommit) has been turned off). If a new table is created with either of these metacommands (through the use of the NEW or REPLACEMENT keywords), the CREATE TABLE statement will not be committed separately from the data addition, except when using Firebird. Thus, if an error occurs during addition of the data, the new target table will not exist---except when using Firebird.

When adding a very large amount of data with the [IMPORT](../reference/metacommands.md#import) or [COPY](../reference/metacommands.md#copy) metacommands, internal transaction limits may be exceeded for some DBMSs. For example, MS-Access may produce a 'file sharing lock count exceeded' error when large data sets are loaded.

## Implicit DROP TABLE Statements

The "REPLACEMENT" keyword for the [IMPORT](../reference/metacommands.md#import) and [COPY](../reference/metacommands.md#copy) metacommands allows a previously existing table to be replaced. To accomplish this, execsql issues a "DROP TABLE" statement to the database in use. PostgreSQL, SQLite, MySQL, MariaDB, and Oracle support a form of the "DROP TABLE" statement that automatically removes all foreign keys to the named table. execsql uses these forms of the "DROP TABLE" statement for these DBMSs, and therefore use of the "REPLACEMENT" keyword always succeeds at removing the named table before trying to create a new table with the same name. SQL Server, MS-Access, and Firebird do not have a form of the "DROP TABLE" statement that automatically removes foreign keys. Therefore, if the "REPLACEMENT" keyword is used with any of these three DBMSs, for a table that has foreign keys into it, that table will not be dropped, and an error will subsequently occur when execsql issues a "CREATE TABLE" statement to create a new table of the same name. To avoid this, when using any of these three DBMSs, you should include in the script the appropriate SQL commands to remove foreign keys (and possibly even to remove the table) before using the IMPORT or COPY metacommands.

## Boolean Data Types

Not all DBMSs have explicit support for a boolean data type. When execsql creates a new table as a result of the NEW or REPLACEMENT keyword in [IMPORT](../reference/metacommands.md#import) and [COPY](../reference/metacommands.md#copy) metacommands, it uses the following data type for boolean values in each DBMS:

> - Postgres: boolean.
> - SQLite: integer. *True* values are converted to 1, and *False* values are converted to 0.
> - Access: integer. Although Access supports a "bit" data type, bit values are non-nullable, and so to preserve null boolean values, execsql uses the integer type instead. *True* values are converted to 1, and *False* values are converted to 0.
> - SQL Server: bit.
> - MySQL and MariaDB: boolean
> - Firebird: integer. *True* values are converted to 1, and *False* values are converted to 0.
> - Oracle: integer. *True* values are converted to 1, and *False* values are converted to 0.

If boolean values are imported to some other data type in an existing table, the conversion to that data type may or may not be successful.

When scanning input data to determine data types, execsql will consider a column to contain boolean values if it contains only values of 0, 1, '0', '1', 'true', 'false', 't', 'f', 'yes', 'no', 'y', or 'n'. Character matching is case-insensitive. This behavior can be altered with the `boolean_int` and `boolean_words` [configuration
settings](../reference/configuration.md#config_input) or with the [CONFIG BOOLEAN_INT](../reference/metacommands.md#boolean_int) and [CONFIG BOOLEAN_WORDS](../reference/metacommands.md#boolean_words) metacommands.

## Schemas, the IMPORT and COPY Metacommands, and Schema-less DBMSs

If a schema name is used with the table specifications for the [IMPORT](../reference/metacommands.md#import) or [COPY](../reference/metacommands.md#copy) metacommands, when the command is run against either MS-Access or SQLite, the schema name will be ignored. No error or warning message will be issued. Such irrelevant schema specifications are ignored to reduce the need to customize scripts for use with different DBMSs.

## MS-Access Quirks

The version of SQL that is used by the Jet engine when accessed via DAO or ODBC, and thus that must be used in the script files executed with execsql, is generally equivalent to that used within Access itself, but is not identical, and is also not the same in all respects as standard SQL. There are also differences in the SQL syntax accepted by the DAO and ODBC interfaces. To help avoid inconsistencies and errors, here are a few points to keep in mind when creating SQL scripts for use with Access:

> - The Jet engine can fail to correctly parse multi-table JOIN expressions. In these cases you will need to give it some help by parenthesizing parts of the JOIN expression. This means that you have some responsibility for constructing optimized (or at least acceptably good) SQL.
>
> - Not all functions that you can use in Access are available via DAO or ODBC. Sometimes these can be worked around with slightly lengthier code. For example, the `Nz()` function is not available in an ODBC connection, but it can be replaced with an expression such as `If([Column] is null, 0, [Column])`. The list of ODBC functions that can be used is listed here: <https://msdn.microsoft.com/en-us/library/office/ff835353.aspx>. When creating (temporary) queries---i.e., when using DAO---the functions available are equivalent to those available in Access' GUI interface. A partial list of the differences between Access and ANSI SQL is here: <https://msdn.microsoft.com/en-us/library/bb208890%28v=office.12%29.aspx>
>
> - The reserved words recognized by the ODBC connection are different than the reserved words recognized by Access' user interface. SQL statements that execute successfully in the user interface may fail when run using execsql if they contain an ODBC reserved word.
>
> - Literal string values in SQL statements should be enclosed in single quotes, not double quotes. Although Access allows double quotes to be used, the ANSI SQL standard and the connector libraries used for execsql require that single quotes be used.
>
> - Square brackets must be used around column names that contain embedded spaces when a temporary query is being used (i.e., DAO is used). At all other times, double quotes will work.
>
> - Expressions that should produce a floating-point result ('Double') sometimes do not, with the output being truncated or rounded to an integer. A workaround is to multiply and then divide the expression by the same floating-point number; for example: '1.00000001 * \<expression> / 1.00000001'.
>
> - The wildcard character to use with the LIKE expression, in a `CREATE [TEMPORARY] QUERY` statement, differs under different circumstances:
>
>     > - "\*" must be used in action queries (UPDATE, INSERT, DELETE).
>     > - "\*" must be used in simple SELECT queries.
>     > - "%" must be used in subqueries of SELECT queries.
>
>     These differences are due to the different syntaxes supported by the ODBC and DAO connections, and circumstances (such a subqueries) in which the text of a saved query is recompiled by the ODBC driver. When you are not creating a (temporary) query, "%" should always be used as the wildcard. In particular, avoid creating a query that will be used both directly and as a subquery in another query--this situation is very likely to result in errors. *Because of the potentially adverse consequences of improper interpretation of wildcards with Access databases, you should always test such statements very carefully.*
