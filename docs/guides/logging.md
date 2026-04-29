# Logging

*execsql* automatically logs actions, conditions, and errors during script processing. A script file alone is not a definitive record of what happened when:

- Errors occurred
- The user made choices in response to a [PROMPT](../reference/metacommands.md#prompt) metacommand
- The script was cancelled via a [PAUSE](../reference/metacommands.md#pause) metacommand or password prompt from [CONNECT](../reference/metacommands.md#connect)

## Log file location

Log entries are written to a tab-delimited text file named `execsql.log` in the directory from which the script was run. If the `-l` flag or the `user_logfile` [configuration](../reference/configuration.md#configuration) option is used, the file is written to the user's home directory instead.

Messages for each run are appended to the end of the log file. The log file is set to read-only when *execsql* exits.

## Record types

Each line starts with a record type, followed by a run identifier (a compact date-time representation shared by all records from the same run). The remaining fields depend on the record type:

### `run`

Information about the run as a whole.

| Field          | Description                  |
| -------------- | ---------------------------- |
| Record type    | `run`                        |
| Run identifier | Compact date-time string     |
| Script name    | Name of the script file      |
| Script path    | Full path to the script file |
| Revision date  | Script file revision date    |
| File size      | Script file size in bytes    |
| User name      | OS user who ran the script   |
| Options        | Command-line options used    |

### `run_db_file`

File-based database used (Access, SQLite, or DuckDB).

| Field          | Description                    |
| -------------- | ------------------------------ |
| Record type    | `run_db_file`                  |
| Run identifier | Compact date-time string       |
| Database file  | Full path to the database file |

### `run_db_server`

Server-based database used (PostgreSQL, MySQL, MariaDB, Firebird, Oracle, or SQL Server).

| Field          | Description              |
| -------------- | ------------------------ |
| Record type    | `run_db_server`          |
| Run identifier | Compact date-time string |
| Server name    | Database server hostname |
| Database name  | Name of the database     |

### `connect`

A database connection was established (file-based or client-server).

| Field          | Description                        |
| -------------- | ---------------------------------- |
| Record type    | `connect`                          |
| Run identifier | Compact date-time string           |
| Database info  | DBMS type and database identifiers |

### `action`

Significant actions carried out by the script.

| Field           | Description                                                                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Record type     | `action`                                                                                                                                            |
| Run identifier  | Compact date-time string                                                                                                                            |
| Sequence number | Auto-generated order of actions, status messages, and errors                                                                                        |
| Action type     | `export` ([EXPORT](../reference/metacommands.md#export) executed) or `prompt_quit` (user choice from [PROMPT](../reference/metacommands.md#prompt)) |
| Line number     | Script line where the action occurred                                                                                                               |
| Description     | Free text                                                                                                                                           |

### `status`

Status messages, typically errors.

| Field           | Description              |
| --------------- | ------------------------ |
| Record type     | `status`                 |
| Run identifier  | Compact date-time string |
| Sequence number | Auto-generated order     |
| Status type     | `exception` or `error`   |
| Description     | Free text                |

### `exit`

Program status at exit.

| Field          | Description                                                                                                                   |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Record type    | `exit`                                                                                                                        |
| Run identifier | Compact date-time string                                                                                                      |
| Exit type      | `end_of_script` (normal), `prompt_quit`, `halt` ([HALT](../reference/metacommands.md#halt) executed), `error`, or `exception` |
| Line number    | Script line that triggered the exit (may be null)                                                                             |
| Description    | Free text                                                                                                                     |

## Custom logging

- The [LOG](../reference/metacommands.md#log) metacommand writes additional messages to the log file.
- The [LOG_WRITE_MESSAGES](../reference/metacommands.md#logwritemessages) metacommand echoes all [WRITE](../reference/metacommands.md#write) output to the log file.
- The `$RUN_ID` [system variable](../reference/substitution_vars.md#system_vars) links other output to the run recorded in the log file.
