# Usage Notes { #usage }

## Required Arguments

Use `execsql run SCRIPT.sql` or `execsql run -c "SQL or metacommand text"`. Connection information can come from [configuration files](../reference/configuration.md#configuration), a DSN or positional connection arguments. `execsql --help` lists all seven subcommands; invoking execsql without arguments prints usage and exits with status 2.

<a id="continuationchars"></a>

## SQL Statement Recognition

*execsql* recognizes a SQL statement as consisting of a sequence of non-comment lines that ends with a line ending with a semicolon. A backslash ("\\") at the end of a line is treated as a line continuation character. Backslashes do not need to be used for simple SQL statements, but can be used for procedure and function definitions, where there are semicolons within the body of the definition, and a semicolon appears at the end of lines for readability purposes. The [BEGIN SQL](../reference/metacommands.md#beginsql) and [END SQL](../reference/metacommands.md#beginsql) metacommands can be used to bracket procedure and function definitions instead of using backslashes. Backslashes may not be used as continuation characters for [metacommands](../reference/metacommands.md#metacommands).

With the exception of the "CREATE TEMPORARY QUERY..." statement when used with MS-Access, the *execsql* program does not parse or interpret SQL syntax in any way.

SQL syntax used in the script must conform to that recognized by the DBMS engine in use. Because *execsql* can connect to several different DBMSs simultaneously, a single script can contain a mixture of different SQL syntaxes. To minimize this variation (and possible mistakes that could result), *execsql* metacommands provide some common features of DBMS-specific scripting languages (e.g., pgScript and T-SQL), and *execsql* turns on ANSI-compatible mode for SQL Server and MySQL when it connects to those databases.

## Comments in SQL Scripts

Script files can contain single-line comments, which are identified by two dashes ("`--`") at the start of a line. Script files can also contain multi-line comments, which begin on a line where the first characters are "`/*`" and end on a line where the last characters are "`*/`".

*execsql* strips single-line and multi-line comments from the script file when compiling SQL statements to send to the DBMS. *execsql* does not strip comments that follow part of a SQL statement on the same line, such as:

```sql
select
    scramble(eggs)      -- Use custom aggregate function
from
    refrigerator join stove using (kitchen);
```

The DBMS in use must be able to recognize and ignore any such comments. If any such comment occurs on the last line of the SQL statement, following the semicolon, then *execsql* will not recognize the end of the SQL statement, and an error will result.

## Metacommands

[Metacommands](../reference/metacommands.md#metacommands) are directives to *execsql* that can control script processing, import and export data, report status information, and perform other functions. Metacommands are embedded in single-line SQL comments. These metacommands are identified by the token "`!x!`" immediately following the SQL comment characters at the beginning of a line, i.e.:

```sql
-- !x! <metacommand>
```

The special commands that are available are described in the [Metacommands](../reference/metacommands.md#metacommands) section.

## Autocommit

SQL statements normally commit after each successful execution. [AUTOCOMMIT OFF](../reference/metacommands.md#autocommit) leaves transaction completion to the script. [BEGIN BATCH](../reference/metacommands.md#batch) holds eligible statements until `END BATCH`, which commits only if the batch and its enclosing batches have not failed.

SQL and metacommands using the same connection can see that connection's pending changes. For example, `ASSERT HASROWS(t)` can check an INSERT inside a batch before commit. Other connections follow the DBMS's transaction isolation rules.

Read the canonical [batch rules](../reference/metacommands.md#batch) before choosing a boundary. They cover failed statements, early exits, DDL support, `AUTOCOMMIT OFF` and metacommands that commit independently. A batch across connections is not an atomic distributed transaction.

## Rollback on Exit

When *execsql* exits, or closes a database connection because the same alias will be used again in a [CONNECT](../reference/metacommands.md#connect) metacommand, a rollback command will be sent to the database immediately before each connection is closed. Therefore if, for example, a [PROMPT DISPLAY](../reference/metacommands.md#prompt) metacommand is used within a transaction, and the user cancels the display, and thus the script, a rollback command will be sent to the database, thereby terminating the transaction. This prevents transactions from being left open and incomplete, which may cause problems in some circumstances.

## Exit Status

See the [CLI exit-status reference](../getting-started/syntax.md#exit_codes) for the common tool statuses and `run`'s additional HALT, cancellation and signal statuses. A nonzero status does not always mean bad command-line syntax.

## Performance

Data import, export, display, and logging all affect the run time of an *execsql* script. Performance of several of these operations can be affected by configuration settings and metacommand usage.

### Importing Data

`IMPORT` / `COPY` scan input to choose types for NEW/REPLACEMENT tables. Existing targets convert values using the target column types; text columns retain the source text, and fractional values cannot enter integer columns. Choosing the target schema explicitly is useful when input inference would not express the desired types. It does not bypass value validation or necessarily avoid scanning the source.

PostgreSQL and MySQL/MariaDB can use file-loading paths for eligible delimited imports: `COPY FROM STDIN` on PostgreSQL and `LOAD DATA LOCAL INFILE` on MySQL/MariaDB. These paths require the file columns to match the target columns in order, `EMPTY_STRINGS` and `EMPTY_ROWS` enabled, and `DELETE_EMPTY_COLUMNS`, `CREATE_COLUMN_HEADERS`, `TRIM_STRINGS` and `REPLACE_NEWLINES` disabled. Neither accepts a detected escape character on its fast path. PostgreSQL additionally requires a detected/configured quote character and matching input/database encodings. Otherwise the adapter uses its row insertion path.

`EMPTY_STRINGS NO` disables these file-loading paths, which can help diagnose a driver or server incompatibility. It also changes how empty fields are interpreted. Choose null/empty-row and text-cleaning settings for the input's meaning, rather than changing stored values merely to pursue a faster path. The row buffer setting does not control a server's native file loader.

Changing the size of the import row buffer, using either the appropriate [metacommand](../reference/metacommands.md#config_import_row_buffer) or [configuration setting](../reference/configuration.md#setting_import_row_buffer) may affect the performance of data imports.

### Exporting Data

Changing the size of the row buffer used for data export, using either the appropriate [metacommand](../reference/metacommands.md#config_export_row_buffer) or [configuration setting](../reference/configuration.md#setting_export_row_buffer) may affect the performance of data exports. A larger buffer size may be appropriate for large data sets.

### Logging of Data Variables

*execsql* will always create or update a [record of operations that have been carried out](logging.md#logging). That log ordinarily includes all assignments to [data variables](../reference/substitution_vars.md#data_vars). However, some scripts may make extensive use of data variables, and logging of large numbers of data variable assignments can reduce a script's performance. Therefore, logging of data variables can be turned off with either a [metacommand](../reference/metacommands.md#logdatavars) or a [configuration setting](../reference/configuration.md#conf_log_datavars).

## DSN Connections

When a DSN is used as a data source, *execsql* has no information about the features or SQL syntax used by the underlying DBMS. In the expectation that a DSN connection will most commonly be used for Access databases, a DSN connection will use Access' syntax when issuing a CREATE TABLE statement in response to a COPY or IMPORT metacommand. However, a DSN connection does not (and cannot) use DAO to manage queries in a target Access database, so all data manipulations must be carried out using SQL statements. The EXECUTE metacommand uses the same approach for DSN connections as is used for SQL Server.

## PostgreSQL-Compatible Databases

A server that accepts PostgreSQL connections is not necessarily compatible with every PostgreSQL SQL statement, catalog query or transaction behavior used by execsql. Such servers have no independent support tier or live CI coverage here. Test the particular scripts and adapter operations you need against a disposable database; use the [database support table](../getting-started/requirements.md#support-tiers) for the backends actually verified by this project.

## SCRIPTs and CURRENT_SCRIPT System Variables

If any of the $CURRENT_SCRIPT system variables are used in a sub-script that is defined with the [BEGIN SCRIPT](../reference/metacommands.md#beginscript) metacommand, the script name, path, and line number that is contained in those variables refers to the script containing the BEGIN SCRIPT metacommand, not the script containing the [EXECUTE SCRIPT](../reference/metacommands.md#executescript) metacommand.

## Editor Customization

Editor setup has moved to [Editors](editors.md). The [Geany and Vim instructions](editors/other-editors.md#geany-and-vim) retain the build-command and highlighting examples.

<a id="running-execsql-from-within-the-geany-editor"></a>

[Running execsql from Geany](editors/other-editors.md#running-execsql-from-within-the-geany-editor).

<a id="highlighting-execsql-metacommands-in-vim"></a>

[Highlighting metacommands in Vim](editors/other-editors.md#highlighting-execsql-metacommands-in-vim).

<a id="highlighting-execsql-metacommands-in-bluefish"></a>

[Bluefish highlighting](editors/other-editors.md#highlighting-execsql-metacommands-in-bluefish) is documented with the other editor setups.

## MS-Access-Specific Considerations

### Temporary Queries

The syntax of the "CREATE TEMPORARY QUERY" DDL supported by *execsql* when used with an MS-Access database is:

```
CREATE [TEMP[ORARY]] QUERY|VIEW <query_name> AS <sql_command>
```

The "TEMPORARY" specification is optional: if it is included, the query will be deleted after the entire script has been executed, and if it is not, the query will remain defined in the database after the script completes successfully. If a query of the same name is already defined in the Access database when the script runs, the existing query will be deleted before the new one is created---no check is performed to determine whether the new and old queries have the same definition, and no warning is issued by *execsql* that a query definition has been replaced. The keyword "VIEW" can be used in place of the keyword "QUERY". This alternative provides compatibility with the "CREATE TEMPORARY VIEW" command in PostgreSQL, and minimizes the need to edit any scripts that are intended to be run against both Access and PostgreSQL databases.

Scripts for Microsoft Access that use temporary queries will result in those queries being created in the Access database, and then removed, every time the scripts are run. This will lead to a gradual increase in the size of the Access database file. If the script halts unexpectedly because of an error, the temporary queries will remain in the Access database. This may assist in debugging the error, but if the temporary queries are not created conditional on their non-existence, you may have to remove them manually before re-running the script.

### Password-Protected Databases

The user name for password-protected Access databases is "Admin" by default (i.e., if no other user name was explicitly specified when the password was applied). To ensure that *execsql* prompts for a password for password-protected Access databases, a user name must be specified either on the command line with the "-u" option or in a configuration file with the `access_username` [configuration item](../reference/configuration.md#config_connect). When the user name in Access is "Admin", any user name can be provided to *execsql*.

### ODBC and DAO Connections

With Access databases, an ODBC connection is used for SELECT queries, to allow errors to be caught, and a DAO connection to the Jet engine is used when saved action queries (UPDATE, INSERT, DELETE) are created or modified. Because the Jet engine only flushes its buffers every five seconds, *execsql* will ensure that at least five seconds have passed between the last use of DAO and the execution of a SELECT statement via ODBC. In some cases (possibly related to database size or network speed), a longer delay may be required; a longer delay can be specified with the [dao_flush_delay_secs](../reference/configuration.md#dao_delay) configuration setting..

### Boolean Columns

Boolean (Yes/No) columns in Access databases cannot contain NULL values. If you [IMPORT](../reference/metacommands.md#import) boolean data into a column having Access' boolean data type, any NULL values in the input data will be converted to *False* boolean values. This is a potentially serious data integrity issue. To help avoid this, when the NEW or REPLACEMENT keywords are used with the [IMPORT](../reference/metacommands.md#import) or [COPY](../reference/metacommands.md#copy) metacommands, and *execsql* determines that the input file contains boolean data, *execsql* will create that column in Access with an integer data type rather than a boolean data type, and when adding data will convert non-integer *True* values to 1, and *False* values to 0.

### Exporting Access Queries to Script Files

If you have an Access database full of queries and you want to export them all to SQL script files for easier searching, to add documentation, to establish version control, to run them using *execsql*, or for other reasons, create and run the following Visual Basic procedure in the Access database.

```basic
Sub ExportAllQueries(OutputDir)
  Dim db As DAO.Database
  Dim qdf As DAO.QueryDef
  Dim fso As Object
  Dim Outfile As Object

  Set db = CurrentDb()
  Set fso = CreateObject("Scripting.FileSystemObject")

  For Each qdf In db.QueryDefs
    Fname = OutputDir + "\" + qdf.Name + ".sql"
    Set Outfile = fso.CreateTextFile(Fname, True, True)
    Outfile.Write qdf.SQL
    Outfile.Close
  Next qdf
  Set qdf = Nothing
  Set db = Nothing
  Set Outfile = Nothing
  Set fso = Nothing
End Sub
```

## Ensuring That a Script is Run Using execsql

*execsql's* metacommands are hidden in SQL comments to allow scripts to be run using other SQL script processors or using GUI tools. However, scripts that make use of [IF](../reference/metacommands.md#if_cmd), [EXECUTE SCRIPT](../reference/metacommands.md#executescript), [IMPORT](../reference/metacommands.md#import), [COPY](../reference/metacommands.md#copy), [INCLUDE](../reference/metacommands.md#include) or [LOOP](../reference/metacommands.md#loop) metacommands are likely to operate incorrectly if they are *not* run using *execsql*. The following code will cause a script to fail with a syntax error from the DBMS if it is run using anything other than *execsql*:

```sql
-- !x! if(False)
    ERROR: This script must be run using execsql;
-- !x! endif
```

Note that the error message must end with a semicolon.

## Allowing Multiple Users with Different Logins to Run the Same Script

In a multi-user environment, where more than one person may run a script, and each person has unique database credentials, connection settings should be specified in two different copies of *execsql.conf*:

- One copy of *execsql.conf* should be in the directory that contains the script, or in the directory from which it is run, and should contain all of the connection settings except [username].
- A second copy of *execsql.conf* should be in the user-specific configuration directory (e.g., ~/.config on Linux), and should contain the [username] configuration setting.

## Password Storage and the OS Keyring

When installed with the `auth` extra (`uv tool install "execsql2[auth]"`), *execsql* uses the [keyring](https://pypi.org/project/keyring/) package to store database passwords in your OS credential store (macOS Keychain, Windows Credential Manager, or a SecretService-compatible backend on Linux). After a successful interactive prompt, the password is saved automatically and reused on later runs — so you typically see a password prompt only once per `db_type / server / database / username` combination.

If a stored password is later rejected by the server (e.g. it was rotated), *execsql* clears the stale entry and re-prompts; the new password replaces the old one in the keyring.

To opt out, install without the extra, or set `use_keyring=No` in `[connect]`:

```ini
[connect]
use_keyring=No
```

To remove a stored password, open your OS credential manager (Keychain Access on macOS, Credential Manager on Windows, Seahorse / KWallet on Linux) and delete the entry under the service name pattern `execsql/<db_type>/<server>/<database>`.

## SQL Server with Windows Authentication

When a username is set in a user-level config (typical when most of your DBMSs require one), connecting to a Windows-authenticated SQL Server instance fails because no username should be sent. Override by placing an `execsql.conf` next to the script that explicitly blanks the username:

```sh
[connect]
db_type=s
server=some-server-name\SQLEXPRESS
db=rasa
username=
```

## Vim 'Inner Word' Commands with Substitution Variables

Vim treats the `!` delimiters around substitution variables as word boundaries, so `ciw` on a variable name like `!!myvar!!` replaces just `myvar` and leaves the delimiters intact.
