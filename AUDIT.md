# Codebase Audit

**Date:** 2026-05-01
**Scope:** Full codebase — 34,612 source LOC across 100 Python modules
**Auditor:** Claude Opus 4.6 (automated deep audit)

---

## 1. Executive Summary

- **Shape:** Well-structured modular codebase (refactored from 16.6k-line monolith) with 4,202 tests, 89% coverage floor, clean ruff, and solid CI. The refactoring is largely successful.
- **Top theme — security surface area:** The SYSTEM_CMD metacommand uses `subprocess.call()` on user-controlled strings, the crypto module is XOR obfuscation with hardcoded keys, and IMPORT/EXPORT paths lack traversal validation. These are the highest-priority items.
- **Top theme — resource lifecycle:** Cursor leaks in `select_rowsource()` and `populate_table()`, unbounded file loads in `import_entire_file()` and JSON importer, and no streaming for large datasets. These are production reliability risks.
- **Top theme — AST/legacy inconsistency:** The AST executor doesn't evaluate ELSEIF with ANDIF/ORIF modifiers (unlike IF), deep-copies immutable AST bodies on every loop iteration, silently ignores unknown node types, and uses a fragile `_FakeScriptCmd` compatibility shim.
- **Top theme — broad exception swallowing:** 241 `except Exception` handlers across the source, with at least 9 bare `pass` handlers in `db/base.py` alone. These mask real errors.
- **Fix first:** ~~(1) SYSTEM_CMD injection~~, ~~(2) cursor lifecycle in `select_rowsource`~~, ~~(3) ELSEIF modifier bug in executor~~. All three resolved.
- Intake context was provided by the maintainer. Coverage omissions (GUI, prompt, executor, 6 DB adapters) exclude substantial code from measurement.
- Empty CHANGELOG entries for v2.16.11 and v2.16.12 suggest metadata-only bumps without user-visible changes.

---

## 2. System Overview as Observed

execsql2 is a CLI tool and Python library that executes SQL scripts against 9 database backends (PostgreSQL, MySQL/MariaDB, SQLite, DuckDB, MS SQL Server, MS Access, Firebird, Oracle, ODBC). Scripts contain standard SQL plus metacommands (embedded in SQL comments with `-- !x!` prefix) for importing/exporting data, conditional execution, looping, substitution variables, and interactive GUI prompts.

The codebase was refactored from a single-file monolith into ~80 modules organized by concern: `cli/` (entry points), `script/` (parsing, AST, execution engine), `metacommands/` (16 handler modules), `db/` (9 database adapters + pool), `exporters/` (16 format modules), `importers/` (6 format modules), `gui/` (3 backends), and `utils/` (10 utility modules). A recent major addition is the AST parser and executor (`script/parser.py`, `script/ast.py`, `script/executor.py`) which replaces the flat `CommandList` execution model for structured control flow.

The README and documentation are accurate and comprehensive. The library API (`api.py`) provides isolated `RuntimeContext` per call with proper context management. The plugin system uses standard Python entry points.

---

## 3. Baselines

| Metric | Value |
|--------|-------|
| Source LOC | 34,612 (100 .py files) |
| Test LOC | 53,144 (120 .py files) |
| Test functions | 4,202 |
| Coverage floor | 89% (pyproject.toml) |
| Direct dependencies | 5 (python-dateutil, rich, sqlglot, textual, typer) |
| Lockfile entries | ~140 |
| Ruff status | All checks passed |
| Commits (6 months) | 281 |
| Current version | 2.16.12 |

**Top 10 files by churn:**

| File | Touches |
|------|---------|
| CHANGELOG.md | 161 |
| pyproject.toml | 100 |
| uv.lock | 82 |
| docs/about/divergence.md | 41 |
| README.md | 32 |
| src/execsql/db/base.py | 19 |
| src/execsql/state.py | 18 |
| src/execsql/metacommands/**init**.py | 17 |
| src/execsql/cli/run.py | 17 |
| src/execsql/script/engine.py | 15 |

**Largest source files:**

| File | Lines |
|------|-------|
| metacommands/dispatch.py | 2,259 |
| gui/tui.py | 1,741 |
| gui/desktop.py | 1,397 |
| script/executor.py | 994 |
| cli/run.py | 960 |
| metacommands/prompt.py | 950 |
| metacommands/conditions.py | 863 |
| exporters/delimited.py | 822 |
| script/parser.py | 820 |

---

## 4. Feature Inventory and Trace Results

| Feature | Entry Point | Layers | Test Coverage | Health |
|---------|-------------|--------|---------------|--------|
| CLI execution | `cli:_legacy_main` → `cli/run.py:_run` | cli, state, script, metacommands, db | `test_cli_e2e.py` (26 tests) | Good |
| Library API | `api.py:run()` | api, state, script, metacommands, db | `test_api.py` | Good |
| SQL parsing + AST | `script/parser.py:parse_script` | parser, ast | `test_ast_parser.py`, `test_ast.py` | Good |
| AST execution | `script/executor.py:execute` | executor, engine, state | `test_executor.py` (95 tests) | Fair — see F-001, F-002, F-003 |
| Metacommand dispatch | `metacommands/dispatch.py` | dispatch, 12 handler modules | `metacommands/test_*.py` | Good |
| Conditional tests | `metacommands/conditions.py` | conditions, parser | tests present | Fair — regex gaps |
| Control flow (LOOP/BATCH) | `metacommands/control.py` + executor | control, script | tests present | Good |
| Import (CSV/JSON/etc.) | `metacommands/io_import.py` → importers/* | io_import, importers, db | tests present | Fair — path traversal |
| Export (20+ formats) | `metacommands/io_export.py` → exporters/* | io_export, exporters, db | tests present | Fair — cursor leaks |
| Database connections | `db/*.py` + `db/factory.py` | db, pool | `db/test_base.py` | Fair — lifecycle issues |
| Substitution variables | `script/variables.py` | variables, engine | tests present | Good |
| GUI prompts | `metacommands/prompt.py` → gui/* | prompt, gui backends | Excluded from coverage | Unknown |
| Config system | `config.py` | config | `test_config*.py` | Good |
| Debug REPL | `debug/repl.py` | debug | `test_debug_repl.py` | Good |
| Script formatter | `format.py` | format | `test_format.py` | Good |
| Lint | `cli/lint.py`, `cli/lint_ast.py` | lint, parser | tests present | Fair — false positives |
| Plugin system | `plugins.py` | plugins, entry_points | `test_plugins.py` | Fair — no sandboxing |
| pg-upsert | `metacommands/upsert.py` | upsert | tests present | Good |
| SYSTEM_CMD | `metacommands/system.py` | system, subprocess | tests present | Poor — injection risk |

---

## 5. Findings

### Correctness

#### ~~F-001: ELSEIF conditions don't evaluate ANDIF/ORIF modifiers~~ RESOLVED

Fixed. Added `condition_modifiers` field to `ElseIfClause` in ast.py, updated parser.py to route ANDIF/ORIF to the current ELSEIF clause, and updated executor.py to call `_eval_condition()` for ELSEIF. 4 parser tests + 4 executor tests added.

#### ~~F-002: Unknown AST node types are silently ignored~~ RESOLVED

Fixed. Added `else: raise ErrInfo(...)` to `_execute_node()` for unhandled node types.

#### F-003: Deep copy of AST body on every loop iteration — KEPT

Reviewed and decided to keep as defensive safety net. AST node fields include mutable lists (`body: list[Node]`) that frozen dataclasses don't protect from mutation. The deep copy guards against future code paths that might mutate node contents during execution.

#### ~~F-004: Empty CHANGELOG entries for v2.16.11 and v2.16.12~~ RESOLVED

Filled in from git history. v2.16.11: block comment docstring fix + 12 parser tests. v2.16.12: coverage threshold change + SCRIPT introspection tests.

#### F-005: _FakeScriptCmd uses dynamic type() — fragile compatibility shim

- **Severity / Effort / Confidence:** Low / M / Verified
- **Locations:** `src/execsql/script/executor.py:886-913`
- **What's there:** `_FakeScriptCmd` creates anonymous classes via `type("_cmd", (), {...})()` to satisfy `ctx.last_command` readers. The lambda `lambda self: self.statement` binds `self` to the anonymous class instance, not `_FakeScriptCmd`.
- **Why it's a problem:** Code that uses `isinstance(ctx.last_command, ScriptCmd)` or `type(ctx.last_command).__name__` will get incorrect results. This is a fragile bridge between the AST executor and the legacy engine.
- **Recommended change:** Define a proper `_CommandProxy` dataclass with `statement` and `commandline()` method.
- **Definition of done:** `_FakeScriptCmd` replaced with typed proxy class.

---

### Architecture & Drift

#### ~~F-006: Coverage threshold drift — docs say 90%, config says 89%~~ RESOLVED

Fixed. Updated project_context.md to say 89% and noted the v2.16.12 change.

#### ~~F-007: Project context version stale (says 2.13.2, actual is 2.16.12)~~ RESOLVED

Fixed. Replaced hardcoded version with "See `pyproject.toml` for the current version."

#### F-008: textual is a core dependency but should be optional

- **Severity / Effort / Confidence:** Medium / M / Verified
- **Locations:** `pyproject.toml:47`, `src/execsql/gui/__init__.py:42-52`, `src/execsql/gui/tui.py:33-48`
- **What's there:** `textual>=0.47.0` is listed in core `dependencies`. However, `gui/__init__.py` catches `ImportError` for TextualBackend and falls back to `ConsoleBackend`. The TUI module itself wraps the import in try/except.
- **Why it's a problem:** Every `pip install execsql2` pulls textual and its transitive dependencies even when the user will never use a TUI. Headless CI, ETL scripts, and library API users pay for unused weight.
- **Recommended change:** Move textual to `[project.optional-dependencies]` under a `tui` or `gui` extra. Keep the graceful fallback in `gui/__init__.py`.
- **Definition of done:** `pip install execsql2` without extras does not install textual.

#### F-009: Stale stub handlers for LOOP and INCLUDE in dispatch

- **Severity / Effort / Confidence:** Low / S / Verified
- **Locations:** `src/execsql/metacommands/control.py:122-130`, `src/execsql/metacommands/io_fileops.py:26-32`
- **What's there:** `x_loop()` and `x_include()` are registered in the dispatch table but immediately raise `ErrInfo("LOOP/INCLUDE should be handled by the AST executor")`.
- **Why it's a problem:** These are dead-code placeholders. If the AST executor misses a case and falls through to dispatch, users get a confusing error message rather than correct behavior.
- **Recommended change:** Either remove from dispatch (since AST handles them) or improve the error message to say "internal error — AST executor should have handled this."
- **Definition of done:** Error message is clear, or handlers are removed with a comment explaining why.

---

### Security

#### ~~F-010: SYSTEM_CMD metacommand — subprocess.call() on user-controlled string~~ RESOLVED

Fixed. Added `--no-system-cmd` CLI flag and `allow_system_cmd` config option (default: True) to disable SYSTEM_CMD execution entirely. When disabled, `x_system_cmd()` raises `ErrInfo` with a clear message. Replaced deprecated `subprocess.call()` with `subprocess.run()`. Removed the broken `&` double-quoting workaround (a Windows `cmd.exe` hack from the monolith that injected literal `"` into argv). Security docs updated with disabling instructions and Windows `.bat`/`.cmd` edge case. Library API exposes `allow_system_cmd=False`.

#### F-011: Crypto module is obfuscation, not encryption

- **Severity / Effort / Confidence:** Medium / S / Verified
- **Locations:** `src/execsql/utils/crypto.py:49-61`
- **What's there:** The `Encrypt` class uses XOR with 9 hardcoded hex keys (lines 49-61). Anyone with access to the source code can decrypt any stored password. The module has thorough docstring warnings (lines 4-22) about this.
- **Why it's a problem:** Users may store `enc_password` in config files believing it's secure. The warnings are in the source code (not the user-facing docs or CLI output).
- **Recommended change:** (1) Emit a runtime warning when `enc_password` is used, directing users to keyring. (2) Add a deprecation timeline. (3) Ensure the security docs page explicitly warns about this.
- **Definition of done:** Users see a warning when using enc_password; docs warn prominently.

#### F-012: No path traversal validation in IMPORT/EXPORT

- **Severity / Effort / Confidence:** Medium / M / Verified
- **Locations:** `src/execsql/metacommands/io_import.py:34-35,333-334,367-368,401-402`, `src/execsql/importers/csv.py:39`, `src/execsql/importers/json.py:51`
- **What's there:** File paths from metacommands undergo tilde expansion but no validation against directory traversal (`../`). Symlinks are followed without checking.
- **Why it's a problem:** In a shared environment where scripts are provided by semi-trusted users, IMPORT could read arbitrary files. EXPORT could write to unexpected locations. The SERVE metacommand (`io_fileops.py:253-286`) could expose arbitrary files via symlinks.
- **Recommended change:** Add optional `conf.allowed_import_dirs` / `conf.allowed_export_dirs` settings. Validate resolved paths when configured. Default to unrestricted (backwards compatible).
- **Definition of done:** Configurable path restrictions available; documented in security docs.

#### F-013: Plugin system executes arbitrary code without sandboxing

- **Severity / Effort / Confidence:** Low / S / Verified
- **Locations:** `src/execsql/plugins.py:295-320`
- **What's there:** Plugins are loaded via `entry_points()` → `ep.load()` which executes arbitrary Python. Registration functions receive the full dispatch table and can override any metacommand.
- **Why it's a problem:** This is standard Python entry point behavior, but users may not realize that `pip install some-plugin` grants full code execution within execsql. Broken plugins are caught but malicious ones are not.
- **Recommended change:** Document the trust model in the plugin docs and security page. Consider adding `--no-plugins` CLI flag.
- **Definition of done:** Plugin trust model documented; opt-out flag available.

---

### Data Layer

#### ~~F-014: Cursor leak in select_rowsource()~~ RESOLVED

Fixed. Added `curs.close()` before `self.rollback()` in the `except` block of both `select_rowsource()` and `select_rowdict()` (query failure path). Added explicit `rows.close()` in the two highest-traffic callers (EXPORT in `io_export.py`, COPY in `io_fileops.py`) so the generator and cursor are deterministically cleaned up on error. The generator's `finally: curs.close()` remains as the GC safety net for normal consumption.

#### ~~F-015: SQLite populate_table() cursor not protected by try/finally~~ RESOLVED

Fixed. Wrapped cursor in try/finally in `populate_table()`. Also converted `import_entire_file()` to use `with self._cursor()` context manager.

#### F-016: Unbounded file load in import_entire_file()

- **Severity / Effort / Confidence:** Medium / S / Verified
- **Locations:** `src/execsql/db/base.py:641-642`
- **What's there:** `f.read()` loads the entire binary file into memory with no size limit.
- **Why it's a problem:** A multi-GB file will OOM the process.
- **Recommended change:** Add a configurable size limit (e.g., `conf.max_import_file_size`) and warn/fail above it.
- **Definition of done:** Size limit configurable; default reasonable (e.g., 1 GB).

#### F-017: JSON importer loads entire file into memory

- **Severity / Effort / Confidence:** Medium / S / Verified
- **Locations:** `src/execsql/importers/json.py:51`
- **What's there:** `Path(filename).read_text()` loads the full file, then `json.loads()` parses it all at once.
- **Why it's a problem:** No streaming JSON parser. 100+ MB JSON files will OOM.
- **Recommended change:** Use `ijson` for streaming or document the file size limitation. For NDJSON, read line-by-line.
- **Definition of done:** Either streaming parser or documented limitation.

#### F-018: Encoding fallback hard-coded to "backslashreplace"

- **Severity / Effort / Confidence:** Low / S / Verified
- **Locations:** `src/execsql/db/base.py:244-250`
- **What's there:** `c.decode(self.encoding, "backslashreplace")` ignores `conf.enc_err_disposition` which exists in config.py but is not consulted here.
- **Why it's a problem:** Non-UTF8 bytes become `\xNN` literals in export output, silently corrupting data. The config setting exists but isn't used.
- **Recommended change:** Use `conf.enc_err_disposition` instead of hard-coded `"backslashreplace"`.
- **Definition of done:** Config setting respected.

---

### Concurrency & Failure Modes

#### F-019: DatabasePool has no thread synchronization

- **Severity / Effort / Confidence:** Medium / M / Likely
- **Locations:** `src/execsql/db/base.py:665-695`
- **What's there:** `DatabasePool` uses a plain dict with no locks. `add()`, `remove()`, `closeall()`, and `current()` all mutate or read shared state without synchronization.
- **Why it's a problem:** The library API (`api.py`) creates isolated contexts per call, so concurrent `run()` calls each get their own pool. However, if a user creates a shared pool and passes a connection to multiple `run()` calls, races are possible. The pool is also used by the Textual console which runs scripts in a background thread.
- **Recommended change:** Add `threading.Lock` around pool mutations, or document that pools are not thread-safe.
- **Definition of done:** Pool is either locked or documented as single-threaded only.

#### F-020: atexit handlers registered on thread-local state

- **Severity / Effort / Confidence:** Low / M / Likely
- **Locations:** `src/execsql/cli/run.py:639,721`
- **What's there:** `atexit.register(filewriter_end)` and `atexit.register(_state.dbs.closeall)` are called during `_run()`. Since `_state` is thread-local, the atexit callbacks reference the main thread's context. Worker threads' connections won't be closed at exit.
- **Recommended change:** Use context managers or `try/finally` instead of atexit for cleanup.
- **Definition of done:** Cleanup happens via try/finally, not atexit.

#### F-021: FileWriter restart on repeated _run() calls

- **Severity / Effort / Confidence:** Low / S / Likely
- **Locations:** `src/execsql/cli/run.py:631-639`
- **What's there:** Each call to `_run()` checks `_state.filewriter is None or not _state.filewriter.is_alive()` and creates a new FileWriter if needed. Each time, `atexit.register(filewriter_end)` is called, potentially registering multiple handlers.
- **Recommended change:** Track whether atexit was already registered; or use a single-shot registration.
- **Definition of done:** Multiple `_run()` calls don't stack atexit handlers.

---

### Performance

#### F-022: Broad exception handling pattern — 241 instances

- **Severity / Effort / Confidence:** Medium / L / Verified
- **Locations:** 241 `except Exception` handlers across `src/execsql/`, with at least 9 in `db/base.py` followed by `pass`
- **What's there:** Pattern: `except Exception: pass` with comments like "Non-critical: some drivers lack rowcount support." Also in `io_fileops.py` (lines 67, 77, 95, 146) and `io_write.py` (line 185).
- **Why it's a problem:** These mask real errors. A disk-full condition during export, a permission error on import, or a SQL syntax error in a metadata query all get silently swallowed. Makes production debugging extremely difficult.
- **Recommended change:** Replace with specific exception types (`OperationalError`, `ProgrammingError`, etc.). At minimum, log caught exceptions at DEBUG level.
- **Definition of done:** No bare `except Exception: pass` without logging. Specific exception types where possible.

#### F-023: Conditional regex patterns too restrictive for quoted identifiers

- **Severity / Effort / Confidence:** Medium / S / Verified
- **Locations:** `src/execsql/metacommands/conditions.py:635-694`
- **What's there:** `TABLE_EXISTS`, `COLUMN_EXISTS` and similar conditional test regexes use character classes like `[A-Za-z0-9_\-\:]` for table/schema names. These reject quoted identifiers with spaces (e.g., `"My Table"`), backtick-quoted names (MySQL), and bracket-quoted names (SQL Server).
- **Why it's a problem:** Users with space-containing identifiers (common in Access and Excel-imported data) can't use these conditionals.
- **Recommended change:** Expand character classes to support quoted identifiers: `\"[^\"]+\"|` + `` `[^`]+` `` + `[A-Za-z0-9_]+`.
- **Definition of done:** `TABLE_EXISTS("My Table")` works.

#### F-024: Lint false positives — SELECTSUB variables not tracked

- **Severity / Effort / Confidence:** Medium / S / Verified
- **Locations:** `src/execsql/cli/lint_ast.py:196-205`
- **What's there:** `_extract_var_definition()` checks for SUB, SUB_EMPTY, etc., but does not recognize SELECTSUB (PROMPT SELECT_SUB) as a variable-defining metacommand. The regex `_RX_SELECTSUB` is defined (line 64) but never matched in the extraction function.
- **Why it's a problem:** Variables defined via SELECTSUB produce false-positive "undefined variable" warnings in `--lint`.
- **Recommended change:** Add `_RX_SELECTSUB` to the extraction loop.
- **Definition of done:** `--lint` doesn't warn about SELECTSUB-defined variables.

---

### Dependencies

#### F-025: sqlglot is a core dependency for an optional feature

- **Severity / Effort / Confidence:** Low / M / Likely
- **Locations:** `pyproject.toml:46`
- **What's there:** `sqlglot>=25.0` is a core dependency, but it's primarily used by `execsql-format` (the formatter) and `--parse-tree` flag. The main execution engine doesn't use sqlglot.
- **Why it's a problem:** Minor — adds dependency weight for users who never format scripts. Less impactful than textual (F-008) since sqlglot is pure Python.
- **Recommended change:** Consider making optional (lower priority than textual).
- **Definition of done:** Evaluated and documented.

---

### Tests

#### F-026: Coverage omissions exclude substantial code

- **Severity / Effort / Confidence:** Medium / L / Verified
- **Locations:** `pyproject.toml:200-218`
- **What's there:** Coverage omits: `gui/desktop.py`, `gui/tui.py`, `metacommands/prompt.py`, `script/executor.py`, and 6 database adapters (postgres, mysql, oracle, firebird, sqlserver, access, dsn).
- **Why it's a problem:** These represent roughly 6,000+ lines of untested code. The executor is the newest and most complex module — excluding it from coverage measurement means the 89% floor doesn't reflect actual coverage of the execution path.
- **Recommended change:** At minimum, remove `executor.py` from omissions (it has 95 tests already). GUI modules are harder but should have unit tests for non-display logic.
- **Definition of done:** `executor.py` included in coverage measurement; threshold maintained.

#### F-027: Tests mock at wrong level — verify calls, not behavior

- **Severity / Effort / Confidence:** Medium / M / Likely
- **Locations:** Various metacommand test files (e.g., `tests/metacommands/test_io_import.py`)
- **What's there:** Many metacommand tests mock the database `importtable()` and `Path.exists()`, then assert the mock was called with expected arguments. They don't verify that data was actually imported correctly.
- **Why it's a problem:** Tests pass even if the import logic has bugs (wrong column mapping, encoding errors, off-by-one in header skip). The tests verify "the function was called" not "the correct data resulted."
- **Recommended change:** Add integration-style tests for import/export that use real SQLite databases and verify row data.
- **Definition of done:** At least one real-database import/export test per format.

---

### Documentation

#### F-028: Divergence.md claims O(1) substitution without noting O(N*V) fallback

- **Severity / Effort / Confidence:** Low / S / Verified
- **Locations:** `docs/about/divergence.md`
- **What's there:** Claims "O(1) substitution" for the `TOKEN_RX` regex path. Doesn't mention the `_substitute_nested()` fallback which is O(N*V) where N is text length and V is variable count.
- **Recommended change:** Add a note: "Falls back to O(N*V) substring search for nested patterns like `!!N_!!CHECK_GROUP!!_CHECKS!!`."
- **Definition of done:** Divergence doc notes the fallback.

#### ~~F-029: CI doesn't run ruff or formatting checks~~ RESOLVED

Fixed. Added a `lint` job to ci-cd.yml that runs `ruff check` and `ruff format --check` on `src/` and `tests/`. Build job now depends on lint passing.

---

## 6. Kill List

Items that should be deleted (not refactored).

| Item | Location | Justification | Zero-ref check |
|------|----------|---------------|----------------|
| Stub `x_loop()` handler | `metacommands/control.py:122-130` | Dead code — AST executor handles LOOP. Only purpose is to raise an error if dispatch table is reached, which indicates a bug. | Dispatch table references it, but it should never be called in normal operation. |
| Stub `x_include()` handler | `metacommands/io_fileops.py:26-32` | Same as above for INCLUDE. | Same. |
| ~~`copy.deepcopy()` in executor~~ | ~~`script/executor.py:768`~~ | Kept — defensive safety net against future mutation in loop bodies. | N/A |
| ~~Hardcoded version in context doc~~ | ~~`.claude/project_context.md:196`~~ | RESOLVED — replaced with reference to pyproject.toml. | N/A |

---

## 7. Themes and Root Causes

### Theme 1: Legacy bridge tax

The AST executor was built alongside the legacy `CommandList` engine. This created compatibility shims (`_FakeScriptCmd`), stub dispatch handlers (`x_loop`, `x_include`), and behavioral gaps (ELSEIF modifiers). As the AST executor matures, these bridges should be removed and the executor should become the sole execution path.

### Theme 2: Defensive-to-a-fault exception handling

The original monolith used broad `except Exception` patterns to survive diverse database drivers with different exception hierarchies. During the modular refactor, these patterns were preserved uncritically. The result is 241 broad handlers, many with `pass`, that mask real errors. The fix is systematic: identify the specific driver exceptions at each call site.

### Theme 3: Resource lifecycle gaps

Cursors, file handles, and the FileWriter process all have lifecycle issues. The root cause is that the original monolith managed resources imperatively (open → use → close), while the modular code sometimes returns generators or spans multiple function boundaries. Context managers (`with` statements) should be used consistently.

### Theme 4: Security as afterthought

The SYSTEM_CMD metacommand, crypto module, and path handling were inherited from a single-user desktop tool and haven't been hardened for multi-user or untrusted-script scenarios. The security docs exist but the code hasn't caught up. This is addressable with a security audit sweep and config-gated restrictions.

---

## 8. Adversarial Findings

### Attacker perspective

**Highest-value target:** Database credentials and data.

1. **Attack path — SYSTEM_CMD injection via substitution variables:** If an attacker can influence a substitution variable (e.g., via database query result → SUB → SHELL), they achieve RCE. Defense: none beyond trusting the script author.
2. **Attack path — config file credential extraction:** `enc_password` values in `execsql.conf` are XOR-obfuscated with hardcoded keys. Anyone with source code can decrypt. Defense: keyring auth exists as alternative.
3. **Attack path — malicious plugin:** `pip install evil-plugin` → entry point auto-loaded → full dispatch table access. Defense: none; standard Python trust model.
4. **Attack path — IMPORT path traversal:** `IMPORT FROM ../../etc/shadow` — no path validation. Defense: OS file permissions only.

### Confused new hire perspective

1. **`_FakeScriptCmd`** — the name suggests it's a test fixture, but it's production code in the executor. A developer might delete it thinking it's dead code.
2. **`state.py` module proxy** — the `_StateModule` class replaces `sys.modules["execsql.state"]` at import time (line 548). A developer adding a module-level variable to `state.py` would be confused when it becomes a RuntimeContext attribute.
3. **Two parsers, two linters** — `cli/lint.py` (legacy flat) and `cli/lint_ast.py` (AST-based) coexist. It's unclear which is used when, and they have different coverage of edge cases.
4. **`x_loop()` raises an error** — a developer reading the dispatch table would think LOOP is broken, not realizing the AST executor handles it before dispatch.

### Future maintainer perspective (18 months)

1. **Hardest to change safely:** `metacommands/dispatch.py` (2,259 lines of regex registrations). Any change here can silently break metacommand parsing. The `test_registry.py` consistency test helps, but regex behavior changes are subtle.
2. **Hidden coupling:** The executor depends on `_state` for everything — substitution variables, IF stack, database pool, counters, profile data. Adding a new feature means understanding all the state it might need.
3. **Test brittleness:** Many tests mock at implementation level (specific function calls). Refactoring internal structure breaks tests even if behavior is preserved.

---

## 9. Recommended Sequencing

### Wave 1 — Security & correctness (do first)

1. ~~**F-001** (ELSEIF modifiers): Fix AST model + executor~~ DONE
2. ~~**F-002** (unknown node types): Add else-raise to executor~~ DONE
3. ~~**F-004** (empty changelog): Fill in from git history~~ DONE
4. ~~**F-014** (cursor leaks): Fix `select_rowsource()` with cursor cleanup~~ DONE
5. ~~**F-010** (SYSTEM_CMD injection): Add `--no-system-cmd` flag, document trust model, replace deprecated subprocess calls~~ DONE

### Wave 2 — Reliability

1. ~~**F-015** (SQLite cursor): Add try/finally~~ DONE
2. **F-022** (broad exception handling): Systematic sweep — start with `db/base.py` (9 instances), then exporters/importers

### Wave 3 — Infrastructure

1. ~~**F-006, F-007** (doc drift): Align context doc~~ DONE
2. ~~**F-029** (CI ruff): Add lint step~~ DONE
3. **F-008** (textual optional): Move to extras
4. **F-026** (coverage omissions): Remove executor.py from omissions

### Wave 4 — Polish

12. **F-011** (crypto warning): Add runtime deprecation warning
2. **F-012** (path traversal): Add configurable restrictions
3. **F-023** (regex patterns): Expand for quoted identifiers
4. **F-024** (lint false positives): Add SELECTSUB tracking
5. **F-005** (_FakeScriptCmd): Replace with typed proxy

### Requires design decision

- **F-016, F-017** (unbounded loads): Need to decide on size limits and streaming strategy
- **F-019** (pool thread safety): Need to decide if pool should be thread-safe or documented as single-threaded
- **F-013** (plugin sandboxing): Need to decide trust model

---

## 10. Open Questions for the Maintainer

1. **SYSTEM_CMD trust model:** Is SHELL intended for trusted scripts only, or should there be a safety mode? Should substitution variables be shell-quoted when injected into SYSTEM_CMDs?
2. **enc_password deprecation:** Should this be deprecated with a timeline, or kept as "convenience obfuscation" with louder warnings?
3. **AST executor as sole path:** Is the plan to eventually remove the legacy `CommandList` engine entirely? If so, the stub handlers and `_FakeScriptCmd` can be removed more aggressively.
4. **Coverage omissions:** Is `executor.py` excluded intentionally (subprocess tests only), or is it an oversight? Same question for `prompt.py` — are there plans for GUI testing?
5. **textual as optional:** Would removing textual from core deps break any documented install path or deployment?
6. **Two linters:** Is `cli/lint.py` (legacy flat) still needed, or can it be removed in favor of `cli/lint_ast.py`?
7. ~~**Empty changelog entries:**~~ RESOLVED — filled in from git history.

---

## 11. Audit Metadata

- **Date:** 2026-05-01
- **Scope:**
  - **Deep:** cli/, script/ (parser, ast, executor, engine, variables, control), metacommands/ (all 16 modules), db/base.py, db/sqlite.py, api.py, state.py, plugins.py, utils/ (all 10 modules), exceptions.py
  - **Medium:** exporters/ (base, delimited, json, protocol), importers/ (base, csv, json), config.py, format.py, types.py, models.py
  - **Shallow:** gui/ (read structure, not deep-traced), constants.py
  - **Skipped:** `_execsql/` (reference monolith), VS Code extension, templates/, docs/ content (spot-checked)
- **Coverage omissions noted:** gui/desktop.py, gui/tui.py, metacommands/prompt.py, script/executor.py, 6 DB adapters — these modules are excluded from the 89% coverage floor
- **Tools run:** `ruff check` (passed), `git log` (churn analysis), `wc -l` / `find` (baselines), `grep` (pattern searches)
- **Limits:** Did not run the test suite, the application, or any database integration. Did not install or test plugins. Did not review the Textual or Tkinter GUI behavior visually.
- **Confidence:** High for correctness and security findings (code-traced). Medium for concurrency findings (reasoned from code, not tested under load). Low for performance findings (no profiling data).
