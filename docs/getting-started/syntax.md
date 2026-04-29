# Syntax and Options

*execsql* is a command-line tool installed via the `execsql2` package. After [installation](installation.md#installation), the `execsql` command is available on your PATH. Run it from a shell prompt on Linux/macOS or a command window on Windows.

*execsql* requires Python 3.10 or later.

## Basic Usage { #basic_usage }

```text
execsql [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
```

At minimum, provide a SQL script file to run. If database connection information is specified in a [configuration file](../reference/configuration.md#configuration), only the script file is required.

### Client-server databases

For client-server databases (PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, Firebird), provide the server and database name after the script file:

```bash
execsql -tp script.sql myserver mydb        # PostgreSQL
execsql -tm script.sql myserver mydb        # MySQL / MariaDB
execsql -ts script.sql myserver mydb        # SQL Server
execsql -to script.sql myserver myservice   # Oracle
execsql -tf script.sql myserver mydb        # Firebird
```

If only one argument is provided after the script file, it is interpreted as the database name when the server name has been set in a configuration file; otherwise it is interpreted as the server name.

### File-based databases

For file-based databases (SQLite, DuckDB, MS Access), provide the database file path:

```bash
execsql -tl script.sql mydb.sqlite          # SQLite
execsql -tk script.sql mydb.duckdb          # DuckDB
execsql -ta script.sql mydb.accdb           # MS Access
```

### DSN and connection URLs

Connect via an ODBC DSN or a connection URL:

```bash
execsql -td script.sql my_dsn_name                          # ODBC DSN
execsql --dsn postgresql://user:pass@host:5432/db script.sql # Connection URL
```

### Inline scripts

Use `-c` to execute a SQL or metacommand string directly, without a script file:

```bash
execsql -tl -c "SELECT sqlite_version();" mydb.sqlite
```

### Config-only invocation

When all connection parameters are in a [configuration file](../reference/configuration.md#configuration):

```bash
execsql script.sql
```

## Database Types { #db_types }

The `-t` option specifies the database type using a single-character code:

| Flag | Database        |
| ---- | --------------- |
| `p`  | PostgreSQL      |
| `m`  | MySQL / MariaDB |
| `s`  | MS SQL Server   |
| `l`  | SQLite          |
| `k`  | DuckDB          |
| `a`  | MS Access       |
| `f`  | Firebird        |
| `o`  | Oracle          |
| `d`  | ODBC DSN        |

## Options Reference { #options }

### Connection options

`-t`, `--type` *{a,d,f,k,l,m,o,p,s}*

:   Database type (see table above).

`-u`, `--user` *USER*

:   Database user name. *execsql* will prompt for a password unless `-w` is also specified.

`-p`, `--port` *PORT*

:   Database server port. Override only if the DBMS uses a non-default port. Defaults:

    - PostgreSQL: 5432
    - SQL Server: 1433
    - MySQL: 3306
    - Firebird: 3050
    - Oracle: 1521

`-w`, `--no-passwd`

:   Skip the password prompt when a user name is specified.

`-n`, `--new-db`

:   Create a new SQLite or PostgreSQL database if the specified database does not exist.

`--dsn`, `--connection-string` *URL*

:   Database connection URL, e.g. `postgresql://user:pass@host:5432/db`. Supported schemes: `postgresql`, `postgres`, `mysql`, `mariadb`, `mssql`, `sqlserver`, `oracle`, `firebird`, `sqlite`, `duckdb`. Overrides `-t`, `-u`, `-p`, and positional server/database arguments. Passwords included in the URL are used directly without prompting.

### Script options

`-c`, `--command` *SCRIPT*
:   Execute an inline SQL/metacommand script string instead of reading from a file. Use shell `$'line1\nline2'` syntax for multi-line scripts. When `-c` is used, no script file argument is required.

`-a`, `--assign-arg` *VALUE*
:   Define the replacement string for a [substitution variable](../reference/substitution_vars.md#substitution_vars) `$ARG_x`. Can be used repeatedly to define `$ARG_1`, `$ARG_2`, etc. Assignments are [logged](../guides/logging.md#logging). See [Example 9](../guides/examples.md#example9).

### Encoding options

`-e`, `--database-encoding` *ENCODING*
:   Character encoding used by the database. Only used for some database types.

`-f`, `--script-encoding` *ENCODING*
:   Character encoding of the script file. Default: UTF-8.

`-g`, `--output-encoding` *ENCODING*
:   Character encoding for WRITE and EXPORT output.

`-i`, `--import-encoding` *ENCODING*
:   Character encoding for data files used with IMPORT.

Valid encoding names can be displayed with the `-y` option. See also [Character Encoding](../guides/encoding.md#encoding).

### Output options

`-d`, `--directories`
:   Auto-create directories used by the EXPORT and WRITE metacommands.

`--output-dir` *DIR*
:   Default base directory for EXPORT output files. Relative paths in EXPORT metacommands are joined to this directory. Absolute paths and `stdout` are unaffected.

`-l`, `--user-logfile`
:   Write the run log to `~/execsql.log` instead of the current directory.

### Import options

`-b`, `--boolean-int` *{0,1,t,f,y,n}*
:   Control whether input data columns containing only 0 and 1 are treated as Boolean (`y`, the default) or integer (`n`).

`-s`, `--scan-lines` *N*
:   Number of lines of an imported file to scan to determine the quote and delimiter characters. Default: 100. Use 0 to scan the entire file.

`-z`, `--import-buffer` *KB*
:   Buffer size in KB for the IMPORT metacommand. Default: 32.

### GUI options

`-v`, `--visible-prompts` *{0,1,2,3}*

:   GUI interaction level:

    - **0**: Use the terminal for all prompts (the default).
    - **1**: Use a GUI dialog for password prompts and the [PAUSE](../reference/metacommands.md#pause) metacommand.
    - **2**: Additionally, use a GUI dialog for [HALT](../reference/metacommands.md#halt) messages and prompt for the initial database if no connection parameters are specified.
    - **3**: Additionally, open a GUI [console](../reference/metacommands.md#console) when *execsql* starts.

`--gui-framework` *{tkinter,textual}*

:   GUI framework to use with `--visible-prompts`. Default: `tkinter`. Use `textual` for a terminal-based UI.

### Informational options

`-m`, `--metacommands`

:   List all metacommands and exit.

`-o`, `--online-help`

:   Open the online documentation in the default browser.

`-y`, `--encodings`

:   List all valid character encoding names and exit.

`--dump-keywords`

:   Dump all metacommand keywords, conditional functions, config options, and export formats as JSON and exit. Useful for tooling that consumes execsql's keyword registry (e.g., the VS Code grammar generator).

`--dry-run`

:   Parse the script (or inline `-c` command) and print the full command list — SQL statements and metacommands with source locations — without connecting to a database or executing anything. Useful for validating scripts.

    Substitution variables that are already populated at parse time are expanded in the output: environment variables (`!!&ENV_VAR!!`), `--assign-arg` values (`!!$ARG_1!!`), and built-in start-time variables like `!!$SCRIPT_START_TIME!!` and `!!$USER!!`. Variables that are set during execution — such as `$CURRENT_TIME`, `$DB_NAME`, and `$TIMER` — remain unexpanded because no database connection is established in dry-run mode. Local `~`-prefixed script-scope variables are also left unexpanded.

`--lint`

:   Parse the script and perform static analysis without connecting to a database or executing anything. A complement to `--dry-run` focused on structural correctness rather than command display.

    Checks performed:

    - **Unmatched IF / ENDIF** — open IF blocks with no closing ENDIF, or orphan ENDIF with no IF (error).
    - **Unmatched LOOP / END LOOP** — open LOOP with no END LOOP, or orphan END LOOP (error).
    - **Unmatched BEGIN BATCH / END BATCH** — open batch with no close, or orphan END BATCH (error).
    - **Potentially undefined variables** — `!!$VAR!!` references where `$VAR` is not a built-in system variable, not `$ARG_N`, not `$COUNTER_N`, and was not defined by a `SUB`, `SUB_EMPTY`, `SUB_ADD`, `SUB_APPEND`, `SUBDATA`, or `SUB_INI` metacommand anywhere in the script (warning — may be a false-positive if the variable is set in a config file or via `-a`).
    - **Missing INCLUDE files** — `INCLUDE` targets that do not exist on disk relative to the script's directory (warning; `INCLUDE IF EXISTS` targets are never checked).
    - **Unknown EXECUTE SCRIPT target** — `EXECUTE SCRIPT` names a script block that was not defined in the file (warning; `EXECUTE SCRIPT IF EXISTS` targets are never warned about).
    - **Empty script** — no commands found (warning).

    Variable analysis uses two passes: the first collects every variable definition across the entire script and all named script blocks; the second performs the checks. Variables may be referenced before their definition point without producing false warnings. The linter also descends into named script blocks (`BEGIN SCRIPT … END SCRIPT`) reached via `EXECUTE SCRIPT`, `EXEC SCRIPT`, or `RUN SCRIPT`, so variables defined inside a block are visible to the caller. `SUB_INI` INI files are read at lint time to register their section keys as defined variables.

    Built-in system variables are discovered automatically from the installed execsql source, so new variables added in future releases are recognized without any linter changes.

    Exits 0 when no errors are found (warnings alone do not affect the exit code). Exits 1 when any errors are found.

    ```bash
    execsql --lint script.sql
    ```

`--ping`

:   Test database connectivity and exit. Connects to the configured database, queries the server version if possible, and prints a one-line summary on success (exit 0). On failure, prints the error message and exits with code 1. No script file is required — `--ping` can be combined with `--dsn` or other connection flags without specifying a `.sql` file.

    ```bash
    execsql --ping --dsn postgresql://user:pass@host/db
    execsql --ping --dsn sqlite:///mydb.sqlite
    ```

`--parse-tree`

:   Parse the script into an Abstract Syntax Tree and print a visual tree showing block nesting (IF/LOOP/BATCH/SCRIPT), source line ranges, compound conditions (ANDIF/ORIF), and all metacommands. Does not connect to a database or execute anything. Useful for understanding script structure.

    ```bash
    execsql --parse-tree script.sql
    ```

`--list-plugins`

:   List all discovered plugins (metacommands, exporters, importers) and exit. Plugins are Python packages that register extensions via entry points. See the [Plugin System](#plugin-system) section in the developer guide.

    ```bash
    execsql --list-plugins
    ```

`--debug`

:   Start in step-through debug mode. The debug REPL pauses before each statement, as if a `BREAKPOINT` metacommand were inserted at the top of the script with `.next` always active. Type `.continue` or `.c` at the REPL prompt to resume normal execution, or `.next` / `.n` to step one statement at a time. Silently skipped in non-TTY environments.

`--profile`

:   Record the wall-clock execution time of each SQL statement and metacommand. After the script finishes, print a summary table to the console showing elapsed time, percentage of total time, source file and line number, command type, and a preview of the command text. Statements are sorted from slowest to fastest; the top 20 are displayed. Useful for identifying slow queries or metacommands in long-running scripts.

`--version`

:   Show the version number and exit.

## Configuration File Defaults { #config_defaults }

Most command-line options and arguments can be specified in [configuration files](../reference/configuration.md#configuration) instead of on the command line. If the database type and connection information is specified in a configuration file, the `-t` option and the server/database arguments can be omitted. The only required command-line argument is the script file (or `-c` for inline scripts).
