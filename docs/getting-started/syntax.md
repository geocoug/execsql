# execsql run: syntax and options { #syntax }

*execsql* is a command-line tool installed via the `execsql2` package. After [installation](installation.md#installation), the `execsql` command is available on your PATH. Run it from a shell prompt on Linux/macOS or a command window on Windows.

*execsql* requires Python 3.10 or later.

## Commands { #commands }

*execsql* has eight subcommands. See the [command overview](../reference/cli/index.md). `run` executes scripts; `inspect database` connects for metadata-only inspection:

```text
execsql run    [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
execsql format [--check | -i] [--indent N] FILE_OR_DIR...
execsql lint   [OPTIONS] FILE_OR_DIR...
execsql config [SQL_SCRIPT] [--init] [--config FILE]
execsql list   metacommands|encodings|plugins|keywords [--output-format text|json]
execsql inspect database --dsn URL [--schema NAME] [--table NAME]
execsql inspect schema NAME --dsn URL
execsql inspect table NAME --dsn URL [--schema NAME]
execsql init   [DIR] [--script NAME | --no-script] [--no-config] [--no-pre-commit] [--force]
execsql lsp    [--check] [--log-level LEVEL] [--log-file PATH]
```

| Command   | Purpose                                                                                                 |
| --------- | ------------------------------------------------------------------------------------------------------- |
| `run`     | Execute a script against a database.                                                                    |
| `format`  | Normalize metacommand keywords, block indentation, and SQL layout.                                      |
| `lint`    | Static analysis without a database. Exits 1 when any error is found.                                    |
| `config`  | List every config option with its value, default and source; `--init` prints the template.              |
| `list`    | Print metacommands, encoding names, installed plugins, or the full keyword vocabulary.                  |
| `init`    | Set up a project: `execsql.conf`, a script with a header, and the pre-commit hooks.                     |
| `lsp`     | The language server editors start for `.sql` files; see [Editor Support](../guides/editors.md#editors). |
| `inspect` | Read-only database metadata; see [inspect database](../reference/cli/inspect.md).                       |

`format` and `lint` accept files or directories; directories are searched
recursively for `*.sql`, and `-` reads one script from stdin. A CI job runs them
as two steps, so both report. Both read scripts with `-f`/`--script-encoding`, or
`[encoding] script` from a config file, and take `--config`; config files are read
once per invocation, not from each script's directory.
`lint` options and every rule it checks are described in the
[lint rules reference](../reference/lint.md).

!!! warning "The original form is deprecated"

    ```text
    execsql [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
    ```

    Running a script without `run` still works and still means the same
    thing — `execsql script.sql myserver mydb` is `execsql run script.sql myserver mydb` — but it prints a deprecation warning on stderr, and it
    stops working in execsql2 3.0. Put `run` first. The flags that became
    commands warn the same way when used without one, and name their
    replacement:

    | Instead of                | Use                                          |
    | ------------------------- | -------------------------------------------- |
    | `execsql script.sql …`    | `execsql run script.sql …`                   |
    | `execsql -m`              | `execsql list metacommands`                  |
    | `execsql -y`              | `execsql list encodings`                     |
    | `execsql --list-plugins`  | `execsql list plugins`                       |
    | `execsql --dump-keywords` | `execsql list keywords --output-format json` |
    | `execsql --init-config`   | `execsql config --init`                      |
    | `execsql --ping …`        | `execsql run --ping …`                       |

    Until then, a script named exactly like a command — `run`, `format`,
    `lint`, `config`, `list`, `init`, `lsp` or `inspect`, with no extension — must be run
    as `execsql run lint`: a command name always selects
    the command. Names with an extension, such as `lint.sql`, are never
    ambiguous.

<a id="config_command"></a>

See [`execsql config`](../reference/cli/config.md) for usage, options and examples.

<a id="config_validate"></a>

See [configuration validation](../reference/cli/config.md#config_validate).

<a id="list"></a>

See [`execsql list`](../reference/cli/list.md) for usage, options and examples.

<a id="init"></a>

See [`execsql init`](../reference/cli/init.md) for usage, options and examples.

### Help and color { #help_color }

`execsql --help` lists the commands and the global options;
`execsql <command> --help` shows that command's own options, for example
`execsql run --help` for every connection and output flag below. Help uses the
full width of the terminal; piped help wraps at 80 columns.

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

The tool commands use the statuses below. `run` also reports script-controlled
and lifecycle statuses; inspect the second table when automating script execution.

| Code | Meaning                           | Examples                                                                                                                                                                                                                                                                                   |
| ---- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `0`  | Success                           | The script ran; `lint` found no errors (warnings allowed); `format --check` found nothing to change; `run --ping` connected.                                                                                                                                                               |
| `1`  | The task failed or found problems | A script error; `lint` found an error (or any issue, with `--strict`); `format --check` or `--diff` would change a file; `run --ping` could not connect; no `.sql` files were found.                                                                                                       |
| `2`  | Bad command line                  | An unknown option or command, an invalid choice, a missing config file named by `--config`, `run --lint`. Until execsql2 3.0, a first word that is not a command is taken as a script (the deprecated bare form), so a mistyped command exits `1`: `SQL script file "lnt" does not exist`. |

Additional `run` statuses:

| Code            | Meaning                                                                                     |
| --------------- | ------------------------------------------------------------------------------------------- |
| `0`             | Normal completion, or an explicitly selected successful HALT status.                        |
| `1`             | Halting script/SQL/metacommand error, or a missing script file.                             |
| `2`             | A cancelled prompt with `CANCEL_HALT ON`, as well as command-line usage errors.             |
| `3`             | `HALT` without an explicit status.                                                          |
| Explicit status | `HALT EXIT_STATUS N` returns the requested status; operating-system exit-code limits apply. |
| `143`           | SIGTERM handled by the CLI (`128 + 15`).                                                    |

Arguments after a script are not all validated like subcommand options. Use the documented invocation forms, and do not interpret every `2` from `run` as a bad option.

A `run` stopped with SIGTERM (`kill`, `timeout`, `docker stop`, a cancelled CI
job) exits `143`. It first stops a running `SYSTEM_CMD`, rolls back the open
transaction and writes its log, ending with an `exit` record of type `terminated`.

## Basic Usage { #basic_usage }

```text
execsql run [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
```

At minimum, provide a SQL script file to run. If database connection information is specified in a [configuration file](../reference/configuration.md#configuration), only the script file is required.

### Client-server databases

For client-server databases (PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, Firebird), provide the server and database name after the script file:

```sh
execsql run -tp script.sql myserver mydb        # PostgreSQL
execsql run -tm script.sql myserver mydb        # MySQL / MariaDB
execsql run -ts script.sql myserver mydb        # SQL Server
execsql run -to script.sql myserver myservice   # Oracle
execsql run -tf script.sql myserver mydb        # Firebird
```

If only one argument is provided after the script file, it is interpreted as the database name when the server name has been set in a configuration file; otherwise it is interpreted as the server name.

### File-based databases

For file-based databases (SQLite, DuckDB, MS Access), provide the database file path:

```sh
execsql run -tl script.sql mydb.sqlite          # SQLite
execsql run -tk script.sql mydb.duckdb          # DuckDB
execsql run -ta script.sql mydb.accdb           # MS Access
```

### DSN and connection URLs

Connect via an ODBC DSN or a connection URL:

```sh
execsql run -td script.sql my_dsn_name                          # ODBC DSN
execsql run --dsn postgresql://user:pass@host:5432/db script.sql # Connection URL
```

### Inline scripts

Use `-c` to execute a SQL or metacommand string directly, without a script file:

```sh
execsql run -tl -c "SELECT sqlite_version();" mydb.sqlite
```

### Config-only invocation

When all connection parameters are in a [configuration file](../reference/configuration.md#configuration):

```sh
execsql run script.sql
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

`execsql inspect database`, `inspect schema NAME` and `inspect table NAME` have
their own options: required `--dsn URL` (alias `--connection-string URL`), and
`--output-format text|json` (text by default). Without `--table`, text summarizes
matching objects for `database`; with it, text shows columns and relationships.
`inspect schema NAME` requires an exact, case-sensitive schema name and prints
an overview. `inspect table NAME` requires an exact table/view name and prints
column/key details; its optional `--schema NAME` narrows the search. `database`
retains both optional `--schema NAME` and `--table NAME` filters.
Names are separate components; a dot in a table name is literal.
Text on a terminal
allows a hidden password prompt for a URL user. `-w` / `--no-passwd` disables it;
`--prompt-password` explicitly allows it with JSON output on a terminal.
Redirected stdin and JSON output never prompt automatically. See [schema discovery](../reference/schema.md) for the contract, scope and
adapter support.

The options below belong to `run`: `execsql run -tl script.sql mydb.sqlite`.
`execsql run --help` lists them all. `-h`/`--help` works on every command.
`--version` and `-o`/`--online-help` work on their own (`execsql --version`)
and anywhere on a `run` command line.
`format` has its own options, described in the [formatter guide](../guides/formatter.md);
`lint`'s are in the [lint rules reference](../reference/lint.md); `lsp`'s (`--check`,
`--log-level`, `--log-file`) are in the [language-server command reference](../reference/cli/lsp.md#options).
See the individual references for [config](../reference/cli/config.md), [list](../reference/cli/list.md) and [init](../reference/cli/init.md).

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

    For SQL Server, a port given here (or in `mssql://host:port/db`) connects to `host,port`. With no port, the server name is used as written, so a named instance (`host\SQLEXPRESS`) is found through SQL Server Browser.

`-w`, `--no-passwd`

:   Skip the password prompt when a username is specified. Server databases and ODBC DSNs retain that username; the driver can use its configured password-free authentication or stored credentials. To use the driver's default identity, leave the username unspecified. The same identity rule applies to `password_prompt=No` and `CONNECT ... NEED_PWD=FALSE`.

`-n`, `--new-db`

:   Create a new SQLite, DuckDB or PostgreSQL database if the specified database does not exist.

`--dsn`, `--connection-string` *URL*

:   Database connection URL, e.g. `postgresql://user:pass@host:5432/db`. Supported schemes: `postgresql`, `postgres`, `mysql`, `mariadb`, `mssql`, `sqlserver`, `oracle`, `firebird`, `sqlite`, `duckdb`. Overrides `-t`, `-u`, `-p`, and positional server/database arguments. Passwords included in the URL are used directly without prompting.

    The only query parameter execsql reads is `trust_server_certificate`, for SQL Server: `mssql://user@host/db?trust_server_certificate=yes` accepts a self-signed server certificate (see [`trust_server_certificate`](../reference/configuration.md#config_connect)). Any other parameter is an error.

    As in any URL, characters with a meaning in the URL are percent-encoded in the user name, password and database: a password `p@ss/w:rd#1` is written `p%40ss%2Fw%3Ard%231`, and a literal `%` is `%25`. Python's `urllib.parse.quote(password, safe='')` produces the encoded form.

### Script options

`-c`, `--command` *SCRIPT*

:   Execute an inline SQL/metacommand script string instead of reading from a file. Use shell `$'line1\nline2'` syntax for multi-line scripts. When `-c` is used, no script file argument is required.

`-a`, `--assign-arg` *VALUE*

:   Define the replacement string for a [substitution variable](../reference/substitution_vars.md#substitution_vars) `$ARG_x`. Can be used repeatedly to define `$ARG_1`, `$ARG_2`, etc., in order — the script's positional arguments, like `$1` and `$2` in a shell script. Assignments are [logged](../guides/logging.md#logging). See [Example 9](../guides/examples.md#example9).

`--var` *NAME=VALUE*

:   Set the named substitution variable `!!NAME!!`. Repeatable. It acts like a `[variables]` entry in a [config file](../reference/configuration.md#configuration) but wins over one, and a `SUB` in the script can still reassign it. Names use letters, digits and `_`; the `$`, `&` and `@` prefixes are execsql's own. The value may contain `=`. Assignments are logged with the value hidden.

    ```sh
    execsql run load.sql -tp db.example.com warehouse --var region=west --var month=2026-09
    ```

    Use `-a` when a script takes positional arguments and `--var` when it reads variables by name; both can be given together.

### Encoding options

`-e`, `--database-encoding` *ENCODING*
:   Character encoding used by the database. Only used for some database types. With `-n` on PostgreSQL, the new database is created with this encoding (`CREATE DATABASE ... ENCODING`); PostgreSQL refuses an encoding that differs from its template database's, normally UTF8, and the run stops with its message. Without `-e`, a new PostgreSQL database is UTF8.

`-f`, `--script-encoding` *ENCODING*
:   Character encoding of the script file. Default: `[encoding] script` from a config file, else UTF-8. `format` and `lint` take the same option.

`-g`, `--output-encoding` *ENCODING*
:   Character encoding for WRITE and EXPORT output.

`-i`, `--import-encoding` *ENCODING*
:   Character encoding for data files used with IMPORT.

Valid encoding names can be displayed with `execsql list encodings`. See also [Character Encoding](../guides/encoding.md#encoding).

### Output options

`-d`, `--directories` *{0,1,t,f,y,n}*
:   Create missing output directories for the EXPORT and WRITE metacommands (`y`), or stop with an error when the directory does not exist (`n`, the default). The value is required: `-d y script.sql`, not `-d script.sql`. Equivalent to the [`make_export_dirs`](../reference/configuration.md#make_export_dirs) configuration setting.

`--output-dir` *DIR*
:   Containment root for EXPORT output. Relative paths are resolved beneath this directory; absolute targets must also be inside it. Resolved paths, including symlinks and `..`, cannot escape the root. ZIP archive paths and member names are checked as well. `stdout` is exempt. This flag does not constrain WRITE output or every filesystem operation; see [path restrictions](../reference/security.md#path-containment-roots).

`-l`, `--user-logfile`
:   Write the run log to `~/execsql.log` instead of `execsql.log` in the current directory.

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

### Connection test { #connection_test }

`--ping`

:   Test database connectivity. Connects to the configured database, queries the server version if possible, and prints a one-line summary on success (exit 0). On failure, prints the error message and exits with code 1. `--ping` can be combined with `--dsn` or other connection flags without a `.sql` file, and `-n` creates a missing SQLite, DuckDB or PostgreSQL database as it does for a run.

    ```sh
    execsql run --ping --dsn postgresql://user@host/db
    execsql run --ping -t l mydb.sqlite
    ```

### Preview, debugging and safety options

`-o`, `--online-help`

:   Open the online documentation in the default browser.

`--dry-run`

:   Parse the script (or `-c` command) and print the full command list with source locations, without connecting to a database. Configured required and optional startup includes are listed before the main script and are not executed. Substitution variables already populated at parse time (environment variables, `--assign-arg` and `--var` values, start-time built-ins) are expanded; execution-time variables (`$CURRENT_TIME`, `$DB_NAME`, etc.) and `~`-prefixed locals remain literal.

`--parse-tree`

:   Parse the script into an Abstract Syntax Tree and print a visual tree showing block nesting (IF/LOOP/BATCH/SCRIPT), source line ranges, compound conditions (ANDIF/ORIF), and all metacommands. Does not connect to a database or execute anything. Useful for understanding script structure.

    ```sh
    execsql run --parse-tree script.sql
    ```

`--debug`

:   Start in step-through debug mode. The debug REPL pauses before each statement, as if a `BREAKPOINT` metacommand were inserted at the top of the script with `.next` always active. Type `.continue` or `.c` at the REPL prompt to resume normal execution, or `.next` / `.n` to step one statement at a time. Silently skipped in non-TTY environments.

`--profile`

:   Record the wall-clock execution time of each SQL statement and metacommand. After the script finishes, print a summary table to the console showing elapsed time, percentage of total time, source file and line number, command type, and a preview of the command text. Statements are sorted from slowest to fastest; the top N (default 20, configurable via `--profile-limit`) are displayed. Useful for identifying slow queries or metacommands in long-running scripts.

`--profile-limit` *N*

:   Number of top statements to display in the `--profile` summary (default: 20). Remaining statements are counted and noted in the output footer.

`--manifest` *FILE*

:   Write a JSON record of the run to *FILE* when it ends — whether it succeeded, failed or was halted — for orchestrators and audits that should not have to parse the log. Written atomically; folders in the path are created. Not written for `--dry-run`.

    ```json
    {
      "execsql_version": "2.24.0",
      "script": "load.sql",
      "started": "2026-09-29T14:02:11+00:00",
      "finished": "2026-09-29T14:02:23+00:00",
      "duration_s": 12.4,
      "exit_status": 0,
      "config_files": ["/home/etl/.config/execsql.conf"],
      "database": {"dbms": "PostgreSQL", "server": "db.example.com", "database": "warehouse", "user": "etl"},
      "variables": ["$ARG_1", "region"],
      "statements": {"sql": 42, "metacommands": 17},
      "files_read": [{"source": "load.sql", "line": 12, "by": "IMPORT", "path": "data/orders.csv"}],
      "files_written": [{"source": "load.sql", "line": 30, "by": "EXPORT QUERY", "path": "out/west.csv"}],
      "files_deleted": [],
      "connections": [{"source": "load.sql", "line": 5, "by": "CONNECT", "target": "stage: db2.example.com/staging", "detail": "PostgreSQL, user etl"}],
      "errors": []
    }
    ```

    Files and connections are recorded as each metacommand succeeds, after variable substitution, so paths are the ones used (`out/west.csv`, not `out/!!region!!.csv`); `INCLUDE`d scripts count as files read. When a run fails, `exit_status` is its exit code and `errors` holds the message, its `type`, `source`, `line` and the failing `command`. Errors are retained in execution order even when `ERROR_HALT OFF` or
    `METACOMMAND_ERROR_HALT OFF` lets the script continue. A later successful command
    does not erase them, and a later halting error is recorded once. The original
    halting cause precedes any errors from its `ON ERROR_HALT` script, even if
    that script also stops on an error. `exit_status`
    remains the CLI exit code; a script that carries on to its end can have
    `exit_status: 0` and a nonempty `errors` array. Check both when assessing a run.
    `variables` lists the names set with `-a` and `--var`, not their values. A password (from `--dsn`, a prompt or the keyring), a `SUB_DECRYPT` result, or a common secret shape (a URL's password, `password=...`, an API token) that ends up in a path, a connection target or an error message is written as `***`. Values given with `-a` and `--var` are kept where a path uses them, as in `out/west.csv`, although the log masks them: keep a secret out of `-a` and `--var` if the manifest is collected.

    The path is checked before the run starts: if *FILE* cannot be written (its folder is a file, or not writable), `execsql run` exits 2 before any SQL runs.

`--no-system-cmd`

:   Disable the `SYSTEM_CMD` metacommand. Scripts that attempt to execute an OS command will fail with a clear error. Useful for CI pipelines, shared execution environments, or running semi-trusted scripts. Equivalent to `allow_system_cmd = No` in `execsql.conf` `[config]` section or `allow_system_cmd=False` in the [library API](../api/index.md#library-api). The CLI flag always takes precedence over the config file.

`--no-rm-file`

:   Disable the `RM_FILE` metacommand, so scripts cannot delete files. Fails with a clear error if a script attempts it. Equivalent to `allow_rm_file = No` in `execsql.conf` `[config]` section or `allow_rm_file=False` in the [library API](../api/index.md#library-api). The CLI flag always takes precedence over the config file.

`--no-serve`

:   Disable the [`SERVE`](../reference/metacommands.md#serve) metacommand, so scripts cannot copy a file to stdout with HTTP headers (its CGI use). Fails with a clear error if a script attempts it. Equivalent to `allow_serve = No` in `execsql.conf` `[config]` section or `allow_serve=False` in the [library API](../api/index.md#library-api). The CLI flag always takes precedence over the config file.

`--config` *FILE*

:   Load an explicit configuration file *after* the implicit search paths (system, user, script-dir, working-dir). Its values take precedence over those four; CLI arguments still override everything. The file may chain additional configs via its `[config]` section.

`--version`

:   Show the version number and exit.

See [Configuration Files](../reference/configuration.md#configuration) for the full list of options that can be set via `execsql.conf` instead of (or in addition to) command-line flags.

### Flags that became commands { #former_flags }

These `run` flags are now commands. Each old spelling still works, is hidden
from `execsql run --help`, and prints exactly what its command prints — except
`--lint`, which was removed. Used without a command (`execsql -m`), each prints
a deprecation warning naming its replacement.

| Old flag               | Use instead                                  | Old flag still works?                                                                  |
| ---------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------- |
| `-m`, `--metacommands` | `execsql list metacommands`                  | Yes                                                                                    |
| `-y`, `--encodings`    | `execsql list encodings`                     | Yes                                                                                    |
| `--list-plugins`       | `execsql list plugins`                       | Yes                                                                                    |
| `--dump-keywords`      | `execsql list keywords --output-format json` | Yes                                                                                    |
| `--init-config`        | `execsql config --init`                      | Yes                                                                                    |
| `--lint`               | `execsql lint`                               | No: exits 2 with `run --lint was removed; use execsql lint`, and never runs the script |
