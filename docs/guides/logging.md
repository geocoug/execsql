# Logging

*execsql* automatically logs actions, conditions, and errors during script processing. A script file alone is not a definitive record of what happened when:

- Errors occurred
- The user made choices in response to a [PROMPT](../reference/metacommands.md#prompt) metacommand
- The script was cancelled via a [PAUSE](../reference/metacommands.md#pause) metacommand or password prompt from [CONNECT](../reference/metacommands.md#connect)

## Log file location

Log entries are written to a tab-delimited text file named `execsql.log` in the directory from which the script was run. If the `-l` flag or the `user_logfile` [configuration](../reference/configuration.md#configuration) option is used, the file is written to the user's home directory instead.

Messages for each run are appended to the end of the log file. On POSIX, execsql
attempts to restrict the file to owner read/write permissions (`0600`). It closes
the file at exit; it does not make it read-only.

Before its final `exit` record, a run writes an ordinary `status`/`info` summary:

```text
Run finished: completed_with_errors; exit=0; attempted=12; errors=1; warnings=2; duration=1.230s
```

The summary distinguishes a clean success from a script that continued after errors.
It also reports failed, halted, interrupted, terminated or unknown outcomes. An
error-free `HALT EXIT_STATUS 0` is a success. Counts include attempted executable
nodes, even a command that fails or halts; warnings count logged warning records.
Durations use a monotonic clock. The existing TSV record columns are unchanged.
The optional [run manifest](../getting-started/syntax.md#options) contains the same
`run_id` as the log, so callers can match the two without guessing from filenames
or timestamps.

## Record types

Each line starts with a record type, followed by a run identifier (a compact date-time representation shared by all records from the same run). The remaining fields depend on the record type:

### `run`

Information about the run as a whole.

| Field          | Description                  |
| -------------- | ---------------------------- |
| Record type    | `run`                        |
| Run identifier | Compact date-time string     |
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

| Field           | Description                        |
| --------------- | ---------------------------------- |
| Record type     | `connect`                          |
| Run identifier  | Compact date-time string           |
| Sequence number | Auto-generated order               |
| Timestamp       | ISO 8601 event time                |
| Database info   | DBMS type and database identifiers |

### `action`

Significant actions carried out by the script.

| Field           | Description                                                                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Record type     | `action`                                                                                                                                            |
| Run identifier  | Compact date-time string                                                                                                                            |
| Sequence number | Auto-generated order of actions, status messages, and errors                                                                                        |
| Timestamp       | ISO 8601 event time                                                                                                                                 |
| Action type     | `export` ([EXPORT](../reference/metacommands.md#export) executed) or `prompt_quit` (user choice from [PROMPT](../reference/metacommands.md#prompt)) |
| Line number     | Script line where the action occurred                                                                                                               |
| Description     | Free text                                                                                                                                           |

### `status`

Status messages, typically errors.

| Field           | Description                               |
| --------------- | ----------------------------------------- |
| Record type     | `status`                                  |
| Run identifier  | Compact date-time string                  |
| Sequence number | Auto-generated order                      |
| Timestamp       | ISO 8601 event time                       |
| Status type     | `info`, `warning`, `exception` or `error` |
| Description     | Free text                                 |

### `exit`

Program status at exit. Every run writes exactly one, as the last record of its section, whether it ends normally, with an error, at a `HALT` or a cancelled prompt, with Ctrl-C, or with SIGTERM (`kill`, `timeout`, `docker stop`, a cancelled CI job). A section with no `exit` record belongs to a run that is still going or was killed with SIGKILL.

| Field           | Description                                                                                                                                                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Record type     | `exit`                                                                                                                                                                                                                             |
| Run identifier  | Compact date-time string                                                                                                                                                                                                           |
| Exit type       | `end_of_script` (normal), `halt` ([HALT](../reference/metacommands.md#halt) executed or a prompt cancelled), `error`, `exception`, `interrupted` (Ctrl-C), `terminated` (SIGTERM), or `unknown` (the process ended some other way) |
| Source location | Script path and line formatted as `path(line)`; empty components are possible                                                                                                                                                      |
| Description     | Free text                                                                                                                                                                                                                          |
| Elapsed         | Total wall-clock run duration                                                                                                                                                                                                      |

### `sql`

Each executed SQL statement, when the [`log_sql`](../reference/configuration.md#log_sql) config option (or `CONFIG LOG_SQL ON` metacommand) is enabled.

| Field           | Description              |
| --------------- | ------------------------ |
| Record type     | `sql`                    |
| Run identifier  | Compact date-time string |
| Sequence number | Auto-generated order     |
| Timestamp       | ISO 8601 event time      |
| Database        | Active database name     |
| Line number     | Script line              |
| Query           | The SQL text             |

### `import_progress`

Periodic row-count status lines during an `IMPORT`, written every N rows when the [`import_progress_interval`](../reference/configuration.md#import_progress_interval) config option is set to a positive integer. A final completion line is also written.

### Per-event timestamps

`status`, `connect`, `action`, `sql` and `user_msg` records include an ISO 8601 timestamp field in addition to the run identifier. The run identifier itself uses millisecond precision (`%Y%m%d_%H%M_%S_NNN`).

## Custom logging

- The [LOG](../reference/metacommands.md#log) metacommand writes additional messages to the log file.
- The [LOG_WRITE_MESSAGES](../reference/metacommands.md#logwritemessages) metacommand echoes all [WRITE](../reference/metacommands.md#write) output to the log file.
- The `$RUN_ID` [system variable](../reference/substitution_vars.md#system_vars) links other output to the run recorded in the log file.
