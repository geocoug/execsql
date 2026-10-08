# Syntax and Options { #syntax }

*execsql* is a command-line tool installed via the `execsql2` package. After [installation](installation.md#installation), the `execsql` command is available on your PATH. Run it from a shell prompt on Linux/macOS or a command window on Windows.

*execsql* requires Python 3.10 or later.

## Commands { #commands }

*execsql* is six commands behind one program. Only `run` connects to a database:

```text
execsql run    [OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]
execsql format [--check | -i] [--indent N] FILE_OR_DIR...
execsql lint   [OPTIONS] FILE_OR_DIR...
execsql config [SQL_SCRIPT] [--init] [--config FILE]
execsql list   metacommands|encodings|plugins|keywords [--output-format text|json]
execsql init   [DIR] [--script NAME | --no-script] [--no-config] [--no-pre-commit] [--force]
```

| Command  | Purpose                                                                                    |
| -------- | ------------------------------------------------------------------------------------------ |
| `run`    | Execute a script against a database.                                                       |
| `format` | Normalize metacommand keywords, block indentation, and SQL layout.                         |
| `lint`   | Static analysis without a database. Exits 1 when any error is found.                       |
| `config` | List every config option with its value, default and source; `--init` prints the template. |
| `list`   | Print metacommands, encoding names, installed plugins, or the full keyword vocabulary.     |
| `init`   | Set up a project: `execsql.conf`, a script with a header, and the pre-commit hooks.        |

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
    `lint`, `config`, `list` or `init`, with no extension — must be run
    as `execsql run lint`: a command name always selects
    the command. Names with an extension, such as `lint.sql`, are never
    ambiguous.

### config { #config_command }

```text
execsql config [SQL_SCRIPT] [--init | --validate] [--config FILE] [--output-format text|json]
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
  /home/etl/.config/execsql.conf
  /home/etl/project/scripts/execsql.conf

[connect]
  server    db.example.com  /home/etl/.config/execsql.conf
  db_type   p               /home/etl/project/scripts/execsql.conf
  port                      default
```

Each JSON option has `section`, `key`, `type`, `value`, `default` and
`source` (`null` when the default applies).

#### Validating config files { #config_validate }

A run stops at the first invalid value in a config file, and silently ignores
anything it does not recognize, so a misspelled key simply does nothing.
`--validate` checks every file a run would read — the same files, including
any a `config_file` setting chains to — and reports every problem with its
file and line:

```sh
execsql config --validate                   # the files a run from here would read
execsql config --validate scripts/etl.sql   # plus scripts/execsql.conf
execsql config --validate --config ci.conf  # plus ci.conf
```

```text
~/.config/execsql.conf
  2  warning  unknown key 'sever' in [connect]; did you mean 'server'?
  3  error    db_type = q: Invalid database type: q
  5  warning  unknown section [conect]; did you mean [connect]?
  8  warning  scan_lines belongs in [input], not [interface]

Found 4 problems in 1 file: 1 error, 3 warnings (2 config files checked)
```

| Severity  | Problem                                                                                                                                                        |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `error`   | An invalid value; a missing `[include_required]` file; a file that cannot be parsed (no section header, a key set twice, a bare `%`). A run fails on these.    |
| `warning` | An unknown section or key, with the likely intended name; a key in the wrong section; a `config_file` that names a missing file. A run ignores these silently. |

Values are checked by the same code a run uses, so `--validate` and a run
never disagree about a value. It exits `1` when any error is found; warnings
alone exit `0`. With `--output-format json` it prints
`{"files_checked": [...], "problems": [...]}`, each problem with `file`,
`line`, `severity` and `message`.

### list { #list }

```text
execsql list metacommands|encodings|plugins|keywords [--output-format text|json]
```

| Command        | Prints                                                                                                                        |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `metacommands` | Every metacommand and its syntax.                                                                                             |
| `encodings`    | Every character encoding name accepted by `-e`, `-f`, `-g` and `-i`.                                                          |
| `plugins`      | Installed plugins: metacommands, exporters, importers. See [Plugin System](../dev/architecture.md#plugin-system).             |
| `keywords`     | The full vocabulary: metacommands by category, conditions, CONFIG options, export formats, database types, variable patterns. |

Each list is its own command, `execsql list keywords --help` included. With
`--output-format json`, `keywords` prints the JSON that editor tooling such as
the VS Code grammar generator reads.

### init { #init }

```text
execsql init [DIR] [--script NAME | --no-script] [--no-config] [--no-pre-commit] [--force]
```

Sets up execsql in `DIR` (default: the current directory, created if missing):

| File                           | Content                                                                              | Skip with         |
| ------------------------------ | ------------------------------------------------------------------------------------ | ----------------- |
| `execsql.conf`                 | The commented template, as `execsql config --init` prints it                         | `--no-config`     |
| `main.sql`, or `--script NAME` | A header: PURPOSE, NOTES, PROJECT, COPYRIGHT, AUTHORS, and HISTORY with today's date | `--no-script`     |
| `.pre-commit-config.yaml`      | The `execsql-format` and `execsql-lint` hooks at this version                        | `--no-pre-commit` |

```text
$ execsql init warehouse --script load
  created     warehouse/execsql.conf
  created     warehouse/load.sql
  created     warehouse/.pre-commit-config.yaml
```

Existing files are never changed unless `--force` is given, and even then
`.pre-commit-config.yaml` is only ever added to: if it exists without the
execsql hooks, they are appended under `repos:` in the file's own
indentation, or — when `repos:` is not the file's last key — printed for you to
add by hand. `.sql` is added to a `--script` name without one, and folders in it
are created. To add a script to an existing project:

```sh
execsql init --no-config --no-pre-commit --script scripts/transform.sql
```

The new script passes the `execsql-format` and `execsql-lint` hooks as written.

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

Every command uses the same three exit codes, so a CI step or shell script can
tell a problem in the scripts from a mistake in the command line.

| Code | Meaning                           | Examples                                                                                                                                                                                                                                                                                   |
| ---- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `0`  | Success                           | The script ran; `lint` found no errors (warnings allowed); `format --check` found nothing to change; `run --ping` connected.                                                                                                                                                               |
| `1`  | The task failed or found problems | A script error; `lint` found an error (or any issue, with `--strict`); `format --check` or `--diff` would change a file; `run --ping` could not connect; no `.sql` files were found.                                                                                                       |
| `2`  | Bad command line                  | An unknown option or command, an invalid choice, a missing config file named by `--config`, `run --lint`. Until execsql2 3.0, a first word that is not a command is taken as a script (the deprecated bare form), so a mistyped command exits `1`: `SQL script file "lnt" does not exist`. |

`run` keeps upstream execsql's exit codes where they differ: a missing script
file exits `1`, and unknown options after the script are not rejected.

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

The options below belong to `run`: `execsql run -tl script.sql mydb.sqlite`.
`execsql run --help` lists them all. `-h`/`--help` works on every command.
`--version` and `-o`/`--online-help` work on their own (`execsql --version`)
and anywhere on a `run` command line.
`format` has its own options, described in the [formatter guide](../guides/formatter.md);
`lint`'s are in the [lint rules reference](../reference/lint.md); `config`, `list` and `init`
are described [above](#config_command).

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

:   Parse the script (or `-c` command) and print the full command list with source locations, without connecting to a database. Substitution variables already populated at parse time (environment variables, `--assign-arg` and `--var` values, start-time built-ins) are expanded; execution-time variables (`$CURRENT_TIME`, `$DB_NAME`, etc.) and `~`-prefixed locals remain literal.

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

    Files and connections are recorded as each metacommand succeeds, after variable substitution, so paths are the ones used (`out/west.csv`, not `out/!!region!!.csv`); `INCLUDE`d scripts count as files read. When a run fails, `exit_status` is its exit code and `errors` holds the message, its `type`, `source`, `line` and the failing `command`. `variables` lists the names set with `-a` and `--var`; their values are never written, for the same reason the log hides them, and neither are passwords.

    The path is checked before the run starts: if *FILE* cannot be written (its folder is a file, or not writable), `execsql run` exits 2 before any SQL runs.

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
