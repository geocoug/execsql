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

Three additional variants exist for diagnosing the script engine itself: `DEBUG WRITE METACOMMANDLIST TO <filename>` (dump all registered metacommand patterns), `DEBUG WRITE COMMANDLISTSTACK` (current execution stack), and `DEBUG WRITE IFLEVELS` (nested IF condition state).

# Interactive Debug REPL (BREAKPOINT)

Insert `-- !x! BREAKPOINT` anywhere in a script to pause execution and drop into the interactive debug REPL:

```sql
-- !x! BREAKPOINT
SELECT * FROM orders WHERE status = 'pending';
```

On entry, the REPL prints a horizontal rule with the label (`Breakpoint` or `Step` for step-mode), the current file:line, the upcoming statement with its type tag, and a one-line help hint:

```
── Breakpoint ── myscript.sql:42 ────────────────────────────
  (sql) SELECT * FROM orders WHERE status = 'pending'
  Type '.help' for commands, '.c' to resume.

execsql debug>
```

**Available commands:**

| Command         | Shortcut | Description                                                               |
| --------------- | -------- | ------------------------------------------------------------------------- |
| `.continue`     | `.c`     | Resume script execution                                                   |
| `.quit`         | `.q`     | Halt the script (exit 1). `.abort` is accepted as an alias.               |
| `.vars`         | `.v`     | List all execsql substitution variables                                   |
| `.vars VAR`     | `.v VAR` | Print the value of one variable (e.g. `.vars logfile`, `.vars $ARG_1`)    |
| `.next`         | `.n`     | Execute the next statement, then pause again (step mode)                  |
| `.where`        | `.w`     | Re-display the current script location and upcoming statement             |
| `.stack`        |          | Show the command-list stack (script name, cursor position, nesting depth) |
| `.set VAR VAL`  | `.s`     | Set or update a substitution variable                                     |
| `.scripts`      |          | List all registered SCRIPT definitions with parameters and source         |
| `.scripts NAME` |          | Show detail for a specific SCRIPT (parameters, source file/line range)    |
| `.cancel`       |          | Discard the current partial multi-line SQL buffer (also Ctrl-C / EOF)     |
| `.help`         | `.h`     | Show available commands                                                   |

**Dispatch is two-way** (changed in 2.19.0): input starting with `.` is a REPL command, everything else is SQL. There is no bare-name variable lookup — use `.vars VAR` to print a single variable.

**SQL execution:**

- Input is buffered as SQL until a line ends with `;`, at which point the buffered statement is sent to the live connection. Multi-line statements are accepted; the prompt switches to a continuation indicator while a partial statement is being entered.
- `SELECT` (and other row-returning statements) print the result rows in tabular form.
- DML (`INSERT` / `UPDATE` / `DELETE`) prints `(N rows affected)`.
- DDL and transaction-control statements (`CREATE`, `DROP`, `BEGIN`, `COMMIT`, `ROLLBACK`, …) print `(statement executed)`.
- A SQL error prints the database error inline and returns to the prompt — the REPL session is not terminated.
- `.cancel` (or Ctrl-C / EOF mid-statement) discards a partial buffer without executing it.

The `--debug` CLI flag starts execution in step mode, pausing before every statement.

In non-interactive environments (CI, piped input) `BREAKPOINT` is silently skipped so automated pipelines are never blocked.

The ON ERROR_HALT metacommands allow custom reporting (or cleanup) actions to be taken when errors occur.

Setting the configuration setting [write_warnings](../reference/configuration.md#write_warnings) to "Yes" can also assist with debugging by displaying conditions that may result from errors in the script.

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
- Character encoding inconsistencies, particularly with data being [imported](../reference/metacommands.md#import).
- Bugs in *execsql*.
