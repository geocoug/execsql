# Substitution Variables

Substitution variables are words that have been defined to be equivalent to some other text, so that when they are used, those words will be replaced (substituted) by the other text in a SQL statement or metacommand. Substitution variables are similar to macros in the C programming language. Execsql performs the substitutions immediately before each statement or metacommand is executed (unlike C). Ordinary substitution variables can be defined and re-defined dynamically as a script runs.

Substitution variables can be defined using the SUB metacommand, as follows:

```sql
SUB <match_string> <replacement_string>
```

The \<match_string> is the word (substitution variable) that will be matched, and the \<replacement_string> is the text that will be substituted for the matching word. Substitution variables are only recognized in SQL statements and metacommands when the match string is preceded and followed by two exclamation points (`!!`) or by either of two variants:

- Exclamation points bracketing an apostrophe (`!'!`). This will cause all apostrophes in the replacement string to be doubled.
- Exclamation points bracketing a double quote (`!"!`). This will cause the replacement string to be double-quoted.

The first of these variants is useful when the replacement value is a data value that may contain apostrophes. For example, it could be used in a SQL statement such as:

```sql
create or replace temporary view docs as
select * from documents
where author = '!!@author!!';
```

The second variant is useful when a database object name must be double-quoted when it is used in a metacommand. For example:

```sql
-- !x! export !"!foreign_table!"! to xtable.csv as csv
```

The `!!` dereferencing token causes the replacement string to be substituted for the match string without any modification.

Substitution variable names may contain only letters, digits, and the underscore character (the first character may be different in some cases, as described in the following sections). Substitutions are processed in the order in which they are defined. Substitution variable definitions can themselves include substitution variables. SQL statements and metacommands may contain nested references to substitution variables, as illustrated in [Example 7](examples.md#example7). Complex expressions using substitution variables can be evaluated using SQL, as illustrated in [Example 16](examples.md#example16).

Substitution variables are global by default, but local substitution variables can also be created. The scope of local substitution variables is limited to the [SCRIPT](metacommands.md#beginscript) in which they are created. Local substitution variables must be prefixed with "~" when they are referenced.

In addition to ordinary substitution variables, there are four additional kinds of substitution variables that are defined automatically by execsql or by specific metacommands. These are [system variables](#system_vars), [data variables](#data_vars), [argument variables](#arg_vars), and [environment variables](#envt_vars). System, data, argument, and environment variable names are prefixed with "$", "@", "#", and "&", respectively. Because these prefixes cannot be used when defining substitution variables with the SUB metacommand, system variable, data variable, argument variable, and environment variable names will not conflict with user-created variable names.

The differences between types of substitution variables are summarized in the following table.

| Type         | Prefix | Scope                            | R/W or R/O |
| ------------ | ------ | -------------------------------- | ---------- |
| Ordinary     | None   | Global                           | R/W        |
| Local        | ~      | SCRIPT where defined             | R/W        |
| Local, outer | +      | Outer scope of SCRIPT where used | R/O        |
| System       | $      | Global                           | R/O        |
| Data         | @      | Global                           | R/O        |
| Argument     | #      | SCRIPT where used                | R/O        |
| Environment  | &      | Global                           | R/O        |

The types of substitution variables are more fully described in the following sections. All of the substitution variables that are defined can be displayed with a [DEBUG](debugging.md#debugging) metacommand.

## Local Variables

Ordinary user-defined substitution variables, system variables, data variables, and environment variables are all global in scope: they can be referenced anywhere, including within other scripts that are [INCLUDEEd](metacommands.md#include) or defined with the [SCRIPT](metacommands.md#beginscript) metacommand.

If the variable name starts with a tilde (~), however, the variable will be local to the [script](metacommands.md#beginscript) in which it is defined, and will not be accessible in any other script. The same local variable name can be used in multiple scripts without the instances interfering with one another.

In addition, within a [script](metacommands.md#beginscript), a plus (+) prefix may be used to refer to a local variable in an outer scope. Substitutions defined for a "+"-prefixed variable will be applied to the first (proceeding outward) local variable by the same name found in an enclosing script. The plus prefix may only be used to refer to an existing instance of an outer-scope local variable; it cannot be used to create a new instance. If no corresponding local variable exists in any outer scope, an error will be raised. A plus prefix may be used with the following metacommands: [SUB](metacommands.md#subcmd), [SUB_ADD](metacommands.md#sub_add), [SUB_APPEND](metacommands.md#sub_append), [SUB_DECRYPT](metacommands.md#sub_decrypt), [SUB_EMPTY](metacommands.md#sub_empty), [SUB_ENCRYPT](metacommands.md#sub_encrypt), [SUB_TEMPFILE](metacommands.md#sub_tempfile), and [SUBDATA](metacommands.md#subdata). [Example 24](examples.md#example24) illustrates use of the "+" prefix to assign a value to an outer-scope local variable.

The scope of [argument variables](#arg_vars) is also limited to the script in which they are defined, but no changes can be made to argument variables, whereas local variables can be freely created, modified, and removed.

## System Variables { #system_vars }

Several special substitutions (pairs of matching strings and replacement strings) are automatically defined and maintained by execsql. The names and definitions of these substitution variables are:

$ARG_x
:   The value of a substitution variable that has been assigned on the command line using the "-a" command-line option. The value of \<x> must be an integer greater than or equal to 1. See [Example 9](examples.md#example9) for an illustration of the use of "$ARG_x" variables.

$AUTOCOMMIT_STATE
:   A value indicating whether or not execsql will automatically commit each SQL statement as it is executed. This will be either "ON" or "OFF". The autocommit state is database specific, and the value applies only to the database currently in [use](metacommands.md#use).

$CANCEL_HALT_STATE
:   The value of the status flag that is set by the [CANCEL_HALT](metacommands.md#cancel_halt) metacommand. The value of this variable is always either "ON" or "OFF". A modularized sub-script can use this variable to access and save (in another substitution variable) the CANCEL_HALT state before changing it, so that the previous state can be restored.

$CONSOLE_WAIT_WHEN_DONE_STATE
:   The value of the status flag that is set by the `console_wait_when_done` configuration setting or by the [CONFIG CONSOLE WAIT_WHEN_DONE](metacommands.md#console_wait_when_done) metacommand. The value of this variable is always either "ON" or "OFF".

$CONSOLE_WAIT_WHEN_ERROR_STATE
:   The value of the status flag that is set by the `console_wait_when_error_halt` configuration setting or by the [CONFIG CONSOLE WAIT_WHEN_ERROR](metacommands.md#console_wait_when_error) metacommand. The value of this variable is always either "ON" or "OFF".

$COUNTER_x
:   An integer value that is automatically incremented every time that it is referenced. As many counter variables as desired can be used. The value of *x* must be an integer that identifies the counter variable. Counter variable names do not have to be used sequentially. The first time that a counter variable is referenced, it returns the value 1. If a counter variable is referenced multiple times in one command, each reference will have the same value. The [RESET COUNTER](metacommands.md#reset_counter) metacommand can be used to re-initialize counter variables so that the next reference returns a value of 1. The [SET COUNTER](metacommands.md#set_counter) metacommand can be used to set a counter variable to a specified value. See examples [6](examples.md#example6), [7](examples.md#example7), [11](examples.md#example11), and [19](examples.md#example19) for illustrations of the use of counter variables.

$CURRENT_ALIAS
:   The alias of the database currently in use, as defined by the [CONNECT](metacommands.md#connect) metacommand, or "initial" if no CONNECT metacommand has been used. This value will change if a different database is [USEd](metacommands.md#use).

$CURRENT_DATABASE
:   The DBMS type and the name of the current database. This value will change if a different database is [USEd](metacommands.md#use).

$CURRENT_DBMS
:   The DBMS type of the database in use. This value may change if a different database is [USEd](metacommands.md#use).

$CURRENT_DIR
:   The full path to the current directory. The value will not have a directory separator character (i.e., "/" or "\\") at the end.

$CURRENT_PATH
:   The full path to the current directory, including a directory separator character (i.e., "/" or "\\") at the end.

$CURRENT_SCRIPT
:   The file name of the script from which the current command originated. This value will change if a different script is [INCLUDEEd](metacommands.md#include). This file name may or may not include a path, depending on how the script file was identified on the command line or in an INCLUDE metacommand.

$CURRENT_SCRIPT_NAME
:   The base file name, without a path, of the script from which the current command originated. This value will change if a different script is [INCLUDEEd](metacommands.md#include).

$CURRENT_SCRIPT_PATH
:   The complete path of the script from which the current command originated, including a terminating path separator character. This value will change if a different script is [INCLUDEEd](metacommands.md#include).

$CURRENT_TIME
:   The date and time at which the current script line is run. See [Example 4](examples.md#example4) for an illustration of its use.

$CURRENT_TIME_UTC
:   The date and time at which the current script line is run, in Universal Coordinated Time (UTC).

$DATE_TAG
:   The date on which execsql started processing the current script, in the format YYYYMMDD. This is intended to be a convenient short form of the date that can be used to apply sequential version indicators to directory names or file names (e.g., of exported data). See [Example 2](examples.md#example2) for an illustration of its use.

$DATETIME_TAG
:   The date and time at which execsql started processing the current script, in the format YYYYMMDD_hhmm. This is intended to be a convenient short form of the date and time that can be used to apply sequential versions to directory names or file names. See [Example 8](examples.md#example8) for an illustration of its use.

$DATETIME_UTC_TAG
:   The date and time at which execsql started processing the current script, in Universal Coordinated Time (UTC), in the format YYYYMMDD_hhmm. This is intended to be a convenient short form of the date and time that can be used to apply sequential versions to directory names or file names. See [Example 8](examples.md#example8) for an illustration of its use.

$DB_NAME
:   The name of the database currently in use, as specified on the command line or in a [CONNECT](metacommands.md#connect) metacommand. This will be the database name for server-based databases, and the file name for file-based databases.

$DB_NEED_PWD
:   A string equal to "TRUE" or "FALSE" indicating whether or not a password was required for the database currently in use.

$DB_SERVER
:   The name of the database server for the database currently in use, as specified on the command line or in a [CONNECT](metacommands.md#connect) metacommand. If the database in use is not server-based, the result will be an empty string.

$DB_USER
:   The name of the database user for the database currently in use, as specified on the command line or in a [CONNECT](metacommands.md#connect) metacommand. If the database connection does not require a user name, the result will be an empty string.

$ERROR_HALT_STATE
:   The value of the status flag that is set by the [ERROR_HALT](metacommands.md#error_halt) metacommand. The value of this variable is always either "ON" or "OFF". A modularized sub-script can use this variable to access and save (in another substitution variable) the ERROR_HALT state before changing it, so that the previous state can be restored.

$ERROR_MESSAGE
:   The message generated by any error, as it would be printed on the terminal by default. This is initially an empty string, and is set by any SQL error or metacommand error. If an error occurs, the error message is only accessible if the [ERROR_HALT OFF](metacommands.md#error_halt) or [METACOMMAND_ERROR_HALT OFF](metacommands.md#metacommanderrorhalt) metacommand has been used, or in an [ON ERROR_HALT EMAIL](metacommands.md#error_halt_email), [ON ERROR_HALT WRITE](metacommands.md#error_halt_write), or [ON ERROR_HALT EXECUTE SCRIPT](metacommands.md#error_halt_exec) metacommand.

$LAST_ERROR
:   The text of the last SQL statement or metacommand that caused an error. This value will only be available if the [ERROR_HALT OFF](metacommands.md#error_halt) or [METACOMMAND_ERROR_HALT OFF](metacommands.md#metacommanderrorhalt) metacommand has been used, or in an [ON ERROR_HALT EMAIL](metacommands.md#error_halt_email), [ON ERROR_HALT WRITE](metacommands.md#error_halt_write), or [ON ERROR_HALT EXECUTE SCRIPT](metacommands.md#error_halt_exec) metacommand.

$LAST_ROWCOUNT
:   The number of rows that were affected by the last INSERT, UPDATE, or SELECT statement. Note that support for $LAST_ROWCOUNT varies among DBMSs. For example, for SELECT statements, Postgres provides an accurate count, SQLite always returns -1, Firebird always returns 0, and DuckDB does not provide a value.

$LAST_SQL
:   The text of the last SQL statement that ran without error.

$METACOMMAND_ERROR_HALT_STATE
:   The value of the status flag that is set by the [METACOMMAND_ERROR_HALT](metacommands.md#metacommanderrorhalt) metacommand. The value of this variable is always either "ON" or "OFF".

$OS
:   The name of the operating system. This will be "linux", "windows", "cygwin", "darwin", "os2", "os2emx", "riscos", or "atheos".

$PATHSEP
:   The path separator used by the operating system. This is "/" on Linux and "\\" on Windows.

$PYTHON_EXECUTABLE
:   The path and name of the Python interpreter that is running execsql. This can be used with the [SYSTEM_CMD](metacommands.md#system_cmd) metacommand to run a Python program in a version-independent and operating-system-independent manner.

$RANDOM
:   A random real number in the semi-open interval \[0.0, 1.0). Multiple references to $RANDOM in a single SQL statement or metacommand will return the same value.

$RUN_ID
:   The run identifier that is used in execsql's log file.

$SCRIPT_LINE
:   The line number of the current script for the current command.

$SCRIPT_START_TIME
:   The date and time at which execsql started processing the current script. This value never changes within a single run of execsql.

$SCRIPT_START_TIME_UTC
:   The date and time at which execsql started processing the current script, in Universal Coordinated Time (UTC). This value never changes within a single run of execsql.

$SHEETS_IMPORTED
:   A comma-delimited list of the names of all worksheets [IMPORTed](metacommands.md#import) when using the SHEETS MATCHING clause.

$SHEETS_TABLES
:   A comma-delimited list of the names of all of the tables created when the SHEETS MATCHING clause of the [IMPORT](metacommands.md#import) metacommand is used. The table names will *not* include any schema name that is used with the IMPORT metacommand.

$SHEETS_TABLES_VALUES
:   A comma-delimited list of parenthesized single-quoted names of all of the tables created when the SHEETS MATCHING clause of the [IMPORT](metacommands.md#import) metacommand is used. The table names *will* include any schema name that is used with the IMPORT metacommand.

$STARTING_PATH
:   The path of the directory from which execsql was started, including a terminating path separator character.

$STARTING_SCRIPT
:   The file name of the script specified on the command line when execsql is run. This value never changes within a single run of execsql. This file name may or may not include a path, depending on how it was specified on the command line.

$STARTING_SCRIPT_NAME
:   The base file name of the script specified on the command line when execsql is run, without any path specification. This value never changes within a single run of execsql. This may or may not be the same as $STARTING_SCRIPT; the latter may include a path.

$STARTING_SCRIPT_REVTIME
:   The date and time of the script specified on the command line when execsql is run.

$SYSTEM_CMD_EXIT_STATUS
:   The exit status of the command executed by the [SYSTEM_CMD](metacommands.md#system_cmd) metacommand. The value is "0" (zero) prior to the first use of the SYSTEM_CMD metacommand.

$TIMER
:   The elapsed time of the script timer. If the [TIMER ON](metacommands.md#timer) command has never been used, this value will be zero. If the timer has been started but not stopped, this value will be the elapsed time since the timer was started. If the timer has been started and stopped, this value will be the elapsed time when the timer was stopped.

$USER
:   The name of the person logged in when the script is started. This is not necessarily the same as the user name used with any database.

$UUID
:   A random 128-bit Universally Unique Identifier in the canonical form of 32 hexadecimal digits. Multiple references to $UUID in a single SQL statement or metacommand will return the same value.

$VERSION1
:   Execsql's primary version number.

$VERSION2
:   Execsql's secondary version number.

$VERSION3
:   Execsql's tertiary version number.

The system variables can be used for conditional execution of different SQL commands or metacommands, and for [custom logging](documentation.md#documentation) of a script's actions.

## Data Variables { #data_vars }

Three metacommands, [SELECT_SUB](metacommands.md#select_sub), [PROMPT
SELECT_SUB](metacommands.md#prompt_selsub), and [PROMPT ACTION](metacommands.md#prompt_action) will each create a set of substitution variables that correspond to the data values in a single row of a data table. The column names of the data table, prefixed with "@", will be automatically assigned as the names of these data variables. The prefix of "@" cannot be assigned using [SUB](metacommands.md#subcmd) or similar metacommands, and so will prevent data variables from overwriting any user-defined substitution variables that may have the same name as a data table column. See [Example 8](examples.md#example8) for an illustration of the use of a data variable. All assignments to data variables are automatically [logged](logging.md#logging).

Note that if database column names contain characters that are invalid for substitution variable names (i.e., other than letters, digits, and the underscore), the data variables that are created will not be usable.

## Argument Variables { #arg_vars }

Argument variables are defined by the WITH ARGUMENTS clause of the [EXECUTE SCRIPT](metacommands.md#executescript) metacommand. When referenced within the body of the script, argument variable names must be prefixed with "#". The scope of argument variables is limited to the script for which they are arguments: they cannot be referenced outside of the script. No direct assignments can be made to argument variables; their values are set only once, in the WITH ARGUMENTS clause, so they are read-only, even within the script.

## Environment Variables { #envt_vars }

The operating system environment variables that are defined when execsql starts will be available as substitution variables prefixed with "&". New environment variables cannot be added by any metacommand.

Any environment variable names that contain characters other than letters, digits, and the underscore will not be defined in execsql.

!!! warning "Security consideration"

    **All** environment variables present at startup are exposed as substitution
    variables. This includes any sensitive values such as API keys, tokens, or
    credentials that may be set in the process environment. If a script is
    shared, logged, or produces output that includes substitution variable
    expansions, those secret values could be disclosed. To reduce risk, avoid
    storing secrets in environment variables that will be present when execsql
    runs, or use the `$ENV:` prefix in configuration files instead of
    referencing `&`-prefixed variables in scripts.

## Metacommands to Assign Substitution Variables

In addition to the [SUB](metacommands.md#subcmd) metacommand, several other metacommands can be used to define substitution variables based on values in a data table, user input, or a configuration file. All of the metacommands that can be used to define substitution variables are:

[PROMPT DIRECTORY](metacommands.md#prompt_dir)
:   Opens a dialog box and prompts the user to identify an existing directory on the file system. The name of the substitution variable is specified in the metacommand, and the full path to the selected directory will be used as the replacement string.

[PROMPT ENTER_SUB](metacommands.md#prompt_enter)
:   Opens a dialog box and prompts the user to interactively enter the text that will be used as a replacement string. The name of the substitution variable is specified in the metacommand.

[PROMPT ENTRY_FORM](metacommands.md#prompt_entry)
:   Displays a custom data entry form and assigns each of the values entered to a specified substitution variable.

[PROMPT OPENFILE](metacommands.md#prompt_open)
:   Opens a dialog box and prompts the user to select an existing file. The name of the substitution variable is specified in the metacommand, and the full path to the selected file will be used as a replacement string.

[PROMPT SAVEFILE](metacommands.md#prompt_save)
:   Opens a dialog box and prompts the user to enter the name of a new or existing file; the full path to this file will be used as a replacement string.

[PROMPT SELECT_SUB](metacommands.md#prompt_selsub)
:   Opens a dialog box, displays a data table or view, and prompts the user to select a row. The data values on the selected row will be assigned to a set of data variables.

[SELECT_SUB](metacommands.md#select_sub)
:   The data values on the first row of a specified table or view will be assigned to a set of data variables. No prompt is displayed.

[SUB](metacommands.md#subcmd)
:   Directly assigns a replacement string to a substitution variable.

[SUB_ADD](metacommands.md#sub_add)
:   Adds a numeric value to a substitution variable, which should already contain a numeric value.

[SUB_APPEND](metacommands.md#sub_append)
:   Appends text to a substitution variable. The appended text is separated from the existing text with a newline.

[SUB_INI](metacommands.md#sub_ini)
:   Assigns substitution variables that are defined in a specified section of an INI file.

[SUB_LOCAL](metacommands.md#sub_local)
:   Defines a local substitution variable that is accessible only within the script in which it is defined.

[SUB_TEMPFILE](metacommands.md#sub_tempfile)
:   Assigns a temporary file name to the specified substitution variable.

[SUBDATA](metacommands.md#subdata)
:   The data value in the first column of the first row of a specified table or view will be assigned to a user-specified substitution variable.

Substitution variables can also be defined in the "variables" section of a [configuration file](configuration.md#configuration).

## Deferred Variable Substitution { #deferred_substitution }

The ON ERROR_HALT metacommands, the ON CANCEL_HALT metacommands, the EXECUTE SCRIPT WHILE/UNTIL metacommands, the LOOP metacommand, and two forms of the EXTEND SCRIPT metacommand all accept clauses or arguments that can contain substitution variables that are meant to be evaluated after the execution of the metacommand itself. For example, in the metacommand line:

```
ON ERROR_HALT WRITE "Error in line: !!$LAST_ERROR!!"
```

The $LAST_ERROR system variable is intended to be evaluated when an error occurs. Instead, however, it will be evaluated when the ON ERROR_HALT WRITE metacommand itself is executed, and because no error has occurred at that point in the script, the $LAST_ERROR system variable will be empty, and the value that will be written when an error occurs will be just "Error in line: ".

This problem can be eliminated by deferring variable substitution. Variables for which substitution is to be deferred should be bracketed with the tokens "!!" instead of "!!". Using deferred substitution, the example metacommand above should be written:

```
ON ERROR_HALT WRITE "Error in line: !!"
```
