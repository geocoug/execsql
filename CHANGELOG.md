# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries prior to `2.0.0` are from the upstream
[execsql](https://execsql.readthedocs.io/) project by R.Dreas Nielsen.

______________________________________________________________________

## [Unreleased]

### Changed

- Published `execsql-format` pre-commit hook now defaults to `args: [--in-place]`. Downstream configs that listed `- id: execsql-format` with no `args:` previously got a silent no-op (the CLI's default is stdout, which pre-commit doesn't capture); they will now reformat files in place. Override with `args: [--check]` for check-only mode.
- Pre-commit `rev:` snippets in `README.md` and `docs/guides/formatter.md` now point at `v2.19.2` and are rewritten automatically by `bump-my-version` on every version bump, so they cannot drift.

### Fixed

- `[firebird]` extra now connects: the adapter imports `firebird.driver` (provided by `firebird-driver`) instead of the missing `fdb` module. Users who installed `pip install execsql2[firebird]` previously hit `ModuleNotFoundError: No module named 'fdb'` at connect time.

______________________________________________________________________

## [2.19.2] - 2026-06-03

### Fixed

- `pre-commit` hook `execsql-format` now installs `sqlglot` into its isolated env. Since 2.19.0 moved `sqlglot` to the `[formatter]` extra, the hook env (which installs the bare package) was missing it and crashed with `ModuleNotFoundError: No module named 'sqlglot'`. Re-run `pre-commit clean && pre-commit install --install-hooks` after upgrading to pick up the new dependency.

______________________________________________________________________

## [2.19.1] - 2026-06-03

### Fixed

- `execsql-format` no longer mangles quoted substitution variables: `!'!var!'!` and `!"!var!"!` were being parsed by sqlglot as `NOT` operators (e.g. `!'!myvar!'!` → `NOT NOT '!myvar!'`). All three quote forms plus deferred `!{var}!` are now hidden from SQL formatting.

______________________________________________________________________

## [2.19.0] - 2026-06-02

### Fixed

- `IMPORT … FORMAT xlsx` rejects zip-bomb workbooks (per-member ratio over 100:1, or total uncompressed size over 500 MB). Convert large workbooks to CSV for import. Legacy `.xls` is unaffected.
- `EXPORT … FORMAT hdf5` no longer truncates `BIGINT` columns to 32-bit, and `DT_Text` columns now honour the configured `hdf5_text_len`.
- `BREAKPOINT` REPL no longer ends the session on a bad SQL statement — errors print inline and the prompt returns.
- `BREAKPOINT` REPL handles DML / DDL / transaction-control statements: DML prints `(N rows affected)`, DDL / `BEGIN` / `COMMIT` / `ROLLBACK` print `(statement executed)`.
- `BREAKPOINT` REPL accepts multi-line SQL — input is buffered until a line ends with `;`. `.cancel` (or Ctrl-C / EOF) discards a partial buffer.

### Changed

- **`BREAKPOINT` REPL dispatch is now two-way**: input starting with `.` is a REPL command, everything else is SQL. Bare-name variable lookup is removed — use `.vars VAR` (e.g. `.vars logfile`, `.vars $ARG_1`) to print one variable; `.vars` alone still lists all.
- `sqlglot` moved to the new `[formatter]` extra. Install `execsql2[formatter]` to use `execsql-format`'s SQL pass; `execsql-format --no-sql` works without.
- `textual` dependency floor raised to `>=1.0` (was `>=0.47.0`).

______________________________________________________________________

## [2.18.1] - 2026-05-28

### Changed

- Internal: `execsql.cli.lint_ast` has been folded into `execsql.cli.lint`; the AST walker entry point is now `execsql.cli.lint.lint()`. Code that imported `execsql.cli.lint_ast.lint_ast` should import `execsql.cli.lint.lint` instead.

### Removed

- Internal: the unused `run_when_false` and `run_in_batch` flags on `MetaCommand` (and the matching keyword arguments on `MetaCommandList.add()`) — neither has been consulted since v2.16.0. Code that still passes either kwarg to `mcl.add()` will raise `TypeError`.

______________________________________________________________________

## [2.18.0] - 2026-05-27

### Added

- `IS_FALSE(<value>)` conditional predicate — recognises `No`, `N`, `False`, `F`, and `0` as falsy (case-insensitive); inverse of `IS_TRUE`. Previously documented but not implemented, so `IF (IS_FALSE(...))` raised `CondParserError`.
- `--no-rm-file` and `--no-serve` CLI flags disable the `RM_FILE` and `SERVE` metacommands, symmetric with the existing `--no-system-cmd`. Matching `allow_rm_file` and `allow_serve` config keys are honoured in the `[config]` section of `execsql.conf`.
- New `include_root`, `serve_root`, and `template_root` config keys in the `[config]` section of `execsql.conf`. When set, `INCLUDE` / `EXECUTE SCRIPT`, `SERVE`, and Jinja2 / `string.Template` loaders confine resolved paths under the named root and reject anything that escapes via `..`, absolute paths, drive letters, or UNC paths.
- `Database.quote_literal(value)` and `Database.quote_qualified_identifier(*parts)` helpers on the base `Database` class. The default `quote_literal` escapes `\` and doubles `'` and rejects NUL bytes; subclasses can override for dialect-specific literal forms.
- `Database.needs_explicit_commit_after_ddl()` and `Database.auto_commits_ddl()` capability hooks. Firebird overrides the first (its driver leaves DDL pending until commit). Oracle, MySQL, SQL Server, and MS Access override the second (their drivers implicitly commit DDL — `rollback()` is a silent no-op for transactions whose boundary the DDL crossed).
- `EncodedFile` now supports the context-manager protocol (`with EncodedFile(...) as fh:`); callers no longer have to remember an explicit `close()` in a `try` / `finally` block.
- `~/execsql.log` is now created with mode `0o600` on POSIX so the substituted SQL, `-a` values, env vars, and DSN URLs it captures are not world-readable. Previously the file inherited the umask default (typically `0o644`).
- `-a NAME VALUE` substitution-variable assignments are redacted to `***` in the log when the value contains a sensitive substring (`PASSWORD`, `SECRET`, `TOKEN`, `PASSWD`, `PRIVATE_KEY`, `CREDENTIAL`).
- A warning is now printed when the `--dsn` URL contains an embedded password, since it remains visible in `ps`, shell history, and process accounting.
- `EXPORT … FORMAT xlsx` and `IMPORT … FORMAT xlsx` now reject zip-bomb XLSX files via a new `check_zip_decompression_ratio` helper that inspects the OOXML zip directory before openpyxl parses the file. Rejects individual members with a compression ratio above 100:1 (default) and aggregate uncompressed size above 500 MB (default).
- `IMPORT … FORMAT ods` and `EXPORT … FORMAT ods` defuse the stdlib XML parsers via `defusedxml.defuse_stdlib()` on first `OdsFile` construction, protecting odfpy from billion-laughs / external-entity attacks. The `defusedxml` package is now part of the `[formats]` extra.
- `substitute_vars()` now aborts when expanded output exceeds 10 MB (configurable via the new `max_substitution_bytes` key in the `[config]` section), defending against exponential-expansion bombs where a chain of substitutions accumulates beyond a safe size before the iteration depth cap fires.
- `IMPORT … ODS PATTERN <regex>` and `IMPORT … XLS PATTERN <regex>` now raise a friendly `ErrInfo` listing the invalid pattern instead of letting an uncaught `re.error` bubble up from `re.compile`.
- `IMPORT … FROM JSON` with [JSON Lines](https://jsonlines.org/) (JSONL) now reads the file line-by-line instead of buffering the entire text alongside the parsed records. The standard JSON-array path is unchanged (would require an `ijson` dependency to stream).
- New `execsql.utils.auth.is_plaintext_keyring()` helper detects when the active OS keyring backend stores secrets in cleartext (e.g. `keyrings.alt.file.PlaintextKeyring` on headless Linux without a real Secret Service). The internal `_keyring_set()` path now emits a one-time stderr warning before writing into a plaintext backend so users know stored passwords are not meaningfully protected at rest.
- On POSIX systems without `$DISPLAY` or `$WAYLAND_DISPLAY`, `enable_gui()` now skips the Tkinter backend entirely and falls through to the Textual / Console backends, instead of failing with a cryptic `_tkinter.TclError` that the broad-except previously swallowed.
- Internal: `.github/workflows/ci-cd.yml` now SHA-pins all third-party GitHub Actions with a trailing `# vX.Y.Z` comment; new `.github/dependabot.yml` files weekly bump PRs grouping minor/patch action updates.
- Documented `$CURRENT_DATE` and `$CURRENT_SCRIPT_LINE` substitution variables in `docs/reference/substitution_vars.md`; the `[map]` extra in the README installation list; `RUN SCRIPT` as an alias for `EXECUTE SCRIPT` in `docs/reference/metacommands.md`. All were functional, just undocumented.
- Expanded `SECURITY.md` from a stub-policy page to a defense-in-depth catalogue covering substitution-variable quoters, path-containment, SQL-injection mitigations, file-format defenses (XLSX zip-bomb, ODS XML), credential/logging hygiene, and known limitations.

### Changed

- Bundled `templates/{pg,md,ss}_{upsert,compare,glossary}.sql` now use the safe `!'!#var!'!` substitution form instead of `'!!#var!!'`, so single quotes in script-argument values are escaped when interpolated into SQL string literals.
- `--output-dir` is now a containment boundary, not just a prefix. Absolute paths or `..` traversals that escape the configured root are rejected. Stdout passes through unchanged. The setting now also applies to `EXPORT QUERY`, `EXPORT … WITH TEMPLATE`, `EXPORT METADATA`, and the multi-sheet `EXPORT ODS` / `EXPORT XLSX` variants, which previously ignored it.

### Fixed

- `templates/script_template.sql` had two `WRITE` lines (`Committing:` and `Cleaning up:`) with unterminated double-quoted strings; the closing quotes are now present.
- `ends_with(string, "")` now returns `True` for any string, matching Python's `str.endswith` semantics. Previously it returned `True` only when the haystack was also empty.
- ODBC DSN connections now brace-quote the DSN, UID, and PWD attribute values with `{…}` (and double any embedded `}`) so a password or user containing `;` cannot inject additional connection-string attributes (CWE-91 / ODBC attribute injection).
- The `!"!var!"!` substitution operator now doubles embedded `"` so a value like `foo"; DROP TABLE x; --` produces a single valid quoted identifier rather than a closing quote followed by a second statement.
- The `!'!var!'!` substitution operator now always escapes embedded `\`, not just on Windows. The previous Windows-only branch left MySQL default-mode and PostgreSQL E-string literals open to `\'` injection from POSIX hosts.
- All three substitution forms (`!!var!!`, `!'!var!'!`, `!"!var!"!`) now reject values containing NUL bytes, which most DBMS wire protocols silently truncate or reject. The check fires only for the variable actually being interpolated — a NUL byte in an unrelated, unreferenced variable no longer blocks every other substitution.
- `EXPORT … FORMAT sqlite` and `EXPORT … FORMAT duckdb` now identifier-quote the table name in `DROP TABLE` / `INSERT INTO` and parameter-bind it in the existence check, closing two SQL-injection-via-tablename sites.
- MySQL / MariaDB and SQL Server `Database.quote_identifier()` now use the native backtick (`` `…` ``) and bracket (`[…]`) forms respectively, so identifier quoting works even if user SQL has reset `sql_mode` / `QUOTED_IDENTIFIER`.
- `IMPORT` into a SQLite database now batches rows and uses `cursor.executemany()` (honouring `import_row_buffer`, default 1000) instead of issuing one `cursor.execute()` per row. Million-row imports are 10–100× faster.
- `MySQL.table_exists()`, `column_exists()`, and `view_exists()` now honour the server's `@@lower_case_table_names` setting: on Linux with the default `0`, identifiers are compared case-sensitively as before; on Windows/macOS (`1`) or `2`, the input name is folded to lowercase so a query like `table_exists("MyTable")` matches a row stored as `mytable`. The server variable is queried once and cached per connection.

### Removed

- `EXPORT` no longer adds a leading `'` to CSV / XLSX / ODS string cells starting with `=`, `+`, `-`, `@`, or tab; exports preserve string values verbatim. The `csv_safe_formulas` config key is removed.
- Internal: the legacy flat-CommandList linter (`_lint_script` and helpers in `execsql.cli.lint`) has been deleted. The `--lint` CLI has used the AST-based linter (`execsql.cli.lint_ast`) since v2.13; only `_print_lint_results` and the issue-constructor helpers remain in `execsql.cli.lint`. Breaking change for code that imported `_lint_script` from `execsql.cli.lint` directly.

______________________________________________________________________

## [2.17.3] - 2026-05-26

### Changed

- Optional `[upsert]` extra now requires `pg-upsert>=1.22.1` (was `>=1.22.0`). 1.22.1 removed upper bounds on its `typer` and `pyyaml` dependencies, so installing `execsql2[upsert]` alongside the latest Typer/PyYAML no longer triggers a resolver conflict.

______________________________________________________________________

## [2.17.2] - 2026-05-26

### Fixed

- `!'!var!'!` substitution now wraps the value in single quotes, matching the documented behavior. Previously only embedded apostrophes were doubled.
- `BREAK` inside an `EXECUTE SCRIPT` body raises an error instead of silently terminating the caller's `LOOP`.
- `WRITE SCRIPT` output is now re-includable: nested `IF` / `LOOP` / `BATCH` / `SQL` blocks, `INCLUDE`, `EXECUTE SCRIPT`, and comments are all preserved, and `BEGIN/END SCRIPT` lines carry the `-- !x!` prefix.
- `PROMPT MAP` falls back to the tabular view on any map-widget construction failure (headless display, missing dependencies).
- `TABLE_EXISTS` / `VIEW_EXISTS` against SQLite, Oracle, Firebird, and Access now match identifiers case-insensitively per each database's native semantics. Access also moved off the now-restricted `MSysObjects` catalog so the checks work on Access 2016+ default permissions.
- Oracle `ROLE_EXISTS` works for non-DBA accounts (falls back to `session_roles` when `dba_roles` isn't accessible).
- SQL Server connection setup, PostgreSQL / MySQL fast-path `IMPORT`, and `Database.close()` no longer crash with `AttributeError` when called before the execution log is initialised (library and pre-run code paths).
- File-output operations complete instead of hanging if the background `FileWriter` subprocess crashes mid-run.

### Removed

- Internal: legacy command-list execution engine removed. Breaking change for code that imported `CommandList` / `IfLevels` from `execsql.script` or read `_state.commandliststack` / `_state.if_stack` / `_state.savedscripts` directly; migrate to `_state.current_localvars()` / `_state.current_paramvals()` and the `ExecFrame` data class on `_state.ast_exec_stack`.

______________________________________________________________________

## [2.17.1] - 2026-05-22

### Fixed

- VS Code grammar now highlights the single-quoted (`!'!name!'!`) and double-quoted (`!"!name!"!`) substitution variable variants, not just the bare `!!name!!` form. Regenerate the bundled grammar with `just install-vscode`.
- Mermaid diagrams in the docs site now render as SVG (previously plain code blocks).
- Documentation accuracy sweep across `docs/reference/`, `docs/guides/`, `docs/getting-started/`, `docs/about/`, and `docs/dev/`: fixed nine broken cross-link anchors, corrected ~30 source-module docstrings (stale class/function/extras names), repaired API reference page rendering, and corrected the `--profile` description to mention `--profile-limit`.

### Added

- New "Quoting Convention" section in `docs/reference/substitution_vars.md` documenting how `SUB`, variable substitution, and `EXECUTE SCRIPT` argument parsing compose — and the common quote-stripping footgun with `wo_quotes()`.
- Documented eight `DEBUG WRITE …` variants, the `PROMPT MAP` metacommand, the `IS_FALSE` conditional, and `RUN` as an alias for `EXECUTE` in `docs/reference/metacommands.md`. All were functional, just undocumented.
- Documented five previously-undocumented CLI flags: `--progress`, `--profile-limit`, `--no-system-cmd`, `--config`, `--init-config`.

______________________________________________________________________

## [2.17.0] - 2026-05-07

### Changed

- **Behavior change.** `PG_UPSERT`, `PG_UPSERT QA`, and `PG_UPSERT CHECK` no longer raise a metacommand error when QA checks fail. The outcome is reported via `$PG_UPSERT_QA_PASSED`, `$PG_UPSERT_TABLE_QA_PASSED`, and `$PG_UPSERT_RESULT_JSON`, so the script controls flow with `IF` or `ASSERT`. `EXPORT_FAILURES` still runs and the upsert is still skipped on QA failure. Migration: add `ASSERT !!$PG_UPSERT_QA_PASSED!! = TRUE` at the call site to preserve the previous halt-on-failure behavior.

### Fixed

- `!!$COUNTER_N!!` references inside metacommands (`WRITE`, `IF`, `SUB`, etc.) now return the documented sequence `1, 2, 3, …` starting at 1. The same fix stabilizes `!!$RANDOM!!` and `!!$UUID!!` across `BREAK` detection and dispatch.

______________________________________________________________________

## [2.16.18] - 2026-05-05

### Fixed

- `BEGIN SCRIPT` parameter defaults now strip surrounding quotes, matching the existing handling at the call site. A default written as `default_unit_set="Default"` previously bound the literal string `"Default"` (quotes intact).

### Changed

- `SHOW SCRIPTS <name>` and `.scripts <name>` now display the full source path (including `<inline>` for `-c` scripts). List views continue to show basenames for column alignment.
- `BEGIN SCRIPT WITH PARAMETERS (...)` now accepts quoted default values containing spaces, commas, and other special characters. Unterminated quoted values are now rejected as malformed instead of being silently stored.

______________________________________________________________________

## [2.16.17] - 2026-05-04

### Fixed

- Formatter no longer treats inline `IF (cond) { command }` as a block opener (lines after an inline `IF` were previously indented forever).
- Formatter no longer escapes blank lines inside `BEGIN SQL` / `BEGIN BATCH` blocks.

______________________________________________________________________

## [2.16.16] - 2026-05-02

### Added

- `--init-config` CLI flag prints a default `execsql.conf` template (all options commented out and documented) to stdout. Use `execsql --init-config > execsql.conf` to bootstrap.
- `--no-system-cmd` CLI flag disables `SYSTEM_CMD`/`SHELL`. Also configurable via `allow_system_cmd = No` in `[config]` or `allow_system_cmd=False` in the library API.

### Changed

- CLI `--help` now groups options by category: connection, encoding, import/export, execution, GUI, configuration, information.
- `execsql.conf` template updated: added missing options (`use_keyring`, `gui_framework`, `allow_system_cmd`, `log_sql`, `max_log_size_mb`, `show_progress`, `import_progress_interval`, `macos_config_file`), fixed incorrect defaults (`password_prompt`, `new_db`, `scan_lines`), added DuckDB (`k`) to database types.

### Fixed

- `SYSTEM_CMD` no longer wraps arguments containing `&` in spurious double quotes (a Windows `cmd.exe` workaround inherited from upstream that broke non-`cmd` targets).

______________________________________________________________________

## [2.16.15] - 2026-05-02

### Changed

- Merged `SHOW SCRIPTS` and `SHOW SCRIPT <name>` into `SHOW SCRIPTS [<name>]`. Without a name, lists all registered scripts; with a name, shows detail.

______________________________________________________________________

## [2.16.14] - 2026-05-01

### Fixed

- `ELSEIF` conditions now support `ANDIF`/`ORIF` modifiers (previously silently attached to the parent `IF`).
- Unknown AST node types now raise an error instead of being silently ignored.
- Cursor leak in `select_rowsource()` and `select_rowdict()`: cursor is now closed on query failure; `EXPORT` and `COPY` explicitly close the row generator on error.

______________________________________________________________________

## [2.16.13] - 2026-05-01

### Added

- `execsql-format`: `--indent` now controls SQL indentation in addition to metacommand indentation.
- `execsql-format`: new `--leading-comma` flag places commas at the start of lines.

### Fixed

- `execsql-format`: comments interleaved within multi-line SQL no longer corrupt the formatted output. Statements are no longer split at comment boundaries (which previously turned commas into semicolons and dropped content silently).
- `execsql-format`: `/* */` block comments containing `-- !x!` metacommand markers are no longer mangled.
- `execsql-format`: blank lines within multi-line SQL no longer split the statement into independent format blocks.
- `execsql-format`: if sqlglot produces more or fewer statements than the input, the formatter falls back to the original text instead of emitting corrupted SQL.

______________________________________________________________________

## [2.16.12] - 2026-05-01

### Changed

- Internal: added parser test coverage for `SHOW SCRIPTS` and default-parameter handling. No user-visible changes.

______________________________________________________________________

## [2.16.11] - 2026-05-01

### Fixed

- Multi-line `/* */` block comment docstrings in `BEGIN SCRIPT` are now captured in full (the doc collector previously classified comment continuation lines as non-comment and stopped early).

______________________________________________________________________

## [2.16.10] - 2026-05-01

### Fixed

- `EXECUTE SCRIPT !!#script_name!!` (variable-substituted script target) now works. The parser regex previously rejected non-literal identifiers, causing dispatch to fail with "should be handled by the AST executor".

______________________________________________________________________

## [2.16.9] - 2026-05-01

### Added

- `SHOW SCRIPTS` metacommand lists all registered SCRIPT definitions with parameter signatures and source locations.
- `SHOW SCRIPT <name>` shows detail for one SCRIPT (parameters, source file/lines, docstring).
- `.scripts` and `.scripts <name>` REPL commands — same as the metacommands.
- Default parameter values: `BEGIN SCRIPT load(schema, table, batch=1000)`. Parameters with defaults can be omitted at the call site. Required parameters must precede optional ones.
- Automatic docstring extraction for SCRIPT blocks. `--` or `/* */` comments immediately after `BEGIN SCRIPT` are captured as documentation; a blank line terminates it. Displayed by `SHOW SCRIPTS`, `SHOW SCRIPT`, and `.scripts`.

______________________________________________________________________

## [2.16.8] - 2026-04-30

### Fixed

- SQL comments (`--` and `/* */`) inside multi-line SQL statements no longer split the statement. Comments between SELECT columns or before CASE clauses are now preserved as part of the statement text.

______________________________________________________________________

## [2.16.7] - 2026-04-30

### Fixed

- `ANDIF`/`ORIF` conditions now short-circuit. `IF (sub_defined(x)) ANDIF (not sub_empty(x))` previously evaluated `sub_empty` even when `sub_defined` returned false, throwing "Unrecognized substitution variable" on undefined variables.
- `IF`, `LOOP`, and `INCLUDE` error reports now show the correct source line instead of the previous command's location.

______________________________________________________________________

## [2.16.6] - 2026-04-30

### Fixed

- `execsql-format` no longer corrupts PL/pgSQL function bodies inside `$$`-delimited blocks. sqlglot was rewriting `IF NOT EXISTS … END IF` and similar PL/pgSQL constructs as `COMMIT;`; the formatter now skips sqlglot for any block containing dollar-quoted content.
- Debug REPL `.vars` now shows `~` local and `#` param variables from the current stack frame, not just globals. `.vars ~myvar` and `.set ~myvar value` also read/write the stack frame's local scope.

______________________________________________________________________

## [2.16.5] - 2026-04-30

### Fixed

- Debug REPL `.vars`, `.set` now read/write `~` local and `#` param variables from the current stack frame instead of globals only.

______________________________________________________________________

## [2.16.4] - 2026-04-30

### Fixed

- Forward references in SCRIPT blocks now work: `EXECUTE SCRIPT foo` can appear before `BEGIN SCRIPT foo` in the same file or `INCLUDE`'d file. The AST executor pre-scans for SCRIPT definitions, matching the legacy engine's two-pass behavior.

______________________________________________________________________

## [2.16.3] - 2026-04-30

### Fixed

- `BEGIN SCRIPT name(params)` without a space before the opening parenthesis now parses correctly. The previous regex required whitespace and silently ignored the SCRIPT block, causing `END SCRIPT` to fail.

______________________________________________________________________

## [2.16.2] - 2026-04-30

### Fixed

- `INCLUDE` with quoted paths (e.g. `-- !x! INCLUDE "!!path!!/file.sql"`) now strips the surrounding quotes before resolving the file path.

______________________________________________________________________

## [2.16.1] - 2026-04-30

### Fixed

- `~` (local) and `+` (outer-scope) substitution variables inside SCRIPT blocks now work correctly. Previously these wrote to a disconnected scope, causing the variable to be invisible to subsequent SQL and producing spurious "potential un-substituted variable" warnings.
- `EXECUTE SCRIPT` argument expressions like `val=!!#parent_param!!` are now expanded in the caller's scope before the child frame is created, fixing nested script calls that pass `~` or `#` variables as arguments.

### Changed

- `RuntimeContext` is now stored in `threading.local()` instead of a module-level global, making concurrent `from execsql import run` calls thread-safe.

______________________________________________________________________

## [2.16.0] - 2026-04-29

### Added

- `--parse-tree` CLI flag — parses a script into an Abstract Syntax Tree and prints a visual tree showing block nesting (`IF`/`LOOP`/`BATCH`/`SCRIPT`), source line ranges, compound conditions, and all metacommands. No database connection required.
- Plugin system (`execsql.plugins`) for extending execsql with custom metacommands, exporters, and importers via Python entry points: `execsql.metacommands`, `execsql.exporters`, `execsql.importers`. Discovered automatically at startup.
- `--list-plugins` CLI flag shows all discovered plugins.
- Python library API: `from execsql import run` for programmatic script execution from notebooks, pipelines, and applications. Returns a `ScriptResult` with success/failure, command count, timing, errors, and final variable state. Supports DSN strings, pre-existing connections, substitution variables, and error control.
- Deprecation warning for `enc_password` in config files — advises switching to keyring or environment variables.
- Sensitive environment variables (`*SECRET*`, `*TOKEN*`, `*PASSWORD*`, etc.) are now filtered from `&`-prefixed substitution variable exposure.

### Changed

- **Execution engine replaced.** The legacy flat command-list engine has been replaced by the AST-based executor. Scripts are parsed into a tree of typed nodes and walked for execution. `INCLUDE`'d files are parsed and executed natively with circular-include detection. Transparent to users.
- **`BREAK` outside `LOOP` is now an error** (exit 1) instead of being silently ignored.
- `--lint` now uses the AST parser for structural validation. Unmatched `IF`/`LOOP`/`BATCH`/`SCRIPT` blocks are caught at parse time with precise line ranges. No database connection required.
- Default database type changed from Access (`-t a`) to SQLite (`-t l`). Users targeting Access should pass `-t a` explicitly.

### Fixed

- \*\*[Critical]\*\* `WriteSpec.write()` and `MailSpec.send()` error-recovery paths crashed because `SubVarSet.substitute_all()` returns `(str, bool)` but callers treated it as a plain string. All 14 call sites fixed.
- **[Critical]** Error-recovery in `WriteSpec.write()` and `io_write` called `.encode()` producing bytes passed to `sys.stdout.write()` which expects `str`.
- SQL injection across all 8 database adapters in `exec_cmd()` — stored procedure / function / view names are now quoted with `quote_identifier()`.
- `DSN` and `SQL Server` adapters no longer encode SQL strings to bytes before execution.
- Database adapters now clear `self.password` after successful connection, reducing credential exposure window.
- `SubVarSet.substitute_all()` enforces a 100-iteration depth limit to prevent infinite loops from cyclic variable references.

### Removed

- `--ast` / `--no-ast` CLI flag — the AST executor is now the only execution engine.
- Legacy flat command-list execution engine and its helpers (`_parse_script_lines`, `read_sqlfile`, `read_sqlstring`, `runscripts`, `ScriptFile`, `CommandListWhileLoop`, `CommandListUntilLoop`).

______________________________________________________________________

## [2.15.11] - 2026-04-27

### Fixed

- `PAUSE` console-mode fallback now checks `sys.platform` before attempting POSIX terminal imports, preventing hangs on Windows when stdin reports as a TTY.

______________________________________________________________________

## [2.15.10] - 2026-04-27

### Added

- `--config FILE` CLI flag specifies an explicit configuration file. Loaded after the implicit search paths (system, user, script-dir, working-dir) so its values take precedence; CLI arguments still override everything.
- `$HOSTNAME` system substitution variable — the network name of the machine running execsql.

### Fixed

- Config file chaining no longer mutates a list during iteration.
- `PAUSE` console mode no longer crashes on Windows CI due to unconditional `import termios`.
- `HAS_ROWS`, `ROW_COUNT_*` condition predicates now quote table names with SQL identifier quoting, preventing injection when table names come from substitution variables.

______________________________________________________________________

## [2.15.9] - 2026-04-27

### Added

- Textual TUI now displays a progress bar and remaining-time countdown for `PROMPT PAUSE` and `PAUSE` dialogs with `CONTINUE AFTER` / `HALT AFTER` (matching existing Tkinter behavior).

### Fixed

- `PAUSE` in console mode (no `-v`) now responds to single keypresses (Enter to continue, Esc to quit) instead of requiring Enter after every key.
- `PAUSE` with `CONTINUE AFTER` / `HALT AFTER` in console mode displays a live SIGALRM-driven progress bar showing time remaining.
- Double minutes-to-seconds conversion in the console `PAUSE` path: a 1-minute pause used to sleep for 60 minutes.

______________________________________________________________________

## [2.15.8] - 2026-04-20

### Added

- `PG_UPSERT` / `PG_UPSERT QA` / `PG_UPSERT CHECK` now support the `STRICT_COLUMNS` keyword. All missing columns in staging tables are treated as errors (not just PK and NOT NULL / no-default columns).
- New `$PG_UPSERT_QA_WARNINGS` substitution variable — comma-separated list of tables with WARNING-level QA findings.

### Changed

- `$PG_UPSERT_RESULT_JSON` now includes a `qa_warnings` array per table.
- Minimum pg-upsert version bumped to `>=1.22.0`.

### Fixed

- `PG_UPSERT QA` and `PG_UPSERT CHECK` now capture all QA findings (errors + warnings) instead of only errors.

______________________________________________________________________

## [2.15.7] - 2026-04-20

### Fixed

- `CounterVars.substitute` now correctly searches the full string. `re.I` was mistakenly passed as the `pos` argument to `re.search`, skipping the first two characters of every input.
- SQL injection in MySQL `LOAD DATA INFILE`: file path, field delimiter, and quote character are now escaped before being interpolated into SQL.
- SQLite and DuckDB `exec_cmd` no longer encodes the SQL string to bytes before passing to `execute()` (always raised `TypeError` in Python 3).
- Cursor leaks across all database adapters — call sites that manually opened cursors now use the `with self._cursor()` context manager.
- Config file chaining is now capped at 20 files to prevent infinite loops from `config_file` cycles.
- `TempFileMgr` now uses `tempfile.mkstemp()` instead of `NamedTemporaryFile().name`, eliminating a TOCTOU race.
- JSON export serializes column names with `json.dumps()` (previously bare f-string interpolation broke on column names with quotes or backslashes).
- PostgreSQL `VACUUM` autocommit session state is restored in a `finally` block.
- HTML export now HTML-escapes the description, author, and CSS href meta tag values.
- `shlex.split` on Windows now uses `posix=False` instead of pre-escaping backslashes.
- MySQL adapter no longer coerces `None` arguments to the string `"None"` for `server_name`, `db_name`, `user_name`.

______________________________________________________________________

## [2.15.6] - 2026-04-16

### Fixed

- Nested substitution variable names (e.g. `!!N_!!CHECK_GROUP!!_CHECKS!!`) now resolve correctly. The single-pass token regex introduced in 2.15.0 could not find inner `!!var!!` tokens embedded in an outer variable name.

______________________________________________________________________

## [2.15.5] - 2026-04-15

### Fixed

- `DT_Timestamp` type inference no longer claims time-only values like `13:15:45`. `dateutil.parser.parse()` silently filled in today's date for bare time strings, generating PostgreSQL `InvalidDatetimeFormat` errors on CSV import.

______________________________________________________________________

## [2.15.4] - 2026-04-15

### Fixed

- Test data encoding typo causing assertion failure on Windows CI.

______________________________________________________________________

## [2.15.3] - 2026-04-15

### Added

- Optional dependency extras `auth-plaintext` and `auth-encrypted` for headless Linux keyring backends. `pip install execsql2[auth-plaintext]` installs `keyring` + `keyrings.alt`; `[auth-encrypted]` adds `pycryptodome` for the encrypted file backend.

______________________________________________________________________

## [2.15.2] - 2026-04-14

### Changed

- Performance: `DT_Integer`, `DT_Float`, `DT_Decimal`, `DT_Boolean` matchers now use pre-compiled regex / cached match tuples instead of rebuilding on every call — reduces overhead during large imports.

### Fixed

- `DT_Text.data_type_name` corrected from `"character"` to `"text"` — error messages now identify the text type correctly.
- `DT_Varchar._from_data()` now converts non-string data to string and enforces the 255-character length limit.
- `CondAstNode.eval()` now raises `CondParserError` for unknown node types instead of silently returning `None`.
- `NumericAstNode.eval()` now raises `NumericParserError` on division by zero instead of an unhandled `ZeroDivisionError`.

______________________________________________________________________

## [2.15.1] - 2026-04-14

### Added

- Cell-level diff marking in `PROMPT COMPARE` — when "Highlight Diffs" is toggled, differing cells within changed rows are prefixed with a bullet marker. Works across all three backends.
- `macos_config_file` option in `execsql.conf` `[config]` section — additional config file to read on macOS, mirroring `linux_config_file`.
- `EXPORT` operations now log structured `action` records with query name, output file, and source line number.

### Changed

- `linux_config_file` now only applies on Linux (`sys.platform == "linux"`), not all POSIX. macOS users should use the new `macos_config_file` option.
- Date/time parsing now uses `python-dateutil` instead of 231 hardcoded `strptime` format strings. Handles ISO 8601 with `T` separator, microseconds, `Z` suffix, and named timezones.

### Removed

- `constants.py` — 370 lines of map tile servers, XBM bitmaps, and X11 color names never imported anywhere. Vestigial from upstream.
- `Tz` class in `types.py` — custom `tzinfo` subclass orphaned by the `python-dateutil` migration.

### Fixed

- `NumericParser` now uses left-associative parsing. Previously `10 - 3 - 2` evaluated as `10 - (3 - 2) = 9` instead of `5`. Same fix for division.
- SQLite `populate_table()` now applies `trim_strings`, `replace_newlines`, and `empty_strings` processing before extracting column data (previously processing was applied after the insert data was copied, so it never took effect).
- `$CURRENT_DATABASE` and `$CURRENT_DBMS` system variables now refresh on `USE` (previously stale after switching databases).
- `PROMPT COMPARE` diff logic now uses native Python equality instead of string comparison — `int(1)` vs `float(1.0)`, `Decimal("10.00")` vs `Decimal("10.0")`, and `True` vs `1` are correctly treated as equal.
- `PROMPT COMPARE` treats `None` (SQL NULL) as distinct from `""`. Summary stats now match by column name, exclude key columns from the diff, and keep the first row when duplicate PK values exist.
- `PG_UPSERT` no longer writes pg-upsert output to `execsql.log`. Output goes only to the file specified by `LOGFILE`.
- `win_config_file` now works on Windows. Previously checked `os.name == "windows"` (Python returns `"nt"`).

______________________________________________________________________

## [2.15.0] - 2026-04-09

### Added

- `PG_UPSERT` "fix sheet" export: new `EXPORT_FAILURES <dir>`, `EXPORT_FORMAT csv|json|xlsx`, and `EXPORT_MAX_ROWS <n>` keywords write failing QA rows (one per unique violating staging row, with a consolidated `_issues` column) to CSV, JSON, or XLSX. Works in all three modes (full pipeline, QA-only, schema check) and runs even when QA fails. New `$PG_UPSERT_EXPORT_PATH` substitution variable holds the directory written.

### Changed

- `[upsert]` extra now requires `pg-upsert>=1.21.0` (up from `>=1.20.0`) for the fix-sheet feature.

### Fixed

- `PROMPT MESSAGE … CREDENTIALS <user_var> <pw_var>` no longer crashes in console-fallback mode. The fallback now uses `getpass.getpass()` for the password.

______________________________________________________________________

## [2.14.1] - 2026-04-07

### Fixed

- Windows CI: use `zf.namelist()[0]` instead of path for zip entry lookup.

______________________________________________________________________

## [2.14.0] - 2026-04-07

### Added

- Row count footer in all GUI dialog tables (Textual TUI, Tkinter desktop, console fallback). Format: "3 rows" / "1 row" with thousands separators.
- Help URL button in all GUI dialogs that support the `HELP` keyword.
- Diff summary line in compare dialogs ("3 matching | 1 differing | 2 only in Table 1").
- `PROMPT ENTRY_FORM` now enforces `validation_regex` (on submit) and `validation_key_regex` (per-keystroke). Required fields are validated on submit. Tkinter shows a messagebox, Textual shows a notification, console re-prompts.
- "Highlight Diffs" toggle in compare dialogs color-codes rows: green for matching, yellow for changed, red for rows only in one table.

### Fixed

- `CONFIG GUI_LEVEL` now accepts value `3` (open GUI console on start), matching the `gui_level` config file setting.
- `PROMPT COMPARE` now respects `AND` vs `BESIDE`: `AND` stacks tables vertically, `BESIDE` displays side-by-side. Previously both were side-by-side.
- `PROMPT ENTRY_FORM` now renders all documented `entry_type` values: `listbox`, `radiobuttons`, `textarea`, `inputfile`, `outputfile`. Previously only `checkbox` and `dropdown`/`select` were implemented.
- `PROMPT ENTER_SUB` HELP URL regex now correctly matches URLs containing `+` characters.
- PostgreSQL and DSN `CONNECT` handlers now unquote the `PASSWORD` parameter consistently with other database handlers.

### Removed

- `FREE` keyword from `PROMPT DISPLAY` — the non-blocking display behavior was only implemented in the console backend.

______________________________________________________________________

## [2.13.2] - 2026-04-06

### Changed

- `--lint` static analysis improvements:
    - `SUB_EMPTY`, `SUB_ADD`, `SUB_APPEND`, and `SUBDATA` now register as variable definitions (eliminates false undefined-variable warnings).
    - Descends into `EXECUTE SCRIPT` / `EXEC SCRIPT` / `RUN SCRIPT` so variables defined inside are visible to the caller.
    - Two-pass variable collection — definition order no longer matters.
    - Reads `SUB_INI` INI files and registers section keys as defined variables.
    - Warns when `EXECUTE SCRIPT` targets a non-existent script block (respects `IF EXISTS`).
    - Sorts errors before warnings, both by line number; padded location columns for alignment.

______________________________________________________________________

## [2.13.1] - 2026-04-04

### Changed

- Bump pg-upsert minimum to `>=1.20.0`.

______________________________________________________________________

## [2.13.0] - 2026-04-04

### Added

- `IMPORT … FROM JSON` metacommand — imports a JSON array of objects or [JSON Lines](https://jsonlines.org/) file into a database table. Nested objects are flattened with dot-separated column names; nested arrays are stored as JSON strings. Missing keys become NULL.
- `SHELL … CONTINUE` now sets `$SYSTEM_CMD_PID` with the PID of the background process.

### Fixed

- `Mailer`, `WriteableZipfile`, `ZipWriter` now support the context manager protocol (`with` statement) for reliable resource cleanup.
- `FileWriter`, `FileControl`, `Mailer`, `WriteableZipfile`, `ZipWriter` `__del__` methods no longer raise during interpreter shutdown.

______________________________________________________________________

## [2.12.7] - 2026-04-03

### Fixed

- Bump pg-upsert minimum to `>=1.18.2` — fixes the interactive FK check dialog showing only 1 violation row instead of all rows.

______________________________________________________________________

## [2.12.6] - 2026-04-03

### Added

- `PG_UPSERT` now supports per-table progress via pg-upsert's callback API. New substitution variables `$PG_UPSERT_CURRENT_TABLE`, `$PG_UPSERT_TABLE_QA_PASSED`, `$PG_UPSERT_TABLE_ROWS_UPDATED`, `$PG_UPSERT_TABLE_ROWS_INSERTED` are updated as each table is processed.
- New `CLEANUP` keyword for `PG_UPSERT` — drops all `ups_*` temporary tables and views after execution. Without it, temp objects persist for inspection (default).

______________________________________________________________________

## [2.12.5] - 2026-04-03

### Fixed

- CLI test fixture: handle CliRunner's separate stderr capture.

______________________________________________________________________

## [2.12.4] - 2026-04-03

### Added

- New `PG_UPSERT` metacommand for QA-checked, FK-dependency-ordered upserts from a staging schema to a base schema on PostgreSQL. Integrates [pg-upsert](https://pg-upsert.readthedocs.io/) as an optional dependency (`pip install execsql2[upsert]`). Three modes: full pipeline (`PG_UPSERT FROM … TO … TABLES …`), QA-only (`PG_UPSERT QA …`), and schema check (`PG_UPSERT CHECK …`). Supports `METHOD`, `COMMIT`, `INTERACTIVE`, `COMPACT`, `EXCLUDE`, `EXCLUDE_NULL`, `LOGFILE` keywords. Sets 12 `$PG_UPSERT_*` substitution variables.

______________________________________________________________________

## [2.12.3] - 2026-04-02

### Changed

- Performance: `set_system_vars()` split into static (once per script + on `CONNECT`/`CHDIR`) and dynamic (per statement) — eliminates ~14 redundant calls per statement.
- Performance: `$RANDOM` and `$UUID` are now lazy — computed only when referenced.
- Performance: CSV/TSV import uses Python's `csv` module as a fast path for standard delimited formats (comma, tab, semicolon, pipe). Falls back to the character-at-a-time parser for non-standard formats.

______________________________________________________________________

## [2.12.2] - 2026-04-02

### Added

- Keyring setup guide for headless Linux servers (encrypted and plaintext file backends) in the Security reference.

### Changed

- `ASSERT` failures now report `**** Assertion failed.` instead of `**** Error in metacommand.` to distinguish intentional script-level checks from metacommand errors.

______________________________________________________________________

## [2.12.1] - 2026-04-02

### Changed

- Performance: cached source paths on `ScriptCmd` (eliminates per-statement `Path.resolve()` calls); batched `fetchmany()` in `select_rowdict()`; removed dead regex compilation.

### Fixed

- Cursor leak in `select_rowsource()` — generator now closes the cursor in a `finally` block.

______________________________________________________________________

## [2.12.0] - 2026-04-01

### Added

- Debug REPL `.where` / `.w` — shows current script file, line number, and the upcoming statement text (truncated to 120 chars). The entry banner now includes the location (`[Breakpoint] myscript.sql:42`).
- Debug REPL `.set VAR VAL` — sets or updates a substitution variable interactively during a `BREAKPOINT` session.
- Debug REPL ANSI color output. Auto-detected via TTY; suppressed by `NO_COLOR` / `EXECSQL_NO_COLOR`.
- Debug REPL aliases: `.h` for `.help`, `.v` for `.vars`, `.v all` for `.vars all`.
- Debug REPL step mode banner — shows "Step" instead of "Breakpoint" when re-entering via `.next`.
- `--profile-limit N` CLI option — controls how many top statements appear in the `--profile` timing summary (default: 20).

### Changed

- `execsql.debug.repl` is now a dedicated package (`src/execsql/debug/repl.py`); previously at `execsql.metacommands.debug_repl`. No public API change.

______________________________________________________________________

## [2.11.1] - 2026-04-01

### Fixed

- `x_assert` crash when `exec_log` is `None`.
- `--ping` version-query loop exiting prematurely — `break` was at wrong indentation, skipping fallback queries.
- `CONSOLE SET WIDTH/HEIGHT` crash — `gui_console_width()`/`gui_console_height()` restored as setter functions.
- `$ERROR_MESSAGE` now contains full `errmsg()` (with script location and timestamp) for non-halting errors.
- Non-halting SQL and metacommand errors now logged to `exec_log`.
- YAML `append=True` now emits `---` document separator for valid multi-document streams.

______________________________________________________________________

## [2.11.0] - 2026-04-01

### Added

- `--debug` CLI flag — starts the script in step-through debug mode. The debug REPL pauses before each statement, as if `BREAKPOINT` were inserted at the top with `.next` always active.

### Changed

- `BREAKPOINT` debug REPL now pauses **before** each statement instead of after, so the upcoming statement can be inspected before it runs.

### Fixed

- `BREAKPOINT` REPL no longer wraps variable values in extra single quotes.
- Error messages now include script file name and line number — `ErrInfo` fields `script_file` and `script_line_no` are populated in all error paths.
- `$ERROR_MESSAGE` is now updated on every error (was initialized once to `""` and never changed).
- `MetacommandStmt.run()` now re-raises the original handler `ErrInfo` when `halt_on_metacommand_err` is True, instead of raising a generic "Unknown metacommand".
- `write_warning()` now accepts `always=True` to bypass the `conf.write_warnings` gate, so structural warnings (IF-level mismatch, unsubstituted variables) are always visible on stderr.

______________________________________________________________________

## [2.10.1] - 2026-04-01

### Fixed

- `BREAKPOINT` variable lookup — `$logfile` was showing `(undefined)` because `SUB` stores keys without a sigil prefix. The debug REPL now strips `$`, `&`, `@`, `#`, `~` prefixes and retries when the exact name isn't found.

______________________________________________________________________

## [2.10.0] - 2026-04-01

### Added

- **`BREAKPOINT` metacommand** — pauses script execution and drops into an interactive debug REPL. Accepts `continue`/`c` to resume, `abort`/`q` to halt, `vars` to list substitution variables, `$VARNAME` to print a single variable, `SELECT …;` to run ad-hoc SQL, `next`/`n` to step one statement at a time, `stack` to inspect the command-list stack, `help` for a summary. Silently skipped in non-TTY environments (CI, piped input).
- **`ROW_COUNT_GT(table, N)`**, **`ROW_COUNT_GTE`**, **`ROW_COUNT_EQ`**, **`ROW_COUNT_LT`** conditional tests — compare row count of any table or view against an integer threshold using `IF`, `ELSEIF`, `ASSERT`. Issues `SELECT count(*)`.

______________________________________________________________________

## [2.9.0] - 2026-04-01

### Added

- **`--lint` flag** — parses a script and performs static analysis without connecting to a database. Reports unmatched `IF`/`ENDIF`, `LOOP`/`END LOOP`, `BEGIN BATCH`/`END BATCH` as errors; potentially undefined `!!$VAR!!` references and missing `INCLUDE` targets as warnings. Exits 0 if no errors are found (warnings don't affect exit code); exits 1 on any error.
- **`--ping` flag** — tests database connectivity without running a script. `execsql --ping --dsn <URL>` connects, queries the server version, prints a one-line summary, exits 0. No script file required.

______________________________________________________________________

## [2.8.0] - 2026-04-01

### Added

- **`--profile` flag** — records wall-clock time for each SQL and metacommand statement and prints a timing summary after the script completes. Sorted by elapsed time descending (top 20).
- **`ASSERT` metacommand** — evaluates any `IF`-compatible condition and raises an error (halting the script when `HALT_ON_METACOMMAND_ERROR` is `ON`) if false. Optional quoted failure message; omitting it produces `Assertion failed: <condition>`. Silently skipped inside a false `IF` block.

### Changed

- **`--dry-run` expands substitution variables** — the printed command list now shows resolved `!!$VAR!!` tokens for variables already populated at parse time (environment, `--assign-arg`, config, startup built-ins). Variables set during execution remain unexpanded.

______________________________________________________________________

## [2.7.1] - 2026-04-01

### Fixed

- `AttributeError: module 'execsql.state' has no attribute 'dedup_words'` when importing CSV with `DEDUP_COL_HDRS` enabled.

______________________________________________________________________

## [2.7.0] - 2026-04-01

### Added

- **Markdown export** (`FORMAT MARKDOWN` / `FORMAT MD`) — GitHub-flavored pipe tables with column alignment and pipe/backslash escaping. No dependencies.
- **YAML export** (`FORMAT YAML`) — list-of-dicts output with native type preservation. Requires `PyYAML` (in `formats` extra).
- **XLSX export** (`FORMAT XLSX`) — single-sheet and multi-sheet Excel via openpyxl, with bold headers, native type preservation, and a "Datasheets" inventory sheet. Multi-sheet syntax: `EXPORT table1, table2 TO file.xlsx AS XLSX`.

______________________________________________________________________

## [2.6.0] - 2026-04-01

### Added

- Textual TUI `console_save()` — writes console output to a file, matching Tkinter parity.
- Keyboard shortcut hints on all major Textual TUI dialog screens (Escape to cancel, Enter to submit, `Footer` widget).
- `RuntimeContext` class in `state.py` — groups all 33 mutable runtime globals into a single slotted object, enabling isolated contexts for testing and future concurrent execution.
- `get_context()` / `set_context()` public API for programmatic access to the active runtime context.
- Divergence from Upstream documentation page (`docs/about/divergence.md`).

### Changed

- `state.py` now uses a `types.ModuleType` subclass that transparently proxies attribute reads/writes to the active `RuntimeContext`. All existing `_state.foo` call sites continue working unchanged.

______________________________________________________________________

## [2.5.0] - 2026-04-01

### Added

- Docstrings on 183 public API symbols across `db/`, `exporters/`, `importers/`, `config.py`, `models.py`, `types.py`, `parser.py`. Public API coverage raised from 40% to 81%.
- Developer architecture guide (`docs/dev/architecture.md`) with Mermaid diagrams covering execution flow, module map, command stack, metacommand dispatch, conditionals, substitution variables, database abstraction, export/import, GUI, and global state.
- Exporter `Protocol` types (`QueryExporter`, `RowsetExporter`) in `exporters/protocol.py`.

### Changed

- Cursor lifecycle in database adapters — all `exec_cmd()` and PostgreSQL `vacuum()` now use the `_cursor()` context manager to prevent leaks.

______________________________________________________________________

## [2.4.6] - 2026-03-31

### Added

- End-to-end CLI tests (26 tests) covering `--version`, `--help`, `--dump-keywords`, `-c`, file execution, `--dry-run`, error cases, and `execsql-format`.
- Exception chaining (`from None`) on all `raise` statements inside `except` blocks; ruff rule B904 enabled.

### Changed

- Documentation reorganized into nav-aligned subdirectories: `getting-started/`, `reference/`, `guides/`, `about/`. All 306 cross-references updated.

______________________________________________________________________

## [2.4.5] - 2026-03-31

### Added

- VS Code syntax highlighting section in the README.
- Pre-commit hook usage in the README formatting section.

### Fixed

- `ON ERROR_HALT EXECUTE SCRIPT` and `ON CANCEL_HALT EXECUTE SCRIPT` were not recognized — handlers existed but dispatch patterns were missing.
- `EXTEND SCRIPT <X> WITH SCRIPT <Y>` was not recognized — only the `APPEND SCRIPT` synonym was ported.
- `PROMPT ASK` with single-quoted (`'…'`) or bracket-delimited (`[…]`) questions, and with unquoted `HELP` arguments, were not recognized.
- `CONNECT TO SQLSERVER` with mixed quoting (e.g. quoted SERVER + unquoted DB) or quoted PASSWORD was not recognized.

______________________________________________________________________

## [2.4.4] - 2026-03-30

### Fixed

- PyPI publish URL — use `execsql2` package name instead of repo name.
- SQLite import-error test: patch `fatal_error` before `__import__`.

______________________________________________________________________

## [2.4.3] - 2026-03-30

### Added

- Pre-commit hook for `execsql-format` — add the repo to `.pre-commit-config.yaml` and pass `--check` or `--in-place` via `args`.

______________________________________________________________________

## [2.4.2] - 2026-03-30

### Changed

- Internal: raised test coverage floor 75 → 80%. No user-visible changes.

______________________________________________________________________

## [2.4.1] - 2026-03-30

### Fixed

- `--dsn` now correctly overrides connection settings from configuration files.
- MySQL `LOAD DATA INFILE` encoding — Python encoding names (e.g. `utf-8`) are now mapped to MySQL charset names (e.g. `utf8mb4`).
- Importer error reporting: replaced removed `exception_info()` with `exception_desc()`.

### Changed

- Integration tests moved to `tests/integration/` with a shared conftest and parallel CI execution.

______________________________________________________________________

## [2.4.0] - 2026-03-30

### Added

- Python 3.14 support — added to CI matrix and PyPI classifiers.
- PostgreSQL integration tests (9 tests) — full lifecycle via `--dsn` connection strings.
- MySQL/MariaDB integration tests (9 tests, 1 xfail for a pre-existing import adapter bug).
- CI integration test job with GitHub Actions services (PostgreSQL 16, MySQL 8).

### Changed

- `Database` is now an abstract base class (ABC) with `open_db()` and `exec_cmd()` as `@abstractmethod`. Subclasses missing either raise `TypeError` at instantiation time instead of `DatabaseNotImplementedError` at call time.
- Cursor lifecycle: `execute()`, `select_data()`, `schema_exists()`, `table_exists()`, `column_exists()`, `table_columns()`, `view_exists()`, `import_entire_file()` now use a context manager that guarantees cleanup.
- Metacommand dispatch uses keyword-indexed lookup, reducing dispatch from O(205) regex scans to O(K) where K ≈ 1–5.
- Variable substitution uses a single combined regex to find tokens in one pass, then dict lookup for the value — reducing `substitute()` from O(V) to O(1) per call.

### Fixed

- ODS import/export — `import odf as of` was previously `import of as of`. ODS support was broken since the modular refactor.
- `--dsn` password is now passed through to all database backends (MySQL, SQL Server, Oracle, Firebird, DSN). Previously only PostgreSQL received it.
- Importer error reporting: `exception_info()` (tuple) replaced with `exception_desc()` (string) in 6 call sites. Previously caused `AttributeError: 'tuple' has no attribute 'replace'` on any import failure.
- MySQL `LOAD DATA LOCAL INFILE` encoding name mapping (Python encoding → MySQL charset).
- `--dsn` now overrides conf-file connection settings (server, database, user, port). Previously conf-file values took precedence.

______________________________________________________________________

## [2.3.0] - 2026-03-30

### Added

- Security documentation (`docs/security.md`) covering trust model, SHELL execution, credential handling, file system access, SMTP, and SQL variable substitution.

### Fixed

- Plaintext passwords (`Pwd=***`) redacted from ODBC connection strings in log output for Access and SQL Server adapters.

### Changed

- Removed lazy-import anti-pattern from 6 modules — stdlib imports moved to module level; optional deps (`xlrd`, `openpyxl`, `jinja2`) use instance attributes instead of `global`.

______________________________________________________________________

## [2.2.1] - 2026-03-26

### Fixed

- Skip `TimerHandler` alarm tests on Windows where `signal.setitimer` is unavailable.
- `UnicodeDecodeError` in CLI subprocess tests on Windows — specify UTF-8 encoding.

______________________________________________________________________

## [2.2.0] - 2026-03-26

### Added

- `py.typed` marker for PEP 561 downstream type checking.
- `--progress` CLI flag and `CONFIG SHOW_PROGRESS` metacommand — Rich progress bar during long `IMPORT` operations. Also configurable via `show_progress` in `execsql.conf`.
- `log_sql` config option and `CONFIG LOG_SQL` metacommand — opt-in SQL query audit logging. All executed statements written to the log with a `sql` record type, database name, line number, and query text.
- `--dump-keywords` CLI option — outputs all metacommand keywords, conditional functions, config options, export formats, database types, and variable patterns as structured JSON. Enables tooling (e.g. editor grammar generators) to consume keyword data directly from the dispatch table.
- VS Code syntax highlighting extension at `extras/vscode-execsql/`. The grammar is auto-generated from the dispatch table via `just generate-vscode-grammar`.
- Keyring credential storage documentation in the usage notes.

### Changed

- CLI reorganized from flat `_cli_*.py` files into a `cli/` subpackage (`cli/__init__.py`, `cli/run.py`, `cli/dsn.py`, `cli/help.py`). All existing `from execsql.cli import …` paths preserved.
- Exception hierarchy: `ErrInfo`, `DataTypeError`, `DbTypeError`, `DatabaseNotImplementedError` now inherit from `ExecSqlError`.
- Exception chaining: `from e` added to 115 `raise` statements across 38 files.
- `metacommands/io.py` (1304 lines) split into `io_export.py`, `io_import.py`, `io_write.py`, `io_fileops.py`. All existing import paths preserved.

### Fixed

- ODS export/import was completely broken when `odfpy` was installed — `import odf as of` was previously `import of as of`.
- File-handle leaks in many exporters and metacommands — `try/finally` added to guarantee close on error in `exporters/raw.py`, `xml.py`, `json.py`, `templates.py`, `values.py`, `pretty.py`, `html.py`, `latex.py`, and `metacommands/debug.py`, `control.py`, `prompt.py`.
- XML export injection: cell values are now escaped via `xml.sax.saxutils.escape()`; column headers and table names used as XML element names have invalid characters replaced with underscores.
- HTML export XSS: column headers and cell values are now escaped via `html.escape()`.
- JSON export injection: descriptions and column names are now serialized with `json.dumps()`.
- Jinja2 template injection: `templates.py` now uses `jinja2.sandbox.SandboxedEnvironment`.
- SQL injection in metadata queries: `role_exists()`, `schema_exists()`, `table_exists()`, `column_exists()`, `table_columns()`, `view_exists()` across all adapters now use parameterized queries or `quote_identifier()` for SQL identifiers.
- SQL injection in `import_entire_file()` across 6 database backends — the `column_name` parameter is now quoted with `quote_identifier()`.
- SQL injection in PostgreSQL `create_db()` — database name and encoding now use `quote_identifier()`; COPY delimiter and quote character are escaped/validated.
- HTTP header injection in `SERVE` metacommand — `Content-Disposition` filename is sanitized (newlines/CRs stripped, quotes escaped).
- `$SHEETS_TABLES_VALUES` SQL injection: ODS/XLS sheet names are now escaped (single quotes doubled) before embedding in SQL.
- CPU busy-loop in `utils/fileio.py`: `FileWriter.run()` now uses blocking `queue.get(timeout=0.1)` instead of `get_nowait()` in a tight loop.
- Substitution variable cycle detection — `substitute_vars()` enforces a 100-iteration cap.
- Empty `dt_cast` type-cast mapping in `Database` base class — the monolith populated this with 8 type converters; the refactored version was initialized to `{}`. Now lazily populated on first access.
- `WriteSpec.write()` file-descriptor leak in `exporters/base.py`: `EncodedFile(...).open("a").write(msg)` was opening and discarding the handle without closing.
- Missing `PARQUET` in EXPORT format regex — `EXPORT … AS PARQUET` was unreachable despite the handler existing.
- `CONNECT TO DSN` was unreachable — the `x_connect_dsn` handler was imported but never registered with `mcl.add()`.
- Missing WRITE metacommand delimiter patterns (tilde, hash, backtick, bracket, single-quote) and bare (non-CONFIG) settings aliases that were present in the monolith.
- Backward-compatible `TXT-AND` / `TEXT-AND` export format aliases.

______________________________________________________________________

## [2.1.2] - 2026-03-25

### Added

- DuckDB integration tests (15 end-to-end tests) covering basic SQL, substitution variables, CSV export/import, conditionals, `WRITE`, round-trip, and DuckDB-specific features (views, schemas, native types).

### Fixed

- Config parser now accepts `k` (DuckDB) as a valid `db_type` in `execsql.conf`. Previously only the CLI flag `-t k` worked.
- Read the Docs build: added `mkdocstrings-python` and editable project install so `mkdocstrings` resolves API references.

______________________________________________________________________

## [2.1.1] - 2026-03-25

### Added

- Keyring credential retry on auth failure — when a keyring-stored password is rejected, the stale entry is auto-deleted, the user is re-prompted for the current password, the connection is retried, and the new password is saved. Applies to all database adapters. New public helpers `password_from_keyring()`, `clear_stored_password()`, and `skip_keyring` parameter on `get_password()`.
- Security warning in `docs/substitution_vars.md` about environment variable exposure via `&`-prefixed substitution variables, with mitigation guidance.
- Automatic changelog versioning on `bump-my-version` — `CHANGELOG.md` is now bumpversion-managed (the `[Unreleased]` section is replaced with a dated heading and a fresh `[Unreleased]` is preserved).

### Fixed

- `ExecSqlTimeoutError` now inherits from `ExecSqlError` instead of `Exception`, so generic `except ExecSqlError` handlers catch timeouts. Accepts an optional message (defaults to "Operation timed out").
- ODS import/export was silently non-functional — `import odf as of` was previously `import of as of`.
- Python 3.10 compatibility: replaced `datetime.UTC` (3.11+) with `datetime.timezone.utc`.
- SQLite connection leaks: `state.reset()` now calls `dbs.closeall()` before discarding the `DatabasePool`; `export_sqlite()` uses `try/finally` to guarantee close on error.

______________________________________________________________________

## [2.1.0]

### Added

- `--dsn` / `--connection-string` CLI option — accepts a standard database URL (e.g. `postgresql://user:pass@host:5432/db`) and populates connection parameters automatically. Supported schemes: `postgresql`, `postgres`, `mysql`, `mariadb`, `mssql`, `sqlserver`, `oracle`, `firebird`, `sqlite`, `duckdb`. Overrides `-t`/`-u`/`-p` and positional server/db arguments.
- `--dry-run` output now displays multi-line SQL statements and metacommands with proper indentation, showing continuation lines aligned under the first line instead of truncating or wrapping text.
- `--output-dir DIR` CLI option — sets a default base directory for `EXPORT` output files. Relative paths in `EXPORT` are joined to this directory; absolute paths and `stdout` are unaffected.
- Feather, Parquet, and HDF5 export support (via `polars` / `tables`, included in the `formats` extra).
- OS keyring integration for database password storage (`utils/auth.py`) — when `keyring` is installed, `get_password()` checks the OS credential store (macOS Keychain, Windows Credential Manager, Linux SecretService) before prompting. Controlled by `use_keyring` config option (default `yes`). Requires the `auth` extra.
- `max_log_size_mb` config setting (default `0` = disabled) — when positive, the log file is rotated to `.1` before each new run if it exceeds the threshold.
- `import_progress_interval` config option — logs a status line every N rows during `IMPORT` operations. `0` = silent (default). A final completion line is also written.
- Per-event ISO 8601 timestamps in log records (`status`, `connect`, `action`, `user_msg`).
- Run duration in the `exit` log record (elapsed wall-clock time as the last field).
- Run ID millisecond precision: format changed from `%Y%m%d_%H%M_%S` to `%Y%m%d_%H%M_%S_NNN` to prevent collisions.
- API reference section in the docs (`docs/api/`) covering `cli`, `db`, `exporters`, `importers`, `metacommands`.
- `ExecSqlError` base class in `exceptions.py` — `ConfigError`, `ColumnError`, `DataTableError`, `OdsFileError`, `XlsFileError`, `XlsxFileError`, `ConsoleUIError`, `CondParserError`, and `NumericParserError` now inherit from it.

### Changed

- Consolidated optional dependency extras: replaced `ods`, `excel`, `jinja`, `feather`, `parquet`, `hdf5` extras with a single `formats` bundle. Renamed `keyring` extra to `auth`. Added `all-db` convenience group for all database drivers.
- Replaced `os.path` calls with `pathlib.Path` equivalents across 21 source files. `os.path.expandvars()` is retained where used (no `pathlib` equivalent).
- `SubVarSet` refactored: internal storage changed from list-of-tuples to dict for O(1) lookups; regex patterns pre-compiled on `add_substitution()` instead of recompiled on every `substitute()` call.
- `PostgresDatabase` and `SQLiteDatabase` now accept connection timeout parameters (default 30s); `Database.quote_identifier()` added for safe SQL identifier quoting.
- `utils/crypto.py`: added prominent security warnings to module and `Encrypt` class docstrings documenting that XOR "encryption" is obfuscation only.

### Fixed

- `IMPORT` completion log message is now always written when a log is active, regardless of `import_progress_interval`. Previously the completion record was suppressed in silent mode, leaving no trace of successful imports.
- `Logger.exit_type` defaults to `"unknown"` instead of `None` — prevents the literal string `"None"` from appearing in the `exit` log record.
- SQL injection in `schema_exists()`, `table_exists()`, `column_exists()`, `table_columns()`, `view_exists()`, `role_exists()` across `db/base.py`, `db/postgres.py`, `db/oracle.py`, `db/duckdb.py`, `db/sqlite.py` — now uses parameterized queries and `quote_identifier()`.
- `config.py`: five misnamed attribute writes (`only_strings`, `fold_column_headers`, `replace_newlines`, `import_row_buffer`, `css_styles`) all wrote to the wrong target.
- `models.py`: missing opening `[` in `replace_newlines` regex pattern; `column_type()` referenced undefined `ac.maxlen` for all-NULL columns.
- DuckDB temporal type mappings (`DT_TimestampTZ`, `DT_Timestamp`, `DT_Date`, `DT_Time`) now use native DuckDB types (`TIMESTAMPTZ`, `TIMESTAMP`, `DATE`, `TIME`) instead of `TEXT`.

### Removed

- `AirspeedTemplateReport` and `FORMAT airspeed` template export variant. The Airspeed library has been unmaintained since ~2018. Use `FORMAT jinja` instead.

______________________________________________________________________

## [2.0.1] - 2026-03-23

### Fixed

- Windows `PermissionError` when exporting to HTML in append mode — the file descriptor from `tempfile.mkstemp()` is now closed before the file is opened for writing.
- Windows `PermissionError` when exporting to LaTeX — the file descriptor from `tempfile.mkstemp()` is now closed before `EncodedFile` opens the same path.

______________________________________________________________________

## [2.0.0] - 2026-03-23

### Changed

- Forked from execsql by R.Dreas Nielsen; repackaged as execsql2.
- Added support for Python 3.10, 3.11, 3.12, 3.13; dropped Python 2 compatibility.
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
