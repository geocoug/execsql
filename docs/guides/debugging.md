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

**What you type runs as if it were the next lines of the script.** The REPL uses the same engine as [`execsql shell`](../getting-started/syntax.md#shell), and input runs where the script paused: in its variable scope, its transaction and its loop.

- **SQL** ends with `;` and may span lines; the prompt changes to `...>` until the statement is complete. Variables are substituted, as in the script. Rows print as a table; `INSERT` / `UPDATE` / `DELETE` print `(N rows affected)`; DDL and transaction control print `(statement executed)`.
- **Metacommands** are typed as in the script (`-- !x! SUB count 10`) or without the comment marker (`!x! SUB count 10`).
- **Blocks** (`IF` … `ENDIF`, `LOOP` … `END LOOP`, `BEGIN BATCH` … `END BATCH`, `BEGIN SCRIPT` … `END SCRIPT`) keep the prompt reading until they are closed, then run as a whole.

Because input runs inside the paused script, it changes what the script sees after `.continue`:

| You type at the breakpoint        | Effect on the script                                                                  |
| --------------------------------- | ------------------------------------------------------------------------------------- |
| `!x! SUB threshold 50`            | `!!threshold!!` is 50 for the rest of the run                                         |
| `select '!!~counter!!';`          | Reads the paused SCRIPT's `~local` and `#param` variables                             |
| `insert into staging values (1);` | Committed as the script's own SQL would be: now, unless `AUTOCOMMIT OFF` or a batch   |
| `!x! USE other_db`                | The script continues against `other_db`                                               |
| `!x! BREAK`                       | Inside a `LOOP` (or a looping `EXECUTE SCRIPT`), leaves that loop, as a `BREAK` would |
| `!x! HALT`                        | Ends the run                                                                          |

**Errors end only the input that caused them.** A SQL or metacommand error that would halt the script is printed, and the prompt reads the next input; `ON ERROR_HALT` actions do not run. `HALT` and `.quit` still end the run.

**Transactions follow the script's rules.** Each SQL statement is committed as it runs unless `AUTOCOMMIT OFF` is in effect or the breakpoint is inside `BEGIN BATCH`. The prompt then reads `execsql debug*>`, so you can see that what you type is not committed yet.

**Commands to the REPL** start with `.`:

| Command           | Shortcut | Description                                                               |
| ----------------- | -------- | ------------------------------------------------------------------------- |
| `.continue`       | `.c`     | Resume script execution                                                   |
| `.next`           | `.n`     | Execute the next statement, then pause again (step mode)                  |
| `.quit`           | `.q`     | Halt the script (exit 1). `.abort` is accepted as an alias.               |
| `.where`          | `.w`     | Re-display the current script location and upcoming statement             |
| `.stack`          |          | Show the execution stack (scripts, includes, IF/LOOP/BATCH blocks)        |
| `.vars`           | `.v`     | List substitution variables; `.vars all` adds environment (`&`) variables |
| `.vars VAR`       | `.v VAR` | Print the value of one variable (e.g. `.vars logfile`, `.vars $ARG_1`)    |
| `.set VAR VAL`    | `.s`     | Set or update a substitution variable                                     |
| `.scripts [NAME]` |          | List SCRIPT definitions, or show one (parameters, source lines)           |
| `.cancel`         |          | Discard a statement or block you are typing (also Ctrl-C / Ctrl-D)        |
| `.help`           | `.h`     | Show available commands                                                   |

`.vars`, `.set`, `.scripts` and `.cancel` work the same way in `execsql shell`. Ctrl-D or Ctrl-C at an empty prompt resumes the script.

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
