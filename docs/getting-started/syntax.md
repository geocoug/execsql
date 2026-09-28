# Syntax and Options { #syntax }

*execsql* is a command-line tool installed via the `execsql2` package. After [installation](installation.md#installation), the `execsql` command is available on your PATH. Run it from a shell prompt on Linux/macOS or a command window on Windows.

*execsql* requires Python 3.10 or later.

## Commands { #commands }

*execsql* is six commands behind one program. Only `run` and `ping` connect to a database:

```text
execsql run    [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
execsql format [--check | -i] [--indent N] FILE_OR_DIR...
execsql lint   [OPTIONS] FILE_OR_DIR...
execsql ping   [OPTIONS] [SERVER DATABASE | DATABASE_FILE]
execsql config [SQL_SCRIPT] [--init] [--config FILE]
execsql list   metacommands|encodings|plugins|keywords
```

| Command  | Purpose                                                                                    |
| -------- | ------------------------------------------------------------------------------------------ |
| `run`    | Execute a script against a database. The default when no command is given.                 |
| `format` | Normalize metacommand keywords, block indentation, and SQL layout. `fmt` works too.        |
| `lint`   | Static analysis without a database. Exits 1 when any error is found.                       |
| `ping`   | Test a database connection and print the server version.                                   |
| `config` | List every config option with its value, default and source; `--init` prints the template. |
| `list`   | Print metacommands, encoding names, installed plugins, or the full keyword vocabulary.     |

`format` and `lint` accept files or directories; directories are searched
recursively for `*.sql`, and `-` reads one script from stdin. A CI job runs them
as two steps, so both report. Both read scripts with `-f`/`--script-encoding`, or
`[encoding] script` from a config file, and take `--config`; config files are read
once per invocation, not from each script's directory.
`lint` options and every rule it checks are described in the
[lint rules reference](../reference/lint.md).

!!! note "The original form still works"

    ```text
    execsql [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
    ```

    Every invocation that worked before commands were added still works and
    still means the same thing — `execsql script.sql myserver mydb` is
    identical to `execsql run script.sql myserver mydb`. There is no
    deprecation and none is planned.

    The one exception is a script named exactly like a command — `run`,
    `format`, `fmt`, `lint`, `ping`, `config` or `list`, with no extension.
    A command name always selects the command, so run such a script with
    `execsql run lint` or `execsql ./lint`. Names with an extension, such as
    `lint.sql`, are never ambiguous.

### ping { #ping }

```text
execsql ping [OPTIONS] [SERVER DATABASE | DATABASE_FILE]
```

Connects, prints the DBMS, its version and where it is, and disconnects. No
script is read. Exits 0 when the connection succeeds and 1 when it fails,
with the error on stderr. The database comes from the same places `run` gets
it: positional arguments, `--dsn`, or a [configuration file](../reference/configuration.md#configuration).

```sh
execsql ping -t p db.example.com warehouse
execsql ping --dsn postgresql://etl@db.example.com/warehouse
execsql ping -t l data.db --output-format json
```

```text
Connected to PostgreSQL 16.4 at db.example.com/warehouse
{"dbms": "SQLite", "version": "3.50.4", "location": "data.db"}
```

`ping` never creates a database: it has no `-n`, and `new_db = yes` in a
config file is ignored. In JSON, `version` is `null` when the server does not
report one.

Options: `-t`, `--dsn`, `-u`, `-p`, `-w` and `--config`, exactly as for
[`run`](#connection-options), plus `--output-format text|json`.

### config { #config_command }

```text
execsql config [SQL_SCRIPT] [--init] [--config FILE] [--output-format text|json]
```

Lists every configuration option: its current value, its default, and the
file that set it. Config files are read from the same places a run reads
them, in the same order. Passwords are shown as `***`.

```sh
execsql config                       # system, user and working-directory files
execsql config scripts/etl.sql       # also scripts/execsql.conf, as `run scripts/etl.sql` would
execsql config --config ci.conf      # also ci.conf, loaded last
execsql config --output-format json  # {"files_read": [...], "options": [...]}
execsql config --init > execsql.conf # start a new config file from the template
```

```text
Config files read, in order:
  ~/.config/execsql.conf
  scripts/execsql.conf

[connect]
  server    db.example.com  ~/.config/execsql.conf
  db_type   p               scripts/execsql.conf
  port                      default
```

Each JSON option has `section`, `key`, `type`, `value`, `default` and
`source` (`null` when the default applies).

### list { #list }

```text
execsql list metacommands|encodings|plugins|keywords [--output-format text|json]
```

| Thing          | Prints                                                                                                                        |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `metacommands` | Every metacommand and its syntax.                                                                                             |
| `encodings`    | Every character encoding name accepted by `-e`, `-f`, `-g` and `-i`.                                                          |
| `plugins`      | Installed plugins: metacommands, exporters, importers. See [Plugin System](../dev/architecture.md#plugin-system).             |
| `keywords`     | The full vocabulary: metacommands by category, conditions, CONFIG options, export formats, database types, variable patterns. |

With `--output-format json`, `keywords` prints the JSON that editor tooling
such as the VS Code grammar generator reads.

### Help and color { #help_color }

`execsql --help` lists the commands and the global options;
`execsql <command> --help` shows that command's own options, for example
`execsql run --help` for every connection and output flag below.

On a terminal, help is colored: headings in green, option flags and command
names in cyan. Piped or redirected help (`execsql run --help | less`,
`execsql --help > options.txt`) is always plain text. To turn color off on a
terminal as well, set either environment variable to any value:

```sh
export NO_COLOR=1           # the cross-tool convention, https://no-color.org
export EXECSQL_NO_COLOR=1   # execsql only
```

The same two variables also turn off color in the [debug REPL](../reference/metacommands.md#breakpoint).

### Exit codes { #exit_codes }

Every command uses the same three exit codes, so a CI step or shell script can
tell a problem in the scripts from a mistake in the command line.

| Code | Meaning                           | Examples                                                                                                                           |
| ---- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `0`  | Success                           | The script ran; `lint` found no errors (warnings allowed); `format --check` found nothing to change; `ping` connected.             |
| `1`  | The task failed or found problems | A script error; `lint` found an error; `format --check` would change a file; `ping` could not connect; no `.sql` files were found. |
| `2`  | Bad command line                  | An unknown option or command, an invalid choice, a missing config file named by `--config`, `run --lint`.                          |

`run` keeps upstream execsql's exit codes where they differ: a missing script
file exits `1`, and unknown options after the script are not rejected.

## Basic Usage { #basic_usage }

```text
execsql run [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
```

At minimum, provide a SQL script file to run. If database connection information is specified in a [configuration file](../reference/configuration.md#configuration), only the script file is required.

### Client-server databases

For client-server databases (PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, Firebird), provide the server and database name after the script file:

```sh
execsql -tp script.sql myserver mydb        # PostgreSQL
execsql -tm script.sql myserver mydb        # MySQL / MariaDB
execsql -ts script.sql myserver mydb        # SQL Server
execsql -to script.sql myserver myservice   # Oracle
execsql -tf script.sql myserver mydb        # Firebird
```

If only one argument is provided after the script file, it is interpreted as the database name when the server name has been set in a configuration file; otherwise it is interpreted as the server name.

### File-based databases

For file-based databases (SQLite, DuckDB, MS Access), provide the database file path:

```sh
execsql -tl script.sql mydb.sqlite          # SQLite
execsql -tk script.sql mydb.duckdb          # DuckDB
execsql -ta script.sql mydb.accdb           # MS Access
```

### DSN and connection URLs

Connect via an ODBC DSN or a connection URL:

```sh
execsql -td script.sql my_dsn_name                          # ODBC DSN
execsql --dsn postgresql://user:pass@host:5432/db script.sql # Connection URL
```

### Inline scripts

Use `-c` to execute a SQL or metacommand string directly, without a script file:

```sh
execsql -tl -c "SELECT sqlite_version();" mydb.sqlite
```

### Config-only invocation

When all connection parameters are in a [configuration file](../reference/configuration.md#configuration):

```sh
execsql script.sql
```

## Database Types { #db_types }

The `-t` option specifies the database type using a single-character code.
When `-t` is not specified, the default is SQLite (`l`).

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

The options below belong to `run`, so they work with `execsql run` and with
the bare form (`execsql -tl script.sql mydb.sqlite`). `execsql run --help`
lists them all. `-h`/`--help`, `--version`, and `-o`/`--online-help` also work
on their own (`execsql --version`) and anywhere on the command line.
`format` has its own options, described in the [formatter guide](../guides/formatter.md);
`lint`'s are in the [lint rules reference](../reference/lint.md); `ping`, `config` and `list`
are described [above](#ping).

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
:   Character encoding of the script file. Default: `[encoding] script` from a config file, else UTF-8. `format` and `lint` take the same option.

`-g`, `--output-encoding` *ENCODING*
:   Character encoding for WRITE and EXPORT output.

`-i`, `--import-encoding` *ENCODING*
:   Character encoding for data files used with IMPORT.

Valid encoding names can be displayed with `execsql list encodings`. See also [Character Encoding](../guides/encoding.md#encoding).

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

`--progress`
:   Show a Rich progress bar during long-running IMPORT operations. Equivalent to setting `show_progress = yes` in `execsql.conf` or `-- !x! CONFIG SHOW_PROGRESS YES` at runtime.

### GUI options

`-v`, `--visible-prompts` *{0,1,2,3}*

:   GUI interaction level:

    - **0**: Use the terminal for all prompts (the default).
    - **1**: Use a GUI dialog for password prompts and the [PAUSE](../reference/metacommands.md#pause) metacommand.
    - **2**: Additionally, use a GUI dialog for [HALT](../reference/metacommands.md#halt) messages and prompt for the initial database if no connection parameters are specified.
    - **3**: Additionally, open a GUI [console](../reference/metacommands.md#console) when *execsql* starts.

`--gui-framework` *{tkinter,textual}*

:   GUI framework to use with `--visible-prompts`. Default: `tkinter`. Use `textual` for a terminal-based UI.

### Preview, debugging and safety options

`-o`, `--online-help`

:   Open the online documentation in the default browser.

`--dry-run`

:   Parse the script (or `-c` command) and print the full command list with source locations, without connecting to a database. Substitution variables already populated at parse time (environment variables, `--assign-arg` values, start-time built-ins) are expanded; execution-time variables (`$CURRENT_TIME`, `$DB_NAME`, etc.) and `~`-prefixed locals remain literal.

`--parse-tree`

:   Parse the script into an Abstract Syntax Tree and print a visual tree showing block nesting (IF/LOOP/BATCH/SCRIPT), source line ranges, compound conditions (ANDIF/ORIF), and all metacommands. Does not connect to a database or execute anything. Useful for understanding script structure.

    ```sh
    execsql --parse-tree script.sql
    ```

`--debug`

:   Start in step-through debug mode. The debug REPL pauses before each statement, as if a `BREAKPOINT` metacommand were inserted at the top of the script with `.next` always active. Type `.continue` or `.c` at the REPL prompt to resume normal execution, or `.next` / `.n` to step one statement at a time. Silently skipped in non-TTY environments.

`--profile`

:   Record the wall-clock execution time of each SQL statement and metacommand. After the script finishes, print a summary table to the console showing elapsed time, percentage of total time, source file and line number, command type, and a preview of the command text. Statements are sorted from slowest to fastest; the top N (default 20, configurable via `--profile-limit`) are displayed. Useful for identifying slow queries or metacommands in long-running scripts.

`--profile-limit` *N*

:   Number of top statements to display in the `--profile` summary (default: 20). Remaining statements are counted and noted in the output footer.

`--no-system-cmd`

:   Disable the `SYSTEM_CMD` metacommand. Scripts that attempt to execute an OS command will fail with a clear error. Useful for CI pipelines, shared execution environments, or running semi-trusted scripts. Equivalent to `allow_system_cmd = No` in `execsql.conf` `[config]` section or `allow_system_cmd=False` in the [library API](../api/index.md#library-api). The CLI flag always takes precedence over the config file.

`--no-rm-file`

:   Disable the `RM_FILE` metacommand, so scripts cannot delete files. Fails with a clear error if a script attempts it. Equivalent to `allow_rm_file = No` in `execsql.conf` `[config]` section or `allow_rm_file=False` in the [library API](../api/index.md#library-api). The CLI flag always takes precedence over the config file.

`--no-serve`

:   Disable the `SERVE` metacommand, so scripts cannot stream files over HTTP. Fails with a clear error if a script attempts it. Equivalent to `allow_serve = No` in `execsql.conf` `[config]` section or `allow_serve=False` in the [library API](../api/index.md#library-api). The CLI flag always takes precedence over the config file.

`--config` *FILE*

:   Load an explicit configuration file *after* the implicit search paths (system, user, script-dir, working-dir). Its values take precedence over those four; CLI arguments still override everything. The file may chain additional configs via its `[config]` section.

`--version`

:   Show the version number and exit.

See [Configuration Files](../reference/configuration.md#configuration) for the full list of options that can be set via `execsql.conf` instead of (or in addition to) command-line flags.

### Flags that became commands { #former_flags }

These `run` flags are now commands. Each old spelling still works, is hidden
from `execsql run --help`, and prints exactly what its command prints — except
`--lint`, which was removed.

| Old flag               | Use instead                                  | Old flag still works?                                                                  |
| ---------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------- |
| `-m`, `--metacommands` | `execsql list metacommands`                  | Yes                                                                                    |
| `-y`, `--encodings`    | `execsql list encodings`                     | Yes                                                                                    |
| `--list-plugins`       | `execsql list plugins`                       | Yes                                                                                    |
| `--dump-keywords`      | `execsql list keywords --output-format json` | Yes                                                                                    |
| `--init-config`        | `execsql config --init`                      | Yes                                                                                    |
| `--ping`               | `execsql ping`                               | Yes; unlike `ping`, `--ping -n` still creates a missing database                       |
| `--lint`               | `execsql lint`                               | No: exits 2 with `run --lint was removed; use execsql lint`, and never runs the script |
