Deep Codebase Analysis: execsql2

1. metacommands/system.py:38-54 — subprocess.call() / subprocess.Popen() with script-derived args

- This is by design (it's a documented metacommand feature), but worth noting that SQL scripts can execute arbitrary OS commands.
    Users running untrusted scripts should be aware.

1. Code Quality & Maintainability

SHOULD FIX — ConfigData.init is 500+ lines of repetitive if/has_option blocks

1. config.py:58-515 — Massive single method

- The __init__ method is ~457 lines of nearly identical if cp.has_option(...): self.x = cp.get...(...) blocks.
- Recommendation: Refactor into a declarative config schema (list of dicts with section, key, attribute, type, default, validator)
    and a single generic parsing loop.

NICE TO HAVE — MetaCommandList is a hand-rolled linked list ✅ *completed 2026-03-24*

1. script.py:451-509 — Custom linked list with move-to-front heuristic

- MetaCommandList.eval() moves successfully matched commands to the head of the linked list. This is a performance heuristic from
    the monolith but makes debugging harder — command ordering changes at runtime.
- A simple list with enumerate or a dict-based dispatch would be clearer and likely equally fast.
- **Done:** Replaced linked list with `list[MetaCommand]` using prepend semantics; removed `next_node`, `insert_node()`, and move-to-front heuristic from `eval()`.

NICE TO HAVE — Broad except Exception / except: usage

1. 245 occurrences of except Exception: across 48 source files

- Many of these swallow exceptions silently (e.g., config.py:158, config.py:466, db/base.py:103-104, db/base.py:109).
- Recommendation: Progressively narrow these to specific exception types during refactoring.

1. Architecture & Design

SHOULD FIX — Global mutable state in state.py

1. state.py — 40+ module-level mutable globals

- Everything is accessed via import execsql.state as \_state. This creates tight coupling and makes testing difficult (requires
    state.reset() between tests).
- Recommendation: For v2, consider a RuntimeContext class that holds all these fields, passed explicitly or via a context
    variable.

NICE TO HAVE — Circular import avoidance via deferred imports

1. Many import X statements inside function bodies (e.g., cli.py:456,564,571,580, script.py:216,302, errors.py:79,97,110,127).

- These exist to break circular dependencies between state ↔ script ↔ errors ↔ cli.
- Not a bug, but a sign that the dependency graph could be simplified.

______________________________________________________________________

1. Feature Improvements & Enhancements

Connection string / URL support ✅ *completed 2026-03-24*

1. Modern tools use connection strings (postgresql://user:pass@host/db). execsql requires separate server/db/user/port args.

- Recommendation: Add --connection-string / --dsn CLI option that parses a URL.
- **Done:** `--dsn` / `--connection-string` option added. Parses standard URL syntax into `db_type`, `server`, `db`, `db_file`, `user`, `password`, `port`. Supported schemes: postgresql, postgres, mysql, mariadb, mssql, sqlserver, oracle, firebird, sqlite, duckdb. Passwords included in the URL suppress the interactive password prompt.

Structured output for EXPORT ✅ *completed 2026-03-24*

1. The EXPORT metacommand supports many formats (CSV, JSON, XML, etc.) but the output path must be specified per-command.

- Recommendation: Add an --output-dir CLI option or config setting as a default base directory.
- **Done:** `--output-dir DIR` option added. The `_apply_output_dir()` helper in `metacommands/io.py` prepends the configured directory to relative EXPORT paths at runtime. Absolute paths and `stdout` are unchanged.

Progress reporting for long imports ✅ *completed 2026-03-24*

1. Large IMPORT operations provide no progress feedback. The FileWriter subprocess model makes this feasible.

- Recommendation: Log or print row counts periodically during import.
- **Done:** After each batch commit in `populate_table` (base.py), `import_tabular_file` (mysql.py), and `import_tabular_file` (postgres.py), a `log_status_info` message is written with the running row count (e.g. `IMPORT into schema.table: 1000 rows imported so far.`) and a final completion message after the loop.

Dry-run / explain mode ✅ *completed 2026-03-24*

1. No way to validate a script without executing it. Users must run against a real database.

- Recommendation: Add --dry-run that parses the script, resolves includes, and reports the command list without executing.
- **Done:** `--dry-run` flag added to CLI; prints numbered command list (SQL/METACMD with source:line) without connecting to DB.
