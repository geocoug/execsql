# Debugging

Execsql includes several metacommands that will display elements of its internal environment, to assist with script debugging.

```
DEBUG LOG [LOCAL] [USER] SUBVARS
```

Writes substitution variables to the log file. If the LOCAL keyword is used, *only* the local variables are logged. If the USER keyword is used, no system, data, or environment variables are logged.

```
DEBUG WRITE [LOCAL] [USER] SUBVARS [[APPEND] TO <filename>]
```

Writes all substitution variables to the terminal or to the specified text file. Local variables in the current context are always included. If the LOCAL keyword is used, *only* the local variables are written. If the USER keyword is used, no system, data, or environment variables are written.

```
DEBUG LOG CONFIG
```

Writes configuration settings to the log file.

```
DEBUG WRITE CONFIG [[APPEND] TO <filename>]
```

Writes configuration settings to the console or to the specified text file.

```
DEBUG WRITE ODBC_DRIVERS [[APPEND] TO <filename>]
```

Writes the names of available ODBC drivers to the console or to the specified text file. ODBC drivers are used with SQL Server and MS-Access.

```
DEBUG WRITE <script_name> [[APPEND] TO <filename>]
```

This is an alias for the [WRITE SCRIPT](metacommands.md#write_script) metacommand.

The ON ERROR_HALT metacommands allow custom reporting (or cleanup) actions to be taken when errors occur.

Setting the configuration setting [write_warnings](configuration.md#write_warnings) to "Yes" can also assist with debugging by displaying conditions that may result from errors in the script.

# Error Messages and Reporting

When *execsql* encounters an error it will print an error message that includes the command that caused the error, the line number in the script being processed, and the line number in *execsql*. These messages will appear similar to the following:

```
**** Error in metacommand.
    Line 19 of script bad_import_statement.sql
    Unknown metacommand
    import to replacement staging.locs from locations.csv with quote " delimiter ,
    Metacommand: import to replacement staging.locs from locations.csv with quote " delimiter ,
    Error occurred at 2016-09-28 21:30:50 UTC.
```

Error messages may result from:

- Typographic or syntax errors in metacommands (as above) or SQL statements.
- SQL statements that are inconsistent with the database structure or that violate data type, integrity, or check constraints--that is, errors that originate from the DBMS.
- Character encoding inconsistencies, particularly with data being [imported](metacommands.md#import).
- Bugs in *execsql*.
