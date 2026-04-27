# Divergence from Upstream

execsql2 is a maintained fork of [execsql](https://execsql.readthedocs.io/)
v1.130.1 by R. Dreas Nielsen. This page documents all user-visible changes
since the fork was created: new features, changed behavior, security fixes,
and removed functionality.

For a chronological view, see the [Change Log](change_log.md).

______________________________________________________________________

## Added Features

### CLI Options

| Flag                            | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--version`                     | Print version and exit (Rich-formatted).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `-c` / `--command`              | Execute an inline SQL or metacommand string instead of a script file.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `--dsn` / `--connection-string` | Accept a standard database URL (e.g. `postgresql://user:pass@host/db`). Supports `postgresql`, `mysql`, `mssql`, `oracle`, `firebird`, `sqlite`, and `duckdb` schemes.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `--output-dir`                  | Set a default base directory for export output files.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `--progress`                    | Show a Rich progress bar during long-running IMPORT operations.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `--dump-keywords`               | Emit all metacommand keywords, conditionals, config options, and export formats as structured JSON.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `--config FILE`                 | Load an explicit configuration file after the implicit search paths. Its values take precedence over system, user, script-dir, and working-dir config files; CLI arguments still override everything. The file may chain additional configs via its `[config]` section.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `--gui-framework`               | Select GUI backend: `tkinter` (default) or `textual` (terminal UI).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `--debug`                       | Start in step-through debug mode. The debug REPL pauses before each statement, as if `BREAKPOINT` were at the top with `.next` always active.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `--dry-run`                     | Parse the script and print the full command list without connecting to a database or executing anything. Substitution variables already populated at parse time (env vars, `--assign-arg` values, built-in start-time vars) are expanded in the output; execution-time variables (`$DB_NAME`, `$CURRENT_TIME`, etc.) remain unexpanded.                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `--profile`                     | Record wall-clock time for each SQL and metacommand statement. After the script completes, print a summary table sorted by elapsed time (descending), showing time, percentage of total, source location, command type, and a command preview.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `--profile-limit N`             | Number of top statements to display in the `--profile` summary (default: 20). Remaining statements are counted and noted in the output footer.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `--ping`                        | Test database connectivity and exit. Connects using the supplied connection parameters, queries for the server version, and prints a one-line success message (exit 0) or the error (exit 1). No script file argument is required.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `--lint`                        | Parse the script and perform static analysis without connecting to a database. Reports unmatched IF/ENDIF, LOOP/END LOOP, and BEGIN BATCH/END BATCH blocks (errors); potentially undefined `!!$VAR!!` references (warnings); missing INCLUDE file targets (warnings); and unknown `EXECUTE SCRIPT` targets (warnings). Variable analysis uses two passes so definition order does not matter. The linter descends into named script blocks reached via `EXECUTE SCRIPT` / `EXEC SCRIPT` / `RUN SCRIPT`, reads `SUB_INI` INI files at lint time, recognizes `SUB_EMPTY` / `SUB_ADD` / `SUB_APPEND` / `SUBDATA` as definitions, suppresses false warnings for `$COUNTER_N`, and auto-discovers built-in system variables from the installed source. Exits 0 if no errors, 1 if errors found. |

### Export Formats

| Format            | Description                                                                                                          |
| ----------------- | -------------------------------------------------------------------------------------------------------------------- |
| `PARQUET`         | Export query or table results to Apache Parquet via `polars`.                                                        |
| `FEATHER`         | Export to Apache Feather/IPC via `polars` (upstream used `pandas` + `pyarrow`).                                      |
| `YAML`            | Export query or table results as a YAML sequence of mappings via `PyYAML`.                                           |
| `MARKDOWN` / `MD` | Export query or table results as a GitHub-Flavored Markdown (GFM) pipe table. Pure Python, no optional dependencies. |
| `XLSX`            | Export query or table results to an Excel XLSX workbook via `openpyxl` (single or multi-sheet).                      |

### Metacommands

| Metacommand            | Description                                                                                                                                                                                                                                                                                                                                                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ASSERT`               | Evaluate a condition and raise an error (halting the script) if it is false. Supports all IF conditions. Optional quoted failure message. Skipped in false IF blocks.                                                                                                                                                                                                                                                    |
| `BREAKPOINT`           | Pause script execution and drop into an interactive debug REPL. See [Debugging](#debugging) below for full details.                                                                                                                                                                                                                                                                                                      |
| `CONFIG SHOW_PROGRESS` | Enable the Rich progress bar for IMPORT operations at runtime.                                                                                                                                                                                                                                                                                                                                                           |
| `CONFIG LOG_SQL`       | Enable SQL query audit logging — writes executed SQL to the log file.                                                                                                                                                                                                                                                                                                                                                    |
| `PG_UPSERT`            | QA-checked, FK-dependency-ordered upserts from staging to base schema on PostgreSQL. Integrates [pg-upsert](https://pg-upsert.readthedocs.io/) as an optional dependency. Three modes: full pipeline, QA-only, and schema check. Supports `EXPORT_FAILURES`, `EXPORT_FORMAT`, `EXPORT_MAX_ROWS`, and `STRICT_COLUMNS` keywords. `STRICT_COLUMNS` forces all missing columns to be errors (requires `pg-upsert>=1.22.0`). |
| `IMPORT … FROM JSON`   | Import a JSON file (array of objects or NDJSON) into a database table. Nested objects are flattened with dot-separated column names; arrays are stored as JSON strings.                                                                                                                                                                                                                                                  |

### Conditional Tests

| Conditional               | Description                                                                                              |
| ------------------------- | -------------------------------------------------------------------------------------------------------- |
| `ROW_COUNT_GT(table, N)`  | True if the number of rows in *table* is strictly greater than *N* (integer). Queries `SELECT count(*)`. |
| `ROW_COUNT_GTE(table, N)` | True if the number of rows in *table* is greater than or equal to *N*.                                   |
| `ROW_COUNT_EQ(table, N)`  | True if the number of rows in *table* is exactly equal to *N*.                                           |
| `ROW_COUNT_LT(table, N)`  | True if the number of rows in *table* is strictly less than *N*.                                         |

### Configuration Options

New options in `execsql.conf`:

| Option                     | Section       | Description                                                       |
| -------------------------- | ------------- | ----------------------------------------------------------------- |
| `use_keyring`              | `[connect]`   | Use the OS keyring for credential storage (default: `yes`).       |
| `show_progress`            | `[input]`     | Enable Rich progress bar for IMPORT (default: `no`).              |
| `import_progress_interval` | `[input]`     | Log a status line every N rows during IMPORT (default: `0`).      |
| `gui_framework`            | `[interface]` | GUI backend: `tkinter` (default) or `textual` (terminal UI).      |
| `log_sql`                  | `[config]`    | Enable SQL audit logging (default: `no`).                         |
| `max_log_size_mb`          | `[config]`    | Rotate the log file at this size in MB (default: `0` = disabled). |
| `macos_config_file`        | `[config]`    | Additional config file path, active only on macOS.                |

### Tools

| Tool             | Description                                                                                                                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `execsql-format` | Standalone CLI for normalizing metacommand indentation and uppercasing SQL keywords. Supports `--check` and `--in-place` modes. Also available as a [pre-commit hook](../guides/formatter.md). |

### GUI

| Feature              | Description                                                                                                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Textual TUI backend  | Full terminal-UI backend via the `textual` library. Provides all dialog types (password, pause, message, entry, compare, action, etc.) in the terminal.                |
| Console fallback     | Text-only backend that handles GUI calls in headless environments by printing to stdout.                                                                               |
| Table row counts     | All GUI backends (Tkinter, Textual, Console) display a row count footer below every table widget (e.g. "3 rows", "1 row").                                             |
| Help URL button      | Dialogs that accept the `HELP` keyword display a clickable Help button that opens the URL in the system browser.                                                       |
| Compare diff summary | The compare dialog shows a one-line summary of matching, differing, and table-exclusive rows when key columns are specified.                                           |
| Compare cell markers | When diff highlighting is active, individual cells that differ within a changed row are prefixed with a bullet marker across all backends (Tkinter, Textual, console). |
| Form validation      | `PROMPT ENTRY_FORM` enforces `validation_regex` (on submit) and `validation_key_regex` (per-keystroke) across all backends. Required fields validated.                 |

### Authentication

| Feature                       | Description                                                                                                                                                                    |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OS keyring integration        | When the `keyring` package is installed, passwords are stored in and retrieved from the OS credential store (macOS Keychain, Windows Credential Manager, Linux SecretService). |
| Keyring retry on auth failure | If a stored password is rejected, the stale entry is deleted, the user is re-prompted, and the new password is saved automatically.                                            |

### Logging Enhancements

| Feature                       | Description                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| Per-event ISO 8601 timestamps | `status`, `connect`, `action`, and `user_msg` log entries include a timestamp.     |
| Run duration in exit record   | The `exit` log record includes elapsed wall-clock time.                            |
| Run ID millisecond precision  | Run identifier format changed from `%Y%m%d_%H%M_%S` to `%Y%m%d_%H%M_%S_NNN`.       |
| SQL audit log record          | New `sql` record type containing DB name, line number, and query text.             |
| Import progress log           | Periodic row-count status lines during IMPORT when `import_progress_interval > 0`. |

### Developer / Packaging

| Feature                      | Description                                                                                                                                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| VS Code syntax highlighting  | Auto-generated `tmLanguage.json` grammar from the dispatch table.                                                                                                                            |
| `py.typed` marker            | PEP 561 marker enabling downstream static type checking.                                                                                                                                     |
| Structured keyword registry  | `--dump-keywords` introspects the dispatch table and outputs JSON used by the grammar generator and test suite.                                                                              |
| `python-dateutil` dependency | Date/time parsing delegates to `dateutil.parser.parse()` instead of 231 hardcoded `strptime` format strings. Handles ISO 8601 `T` separators, microseconds, `Z` suffix, and named timezones. |

### Debugging { #debugging }

execsql2 adds a full interactive debugging system that has no equivalent in upstream execsql.

**`BREAKPOINT` metacommand** — insert `-- !x! BREAKPOINT` anywhere in a script to pause execution and drop into a debug REPL. The REPL provides a `execsql debug>` prompt where you can inspect state and interact with the database before resuming.

**`--debug` CLI flag** — start the script in step-through mode, pausing before every statement as if `BREAKPOINT` were inserted at the top with `.next` always active.

**REPL commands** (all dot-prefixed to avoid collisions with variable names and SQL):

| Command                | Description                                                               |
| ---------------------- | ------------------------------------------------------------------------- |
| `.continue` / `.c`     | Resume normal script execution                                            |
| `.abort` / `.q`        | Halt the script with exit status 1                                        |
| `.vars` / `.v`         | List all user, system, local, and counter variables (grouped by type)     |
| `.vars all` / `.v all` | Include environment variables (`&`) in the listing                        |
| `.next` / `.n`         | Execute the next statement, then pause again (step mode)                  |
| `.where` / `.w`        | Show the current script file, line number, and upcoming statement text    |
| `.stack`               | Show the command-list stack (script name, cursor position, nesting depth) |
| `.set VAR VAL` / `.s`  | Set or update a substitution variable; prints confirmation on success     |
| `.help` / `.h`         | Show available commands                                                   |

**Non-prefixed input** is interpreted as either a variable lookup or ad-hoc SQL:

| Input                          | Behavior                                                                         |
| ------------------------------ | -------------------------------------------------------------------------------- |
| `logfile`                      | Print the value of the `logfile` substitution variable                           |
| `$ARG_1`                       | Print the value of a system/built-in variable                                    |
| `SELECT count(*) FROM orders;` | Execute SQL against the current database and pretty-print the results in a table |

**Key behaviors:**

- **Non-interactive safety** — `BREAKPOINT` is silently skipped when `sys.stdin` is not a TTY (CI pipelines, piped input, cron). Scripts never hang in automation.
- **Ad-hoc SQL** — any input ending with `;` is executed against the current database connection using the same cursor and transaction state as the script. Queries return a formatted table; DML statements (INSERT, UPDATE, DELETE) execute and commit/rollback according to the current autocommit and batch settings.
- **Variable inspection** — bare names look up user-defined variables (e.g., `logfile`); sigil-prefixed names look up system (`$`), environment (`&`), local (`~`), or counter (`@`) variables. If a `$`-prefixed name isn't found, the REPL strips the sigil and retries (since `SUB` stores keys without a prefix).
- **Step mode** — `.next` executes exactly one statement then re-enters the REPL. When stepping, the entry banner shows "Step" instead of "Breakpoint" to distinguish stepping from an explicit `BREAKPOINT`. Combined with `.where`, `.vars`, and SQL queries, this allows line-by-line script debugging with full state visibility.
- **Location display** — on entry to the REPL (via `BREAKPOINT` or step mode) the banner shows a horizontal rule with the label ("Breakpoint" or "Step"), the current filename and line number, and the upcoming statement. Use `.where` (or `.w`) at any time to re-display this information.
- **ANSI color output** — the REPL uses ANSI color on TTY outputs: bold yellow for section labels, cyan for filenames and variable names, dim for separators and `=` signs, red for error messages, bold for SQL column headers, and dim italic for `NULL` values. Color is suppressed when `NO_COLOR` or `EXECSQL_NO_COLOR` environment variables are set, or when the output stream is not a TTY.
- **Readline support** — on platforms where `readline` is available (macOS, Linux), the REPL supports arrow-key history navigation and line editing.

______________________________________________________________________

## Changed Behavior

### CLI Interface

The CLI framework changed from `optparse` to [Typer](https://typer.tiangolo.com/) with Rich-formatted help text. All original short flags (`-a` through `-z`) are preserved. The tool can be invoked as either `execsql` or `execsql2`.

### Configuration

- **`linux_config_file`** — now only active on Linux (`sys.platform == "linux"`). Upstream applied it to all POSIX systems, including macOS. A new `macos_config_file` option handles macOS specifically.

### Internal State Management

All 33 mutable runtime globals in `state.py` have been consolidated into a `RuntimeContext` object. The module uses a transparent proxy so existing code is unaffected, but the architecture now supports isolated contexts for testing and future concurrent execution.

### Substitution Variables

- **`$HOSTNAME`** — Network name of the machine running execsql (`platform.node()`). Useful for log messages and environment detection.
- **`$SYSTEM_CMD_PID`** — New system variable set to the PID of the background process when `SHELL … CONTINUE` is used.
- **Cycle detection** — `substitute_vars()` raises an error after 100 iterations to prevent infinite loops when variables reference each other cyclically. Upstream had no protection.
- **O(1) substitution** — Variable substitution uses a single combined regex and dict lookup instead of O(V) per-variable regex passes. Behavior is identical; performance is improved.
- **Lazy `$RANDOM`/`$UUID`** — These system variables are now computed on first access rather than generated unconditionally for every statement. Behavior is identical when referenced; scripts that never reference them skip the computation entirely.
- **Static/dynamic system var split** — System substitution variables are split into static (set once per script and refreshed on CONNECT/CHDIR) and dynamic (refreshed per statement). Eliminates redundant `Path.resolve()` syscalls and database pool lookups per statement.

### CSV Import

- **Fast-path CSV reader** — Standard delimited imports (comma, tab, semicolon, pipe with doubled-quote escaping) now use Python's `csv` module. Non-standard formats (space-delimiter collapsing, escape characters) fall back to the original character-at-a-time parser.

### Database Adapters

- **`Database` is an ABC** — `open_db()` and `exec_cmd()` are abstract methods. Subclasses that omit them raise `TypeError` at instantiation instead of at call time.
- **Connection timeouts** — PostgreSQL and SQLite adapters accept a connection timeout parameter (default 30 seconds).
- **DuckDB temporal types** — `TIMESTAMPTZ`, `TIMESTAMP`, `DATE`, `TIME` now map to native DuckDB types instead of `TEXT`.

### Error Handling

- **Exception hierarchy** — All custom exceptions inherit from `ExecSqlError`, enabling `except ExecSqlError` to catch any execsql-originated error.
- **Exception chaining** — All `raise` statements inside `except` blocks preserve the original traceback via `from`.
- **ASSERT error type** — `ASSERT` failures now use a dedicated `"assert"` error type that produces `**** Assertion failed.` instead of `**** Error in metacommand.`. This distinguishes intentional script-level checks from actual metacommand errors. Upstream did not have `ASSERT`.

______________________________________________________________________

## Security and Correctness Fixes

These are behavioral changes driven by security or correctness issues in the upstream code.

### Injection Fixes

| Area                         | Fix                                                                                                                                                                                                  |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Database metadata queries    | `schema_exists()`, `table_exists()`, `column_exists()`, `table_columns()`, `view_exists()`, `role_exists()` across all 9 adapters now use parameterized queries. Upstream used string interpolation. |
| `import_entire_file()`       | Column names are quoted with `quote_identifier()` instead of interpolated into INSERT statements.                                                                                                    |
| PostgreSQL `CREATE DATABASE` | Database name and encoding are quoted. COPY delimiter and quote character are validated.                                                                                                             |
| MySQL `LOAD DATA INFILE`     | File path, delimiter, and quotechar are now escaped with `replace("'", "''")` before interpolation into the SQL statement.                                                                           |
| `$SHEETS_TABLES_VALUES`      | Sheet names from ODS/XLS imports are escaped before embedding in SQL.                                                                                                                                |
| HTTP `Content-Disposition`   | Filename is sanitized to prevent HTTP response splitting in SERVE.                                                                                                                                   |

### Template and Export Safety

| Area              | Fix                                                                                                    |
| ----------------- | ------------------------------------------------------------------------------------------------------ |
| Jinja2 sandboxing | Templates run in `SandboxedEnvironment` instead of the default `jinja2.Template`.                      |
| HTML export       | Column headers and cell values are escaped with `html.escape()` to prevent XSS.                        |
| XML export        | Values are escaped with `xml.sax.saxutils.escape()`. Invalid XML element name characters are replaced. |
| JSON export       | The `description` field and all column names use `json.dumps()` instead of string interpolation.       |

### Credential and Logging Safety

| Area                         | Fix                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------ |
| ODBC password redaction      | Connection strings in log output have `Pwd=***` substituted before logging.                |
| `enc_password` documentation | Prominent warnings that XOR encryption is obfuscation only — keys are hardcoded in source. |

### Bug Fixes

| Area                                                | Fix                                                                                                                                                                                                                                                                                                    |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Oracle default port                                 | Corrected from `5432` (PostgreSQL) to `1521`.                                                                                                                                                                                                                                                          |
| MySQL `LOAD DATA INFILE` encoding                   | Python encoding names are now mapped to MySQL charset names.                                                                                                                                                                                                                                           |
| `dt_cast` type converters                           | Base `Database` class auto-populates 8 type converters that were previously left empty after the refactor.                                                                                                                                                                                             |
| `FileWriter` CPU busy-loop                          | Uses blocking `queue.get(timeout=0.1)` instead of `get_nowait()` in a tight loop.                                                                                                                                                                                                                      |
| Substitution variable cycles                        | 100-iteration limit prevents infinite loops on cyclic variable references.                                                                                                                                                                                                                             |
| Script location in error messages                   | `ErrInfo.script_file` and `script_line_no` are now populated via `stamp_errinfo()` so error output includes "Line N of script foo.sql" context — restoring behavior present in the monolith.                                                                                                           |
| `$ERROR_MESSAGE` not updated                        | `$ERROR_MESSAGE` is now set on every error path: `exit_now()`, non-halting SQL errors, and non-halting metacommand errors. Previously it was initialized to `""` and never changed.                                                                                                                    |
| Metacommand error message lost                      | When `halt_on_metacommand_err` is `ON`, the original handler `ErrInfo` is now re-raised; the generic "Unknown metacommand" message no longer replaces the specific error from the handler.                                                                                                             |
| Empty script name in error msg                      | `_execute_script_direct()` and `_execute_script_textual_console()` no longer append "in script , line 0" to uncaught-exception messages when `current_script_line()` returns an empty string.                                                                                                          |
| `PROMPT COMPARE` diff comparison                    | Diff engine uses native Python equality instead of string comparison — numeric types, Decimals, and booleans compare correctly. `None` is distinguished from empty string. Columns are matched by name (not position), key columns are excluded from comparison, and duplicate PKs keep the first row. |
| `win_config_file` broken                            | Checked `os.name == "windows"` which Python never returns (correct value is `"nt"`). Fixed to `os.name == "nt"`. Inherited from upstream.                                                                                                                                                              |
| `NumericParser` right-associative                   | Arithmetic operators were parsed right-to-left. `10 - 3 - 2` evaluated as `9` instead of `5`. Fixed to left-associative parsing. Inherited from upstream.                                                                                                                                              |
| Empty-column check precedence                       | `DataTable` and `Database.populate_table()` had an operator precedence bug in the extra-column emptiness check — a redundant `and conf.del_empty_cols` caused incorrect short-circuit evaluation. Inherited from upstream.                                                                             |
| SQLite import string processing                     | `SQLiteDatabase.populate_table()` applied `trim_strings`, `replace_newlines`, and `empty_strings` after copying row data, so processing never reached the INSERT. Fixed to process before extraction. Inherited from upstream.                                                                         |
| `$CURRENT_DATABASE`/`$CURRENT_DBMS` stale after USE | These variables were only set at startup and on CONNECT, not refreshed when `USE` switched the active database. Now set in `set_static_system_vars()` so they update on any connection change.                                                                                                         |
| `DT_Text.data_type_name` wrong                      | Was `"character"` (same as `DT_Character`), making error messages indistinguishable. Corrected to `"text"`. Inherited from upstream.                                                                                                                                                                   |
| `DT_Varchar` non-string data unchecked              | `_from_data()` only enforced the 255-char limit for `str` inputs; non-string values passed through without conversion or length check. Inherited from upstream.                                                                                                                                        |
| `WriteHooks.write_err()` crash on empty string      | `strval[-1]` raised `IndexError` on empty input. Fixed to use `str.endswith()`. Inherited from upstream.                                                                                                                                                                                               |
| `NumericParser` division by zero                    | `NumericAstNode.eval()` raised unhandled `ZeroDivisionError`. Now raises `NumericParserError` with a clear message. Inherited from upstream.                                                                                                                                                           |
| `CondAstNode.eval()` could return `None`            | Missing fallthrough for unknown node types silently returned `None`. Now raises `CondParserError`. Inherited from upstream.                                                                                                                                                                            |
| `DT_Timestamp` claims time-only values              | `dateutil.parser.parse()` silently fills in today's date for bare time strings like `"13:15:45"`, so `DT_Timestamp` matched before `DT_Time` in the inference order. `parse_datetime()` now rejects time-only strings. Inherited from upstream.                                                        |
| `CounterVars.substitute` skipped pos 0–1            | `re.I` was passed as the positional `pos` argument, skipping the first 2 characters of every string during counter variable expansion. Counter variables at the very start of a line were never matched. Inherited from upstream.                                                                      |
| `exec_cmd` (SQLite/DuckDB) always raised TypeError  | Passed bytes to `curs.execute()` via `.encode()`, which Python 3 `sqlite3`/`duckdb` reject. `EXECUTE PROCEDURE` metacommand was non-functional on these backends. Inherited from upstream.                                                                                                             |
| MySQL `LOAD DATA INFILE` injection                  | File path, delimiter, and quotechar were interpolated without escaping. Now single-quotes are escaped consistent with the PostgreSQL COPY path. Inherited from upstream.                                                                                                                               |
| Config file chain infinite loop                     | The `config_file` directive could chain config files without limit. A circular reference (via symlinks or different relative paths) caused an infinite loop at startup. Now capped at 20 files. Inherited from upstream.                                                                               |
| Cursor leaks in database adapters                   | ~15 methods across all adapters used `curs = self.cursor()` / `curs.close()` without `try/finally`. If the query raised, the cursor leaked. Converted to `with self._cursor() as curs:`. Inherited from upstream.                                                                                      |
| JSON export malformed on special column names       | Column names containing `"` or `\` produced invalid JSON. Now uses `json.dumps()` for all field names. Inherited from upstream.                                                                                                                                                                        |
| Temp file creation TOCTOU race                      | `TempFileMgr.new_temp_fn()` discarded the `NamedTemporaryFile` handle, creating a race window. Now uses `tempfile.mkstemp()` for secure creation. Inherited from upstream.                                                                                                                             |
| `shlex.split` on Windows incorrect mode             | Called without `posix=False` on Windows, mishandling backslash-heavy paths in SHELL commands. Inherited from upstream.                                                                                                                                                                                 |

______________________________________________________________________

## Removed Features

| Feature                            | Reason                                                                                                                                                                                  |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Airspeed template processor        | The `airspeed` library (Velocity clone) is unmaintained since ~2018. Use `FORMAT jinja` instead. The `airspeed` value for `template_processor` in `execsql.conf` is no longer accepted. |
| Python 2 compatibility             | All Python 2 constructs (`stringtypes`, `u""` literals, `optparse`, etc.) have been removed. execsql2 requires Python 3.10+.                                                            |
| `FREE` keyword on `PROMPT DISPLAY` | The non-blocking display behavior was only implemented in the console backend; the Textual and Tkinter GUI backends ignored it. Removed rather than partially supported.                |
