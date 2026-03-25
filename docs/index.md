# A Multi-DBMS SQL Script Processor

[![image](images/execsql_logo_01.png)](https://pypi.org/project/execsql2/)

*execsql* is a command-line tool that applies a SQL script stored in a text file to a PostgreSQL, SQLite, DuckDB, MS-SQL-Server, MariaDB, MySQL, Firebird, MS-Access, or Oracle database, or an ODBC DSN. *execsql* also supports a set of special commands ([metacommands](metacommands.md#metacommands)) that can import and export data, copy data between databases, display data, and conditionally execute SQL statements and metacommands. These metacommands make up a control language that works the same across all supported database management systems (DBMSs). The metacommands are embedded in SQL comments, so they will be ignored by other script processors (e.g., *psql* for Postgres and *sqlcmd* for SQL Server). The metacommands are a toolbox that can be used to create both automated and interactive data processing applications; some of these uses are illustrated in the [examples](examples.md#examples).

# Capabilities

You can use *execsql* to:

- Import data from text files and spreadsheets into a database.
- Export tables and views to text files, OpenDocument spreadsheets, HTML, JSON, LaTeΧ, XML, or 17 other data formats.
- Copy data between different databases, even databases using different DBMSs.
- Display tables or views on the terminal or in a GUI dialog window.
- Export data using template processors to produce non-tabular output with customized format and contents.
- Conditionally execute different SQL commands and metacommands based on the DBMS in use, the database in use, data values, user input, and other conditions.
- Execute blocks of SQL statements and metacommands repeatedly, using any of three different looping methods.
- Prompt the user to select files or directories, answer questions, or enter data values.
- Allow the user to visually compare two tables or views.
- Serve data tables to a web application when used as a CGI script.
- Write messages to the console or to a file during the processing of a SQL script. These messages can be used to display the progress of the script or create a custom log of the operations that have been carried out or results obtained. Status messages and data exported in text format can be combined in a single text file. Data tables can be exported in a text format that is compatible with Markdown pipe tables, so that script output can be converted into a variety of document formats (see [Example 8](examples.md#example8) and [Example 11](examples.md#example11)).

Different DBMSs and DBMS-specific client programs provide different and incompatible extensions to SQL, ordinarily to allow interactions with the file system and to allow conditional tests and looping. Some DBMSs do not have any native extensions of this sort. *execsql* provides these features, as well as features for user interaction, in an identical fashion for all supported DBMSs. This allows standardization of the SQL scripting language used for different types of database management systems.

*execsql*'s features for conditional tests, looping, and sub-scripts allow the script author to write modular, maintainable, and re-usable code.

*execsql* is inherently a command-line program that can operate in a completely non-interactive mode (except, in some cases, for password prompts). Therefore, it is suitable for incorporation into a toolchain controlled by a shell script (on Linux), batch file (on Windows), or other system-level scripting application. However, several [metacommands](metacommands.md#metacommands) can be used to generate interactive prompts and data displays, so *execsql* scripts can be written to provide some user interactivity.

In addition, *execsql* automatically maintains a [log](logging.md#logging) that documents key information about each run of the program, including the databases that are used, the scripts that are run, and the user's choices in response to interactive prompts. Together, the script and the log provide documentation of all actions carried out that may have altered data.

# Documentation Guide

The sections of the *execsql* documentation fall into several categories, described in the following sections.

## Getting Started

These documentation sections contain information that most users will need to read in order to start using *execsql*.

> | [Installation](installation.md#installation): Installation of *execsql*.
> | [Requirements](requirements.md#requirements): Other Python packages that may be needed.
> | [Syntax and Options](syntax.md#syntax): Command-line arguments and flags.

## Major Features and Reference

These documentation sections contain detailed descriptions of major features of *execsql*. These sections may need to be consulted repeatedly when writing SQL scripts. Some tips and guidance are included within these sections; see below for other sections containing tips and guidance.

> | [Configuration Files](configuration.md#configuration): Fire-and-forget control over *execsql*'s environment and operation.
> | [Substitution Variables](substitution_vars.md#substitution_vars): Text substitutions to customize any part of a script.
> | [Metacommands](metacommands.md#metacommands): Import and export data, interact with the user, and dynamically control script flow.

## Tips and Guidance

These documentation sections include information that is pertinent to specific DBMSs and may improve your understanding and usage of *execsql*'s features. If you are encountering unexpected behavior, information in these sections may be of assistance.

> | [Usage Notes](usage.md#usage): Important but not necessarily essential information about *execsql*'s operation.
> | [SQL Syntax Notes](sql_syntax.md#sql_syntax): Details about handling of SQL statements.
> | [Logging](logging.md#logging): A description of the automatically maintained log file, which can be useful for *post-mortem* evaluation of script actions.
> | [Character Encoding](encoding.md#encoding): Information on handling of different character encodings.
> | [Using Script Files](using_scripts.md#scripting): Recommendations (really, advocacy) for the use of script files.
> | [Documenting Script Actions](documentation.md#documentation): Information to support the creation of comprehensive documentation.
> | [Debugging](debugging.md#debugging): Metacommands to assist with SQL script debugging.

## Examples

This section contains examples of *execsql*'s usage, focusing primarily on [metacommands](metacommands.md#metacommands). The code snippets in these examples can generally be easily modified for use in other applications.

> | [Examples](examples.md#examples): Code snippets to illustrate *execsql* usage.
