# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries prior to `2.0.0a1` are from the upstream
[execsql](https://execsql.readthedocs.io/) project by R.Dreas Nielsen.

______________________________________________________________________

## [Unreleased]

### Added

- `execsql-format`: The `--indent` flag now controls SQL indentation in addition to metacommand indentation. Previously only metacommand depth was affected; now sqlglot's `pad` and `indent` parameters follow the same value (default 4).
- `execsql-format`: New `--leading-comma` flag places commas at the start of lines instead of the end (e.g., `  , col2` instead of `col1,`).

### Fixed

- `execsql-format`: Fixed SQL corruption when formatting scripts with comments interleaved within multi-line SQL statements (e.g., `SELECT` with comment lines between columns, `CASE` with comments before `WHEN` clauses). Previously, the formatter split statements at comment boundaries and sent each fragment to sqlglot independently, which produced broken output (commas became semicolons, CASE expressions were split apart, content was silently dropped). The formatter now uses a marker-based round-trip: comments are replaced with inline markers before formatting so sqlglot sees the complete statement, then markers are restored to their original `--` comment style and position in the output. Comments that sqlglot's AST drops (e.g., inside CASE expressions) are detected and re-inserted at the best matching position using token-based heuristics.
- `execsql-format`: Fixed `/* */` block comments containing `-- !x!` metacommand markers being incorrectly processed as real metacommands. This caused the block comment to be broken apart, with `*/` becoming `* /` and commented-out code being mangled. The formatter now tracks block comment boundaries and skips metacommand processing inside them.
- `execsql-format`: Fixed blank lines within multi-line SQL statements (e.g., between column groups in a large `SELECT`) incorrectly splitting the statement into separate formatting blocks, causing each fragment to be formatted independently and producing invalid SQL.
- `execsql-format`: Added safety checks to the sqlglot formatting pass — if sqlglot produces more statements than the input contained or drops significant content, the formatter now falls back to the original text instead of emitting corrupted SQL.

______________________________________________________________________

## [2.16.12] - 2026-05-01

### Changed

- Lowered coverage threshold from 90% to 89% — SCRIPT introspection code is tested via subprocess integration tests which don't contribute to in-process coverage, and Windows CI skips TTY/POSIX tests that contribute ~1% on other platforms.

### Added

- Unit tests for `_parse_param_defs`, `_format_script_signature`, `_format_script_source`, and `SHOW SCRIPTS`/`SHOW SCRIPT` handlers.
- Parser coverage tests for default parameters and docstring extraction.

______________________________________________________________________

## [2.16.11] - 2026-05-01

### Fixed

- Multi-line `/* */` block comment docstrings in `BEGIN SCRIPT` blocks now capture all lines correctly. Previously, the doc collection guard ran on block comment continuation lines, classified them as "non-comment", and stopped doc collection before the block comment handler could process them.

### Added

- 12 parser tests covering default parameters and docstring extraction (single-line, multi-line, block comments, empty separators, metacommand termination, required-after-optional validation).

______________________________________________________________________

## [2.16.10] - 2026-05-01

### Fixed

- EXECUTE SCRIPT with a variable-substituted target name (e.g., `EXECUTE SCRIPT !!#script_name!!`) now works correctly. Previously, the parser's regex only accepted literal word characters as the script identifier, causing variable targets to fall through to the dispatch table and fail with "EXECUTE SCRIPT should be handled by the AST executor." The parser now recognizes `!!var!!` substitution patterns as valid script identifiers.

______________________________________________________________________

## [2.16.9] - 2026-05-01

### Added

- `SHOW SCRIPTS` metacommand lists all registered SCRIPT definitions with parameter signatures and source locations.
- `SHOW SCRIPT <name>` metacommand shows detail for a single SCRIPT (parameters, source file and line range, docstring).
- `.scripts` REPL command lists all registered scripts; `.scripts <name>` shows detail for one script.
- Default parameter values for SCRIPT definitions: `BEGIN SCRIPT load(schema, table, batch=1000)`. Parameters with defaults can be omitted at call site; the default value is used automatically. Required parameters must precede optional parameters (like Python).
- Automatic docstring extraction for SCRIPT blocks. Comments (`--` or `/* */`) immediately following `BEGIN SCRIPT` are captured as documentation. A blank line terminates the docstring. Docstrings are displayed by `SHOW SCRIPT`, `SHOW SCRIPTS`, and `.scripts` in the debug REPL.

______________________________________________________________________

## [2.16.8] - 2026-04-30

### Fixed

- SQL comments (`--` and `/* */`) inside multi-line SQL statements no longer split the statement. Previously, a comment like `-- col2,` between SELECT columns would cause the parser to flush the accumulated SQL at the comment line, sending an incomplete statement to the database. Comments inside SQL are now preserved as part of the statement text.

______________________________________________________________________

## [2.16.7] - 2026-04-30

### Fixed

- ANDIF/ORIF conditions now short-circuit: `IF (sub_defined(x)) ANDIF (not sub_empty(x))` no longer evaluates `sub_empty` when `sub_defined` returns false. Previously all modifiers were evaluated unconditionally, causing `sub_empty` to throw "Unrecognized substitution variable" on undefined variables.
- Error reports for IF, LOOP, and INCLUDE nodes now show the correct source line and metacommand text instead of the previous command's location.

______________________________________________________________________

## [2.16.6] - 2026-04-30

### Fixed

- `execsql-format` no longer corrupts PL/pgSQL function bodies inside `$$`-delimited blocks. sqlglot does not understand PL/pgSQL and was rewriting `IF NOT EXISTS ... END IF`, `IF ... THEN RETURN ... END IF`, and similar constructs as `COMMIT;`. The formatter now tracks `$$` boundaries and skips sqlglot formatting for any SQL block containing dollar-quoted content.
- Debug REPL `.vars` now shows `~` local and `#` param variables from the current stack frame, not just global variables. `.vars ~myvar` and `.set ~myvar value` also correctly read/write the stack frame's local scope instead of the global pool.

______________________________________________________________________

## [2.16.5] - 2026-04-30

### Fixed

- Debug REPL `.vars` now shows `~` local and `#` param variables from the current stack frame, not just global variables. `.vars ~myvar` and `.set ~myvar value` also correctly read/write the stack frame's local scope instead of the global pool.

______________________________________________________________________

## [2.16.4] - 2026-04-30

### Fixed

- Forward references in SCRIPT blocks now work: `EXECUTE SCRIPT foo` can appear before `BEGIN SCRIPT foo` in the same file or INCLUDE'd file. The AST executor now pre-scans for all SCRIPT block definitions before execution begins, matching the legacy engine's two-pass behavior.

______________________________________________________________________

## [2.16.3] - 2026-04-30

### Fixed

- `BEGIN SCRIPT name(params)` without a space before the opening parenthesis now parses correctly. The AST parser regex required whitespace between the script name and parameter list, causing `BEGIN SCRIPT` to be silently ignored and the matching `END SCRIPT` to fail with "Unmatched END SCRIPT metacommand."

______________________________________________________________________

## [2.16.2] - 2026-04-30

### Fixed

- INCLUDE with quoted paths (e.g., `-- !x! INCLUDE "!!path!!/file.sql"`) now strips the surrounding quotes before resolving the file path. The AST parser captured the full target text including quotes, but the legacy dispatch regex stripped them — quoted INCLUDE paths would fail with "File does not exist" even when the file was present on disk.

______________________________________________________________________

## [2.16.1] - 2026-04-30

### Fixed

- AST executor now correctly handles `~` (local) and `+` (outer-scope) substitution variables inside SCRIPT blocks. Previously, `-- !x! SUB ~var value` inside a SCRIPT body would write to a disconnected scope, causing the variable to be invisible to subsequent SQL statements and producing spurious "potential un-substituted variable" warnings. The fix pushes proper `CommandList` frames onto `commandliststack` at script and top-level boundaries, bridging the AST executor with the legacy metacommand handlers (`x_sub`, `x_rm_sub`, `xf_sub_defined`, `SUB_LOCAL`, prompt handlers, REPL `.vars`/`.stack`, etc.).
- EXECUTE SCRIPT argument expressions (e.g., `val=!!#parent_param!!`) are now expanded in the caller's scope before the child script frame is created, fixing nested script calls that pass `~` or `#` variables as arguments.

### Changed

- `RuntimeContext` is now stored in `threading.local()` instead of a module-level global, making `_state.foo` access thread-safe. Each thread gets its own isolated context via lazy initialization. The `active_context` context manager is now safe for concurrent use across threads. Enables future PARALLEL blocks and concurrent `from execsql import run` calls.
- `_run()` in `cli/run.py` decomposed into 8 standalone functions: `_seed_early_subvars()`, `_load_config()`, `_seed_script_subvars()`, `_load_script()`, `_apply_dsn()`, `_apply_cli_options()`, `_route_positionals()`, and `_setup_logging()`. Reduces `_run()` from ~380 lines to ~150 lines of orchestration with zero behavioral change.

______________________________________________________________________

## [2.16.0] - 2026-04-29

### Added

- `--parse-tree` CLI flag: parse a script into an Abstract Syntax Tree and print a visual tree structure showing block nesting (IF/LOOP/BATCH/SCRIPT), source line ranges, compound conditions (ANDIF/ORIF), and all metacommands. Requires no database connection or configuration.
- AST parser module (`execsql.script.parser`) with `parse_script()` and `parse_string()` entry points. Produces a structured `Script` tree with typed nodes for all block constructs (IfBlock, LoopBlock, BatchBlock, ScriptBlock, SqlBlock, IncludeDirective).
- AST node definitions (`execsql.script.ast`) with `format_tree()` for human-readable tree output.
- AST-based execution engine is now the default (and only) engine. Scripts are parsed into a tree of typed nodes, then walked for execution. INCLUDE'd files are parsed and executed natively with circular-include detection. Control flow (IF/LOOP/BATCH) is driven by tree structure.
- `active_context()` context manager in `execsql.state` for installing an isolated `RuntimeContext` as the active global context within a `with` block.
- Plugin system (`execsql.plugins`) for extending execsql with custom metacommands, export formats, and import formats via Python entry points. Entry point groups: `execsql.metacommands`, `execsql.exporters`, `execsql.importers`. Plugins are discovered automatically at startup.
- `--list-plugins` CLI flag to show all discovered plugins and exit.
- Python library API: `from execsql import run` for programmatic script execution from notebooks, pipelines, and applications. Returns a `ScriptResult` with success/failure, command count, timing, errors, and final variable state. Supports DSN connection strings, pre-existing connections, substitution variables, and error control. Full RuntimeContext isolation between calls.
- AST `Comment` node: the parser now preserves SQL comments in the tree. Consecutive single-line `--` comments are grouped into one node; `/* */` block comments are captured as single nodes. The `--parse-tree` output includes `<CMT>` tagged comment nodes.
- `--parse-tree` visual improvements: color-coded type tags (`<SQL>`, `<CMD>`, `<CMT>`, `<IF>`, `<LOOP>`, etc.), dimmed line numbers, and content truncation for cleaner output.
- Deprecation warning emitted when `enc_password` is used in config files, advising users to switch to keyring or environment variables.
- Sensitive environment variables (`*SECRET*`, `*TOKEN*`, `*PASSWORD*`, etc.) are now filtered from automatic substitution variable exposure.

### Changed

- **Execution engine replaced.** The legacy flat command-list engine has been replaced by the AST-based executor. Scripts are now parsed into a tree of typed nodes and executed by walking the tree. INCLUDE'd files are parsed and executed natively with circular-include detection. All metacommands, SQL, and control flow work identically. This change is transparent to users.
- **BREAK outside LOOP is now an error.** `BREAK` outside a loop block now raises an error (exit 1) instead of being silently ignored. This catches script bugs that were previously unreported.
- `--lint` now uses the AST parser for structural validation. Unmatched IF/LOOP/BATCH/SCRIPT blocks are caught at parse time with precise source line ranges. No database connection or runtime state initialization is required. All prior lint checks (variable analysis, INCLUDE file existence, EXECUTE SCRIPT resolution, SUB_INI reading) are preserved.
- Export format dispatch logic (`EXPORT` and `EXPORT QUERY` metacommands) refactored from duplicated ~180-line if/elif chains into shared `_dispatch_format()` function, eliminating code duplication and fixing missing zip-compatibility checks for `EXPORT QUERY`.
- `MailSpec.send()` refactored: extracted `_expand()` helper to replace 12 repetitive substitution lines.
- Default database type changed from Access (`-t a`) to SQLite (`-t l`). Upstream defaulted to Access, which requires Windows and pyodbc. Users targeting Access databases should pass `-t a` explicitly.

### Fixed

- **[Critical]** `WriteSpec.write()` and `MailSpec.send()` error-recovery paths crashed because `SubVarSet.substitute_all()` returns `(str, bool)` but callers treated the return as a plain string. All 14 call sites now unpack the tuple correctly.
- **[Critical]** Error-recovery fallback in `WriteSpec.write()` and `io_write` called `.encode()` producing bytes passed to `sys.stdout.write()` which expects `str`. Removed the `.encode()` calls.
- `WriteSpec.write()` no longer crashes with `IndexError` when `commandliststack` is empty during early initialization errors.
- SQL injection vector in `exec_cmd()` across all 8 database adapters — stored procedure/function/view names are now quoted with `quote_identifier()`.
- `DSN` and `SQL Server` adapters no longer encode SQL strings to bytes before execution.
- Duplicate tuple entries in export format checks (`"txt-and"` and `"text-and"` each appeared twice).
- Database adapters now clear `self.password` after successful connection, reducing credential exposure window.
- Removed unused `_DEFAULT_CTX = RuntimeContext()` allocation in `state.py`.
- Version bump commits no longer skip pre-commit hooks (`--no-verify` removed from bumpversion config).
- `SubVarSet.substitute_all()` now enforces a 100-iteration depth limit to prevent infinite loops from cyclic variable references. The per-statement guard in the executor already had this protection, but direct callers (e.g. config loading) did not.
- `ConfigData.export_output_dir` is now declared in `__init__` with a default of `None` instead of being dynamically added in the CLI entry point.
- `Encrypt.ky` key table is now an immutable `MappingProxyType` instead of a mutable class-level dict.
- `JsonDatatype` attributes are now declared as class variables in the class body instead of assigned externally after class definition.
- `minimal_conf` test fixture expanded with commonly needed attributes (`import_encoding`, `script_encoding`, `export_output_dir`, `write_prefix`, `write_suffix`, `fold_col_hdrs`, `trim_col_hdrs`, etc.) to reduce ad-hoc attribute additions in individual tests.

### Documentation

- Fixed false `$ENV:` prefix claim in substitution variables reference — feature does not exist.
- Documented environment variable filtering (SECRET, TOKEN, PASSWORD, etc.) in substitution variables reference.
- Added missing exporter API docs (markdown, yaml, xlsx) and importer API docs (json).
- Added 8 missing CLI flags to README Options table (-b, -e, -g, -i, -o, -s, -y, -z).
- Added missing installation extras ([upsert], [firebird], [oracle]) to README and installation guide.
- Fixed broken `PROMPT.md` link in logging guide.
- Added explicit `{ #exampleN }` anchors to all 34 examples for reliable cross-referencing.
- Updated architecture doc: corrected metacommand count (~225), export format count (20+), added debug/notebook/server/lsp packages to module map.
- Updated metacommand developer guide to reflect io.py split into io_export.py, io_import.py, io_write.py, io_fileops.py.
- Noted SQLite as the default database type in syntax reference.

### Removed

- `--ast` / `--no-ast` CLI flag — the AST executor is now the only execution engine; no opt-out.
- Legacy flat command-list execution engine (`_parse_script_lines`, `read_sqlfile`, `read_sqlstring`, `runscripts`, `ScriptFile`, `CommandListWhileLoop`, `CommandListUntilLoop`, `ScriptExecSpec.execute()`).
- Legacy `_execute_script_direct()` function and `_execute_include_legacy()` fallback path.

______________________________________________________________________

## [2.15.11] - 2026-04-27

### Fixed

- `PAUSE` console-mode fallback now checks `sys.platform` before attempting POSIX terminal imports, preventing hangs on Windows when stdin reports as a TTY.

______________________________________________________________________

## [2.15.10] - 2026-04-27

### Added

- `--config FILE` CLI flag to specify an explicit configuration file. The file is loaded after the implicit search paths (system, user, script-dir, working-dir) so its values take precedence, while CLI arguments still override everything.
- `$HOSTNAME` system substitution variable — the network name of the machine running execsql, useful for log messages and environment detection.

### Fixed

- Config file chaining no longer mutates a list during iteration; uses a deque for safe, predictable processing order.
- REPL `_use_color()` result is now cached instead of re-checking environment variables and TTY status on every colorized output.
- `DatabasePool.closeall()` no longer calls `self.__init__()` to reset state; fields are reset directly to avoid the re-initialization anti-pattern.
- `PAUSE` console mode no longer crashes on Windows CI due to unconditional `import termios`; POSIX-only imports are now guarded by the TTY fallback check.
- `HAS_ROWS()`, `ROW_COUNT_GT()`, `ROW_COUNT_GTE()`, `ROW_COUNT_EQ()`, and `ROW_COUNT_LT()` condition predicates now quote table names with standard SQL identifier quoting, preventing potential SQL injection when table names originate from substitution variables.
- Corrected `__init__.py` module docstring that incorrectly described the CLI entry point as `execsql2` (the command is `execsql`).
- Added note to configuration reference clarifying that `--output-dir` is a CLI-only option with no equivalent configuration file setting.

______________________________________________________________________

## [2.15.9] - 2026-04-27

### Added

- Textual TUI now displays a progress bar and remaining-time countdown for `PROMPT PAUSE` and `PAUSE` dialogs when the `CONTINUE AFTER` or `HALT AFTER` keywords specify a timed duration (matching existing Tkinter behavior).

### Fixed

- `PAUSE` metacommand in console mode (no `-v`) now responds to single keypresses (Enter to continue, Esc to quit) instead of requiring Enter after every key. Uses raw-mode terminal reading on POSIX and `msvcrt` polling on Windows.
- `PAUSE` with `CONTINUE AFTER`/`HALT AFTER` in console mode now displays a live SIGALRM-driven progress bar showing time remaining, matching the documented behavior and terminal screenshot.
- `PAUSE` progress bar output no longer bleeds into subsequent script output — the progress line is cleared before returning.
- Fixed double minutes-to-seconds conversion in the console `PAUSE` path that caused a 1-minute pause to sleep for 60 minutes.

______________________________________________________________________

## [2.15.8] - 2026-04-20

### Added

- `PG_UPSERT` / `PG_UPSERT QA` / `PG_UPSERT CHECK` now support the `STRICT_COLUMNS` keyword. When present, all missing columns in staging tables are treated as errors (not just PK and NOT NULL/no-default columns). Maps to pg-upsert's `strict_columns=True` parameter.
- New substitution variable `$PG_UPSERT_QA_WARNINGS` — a comma-separated list of table names that received WARNING-level QA findings. Scripts can use this to react to warnings without parsing `$PG_UPSERT_RESULT_JSON`.

### Changed

- `$PG_UPSERT_RESULT_JSON` now includes a `qa_warnings` array per table (previously only `qa_errors` was present). This reflects pg-upsert v1.22's severity-aware QA model.
- Minimum pg-upsert version bumped from `>=1.21.0` to `>=1.22.0`.

### Fixed

- `PG_UPSERT QA` and `PG_UPSERT CHECK` now capture all QA findings (errors + warnings) instead of only errors, so `$PG_UPSERT_RESULT_JSON` includes the full picture.
- Fixed compatibility with pg-upsert v1.22.0 where `TableResult.qa_errors` became a read-only property (now writes to `_qa_findings` field).

______________________________________________________________________

## [2.15.7] - 2026-04-20

### Fixed

- `CounterVars.substitute` now correctly searches the full string. `re.I` was mistakenly passed as the `pos` argument to `re.search`, causing the first two characters of every string to be skipped when looking for counter variable references.
- `DataTypeError`, `DbTypeError`, and `DatabaseNotImplementedError` now call `super().__init__()` instead of bypassing the MRO with `Exception.__init__(self, ...)`, fixing `repr()` crashes for these exception types.
- SQL injection in MySQL `LOAD DATA INFILE`: file path, field delimiter, and quote character are now escaped before being interpolated into the import SQL statement.
- SQLite and DuckDB `exec_cmd` no longer encodes the SQL string to bytes before passing it to `execute()`, which always raised `TypeError` in Python 3.
- Substitution variable token matching in `_substitute_nested` now uses `str.find()` on a lower-cased copy of the string instead of compiling a new regex per variable per call, eliminating unnecessary regex compilation on every substitution.
- Cursor leaks across all database adapters (PostgreSQL, MySQL, SQLite, DuckDB, Firebird, Access, SQL Server, Oracle) — call sites that manually opened cursors now use the `with self._cursor()` context manager so cursors are always closed, including on exceptions.
- `__delattr__` in `state.py` now instantiates a fresh `RuntimeContext()` when resetting an attribute to its default, rather than reading from a cached `_DEFAULT_CTX` instance. This prevents mutable defaults (lists, dicts) from being shared across resets.
- `cmds_run` counter no longer overcounts: the `StopIteration` branch in `runscripts()` now calls `continue` after popping the command list stack, preventing the increment that follows from executing.
- Config file chaining is now capped at 20 files to prevent an infinite loop when `config_file` entries form a cycle.
- Temp file creation in `TempFileMgr` now uses `tempfile.mkstemp()` instead of `tempfile.NamedTemporaryFile().name`, eliminating the TOCTOU race where another process could claim the name between creation and use.
- JSON export now serializes column names with `json.dumps()` instead of bare f-string interpolation, preventing malformed JSON when column names contain quotes, backslashes, or other special characters.
- PostgreSQL `VACUUM` autocommit session state is now restored in a `finally` block, ensuring the connection returns to non-autocommit mode even if the vacuum statement raises an exception.
- HTML export now HTML-escapes the description, author, and CSS href meta tag values, preventing malformed HTML when these values contain `<`, `>`, `"`, or `&` characters.
- `shlex.split` on Windows is now called with `posix=False` instead of pre-escaping backslashes, which produced incorrect splits for paths with consecutive backslashes.
- Duplicate `JsonDatatype.integer = "integer"` assignment in `models.py` removed; `JsonDatatype.number` is the correct attribute and was already present.
- MySQL adapter constructor no longer coerces `None` arguments to the string `"None"` for `server_name`, `db_name`, and `user_name`; `None` values are now preserved as `None`.
- `importfile()` parameter renamed from `columname` to `column_name`, matching the internal variable name used throughout the function body.

______________________________________________________________________

## [2.15.6] - 2026-04-16

### Fixed

- Nested substitution variable names (e.g., `!!N_!!CHECK_GROUP!!_CHECKS!!`) now resolve correctly, matching original execsql behavior. The single-pass token regex introduced in 2.15.0 could not find inner `!!var!!` tokens embedded within an outer variable name; a per-variable substring fallback now handles this edge case.

______________________________________________________________________

## [2.15.5] - 2026-04-15

### Fixed

- `DT_Timestamp` type inference no longer claims time-only values (e.g. `13:15:45`). `dateutil.parser.parse()` silently fills in today's date for bare time strings, causing `DT_Timestamp` to match before `DT_Time` and generating PostgreSQL `InvalidDatetimeFormat` errors on CSV import. Time-only strings are now rejected by `parse_datetime()`.

______________________________________________________________________

## [2.15.4] - 2026-04-15

### Fixed

- Fixed typo in `test_latin1_encoding` test data (`calf\xe9` → `calf\xe9`) that caused assertion failure on Windows CI.

______________________________________________________________________

## [2.15.3] - 2026-04-15

### Added

- New optional dependency extras `auth-plaintext` and `auth-encrypted` for headless Linux keyring backends. `pip install execsql2[auth-plaintext]` installs `keyring` + `keyrings.alt`; `pip install execsql2[auth-encrypted]` adds `pycryptodome` for the encrypted file backend.

______________________________________________________________________

## [2.15.2] - 2026-04-14

### Changed

- `DT_Integer`, `DT_Float`, and `DT_Decimal` data type matchers now use pre-compiled regex class attributes instead of recompiling on every call — reduces overhead during large imports.
- `DT_Boolean` match tuples are now cached and only rebuilt when the `boolean_words`/`boolean_int` config changes, instead of on every `_is_match()`/`_from_data()` call.
- SQLite and DuckDB adapter methods (`table_exists`, `table_columns`, `view_exists`, `schema_exists`) now use the `_cursor()` context manager to prevent cursor leaks on exceptions.

### Fixed

- `DT_Text.data_type_name` corrected from `"character"` to `"text"` — error messages now correctly identify the text data type instead of showing "character".
- `DT_Varchar._from_data()` now converts non-string data to string and enforces the 255-character length limit. Previously, non-string values passed through without conversion or length check.
- `WriteHooks.write_err()` no longer crashes on empty string input.
- `CondAstNode.eval()` now raises `CondParserError` for unknown node types instead of silently returning `None`.
- `NumericAstNode.eval()` now raises `NumericParserError` on division by zero instead of an unhandled `ZeroDivisionError`.

______________________________________________________________________

## [2.15.1] - 2026-04-14

### Added

- Cell-level diff marking in `PROMPT COMPARE` dialog — when "Highlight Diffs" is toggled, differing cells within changed rows are prefixed with a bullet marker so users can see exactly which columns differ. Works across all three backends (Tkinter, Textual, and console).
- `macos_config_file` option in `execsql.conf` `[config]` section — specifies an additional configuration file to read on macOS (`sys.platform == "darwin"`). Behaves identically to `linux_config_file` with tilde expansion support.
- EXPORT operations now log structured `action` records to `execsql.log` with the query name, output file, and source line number.

### Removed

- `Logger.log_action_prompt_quit()` — dead code inherited from upstream, never called. Prompt halt events are already captured by `log_exit_halt()`.
- `constants.py` — 370 lines of map tile servers, XBM bitmaps, and X11 color names never imported by any module. Vestigial from the upstream monolith.
- `Tz` class in `types.py` — custom `tzinfo` subclass orphaned by the `python-dateutil` migration.
- Duplicate `file_size_date()`, `chainfuncs()`, and `as_none()` definitions in `conditions.py` — canonical versions in `utils/errors.py`. `chainfuncs()` and `as_none()` were also removed from `utils/errors.py` as they had zero callers.

### Changed

- `linux_config_file` config option now only applies on Linux (`sys.platform == "linux"`), not all POSIX systems. macOS users should use the new `macos_config_file` option instead.
- Date/time parsing now uses `python-dateutil` instead of 231 hardcoded `strptime` format strings. Handles ISO 8601 with `T` separator, microseconds, `Z` suffix, and named timezones that the old format list could not parse.
- Refactored `ConfigData` to use private helper methods (`_get_str`, `_get_enum`, `_get_bool`, `_get_int`, `_get_float`) — reduces ~370 lines of repetitive option parsing to ~80 lines with identical behavior.

### Fixed

- `NumericParser` now uses left-associative parsing for arithmetic operators. Previously, right-recursive descent caused `10 - 3 - 2` to evaluate as `10 - (3 - 2) = 9` instead of the correct `(10 - 3) - 2 = 5`. Same fix for division.
- Operator precedence bug in `DataTable` and `Database.populate_table()` empty-column check — a redundant `and conf.del_empty_cols` inside an already-guarded block caused incorrect short-circuit evaluation due to Python operator precedence.
- SQLite `populate_table()` now applies `trim_strings`, `replace_newlines`, and `empty_strings` processing before extracting column data. Previously, processing was applied after the insert data was copied, so trimming and null-conversion never took effect.
- `$CURRENT_DATABASE` and `$CURRENT_DBMS` system variables now refresh on `USE` metacommand. Previously they were only set at startup and on `CONNECT`, becoming stale after switching the active database with `USE`.
- Documentation: `$CONSOLE_WAIT_WHEN_ERROR_HALT_STATE` variable name corrected in substitution variables reference (was incorrectly documented as `$CONSOLE_WAIT_WHEN_ERROR_STATE`).
- `PROMPT COMPARE` diff logic now uses native Python equality instead of string comparison — `int(1)` vs `float(1.0)`, `Decimal("10.00")` vs `Decimal("10.0")`, and `True` vs `1` are correctly treated as equal instead of producing false diffs.
- `PROMPT COMPARE` diff logic now treats `None` (SQL NULL) as distinct from empty string `""`. Previously both were normalized to `""` and compared as equal.
- `PROMPT COMPARE` summary stats now match by column name instead of position — tables with the same columns in different order no longer produce false diffs.
- `PROMPT COMPARE` summary stats no longer include key columns in the diff comparison — only non-key shared columns are compared, consistent with the cell-level diff engine.
- `PROMPT COMPARE` diff engine now keeps the first row when duplicate PK values exist, instead of silently using the last.
- `compare_stats()` now delegates to `compute_row_diffs()` so the summary line and cell-level highlighting always agree.
- `PG_UPSERT` metacommand no longer writes pg-upsert output to `execsql.log`. Logging now only goes to the file specified by the `LOGFILE` keyword.
- `win_config_file` config option now works on Windows. Previously checked `os.name == "windows"` which is never true (Python returns `"nt"`). Inherited from upstream.

______________________________________________________________________

## [2.15.0] - 2026-04-09

### Added

- `PG_UPSERT` metacommand: new `EXPORT_FAILURES <dir>`, `EXPORT_FORMAT csv|json|xlsx`, and `EXPORT_MAX_ROWS <n>` keywords that write a "fix sheet" of failing QA rows — one row per unique violating staging row with a consolidated `_issues` column — to CSV, JSON, or XLSX. Works in all three modes (full pipeline, QA-only, schema check) and runs even when QA fails. New `$PG_UPSERT_EXPORT_PATH` substitution variable holds the directory written. A user-visible message reporting the export directory and format is emitted to both the console and the execsql log after every export.

### Changed

- `[upsert]` extra now requires `pg-upsert>=1.21.0` (up from `>=1.20.0`) for the fix-sheet export feature.

### Fixed

- `PROMPT MESSAGE ... CREDENTIALS <user_var> <pw_var>` no longer crashes in console-fallback mode with `TypeError: get_password() missing 2 required positional arguments: 'database_name' and 'user_name'`. The fallback now uses `getpass.getpass()` to read the password, matching the intent (keyring-aware `auth.get_password()` is for CONNECT, not for bare credential prompts).

______________________________________________________________________

## [2.14.1] - 2026-04-07

### Fixed

- Fix Windows CI: use `zf.namelist()[0]` instead of path for zip entry lookup.

______________________________________________________________________

## [2.14.0] - 2026-04-07

### Added

- Row count footer displayed below every table in GUI dialogs (Textual TUI, Tkinter desktop, and console fallback). Shows format like "3 rows" or "1 row" with comma-separated thousands for large counts.
- Help URL button in all GUI dialogs that support the `HELP` keyword. Clicking the button opens the URL in the system browser. Console fallback prints the URL.
- Diff summary line in compare dialogs showing matching, differing, and table-exclusive row counts (e.g., "3 matching | 1 differing | 2 only in Table 1").
- `PROMPT ENTRY_FORM` now enforces `validation_regex` (on submit) and `validation_key_regex` (per-keystroke) validation across all GUI backends. Required fields are also validated on submit. Tkinter shows a messagebox on validation failure; Textual shows a notification; Console re-prompts.
- "Highlight Diffs" toggle button in compare dialogs (Textual and Tkinter) that color-codes rows: green for matching, yellow for changed, red for rows only in one table.

### Fixed

- `CONFIG GUI_LEVEL` now accepts value `3` (open GUI console on start), matching the `gui_level` configuration file setting.
- `PROMPT COMPARE` now respects the `AND` vs `BESIDE` keyword: `AND` stacks tables vertically, `BESIDE` displays them side-by-side. Previously both orientations displayed side-by-side.
- `PROMPT ENTRY_FORM` now renders all documented `entry_type` values: `listbox` (multi-select list), `radiobuttons` (radio button group), `textarea` (multi-line text area), `inputfile` and `outputfile` (text field with file browser button). Previously only `checkbox` and `dropdown`/`select` were implemented; all others fell through to a plain text input.
- `PROMPT ENTER_SUB` HELP URL regex typo: quoted HELP URLs containing `+` characters now match correctly (was using `[^+]` instead of `[^"]`).
- PostgreSQL and DSN `CONNECT` handlers now unquote the PASSWORD parameter consistently with all other database handlers.
- SQL Server `CONNECT` handler now uses consistent keyword argument `user_name=` in all code paths.

### Changed

- Documentation: added `CONFIG LOG_SQL` and `CONFIG SHOW_PROGRESS` sections to metacommands reference (were implemented but undocumented).
- Documentation: DuckDB `CONNECT` syntax now shows the `NEW` keyword (was supported but undocumented).
- Documentation: `EXPORT QUERY` format list now explicitly mentions PARQUET, FEATHER, YAML, MARKDOWN support.
- Documentation: added alias notes for `EXEC SCRIPT` / `RUN SCRIPT` and `APPEND SCRIPT`.
- Documentation: `RM_SUB` now documents `~` prefix for deleting local variables.
- Documentation: fixed missing bracket in `WRITE CREATE_TABLE FROM EXCEL` syntax.

### Removed

- `FREE` keyword from `PROMPT DISPLAY` metacommand. The non-blocking display behavior was only implemented in the console backend; Textual and Tkinter backends ignored it.
- Tkinter dialog buttons are now right-aligned (matching the Textual TUI layout) instead of centered.
- Tkinter dialog message text is now left-aligned instead of center-justified.

______________________________________________________________________

## [2.13.2] - 2026-04-06

### Changed

- `--lint` static analysis improvements:
    - Track `SUB_EMPTY`, `SUB_ADD`, `SUB_APPEND`, and `SUBDATA` as variable definitions, eliminating false undefined-variable warnings.
    - Descend into named script blocks via `EXECUTE SCRIPT` / `EXEC SCRIPT` / `RUN SCRIPT` so variables defined inside are visible to the caller.
    - Two-pass variable collection: definition order no longer matters. Variables can be referenced before their SUB definition without false warnings.
    - Read `SUB_INI` INI files at lint time and register section keys as defined variables.
    - Auto-discover built-in system variables by scanning installed source instead of a hand-maintained list.
    - Exclude `$COUNTER_N` variables from undefined-variable warnings.
    - Warn when `EXECUTE SCRIPT` targets a non-existent script block (respects `IF EXISTS`).
    - Eliminate duplicate warnings for script blocks reached via multiple execution paths.
    - Sort errors before warnings, both by line number. Pad location columns for alignment.

______________________________________________________________________

## [2.13.1] - 2026-04-04

### Changed

- Bump pg-upsert minimum to >=1.20.0.

______________________________________________________________________

## [2.13.0] - 2026-04-04

### Added

- New `IMPORT … FROM JSON` metacommand — imports a JSON array of objects or newline-delimited JSON (NDJSON) file into a database table. Nested objects are flattened with dot-separated column names; nested arrays are stored as JSON strings. Missing keys across records become NULL.
- `SHELL … CONTINUE` now sets `$SYSTEM_CMD_PID` substitution variable with the PID of the background process.

### Fixed

- `Mailer`, `WriteableZipfile`, `ZipWriter` now support context manager protocol (`with` statement) for reliable resource cleanup. `__del__` methods are guarded against exceptions during interpreter shutdown.
- `FileWriter` and `FileControl` `__del__` methods no longer raise during interpreter shutdown.
- Raw/base64 binary export now uses `with open(…)` context managers instead of bare `open()`.
- HTML export append mode now cleans up temporary files if the final rename fails.

______________________________________________________________________

## [2.12.7] - 2026-04-03

### Fixed

- Bump pg-upsert minimum to >=1.18.2 — fixes interactive FK check dialog only showing 1 violation row instead of all rows.

______________________________________________________________________

## [2.12.6] - 2026-04-03

### Added

- `PG_UPSERT` now supports per-table progress via pg-upsert's callback API. New substitution variables `$PG_UPSERT_CURRENT_TABLE`, `$PG_UPSERT_TABLE_QA_PASSED`, `$PG_UPSERT_TABLE_ROWS_UPDATED`, and `$PG_UPSERT_TABLE_ROWS_INSERTED` are updated as each table is processed.
- New `CLEANUP` keyword for `PG_UPSERT` — drops all `ups_*` temporary tables and views after execution. Without it, temp objects persist for inspection (default).

______________________________________________________________________

## [2.12.5] - 2026-04-03

### Fixed

- Fixed CLI test `test_nonexistent_file_error_message_is_clear` failing with `ValueError: stderr not separately captured` when CliRunner mixes stderr into stdout.

______________________________________________________________________

## [2.12.4] - 2026-04-03

### Added

- New `PG_UPSERT` metacommand for QA-checked, FK-dependency-ordered upserts from a staging schema to a base schema on PostgreSQL. Integrates [pg-upsert](https://pg-upsert.readthedocs.io/) as an optional dependency (`pip install execsql2[upsert]`). Three modes: full pipeline (`PG_UPSERT FROM ... TO ... TABLES ...`), QA-only (`PG_UPSERT QA ...`), and schema check (`PG_UPSERT CHECK ...`). Supports `METHOD`, `COMMIT`, `INTERACTIVE`, `COMPACT`, `EXCLUDE`, `EXCLUDE_NULL`, and `LOGFILE` keywords. Sets 12 `$PG_UPSERT_*` substitution variables after execution.

______________________________________________________________________

## [2.12.3] - 2026-04-02

### Changed

- Performance: split `set_system_vars()` into static (once per script + on CONNECT/CHDIR) and dynamic (per statement) — eliminates ~14 redundant `add_substitution` calls and 2 `Path.resolve()` filesystem syscalls per statement.
- Performance: `$RANDOM` and `$UUID` are now lazy — computed only when actually referenced in a statement, not generated unconditionally for every statement.
- Performance: `LineDelimiter.delimited()` caches `quote_all_text` at construction time instead of reading `_state.conf` via module proxy on every row during export.
- Performance: CSV/TSV import uses Python's `csv` module as a fast path for standard delimited formats (comma, tab, semicolon, pipe) with doubled-quote escaping. Falls back to the character-at-a-time parser for non-standard formats (space-delimiter collapsing, escape characters).

______________________________________________________________________

## [2.12.2] - 2026-04-02

### Added

- Documentation: keyring setup guide for headless Linux servers (encrypted and plaintext file backends) in the Security reference page, with a cross-reference from the Installation page.

### Changed

- `ASSERT` failures now report `**** Assertion failed.` instead of `**** Error in metacommand.` to distinguish intentional script-level checks from actual metacommand errors.

______________________________________________________________________

## [2.12.1] - 2026-04-02

### Changed

- Performance: removed dead `_compiled_patterns` dict from `SubVarSet` — eliminated 3 unused regex compilations per `add_substitution` call (~20 calls per statement in typical scripts).
- Performance: cached `source_dir` and `source_name` on `ScriptCmd` at construction time — eliminated per-statement `Path.resolve()` filesystem calls.
- Performance: `select_rowdict()` now uses batched `fetchmany()` instead of row-at-a-time `fetchone()`, matching `select_rowsource()` behavior for template exports.
- Performance: removed redundant `$CURRENT_TIME` set in `set_system_vars()` — now set once per statement in `run_and_increment()`.
- Performance: removed no-op `copy.copy()` on immutable string in `substitute_vars()`.

### Fixed

- Fixed cursor leak in `select_rowsource()` — generator now closes the cursor in a `finally` block when exhausted or abandoned.

______________________________________________________________________

## [2.12.0] - 2026-04-01

### Added

- Debug REPL `.where` / `.w` command — shows current script file, line number, and the upcoming statement text (truncated to 120 chars). The entry banner now includes the location (`[Breakpoint] myscript.sql:42`) and `_print_where()` is called automatically on REPL entry via `BREAKPOINT` or step mode.
- Debug REPL `.set VAR VAL` / `.s VAR VAL` command — sets or updates a substitution variable interactively during a `BREAKPOINT` session. Prints a confirmation line (`VAR = VAL`) on success; prints an error if substitution variables are not initialised.
- Debug REPL ANSI color output — horizontal rule separators, colored labels ("Breakpoint"/"Step" in bold yellow, filename:line in cyan, type tags in dim green), cyan variable names, dim `=` signs, red error messages, bold SQL column headers, and dim row-count and table borders. Color is auto-detected via TTY and suppressed when `NO_COLOR` or `EXECSQL_NO_COLOR` environment variables are set. Falls back to plain text in non-interactive contexts (CI, piped output). Help text is also colorized with cyan command names and consistent column alignment.
- Debug REPL shortcut aliases — `.h` for `.help`, `.v` for `.vars`, `.v all` for `.vars all`.
- Debug REPL step mode banner — when the REPL is re-entered via `.next` / step mode, the entry banner now shows "Step" instead of "Breakpoint" to make it clear the pause is from stepping rather than an explicit `BREAKPOINT` metacommand.
- `--profile-limit N` CLI option — controls how many top statements appear in the `--profile` timing summary (default: 20). The "not shown" footer message now includes the active limit for clarity.
- Test coverage raised from 86% to 91% — 274 new tests across `metacommands/io_import.py`, `metacommands/io_export.py`, `metacommands/control.py`, `metacommands/data.py`, `importers/csv.py`, and `gui/console.py`. Coverage floor raised from 85% to 90% in `pyproject.toml`.

### Changed

- `execsql.debug.repl` is now a dedicated package (`src/execsql/debug/repl.py`); previously the REPL lived at `execsql.metacommands.debug_repl`. Internal import paths have been updated throughout. No public API change.

______________________________________________________________________

## [2.11.1] - 2026-04-01

### Fixed

- `x_assert` crash when `exec_log` is None — added null guard on `log_user_msg()` call.
- `--ping` version-query loop exiting prematurely — `break` was at wrong indentation, skipping fallback queries when the first query returned no rows.
- `CONSOLE SET WIDTH/HEIGHT` crash — `gui_console_width()`/`gui_console_height()` restored as setter functions with GUI console propagation.
- `$ERROR_MESSAGE` now contains full `errmsg()` (with script location and timestamp) for non-halting errors.
- Non-halting SQL and metacommand errors now logged to exec_log.
- `x_debug_log_subvars` log format — was printing full tuple instead of name/value for local variables.
- Dead `endloop()` removed from `control.py` — `state.endloop()` is canonical.
- YAML `append=True` now emits `---` document separator for valid multi-document streams.
- REPL dot-command parsing consistency between dispatcher and exit-check.
- `__delattr__` on state proxy uses cached `_DEFAULT_CTX` instead of allocating per call.
- `write_query_to_xlsx` single-sheet now updates `export_metadata`.
- `isinstance()` used instead of `type()` equality in `MetaCommandList.add()`.
- Module docstrings in `conditions.py` and `control.py` moved before imports.
- FEATHER divergence doc corrected — `polars` only, not `polars + pyarrow`.
- README pre-commit rev updated to `v2.11.0`; options table completed.

______________________________________________________________________

## [2.11.0] - 2026-04-01

### Added

- `--debug` CLI flag — starts the script in step-through debug mode. The debug REPL pauses before each statement, as if `BREAKPOINT` were inserted at the top with `.next` always active.

### Changed

- BREAKPOINT debug REPL now pauses **before** each statement instead of after, so the upcoming statement can be inspected before it runs.

### Fixed

- BREAKPOINT REPL no longer wraps variable values in extra single quotes — values are now displayed exactly as defined.
- Error messages now include script file name and line number — `ErrInfo` fields `script_file` and `script_line_no` are populated via a new `stamp_errinfo()` helper called from `exit_now()` and metacommand error paths, restoring monolith-level "Line N of script foo.sql" context in all error output.
- `$ERROR_MESSAGE` substitution variable is now updated on every error: in `exit_now()`, in non-halting SQL errors (`SqlStmt.run()`), and in non-halting metacommand errors (`MetacommandStmt.run()`). Previously it was initialized to `""` and never changed.
- `MetacommandStmt.run()` now re-raises the original handler `ErrInfo` when `halt_on_metacommand_err` is True, instead of discarding it and raising a generic "Unknown metacommand" error.
- `write_warning()` now accepts an `always=True` keyword argument that bypasses the `conf.write_warnings` gate, ensuring structural warnings (IF-level mismatch, unsubstituted variables) are always visible on stderr.
- Uncaught-exception error message in `_execute_script_direct()` and `_execute_script_textual_console()` no longer appends "in script , line 0" when `current_script_line()` returns an empty string.

______________________________________________________________________

## [2.10.1] - 2026-04-01

### Fixed

- BREAKPOINT variable lookup — `$logfile` was showing `(undefined)` because `SUB` stores keys without a sigil prefix. The debug REPL now strips `$`, `&`, `@`, `#`, `~` prefixes and retries when the exact name isn't found.

______________________________________________________________________

## [2.10.0] - 2026-04-01

### Added

- **`BREAKPOINT` metacommand** — pauses script execution and drops into an interactive debug REPL. The prompt accepts `continue`/`c` to resume, `abort`/`q` to halt, `vars` to list substitution variables, `$VARNAME` to print a single variable, `SELECT ...;` to run ad-hoc SQL against the current database, `next`/`n` to step one statement at a time, `stack` to inspect the command-list stack, and `help` for a command summary. Silently skipped in non-TTY environments (CI, piped input) so automated pipelines are never blocked.

- **`step_mode` on `RuntimeContext`** — internal boolean flag set by the REPL's `next` command; the script engine re-enters the debug REPL after each subsequent statement while step mode is active.

- **`ROW_COUNT_GT(table, N)`**, **`ROW_COUNT_GTE(table, N)`**, **`ROW_COUNT_EQ(table, N)`**, **`ROW_COUNT_LT(table, N)`** conditional tests — compare the row count of any table or view against an integer threshold using `IF`, `ELSEIF`, or `ASSERT`. Each issues a `SELECT count(*)` query against the current database. An error is raised if the table does not exist or the threshold is not an integer.

______________________________________________________________________

## [2.9.0] - 2026-04-01

### Added

- **`--lint` flag** — parse a script and perform static analysis without connecting to a database or executing anything. Reports unmatched `IF`/`ENDIF`, `LOOP`/`END LOOP`, and `BEGIN BATCH`/`END BATCH` blocks as errors; potentially undefined `!!$VAR!!` variable references and missing `INCLUDE` file targets as warnings. Exits 0 if no errors are found (warnings alone do not affect the exit code); exits 1 if any errors are found. Works with both file scripts and inline `-c` scripts.
- **`--ping` flag** — test database connectivity without running a script. `execsql --ping --dsn <URL>` connects to the database, queries the server version, prints a one-line success summary (DBMS name, version, and location), and exits 0. On failure it prints the error and exits 1. No script file argument is required when `--ping` is used.

______________________________________________________________________

## [2.8.0] - 2026-04-01

### Added

- **`--profile` flag** — records wall-clock time for each SQL and metacommand statement and prints a formatted timing summary after the script completes. The summary lists statements sorted by elapsed time descending (top 20 shown), with per-statement percentage of total time, source location, command type, and a preview of the command text.
- **`ASSERT` metacommand** — evaluates any IF-compatible condition and raises an error (halting the script when `HALT_ON_METACOMMAND_ERROR` is `ON`) if the condition is false. Supports an optional quoted failure message; omitting the message produces `Assertion failed: <condition>`. A passing assertion is logged. ASSERT is silently skipped inside a false IF block.

### Changed

- **`--dry-run` expands substitution variables** — the command list printed by `--dry-run` now shows resolved `!!$VAR!!` / `!!&ENV!!` tokens for variables that are already populated at parse time (environment variables, `--assign-arg` values, config-sourced variables, and built-in start-time variables like `$SCRIPT_START_TIME`). Variables that are set during execution (e.g. `$CURRENT_TIME`, `$DB_NAME`, `$TIMER`) remain unexpanded because the database connection has not yet been established. Local `~`-prefixed script-scope variables are also left unexpanded. If expansion fails (e.g. a cycle is detected), the raw token is displayed instead.

______________________________________________________________________

## [2.7.1] - 2026-04-01

### Fixed

- Fix `AttributeError: module 'execsql.state' has no attribute 'dedup_words'` when importing CSV files with `DEDUP_COL_HDRS` enabled — `dedup_words` is now correctly imported from `execsql.utils.strings` instead of accessed through the state module.

______________________________________________________________________

## [2.7.0] - 2026-04-01

### Added

- **Markdown export** (`FORMAT MARKDOWN` / `FORMAT MD`) — GitHub-flavored pipe tables with column alignment, pipe/backslash escaping, and zip support. No dependencies required.
- **YAML export** (`FORMAT YAML`) — list-of-dicts output via PyYAML with native type preservation (int, float, null). Requires `PyYAML` (included in `formats` extras).
- **XLSX export** (`FORMAT XLSX`) — single-sheet and multi-sheet Excel export via openpyxl with bold headers, native type preservation, sheet name deduplication, and a "Datasheets" inventory sheet. Multi-sheet syntax: `EXPORT table1, table2 TO file.xlsx AS XLSX`.

______________________________________________________________________

## [2.6.0] - 2026-04-01

### Added

- Textual TUI `console_save()` — writes console output to a file, matching Tkinter parity.
- Keyboard shortcut hints on Textual TUI dialog screens — Escape to cancel, Enter to submit, with `Footer` widget on all major dialog screens.
- `RuntimeContext` class in `state.py` — groups all 33 mutable runtime globals into a single slotted object. Enables isolated contexts for testing and future concurrent execution.
- `get_context()` / `set_context()` public API for programmatic access to the active runtime context.
- Divergence from Upstream documentation page (`docs/about/divergence.md`) listing all user-visible changes since the fork.
- Test coverage raised from 80% to 86% — 403 new tests across `db/base.py`, `metacommands/connect.py`, `script/engine.py`, and `exporters/delimited.py`.

### Changed

- `state.py` module now uses a `types.ModuleType` subclass that transparently proxies attribute reads and writes to the active `RuntimeContext` instance. All existing `_state.foo` call sites continue working with zero changes.
- `reset()` simplified from 40 lines with 7 `global` statements to a clean context replacement (preserving `filewriter`).
- `initialize()` and `endloop()` rewritten to use `_ctx` directly instead of `global` statements.
- Removed 180 redundant `# noqa` suppressions from `metacommands/__init__.py` — the existing `__all__` already satisfies ruff F401.

______________________________________________________________________

## [2.5.0] - 2026-04-01

### Added

- Docstrings on 183 public API symbols across `db/`, `exporters/`, `importers/`, `config.py`, `models.py`, `types.py`, and `parser.py` — public API docstring coverage raised from 40% to 81%.
- Developer architecture guide (`docs/dev/architecture.md`) — high-level design overview with Mermaid diagrams covering execution flow, module map, command stack, metacommand dispatch, conditionals, substitution variables, database abstraction, export/import pipeline, GUI subsystem, and global state.
- Exporter `Protocol` types (`QueryExporter`, `RowsetExporter`) in `exporters/protocol.py` for type-checking and documentation of the exporter interface contract.

### Changed

- Cursor lifecycle in database adapters — all `exec_cmd()` methods and PostgreSQL `vacuum()` now use the `_cursor()` context manager to prevent cursor leaks.

- Optimized `SubVarSet.merge()` — copies pre-compiled patterns directly instead of recompiling O(V) regex patterns per merge call. Eliminates the main variable substitution hotspot when local variables are in scope.

- Upgraded GitHub Actions to Node.js 24-compatible versions: checkout v6, setup-python v6, cache v5, upload/download-artifact v7/v8, codecov v6.

### Fixed

- Corrected repo URL in `zensical.toml` — was pointing to `execsql2` instead of `execsql`.
- Fixed formatter before/after example in docs to use correct metacommand syntax.
- Removed unnecessary blockquote nesting in SQL syntax notes and using scripts docs.

______________________________________________________________________

## [2.4.6] - 2026-03-31

### Added

- End-to-end CLI tests (26 tests) covering `--version`, `--help`, `--dump-keywords`, `-c` inline commands, script file execution, `--dry-run`, error cases, and `execsql-format`.
- `__all__` exports to 18 public modules: `state.py`, `format.py`, `constants.py`, `cli/` (4 files), `gui/` (5 files), `script/` (3 files), `metacommands/` (3 files).
- Exception chaining (`from None`) on all `raise` statements inside `except` blocks; enabled ruff rule B904.

### Changed

- Gitignore `docs/change_log.md` — it is auto-generated from `CHANGELOG.md` by the ReadTheDocs pre-build step and `just docs`/`just docs-serve` recipes.
- Clarified conditional test headings in metacommand docs — removed ambiguous "test" suffix from all 30 headings and added a section preamble explaining where conditional expressions can be used.
- Reorganized documentation file structure to match nav groupings: `getting-started/`, `reference/`, `guides/`, `about/` subdirectories. Updated all 306 cross-references.

______________________________________________________________________

## [2.4.5] - 2026-03-31

### Added

- VS Code syntax highlighting section to README.
- Pre-commit hook usage to README formatting section.

### Changed

- Updated README options table, removed test count badge, require doc updates for all changes.

### Fixed

- `ON ERROR_HALT EXECUTE SCRIPT` and `ON CANCEL_HALT EXECUTE SCRIPT` metacommands were not recognized — handler functions existed but dispatch patterns were missing.
- `EXTEND SCRIPT <X> WITH SCRIPT <Y>` metacommand was not recognized — only the `APPEND SCRIPT` synonym was ported from the upstream monolith.
- `PROMPT ASK` with single-quoted (`'...'`) or bracket-delimited (`[...]`) questions, and with unquoted `HELP` arguments, were not recognized — only the double-quoted question with double-quoted help variant was ported.
- `CONNECT TO SQLSERVER` with mixed quoting (e.g., quoted SERVER + unquoted DB) or quoted PASSWORD was not recognized — only the fully-unquoted and fully-quoted variants were ported.

______________________________________________________________________

## [2.4.4] - 2026-03-30

### Fixed

- PyPI publish URL — use `execsql2` package name instead of repo name.
- SQLite import-error test — patch `fatal_error` before `__import__`.

______________________________________________________________________

## [2.4.3] - 2026-03-30

### Added

- Pre-commit hook for `execsql-format` — users can add the repo to their `.pre-commit-config.yaml` and pass `--check` or `--in-place` via `args`.

______________________________________________________________________

## [2.4.2] - 2026-03-30

### Changed

- Raised test coverage floor from 75% to 80% in `pyproject.toml`.

______________________________________________________________________

## [2.4.1] - 2026-03-30

### Fixed

- `--dsn` now correctly overrides connection settings from configuration files.
- MySQL `LOAD DATA INFILE` encoding — map Python encoding names (e.g. `utf-8`) to MySQL charset names (e.g. `utf8mb4`).
- Importer error reporting — replaced removed `exception_info()` with `exception_desc()`.

### Changed

- Integration tests moved to `tests/integration/` with a shared conftest and parallel CI execution.
- CI no longer enforces the coverage threshold for integration tests.
- Removed `docker-compose.yml` — CI uses GitHub Actions services directly.

______________________________________________________________________

## [2.4.0] - 2026-03-30

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
- PostgreSQL integration tests (9 tests) — full lifecycle via `--dsn` connection strings.
- MySQL/MariaDB integration tests (9 tests, 1 xfail for pre-existing import adapter bug).
- `docker-compose.yml` for local PostgreSQL and MySQL test databases.
- CI integration test job with GitHub Actions services (PostgreSQL 16, MySQL 8).
- Roadmap items in `templates/README.md` for integrating execsql-compare and execsql-upsert documentation into the main docs site.

### Fixed

- Fix odfpy import — `import of` corrected to `import odf as of` in `exporters/ods.py` and test skip guards. ODS export was broken since the modular refactor.
- Pass `--dsn` password through to all database backends (MySQL, SQL Server, Oracle, Firebird, DSN). Previously only PostgreSQL received the password from connection strings.
- Fix importer error reporting — `exception_info()` (returns tuple) replaced with `exception_desc()` (returns string) in 6 call sites across `importers/base.py`, `importers/csv.py`, and `importers/feather.py`. This caused `AttributeError: 'tuple' has no attribute 'replace'` on any import failure.
- Map Python encoding names to MySQL charset names in `LOAD DATA LOCAL INFILE` (e.g., `utf-8` → `utf8mb4`). Previously caused `Unknown character set` errors on MySQL imports.
- `--dsn` now overrides conf-file connection settings (server, database, user, port). Previously conf-file values took precedence, silently ignoring the DSN.

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
