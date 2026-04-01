______________________________________________________________________

## name: execsql2 project context description: Canonical project context for execsql2 — origin, tooling, roadmap, collaboration norms, and monolith index type: project

# execsql2 Project Context

> **Canonical location:** `.claude/project_context.md` in the repo.
> Global memory (`~/.claude/projects/.../memory/`) mirrors this — the repo file is the source of truth.
> Update this file whenever any architectural, tooling, or directional decision is made.
> Update the CHANGELOG.md whenever making a release or significant change.

______________________________________________________________________

## Origin

`execsql2` is a maintained fork of [`execsql`](https://hg.sr.ht/~rdnielsen/execsql) (v1.130.1) by Dreas Nielsen. The upstream maintainer retired and stopped making changes. Caleb Grant (cgrant) forked it to maintain, modernize, and continue publishing it.

- Upstream: Mercurial repo at `https://hg.sr.ht/~rdnielsen/execsql`, cloned to `/tmp/execsql_hg`
- Upstream docs mirror (more complete images): `~/GitHub/misc/execsql_doc`
- Fork repo: `https://github.com/geocoug/execsql` (git)
- PyPI package name: `execsql2` (`execsql` was already taken on PyPI)
- Maintainer: Caleb Grant <grantcaleb22@gmail.com>

**Why:** Upstream is dead. The tool is useful and actively needed. Goal is to maintain it long-term, modernize the codebase, and publish clean releases.

______________________________________________________________________

## What execsql Does

CLI tool that runs SQL scripts against multiple DBMS backends (PostgreSQL, SQLite, MariaDB/MySQL, DuckDB, Firebird, MS-Access, MS-SQL Server, Oracle, ODBC DSN). Provides metacommands for import/export, data copying between databases, conditional execution, and substitution variables. Originally a 16,900-line Python monolith.

______________________________________________________________________

## Repository Structure

```
_execsql/   # original upstream monolith — reference only, do not edit
  execsql.py               # upstream v1.130.1, ~16,627 lines, kept for diffing/reference
src/execsql/               # active codebase — all new work goes here
  __init__.py              # version via importlib.metadata
  __main__.py              # entry point → cli.main()
  cli/
    __init__.py            # Typer app, main() command, _legacy_main()
    dsn.py                 # connection string / DSN URL parsing
    help.py                # Rich console, --help metacommand/encoding display
    run.py                 # _run() — core CLI execution logic
  config.py                # StatObj, ConfigData, WriteHooks
  constants.py             # map tile servers, X11 bitmaps, color names
  exceptions.py            # ExecSqlError base + ErrInfo, DataTypeError, DbTypeError, etc.
  format.py                # execsql-format CLI (Typer) + format_file()
  models.py                # Column, DataTable, JsonDatatype (type inference)
  parser.py                # CondParser, NumericParser, AST nodes
  state.py                 # module-level global runtime state
  types.py                 # DataType subclasses + DbType dialect mappings
  db/
    __init__.py
    base.py                # Database ABC + DatabasePool
    access.py / dsn.py / sqlserver.py / postgres.py
    oracle.py / sqlite.py / duckdb.py / mysql.py / firebird.py
    factory.py             # db_* convenience constructors
  exporters/
    __init__.py
    base.py                # ExportRecord, ExportMetadata, WriteSpec
    delimited.py / json.py / xml.py / html.py / latex.py
    ods.py / xls.py / zip.py / raw.py / pretty.py
    values.py / templates.py / feather.py / duckdb.py / sqlite.py
  importers/
    __init__.py
    base.py / csv.py / ods.py / xls.py / feather.py
  metacommands/
    __init__.py            # DISPATCH_TABLE, format/db constants, re-exports all handlers
    dispatch.py            # build_dispatch_table() — all mcl.add() regex registrations
    conditions.py          # xf_* conditional tests + CONDITIONAL_TABLE
    connect.py             # x_connect_* database connection handlers
    control.py             # loops, batches, includes, error control, SET
    data.py                # x_export, x_import
    debug.py               # x_debug_write_metacommands
    io.py                  # re-export façade for io_export/io_import/io_write/io_fileops
    io_export.py / io_import.py / io_write.py / io_fileops.py
    prompt.py              # GUI dialogs: ACTION, MESSAGE, DISPLAY, ENTRY…
    script_ext.py          # EXTEND/APPEND SCRIPT
    system.py              # SHELL, ON ERROR/CANCEL_HALT, CONSOLE, EMAIL
  script/
    __init__.py            # re-exports from engine.py, control.py, variables.py
    engine.py              # MetaCommand, MetaCommandList, CommandList, ScriptFile, runscripts()
    control.py             # BatchLevels, IfItem, IfLevels
    variables.py           # SubVarSet, CounterVars, LocalSubVarSet, ScriptArgSubVarSet
  gui/
    __init__.py            # get_backend(), gui_manager_loop()
    base.py                # GuiBackend ABC
    console.py             # ConsoleBackend (text-only fallback)
    desktop.py             # TkinterBackend (full GUI)
    tui.py                 # TextualBackend (TUI)
  utils/
    __init__.py
    auth.py / crypto.py / datetime.py / errors.py / fileio.py
    gui.py / mail.py / numeric.py / regex.py / strings.py / timer.py
docs/                      # MkDocs pages (Zensical builder, Material theme)
  index.md
  getting-started/         # installation, requirements, syntax
  reference/               # configuration, substitution_vars, metacommands, security
  guides/                  # usage, sql_syntax, logging, encoding, debugging, examples, etc.
  about/                   # copyright, contributors, change_log (auto-generated)
  api/                     # mkdocstrings API reference
  dev/                     # contributor guides (adding metacommands/exporters/etc.)
  images/
extras/
  vscode-execsql/          # VS Code syntax highlighting extension (repo-only, not in wheel)
    package.json
    syntaxes/
      execsql.tmLanguage.json  # auto-generated via scripts/generate_vscode_grammar.py
scripts/
  generate_vscode_grammar.py   # generates tmLanguage.json from --dump-keywords
templates/                 # SQL templates + config files
tests/
  test_package.py          # import hygiene, version string
  test_registry.py         # keyword consistency (dispatch table ↔ grammar ↔ CLI)
  test_cli_e2e.py          # 26 end-to-end CLI tests via subprocess
  test_config.py           # ConfigData tests
  metacommands/            # metacommand handler unit tests
  integration/             # SQLite/PostgreSQL/MySQL integration tests
  utils/                   # utility module tests
  gui/                     # GUI backend tests
.github/workflows/
  ci-cd.yml                # CI/CD pipeline (see below)
.pre-commit-config.yaml
justfile                   # task runner (just lint, test, docs, bump-*)
pyproject.toml             # build config
zensical.toml              # docs site config (nav, theme, plugins)
CHANGELOG.md
CLAUDE.md                  # agent instructions
.claude/
  project_context.md       # this file
  agents/                  # SQL Syndicate agent prompts
  commands/                # slash command definitions
```

______________________________________________________________________

## Tooling Decisions

| Tool                | Purpose                  | Decision                                                                                                |
| ------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------- |
| `uv`                | Package/env management   | Chosen over pip/poetry                                                                                  |
| `hatchling`         | Build backend            | via pyproject.toml                                                                                      |
| `ruff`              | Lint + format            | Aggressively configured — B904, E722, E721 enforced; see pyproject.toml for remaining suppressions      |
| `tox-uv`            | Multi-Python test matrix | py310–py314                                                                                             |
| `bump-my-version`   | Version bumping          | tags + commits, hooks run `uv lock`                                                                     |
| `just`              | Task runner              | `lint`, `test`, `test-all`, `docs`, `docs-serve`, `bump-*`, `install-vscode`                            |
| `pre-commit`        | Git hooks                | gitleaks, uv-lock, ruff, mdformat, markdownlint, typos, validate-pyproject                              |
| `zensical`          | Docs builder             | MkDocs-compatible, Material theme, configured via `zensical.toml`                                       |
| `mkdocstrings`      | API docs from docstrings | Wired up — `docs/api/` pages auto-generate from source                                                  |
| `pytest-cov`        | Coverage                 | `--cov-fail-under=80` enforced                                                                          |

## Package Layout Decision

The source package is `src/execsql/` (not `src/execsql2/`). The PyPI name is `execsql2` but the importable module is `execsql`. The CLI entry point is `execsql2 = "execsql.__main__:main"`. Templates are installed as package data at `execsql2_extras/`.

## Python Version Support

Requires Python >=3.10. CI matrix: 3.10, 3.11, 3.12, 3.13, 3.14. All three OS runners (ubuntu, macos, windows). Integration tests on 3.13.

## Optional Dependencies

Database drivers are optional extras:

- `postgres` → psycopg2-binary
- `mysql` → pymysql
- `mssql` / `odbc` → pyodbc
- `duckdb` → duckdb
- `firebird` → firebird-driver
- `oracle` → oracledb
- `ods` → odfpy
- `excel` → xlrd, openpyxl
- `jinja` → Jinja2
- `all` → everything except firebird/oracle

## CI/CD Pipeline (`.github/workflows/ci-cd.yml`)

Triggered on: push to `main`, any tag `v*.*.*`, pull requests.

1. **tests** — matrix across os × python-version, runs `tox -e py`
2. **integration-tests** — SQLite + PostgreSQL + MySQL via Docker services (py3.13)
3. **build** — runs only on `v*.*.*` tags, builds sdist + wheel with `python -m build`, checks with twine
4. **publish** — pushes to PyPI via `pypa/gh-action-pypi-publish` (OIDC trusted publishing, `pypi` environment)
5. **generate-release** — creates GitHub Release with dist artifacts and auto-generated release notes

**After every bump + push:** always `git push && git push --tags`, then `gh run watch <id> --exit-status` to monitor CI. Failures on bump commits need immediate attention since they trigger PyPI publish.

## Versioning

`bump-my-version` manages versions. Current: `2.5.0`. Bump commands:

- `just bump-patch` → 2.5.0 → 2.5.1
- `just bump-minor` → 2.5.0 → 2.6.0
  Bumps commit + tag. Pre-commit hook runs `uv lock` + stages `uv.lock`.

## Ruff Config

`target-version = "py310"`, `line-length = 120`. Rules enabled: E, W, F, I, B, N, SIM, UP, A. Notable suppressions with reasons documented in pyproject.toml — see that file for details. B904 (raise-without-from) is enforced.

## Keyword Registry & VS Code Extension

The dispatch table is the single source of truth for all metacommand keywords. Every `mcl.add()` call in `metacommands/dispatch.py` has `description=` (keyword name) and `category=` (one of: `control`, `block`, `action`, `config`, `config_option`, `prompt`). Conditional functions in `conditions.py` use `category="condition"`.

- `execsql --dump-keywords` introspects the dispatch table at runtime and outputs structured JSON
- `scripts/generate_vscode_grammar.py` consumes that JSON to produce `extras/vscode-execsql/syntaxes/execsql.tmLanguage.json`
- `tests/test_registry.py` validates keyword consistency across dispatch table, CLI output, and grammar
- Export format constants (`QUERY_EXPORT_FORMATS`, `TABLE_EXPORT_FORMATS`, etc.) are centralized in `metacommands/__init__.py`
- The VS Code extension lives at `extras/vscode-execsql/` — it is NOT included in the Python wheel (it's an editor extension, not a library). Install via `just install-vscode` (symlinks into `~/.vscode/extensions/`).

**When adding a new metacommand:** add `description=` and `category=` to the `mcl.add()` call in `dispatch.py`, then run `just install-vscode` to regenerate the grammar.

______________________________________________________________________

## Roadmap

Milestones are v2.x minor releases. Python 3.10 support is maintained for
the foreseeable future.

### Completed

| Item                                              | Version        | Date    |
| ------------------------------------------------- | -------------- | ------- |
| Monolith → modular refactor (80+ files)           | 2.0.0a1–2.1.0 | 2026-03 |
| 30+ security/correctness fixes (ANALYSIS.md)      | 2.1.x          | 2026-03 |
| mkdocstrings API docs wired up                    | 2.1.0          | 2026-03 |
| `execsql-format` surfaced in README + docs nav    | 2.1.0          | 2026-03 |
| Coverage floor raised to 80% (2,596 tests)        | 2.4.x          | 2026-03 |
| Orphaned optional features cleaned up             | 2.1.0          | 2026-03 |
| Keyring auth, Parquet/Feather/HDF5 export, DuckDB | 2.1.0          | 2026-03 |
| Progress bars, SQL audit logging                  | 2.2.x          | 2026-03 |
| Full monolith parity verified + 14 missing patterns fixed | 2.4.5  | 2026-03 |
| Exception hierarchy (`ExecSqlError` base)         | 2.1.0          | 2026-03 |
| `py.typed` marker                                 | 2.1.0          | 2026-03 |
| Exception chaining + B904 enforced                | 2.4.6          | 2026-03 |
| `__all__` exports on 18 public modules            | 2.4.6          | 2026-03 |
| End-to-end CLI tests (26 tests)                   | 2.4.6          | 2026-03 |
| CONTRIBUTING.md                                   | 2.3.x          | 2026-03 |
| Security docs (`docs/reference/security.md`)      | 2.3.x          | 2026-03 |
| E722/E721 ruff enforcement                        | 2.3.x          | 2026-03 |
| Lazy import cleanup (zero instances)              | 2.3.x          | 2026-03 |
| Docs reorganized (getting-started/reference/guides/about) | 2.4.6  | 2026-03 |
| Pre-commit hook for `execsql-format`              | 2.4.3          | 2026-03 |
| VS Code syntax highlighting extension             | 2.4.x          | 2026-03 |
| Docstring coverage 81% on public API              | 2.5.0          | 2026-04 |
| Developer architecture guide with Mermaid diagrams | 2.5.0          | 2026-04 |
| Cursor context managers (exec_cmd + vacuum)       | 2.5.0          | 2026-04 |
| Exporter Protocol types (QueryExporter, RowsetExporter) | 2.5.0   | 2026-04 |
| SubVarSet.merge() optimization (O(1) vs O(V))    | 2.5.0          | 2026-04 |
| GitHub Actions upgraded to Node.js 24             | 2.5.0          | 2026-04 |
| GitHub issue/PR templates + SECURITY.md           | 2.5.0          | 2026-04 |
| Database ABC already in place (verified)          | 2.5.0          | 2026-04 |
| Dispatch optimization already in place (verified) | 2.5.0          | 2026-04 |
| PostgreSQL integration tests (9 tests, CI Docker) | 2.5.0          | 2026-04 |
| MySQL integration tests (9 tests, CI Docker)      | 2.5.0          | 2026-04 |

______________________________________________________________________

### v2.6 — Architecture & Internal Quality

- [x] **`state.py` → `RuntimeContext` refactor** — 33 mutable globals consolidated into a slotted `RuntimeContext` class with transparent module proxy. `get_context()`/`set_context()` API added. Zero external call-site changes.
- [x] **`noqa` cleanup in `metacommands/__init__.py`** — removed all 180 redundant `# noqa` comments; `__all__` already satisfies ruff F401.
- [x] **Coverage push to 86%** — 403 new tests (3010 total) covering `db/base.py` (55→99%), `metacommands/connect.py` (36→100%), `script/engine.py` (77→95%), `exporters/delimited.py` (76→95%). Remaining gap to 90% is in GUI, ODS, and import handlers.

### v2.7 — New Export/Import Formats

- [x] **Parquet import** — already existed as `IMPORT TO table FROM PARQUET file` (verified present).
- [x] **YAML export** — `FORMAT YAML` via PyYAML, list-of-dicts with native type preservation.
- [x] **Markdown (GFM) export** — `FORMAT MARKDOWN` / `MD`, pipe tables with alignment and escaping.
- [x] **Excel (XLSX) multi-sheet export** — `FORMAT XLSX` single + multi-sheet via openpyxl, bold headers, inventory sheet, sheet name deduplication.

### v2.8 — Scripting Power Features

- [ ] **`ASSERT` metacommand** — `-- !x! ASSERT <condition> "message"`. Data validation for CI pipelines and sanity checks.
- [ ] **`--dry-run` improvements** — show SQL with substitution variables expanded, not just raw metacommands.
- [ ] **Script profiling (`--profile`)** — per-statement execution times, summary report at end. Leverages existing `Timer` infrastructure.
- [ ] **Parallel execution blocks** — `PARALLEL BEGIN ... PARALLEL END` for independent statements. See design notes below.

### v2.9 — Library API & Developer Experience

- [ ] **Programmatic Python API** — `execsql.run(script, db=...)` for notebook/pipeline usage. Depends on `RuntimeContext` refactor.
- [ ] **TOML configuration** — `execsql.toml` as modern alternative to legacy INI format (coexist initially).

### v2.10 — Testing & CI Hardening

- [ ] **Property-based testing (Hypothesis)** — for parsers, type inference, substitution variables.
- [ ] **Parser fuzzing** — `CondParser` and `NumericParser` handle arbitrary user input; fuzz for edge cases.
- [ ] **Nightly CI against latest DB driver versions** — catch upstream breakage in psycopg2, pymysql, duckdb, etc.
- [ ] **CI benchmarks** — track substitution variable and dispatch performance over time.

### v2.11 — Documentation & Community

- [ ] **Cookbook / recipes page** — real-world examples: ETL workflows, HTML reports, data validation pipelines.
- [ ] **Migration guide from upstream execsql** — what changed, what's new, how to switch.
- [ ] **Interactive tutorial** — guided walkthrough script against a bundled SQLite DB.

### v3.0+ — Future

- [ ] **Plugin system** — entry points for `execsql.exporters`, `execsql.importers`, `execsql.metacommands` allowing external packages to register new handlers.
- [ ] **LSP / language server** — for the VS Code extension: autocomplete metacommands, validate substitution variables, jump-to-definition for `INCLUDE`d scripts.

______________________________________________________________________

### Ongoing / No-milestone

- Textual TUI polish

______________________________________________________________________

### Design Notes: Parallel Execution Blocks

**Concept:** Allow users to declare groups of independent SQL statements that
can run concurrently, reducing wall-clock time for ETL scripts with
independent work.

**Syntax:**
```sql
-- !x! PARALLEL BEGIN [WORKERS=4]
INSERT INTO summary_a SELECT ... FROM raw_data;
INSERT INTO summary_b SELECT ... FROM raw_data;
INSERT INTO summary_c SELECT ... FROM raw_data;
-- !x! PARALLEL END
```

**How it would work in the engine:**

1. When `runscripts()` encounters `PARALLEL BEGIN`, the engine enters a
   "collecting" mode (similar to how `LOOP` compiles commands into a
   `CommandList` before executing). Statements are accumulated but not run.

2. On `PARALLEL END`, the collected statements are dispatched to a
   `concurrent.futures.ThreadPoolExecutor` (or `ProcessPoolExecutor`).
   Each statement gets its own database cursor (or connection from
   `DatabasePool`).

3. The main `runscripts()` loop blocks at the `PARALLEL END` until all
   futures complete. Errors from any worker are collected and raised as
   a combined `ErrInfo`.

**Key constraints and design decisions:**

- **No shared mutable state inside parallel blocks.** Substitution variable
  writes (`SET`), `IF/ELSE`, `LOOP`, `INCLUDE`, and other control-flow
  metacommands are **prohibited** inside `PARALLEL` blocks — only raw SQL
  and simple export metacommands are allowed. The parser rejects anything
  else at compile time.

- **Connection handling.** Each parallel worker needs its own cursor or
  connection. `DatabasePool` already exists in `db/base.py` but currently
  manages one connection per named alias. This would need a pool-per-alias
  model (e.g., min/max connections) or each worker opens a fresh connection
  from the same DSN.

- **Depends on `RuntimeContext` refactor.** The current `state.py` globals
  (especially `commandliststack`, `if_stack`, `subvars`) are not
  thread-safe. Workers would need isolated read-only snapshots of
  substitution variables and their own cursor state. The `RuntimeContext`
  work in v2.6 is a prerequisite.

- **`WORKERS=N`** defaults to `min(len(statements), os.cpu_count())`.
  Configurable via the metacommand or `execsql.toml`.

- **Transaction semantics.** Each statement runs in its own implicit
  transaction (autocommit). If the user needs atomicity across the whole
  block, they wrap it in `BEGIN BATCH ... END BATCH` outside the parallel
  block — but that negates parallelism for most backends, so this is
  mainly useful for independent ETL loads.

______________________________________________________________________

## Open Design Questions

### Distribution / single-file invocation model

**Decision:** `uv tool install execsql2` / `pipx install execsql2` is the supported install path. No zipapp or wrapper artifacts. Keep the modular package structure as-is.

______________________________________________________________________

## Working with Claude

Claude operates as a senior Python engineer on this project. The following principles govern all collaboration:

**Craft over convenience.** Do what is right and necessary, not merely what is easiest. Quick hacks and shortcuts that accrue technical debt are explicitly unwanted. If the correct solution is harder, do it the correct way.

**Deliberate decision-making.** Before proposing or implementing anything non-trivial, consider the full solution space. Weigh trade-offs explicitly. Recommend the best option with clear reasoning — don't default to the first plausible approach.

**No artificial time pressure.** Time is not a constraint. Quality, correctness, and long-term maintainability take priority over speed. Never cut corners to go faster.

**Best practices and standards are the baseline.** Follow Python community conventions (PEP 8, PEP 257, PEP 20), modern Python 3 idioms, and established patterns for the tools in use (pytest, ruff, uv, hatchling, mkdocs, etc.). If a standard exists, follow it unless there is a documented reason not to.

**Understand before acting.** Read and fully understand existing code before suggesting or making changes. Never propose modifications to code that hasn't been read. Respect the intent behind existing decisions — check this file and the memory store for prior context.

**Minimal surface area.** Only change what is directly requested or clearly necessary. Avoid scope creep, gold-plating, and unsolicited refactoring. A focused change is better than a broad one.

**Secure by default.** Never introduce security vulnerabilities. Validate at system boundaries; trust internal code. Flag any concerns about existing security posture when encountered.

**Honesty over agreeableness.** If a proposed direction is wrong, suboptimal, or in conflict with best practices, say so clearly and explain why. Provide the correct alternative. Flatly accepting bad ideas is not helpful.

______________________________________________________________________

## Monolith → Refactor Mapping

The table below maps each major section of the 16,627-line monolith
(`_execsql/execsql.py`) to the corresponding new module(s) in
`src/execsql/`. Use this to compare old vs new when porting or verifying
behavior.

| Monolith Section (lines)                                                                                                                                                                                                        | New Module(s)                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Module header, imports, lazy globals (1–122)                                                                                                                                                                                    | `state.py`, `__init__.py`                                                                                                                                                                                                                                                                                                                                                                                              |
| **GLOBAL VARIABLES** — runtime state, regexes (123–435)                                                                                                                                                                         | `state.py`                                                                                                                                                                                                                                                                                                                                                                                                             |
| **STATUS RECORDING** — `StatObj`, `ConfigError`, `ConfigData` (438–921)                                                                                                                                                         | `config.py`, `exceptions.py`                                                                                                                                                                                                                                                                                                                                                                                           |
| **SUPPORT FUNCTIONS AND CLASSES (1)** — regex builders, string utilities (926–1218)                                                                                                                                             | `utils/regex.py`, `utils/strings.py`                                                                                                                                                                                                                                                                                                                                                                                   |
| **ALARM TIMER** — `TimeoutError`, `TimerHandler` (1220–1245)                                                                                                                                                                    | `utils/timer.py`, `exceptions.py`                                                                                                                                                                                                                                                                                                                                                                                      |
| **EXPORT METADATA RECORDS** — `ExportRecord`, `ExportMetadata` (1250–1292)                                                                                                                                                      | `exporters/base.py`                                                                                                                                                                                                                                                                                                                                                                                                    |
| **FILE I/O** — `GetChar`, `FileWriter`, `EncodedFile`, `WriteableZipfile`, `WriteSpec`, `Logger`, `TempFileMgr`, ODS/XLS/XLSX file classes (1297–2298)                                                                          | `utils/fileio.py`, `exporters/zip.py`, `exporters/ods.py`, `exporters/xls.py`                                                                                                                                                                                                                                                                                                                                          |
| **SIMPLE ENCRYPTION** — `Encrypt` (2301–2339)                                                                                                                                                                                   | `utils/crypto.py`                                                                                                                                                                                                                                                                                                                                                                                                      |
| **EMAIL** — `Mailer`, `MailSpec` (2344–2454)                                                                                                                                                                                    | `utils/mail.py`                                                                                                                                                                                                                                                                                                                                                                                                        |
| **TIMER** — `Timer` (2458–2480)                                                                                                                                                                                                 | `utils/timer.py`                                                                                                                                                                                                                                                                                                                                                                                                       |
| **ERROR HANDLING** — `ErrInfo`, `exception_info()`, `exit_now()`, `fatal_error()` (2483–2674)                                                                                                                                   | `exceptions.py`, `utils/errors.py`                                                                                                                                                                                                                                                                                                                                                                                     |
| **DATA TYPES** — `DataType` base + 14 subclasses (2678–3167)                                                                                                                                                                    | `types.py`                                                                                                                                                                                                                                                                                                                                                                                                             |
| **DATABASE TYPES** — `DbTypeError`, `DbType` per-DBMS type mapping (3171–3412)                                                                                                                                                  | `types.py`, `exceptions.py`                                                                                                                                                                                                                                                                                                                                                                                            |
| **COLUMNS AND TABLES** — `ColumnError`, `Column`, `DataTableError`, `DataTable` (3416–3630)                                                                                                                                     | `models.py`, `exceptions.py`                                                                                                                                                                                                                                                                                                                                                                                           |
| **JSON SCHEMA TYPES** — `JsonDatatype` (3634–3673)                                                                                                                                                                              | `models.py`                                                                                                                                                                                                                                                                                                                                                                                                            |
| **DATABASE CONNECTIONS** — `Database` base + 9 subclasses, `DatabasePool` (3678–5412)                                                                                                                                           | `db/base.py`, `db/access.py`, `db/dsn.py`, `db/sqlserver.py`, `db/postgres.py`, `db/oracle.py`, `db/sqlite.py`, `db/duckdb.py`, `db/mysql.py`, `db/firebird.py`                                                                                                                                                                                                                                                        |
| **CSV FILES** — `LineDelimiter`, `DelimitedWriter`, `CsvWriter`, `CsvFile`, `ZipWriter` (5416–6136)                                                                                                                             | `exporters/delimited.py`, `exporters/zip.py`                                                                                                                                                                                                                                                                                                                                                                           |
| **TEMPLATE-BASED REPORTS/EXPORTS** — `StrTemplateReport`, `JinjaTemplateReport`, `AirspeedTemplateReport` (6140–6249)                                                                                                           | `exporters/templates.py`                                                                                                                                                                                                                                                                                                                                                                                               |
| **SCRIPTING** — `BatchLevels`, `IfLevels`, `CounterVars`, `SubVarSet`, `MetaCommand`, `MetaCommandList`, `SqlStmt`, `MetacommandStmt`, `ScriptCmd`, `CommandList`, loops, `ScriptFile`, `ScriptExecSpec`, `GuiSpec` (6254–6974) | `script/engine.py`, `script/control.py`, `script/variables.py`, `utils/gui.py`                                                                                                                                                                                                                                                                                                                                         |
| **UI** — Tkinter GUI classes (6979–9508)                                                                                                                                                                                        | `gui/desktop.py` (TkinterBackend), `gui/base.py`, `gui/console.py`, `gui/tui.py`                                                                                                                                                                                                                                                                                                                                      |
| **PARSERS** — `SourceString`, `CondParser`, `NumericParser`, AST nodes (9512–9821)                                                                                                                                              | `parser.py`                                                                                                                                                                                                                                                                                                                                                                                                            |
| **METACOMMAND FUNCTIONS** — ~200 `x_*` handler functions + registrations (9826–13781)                                                                                                                                           | `metacommands/dispatch.py`, `metacommands/connect.py`, `metacommands/control.py`, `metacommands/data.py`, `metacommands/debug.py`, `metacommands/io*.py`, `metacommands/prompt.py`, `metacommands/script_ext.py`, `metacommands/system.py`                                                                                                                                                                              |
| **CONDITIONAL TESTS** — `xf_*` functions + registrations (13785–14163)                                                                                                                                                          | `metacommands/conditions.py`                                                                                                                                                                                                                                                                                                                                                                                           |
| Utility functions: `chainfuncs`, `write_warning`, `parse_datetime`, `parse_datetimetz` (14164–14371)                                                                                                                            | `utils/errors.py`, `utils/datetime.py`                                                                                                                                                                                                                                                                                                                                                                                 |
| `set_system_vars()`, `substitute_vars()` (14373–14423)                                                                                                                                                                          | `script/engine.py`                                                                                                                                                                                                                                                                                                                                                                                                     |
| `runscripts()`, `current_script_line()`, `read_sqlfile()` (14425–14602)                                                                                                                                                         | `script/engine.py`                                                                                                                                                                                                                                                                                                                                                                                                     |
| Export/import helpers: `write_delimited_file`, `write_query_to_*`, `export_*`, `import*`, `pause`, `get_password` (14604–15874)                                                                                                 | `exporters/delimited.py`, `exporters/json.py`, `exporters/xml.py`, `exporters/html.py`, `exporters/latex.py`, `exporters/ods.py`, `exporters/xls.py`, `exporters/raw.py`, `exporters/feather.py`, `exporters/pretty.py`, `exporters/values.py`, `exporters/duckdb.py`, `exporters/sqlite.py`, `importers/csv.py`, `importers/ods.py`, `importers/xls.py`, `importers/feather.py`, `importers/base.py`, `utils/auth.py` |
| GUI bridge functions: `gui_credentials`, `gui_connect`, `gui_console_*` (15875–16052)                                                                                                                                           | `utils/gui.py`                                                                                                                                                                                                                                                                                                                                                                                                         |
| `wo_quotes`, `get_subvarset`, `db_*` convenience constructors (16053–16134)                                                                                                                                                     | `utils/strings.py`, `db/factory.py`                                                                                                                                                                                                                                                                                                                                                                                    |
| `list_metacommands()`, `list_encodings()` (16135–16229)                                                                                                                                                                         | `cli/help.py`                                                                                                                                                                                                                                                                                                                                                                                                          |
| `clparser()` — CLI option definitions (16236–16309)                                                                                                                                                                             | `cli/__init__.py` (Typer-based)                                                                                                                                                                                                                                                                                                                                                                                        |
| **GLOBAL OBJECTS** — module-level singleton instantiations (16316–16366)                                                                                                                                                        | `state.py`, `state.initialize()`                                                                                                                                                                                                                                                                                                                                                                                       |
| `main()` (16372–16627)                                                                                                                                                                                                          | `cli/run.py` (_run())                                                                                                                                                                                                                                                                                                                                                                                                  |

### Coverage Notes

- **Tkinter GUI classes** (lines 6979–9508, ~2,530 lines): **Ported** to
    `src/execsql/gui/desktop.py` as `MsgDialog`, `PauseDialog`, `DisplayDialog`,
    `EntryFormDialog`, `CompareDialog`, `SelectRowsDialog`, `SelectSubDialog`,
    `ActionDialog`, `MapDialog`, `CredentialsDialog`, `ConnectDialog`, and
    `ConsoleWindow` (with progress bar, save, and status). `TkinterBackend`
    wraps all dialogs and the console window. `utils/gui.py` provides the
    full public API for the rest of the codebase.
- All other sections are ported. The new modular structure maps cleanly to
    the monolith sections above.

______________________________________________________________________

## Superseded Monolith Index

**File:** `_execsql/execsql.py`
**Version:** 1.130.1 (2024-09-28) — upstream final release by Dreas Nielsen
**Size:** 16,627 lines
**Status:** Reference only. Do not edit. Used for diffing, porting, and understanding legacy behavior.

### Execution Flow

```
main()
  → clparser()           # optparse-based CLI (lines 16236–16309)
  → ConfigData(...)      # load execsql.conf
  → db_<Type>(...)       # open initial database connection
  → read_sqlfile(...)    # parse script into CommandList
  → runscripts()         # central dispatch loop (line 14425)
      └── CommandList.run_next()
              ├── SqlStmt.run()        # executes SQL via db
              └── MetacommandStmt.run()
                      └── MetaCommandList → MetaCommand.run()
                              └── x_<name>(**kwargs) / xf_<name>(**kwargs)
```

`runscripts()` (line 14425) is the central loop: pops the top `CommandList` from `commandliststack`, calls `run_next()` until `StopIteration`, then pops the stack. Metacommands may push new `CommandList` entries (e.g., `INCLUDE`, `EXECUTE SCRIPT`, `LOOP`).
