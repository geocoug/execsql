# Codebase Audit — execsql2

**Original audit:** 2026-04-13
**Last updated:** 2026-04-29

______________________________________________________________________

## Architecture & Code Quality

### F3. [HIGH] Global mutable state blocks threading and library API

`src/execsql/state.py` — `_ctx` is a plain module-level global. All 200+ metacommand
handlers, SQL execution, variable substitution, and the IF-stack go through `_state.foo` which
resolves to `_ctx.foo`. Two threads executing scripts simultaneously will corrupt each other's
state. Blocks the planned PARALLEL metacommand and safe concurrent `from execsql import run`
usage.

**Fix:** Replace `_ctx` with `contextvars.ContextVar` or `threading.local()`.

### F4. [HIGH] `_run()` is a 460-line god-function with 36 parameters

`src/execsql/cli/run.py` — Performs config parsing, CLI argument merging, DSN parsing,
database connection, GUI init, script loading, dry-run, AST execution, profiling, and cleanup
in a single function. Estimated cyclomatic complexity ~85-90. Untestable as a unit.

**Fix:** Extract into phases: `_setup_config()`, `_connect_db()`, `_load_script()`,
`_execute()`, `_teardown()`.

### F19. [MEDIUM] 51 near-duplicate regex patterns in conditions.py

`src/execsql/metacommands/conditions.py` — `CONTAINS`, `STARTS_WITH`, `ENDS_WITH` each
register 17 quoting variants as separate regex patterns. Adding a new string predicate requires
copying and modifying 17 patterns.

**Fix:** Consolidate into a single pattern per predicate with optional quoting alternation groups.

### CQ-1. [MEDIUM] 111 bare `except Exception` clauses across 38 files

Many suppress errors silently (`pass`). Notable: `db/base.py` (14), `utils/fileio.py` (9),
`db/access.py` (10). Each should be reviewed for more specific exception types.

### CQ-4. [MEDIUM] Inconsistent `_cursor()` context manager vs bare `cursor()`

The `Database` base class provides `_cursor()` for cleanup, but many adapter methods still use
`curs = self.cursor()` without cleanup. Standardize to `with self._cursor() as curs:`.

### F22. [LOW] Eager import of `AccessDatabase` in connect.py

`src/execsql/metacommands/connect.py` — Imports `AccessDatabase` (depends on pyodbc,
Windows-only) at module load. Moving to lazy import was reverted because test patch targets
broke. Marginal benefit.

### F25. [LOW] `format.py` SQL formatter hardcodes PostgreSQL dialect

`src/execsql/format.py` — `sqlglot.parse(read="postgres")` regardless of target DB.

**Fix:** Accept a `--dialect` flag or infer from `--type`.

______________________________________________________________________

## Security

### SEC-1. [MEDIUM] SHELL metacommand passes user input to subprocess

`src/execsql/metacommands/system.py` — `shlex.split()` tokenizes but doesn't sanitize.
Substitution variables from `PROMPT ENTRY`, `SUB_INI`, or env vars could inject arguments.
Partially mitigated: `subprocess.call` with list arg doesn't invoke a shell. User excluded
`--allow-shell` flag (F11).

### SEC-3. [LOW] `Encrypt` class provides no real security

`src/execsql/utils/crypto.py` — Hardcoded XOR keys in source. Any `enc_password` can be
trivially decoded. Documented as obfuscation-only. Deprecation warning now emitted.

### SEC-4. [LOW] `x_include` path traversal

`src/execsql/metacommands/io_fileops.py` — `INCLUDE` accepts arbitrary file paths from
scripts. If variables are populated from external sources, arbitrary files could be included.

______________________________________________________________________

## Performance

### F18. [MEDIUM] `SubVarSet._substitute_nested` is O(V) per call

`src/execsql/script/variables.py` — Fallback iterates over every defined variable with
case-insensitive substring search. With N tokens and V variables, worst case is O(N * V).

**Fix:** Index variables by first few characters for faster fallback lookup.

### PERF-4. [LOW] `substitute_vars` creates merged `SubVarSet` per statement

`src/execsql/script/engine.py` — When `localvars` is not None, creates a new `SubVarSet` with
recompiled regex every statement. Could cache when local vars haven't changed.

### PERF-5. [LOW] `set_dynamic_system_vars()` called per-statement

`src/execsql/script/engine.py` — 7 `add_substitution` calls per statement for values that
only change on CONFIG/AUTOCOMMIT metacommands. A dirty-flag approach would avoid overhead.

### PERF-7. [LOW] Pretty-print materializes entire result set

`src/execsql/exporters/pretty.py` — `list(rows)` forces the entire streaming generator into
memory to compute column widths. A 1M-row result set could blow up memory.

______________________________________________________________________

## Test Gaps

### F9. [HIGH] Core SQL execution unit tests are theater

`tests/test_engine.py` — `SqlStmt.run()` never tested with a real DB.
`MetacommandStmt.run()` patches the entire dispatch table. Error-recovery paths
(`WriteSpec.write()`, `MailSpec.send()`) still have zero integration test coverage.

**Fix:** Unit tests for `SqlStmt.run()` with real in-memory SQLite. Integration tests for
`ON ERROR_HALT WRITE` and `ON ERROR_HALT EMAIL` end-to-end.

### F16. [MEDIUM] Coverage omissions exclude ~7.8K lines

`pyproject.toml` — Excludes gui/desktop.py, gui/tui.py, metacommands/prompt.py,
script/executor.py, all 7 DB adapters, all LSP modules. The 90% gate applies to ~27K of ~35K
lines.

### TEST-1. [MEDIUM] No tests for `debug/repl.py`

REPL commands (`.vars`, `.set`, `.where`, `.stack`, ad-hoc SQL) have no dedicated tests.

### TEST-5. [MEDIUM] Limited importer edge case coverage

CSV importer doesn't cover: inconsistent column counts, encoding errors, BOM markers, empty
files, header-only files.

### TEST-2. [LOW] No tests for `gui/desktop.py` or `gui/tui.py` (excluded from coverage)

### TEST-3. [LOW] No tests for `metacommands/prompt.py` (excluded from coverage)

### TEST-4. [LOW] No tests for `db/dsn.py` (excluded from coverage)

### TEST-6. [LOW] No `format.py` edge case tests

Doesn't cover: nested block comments, metacommands inside block comments, SQL strings
containing `-- !x!` patterns, very long lines.

### TEST-7. [LOW] No property-based tests for parsers

`CondParser` and `NumericParser` handle arbitrary user input. Hypothesis-based testing would
catch edge cases.

### TEST-8. [LOW] DB adapters have zero test coverage

`db/access.py`, `db/firebird.py`, `db/oracle.py`, `db/sqlserver.py` — all excluded from
coverage.

______________________________________________________________________

## Edge Cases & Robustness

### EDGE-5. [LOW] Block comment parsing doesn't handle nested comments

`src/execsql/script/engine.py` — Simple `in_block_cmt` flag;
`/* outer /* inner */ still comment */` exits at first `*/`.

### EDGE-6. [LOW] `SourceString.match_str()` parameter shadows builtin `str`

`src/execsql/parser.py:60` — Suppressed by ruff A002.

______________________________________________________________________

## Divergences from Monolith

### DIV-4. [LOW] `DT_DuckDB` character types all map to TEXT

`src/execsql/types.py` — Loses VARCHAR(N) length constraints.

______________________________________________________________________

## Residual Risks

1. **Thread safety (F3)** is the largest residual risk. `from execsql import run` cannot be
    used from multiple threads. Must be addressed before the library API is promoted.

1. **Env var filter** — scripts relying on `!!&AWS_SECRET_ACCESS_KEY!!` will silently get
    empty strings. No opt-out mechanism.

1. **`exec_cmd` quoting** — `quote_identifier("schema.myproc")` produces `"schema.myproc"`
    (single identifier), not `"schema"."myproc"`. Could break schema-qualified function calls.

1. **WriteSpec/MailSpec** error-recovery paths are correct but still have zero dedicated
    integration tests.

______________________________________________________________________

## Feature Ideas

### Quick wins

- `$TIMER_SECONDS` — numeric companion to `$TIMER` timedelta string
- `$CURRENT_DATE` — clean `YYYY-MM-DD` string (vs `$DATE_TAG`'s `YYYYMMDD`)
- `CONTINUE` in loops — only `BREAK` exists; users nest IF blocks as workaround

### Medium features

- `FOR <var> IN <query|list>` loop — avoids `SUBDATA` + `WHILE` + string manipulation
- `RETRY N [BACKOFF s]` — transient DB error handling without verbose manual patterns
- Native webhook/HTTP notifications — `ON ERROR_HALT WEBHOOK` instead of `SYSTEM_CMD curl`
- `IMPORT FROM URL` — HTTP/REST import without temp file management
- Entry form validation enforcement — `validation_regex` fields exist but aren't enforced

### Strategic features

- Textual TUI console — `CONSOLE ON` is a stub in the Textual backend
- Persistent state across runs — `~/.execsql/state.db` for run history, watermarks, checkpoints
- Thread-safe RuntimeContext (F3) — enables PARALLEL blocks, concurrent library API, easier testing
- LSP enhancements — autocomplete, hover docs, jump-to-definition, inline diagnostics

______________________________________________________________________

## Summary

| Category               | High  | Medium | Low    | Total  |
| ---------------------- | ----- | ------ | ------ | ------ |
| Architecture & Quality | 2     | 3      | 2      | 7      |
| Security               | 0     | 1      | 2      | 3      |
| Performance            | 0     | 1      | 3      | 4      |
| Test Gaps              | 1     | 3      | 6      | 10     |
| Edge Cases             | 0     | 0      | 2      | 2      |
| Divergences            | 0     | 0      | 1      | 1      |
| **Total**              | **3** | **8**  | **16** | **27** |
