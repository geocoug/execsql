# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries prior to `2.0.0` are from the upstream
[execsql](https://execsql.readthedocs.io/) project by R.Dreas Nielsen.

______________________________________________________________________

## [Unreleased]

### Added

- **`EXPORT … AS JSONL` and `EXPORT QUERY … AS JSONL`** write [JSON Lines](https://jsonlines.org/): one object per row, one row per line. `APPEND` adds rows to the file, which stays valid; `IMPORT … FROM JSON` reads it back.

### Changed

- **A value with a fraction loaded into an integer column** (`INTEGER`, `BIGINT`, `DECIMAL(10,0)`, …) of an existing table by `IMPORT` or `COPY` stops the load with an error that names the value and the column, and nothing is loaded. The database used to round it (`1.5` stored as `2`), or on SQL Server truncate it. A delimited file loaded into PostgreSQL or MySQL is not affected: the server reads it as written. Round the values in the source, or load them into a `DECIMAL` column with places for the fraction.
- **MySQL / MariaDB sessions run in strict mode**: a SQL statement, `IMPORT` or `COPY` that gives a column a value MySQL can't store as given stops with MySQL's error, and nothing is loaded. MySQL used to store a changed value with a warning (`3000000000` as `2147483647`, `2024-02-30` as `0000-00-00`, `abcdef` in a `VARCHAR(3)` as `abc`). A timestamp ending in `Z` is one such value: write it with `+00:00`. To keep the old behavior in a script, run `SET SESSION sql_mode = 'ANSI';` after connecting.
- **Scripts with many substitution variables run faster**: a statement or metacommand with no `!!`, `!'!` or `!"!` in it is no longer checked against every defined variable. With 500 variables each such line took about 0.1 ms longer; a 1,000-pass `LOOP` over `EXECUTE SCRIPT` with 200 variables now runs in half the time.

### Fixed

- **`IMPORT` and `COPY` into a table that already exists** convert each value by the type of the column it goes into, not the type guessed from the source data. A text column gets the value as written: `yes`, `1`, `01/05/2024`, `1e3` and `" 7 "` were stored as `true`, `true`, `2024-01-05 00:00:00`, `1000` and `7`. On MySQL a missing value in such a column is NULL, not `''`. `TO NEW` and `TO REPLACEMENT` tables are created and filled as before.
- **`COPY` of a column of 0s and 1s into a PostgreSQL integer, numeric or float column** loads the numbers; it failed with "column … is of type integer but expression is of type boolean". The same goes for true/false values (`yes`/`no`, `t`/`f`) copied, or imported from a spreadsheet, JSON or Feather file, into such a column: they load as 1 and 0, as on the other databases.
- **A missing date or timestamp loaded into MySQL by `IMPORT` or `COPY`** is stored as NULL; it was stored as `0000-00-00` (or `0` in a number column). Delimited files were not affected.

______________________________________________________________________

## [2.33.0] - 2026-10-16

### Added

- **`$PG_UPSERT_STATUS`** says how a `PG_UPSERT` ended (`committed`, `dry_run`, `no_changes`, `qa_failed`, `cancelled`, `db_error`), and **`$PG_UPSERT_ERROR`** holds the database error message. A run with nothing to load and a cancelled run used to look the same in the other variables.

### Fixed

- **A failed metacommand sets `$LAST_ERROR` and `$ERROR_MESSAGE`** with `METACOMMAND_ERROR_HALT OFF`, so a script can tell what failed, not only that `METACOMMAND_ERROR()` is true; an `ON ERROR_HALT` handler (including `ON ERROR_HALT WRITE "…!{$LAST_ERROR}!"`) now gets `$LAST_ERROR` too. The error is also written to `execsql.log`.
- **`execsql.run()` reports a metacommand that failed under `METACOMMAND_ERROR_HALT OFF`** in `result.errors`, with `success` False, as it already did for a SQL error under `ERROR_HALT OFF`.
- **`PG_UPSERT` cancelled from a prompt** no longer leaves an earlier run's `$PG_UPSERT_*` values (such as `$PG_UPSERT_COMMITTED` `TRUE`) in place.

______________________________________________________________________

## [2.32.0] - 2026-10-16

### Changed

- **Working out column types is about twice as fast** for `IMPORT`, `COPY` and the exports that create a table (`EXPORT … AS SQLITE`, `DUCKDB`, `JSON`, `FEATHER`); a CSV whose dates repeat scans close to three times as fast. The types chosen are the same.
- **`IMPORT`, `COPY` and `EXPORT … AS DUCKDB` into DuckDB are about five times as fast**: they insert many rows per statement. Copying 200,000 rows took 124 s and now takes 22 s.

### Fixed

- **A column of large integers**, such as epoch milliseconds, no longer makes `IMPORT`, `COPY` or those exports hang or run out of memory while execsql works out the column types.

______________________________________________________________________

## [2.31.2] - 2026-10-16

### Fixed

- **SQL Server, Access and ODBC DSN connections** start a new database session on every `CONNECT` and `execsql.run()`: temp tables and `SET` options no longer carry over from an earlier connection in the same process on macOS and Linux. execsql turns off pyodbc's connection pooling, which also applies to other pyodbc connections your program makes.

______________________________________________________________________

## [2.31.1] - 2026-10-16

### Added

- **Templates documentation:** a new Templates section in the docs covers the upsert, compare and glossary templates, replacing three separate Read the Docs sites. Each script's notes also show in `SHOW SCRIPTS` and the editor's hover.
- **`trust_server_certificate`** (`[connect]`, or `?trust_server_certificate=yes` on an `mssql://` URL) accepts a SQL Server's self-signed TLS certificate, for `CONNECT` too.

### Changed

- **A connection URL with any other query parameter** (`?sslmode=require`, for example) is an error; it used to be ignored.
- **The `upsert` extra requires pg-upsert 1.26.0.**
- **GitHub Releases** carry the version's `CHANGELOG.md` section as their text.
- **The VS Code extension's version** is execsql's; a pre-release is `2.31.0-rc.1`, so VS Code upgrades from an rc to its final release.
- **Documentation links** in messages, `--online-help`, hover text, the config template, the VS Code extension and PyPI go to the latest release's docs (`/en/stable/`) instead of `main`.

### Fixed

- **`templates/` scripts** run on MySQL 8 and MariaDB 11, and each is now tested on PostgreSQL, MySQL, MariaDB and SQL Server. The fixes that change results:
    - `md_upsert.sql` with `do_commit=No` halts before changing anything; MySQL and MariaDB cannot roll the load back, and it used to commit.
    - `ss_upsert.sql` no longer lets orphan rows past the foreign key check on a second load in the same session, works with `exclude_cols`, and keeps its row counts with `do_commit=No`.
    - The compare scripts report a change in letter case as a change on MySQL, MariaDB and SQL Server; `md_compare.sql` ignores same-named tables in other databases.
    - `script_template.sql` keeps a `get_run_description` or `do_run_numbering` set before it runs, so it can run unattended.
- **SQL Server with ODBC Driver 18** connects (it is tried first). It verifies the server's certificate; for a self-signed one, set `trust_server_certificate`.
- **SQL Server uses the port you give** (`-p`, `mssql://host:port/db`, `CONNECT … PORT`); it used to connect to 1433 and send the password there.
- **SQL Server and Access passwords containing `;`** log in and stay out of `execsql.log`; a database name or path with `;` can no longer add connection settings.
- **`IMPORT` and `COPY … TO REPLACEMENT`** create a missing table on SQL Server, Oracle, Firebird and Access instead of stopping with "Could not drop existing table".
- **`IMPORT` into PostgreSQL or MySQL** with `IMPORT_COMMON_COLUMNS_ONLY` reads a short line's missing values as NULL instead of stopping with `IndexError`, and MySQL no longer adds a NULL row for each blank line at the end of a CSV.
- **`IMPORT` from ODS** reads each cell's stored value: `#` text, comments, merged and multi-line cells no longer shift or split the row, and `12.50%` imports as `0.125`.
- **`EXPORT … AS ODS`** writes `0` and FALSE as values and NULL as an empty cell.
- **`EXPORT … AS VALUES`** files run back as the same rows: values with line breaks, `;`, `!!var!!` or `-- !x!` are no longer split, substituted or run; reserved-word column names are quoted; an empty result writes a comment.
- **`PG_UPSERT`** fails on a database error (deadlock, lock timeout, trigger or constraint error) with the message in `$ERROR_MESSAGE`; it used to report success with zero rows.
- **`SERVE`** writes its headers before the file when stdout is a pipe, as under CGI.
- **The plaintext-keyring warning** appears only when a password would really be saved in cleartext.
- **`execsql lint`, `execsql format` and the language server** no longer open network paths (`\\host\share\…`) named in a script or config; on Windows that sent your login to the host. `execsql run` still follows them.

### Removed

- **`templates/pg_upsert.sql`**: use the `PG_UPSERT` metacommand.
- **The `dev` extra:** the project's own dev tools are now the `dev` dependency group (`uv sync`, or `pip install --group dev`).

______________________________________________________________________

## [2.30.0] - 2026-10-14

### Added

- **`execsql lsp --log-level` and `--log-file`** (or `EXECSQL_LSP_LOG_LEVEL`): `info` logs versions, formatter status, workspace folders and config files read; `debug` adds protocol messages. See [Troubleshooting](https://execsql2.readthedocs.io/en/latest/guides/editors/#troubleshooting) for bug reports.
- **VS Code extension:** the **execsql** Output channel shows the server log (`execsql.server.logLevel`, default `info`) and why the server did not start; `execsql.trace.server` traces the protocol there.

### Fixed

- **`execsql lint`** keeps going when a file has an `INCLUDE` path the OS rejects: that file gets I001 instead of the run stopping with "Uncaught exception". A script lint cannot check at all is one P001 error.
- **The language server** shows "execsql could not check this script" when a check fails, instead of keeping stale findings; hover, completion and navigation still work.
- **The language server is fast with many or large `INCLUDE`s:** it no longer rereads every included file per request, and after a save lints only the open scripts that `INCLUDE` the changed file, once.
- **`execsql --help`** wraps each command's summary instead of cutting it off with `...`.
- **DuckDB temporary tables** last for the whole run, not just one statement.
- **A scheme-less `--dsn` / `dsn=`** (`//user:password@host/db`) is reported with its password as `***`.
- **`--manifest`** masks passwords, `SUB_DECRYPT` results and tokens (URL passwords, `password=...`, API keys) as `***`. `-a` and `--var` values still appear in paths.
- **Registered secrets** in a `HALT MESSAGE`, exported file name or connection name show as `***` in `execsql.log`.
- **`execsql.run()`** restores the caller's working directory after a script that ran `CD`, even on failure.
- **Language server settings** load for a workspace folder added after the first was deleted, instead of linting with stale rules. An unsaved script's relative `INCLUDE` resolves against the workspace root.
- **VS Code extension:** after `CONFIG`, config-file-only keys such as `DB_FILE`, `CONSOLE_HEIGHT` or `CSS_FILE` are no longer highlighted as valid.
- **VS Code extension:** changing `execsql.server.enabled` or `execsql.server.path` needs no window reload; **execsql: Restart Language Server** works when the server is off, and quick restarts no longer leave two servers running.

### Removed

- **Python helpers:** `execsql.gui.get_backend()`, `ins_quoted_rx()`, `execsql.utils.errors.exception_info()` (use `exception_desc()`), and the `execsql.cli.main` re-export (use `execsql.cli.commands.run`).
- **`execsql.utils.fileio`:** `filewriter_closeall()`, `filewriter_shutdown()`, `list_encodings()` and `FileWriter.ping()`. Use `filewriter_end()` and `execsql list encodings`.

______________________________________________________________________

## [2.29.0] - 2026-10-13

### Changed

- **`!'!var!'!` stores backslashes as written** (`C:\data\new` was stored as `C:\\data\\new` outside MySQL/MariaDB). MySQL/MariaDB and PostgreSQL `E!'!var!'!` still double them, so both forms store the same value; drop any `E` or other workaround.

### Fixed

- **Oracle `IMPORT` and `COPY`** create a time column as `VARCHAR2(15)` instead of stopping with "Oracle DBMS type has no specification for data type time".
- **MySQL `IMPORT`** accepts capitalized headers (`Id,Name`) instead of stopping with "columns that are not in table", or loading NULLs with `IMPORT_COMMON_COLUMNS_ONLY`.
- **PostgreSQL `IMPORT` honors `SKIP n`** for quoted CSV files.
- **Spreadsheet `IMPORT`:** an XLSX row of all `0`/FALSE no longer ends the data, and XLS with `SKIP n` keeps its last *n* rows.

______________________________________________________________________

## [2.28.0] - 2026-10-13

### Added

- **`execsql lsp --check`** reports whether the language server can start (exit 0) or what is missing (exit 1).

### Changed

- **Missing-package messages** name the execsql2 extra and how to add it while keeping installed extras.

### Fixed

- **`execsql format` keeps `/*+ ... */` hints and `/*! ... */` MySQL executable comments** as written; they became `/* + ... */`, so MySQL skipped the SQL and hints were ignored. Re-check files the formatter or its pre-commit hook rewrote.
- **`execsql format`** no longer adds a final `;` the script lacked, which made an unfinished statement run.
- **`execsql format`:** a statement kept as written after another on the same line no longer starts with a space.
- **`execsql format` without sqlglot** names the `[formatter]` extra in its install hint.
- **`execsql lint` and the language server read each `SUB_INI` file once**; a large INI named on many lines froze the editor. V002 for a `SUB_INI` variable points at the `SUB_INI` line, not line 0.
- **`execsql lsp` with an incompatible pygls** names that pygls version instead of saying the `lsp` extra is missing.
- **`COPY` keeps binary columns** (BLOB, `bytea`) byte for byte, and `TO NEW` creates them as binary, not escaped text.
- **DuckDB `TO NEW`** ignores same-named tables in `ATTACH`ed databases.

______________________________________________________________________

## [2.27.0] - 2026-10-12

### Added

- **`execsql lsp`**, a language server for editors. Install the `lsp` extra (`uv tool install "execsql2[lsp]"`, naming any extras you already have, e.g. `"execsql2[postgres,lsp]"`); setup for VS Code, Neovim, Helix and others is in the Editor Support guide. It provides:

    - lint findings as you type (`[lint]` settings);
    - completion of metacommands (as syntax templates), conditional tests, variables and export formats;
    - hover for metacommands, conditional tests and variables;
    - Go to Definition, Find All References, Rename Symbol (variables), outline and `INCLUDE` links;
    - folding of `IF`, `LOOP`, `SCRIPT`, `BATCH` and `SQL` blocks, multi-line statements and comments;
    - quick fixes for P002, P003, P004 and V001;
    - Format Document (`[format]` settings);
    - re-linting when `execsql.conf` or an `INCLUDE`d file changes;
    - a separate `execsql.conf` per multi-root workspace folder.

    It never runs a script or connects to a database; it reads only open scripts, files they `INCLUDE` or name in `SUB_INI`, and the config files `execsql lint` reads.

- **VS Code extension** starts `execsql lsp` for `.sql` files, only in a trusted folder; settings `execsql.server.path` (a PATH command or absolute path, never an `execsql` in the open folder) and `execsql.server.enabled`; command **execsql: Restart Language Server**. Highlighting works anywhere. Install the `execsql-syntax.vsix` attached to each GitHub release with `code --install-extension execsql-syntax.vsix`.

### Changed

- **`lsp` is a command name:** run a script file named `lsp` as `execsql run lsp`.
- **`execsql list metacommands`** lists all 95 metacommands with category and summary; `execsql list metacommands <KEYWORD>` shows syntax and a docs link. JSON output's `syntax` is the full first syntax line, plus new `forms` (every syntax line), `category`, `summary` and `url`.

### Fixed

- **DuckDB `TIMESTAMPTZ` values** are read: the `duckdb` and `all-db` extras now install `pytz`.
- **`CONFIG MAX_INT <n>`** works instead of stopping with `Unknown metacommand`.

______________________________________________________________________

## [2.26.0] - 2026-10-09

### Added

- **`execsql format --rewrite-sql`** (`[format] rewrite_sql`): apply sqlglot's SQL rewrites, such as `x::int` to `CAST(x AS INT)`.

### Changed

- **`execsql format` changes only layout and keyword case by default:** statements sqlglot would rewrite (`x::int`, an alias gaining `AS`, `BTRIM` to `TRIM`) are kept. Use `--rewrite-sql` for the old behavior.
- **`execsql format` and the `execsql-format` pre-commit hook pin sqlglot 30.21.x.** The first run after upgrading may reformat files (e.g. `BTRIM(x)` to `TRIM(x)`); see [sqlglot version](https://execsql2.readthedocs.io/en/latest/guides/formatter/#sqlglot-version).

______________________________________________________________________

## [2.25.1] - 2026-10-09

### Fixed

- **`execsql lint` `V001` / `V002`:** in a nested name like `!!N_!!CHECK_GROUP!!_CHECKS!!`, only the inner `!!CHECK_GROUP!!` is checked and counted as used.
- **`execsql lint` and `SUB_INI`:** a FIFO or device (`/dev/zero`) no longer hangs lint, and an unparsable INI no longer stops it.

______________________________________________________________________

## [2.25.0] - 2026-10-09

### Added

- **`execsql lint` rules:**
    - `P002` (`split-dollar-quote`): a `$$ ... $$` function or `DO` body outside `BEGIN SQL` / `END SQL`, which execsql would send in pieces;
    - `P003` (`unknown-metacommand`): a misspelled or malformed metacommand (`SUBSTITUTE x 1`, `EXPORT t TOO out.csv`) that `execsql run` would stop at;
    - `P004` (`unknown-condition`): an unknown test (`IF(hasrowz(t))`) or unparsable condition (`ASSERT !!flag!! = TRUE`) in `IF`, `ELSEIF`, `ANDIF`, `ORIF`, `LOOP`, `EXECUTE SCRIPT ... WHILE`, `ASSERT` and `WAIT_UNTIL`.
- **`[email] ca_file` and `verify_certificate`** for the SMTP server's TLS certificate.

### Changed

- **`EMAIL` with `use_ssl` or `use_tls` verifies the server certificate** and stops before sending the password if it is untrusted or does not match `host`. Set `[email] ca_file` for an internal CA, or `verify_certificate = No`.
- **`--dsn` / `execsql.run(dsn=...)` user, password and database are percent-decoded** (`p%40ss`). A password with `%` and two hex digits must now write `%25`.
- **A relative `WRITE ... TO` path after `CD`** lands in the new directory, like `EXPORT`.
- **A locked `WRITE` / `EXPORT` file can delay the end of a run** by up to `outfile_open_timeout` (default 600 s), then fails naming the file and lines lost. Lower it for unattended runs.
- **Output that cannot be written fails the run:** a failed `WRITE`, `EXPORT` or `TEE` file (full disk, dropped share) ends the run with an error naming it (exit 1, or `success=False` from `execsql.run()`); other files are still written. A target that can never be opened fails at once.
- **Database and driver errors** show just the error (`OperationalError: table t already exists`); `execsql.log` keeps the source location.
- **`execsql lint` with block-structure errors** reports each unmatched `IF`, `LOOP`, `BEGIN BATCH`, `BEGIN SCRIPT` and `BEGIN SQL` as its own `P001` and still runs the other rules.
- **Faster start-up:** about 0.7 s for every `execsql` command and `import execsql`.

### Removed

- **`execsql.utils.fileio` globals** `filewriter`, `fw_input`, `fw_output` and `FileWriter`'s queue arguments. Drop any hand-started writer before `execsql.run()` (the pre-2.23.0 workaround for [#46](https://github.com/geocoug/execsql/issues/46)).

### Fixed

- **Output lost when a script halts is reported** (console, log, `--manifest`, `execsql.run()` errors) after waiting up to 10 seconds for a locked `WRITE`, `TEE` or `ON ERROR_HALT WRITE` file.
- **SIGTERM** (`kill`, `timeout`, `docker stop`) ends a `run` like Ctrl-C: rollback, `SYSTEM_CMD` stopped, `exit` record of type `terminated`, exit status 143.
- **`execsql.log`:**
    - writes an `exit` record for an error, `HALT` or cancelled prompt (type `error` or `halt`); Ctrl-C is `interrupted`;
    - `run_db_file` names the SQLite, DuckDB or Access file;
    - the `run` record counts `-a` values instead of showing them;
    - passwords from `--dsn`, `[email]`, the password prompt or keyring, `PROMPT ENTER_SUB ... PASSWORD`, `PROMPT CREDENTIALS` and `SUB_DECRYPT` are `***`, including in `LOG_SQL ON` output and `SYSTEM_CMD` lines.
- **Keyring:**
    - saves a password only after the connection succeeds;
    - deletes it and prompts again only when the server rejects it, not on a timeout, closed port or missing database;
    - names entries with the port (`execsql/PostgreSQL/host:5432/db`); an old portless entry still works on the default port and is renamed.
- **Oracle** (`-t o`, `oracle://`) connects with `oracledb`, which `execsql2[oracle]` installs.
- **`-n -e` on PostgreSQL** creates the database with that encoding, like `CONNECT ... ENCODING=..., NEW`; PostgreSQL rejects one that differs from its template (usually UTF8).
- **`-d` / `--directories`** rejects values other than `0`, `1`, `t`, `f`, `y`, `n` (exit 2), as upstream did.
- **`access_use_numeric`** (`[input]`) works again: Access decimals are `NUMERIC(precision,scale)`, not `DOUBLE`.
- **`IMPORT` / `COPY ... TO NEW` onto an existing table** stops with `Table <name> already exists` before creating anything; an unqualified name is checked only in the target schema (MySQL: current database).
- **`IMPORT` / `COPY ... TO REPLACEMENT`** handles names that need quoting (SQLite, SQL Server, Oracle, Firebird, Access) and schema-qualified names like `staging.t` (SQL Server, Oracle, Firebird).
- **`COPY` and `COPY QUERY` copy text as written:** text holding `1`/`0`, dates or numbers stays text under `NEW` / `REPLACEMENT`, and `1` stays `1`.
- **`COPY ... TO NEW` / `REPLACEMENT`** no longer holds every source row in memory.
- **A failed `IMPORT` / `COPY` into DuckDB** keeps no rows, as on SQLite and PostgreSQL.
- **`IMPORT`:**
    - a short line loads its missing values as NULL on every DBMS;
    - rows after a blank line are imported; the blank line is a NULL row (dropped with `CONFIG EMPTY_ROWS NO`), trailing blank lines are ignored;
    - PostgreSQL no longer fails with `missing data for column` on a quoted file with a blank line;
    - `TO NEW` / `REPLACEMENT` no longer reads `1-2`, `5/6`, `March 5`, `Jan` or `Monday` as dates: a date needs a year (`2024-01-05`, `1/5/2024`) or a month-first two-digit year (`1/5/24`);
    - a timestamp column mixing values with and without a UTC offset becomes text, not converted with the local time zone;
    - MySQL loads backslashes as written (`C:\new\tbl`, `\N`) and imports files whose path contains one.
- **`EXPORT ... AS XLSX`** writes text starting with `=` as text, not a formula.
- **`execsql.run()`:**
    - no longer runs the SQL twice on macOS and Windows when the calling script lacks an `if __name__ == "__main__":` guard;
    - concurrent calls each get complete output, and one halting does not discard another's;
    - repeated calls no longer pile up exit hooks or duplicate plugin metacommands;
    - removes its temp files and, on Ctrl-C, closes its connection;
    - with `--manifest`, no longer records into another run's manifest;
    - reports the error that halted the run (statement in `ScriptError.sql`) and a `HALT`'s exit status, with `result.errors` in order;
    - setup failures (unreadable script, bad `config_file` or `dsn`) return `success=False` with `source` set to the script, `<config>` or `<connect>`, instead of raising.
- **`execsql lint`:**
    - `V001` ignores variables set by `PROMPT ENTER_SUB`, `ASK ... SUB`, `PROMPT ASK ... SUB`, `PROMPT OPENFILE` / `SAVEFILE` / `DIRECTORY SUB`, `PROMPT CREDENTIALS`, `SUB_TEMPFILE` and `SUB_QUERYSTRING` keys;
    - `V001` flags a user variable named like a system variable without `$` (`!!date_tag!!`) and a `SUB` variable written with `$` (`!!$region!!`);
    - `V002` counts `sub_defined(...)` / `sub_empty(...)` as uses;
    - `IF(1=1)`, `IF(1=0)` and `IF(0=1)` are `P004` (which `execsql run` rejects), not `F001`.
- **Install hints** name the right extra: `formats` for XLSX (not `excel`), none for Textual.
- **Docs:** the 2.17.0 `PG_UPSERT` migration note's `ASSERT !!$PG_UPSERT_QA_PASSED!! = TRUE` always failed; use `ASSERT IS_TRUE(!!$PG_UPSERT_QA_PASSED!!) "QA failed"`.

______________________________________________________________________

## [2.24.0] - 2026-10-01

### Added

- **Commands:** `execsql run`, `format`, `lint`, `config`, `list` and `init`. `format` and `lint` take files or directories and need no database. See [Commands](https://execsql2.readthedocs.io/en/latest/getting-started/syntax/#commands).
- **`run --manifest FILE`** writes a JSON record of the run (files, connections, statement counts, any error), even when it fails. **`--var NAME=VALUE`** sets `!!NAME!!`.
- **`lint`:** rule codes (`V001`, `F002`, …) for `--select` and `--ignore`; `--output-format json|concise|github`, `--statistics`, and `--strict` to fail on warnings. New checks: a `SUB` variable nothing reads, an `IF` whose condition never changes, statements after `HALT`. See the [lint rules reference](https://execsql2.readthedocs.io/en/latest/reference/lint/).
- **`execsql-lint` pre-commit hook**, alongside `execsql-format`.
- **`format --diff`** shows changes without writing; `--sql` and `--no-leading-comma` override the config for one run.
- **`format` and `lint`** read stdin with `-` and take `-f`/`--script-encoding` and `--config`.
- **`[format]` and `[lint]` config sections** set project defaults; a flag wins.
- **`config`** lists every option with its value, default and source file (passwords as `***`). `--validate` reports every problem with its file and line; `--init` prints the config template.
- **`init`** creates `execsql.conf`, a starter script and the pre-commit hooks; `--force` overwrites existing files.
- **`list`** shows `metacommands`, `encodings`, `plugins` and `keywords`, as text or JSON.
- **`PG_UPSERT` QA** fails a staging value longer than its `varchar(n)` or `char(n)` base column and lists it in the `EXPORT_FAILURES` fix sheet.

### Deprecated

- **Running a script without a command** (`execsql script.sql myserver mydb`) warns and stops working in execsql2 3.0; use `execsql run script.sql myserver mydb`. `-m`, `-y`, `--list-plugins`, `--dump-keywords`, `--init-config` and `--ping` without a command warn and name their replacement; see [Flags that became commands](https://execsql2.readthedocs.io/en/latest/getting-started/syntax/#former_flags). After `run` they still work without a warning but are hidden from `execsql run --help`.

### Removed

- **`--lint`:** use `execsql lint`. `execsql run --lint` exits with status 2 without running the script; update CI steps and hooks that call it.
- **The `execsql-format` command:** use `execsql format` (same options). The pre-commit hook id is still `execsql-format`; shell scripts, Makefiles and CI steps that call the command must change.
- **`SqlStmt`, `MetacommandStmt` and `ScriptCmd`** from `execsql.script`; only Python code importing them is affected.

### Changed

- **`PG_UPSERT` QA follows `METHOD` and `EXCLUDE`:** it checks only the staging rows the load would write, so pass `PG_UPSERT QA` the same `METHOD` and `EXCLUDE` as the load. `CHECK ... METHOD update` treats a missing `NOT NULL` column as a warning. See [QA follows METHOD and EXCLUDE](https://execsql2.readthedocs.io/en/latest/reference/metacommands/#pg_upsert_qa_method).
- **`PG_UPSERT` QA can fail where it passed before:** it catches a unique key colliding with an existing base row, a foreign key parent not in `TABLES`, and an excluded `NOT NULL` column on an inserted row, which used to fail during the load.
- **The `upsert` extra requires pg-upsert 1.25.0** or newer.
- **A script named like a command** (`run`, `format`, `lint`, `config`, `list` or `init`, no extension) must be run as `execsql run NAME`.
- **`execsql format --encoding`** is now `-f`/`--script-encoding`, matching `run`; `--encoding` still works.
- **The debug REPL** (`BREAKPOINT`, `--debug`) runs metacommands and blocks as well as SQL, as the next lines of the script: a `SUB` stays set when the script resumes, and SQL is committed as the script's own would be. See [Debugging](https://execsql2.readthedocs.io/en/latest/guides/debugging/).
- **CLI help** is plain text at full terminal width, colored on a terminal (`NO_COLOR` or `EXECSQL_NO_COLOR` turns it off). `execsql` with no arguments prints it and exits with status 2.
- **Lint output** groups issues by file in line order with one summary line; a script that fails to parse is one line with its line number.
- **Error messages** name the fix: a missing SQLite or DuckDB file suggests `-n`/`--new-db`; a config file error names the file and line and suggests `execsql config --validate`.
- **Requires Typer 0.26** or newer (was 0.12).

### Fixed

- **`execsql format` without the `[formatter]` extra** says sqlglot is needed and how to install it, instead of an uncaught `ImportError`.
- **`-h`** works as `--help`, as in upstream execsql.
- **The debug REPL's `.set VAR VALUE`** keeps the value's case instead of lowercasing it; **`.vars all`** lists environment variables instead of looking up a variable named `all`.

______________________________________________________________________

## [2.23.1] - 2026-09-29

### Added

- **Implicit-commit warning on MySQL, MariaDB and Oracle:** DDL (`CREATE TABLE`, `DROP`, `TRUNCATE`, …) run while `AUTOCOMMIT` is `OFF` or a batch is open warns that the server commits it, and everything before it, beyond rollback.
- **A warning when `AUTOCOMMIT OFF` or `BEGIN BATCH` cannot hold statements:** an ODBC DSN whose driver has no transactions, or an MS Access `CREATE TEMPORARY QUERY`, which reopens the connection and rolls back uncommitted work.

### Fixed

- **SQLite:** DDL run while `AUTOCOMMIT` is `OFF` or inside `BEGIN BATCH` is held until commit; it was committed at once, so `AUTOCOMMIT ON WITH ROLLBACK` and `ROLLBACK BATCH` left it in place.
- **DuckDB:** `AUTOCOMMIT OFF` and `BEGIN BATCH` hold statements until commit; every statement used to commit as it ran. A script's own `BEGIN;` and `COMMIT;` work; `COMMIT;` failed with "no transaction is active".
- **DuckDB `$LAST_ROWCOUNT`** holds the rows an `INSERT`, `UPDATE` or `DELETE` changed; it was always `-1`.

______________________________________________________________________

## [2.23.0] - 2026-09-29

### Added

- **Database support tiers:** PostgreSQL, MySQL/MariaDB, MS SQL Server, SQLite and DuckDB are **supported** (verified against a live server or real database file in CI). MS Access, Firebird, Oracle and ODBC DSN are **best effort** (unverified in CI; may break). No adapter changes behavior or is scheduled for removal.
- **`support_tier_notice`** (`[interface]`, default `Yes`): opening a best-effort connection writes one stderr line naming its tier, once per DBMS per run. Set `No` to silence it.

### Changed

- **MySQL and MariaDB connections default to `utf8mb4`** instead of `latin1`, so CJK, emoji, Greek and Cyrillic text no longer raises `UnicodeEncodeError` without `-e utf8mb4`. Existing latin1 databases are unaffected; MySQL transcodes to each column's charset. Pass `-e latin1` for the old behavior.

### Fixed

- **`execsql.api.run()`** writes `WRITE ... TO <file>` and `TEE` output to the file; it was never created, and the run still reported success ([#46](https://github.com/geocoug/execsql/issues/46)). Files are flushed and closed before `run()` returns; a writer the caller started is left alone.
- **File output that cannot be written** because no file writer is running warns instead of vanishing silently; the write is still skipped.
- **`IMPORT` of a CSV with a newline in a quoted field** works; the header was read as one column and the record split into two rows. An exported multi-line value now imports back unchanged.
- **`IMPORT` to MySQL** writes an empty field as NULL instead of `0` or `0000-00-00`.
- **`IMPORT ... WITH QUOTE NONE` to PostgreSQL** keeps double quotes in the data (`Well "A" 12` became `Well A 12`), also when no quote character was detected ([#54](https://github.com/geocoug/execsql/issues/54)).
- **`IMPORT` to PostgreSQL** honors a detected backslash escape; `"Well \"A\" 12"` became `Well \A\ 12`.
- **`IMPORT` to MySQL** reads CRLF files; each row's last field kept a trailing carriage return, turning an empty date into `0000-00-00`.
- **`EXPORT ... AS CSV`** and the other delimited formats no longer turn a newline inside a value into `\r\n` on Windows; rows end in `\n` on every platform, so the same query gives the same bytes everywhere.
- **`EXPORT ... AS TAB`** and console tables keep each row on one line, showing a newline or tab in a value as `\\n` or `\\t`.
- **`EXPORT ... AS VALUES`** quotes dates, timestamps and every other non-numeric value; PostgreSQL stored a bare `2026-09-24` as `1993`, and a timestamp was a syntax error. Numbers and `NULL` are unchanged.
- **`EXPORT ... AS LATEX`** escapes `\\ & % $ # _ { } ~ ^`, not only `_` (an `&` broke the table with "Extra alignment tab has been changed to \\cr"), and writes NULL as an empty cell instead of `None`.
- **`EXPORT ... AS HTML`** renders `0`, `False` and empty strings instead of blank cells.
- **`EXPORT ... AS MARKDOWN`** writes a line break in a value as `<br>` instead of breaking the table.
- **`EXPORT ... AS ODS`** writes `numeric`/`decimal` columns as typed numbers (they were invalid ODF) and keeps newlines in a value instead of replacing them with spaces.
- **`EXPORT ... AS XLSX`** writes `numeric`/`decimal` columns as numbers instead of text.
- **DuckDB float columns** are `DOUBLE`, not single-precision `REAL`, for `EXPORT ... AS DUCKDB` and `COPY` into DuckDB; `1234.567` came back as `1234.5670166015625`.
- **Jinja2 report templates** ending in `.html`, `.htm` or `.xml` escape rendered values; markup in a database value became live markup in the report. Other extensions are unchanged. Use `{{ value|safe }}` to emit markup.

______________________________________________________________________

## [2.22.9] - 2026-09-24

### Fixed

- **`EMAIL`** and the `ON ERROR_HALT EMAIL` and `ON CANCEL_HALT EMAIL` hooks send again; every send failed with `AttributeError: 'SMTP' object has no attribute 'ehlo_or_hello_if_needed'`.
- **An `[email]` `username` with no `password` or `enc_password`** is a configuration error instead of a `TypeError` from `smtplib`.

______________________________________________________________________

## [2.22.8] - 2026-09-17

### Fixed

- **`execsql-format`** leaves no space before `;` when a comment precedes the closing line; `1 = 1 ;` made `--check` fail on the formatter's own output.
- **`execsql-format`** keeps a comment above a select item or `CASE` branch in place; it moved into the expression (such as `COALESCE((a.meas_value).undetected, FALSE)`) and reformatted differently on every run, so `pre-commit` could not pass.

______________________________________________________________________

## [2.22.7] - 2026-09-17

### Fixed

- **`execsql-format`** no longer deletes clauses from SQL it cannot fully parse, such as the `DO NOTHING` of `INSERT ... CROSS JOIN LATERAL (VALUES ...) AS g(a, b) ON CONFLICT (a) DO NOTHING`.
- **`execsql-format`** keeps a `!!~var!!` standing alone in a `WHERE` clause (the upsert templates' optional predicates) and a trailing `ORDER BY` in the same statement.

### Changed

- **`execsql-format`** leaves a run of SQL as written, normalizing only indentation, when any statement in it fails to parse.

______________________________________________________________________

## [2.22.6] - 2026-08-28

### Fixed

- **`execsql-format`** no longer indents inside a multi-line string literal (`$$…$$` or `'…'`) in an `IF`, `LOOP` or `BEGIN SQL` block, which changed the stored value.
- **`execsql-format --leading-comma`** no longer moves a comma into or out of a multi-line string literal.
- **`execsql-format`** reaches a stable result in one pass; an unparsable statement gained a space of indentation on every run, so `--check` never passed.

______________________________________________________________________

## [2.22.5] - 2026-08-27

### Fixed

- **`execsql-format`** no longer alters PostgreSQL escape strings; `E'\\s+'` became `e'\s+'` and lost a further backslash on every run.
- **`execsql-format`** leaves a statement unformatted when any of its string literals would change.

### Changed

- **The `execsql-format` pre-commit hook** pins `sqlglot>=25.0,<31`, so a commit formats identically on every machine.

______________________________________________________________________

## [2.22.4] - 2026-08-27

### Fixed

- **`HALT` with a message** in unattended runs (below `gui_level` 2) writes to the console and exits with the requested `EXIT_STATUS` instead of blocking on a dialog.
- **`HALT … DISPLAY`** writes its table to the console in non-interactive runs instead of discarding it.
- **Textual `HALT` dialogs** show one OK button, render the `DISPLAY` table and ignore <kbd>Esc</kbd>; cancelling exited with status 2 instead of the requested `EXIT_STATUS`.

______________________________________________________________________

## [2.22.3] - 2026-07-23

### Fixed

- **`execsql-format`** keeps a completed dollar-quoted PL/pgSQL body (`CREATE FUNCTION … $$ … $$;`, `DO $$ … $$;`) verbatim; it was reformatted and gained indentation on every run, so `--check` never passed.

______________________________________________________________________

## [2.22.2] - 2026-07-13

### Fixed

- **`ASK … SUB`** stores the actual answer ("Yes" or "No"); it stored "No" for every response, so branches on the answer never took the yes path. `Esc` at the prompt quits the script again.

______________________________________________________________________

## [2.22.1] - 2026-07-04

### Fixed

- **Database factory functions** (`db_SQLite(..., new_db=True)`, etc.) no longer raise `AttributeError` when called before `run()` in library use.
- **`run(halt_on_error=False)`** reports non-halting SQL and metacommand errors in `result.errors` and sets `result.success` to `False`; they were dropped.

______________________________________________________________________

## [2.22.0] - 2026-07-03

### Added

- **`run()` `allow_rm_file=False` and `allow_serve=False`** disable `RM_FILE` and `SERVE` for library callers, like `allow_system_cmd` and the `--no-rm-file` / `--no-serve` flags.
- **`[config] system_cmd_timeout`** bounds foreground `SYSTEM_CMD`; the default is still no timeout.

### Fixed

- **`EXPORT … FORMAT SQLITE` and `FORMAT DUCKDB`** keep source column types from a typed database: text stays text, `Decimal` values bind (as exact strings in SQLite), and unsupported objects such as PostGIS geometry are stringified instead of failing to bind.
- **`EXPORT … FORMAT LATEX` into a ZIP archive** no longer raises `AttributeError`.
- **Connecting to a server database without a server or database name** stops with a clear error instead of a driver traceback.

______________________________________________________________________

## [2.21.2] - 2026-06-30

### Fixed

- **`EXPORT … AS PARQUET` and `AS FEATHER`** no longer fail with `ComputeError` when a column has more than 100 leading `NULL`s followed by numbers.

______________________________________________________________________

## [2.21.1] - 2026-06-24

### Fixed

- **PostgreSQL:** `EXPORT` and other repeated queries against objects a script drops, recreates or alters no longer fail with `FeatureNotSupported: cached plan must not change result type`.

______________________________________________________________________

## [2.21.0] - 2026-06-24

### Changed

- **PostgreSQL** connects with psycopg3 instead of psycopg2; the `postgres` extra installs `psycopg[binary]`.
- **`PG_UPSERT`** requires `pg-upsert>=1.23.0`.

______________________________________________________________________

## [2.20.0] - 2026-06-11

### Added

- **`execsql-format --encoding NAME`** reads and writes SQL files in that encoding (default `utf-8`), for files saved as cp1252, latin-1, shift_jis and so on. A `UnicodeDecodeError` names the file and suggests `--encoding` instead of printing a traceback.

### Changed

- **The `execsql-format` pre-commit hook** defaults to `args: [--in-place]`. A config with no `args:` now reformats files; it used to do nothing. Use `args: [--check]` for check-only.
- **Environment-variable redaction** in the log also covers common secret names (`AWS_ACCESS_KEY_ID`, `STRIPE_KEY`, `OPENAI_API_KEY`, `SENTRY_DSN`, `SLACK_WEBHOOK`, …), and `-a` assignment lines always show `{***}`. Known gaps (`DATABASE_URL`, `GITHUB_PAT`) are listed in `docs/reference/security.md#env_redaction`.
- **`<sys.prefix>/execsql2_extras/execsql.conf`** is no longer installed; create a config with `execsql --init-config > execsql.conf`.

### Fixed

- **The `[firebird]` extra** connects; it used to fail with `ModuleNotFoundError: No module named 'fdb'`.
- **MySQL, SQL Server, MS Access, ODBC DSN, Firebird and SMTP connections** time out after 30 seconds, as PostgreSQL does, instead of hanging on an unresponsive server.
- **`execsql-format`** leaves tagged PL/pgSQL dollar quotes (`$body$ … $body$`) alone, as it does `$$`; their `IF / END IF / LOOP / RETURN` used to be rewritten.
- **`execsql-format`** uppercases every keyword of multi-word metacommands (`PROMPT MAP`, `APPEND SCRIPT`, `PG_UPSERT CHECK`, `RESET COUNTER`, `WRITE CREATE_TABLE`, …), not only the first.
- **`execsql-format`** keeps going after an unreadable file and exits 1 at the end if any file failed or needs changes.
- **`execsql-format --leading-comma`** gives the same result on a second run for SQL with comments inside a statement.

______________________________________________________________________

## [2.19.2] - 2026-06-03

### Fixed

- **The `execsql-format` pre-commit hook** installs `sqlglot`; it used to fail with `ModuleNotFoundError: No module named 'sqlglot'`. After upgrading, run `pre-commit clean && pre-commit install --install-hooks`.

______________________________________________________________________

## [2.19.1] - 2026-06-03

### Fixed

- **`execsql-format`** leaves quoted substitution variables (`!'!var!'!`, `!"!var!"!`) and deferred `!{var}!` intact; `!'!myvar!'!` used to become `NOT NOT '!myvar!'`.

______________________________________________________________________

## [2.19.0] - 2026-06-02

### Fixed

- **`IMPORT … FORMAT xlsx`** rejects zip-bomb workbooks (a member compressed over 100:1, or over 500 MB uncompressed). Convert large workbooks to CSV; `.xls` is unaffected.
- **`EXPORT … FORMAT hdf5`** keeps `BIGINT` columns 64-bit and honours `hdf5_text_len` for text columns.
- **The `BREAKPOINT` REPL**:
    - prints SQL errors and returns to the prompt instead of ending the session;
    - runs DML (prints `(N rows affected)`), DDL and `BEGIN` / `COMMIT` / `ROLLBACK` (prints `(statement executed)`);
    - accepts multi-line SQL, buffered until a line ends with `;`; `.cancel`, Ctrl-C or EOF discards it.

### Changed

- **The `BREAKPOINT` REPL** treats input starting with `.` as a REPL command and everything else as SQL. Typing a bare variable name no longer prints it; use `.vars NAME` (`.vars` alone lists all).
- **`sqlglot`** moved to the new `[formatter]` extra, which `execsql-format`'s SQL pass needs; `execsql-format --no-sql` works without it.
- **`textual`** requires `>=1.0` (was `>=0.47.0`).

______________________________________________________________________

## [2.18.1] - 2026-05-28

- Internal: `execsql.cli.lint_ast` is now `execsql.cli.lint.lint`; deprecated `MetaCommand.run_when_false` / `run_in_batch` kwargs removed.

______________________________________________________________________

## [2.18.0] - 2026-05-27

### Added

- **`IS_FALSE(<value>)`** condition: true for `No`, `N`, `False`, `F` or `0` (any case). It was documented but raised `CondParserError`.
- **`--no-rm-file` and `--no-serve`** (or `allow_rm_file` / `allow_serve` in `[config]`) disable `RM_FILE` and `SERVE`, like `--no-system-cmd`.
- **`include_root`, `serve_root` and `template_root`** (`[config]`) confine `INCLUDE` / `EXECUTE SCRIPT`, `SERVE` and template paths to a directory, rejecting `..`, absolute, drive-letter and UNC paths that escape it.
- **`max_substitution_bytes`** (`[config]`, default 10 MB) stops a run when substitution output grows past it.
- **`execsql.log`** is created with mode `0o600` on POSIX instead of the umask default.
- **`-a NAME VALUE`** values are logged as `***` when the name contains `PASSWORD`, `SECRET`, `TOKEN`, `PASSWD`, `PRIVATE_KEY` or `CREDENTIAL`.
- **`--dsn` with an embedded password** prints a warning, since it is visible in `ps` and shell history.
- **`IMPORT` and `EXPORT … FORMAT xlsx`** reject zip-bomb files (a member compressed over 100:1, or over 500 MB uncompressed).
- **ODS `IMPORT` and `EXPORT`** are protected against XML entity attacks; `defusedxml` is now in the `[formats]` extra.
- **`IMPORT … ODS PATTERN` / `XLS PATTERN`** with an invalid regex reports the pattern instead of crashing with `re.error`.
- **`IMPORT … FROM JSON`** reads JSON Lines files line by line, using less memory.
- **Storing a password in a plaintext keyring** (such as `keyrings.alt.file.PlaintextKeyring` on headless Linux) prints a one-time warning.
- **GUI on headless POSIX** (no `$DISPLAY` or `$WAYLAND_DISPLAY`) skips Tkinter and uses the Textual or Console backend instead of failing with `_tkinter.TclError`.
- **Docs:** `$CURRENT_DATE`, `$CURRENT_SCRIPT_LINE`, the `[map]` extra and `RUN SCRIPT` (alias of `EXECUTE SCRIPT`) are documented; `SECURITY.md` describes the security defenses and known limitations.

### Changed

- **`templates/{pg,md,ss}_{upsert,compare,glossary}.sql`** use `!'!#var!'!`, so single quotes in arguments are escaped.
- **`--output-dir`** confines output: absolute or `..` paths that escape it are rejected (stdout is unaffected). It now also applies to `EXPORT QUERY`, `EXPORT … WITH TEMPLATE`, `EXPORT METADATA` and multi-sheet `EXPORT ODS` / `XLSX`, which ignored it.

### Fixed

- **`templates/script_template.sql`**: the `Committing:` and `Cleaning up:` `WRITE` lines have their closing quotes.
- **`ends_with(string, "")`** is true for any string; it used to be true only for an empty string.
- **ODBC DSN connections**: a user or password containing `;` can no longer add connection-string attributes.
- **`!"!var!"!`** doubles embedded `"`, so a value cannot close the identifier and start another statement.
- **`!'!var!'!`** escapes `\` on every platform, not only Windows, closing `\'` injection into MySQL and PostgreSQL E-string literals.
- **Substitution variables** containing a NUL byte are rejected when used in any of the three forms (`!!var!!`, `!'!var!'!`, `!"!var!"!`).
- **`EXPORT … FORMAT sqlite` / `duckdb`** quote the table name, closing SQL injection through it.
- **MySQL / MariaDB and SQL Server** quote identifiers with backticks and brackets, so quoting works whatever `sql_mode` or `QUOTED_IDENTIFIER` is set.
- **`IMPORT` into SQLite** inserts in batches of `import_row_buffer` (default 1000) rows, 10–100× faster on large files.
- **MySQL table, column and view existence checks** honour `@@lower_case_table_names`: with `1` or `2` (Windows, macOS), `MyTable` matches `mytable`.

### Removed

- **CSV / XLSX / ODS `EXPORT`** no longer prefixes `'` to strings starting with `=`, `+`, `-`, `@` or tab; values are written verbatim. The `csv_safe_formulas` config key is removed.

______________________________________________________________________

## [2.17.3] - 2026-05-26

### Changed

- **The `[upsert]` extra** requires `pg-upsert>=1.22.1`, so it installs alongside the latest Typer and PyYAML without a resolver conflict.

______________________________________________________________________

## [2.17.2] - 2026-05-26

### Fixed

- **`!'!var!'!`** wraps the value in single quotes as documented; it used to only double embedded apostrophes.
- **`BREAK`** inside an `EXECUTE SCRIPT` body is an error instead of ending the caller's `LOOP`.
- **`WRITE SCRIPT`** output can be included again: nested `IF` / `LOOP` / `BATCH` / `SQL` blocks, `INCLUDE`, `EXECUTE SCRIPT` and comments are kept, and `BEGIN/END SCRIPT` lines carry `-- !x!`.
- **`PROMPT MAP`** falls back to the table view when the map can't be built (headless display, missing dependencies).
- **`TABLE_EXISTS` / `VIEW_EXISTS`** match names case-insensitively on SQLite, Oracle, Firebird and Access, and work on Access 2016+ with default permissions.
- **Oracle `ROLE_EXISTS`** works for non-DBA accounts.
- **SQL Server connections, PostgreSQL / MySQL `IMPORT` and closing a database** no longer fail with `AttributeError` when used from the library before a run starts.
- **File output** finishes instead of hanging when the background file writer crashes.

### Removed

- Internal: the legacy command-list engine. Code importing `CommandList` / `IfLevels` from `execsql.script`, or reading `_state.commandliststack` / `_state.if_stack` / `_state.savedscripts`, should use `_state.current_localvars()`, `_state.current_paramvals()` and `_state.ast_exec_stack`.

______________________________________________________________________

## [2.17.1] - 2026-05-22

### Fixed

- **VS Code grammar** highlights `!'!name!'!` and `!"!name!"!` as well as `!!name!!`; regenerate it with `just install-vscode`.
- **Docs:** broken cross-links and the `--profile` description (now mentions `--profile-limit`) are fixed.

### Added

- **Docs:** a "Quoting Convention" section in `docs/reference/substitution_vars.md` covers how `SUB`, substitution and `EXECUTE SCRIPT` arguments handle quotes, including the `wo_quotes()` pitfall. Newly documented: the `DEBUG WRITE …` variants, `PROMPT MAP`, `IS_FALSE`, `RUN` (alias of `EXECUTE`), and `--progress`, `--profile-limit`, `--no-system-cmd`, `--config`, `--init-config`.

______________________________________________________________________

## [2.17.0] - 2026-05-07

### Changed

- **`PG_UPSERT`, `PG_UPSERT QA` and `PG_UPSERT CHECK`** no longer raise an error when QA checks fail (**behavior change**). Check `$PG_UPSERT_QA_PASSED`, `$PG_UPSERT_TABLE_QA_PASSED` and `$PG_UPSERT_RESULT_JSON` with `IF` or `ASSERT`; `EXPORT_FAILURES` still runs and the upsert is still skipped. To halt as before, add `ASSERT IS_TRUE(!!$PG_UPSERT_QA_PASSED!!) "QA failed"`. (Corrected after release: this note first gave an `=` comparison, which is not a valid condition.)

### Fixed

- **`!!$COUNTER_N!!`** in metacommands (`WRITE`, `IF`, `SUB`, …) counts `1, 2, 3, …` from 1 as documented; `!!$RANDOM!!` and `!!$UUID!!` are also stable within a metacommand.

______________________________________________________________________

## [2.16.18] - 2026-05-05

### Fixed

- **`BEGIN SCRIPT` parameter defaults** have surrounding quotes stripped; `default_unit_set="Default"` used to bind `"Default"` with the quotes.

### Changed

- **`SHOW SCRIPTS <name>` and `.scripts <name>`** show the full source path (`<inline>` for `-c` scripts).
- **`BEGIN SCRIPT WITH PARAMETERS (...)`** accepts quoted defaults containing spaces, commas and other special characters, and rejects an unterminated quoted value instead of storing it.

______________________________________________________________________

## [2.16.17] - 2026-05-04

### Fixed

- **Formatter:** lines after an inline `IF (cond) { command }` are no longer indented as if inside a block.
- **Formatter:** blank lines inside `BEGIN SQL` / `BEGIN BATCH` blocks are kept.

______________________________________________________________________

## [2.16.16] - 2026-05-02

### Added

- **`--init-config`** prints a commented default `execsql.conf`: `execsql --init-config > execsql.conf`.
- **`--no-system-cmd`** disables `SYSTEM_CMD` / `SHELL`; also `allow_system_cmd = No` in `[config]` or `allow_system_cmd=False` in the library API.

### Changed

- **`--help`** groups options: connection, encoding, import/export, execution, GUI, configuration, information.
- **The `execsql.conf` template** lists the missing options (`use_keyring`, `gui_framework`, `allow_system_cmd`, `log_sql`, `max_log_size_mb`, `show_progress`, `import_progress_interval`, `macos_config_file`), corrects the `password_prompt`, `new_db` and `scan_lines` defaults, and adds DuckDB (`k`).

### Fixed

- **`SYSTEM_CMD`** no longer wraps arguments containing `&` in double quotes.

______________________________________________________________________

## [2.16.15] - 2026-05-02

### Changed

- **`SHOW SCRIPTS [<name>]`** replaces `SHOW SCRIPT <name>`: without a name it lists all scripts, with one it shows detail.

______________________________________________________________________

## [2.16.14] - 2026-05-01

### Fixed

- **`ELSEIF`** supports `ANDIF` / `ORIF`; they used to attach to the parent `IF`.
- **`EXPORT` and `COPY`** close their cursor when the query fails.

______________________________________________________________________

## [2.16.13] - 2026-05-01

### Added

- **`execsql-format --indent`** also sets SQL indentation, not only metacommand indentation.
- **`execsql-format --leading-comma`** puts commas at the start of lines.

### Fixed

- **`execsql-format`**:
    - comments inside multi-line SQL no longer split the statement, turn commas into semicolons or drop text;
    - `/* */` comments containing `-- !x!` are left intact;
    - blank lines inside multi-line SQL no longer split the statement;
    - falls back to the original text when sqlglot returns a different number of statements.

______________________________________________________________________

## [2.16.12] - 2026-05-01

### Changed

- Internal: parser tests for `SHOW SCRIPTS` and parameter defaults; no user-visible changes.

______________________________________________________________________

## [2.16.11] - 2026-05-01

### Fixed

- **Multi-line `/* */` docstrings** in `BEGIN SCRIPT` are captured in full; they used to stop after the first line.

______________________________________________________________________

## [2.16.10] - 2026-05-01

### Fixed

- **`EXECUTE SCRIPT !!#script_name!!`** works with a substituted script name; it used to fail with "should be handled by the AST executor".

______________________________________________________________________

## [2.16.9] - 2026-05-01

### Added

- **`SHOW SCRIPTS`** lists registered scripts with their parameters and source locations; **`SHOW SCRIPT <name>`** shows one script's parameters, source file and lines, and docstring. The REPL's `.scripts` and `.scripts <name>` do the same.
- **Parameter defaults:** `BEGIN SCRIPT load(schema, table, batch=1000)`; parameters with defaults may be omitted at the call and must follow required ones.
- **Script docstrings:** `--` or `/* */` comments right after `BEGIN SCRIPT`, up to a blank line, are shown by `SHOW SCRIPTS`, `SHOW SCRIPT` and `.scripts`.

______________________________________________________________________

## [2.16.8] - 2026-04-30

### Fixed

- **SQL comments** (`--`, `/* */`) inside a multi-line statement no longer split it.

______________________________________________________________________

## [2.16.7] - 2026-04-30

### Fixed

- **`ANDIF` / `ORIF`** short-circuit: `IF (sub_defined(x)) ANDIF (not sub_empty(x))` no longer fails with "Unrecognized substitution variable" when `x` is undefined.
- **`IF`, `LOOP` and `INCLUDE` errors** report their own source line, not the previous command's.

______________________________________________________________________

## [2.16.6] - 2026-04-30

### Fixed

- **`execsql-format`** leaves PL/pgSQL in `$$` blocks alone; it used to rewrite `IF NOT EXISTS … END IF` and similar as `COMMIT;`.
- **Debug REPL `.vars`** shows the current script's `~` local and `#` parameter variables; `.vars ~myvar` and `.set ~myvar value` use that scope.

______________________________________________________________________

## [2.16.5] - 2026-04-30

### Fixed

- **Debug REPL `.vars` and `.set`** read and write the current script's `~` local and `#` parameter variables, not only globals.

______________________________________________________________________

## [2.16.4] - 2026-04-30

### Fixed

- **`EXECUTE SCRIPT foo`** can come before `BEGIN SCRIPT foo` in the same file or an `INCLUDE`d one.

______________________________________________________________________

## [2.16.3] - 2026-04-30

### Fixed

- **`BEGIN SCRIPT name(params)`** with no space before `(` is recognized; the block used to be ignored, so `END SCRIPT` failed.

______________________________________________________________________

## [2.16.2] - 2026-04-30

### Fixed

- **`INCLUDE`** strips quotes around a path, as in `-- !x! INCLUDE "!!path!!/file.sql"`.

______________________________________________________________________

## [2.16.1] - 2026-04-30

### Fixed

- **`~` (local) and `+` (outer-scope) variables in `SCRIPT` blocks** are visible to later SQL; they used to be lost, with spurious "potential un-substituted variable" warnings.
- **`EXECUTE SCRIPT` arguments** such as `val=!!#parent_param!!` expand in the caller's scope, so nested scripts can pass `~` or `#` variables.

### Changed

- **`execsql.run`** is safe to call from several threads at once.

______________________________________________________________________

## [2.16.0] - 2026-04-29

### Added

- **`--parse-tree`** prints a script as a tree: block nesting (`IF`/`LOOP`/`BATCH`/`SCRIPT`), source line ranges, compound conditions and metacommands. No database connection needed.
- **Plugins** (`execsql.plugins`): custom metacommands, exporters and importers load at startup from the `execsql.metacommands`, `execsql.exporters` and `execsql.importers` entry points. `--list-plugins` lists them.
- **Python API:** `from execsql import run` runs a script and returns a `ScriptResult` (success, command count, timing, errors, final variables). Takes a DSN string or an existing connection, substitution variables and error-control options.
- **`enc_password`** in a config file gives a deprecation warning; use keyring or environment variables.
- **`&` environment variables** leave out sensitive names (`*SECRET*`, `*TOKEN*`, `*PASSWORD*`, etc.).

### Changed

- **New execution engine** (transparent): scripts are parsed before they run, and a circular `INCLUDE` is detected.
- **`BREAK` outside `LOOP`** is an error (exit 1); it used to be ignored.
- **`--lint`** reports unmatched `IF`/`LOOP`/`BATCH`/`SCRIPT` blocks with their line ranges, without a database connection.
- **The default database type is SQLite** (`-t l`), not Access; pass `-t a` for Access.

### Fixed

- **[Critical]** **`ON ERROR_HALT` / `ON CANCEL_HALT` `WRITE` and `EMAIL`** no longer crash when they run.
- **`EXECUTE`** quotes the procedure, function or view name on every DBMS, closing an SQL injection.
- **`EXECUTE` on ODBC DSN and SQL Server** sends SQL as text, not bytes.
- **Passwords** are cleared from memory once connected.
- **Cyclic substitution variables** stop after 100 rounds instead of looping forever.

### Removed

- **`--ast` / `--no-ast`**: the new engine is the only one.

______________________________________________________________________

## [2.15.11] - 2026-04-27

### Fixed

- **`PAUSE` without a GUI** no longer hangs on Windows when stdin is a terminal.

______________________________________________________________________

## [2.15.10] - 2026-04-27

### Added

- **`--config FILE`** reads a configuration file after the usual ones, so its values win over theirs but not over command-line options.
- **`$HOSTNAME`** holds the name of the machine running execsql.

### Fixed

- **Chained config files** (`config_file`) are read reliably.
- **`PAUSE` without a GUI** no longer crashes on Windows.
- **`HAS_ROWS` and `ROW_COUNT_*` conditions** quote the table name, so a name from a substitution variable cannot inject SQL.

______________________________________________________________________

## [2.15.9] - 2026-04-27

### Added

- **Textual `PAUSE` and `PROMPT PAUSE`** with `CONTINUE AFTER` / `HALT AFTER` show a progress bar and countdown, as Tkinter does.

### Fixed

- **`PAUSE` without a GUI** (no `-v`):
    - takes single keypresses: Enter continues, Esc quits;
    - shows a live countdown bar with `CONTINUE AFTER` / `HALT AFTER`;
    - waits the time given; a 1-minute pause used to wait 60 minutes.

______________________________________________________________________

## [2.15.8] - 2026-04-20

### Added

- **`PG_UPSERT`, `PG_UPSERT QA` and `PG_UPSERT CHECK`** accept `STRICT_COLUMNS`: any column missing from a staging table is an error, not only primary key and NOT NULL columns without a default.
- **`$PG_UPSERT_QA_WARNINGS`** lists the tables with WARNING-level QA findings.

### Changed

- **`$PG_UPSERT_RESULT_JSON`** has a `qa_warnings` array per table.
- **The `upsert` extra requires pg-upsert 1.22.0** or later.

### Fixed

- **`PG_UPSERT QA` and `PG_UPSERT CHECK`** report warnings as well as errors.

______________________________________________________________________

## [2.15.7] - 2026-04-20

### Fixed

- **Counter variables** (`!!$COUNTER_n!!`) are substituted in the first two characters of a line too.
- **MySQL `LOAD DATA INFILE`** escapes the file path, delimiter and quote character, closing an SQL injection.
- **`EXECUTE` on SQLite and DuckDB** works; it always failed with `TypeError`.
- **Database cursors** are closed after use on every DBMS.
- **Config file chaining** stops after 20 files, so a `config_file` cycle no longer loops forever.
- **Temporary files** are created without a race between naming and opening them.
- **`EXPORT … AS JSON`** escapes column names; a quote or backslash in a name made invalid JSON.
- **PostgreSQL `VACUUM`** restores the session's autocommit setting even when it fails.
- **`EXPORT … AS HTML`** escapes the description, author and CSS link.
- **`SYSTEM_CMD` on Windows** keeps backslashes in the command line.
- **MySQL connections** with no server, database or user name no longer send the text `None`.

______________________________________________________________________

## [2.15.6] - 2026-04-16

### Fixed

- **Nested variable names** such as `!!N_!!CHECK_GROUP!!_CHECKS!!` resolve again; 2.15.0 broke them.

______________________________________________________________________

## [2.15.5] - 2026-04-15

### Fixed

- **Type inference** no longer reads a time-only value like `13:15:45` as a timestamp; CSV imports into PostgreSQL failed with `InvalidDatetimeFormat`.

______________________________________________________________________

## [2.15.4] - 2026-04-15

### Fixed

- Internal: Windows test fix.

______________________________________________________________________

## [2.15.3] - 2026-04-15

### Added

- **`auth-plaintext` and `auth-encrypted` extras** install a file-based keyring backend for headless Linux (`keyring` + `keyrings.alt`; `auth-encrypted` adds `pycryptodome` for encryption).

______________________________________________________________________

## [2.15.2] - 2026-04-14

### Changed

- **Large imports** are faster: data type detection does less work per value.

### Fixed

- **Type error messages** call the text type `text`, not `character`.
- **`varchar` values** that are not strings are converted, and values over 255 characters are rejected.
- **Conditions** with an unrecognized part raise an error instead of evaluating to nothing.
- **Division by zero in a numeric expression** gives an execsql error instead of a Python `ZeroDivisionError`.

______________________________________________________________________

## [2.15.1] - 2026-04-14

### Added

- **`PROMPT COMPARE`** "Highlight Diffs" marks the differing cells of changed rows with a bullet, in every GUI backend.
- **`macos_config_file`** (`[config]`) names an extra config file to read on macOS, like `linux_config_file`.
- **`EXPORT`** logs an `action` record with the query, output file and source line.

### Changed

- **`linux_config_file`** applies only on Linux, not macOS; use `macos_config_file` there.
- **Dates and times** are parsed with `python-dateutil`: ISO 8601 with a `T` separator, microseconds, a `Z` suffix and named time zones are recognized.

### Fixed

- **Numeric expressions** are left-associative: `10 - 3 - 2` is `5`, not `9`; the same for division.
- **`IMPORT` into SQLite** applies `trim_strings`, `replace_newlines` and `empty_strings`; they had no effect.
- **`$CURRENT_DATABASE` and `$CURRENT_DBMS`** update after `USE`.
- **`PROMPT COMPARE`**:
    - compares values by type, so `1` equals `1.0`, `10.00` equals `10.0`, and `True` equals `1`;
    - treats NULL and `""` as different;
    - summary stats match columns by name, leave key columns out of the diff, and keep the first row of a duplicate key.
- **`PG_UPSERT`** output goes only to the `LOGFILE` file, not `execsql.log`.
- **`win_config_file`** is read on Windows; it was ignored.

______________________________________________________________________

## [2.15.0] - 2026-04-09

### Added

- **`PG_UPSERT` fix sheets:** `EXPORT_FAILURES <dir>`, `EXPORT_FORMAT csv|json|xlsx` and `EXPORT_MAX_ROWS <n>` write the failing staging rows, each with an `_issues` column, in every mode and even when QA fails. `$PG_UPSERT_EXPORT_PATH` holds the directory.

### Changed

- **The `upsert` extra requires pg-upsert 1.21.0** or later.

### Fixed

- **`PROMPT MESSAGE … CREDENTIALS <user_var> <pw_var>`** works without a GUI, reading the password without echo; it used to crash.

______________________________________________________________________

## [2.14.1] - 2026-04-07

### Fixed

- Internal: Windows test fix.

______________________________________________________________________

## [2.14.0] - 2026-04-07

### Added

- **GUI tables** show a row count ("3 rows", "1 row", with thousands separators) in Textual, Tkinter and the console.
- **A Help button** opens the `HELP` URL in every dialog that takes `HELP`.
- **Compare dialogs** show a summary line ("3 matching | 1 differing | 2 only in Table 1") and a "Highlight Diffs" toggle that colors matching, changed and one-sided rows.
- **`PROMPT ENTRY_FORM`** enforces `validation_regex` on submit, `validation_key_regex` per keystroke, and required fields.

### Fixed

- **`CONFIG GUI_LEVEL 3`** (open the GUI console at start) is accepted, as in the `gui_level` setting.
- **`PROMPT COMPARE`** stacks the tables for `AND` and puts them side by side for `BESIDE`; both were side by side.
- **`PROMPT ENTRY_FORM`** renders `listbox`, `radiobuttons`, `textarea`, `inputfile` and `outputfile` entries; only `checkbox` and `dropdown`/`select` worked.
- **`PROMPT ENTER_SUB … HELP`** accepts URLs containing `+`.
- **PostgreSQL and DSN `CONNECT`** unquote `PASSWORD` like the other DBMSs.

### Removed

- **`PROMPT DISPLAY … FREE`**: it only worked in the console backend.

______________________________________________________________________

## [2.13.2] - 2026-04-06

### Changed

- **`--lint`**:
    - treats `SUB_EMPTY`, `SUB_ADD`, `SUB_APPEND` and `SUBDATA` as defining a variable;
    - sees variables defined in scripts run by `EXECUTE SCRIPT` / `EXEC SCRIPT` / `RUN SCRIPT`;
    - no longer depends on definition order;
    - reads `SUB_INI` files for variable names;
    - warns when `EXECUTE SCRIPT` names a missing script (unless `IF EXISTS`);
    - lists errors before warnings, each by line, with aligned locations.

______________________________________________________________________

## [2.13.1] - 2026-04-04

### Changed

- **The `upsert` extra requires pg-upsert 1.20.0** or later.

______________________________________________________________________

## [2.13.0] - 2026-04-04

### Added

- **`IMPORT … FROM JSON`** loads a JSON array of objects or a [JSON Lines](https://jsonlines.org/) file. Nested objects become dot-separated column names, nested arrays JSON strings, and missing keys NULL.
- **`SHELL … CONTINUE`** sets `$SYSTEM_CMD_PID` to the background process's PID.

### Fixed

- **Exiting** no longer raises errors from open file, email or zip writers.

______________________________________________________________________

## [2.12.7] - 2026-04-03

### Fixed

- **The `upsert` extra requires pg-upsert 1.18.2**, whose interactive foreign key check dialog shows every violating row, not just one.

______________________________________________________________________

## [2.12.6] - 2026-04-03

### Added

- **`PG_UPSERT` per-table progress:** `$PG_UPSERT_CURRENT_TABLE`, `$PG_UPSERT_TABLE_QA_PASSED`, `$PG_UPSERT_TABLE_ROWS_UPDATED` and `$PG_UPSERT_TABLE_ROWS_INSERTED` update as each table is processed.
- **`PG_UPSERT … CLEANUP`** drops the `ups_*` temporary tables and views afterwards; by default they stay for inspection.

______________________________________________________________________

## [2.12.5] - 2026-04-03

### Fixed

- Internal: test fix.

______________________________________________________________________

## [2.12.4] - 2026-04-03

### Added

- **`PG_UPSERT`** runs QA-checked upserts from a staging schema to a base schema on PostgreSQL, in foreign key order, using [pg-upsert](https://pg-upsert.readthedocs.io/) (`pip install execsql2[upsert]`).
    - Modes: full pipeline (`PG_UPSERT FROM … TO … TABLES …`), QA only (`PG_UPSERT QA …`) and schema check (`PG_UPSERT CHECK …`).
    - Keywords: `METHOD`, `COMMIT`, `INTERACTIVE`, `COMPACT`, `EXCLUDE`, `EXCLUDE_NULL`, `LOGFILE`.
    - Sets 12 `$PG_UPSERT_*` substitution variables.

______________________________________________________________________

## [2.12.3] - 2026-04-02

### Changed

- **Faster runs:** less per-statement work refreshing system variables, and `$RANDOM` and `$UUID` are computed only when referenced.
- **Faster CSV/TSV `IMPORT`** with comma, tab, semicolon or pipe delimiters.

______________________________________________________________________

## [2.12.2] - 2026-04-02

### Added

- **Security reference:** setting up a keyring on a headless Linux server (encrypted or plaintext file backend).

### Changed

- **`ASSERT` failures** report `**** Assertion failed.` instead of `**** Error in metacommand.`

______________________________________________________________________

## [2.12.1] - 2026-04-02

### Changed

- **Faster runs:** less per-statement overhead and batched row fetching.

### Fixed

- **Query cursors** are closed even when reading stops early.

______________________________________________________________________

## [2.12.0] - 2026-04-01

### Added

- **Debug REPL:**
    - `.where` / `.w` shows the script file, line and next statement; the banner shows the location (`[Breakpoint] myscript.sql:42`).
    - `.set VAR VAL` sets a substitution variable during a `BREAKPOINT` session.
    - ANSI color on a terminal; `NO_COLOR` or `EXECSQL_NO_COLOR` turns it off.
    - Aliases `.h` (`.help`), `.v` (`.vars`) and `.v all` (`.vars all`).
    - The banner says "Step" instead of "Breakpoint" after `.next`.
- **`--profile-limit N`** sets how many statements the `--profile` summary lists (default 20).

______________________________________________________________________

## [2.11.1] - 2026-04-01

### Fixed

- **`ASSERT`** no longer crashes when there is no execution log.
- **`--ping`** tries every version query instead of stopping after the first.
- **`CONSOLE SET WIDTH` / `HEIGHT`** no longer crash.
- **`$ERROR_MESSAGE`** for a non-halting error holds the full message, with script location and timestamp.
- **Non-halting SQL and metacommand errors** are written to `execsql.log`.
- **Appending YAML exports** writes a `---` separator, so the file is a valid multi-document stream.

______________________________________________________________________

## [2.11.0] - 2026-04-01

### Added

- **`--debug`** starts the script in step mode: the debug REPL pauses before each statement, as if `BREAKPOINT` were at the top with `.next` always on.

### Changed

- **`BREAKPOINT`** pauses before each statement instead of after, so you can inspect it before it runs.

### Fixed

- **The `BREAKPOINT` REPL** no longer wraps variable values in extra single quotes.
- **Error messages** include the script file and line number.
- **`$ERROR_MESSAGE`** updates on every error; it used to stay empty.
- **Metacommand errors** with `halt_on_metacommand_err` report the real error, not "Unknown metacommand".
- **Structural warnings** (`IF` level mismatches, unsubstituted variables) always appear on stderr, whatever `write_warnings` says.

______________________________________________________________________

## [2.10.1] - 2026-04-01

### Fixed

- **`BREAKPOINT`** finds a variable named with its prefix (`$`, `&`, `@`, `#`, `~`); `$logfile` used to show `(undefined)`.

______________________________________________________________________

## [2.10.0] - 2026-04-01

### Added

- **`BREAKPOINT`** pauses the script in an interactive debug REPL: `continue`/`c`, `abort`/`q`, `vars`, `$VARNAME`, `SELECT …;`, `next`/`n` to step, `stack`, `help`. Skipped when not on a TTY (CI, piped input).
- **`ROW_COUNT_GT(table, N)`, `ROW_COUNT_GTE`, `ROW_COUNT_EQ`, `ROW_COUNT_LT`** conditions compare a table's or view's row count to a number in `IF`, `ELSEIF` and `ASSERT`.

______________________________________________________________________

## [2.9.0] - 2026-04-01

### Added

- **`--lint`** checks a script without connecting: unmatched `IF`/`ENDIF`, `LOOP`/`END LOOP` and `BEGIN BATCH`/`END BATCH` are errors (exit 1); possibly undefined `!!$VAR!!` and missing `INCLUDE` targets are warnings (exit 0).
- **`--ping`** tests a connection without a script: `execsql --ping --dsn <URL>` prints the server version and exits 0.

______________________________________________________________________

## [2.8.0] - 2026-04-01

### Added

- **`--profile`** prints the 20 slowest SQL and metacommand statements after the run.
- **`ASSERT`** halts with an error (when `HALT_ON_METACOMMAND_ERROR` is `ON`) if an `IF`-style condition is false, with an optional quoted message (default `Assertion failed: <condition>`). Skipped inside a false `IF` block.

### Changed

- **`--dry-run`** shows `!!$VAR!!` values already known at parse time (environment, `--assign-arg`, config, startup built-ins); variables set during the run stay unexpanded.

______________________________________________________________________

## [2.7.1] - 2026-04-01

### Fixed

- **`IMPORT` from CSV with `DEDUP_COL_HDRS`** no longer fails with `AttributeError: module 'execsql.state' has no attribute 'dedup_words'`.

______________________________________________________________________

## [2.7.0] - 2026-04-01

### Added

- **`FORMAT MARKDOWN` / `FORMAT MD`** export: GitHub-flavored pipe tables with column alignment and escaping.
- **`FORMAT YAML`** export: a list of records keeping native types. Requires PyYAML (`formats` extra).
- **`FORMAT XLSX`** export with bold headers, native types and a "Datasheets" inventory sheet; `EXPORT table1, table2 TO file.xlsx AS XLSX` writes one sheet per table.

______________________________________________________________________

## [2.6.0] - 2026-04-01

### Added

- **Textual TUI** can save console output to a file, as Tkinter does, and its dialogs show keyboard hints (Escape to cancel, Enter to submit).
- **`get_context()` / `set_context()`** give Python code access to the active runtime context.
- **Divergence from Upstream** docs page (`docs/about/divergence.md`).

______________________________________________________________________

## [2.5.0] - 2026-04-01

### Added

- Internal: API docstrings, a developer architecture guide, exporter protocol types and cursor cleanup in database adapters.

______________________________________________________________________

## [2.4.6] - 2026-03-31

### Changed

- **Documentation** reorganized into `getting-started/`, `reference/`, `guides/` and `about/` sections.

______________________________________________________________________

## [2.4.5] - 2026-03-31

### Added

- **README** covers VS Code syntax highlighting and the pre-commit hook.

### Fixed

- **`ON ERROR_HALT EXECUTE SCRIPT` and `ON CANCEL_HALT EXECUTE SCRIPT`** are recognized.
- **`EXTEND SCRIPT <X> WITH SCRIPT <Y>`** is recognized; only `APPEND SCRIPT` worked.
- **`PROMPT ASK`** accepts `'…'` and `[…]` questions and an unquoted `HELP` argument.
- **`CONNECT TO SQLSERVER`** accepts mixed quoting (quoted SERVER with unquoted DB, for example) and a quoted PASSWORD.

______________________________________________________________________

## [2.4.4] - 2026-03-30

### Fixed

- Internal: PyPI publishing and test fixes.

______________________________________________________________________

## [2.4.3] - 2026-03-30

### Added

- **Pre-commit hook `execsql-format`**: add the repo to `.pre-commit-config.yaml` and pass `--check` or `--in-place` in `args`.

______________________________________________________________________

## [2.4.2] - 2026-03-30

### Changed

- Internal: test coverage floor raised; no user-visible changes.

______________________________________________________________________

## [2.4.1] - 2026-03-30

### Fixed

- **`--dsn`** overrides connection settings from configuration files.
- **MySQL `LOAD DATA INFILE`** maps Python encoding names (`utf-8`) to MySQL charsets (`utf8mb4`).
- **Import errors** are reported again instead of raising a second error.

______________________________________________________________________

## [2.4.0] - 2026-03-30

### Added

- **Python 3.14** support.

### Changed

- **`Database` subclasses** must implement `open_db()` and `exec_cmd()`; a missing one raises `TypeError` at instantiation instead of `DatabaseNotImplementedError` when called.
- **Metacommand dispatch and variable substitution** are faster.

### Fixed

- **ODS import and export** work again (broken since the modular refactor).
- **`--dsn` password** reaches MySQL, SQL Server, Oracle, Firebird and DSN connections; only PostgreSQL got it.
- **Import failures** report their error instead of `AttributeError: 'tuple' has no attribute 'replace'`.
- **MySQL `LOAD DATA LOCAL INFILE`** maps Python encoding names to MySQL charsets.
- **`--dsn`** overrides conf-file server, database, user and port; conf-file values used to win.

______________________________________________________________________

## [2.3.0] - 2026-03-30

### Added

- **Security documentation** (`docs/security.md`): trust model, `SHELL`, credentials, file system access, SMTP and SQL variable substitution.

### Fixed

- **Access and SQL Server** redact ODBC passwords (`Pwd=***`) in the log.

______________________________________________________________________

## [2.2.1] - 2026-03-26

### Fixed

- Internal: Windows test fixes.

______________________________________________________________________

## [2.2.0] - 2026-03-26

### Added

- **`py.typed`** marker for downstream type checking (PEP 561).
- **`--progress`**, `CONFIG SHOW_PROGRESS` and the `show_progress` config option show a progress bar during long `IMPORT`s.
- **`log_sql`** config option and `CONFIG LOG_SQL` log every executed statement as a `sql` record with database name, line number and query text.
- **`--dump-keywords`** prints metacommand keywords, conditions, config options, export formats, database types and variable patterns as JSON, for editor tooling.
- **VS Code syntax highlighting** extension in `extras/vscode-execsql/`, generated from the metacommand list.
- **Keyring credential storage** documented in the usage notes.

### Changed

- **`ErrInfo`, `DataTypeError`, `DbTypeError` and `DatabaseNotImplementedError`** inherit from `ExecSqlError`.

### Fixed

- **ODS import and export** work when `odfpy` is installed; they were completely broken.
- **Exporters and the `WRITE`, prompt and control metacommands** close their files on error.
- **XML export** escapes cell values and replaces invalid characters in element names from column headers and table names.
- **HTML export** escapes column headers and cell values (XSS).
- **JSON export** serializes descriptions and column names safely.
- **Jinja2 template export** runs in a sandbox.
- **SQL injection** closed in table, schema, column, view and role existence checks on all databases, in the column name for whole-file imports on six databases, in PostgreSQL database creation (name, encoding, COPY delimiter and quote), and in ODS/XLS sheet names in `$SHEETS_TABLES_VALUES`.
- **`SERVE`** sanitizes the `Content-Disposition` filename (header injection).
- **File writing** no longer busy-loops the CPU.
- **Substitution variables** that refer to each other in a cycle stop after 100 passes.
- **Database type casts** restored; they were empty after the refactor.
- **`EXPORT … AS PARQUET`** works; it was unreachable.
- **`CONNECT TO DSN`** works; it was unreachable.
- **`WRITE`** accepts the tilde, hash, backtick, bracket and single-quote delimiters again, and the bare (non-`CONFIG`) settings aliases are back.
- **`TXT-AND` / `TEXT-AND`** export format aliases restored.

______________________________________________________________________

## [2.1.2] - 2026-03-25

### Fixed

- **`db_type = k`** (DuckDB) is accepted in `execsql.conf`; only `-t k` worked.

______________________________________________________________________

## [2.1.1] - 2026-03-25

### Added

- **Keyring retry:** when a stored password is rejected, execsql deletes it, prompts for the current one, retries and saves it. All databases.
- **Substitution variables docs** warn that `&`-prefixed variables expose environment variables, with mitigations.

### Fixed

- **`ExecSqlTimeoutError`** inherits from `ExecSqlError`, so `except ExecSqlError` catches timeouts; its message defaults to "Operation timed out".
- **ODS import and export** work; they silently did nothing.
- **Python 3.10** works (no `datetime.UTC`).
- **SQLite connections** close on reset and when an SQLite export fails.

______________________________________________________________________

## [2.1.0]

### Added

- **`--dsn` / `--connection-string`** takes a database URL (`postgresql://user:pass@host:5432/db`); schemes `postgresql`, `postgres`, `mysql`, `mariadb`, `mssql`, `sqlserver`, `oracle`, `firebird`, `sqlite`, `duckdb`. Overrides `-t`/`-u`/`-p` and the positional server and database.
- **`--dry-run`** indents multi-line statements under their first line instead of truncating them.
- **`--output-dir DIR`** is the base for relative `EXPORT` paths; absolute paths and `stdout` are unchanged.
- **Feather, Parquet and HDF5 export** (`formats` extra).
- **OS keyring** password storage (macOS Keychain, Windows Credential Manager, Linux SecretService), checked before prompting. `use_keyring` config option, default `yes`; requires the `auth` extra.
- **`max_log_size_mb`** (default `0`, off) rotates the log to `.1` before a run when it exceeds the size.
- **`import_progress_interval`** logs a status line every N rows during `IMPORT` (default `0`, silent), plus a completion line.
- **Log records** carry ISO 8601 timestamps (`status`, `connect`, `action`, `user_msg`), and the `exit` record ends with the run duration.
- **Run IDs** include milliseconds (`%Y%m%d_%H%M_%S_NNN`) to avoid collisions.
- **API reference** docs (`docs/api/`) for `cli`, `db`, `exporters`, `importers` and `metacommands`.
- **`ExecSqlError`** base class for `ConfigError`, `ColumnError`, `DataTableError`, `OdsFileError`, `XlsFileError`, `XlsxFileError`, `ConsoleUIError`, `CondParserError` and `NumericParserError`.

### Changed

- **Extras:** `ods`, `excel`, `jinja`, `feather`, `parquet` and `hdf5` are replaced by `formats`; `keyring` is renamed `auth`; `all-db` installs every database driver.
- **PostgreSQL and SQLite connections** time out after 30 seconds by default.
- **`Database.quote_identifier()`** quotes an SQL identifier for the database's dialect.

### Fixed

- **`IMPORT`** always logs its completion record when a log is active; silent mode used to suppress it.
- **The `exit` log record** says `unknown` instead of `None` when the exit type is not set.
- **SQL injection** closed in schema, table, column, view and role existence checks on PostgreSQL, Oracle, DuckDB and SQLite.
- **Config options `only_strings`, `fold_column_headers`, `replace_newlines`, `import_row_buffer` and `css_styles`** take effect; they were written to the wrong setting.
- **`replace_newlines`** pattern fixed, and an all-NULL column no longer fails type detection.
- **DuckDB** timestamp, date and time columns use `TIMESTAMPTZ`, `TIMESTAMP`, `DATE` and `TIME` instead of `TEXT`.

### Removed

- **`FORMAT airspeed`** template export (Airspeed is unmaintained); use `FORMAT jinja`.

______________________________________________________________________

## [2.0.1] - 2026-03-23

### Fixed

- **`EXPORT` to HTML (append) and LaTeX** no longer fails with `PermissionError` on Windows.

______________________________________________________________________

## [2.0.0] - 2026-03-23

### Changed

- Forked from execsql by R.Dreas Nielsen and published on PyPI as `execsql2`; the command is still `execsql`.
- Supports Python 3.10 through 3.13; Python 2 support dropped.

______________________________________________________________________

## [1.130.0] - 2024-12-18

### Added

- Variable substitution to the `config_file` settings read from `execsql.conf`.

## [1.129.0] - 2024-05-21

### Added

- `PROMPT MESSAGE` metacommand that only displays a message in a dialog box.

## [1.128.0] - 2024-05-12

### Added

- Sash between the tables displayed by the `PROMPT COMPARE` metacommand so they can be resized.

## [1.127.0] - 2024-04-09

### Added

- Menu item to table displays allowing columns to be hidden or shown.

## [1.126.1] - 2024-02-16

### Added

- Templates and scripts to the distribution, to be placed in the `execsql_extras` directory.

### Changed

- Improved sorting in tables shown by the `PROMPT DISPLAY` and other metacommands.

### Fixed

- Width specification for listboxes in the `PROMPT ENTRY_FORM` metacommand.

## [1.126.0] - 2024-02-15

### Added

- Horizontal scrollbar to listboxes used with the `PROMPT ENTRY_FORM` metacommand.
- Radio button support for the `PROMPT ENTRY_FORM` metacommand.

## [1.125.3] - 2024-02-09

### Fixed

- Spurious warnings when running under Python 3.12.

## [1.125.0] - 2023-12-13

### Added

- Command-line and configuration settings to use an `execsql.log` file in the user's home directory.

## [1.124.0] - 2023-12-12

### Added

- Optional `HELP` clauses for most metacommands that produce GUI dialogs.

## [1.123.0] - 2023-08-22

### Added

- `RESET DIALOG_CANCELED` metacommand.

## [1.122.0] - 2023-07-27

### Added

- `FREE` keyword to the `PROMPT DISPLAY` metacommand.
- `$SCRIPT_START_TIME_UTC` and `$CURRENT_TIME_UTC` substitution variables.

## [1.120.0] - 2023-07-16

### Changed

- Extended the `PROMPT ENTRY_FORM` specifications to allow listboxes, specification of height for listboxes and text areas, and specification of columns to create a multi-column form.

## [1.119.0] - 2023-07-15

### Changed

- `WRITE` metacommand now runs in a separate process.

## [1.118.0] - 2023-07-09

### Added

- 'Save as' menu items to the `PROMPT COMPARE` UI.

### Changed

- Performance improvement for the data type evaluator used by `IMPORT` and `COPY` metacommands.

## [1.117.0] - 2023-06-10

### Added

- Support for DuckDB databases.
- `EXPORT` metacommand extended to export data to SQLite and DuckDB databases.

## [1.115.0] - 2023-04-06

### Added

- Export of multiple tables to an ODS workbook with a single `EXPORT` metacommand.

## [1.114.0] - 2023-04-01

### Added

- `DELETE_EMPTY_COLUMNS` configuration metacommand and setting.

## [1.113.0] - 2023-03-26

### Added

- `BREAK` metacommand to allow early exit of loops and sub-scripts.

## [1.112.0] - 2023-03-20

### Added

- `!"!` replacement delimiter for substitution variables.

## [1.111.0] - 2023-01-09

### Added

- `PROMPT CREDENTIALS` metacommand.

## [1.110.0] - 2022-12-20

### Added

- `$SHEETS_IMPORTED`, `$SHEETS_TABLES`, and `$SHEETS_TABLES_VALUES` system variables.

## [1.109.0] - 2022-12-13

### Added

- `CONFIG WRITE_PREFIX` and `CONFIG WRITE_SUFFIX` metacommands and configuration settings.

## [1.108.0] - 2022-11-17

### Changed

- Renamed the `EMIT` metacommand to `SERVE`.

## [1.107.0] - 2022-11-02

### Added

- `CGI-HTML` type for the `EXPORT` metacommand.
- `SUB_QUERYSTRING` and `EMIT` metacommands to support use of execsql as a CGI script.

## [1.106.0] - 2022-10-27

### Changed

- `table_exists()` and `view_exists()` conditionals for Postgres now only look for tables in the temporary-table schema or in a schema on Postgres' search path.

## [1.105.0] - 2022-10-19

### Added

- `CD` metacommand.

## [1.104.0] - 2022-10-15

### Added

- `trim_column_headers` configuration setting and configuration metacommand.

## [1.103.0] - 2022-07-23

### Changed

- Extended the `EXPORT_METADATA` metacommand to insert metadata into a database table.

## [1.102.0] - 2022-06-21

### Added

- Import from data files in Feather format.

## [1.101.0] - 2022-06-18

### Added

- Import from data files in Parquet format.

## [1.100.3] - 2022-04-30

### Fixed

- `PROMPT ENTRY_FORM` no longer closes the form when the 'Enter' key is pressed while a checkbox has focus.

## [1.100.1] - 2022-02-22

### Added

- Bottom border to the header row and top-alignment of body cells to ODS export.

## [1.100.0] - 2022-02-20

### Added

- `INITIALLY` clause to the `PROMPT ENTER_SUB` metacommand.

## [1.99.0] - 2022-02-19

### Added

- Variant `IMPORT` metacommands that use a `SHEETS MATCHING <regex>` clause to import multiple sheets from an OpenDocument or Excel workbook in one step.

## [1.98.0] - 2022-01-12

### Added

- `FOLD_COLUMN_HEADERS` configuration setting.

### Changed

- Column header cleaning now adds an underscore to the beginning of any column header that starts with a digit.

## [1.97.0] - 2022-01-08

### Added

- `CONTAINS`, `ENDS_WITH`, and `STARTS_WITH` conditional tests.

### Changed

- `textarea` control in an `ENTRY_FORM` now allows newlines to be inserted and strips trailing newlines.
- SQL statement evaluator now ignores multiple terminating semicolons.

## [1.96.0] - 2022-01-03

### Changed

- Reading of `.xlsx` files now uses the `openpyxl` library (new requirement).

## [1.95.0] - 2021-12-03

### Changed

- `SYSTEM_CMD` metacommand now logs the command to `execsql.log`.

## [1.94.0] - 2021-10-19

### Added

- `$PATHSEP` system variable.

### Changed

- `INCLUDE` and `IMPORT` metacommands now recognize leading tildes on the filename.

## [1.93.0] - 2021-10-02

### Added

- `USER` variant of the `CONNECT` metacommand.

## [1.92.0] - 2021-09-19

### Added

- `TRIM_STRINGS` and `REPLACE_NEWLINES` settings.

## [1.91.0] - 2021-09-16

### Added

- `DIALOG_CANCELED()` conditional.

## [1.90.0] - 2021-08-08

### Changed

- Metacommand patterns are now dynamically re-ordered to match usage.

## [1.89.1] - 2021-05-18

### Changed

- Column name `user` renamed to `username` in the output of the `EXPORT_METADATA` metacommand.

## [1.89.0] - 2021-03-17

### Added

- `TEE` clause to the `HALT` metacommand.

## [1.88.0] - 2021-02-13

### Added

- `EXPORT_METADATA` metacommand.

## [1.87.0] - 2021-02-10

### Added

- `ZIP` metacommand.

## [1.86.0] - 2021-02-09

### Added

- `create_column_headers` configuration setting and configuration metacommand.

## [1.85.0] - 2021-02-09

### Added

- `zip_buffer_mb` configuration setting and configuration metacommand.

## [1.84.0] - 2021-02-06

### Added

- `EXPORT` directly to a zip file for most export formats.

## [1.83.0] - 2021-01-09

### Changed

- Interpretation of both `config_file` and `linux_config_file` settings now expands a leading `~` to the user's home directory.

## [1.82.0] - 2020-11-14

### Added

- Console window size configuration options in `execsql.conf`.

### Changed

- Console height and width configuration metacommands now change settings for any future console windows as well as any currently open console.

## [1.81.0] - 2020-11-08

### Added

- `only_strings` configuration setting and metacommand.

## [1.80.0] - 2020-10-26

### Added

- `linux_config_file` and `win_config_file` configuration settings.

## [1.79.0] - 2020-08-29

### Added

- `ENCODING` clause to the `WRITE CREATE_TABLE` metacommand for text files.

## [1.78.0] - 2020-08-08

### Changed

- `PROMPT SELECT_ROWS` metacommand now sets a grey background on selected rows.

## [1.77.0] - 2020-07-29

### Added

- `$STARTING_SCRIPT_REVTIME` system variable.

## [1.76.0] - 2020-07-18

### Added

- Configuration option and metacommand to deduplicate repeated column headers in IMPORTed data.

### Changed

- Column header cleaning now strips leading and trailing spaces.

## [1.75.0] - 2020-07-16

### Added

- More quoting characters for the `WRITE` metacommand.

## [1.74.3] - 2020-07-11

### Fixed

- `ASK` metacommand under Python 3 on Windows.

## [1.74.1] - 2020-07-08

### Added

- `import_row_buffer` setting and `CONFIG IMPORT_ROW_BUFFER` metacommand to allow buffer size customization.

### Changed

- `IMPORT` metacommand now buffers input rows for slightly better performance.

## [1.73.0] - 2020-05-01

### Changed

- `execsql.log` is now set to read-only on exit.

## [1.72.2] - 2020-03-31

### Fixed

- Correction to 2020-03-30 modification.

## [1.72.0] - 2020-03-30

### Added

- `export_row_buffer` setting and `CONFIG EXPORT_ROW_BUFFER` metacommand to allow buffer size customization.

### Changed

- Export buffer size modified for better performance.

## [1.71.2] - 2020-03-29

### Added

- Encoding name translations to allow more encoding name aliases when using the `EXPORT` metacommand with Postgres.

## [1.71.0] - 2020-03-21

### Added

- `CONFIG LOG_DATAVARS` metacommand and `log_datavars` configuration setting.

## [1.70.0] - 2020-03-14

### Added

- `"!'!"` substitution delimiter.
- `SUB_EMPTY` conditional test.

## [1.69.0] - 2020-03-07

### Added

- Export to HDF5 files.

## [1.68.0] - 2020-03-03

### Added

- `IF EXISTS` clause to the `EXECUTE SCRIPT` metacommand.

## [1.67.0] - 2020-02-22

### Added

- `EXTEND SCRIPT WITH SQL` and `EXTEND SCRIPT WITH METACOMMAND` metacommands.
- `APPEND SCRIPT` aliased to `EXTEND SCRIPT...WITH SCRIPT`.

## [1.66.0] - 2020-02-22

### Added

- `DISCONNECT` metacommand.

## [1.65.0] - 2020-02-22

### Added

- `CONFIG SCAN_LINES` and `CONFIG GUI_LEVEL` metacommands.

## [1.64.0] - 2020-02-22

### Added

- `LOCAL` and `USER` keywords to the `DEBUG LOG SUBVARS` metacommand.

## [1.63.0] - 2020-02-15

### Changed

- `CONFIG` metacommands now accept `0` or `1` as arguments.

## [1.62.0] - 2020-02-13

### Added

- `CONFIG DAO_FLUSH_DELAY_SECS` metacommand and `dao_flush_delay_secs` configuration file setting.

## [1.61.0] - 2020-02-05

### Added

- `PROMPT PAUSE` metacommand.
- execsql version number is now written to `execsql.log`.

## [1.60.0] - 2020-02-01

### Added

- `LOOP` metacommand.

## [1.59.0] - 2020-01-31

### Added

- `$STARTING_PATH` and `$CURRENT_PATH` system variables.

## [1.58.0] - 2020-01-28

### Changed

- `PAUSE` and `ASK` metacommands now allow apostrophes and square brackets as string delimiters.

## [1.57.0] - 2020-01-25

### Changed

- Evaluation of conditionals now accepts Boolean literals.

## [1.56.0] - 2019-12-27

### Added

- `ROLE_EXISTS` conditional.

## [1.55.0] - 2019-12-26

### Added

- `CONTINUE` keyword to the `SYSTEM_CMD` metacommand.

## [1.54.0] - 2019-12-20

### Added

- `BEGIN`/`END SQL` metacommands.

## [1.53.0] - 2019-10-27

### Added

- Oracle database support.

## [1.52.0] - 2019-10-11

### Added

- Export to XML.

## [1.51.0] - 2019-10-10

### Added

- `WHILE` and `UNTIL` loop control to `EXECUTE SCRIPT`.
- Deferred variable substitution.

## [1.50.0] - 2019-10-05

### Added

- Numeric expression parser for the `SUB_ADD` and `SET COUNTER` metacommands.

## [1.49.0] - 2019-10-04

### Added

- Conditional expression parser for the `IF` metacommands.

## [1.48.0] - 2019-09-27

### Added

- `CONFIG EMPTY_ROWS` metacommand and `empty_rows` configuration setting.

## [1.47.0] - 2019-09-21

### Added

- `FROM` keyword to `PROMPT OPENFILE`, `SAVEFILE`, and `DIRECTORY` metacommands.

## [1.46.0] - 2019-09-04

### Added

- `COMPACT` keyword to the `PROMPT ACTION` metacommand.

## [1.45.0] - 2019-09-01

### Added

- `SCRIPT_EXISTS` conditional.
- `PROMPT ACTION` metacommand.

## [1.43.0] - 2019-08-27

### Added

- `PROMPT SELECT_ROWS` metacommand.

## [1.42.1] - 2019-08-22

### Fixed

- `EXPORT...AS VALUES` now correctly writes `NULL` for null data.

## [1.42.0] - 2019-08-18

### Added

- `APPEND SCRIPT` metacommand.

## [1.41.0] - 2019-08-17

### Added

- Export option to produce a JSON table schema.

## [1.40.0] - 2019-08-16

### Added

- `USER` keyword to the `DEBUG WRITE SUBVARS` metacommand.

## [1.39.0] - 2019-08-16

### Added

- `SUB_INI` metacommand.

## [1.38.8] - 2019-06-30

### Added

- Input and output filename prompt options to the entry form specifications.

## [1.37.7] - 2019-05-10

### Fixed

- Error messages containing bad data are now protected from encoding errors.

## [1.37.6] - 2019-05-07

### Changed

- Removed Unicode conversion of data when loaded into Tkinter Treeview control.
- Added `MARS_Connection=Yes` to SQL Server ODBC connections.

## [1.37.4] - 2019-05-04

### Added

- SQL Server ODBC drivers 13.1 and 17.

### Changed

- Improved efficiency of `COPY` metacommand.

### Fixed

- `int`/`long` conversion for Python 3 with Access.

## [1.37.0] - 2019-03-16

### Added

- `PASSWORD` keyword to the `CONNECT` metacommand for SQL Server.

## [1.36.0] - 2019-03-11

### Changed

- Switched to three-part semantic version number.

## [1.35.2.0] - 2019-02-27

### Added

- `WITH COMMIT|ROLLBACK` clause to the `AUTOCOMMIT ON` metacommand.

## [1.35.1.0] - 2019-02-23

### Added

- Warning if a SQL statement is incomplete when a metacommand is encountered.
- Error if a SQL statement is incomplete at the end of a script file.
- `CONFIG WRITE_WARNINGS` metacommand.

## [1.35.0.0] - 2019-02-21

### Changed

- Substitution metacommands now accept a `+` prefix to reference local variables in outer scopes.

## [1.34.9.0] - 2019-02-18

### Added

- `ON ERROR_HALT EXECUTE SCRIPT` and `ON CANCEL_HALT EXECUTE SCRIPT` metacommands.

## [1.34.8.0] - 2019-02-12

### Changed

- Improved reporting of origin lines of mismatched `IF` conditionals.

## [1.34.7.0] - 2019-02-09

### Added

- System variables for execsql's primary, secondary, and tertiary version numbers.
- Script name can now be specified on the `END SCRIPT` metacommand.

### Changed

- Quotes are now optional on the arguments to the `is_true`, `equal`, and `identical` conditionals.

## [1.34.4.0] - 2019-02-08

### Added

- Configuration option to clean IMPORTed column headers of non-alphanumeric characters.

## [1.34.2.0] - 2019-02-03

### Added

- Raises an exception if there is an incomplete SQL statement at `END SCRIPT`.
- Issues a warning if `IF` levels are unbalanced within a script.
- Issues a warning if a command appears to have an unsubstituted variable.

## [1.34.0.0] - 2019-02-02

### Added

- Optional `WITH ARGUMENTS` extension to the `EXECUTE SCRIPT` metacommand.
- Optional `WITH PARAMETERS` extension to the `BEGIN SCRIPT` metacommand.

## [1.33.0.0] - 2019-01-19

### Added

- `PROMPT ASK...COMPARE` metacommand.

### Changed

- All `ASK` metacommands and the `SUBDATA` metacommand can now set local variables.

## [1.32.0.0] - 2018-12-16

### Added

- Export to the Feather file format.

## [1.31.13.0] - 2018-11-07

### Added

- `quote_all_text` output setting and `CONFIG QUOTE_ALL_TEXT` metacommand.

## [1.31.12.0] - 2018-11-03

### Added

- `CONSOLE WIDTH` and `CONSOLE HEIGHT` metacommands.

### Changed

- `PROMPT ENTRY_FORM` now recognizes local variables.
- All `CONFIG` metacommands that take Boolean arguments now recognize both `Yes`/`No` and `On`/`Off`.

## [1.31.10.0] - 2018-10-30

### Added

- Asterisks to denote required entries on `PROMPT ENTRY_FORM`.

## [1.31.9.0] - 2018-10-29

### Added

- Fifth variable to `PROMPT OPENFILE` and `PROMPT SAVEFILE` to get the base filename without path or extension.

## [1.31.8.0] - 2018-10-25

### Changed

- `RM_FILE` metacommand now accepts wildcards.

## [1.31.7.0] - 2018-10-23

### Added

- Optional second, third, and fourth substitution variable names to `PROMPT SAVEFILE` for filename-only, path-only, and extension.

## [1.31.6.0] - 2018-10-22

### Added

- Optional third and fourth substitution variable names to `PROMPT OPENFILE` for path-only and extension.

## [1.31.5.0] - 2018-10-15

### Added

- Optional second substitution variable name to `PROMPT OPENFILE` for filename without path.

## [1.31.4.0] - 2018-10-14

### Added

- `ENCODING` clause to the `IMPORT...FROM EXCEL` metacommand.

## [1.31.3.0] - 2018-10-14

### Added

- Sorting of tabular displays by clicking on column headers.

### Changed

- All path separators returned by `PROMPT OPENFILE`, `SAVEFILE`, and `DIRECTORY` are converted from `/` to `\\` on Windows.

## [1.31.1.0] - 2018-10-09

### Added

- `LOCAL` clause to `DEBUG WRITE SUBVARS`.

## [1.31.0.0] - 2018-10-07

### Added

- Local variables.

## [1.30.6.0] - 2018-09-30

### Added

- Button to show unmatched rows in the `PROMPT COMPARE` display.
- `IF EXISTS` clause to the `INCLUDE` metacommand.
- `IF CONSOLE_ON` conditional test.

## [1.30.3.0] - 2018-09-29

### Added

- `IN <alias>` clauses to the `PROMPT COMPARE` metacommand.
- Checkbox to the `PROMPT COMPARE` GUI to allow highlighting of matches in both tables.

## [1.30.1.0] - 2018-09-23

### Changed

- `PROMPT COMPARE` command now highlights all matching rows in the other table, not just the first.

## [1.30.0.0] - 2018-09-22

### Changed

- Binary data length is now written as a description when binary data are used with `PROMPT DISPLAY` or `EXPORT AS TXT`.

## [1.29.3.0] - 2018-09-22

### Changed

- `WRITE` metacommand now uses the `make_export_dirs` configuration setting.

## [1.29.2.0] - 2018-09-19

### Added

- `SUB_ADD` metacommand.

### Changed

- `WITH` keyword is now optional in the `IMPORT` metacommand.

## [1.29.0.0] - 2018-09-12

### Added

- `IMPORT_FILE` metacommand.

## [1.28.0.0] - 2018-08-19

### Added

- Python 3.x compatibility (in addition to 2.7).

## [1.27.4.0] - 2018-08-19

### Changed

- Python version number is now written to `execsql.log`.

## [1.27.3.0] - 2018-07-31

### Changed

- Configuration files are now read from both the script directory and the starting directory, if different.

## [1.27.2.0] - 2018-07-30

### Added

- `SUB_EMPTY` metacommand.

## [1.27.1.0] - 2018-07-29

### Changed

- `ON ERROR_HALT WRITE` and `ON CANCEL_HALT WRITE` metacommands now allow single quotes and square brackets.

## [1.27.0.0] - 2018-07-29

### Changed

- Internal script processing routines rewritten.

## [1.26.8.0] - 2018-07-25

### Changed

- `WRITE` metacommand now allows single quotes and square brackets.
- Data format evaluation used by `IMPORT` now takes account of the `empty_strings` configuration setting.

### Fixed

- Stripping of extra spaces from input data when input is not strings.

## [1.26.5.0] - 2018-07-20

### Added

- `$PYTHON_EXECUTABLE` system variable.

### Changed

- Strings of only spaces are now treated as empty strings when `empty_strings=False`.

### Fixed

- Trailing space is now trimmed from the last column header of an IMPORTed CSV file.

## [1.26.4.3] - 2018-07-12

### Fixed

- Handling of double-quoted filenames by the `ON ERROR_HALT WRITE` and `ON CANCEL_HALT WRITE` metacommands.

## [1.26.4.2] - 2018-07-09

### Fixed

- Handling of double-quoted filenames by the `WRITE` and `RM_FILE` metacommands.

## [1.26.4.0] - 2018-06-27

### Added

- `$STARTING_SCRIPT_NAME` and `$CURRENT_SCRIPT_NAME` system variables.
- `IS_TRUE` conditional.

## [1.26.2.0] - 2018-06-25

### Added

- `$CURRENT_SCRIPT_PATH` system variable that returns the path only of the current script file.

## [1.26.1.0] - 2018-06-13

### Changed

- `HALT` metacommands now set the exit code to 3.

### Fixed

- Hang on uppercase counter references.

## [1.26.0.0] - 2018-06-13

### Added

- `ON CANCEL_HALT WRITE` and `ON CANCEL_HALT EMAIL` metacommands.

## [1.25.0.0] - 2018-06-10

### Added

- `PROMPT COMPARE` metacommand.

## [1.24.12.0] - 2018-06-09

### Added

- `MAKE_EXPORT_DIRS` metacommand.

### Changed

- All metacommands corresponding to configuration options are grouped under a common `CONFIG` prefix.
- Configuration file size and date are now written to `execsql.log` when a configuration file is read.

## [1.24.9.0] - 2018-06-03

### Changed

- `IMPORT` metacommand now writes the file name, file size, and file date to `execsql.log`.

## [1.24.8.0] - 2018-06-03

### Changed

- Added filename to error message when the `IMPORT` metacommand cannot find a file.
- `SUBDATA` now only removes the substitution variable (rather than raising an exception) when there are no rows in the specified table or view.

### Fixed

- `is_null()`, `equals()`, and `identical()` now correctly strip quotes.

## [1.24.7.0] - 2018-04-03

### Added

- `$SYSTEM_CMD_EXIT_STATUS` system variable.

## [1.24.6.0] - 2018-04-01

### Added

- `B64` format to the `EXPORT` and `EXPORT_QUERY` metacommands.

## [1.24.5.0] - 2018-03-15

### Added

- `textarea` entry type to the `PROMPT ENTRY_FORM` metacommand.

## [1.24.4.0] - 2017-12-31

### Added

- `-o` command-line option to display online help.

### Changed

- `CREATE SCRIPT` is now an alias for `BEGIN SCRIPT`.
- `DEBUG WRITE SCRIPT` is now an alias for `WRITE SCRIPT`.

## [1.24.2.0] - 2017-12-30

### Added

- `TYPE` and `LCASE`/`UCASE` keywords to the `PROMPT ENTER_SUB` metacommand.

### Changed

- Modified characters allowed in user names for Postgres and ODBC connections.

## [1.24.0.0] - 2017-11-04

### Added

- `include_required` and `include_optional` configuration settings.

## [1.23.3.0] - 2017-11-03

### Added

- `CONSOLE_WAIT_WHEN_ERROR_HALT` setting, associated metacommand, and system variable.

## [1.23.2.0] - 2017-11-02

### Added

- `$ERROR_MESSAGE` system variable.

## [1.23.1.0] - 2017-10-20

### Added

- `ASK` metacommand.

## [1.23.0.0] - 2017-10-09

### Added

- `ON ERROR_HALT EMAIL` metacommand.

## [1.22.0.0] - 2017-10-07

### Added

- `ON ERROR_HALT WRITE` metacommand.

## [1.21.13.0] - 2017-09-29

### Added

- `SUB_APPEND` and `WRITE SCRIPT` metacommands.

### Changed

- All metacommand messages now allow multiline text.

## [1.21.12.0] - 2017-09-24

### Added

- `PG_VACUUM` metacommand.

## [1.21.11.0] - 2017-09-23

### Changed

- Error message content and format.

## [1.21.10.0] - 2017-09-12

### Added

- `error_response` configuration setting for encoding mismatches.

## [1.21.9.0] - 2017-09-06

### Changed

- Now handles trailing comments on SQL script lines.

## [1.21.8.0] - 2017-08-11

### Changed

- `CONNECT` metacommand for MySQL now allows a password to be specified.

## [1.21.7.0] - 2017-08-05

### Added

- `DEBUG` metacommands.

### Changed

- `IMPORT` metacommand now allows CSV files with more columns than the target table.

## [1.21.1.0] - 2017-07-04

### Changed

- Column headers are now passed to template processors as a separate object.

## [1.21.0.0] - 2017-07-01

### Added

- `EXPORT` metacommand extended to allow several different template processors to be used.

## [1.20.0.0] - 2017-06-30

### Added

- `EMAIL`, `SUB_ENCRYPT`, and `SUB_DECRYPT` metacommands.
- Configuration properties to support emailing.
- `METACOMMAND_ERROR_HALT` metacommand.
- `$METACOMMAND_ERROR_HALT_STATE` system variable.
- `METACOMMAND_ERROR()` conditional.

## [1.18.0.0] - 2017-06-24

### Changed

- Improved speed of import of CSV files to Postgres and MySQL/MariaDB.
- `EXPORT...APPEND...AS HTML` metacommand now appends tables inside the first `</body>` tag.

## [1.17.0.0] - 2017-05-28

### Changed

- `PROMPT ENTRY_FORM` specifications extended to allow checkboxes.

## [1.16.9.0] - 2017-05-27

### Added

- `DESCRIPTION` keyword to the `EXPORT` metacommands.

## [1.16.8.0] - 2017-05-20

### Added

- `VALUES` export format.

## [1.16.7.0] - 2017-05-20

### Added

- `BOOLEAN_INT` and `BOOLEAN_WORDS` metacommands.
- `console_wait_when_done` configuration parameter.

### Changed

- `PAUSE` metacommand now accepts fractional timeout arguments.
- Server name is now added to the password prompt.

## [1.16.3.0] - 2017-04-23

### Added

- Configuration option allowing specification of additional configuration files to read.
- `MAX_INT` configuration parameter and metacommand.

## [1.16.0.0] - 2017-03-25

### Added

- `BEGIN SCRIPT`, `END SCRIPT`, and `EXECUTE SCRIPT` metacommands.

## [1.15.0.0] - 2017-03-09

### Added

- `TEE` keyword to the `WRITE`, `EXPORT`, and `EXPORT QUERY` metacommands.

## [1.13.0.0] - 2017-03-05

### Added

- `LOG_WRITE_MESSAGES` metacommand and configuration parameter.

## [1.12.0.0] - 2017-03-04

### Added

- `boolean_words` configuration option.
- Reading of CSV files with newlines within delimited text data.
- `SKIP` keyword to the `IMPORT` metacommand for CSV, ODS, and Excel data.
- `COLUMN_EXISTS` conditional.

## [1.8.15.0] - 2017-01-14

### Added

- `$LAST_ROWCOUNT` system variable.

## [1.8.14.0] - 2016-11-13

### Added

- Evaluation of numeric types in input.
- `empty_strings` configuration parameter and metacommand.

### Fixed

- Corrections to `IMPORT` metacommand for Firebird.

## [1.8.13.0] - 2016-11-07

### Added

- `-b` command-line option and configuration parameter.

## [1.8.12.0] - 2016-10-22

### Added

- `RM_SUB` metacommand.

## [1.8.11.0] - 2016-10-19

### Added

- `SET COUNTER` metacommand.

## [1.8.10.2] - 2016-10-17

### Added

- `$RUN_ID` system variable.

### Changed

- Now recognizes as text any imported data that contains only numeric values where the first digit of any value is a zero.

## [1.8.8.0] - 2016-09-28

### Added

- `$CURRENT_ALIAS`, `$RANDOM`, and `$UUID` system variables.

## [1.8.4.0] - 2016-08-13

### Added

- Import from MS-Excel.

### Changed

- Logging of database close when autocommit is off.

### Fixed

- Parsing of numeric time zones.

## [1.7.3.0] - 2016-08-05

### Added

- `$OS` system variable.

## [1.7.2.0] - 2016-06-11

### Added

- `DIRECTORY_EXISTS` conditional.
- Option to automatically make directories used by the `EXPORT` metacommand.

## [1.7.0.0] - 2016-05-20

### Added

- `NEWER_DATE` and `NEWER_FILE` conditionals.

## [1.6.0.0] - 2016-05-15

### Added

- `CONSOLE SAVE` metacommand.
- DSN connections.
- `COPY QUERY` and `EXPORT QUERY` metacommands.

## [1.4.4.0] - 2016-05-02

### Added

- `CONSOLE HIDE`/`SHOW` metacommands.

### Changed

- `CONSOLE WAIT` metacommand now accepts `<Enter>` to continue without closing.

## [1.4.2.0] - 2016-05-02

### Added

- "Save as..." menu to the GUI console.

### Changed

- `PAUSE` and `HALT` metacommands now use a GUI if the console is on.

## [1.4.0.0] - 2016-04-30

### Added

- GUI console with a status bar and progress bar to which `WRITE` output and exported text will be written.

## [1.3.3.0] - 2016-04-09

### Added

- Additional 'Save as...' options in `PROMPT DISPLAY` metacommand.
- Date/time values exported to ODS.

## [1.3.2.0] - 2016-02-28

### Added

- Backslash as a line continuation character for SQL statements.

## [1.3.1.0] - 2016-02-20

### Added

- `PROMPT ENTRY_FORM` and `LOG` metacommands.

## [1.2.15.0] - 2016-02-14

### Added

- `$DB_NAME`, `$DB_NEED_PWD`, `$DB_SERVER`, and `$DB_USER` system variables.
- `RAW` export format for binary data.
- `PASSWORD` keyword to the `PROMPT ENTER_SUB` metacommand.
- Password support in the `CONNECT` metacommand for Access.

## [1.2.10.0] - 2016-01-23

### Added

- `ENCODING` keyword to `IMPORT` metacommand.
- `TIMER` metacommand and `$TIMER` system variable.

## [1.2.8.2] - 2016-01-21

### Fixed

- Extra quoting in drop table method.
- `str` coercion in TXT export.

## [1.2.8.0] - 2016-01-11

### Changed

- Column headers are suppressed when EXPORTing to CSV and TSV with `APPEND`.
- Eliminated `%H%M` pattern to match time values in IMPORTed data.

## [1.2.7.1] - 2016-01-03

### Added

- `AUTOCOMMIT` metacommand.

### Changed

- Modified import of integers to Postgres.
- `BATCH` metacommand modified.
- Now explicitly rolls back any uncommitted changes on exit.

### Fixed

- Miscellaneous bug fixes.

## [1.2.4.6] - 2015-12-19

### Changed

- Modified quoting of column names for the `COPY` and `IMPORT` metacommands.

## [1.2.4.5] - 2015-12-17

### Fixed

- Asterisks in `PROMPT ENTER_SUB`.

## [1.2.4.4] - 2015-12-14

### Fixed

- Regexes for quoted filenames.

## [1.2.4.3] - 2015-12-13

### Fixed

- `-y` option display.
- Parsing of `WRITE CREATE_TABLE` comment option.
- Parsing of backslashes in substitution strings on Windows.

## [1.2.4.0] - 2015-11-21

### Added

- Connections to PostgreSQL, SQL Server, MySQL, MariaDB, SQLite, and Firebird.
- Numerous metacommands and conditional tests.
- Reading of configuration files.

## [0.4.4.0] - 2010-06-20

### Added

- `INCLUDE`, `WRITE`, `EXPORT`, `SUB`, `EXECUTE`, `HALT`, and `IF` (`HASROWS`, `SQL_ERROR`) metacommands.

## [0.3.1.0] - 2008-12-19

### Added

- Internal documentation.

## [0.3.0.0] - 2008-05-20

### Added

- `cp1252` encoding for data read from Access.

## [0.2.0.0] - 2008-04-26

### Added

- Creation and deletion of temporary views (queries).
- Export of final query to Excel.

## [0.1.2.0] - 2008-04-22

### Changed

- Added regular expressions to match `create temp view...` SQL command preface.

## [0.1.1.0] - 2008-04-20

### Changed

- Converted to use DAO instead of the dbconnect library.

## [0.1.0.0] - 2008-01-01

### Added

- Writing of the output of the last SQL command to a CSV file.

## [0.0.1.0] - 2007-11-11

### Added

- Initial release; executes SQL against Access.
