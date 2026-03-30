# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries prior to `2.0.0a1` are from the upstream
[execsql](https://execsql.readthedocs.io/) project by R.Dreas Nielsen.

______________________________________________________________________

## [Unreleased]

### Changed

- `Database` is now an abstract base class (ABC) with `open_db()` and `exec_cmd()` as `@abstractmethod`. Subclasses that omit either method will raise `TypeError` at instantiation time instead of `DatabaseNotImplementedError` at call time.
- Cursor lifecycle management in `Database` — `execute()`, `select_data()`, `schema_exists()`, `table_exists()`, `column_exists()`, `table_columns()`, `view_exists()`, and `import_entire_file()` now use a context manager that guarantees cursor cleanup on exit.
- Metacommand dispatch uses keyword-indexed lookup, reducing per-command dispatch from O(205) regex scans to O(K) where K is the number of patterns sharing the same leading keyword (typically 1–5).
- Variable substitution uses a single combined regex to find tokens in one pass, then does a dict lookup for the value — reducing `substitute()` from O(V) to O(1) per call, where V is the number of defined variables.
- Split `metacommands/__init__.py` (2,047 lines) — dispatch table registration moved to `metacommands/dispatch.py`; `__init__.py` reduced to constants and re-exports (256 lines).
- Split `script.py` (1,210 lines) into `script/` package with `variables.py` (substitution vars), `control.py` (batch/IF state), and `engine.py` (execution, parsing). All imports via `from execsql.script import X` continue to work.
- Converted `templates/READ_ME.rst` to `templates/README.md` (Markdown format).

### Added

- Python 3.14 support — added to CI matrix, tox environments, and PyPI classifiers.
- `formats` extra included in `dev` dependencies so ODS/Excel/Jinja2 tests run without manual installation.
- Roadmap items in `templates/README.md` for integrating execsql-compare and execsql-upsert documentation into the main docs site.

### Fixed

- Fix odfpy import — `import of` corrected to `import odf as of` in `exporters/ods.py` and test skip guards. ODS export was broken since the modular refactor.

______________________________________________________________________

## [2.3.0] - 2026-03-30

### Added

- `__all__` exports on 50 public modules for clean API surface and tooling support.
- Docstrings on all public classes and key methods in `db/`, `exporters/`, `config.py`, and `script.py` (50%+ coverage target met).
- Security documentation (`docs/security.md`) covering trust model, SHELL execution, credential handling, file system access, SMTP, and SQL variable substitution.

### Fixed

- Redact plaintext passwords (`Pwd=***`) from ODBC connection strings in log output for Access and SQL Server adapters.
- Fix 2 ruff UP038 violations — use `X | Y` union syntax in `isinstance` calls.

### Changed

- Remove lazy import anti-pattern from 6 modules — stdlib imports (`json`, `base64`, `itertools`, `string`, `smtplib`, `email.*`) moved to module level; optional deps (`xlrd`, `openpyxl`, `jinja2`) use instance attributes instead of `global`.
- Fix VS Code extension README paths and URLs.

______________________________________________________________________

## [2.2.1] - 2026-03-26

### Fixed

- Skip `TimerHandler` alarm tests on Windows where `signal.setitimer` is unavailable.
- Fix `UnicodeDecodeError` in CLI subprocess tests on Windows by specifying UTF-8 encoding.

______________________________________________________________________

## [2.2.0] - 2026-03-26

### Added

- `py.typed` marker for PEP 561 downstream type checking.
- 252 new tests (2,062 → 2,314) covering metacommands (`data`, `system`, `io_fileops`, `io_write`), utils (`auth`, `errors`, `fileio`, `timer`), and SQLite integration tests for JSON/HTML/LaTeX/TSV exports, DDL operations, WRITE-to-file, CONFIG metacommand, error handling, and inline commands; end-to-end CLI tests for `-c`, `--dsn sqlite://`, `-a` substitution, `--dry-run`, `--dump-keywords`, and `--version`. Coverage floor raised from 70% to 75%.
- `ods` optional-dependency extra in `pyproject.toml` (`pip install execsql2[ods]`).
- Keyring credential storage documentation in usage notes.
- `--progress` CLI flag and `CONFIG SHOW_PROGRESS` metacommand to display a rich progress bar during long-running IMPORT operations. Also configurable via `show_progress` in `execsql.conf`. (FEAT-5)
- Opt-in SQL query audit logging via `log_sql` config option and `CONFIG LOG_SQL` metacommand. When enabled, all executed SQL statements are written to the log file with a `sql` record type, database name, line number, and query text. (FEAT-6)
- `--dump-keywords` CLI option: outputs all metacommand keywords, conditional functions, config options, export formats, database types, and variable patterns as structured JSON. Enables tooling (e.g., editor grammar generators) to consume keyword data directly from the dispatch table.
- VS Code syntax highlighting extension colocated at `extras/vscode-execsql/`. The grammar (`execsql.tmLanguage.json`) is auto-generated from the dispatch table via `just generate-vscode-grammar`.
- Keyword registry: `MetaCommand` and `MetaCommandList` now support `category` parameter. All `mcl.add()` calls are tagged with `description=` and `category=`, making the dispatch table the single source of truth for keyword metadata.
- Export format constants (`QUERY_EXPORT_FORMATS`, `TABLE_EXPORT_FORMATS`, `SERVE_FORMATS`, etc.) centralized in `metacommands/__init__.py` and used in dispatch table regex construction.
- `tests/test_registry.py`: keyword consistency tests validating `--dump-keywords` output, dispatch table categories, conditional table coverage, export format constants, and grammar synchronization.

### Changed

- CLI reorganized from flat `_cli_*.py` files into `cli/` subpackage (`cli/__init__.py`, `cli/run.py`, `cli/dsn.py`, `cli/help.py`). All existing `from execsql.cli import ...` paths preserved.
- Exception hierarchy: `ErrInfo`, `DataTypeError`, `DbTypeError`, and `DatabaseNotImplementedError` now inherit from `ExecSqlError` base class instead of bare `Exception`.
- Exception chaining: added `from e` to 115 `raise` statements across 38 files that previously discarded the original exception context.
- README: replaced "not yet stable" warning with "maintained fork" note reflecting current project maturity.
- Split `cli.py` (1245 lines) into `_cli_help.py`, `_cli_dsn.py`, and `_cli_run.py` with `cli.py` as a re-export façade. All existing import paths preserved. (REFAC-3)
- Split `metacommands/io.py` (1304 lines) into `io_export.py`, `io_import.py`, `io_write.py`, and `io_fileops.py` with `io.py` as a re-export façade. All existing import paths preserved. (REFAC-4)

### Fixed

- `of` module typo throughout `exporters/ods.py`: all imports and references used `of` (e.g., `import of as of`, `of.table.Table`) instead of `of` (e.g., `import of as of`, `of.table.Table`). ODS export/import was completely broken when `odfpy` was installed. Same typo fixed in `tests/exporters/test_ods.py` and `tests/importers/test_ods_importer.py`.

- Unclosed `ScriptFile` in `script.py`: `read_sqlfile()` iterated through the file but never closed it, leaking a file handle on every script load.

- Unclosed CSV file handle in `exporters/delimited.py`: `evaluate_line_format()` opened a file for delimiter diagnosis but never closed it. `reader()` generator also leaked the file handle if not fully consumed or if an exception occurred mid-iteration. Both now use `try/finally`.

- Unclosed `sqlite3.Connection` in test assertions: `with sqlite3.connect(...)` only commits/rolls back but does not close the connection. Fixed in `tests/exporters/test_sqlite_exporter.py` and `tests/metacommands/test_metacommands.py`.

- File handle leaks in exporters: wrapped write operations in `try/finally` blocks to guarantee file handles are closed on error in `exporters/raw.py`, `exporters/xml.py`, `exporters/json.py`, `exporters/templates.py`, `exporters/values.py`, `exporters/pretty.py`, `exporters/html.py`, `exporters/latex.py`, `metacommands/debug.py`, `metacommands/control.py`, and `metacommands/prompt.py`. Previously, an exception during export could leak open file handles.

- XML export injection: `exporters/xml.py` now escapes `<`, `>`, `&` in cell values using `xml.sax.saxutils.escape()` and sanitizes `--` in XML comments. Previously, data containing XML special characters produced malformed XML output.

- HTML export XSS: `exporters/html.py` now escapes column headers and cell values using `html.escape()`. Previously, data containing `<script>` or other HTML markup was written directly to the output file.

- JSON export injection: `exporters/json.py` now uses `json.dumps()` to properly escape the `description` field in JSON-TS exports. Previously, descriptions containing quotes or backslashes produced malformed JSON. Also added missing `import json` to `write_query_to_json_ts` which previously relied on a global set by `write_query_to_json`.

- `JinjaTemplateReport.__repr__` incorrectly returned `StrTemplateReport(...)` instead of `JinjaTemplateReport(...)`.

- `exporters/templates.py`: removed bare `except: raise` clause in `JinjaTemplateReport.write_report()` and added proper exception chaining (`from e`) to Jinja2 template errors.

- `exporters/delimited.py`: `write_delimited_file()` now closes the output file handle via `try/finally`. Previously, the file was opened but never closed, leaking the handle on both success and error paths.

- SQL injection in remaining database metadata queries: `role_exists()` in `db/mysql.py`, `db/sqlserver.py`, and `db/firebird.py`, `schema_exists()` in `db/sqlserver.py`, `table_exists()` and `view_exists()` in `db/access.py` and `db/firebird.py` now use parameterized queries instead of f-string interpolation. `column_exists()` and `table_columns()` in `db/access.py` and `db/firebird.py` now use `quote_identifier()` for SQL identifiers that cannot be parameterized.

- SQL injection in `db/postgres.py`: `create_db()` now uses `quote_identifier()` for database name and encoding in `CREATE DATABASE` DDL. COPY command delimiter and quote character are now escaped/validated to prevent injection.

- CPU busy-loop in `utils/fileio.py`: `FileWriter.run()` now uses blocking `queue.get(timeout=0.1)` instead of `get_nowait()` in a tight loop, eliminating unnecessary CPU consumption when the file writer subprocess is idle.

- Substitution variable cycle detection in `script.py`: `substitute_vars()` now enforces a maximum of 100 iterations to prevent infinite loops when variables reference each other cyclically (e.g., `$A` expands to `!!$B!!` and `$B` expands to `!!$A!!`).

- Jinja2 template injection: `exporters/templates.py` now uses `jinja2.sandbox.SandboxedEnvironment` instead of the default `jinja2.Template` constructor. Previously, a malicious template file could access Python internals and execute arbitrary code.

- SQL injection in `import_entire_file()` across 6 database backends (`db/base.py`, `db/dsn.py`, `db/sqlite.py`, `db/sqlserver.py`, `db/postgres.py`, `db/access.py`): the `column_name` parameter is now quoted with `quote_identifier()` instead of being interpolated directly into the INSERT statement.

- XML export malformed output: `exporters/xml.py` now sanitizes column headers and table names used as XML element names, replacing invalid XML name characters with underscores. Previously, column names containing `>`, `<`, or other XML metacharacters produced malformed XML.

- `$SHEETS_TABLES_VALUES` SQL injection in `metacommands/io_import.py`: sheet names from ODS/XLS imports are now escaped (single quotes doubled) before embedding in SQL value expressions. Previously, a sheet name containing a single quote produced malformed or injectable SQL.

- HTTP header injection in SERVE metacommand (`metacommands/io_fileops.py`): the `Content-Disposition` filename is now sanitized (newlines/carriage returns stripped, quotes escaped) to prevent HTTP response splitting.

- Empty `dt_cast` type-cast mapping in `Database` base class (`db/base.py`): the monolith populated this dict with 8 type converters (int, float, str, bool, datetime, date, Decimal, bytearray) but the refactored version was initialized to `{}`. Now uses a lazy property that auto-populates on first access, ensuring all backends get the correct type casters even though none call `super().__init__()`.

- `WriteSpec.write()` file descriptor leak (`exporters/base.py`): the one-liner `EncodedFile(...).open("a").write(msg)` opened a file, wrote, and discarded the handle without closing. Now properly closes the handle in a try/finally block.

- Removed duplicate `x_halt_msg` function from `metacommands/prompt.py`. The canonical version in `metacommands/control.py` (used by the dispatch table) was the correct one; the prompt.py copy was dead code.

- `read_sqlfile()` double-open file leak (`script.py`): `ScriptFile.__init__` already opens the file, but `read_sqlfile()` called `.open("r")` again, creating a second leaked handle. Now uses the ScriptFile directly.

- Missing WRITE metacommand delimiter patterns in dispatch table (`metacommands/__init__.py`): added 5 missing delimiter variants (tilde, hash, backtick, bracket, single-quote) for WRITE and ON ERROR_HALT/ON CANCEL_HALT WRITE metacommands that were present in the monolith but missing from the refactored dispatch table.

- Missing bare (non-CONFIG) settings aliases in dispatch table (`metacommands/__init__.py`): added 10 bare settings forms (e.g., `FEEDBACK ON` without the `CONFIG` prefix) that the monolith supported but the refactored dispatch table omitted.

- `CONNECT TO DSN` metacommand unreachable (`metacommands/__init__.py`): the `x_connect_dsn` handler was imported but never registered with `mcl.add()`. DSN-based connections via metacommand were completely broken.

- `PARQUET` missing from EXPORT format regex lists (`metacommands/__init__.py`): the export handler code supported Parquet output but the dispatch table regex didn't include `PARQUET` as a valid format, making `EXPORT ... AS PARQUET` unreachable. Added to both EXPORT QUERY and EXPORT table format lists.

- Firebird error message typo (`db/firebird.py`): error message said "required to connect to MySQL" instead of "required to connect to Firebird".

- Oracle default port in function signature (`db/oracle.py`): default port parameter was `5432` (PostgreSQL's port) instead of `1521` (Oracle's port). The body already corrected to 1521 but the signature was misleading.

- Missing documentation for `show_progress` and `log_sql` config options in `docs/configuration.md`.

- Backward compatibility for `TXT-AND` export format (`metacommands/__init__.py`, `metacommands/io_export.py`): the monolith used `TXT-AND`/`TEXT-AND` but the refactored code renamed it to `TXT-AND`/`TEXT-AND`. Added `TXT-AND` as a backward-compatible alias so existing scripts continue to work.

- `docs/api/db.md` missing individual database adapter documentation — added all 9 adapters (postgres, sqlite, duckdb, sqlserver, mysql, oracle, firebird, access, dsn).

- `docs/api/exporters.md` missing `latex` and `zip` module references — added both.

______________________________________________________________________

## [2.1.2] - 2026-03-25

### Added

- DuckDB integration tests: 15 end-to-end tests (`tests/test_integration_duckdb.py`) covering basic SQL, substitution variables, CSV export/import, conditional execution, WRITE metacommand, round-trip, and DuckDB-specific features (views, schemas, native types).

### Changed

- Added PyPI version, Python versions, license, and Read the Docs badges to `README.md`.

### Fixed

- Config parser now accepts `k` (DuckDB) as a valid `db_type` in `execsql.conf`. Previously only the CLI flag `-t k` worked; config file validation rejected it.

- Read the Docs build: added `mkdocstrings-python` and editable project install to `.readthedocs.yaml` so `mkdocstrings` can resolve API references.

- Fixed escaped underscore in `docs/api/cli.md` (`\_run` → `_run`) that caused `mkdocstrings` to fail resolving `execsql.cli._run`.

- Excluded `docs/api/` from `mdformat` pre-commit hook to prevent it from re-escaping underscores in `mkdocstrings` `:::` directives.

______________________________________________________________________

## [2.1.1] - 2026-03-25

### Added

- Keyring credential retry on authentication failure: when a keyring-stored password is rejected by the database, the stale entry is automatically deleted, the user is re-prompted for the current password, and the connection is retried. The new password is then saved to the keyring. Applies to all database adapters (PostgreSQL, MySQL, Oracle, SQL Server, Firebird, DSN, MS Access). New public helpers `password_from_keyring()`, `clear_stored_password()`, and `skip_keyring` parameter on `get_password()` in `utils/auth.py`.

- Tests for `utils/mail.py`: 14 tests covering `MailSpec` construction and `Mailer` config validation/SMTP connection setup (plain, SSL, TLS, auth, sendmail with text/HTML/attachments/multiple recipients) using mocked SMTP.

- Parser edge case tests: 17 new tests for `NumericParser` and `CondParser` error paths (division by zero, unmatched/empty parens, empty/whitespace input, trailing/double operators, deeply nested expressions, non-numeric input).

- Security warning in `docs/substitution_vars.md` about environment variable exposure via `&`-prefixed substitution variables, with guidance on mitigating secret disclosure.

- Codecov integration: CI uploads coverage reports via `codecov/codecov-action@v5` (Ubuntu / Python 3.13 matrix leg) and a coverage badge in the README.

- Automatic changelog versioning on `bump-my-version` runs: `CHANGELOG.md` is now a bumpversion-managed file — the `[Unreleased]` section is replaced with a dated version heading and a fresh `[Unreleased]` header is preserved for the next cycle.

### Changed

- Centered the logo and badges in `README.md`.

### Fixed

- `ExecSqlTimeoutError` now inherits from `ExecSqlError` instead of `Exception`, so generic `except ExecSqlError` handlers will catch timeouts. Accepts an optional message (defaults to `"Operation timed out"`), preserving compatibility with bare `raise ExecSqlTimeoutError`.

- `exporters/ods.py`: Fixed broken ODS import/export — `import of as of` changed to `import of as of` to match the actual `odfpy` package module name. ODS support was silently non-functional.

- ODS test skip guards: replaced `pytest.importorskip("of")` (confusing error message, wrong module name) with a proper `of.opendocument` availability check and clear skip reason.

- Exception chaining: added `from e` to `raise ErrInfo(...)` in `exporters/delimited.py` and `utils/fileio.py` to preserve original tracebacks. Changed `raise e` to bare `raise` in `exporters/delimited.py:_colhdrs()`.

- Security comment in `cli.py` documenting that all environment variables are exposed as `&`-prefixed substitution variables.

- Python 3.10 compatibility: replaced `datetime.UTC` (3.11+) with `datetime.timezone.utc` in `cli.py` and `script.py`.

- Windows test compatibility: replaced hardcoded Unix paths in `TestApplyOutputDir` tests with `tmp_path`-based platform-native paths, and added Windows-aware path for `TestMakeExportDirsErrors`.

- SQLite connection leaks: `state.reset()` and the test `_reset_execsql_state` fixture now call `dbs.closeall()` before discarding the `DatabasePool`, and `export_sqlite()` uses `try/finally` to guarantee the connection is closed on error. Eliminates `ResourceWarning: unclosed database` warnings.

______________________________________________________________________

## [2.1.0]

### Changed

- Consolidated optional dependency extras: replaced individual `ods`, `excel`, `jinja`, `feather`, `parquet`, and `hdf5` extras with a single `formats` bundle. Renamed `keyring` extra to `auth`. Added `all-db` convenience group for all database drivers. The `all` extra now uses self-referential extras (`all-db`, `formats`, `auth`) instead of duplicating package lists.

- Moved all metacommand test modules from `tests/` into a dedicated `tests/metacommands/` subdirectory, matching the existing pattern used by `tests/db/`, `tests/exporters/`, `tests/importers/`, `tests/utils/`, and `tests/gui/`.

### Added

- `EXPORT … FORMAT parquet` support: new `exporters/parquet.py` module writes query results to Apache Parquet files via `polars`. Mirrors the existing Feather export pattern. Parquet import already existed; export completes the round-trip. Included in the `formats` optional dependency extra.

- OS keyring integration for database password storage (`utils/auth.py`): when the `keyring` package is installed, `get_password()` checks the OS credential store (macOS Keychain, Windows Credential Manager, Linux SecretService) before prompting. After a successful interactive prompt the password is stored in the keyring for future use. Controlled by the `use_keyring` config option (default `yes`). Included in the `auth` optional dependency extra.

- `max_log_size_mb` config setting (default `0` = disabled): when set to a positive integer, the log file is rotated to `.1` before a new run appends to it if the file size exceeds the configured threshold. Controlled via `config.py` and implemented in `utils/fileio.py`.

- Per-event ISO 8601 timestamps in log records: `status`, `connect`, `action`, and `user_msg` log entries now include a timestamp as field 4, making it possible to measure elapsed time between steps.

- Run duration in exit record: the `exit` log record now includes elapsed wall-clock time as the last field (e.g. `12.3s`).

- Run ID millisecond precision: the run identifier format changed from `%Y%m%d_%H%M_%S` to `%Y%m%d_%H%M_%S_NNN` to prevent collisions when two runs start within the same second.

- `import_progress_interval` config option (under `[input]`): controls how often row-count progress is written to the execution log during IMPORT operations. Set to a positive integer N to log a status line every N rows (e.g. `import_progress_interval = 10000`); defaults to `0` (silent). When enabled, a final completion line (e.g. `IMPORT into schema.table complete: 1000000 rows imported.`) is also written. Supported for all database adapters (SQLite, PostgreSQL, MySQL, and the generic base adapter).

- `--output-dir DIR` CLI option: sets a default base directory for EXPORT output files. Relative paths in EXPORT metacommands are automatically joined to this directory; absolute paths and `stdout` are unaffected. Eliminates the need to hard-code absolute paths in scripts.

- `--dsn` / `--connection-string` CLI option: accepts a standard database URL (e.g. `postgresql://user:pass@host:5432/db`) and populates the connection parameters automatically. Supported schemes: `postgresql`, `postgres`, `mysql`, `mariadb`, `mssql`, `sqlserver`, `oracle`, `firebird`, `sqlite`, `duckdb`. Overrides `-t`/`-u`/`-p` and positional server/db arguments. Passwords included in the URL are used directly without prompting.

- `--dry-run` CLI flag: parses the script (or inline `-c` command) and prints the full command list (SQL statements and metacommands with source locations) without connecting to a database or executing anything. Useful for validating scripts before running them. parses the script (or inline `-c` command) and prints the full command list (SQL statements and metacommands with source locations) without connecting to a database or executing anything. Useful for validating scripts before running them.

- API reference section in the docs (`docs/api/`) covering `cli`, `db`, `exporters`, `importers`, and `metacommands`; wired `mkdocstrings-python` into `zensical.toml` via `[project.plugins.mkdocstrings]`.

- Feather import/export support (via `polars`, included in the `formats` extra).

- HDF5 export support (via `tables`, included in the `formats` extra).

- `state.reset()` utility function to reset all module-level runtime state to initial values; used by the test suite to ensure a clean slate between tests.

- `state.initialize()` function that consolidates construction of runtime singletons (`conf`, `if_stack`, `counters`, `timer`, `dbs`, `tempfiles`, `export_metadata`, `metacommandlist`, `conditionallist`) into a single documented call site.

- `ExecSqlError` base class in `exceptions.py`; `ConfigError`, `ColumnError`, `DataTableError`, `OdsFileError`, `XlsFileError`, `XlsxFileError`, `ConsoleUIError`, `CondParserError`, and `NumericParserError` now inherit from it, eliminating boilerplate and ensuring `str(exc)` and `exc.args` produce useful output.

- `ErrInfo.__str__` now returns the most informative available message (`other_msg`, then `exception_msg`, then `type`) so standard logging and exception handlers produce useful output without accessing internal attributes.

- Expanded test coverage to meet 68% combined branch+statement floor: added `ErrInfo.__str__` tests, `CondParser` operator-matching tests (`match_not`, `match_andop`, `match_orop`), XML/SQLite/DuckDB exporter ErrInfo re-raise tests, DuckDB exporter "file-exists-but-table-absent" branch, `SourceString.match_regex` at EOI, and `__init__.__version__` fallback on `PackageNotFoundError`.

- Expanded test coverage for `Database` base-class methods (`select_rowdict`, `select_rowsource`, `select_data`, `cursor`, `rollback`, `commit`, `drop_table`, `table_columns`, `paramsubs`, `schema_qualified_table_name`, `autocommit_off/on`, `DatabasePool.closeall`) via `TestDatabaseDeeperMethods` and `TestDatabasePoolCloseAll`.

- Expanded test coverage for `CsvFile` in `test_delimited.py`.

- Tests for `only_strings`, `replace_newlines`, `import_row_buffer`, and `css_styles` config options in `test_config_data.py`.

- Tests for `replace_newlines` regex behavior and all-NULL column with lenspec in `test_models.py`.

- Tests for `FileWriter.try_open()` failure status in `tests/utils/test_fileio.py`.

- Tests for DuckDB native temporal type mappings in `test_types.py`.

- Tests for `SubVarSet` dict-based storage and pre-compiled regex patterns in `test_script.py`.

- Increased test coverage from 68% to 70% (2003 tests, up from 1840) by adding targeted tests for uncovered branches in `types.py` (83%→96%), `models.py` (88%→96%), `config.py` error branches, `utils/errors.py` (exception_info, write_warning, exit_now), `exporters/` (base, templates, xls, values, pretty), `gui/` (backend fallback, manager dispatch), and `utils/fileio.py` (Logger, BOM detection). Raised `--cov-fail-under` threshold from 68 to 70.

- Tests for `DT_Time_Oracle` subclass behavior (matches, from_data, lenspec, varlen) in `test_types.py`.

- Tests for `Database.quote_identifier()` in `tests/db/test_base.py`.

- Tests for PostgreSQL and SQLite connection timeout parameters in `tests/db/`.

- Tests for `write_warning()` null-safety when `exec_log` is uninitialized in `tests/utils/test_errors.py`.

- Tests for `DT_Date` instance-local format deque isolation in `test_types.py`.

- Integration tests (`test_integration.py`) covering end-to-end script execution with SQLite: basic SQL, substitution variables, CSV export/import, conditional execution (IF/ELSE/ENDIF), WRITE metacommand, and full round-trip export-then-import.

- Metacommand handler tests for previously untested modules: `test_metacommands_system.py` (53 tests), `test_metacommands_script_ext.py` (10 tests), `test_metacommands_connect.py` (14 tests), `test_metacommands_io.py` (31 tests).

### Fixed

- IMPORT completion log message is now always written when a log is active, regardless of the `import_progress_interval` setting. Previously the completion record (e.g. `IMPORT into schema.table complete: N rows imported.`) was suppressed when `import_progress_interval` was `0` (silent mode), leaving no trace of successful imports in the log. Affects `db/base.py`, `db/postgres.py`, `db/mysql.py`, and `db/sqlite.py`.

- `Logger.exit_type` now defaults to `"unknown"` instead of Python `None`, preventing the literal string `"None"` from appearing in the `exit` log record when the run completes without an explicit exit type.

- SQL injection in database metadata queries: `schema_exists()`, `table_exists()`, `column_exists()`, `table_columns()`, `view_exists()`, and `role_exists()` across `db/base.py`, `db/postgres.py`, `db/oracle.py`, `db/duckdb.py`, and `db/sqlite.py` now use parameterized queries and `quote_identifier()` instead of f-string interpolation.

- `utils/errors.py`: `write_warning()` and `exit_now()` now guard all `_state.exec_log`, `_state.conf`, and `_state.output` accesses with null checks to prevent `AttributeError` when called before state initialization.

- `config.py`: `only_strings` config option wrote to nonexistent `self.all_strings` attribute instead of `self.only_strings`.

- `config.py`: `fold_column_headers` config option wrote to `self.fold_column_headers` instead of `self.fold_col_hdrs`.

- `config.py`: `replace_newlines` config option overwrote `self.trim_strings` instead of setting `self.replace_newlines`.

- `config.py`: `import_row_buffer` config option overwrote `self.quote_all_text` instead of setting `self.import_row_buffer`.

- `config.py`: `css_styles` validation checked `self.css_file` instead of `self.css_styles`.

- `models.py`: Missing opening `[` in `replace_newlines` regex pattern (`r"\s\t]*..."` → `r"[\s\t]*..."`).

- `models.py`: `column_type()` referenced undefined loop variable `ac.maxlen` for all-NULL columns; changed to `sel_type.maxlen`.

- `fileio.py`: `FileWriter.try_open()` unconditionally set `STATUS_OPEN` after a failed `io.open()`; moved into `else` block.

- DuckDB temporal type mappings (`DT_TimestampTZ`, `DT_Timestamp`, `DT_Date`, `DT_Time`) changed from `TEXT` to native DuckDB types (`TIMESTAMPTZ`, `TIMESTAMP`, `DATE`, `TIME`).

- `db/base.py`: `raise e` in `execute()` changed to bare `raise` for cleaner traceback propagation.

- `db/firebird.py`: `table_exists()` fixed `raise e` → `raise ErrInfo(...)` to correctly raise the constructed error instead of re-raising the original driver exception, and reordered rollback before raise.

- `state.py`: Version-parse fallback changed from legacy `1.130.1` to `0.0.0` to avoid confusion with the v2.x series.

### Changed

- `state.py`: Replaced 20+ `Any`-typed module globals with concrete types under `TYPE_CHECKING` guards (e.g. `IfLevels | None`, `DatabasePool | None`, `FileWriter | None`). Only `gui_console` remains `Any` (varies by backend).

- All bare `except Exception: pass` blocks across 13 source files now have inline comments explaining why the exception is intentionally silenced (e.g. best-effort rollback, driver compatibility, GUI teardown).

- `README.md`: Corrected import/export format lists to match actual implementation — removed false JSON/XML import claims, added Feather/Parquet imports, expanded export list to cover all 15+ formats.

- Added `[tool.mypy]` configuration to `pyproject.toml` (Python 3.10 target, `warn_return_any`, `ignore_missing_imports`, excludes `_execsql/`).

- Replaced all `os.path` calls with `pathlib.Path` equivalents across 21 source files (`config.py`, `cli.py`, `script.py`, `utils/fileio.py`, `utils/errors.py`, `utils/mail.py`, `metacommands/io.py`, `metacommands/conditions.py`, `metacommands/connect.py`, `metacommands/prompt.py`, `exporters/base.py`, `exporters/duckdb.py`, `exporters/html.py`, `exporters/latex.py`, `exporters/ods.py`, `exporters/sqlite.py`, `exporters/xls.py`, `db/access.py`, `db/duckdb.py`, `db/factory.py`, `importers/csv.py`). `os.path.expandvars()` is retained where used as it has no `pathlib` equivalent.

- `MetaCommandList` in `script.py` refactored from a hand-rolled linked list (with a move-to-front performance heuristic) to a plain `list[MetaCommand]`. Command ordering is now stable and predictable; the `insert_node()` method and `next_node` attribute on `MetaCommand` have been removed.

- `config.py`: All `raise ConfigError(...)` patterns now chain the original exception via `from e` for better debugging context.

- `SubVarSet` in `script.py` refactored: internal storage changed from list-of-tuples to dict for O(1) variable lookups; regex patterns pre-compiled on `add_substitution()` instead of recompiled on every `substitute()` call.

- `set_system_vars()` in `script.py`: `_state.dbs.current()` cached once instead of called 7+ times per invocation.

- `DT_Time_Oracle` in `types.py` refactored to a thin subclass of `DT_Time`, overriding only `lenspec = True` and `varlen = True`; duplicated methods and attributes removed.

- `PostgresDatabase` and `SQLiteDatabase` now accept connection timeout parameters (default 30 s) passed through to the underlying driver (`connect_timeout` for psycopg2, `timeout` for sqlite3). `Database.quote_identifier()` added for safe SQL identifier quoting.

- `DT_Date` in `types.py`: date format deque (`date_fmts`) is now copied per-instance instead of mutated globally, eliminating thread-safety issues while retaining the most-recent-format-first performance optimization.

- `utils/crypto.py`: Added prominent security warnings to module and `Encrypt` class docstrings documenting that XOR "encryption" is obfuscation only; keys are hardcoded and passwords are recoverable. `docs/configuration.md` updated with matching admonition.

- `state.initialize()` is now called from `cli._run()` instead of individually assigning each singleton, making initialization order explicit and testable.

- Exception hierarchy refactored: `DataTypeError`, `DbTypeError`, and `DatabaseNotImplementedError` now call `super().__init__()` so `str(exc)` and `exc.args` are populated.

- All bare `except:` clauses replaced with `except Exception:` and bare `except ImportError:` / `except (ValueError, TypeError):` where appropriate, throughout exporters, `script.py`, `db/`, and utilities.

- `isinstance()` checks replace `type(x) == type(...)` comparisons throughout `db/access.py`, `db/base.py`, `exporters/pretty.py`, `exporters/raw.py`, `types.py`, `utils/regex.py`, and `utils/gui.py` for correctness with subclasses.

- `type(data) is T` used in place of `type(data) == T` for exact-type checks in `types.py`.

- `of` imports in `exporters/ods.py` corrected: `import of as of` followed by explicit `import of.*` submodule imports, replacing the broken `import of.*` pattern.

- `exception_info()` references in `exporters/duckdb.py`, `exporters/latex.py`, and `exporters/sqlite.py` corrected to the actual function name `exception_desc()`.

- `FileWriter.write()` status check corrected from comparing to the bare constant `STATUS_OPEN` to `self.status == self.STATUS_OPEN`.

- Unused variable assignments removed (`match_found` in `CounterVars.substitute` and `SubVarSet.substitute`; `enc_match` in `postgres.py`; shadow variable `l` renamed `line` in `ScriptFile.__next__`; unused `button_list` in `ConsoleBackend`; unused `conf` in `_apply_connect_result`; unused `close` in the dispatch-table builder; unused `errmsg` and `hdrs` in `x_subdata`).

- `itertools` and `base64` imports in `utils/crypto.py` split onto separate lines.

- `xml.py` local variable `uhdrs` renamed `str_hdrs` and loop corrected to iterate over the string-converted headers.

- Test `conftest.py` updated to use `_state.reset()` before and after each test instead of manually saving and restoring `_state.conf`.

- Deferred re-exports removed from `state.py` (was ~160 lines at the bottom of the module). All ~28 call-site modules now import names directly from their canonical source modules (`script`, `utils.fileio`, `utils.gui`, `parser`, etc.) rather than via `_state.X`. No behavior change; `state.py` reduced from ~488 to ~317 lines.

### Removed

- `AirspeedTemplateReport` and `FORMAT airspeed` template export variant. The Airspeed library has been unmaintained since ~2018 with no declared extra. Use `FORMAT jinja` instead.
- `airspeed` as a valid value for `template_processor` in `execsql.conf` and the `[output]` config section.
- All documentation references to Airspeed (docs/metacommands.md, docs/requirements.md, docs/configuration.md, README.md, templates/execsql.conf).

______________________________________________________________________

## [2.0.1] - 2026-03-23

### Fixed

- Fixed `PermissionError` on Windows when exporting to HTML in append mode: the file descriptor returned by `tempfile.mkstemp()` is now closed before the file is opened for writing.
- Fixed `PermissionError` on Windows when exporting to LaTeX: the file descriptor returned by `tempfile.mkstemp()` is now closed before `EncodedFile` opens the same path.

______________________________________________________________________

## [2.0.0] - 2026-03-23

### Changed

- Forked from execsql by R.Dreas Nielsen; repackaged as execsql2 with Python 3.13 support and modern tooling.
- Added support for Python 3.10, 3.11, 3.12, and 3.13; dropped Python 2 compatibility.
- Distributed as the `execsql2` package on PyPI; CLI entry point remains `execsql`.

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

- Width specification for listboxes in the `PROMPT ENTRY_FORM` metacommand.

## [1.126.0] - 2024-02-15

### Added

- Horizontal scrollbar to listboxes used with the `PROMPT ENTRY_FORM` metacommand.
- Radio button support for the `PROMPT ENTRY_FORM` metacommand.

## [1.125.3] - 2024-02-09

### Fixed

- Spurious warnings when running under Python 3.12.

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

- `PROMPT ENTRY_FORM` no longer closes the form when the 'Enter' key is pressed while a checkbox has focus.

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

- `ASK` metacommand under Python 3 on Windows.

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

- Correction to 2020-03-30 modification.

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

- `EXPORT...AS VALUES` now correctly writes `NULL` for null data.

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

- Error messages containing bad data are now protected from encoding errors.

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

- `int`/`long` conversion for Python 3 with Access.

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

- Stripping of extra spaces from input data when input is not strings.

## [1.26.5.0] - 2018-07-20

### Added

- `$PYTHON_EXECUTABLE` system variable.

### Changed

- Strings of only spaces are now treated as empty strings when `empty_strings=False`.

### Fixed

- Trailing space is now trimmed from the last column header of an IMPORTed CSV file.

## [1.26.4.3] - 2018-07-12

### Fixed

- Handling of double-quoted filenames by the `ON ERROR_HALT WRITE` and `ON CANCEL_HALT WRITE` metacommands.

## [1.26.4.2] - 2018-07-09

### Fixed

- Handling of double-quoted filenames by the `WRITE` and `RM_FILE` metacommands.

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

- Hang on uppercase counter references.

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

- `is_null()`, `equals()`, and `identical()` now correctly strip quotes.

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

- Corrections to `IMPORT` metacommand for Firebird.

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

- Parsing of numeric time zones.

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

- Extra quoting in drop table method.
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

- Miscellaneous bug fixes.

## [1.2.4.6] - 2015-12-19

### Changed

- Modified quoting of column names for the `COPY` and `IMPORT` metacommands.

## [1.2.4.5] - 2015-12-17

### Fixed

- Asterisks in `PROMPT ENTER_SUB`.

## [1.2.4.4] - 2015-12-14

### Fixed

- Regexes for quoted filenames.

## [1.2.4.3] - 2015-12-13

### Fixed

- `-y` option display.
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
