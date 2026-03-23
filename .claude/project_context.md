______________________________________________________________________

## name: execsql2 project context description: Canonical project context for execsql2 — origin, tooling, roadmap, collaboration norms, and monolith index type: project

# execsql2 Project Context

> **Canonical location:** `.claude/project_context.md` in the repo.
> Global memory (`~/.claude/projects/.../memory/`) mirrors this — the repo file is the source of truth.
> Update this file whenever any architectural, tooling, or directional decision is made.

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
  __init__.py              # version = "1.130.1"
  __main__.py              # entry point → main()
  cli.py                   # argparse CLI + main() orchestration
  config.py                # StatObj, ConfigData, WriteHooks
  constants.py             # map tile servers, X11 bitmaps, color names
  exceptions.py            # custom exception hierarchy
  models.py                # Column, DataTable, JsonDatatype (type inference)
  parser.py                # CondParser, NumericParser, AST nodes
  script.py                # SubVarSet, CommandList, runscripts(), read_sqlfile()
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
    __init__.py            # DISPATCH_TABLE — all metacommand registrations
    conditions.py          # xf_* conditional tests + IF/ELSEIF/ELSE/ENDIF
    connect.py             # x_connect_* database connection handlers
    control.py             # loops, batches, includes, error control, SET
    data.py                # x_export, x_import
    debug.py               # x_debug_write_metacommands
    io.py                  # WRITE, PAUSE, file management, log
    prompt.py              # GUI dialogs: ACTION, MESSAGE, DISPLAY, ENTRY…
    script_ext.py          # EXTEND SCRIPT
    system.py              # SHELL command execution
  utils/
    __init__.py
    auth.py / crypto.py / datetime.py / errors.py / fileio.py
    gui.py / mail.py / numeric.py / regex.py / strings.py / timer.py
docs/               # 18 MkDocs Markdown pages (Material theme)
templates/          # SQL templates + config files
tests/
  test_placeholder.py
.github/workflows/
  ci-cd.yml         # CI/CD pipeline (see below)
.pre-commit-config.yaml
justfile            # task runner (just lint, test, docs, bump-*)
pyproject.toml      # build config
mkdocs.yaml
CHANGELOG.md
.claude/
  project_context.md  # this file
  settings.local.json
```

______________________________________________________________________

## Tooling Decisions

| Tool                | Purpose                  | Decision                                                                     |
| ------------------- | ------------------------ | ---------------------------------------------------------------------------- |
| `uv`                | Package/env management   | Chosen over pip/poetry                                                       |
| `hatchling`         | Build backend            | via pyproject.toml                                                           |
| `ruff`              | Lint + format            | Permissive config during migration, tighten during refactor                  |
| `tox-uv`            | Multi-Python test matrix | py310–py313                                                                  |
| `bump-my-version`   | Version bumping          | tags + commits, hooks run `uv lock`                                          |
| `just`              | Task runner              | `lint`, `test`, `test-all`, `docs`, `docs-serve`, `bump-patch`, `bump-minor` |
| `pre-commit`        | Git hooks                | gitleaks, uv-lock, ruff, mdformat, markdownlint, typos, validate-pyproject   |
| `mkdocs` + Material | Docs site                | converted from Sphinx/RST                                                    |
| `mkdocstrings`      | API docs from docstrings | installed, not yet wired in                                                  |
| `pytest-cov`        | Coverage                 | configured, `--cov-fail-under` commented out until tests are written         |

## Package Layout Decision

The source package is `src/execsql/` (not `src/execsql2/`). The PyPI name is `execsql2` but the importable module is `execsql`. The CLI entry point is `execsql2 = "execsql.__main__:main"`. Templates are installed as package data at `execsql2_extras/`.

## Python Version Support

Requires Python >=3.10. CI matrix: 3.10, 3.11, 3.12, 3.13. All three OS runners (ubuntu, macos, windows).

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
1. **build** — runs only on `v*.*.*` tags, builds sdist + wheel with `python -m build`, checks with twine
1. **publish** — pushes to PyPI via `pypa/gh-action-pypi-publish` (OIDC trusted publishing, `pypi` environment)
1. **generate-release** — creates GitHub Release with dist artifacts and auto-generated release notes

## Versioning

`bump-my-version` manages versions. Current: `1.130.1`. Bump commands:

- `just bump-patch` → 1.130.1 → 1.130.2
- `just bump-minor` → 1.130.1 → 1.131.0
    Bumps commit + tag. Pre-commit hook runs `uv lock` + stages `uv.lock`.

## Ruff Config

`target-version = "py313"`, `line-length = 120`. Currently permissive — many legacy rules ignored (tabs, bare except, ambiguous names, unused imports, etc.). Intent is to tighten rules progressively during refactor.

## Known Issues / Docs Debt

- ~20 in-page anchor links use RST label names that differ from heading text (e.g. `#if_cmd`, `#beginsql`). Need explicit `{ #anchor }` heading IDs added to the relevant markdown headings.
- Docs converted from Sphinx/RST — some formatting artifacts may remain.

## Roadmap / Open Work

1. **Docs cleanup** — fix lingering RST→Markdown formatting issues; add explicit anchor IDs
1. **Ruff tightening** - Progressive modernization — enable stricter Ruff rules, remove Py2 compat remnants, modernize idioms
1. **Integration tests (next)** - Expand coverage for: exporters/{sqlite,duckdb,templates,xls,ods,feather}, metacommands/conditions, metacommands/connect (SQLite), db/base deeper methods, format.py

## Open Design Questions

### Distribution / single-file invocation model

The original monolith could be dropped anywhere and run as `execsql.py <script>` with the directory on PATH. The refactored package no longer supports this directly. Two non-exclusive paths forward (decide post-refactor):

- **Primary: `uv tool install` / `pipx install`** — already works today. Gives every user a global `execsql2` CLI entry point, isolated and versioned. Strictly better than directory-PATH for managed environments.
- **Complement: `zipapp` artifact** — `python -m zipapp src/execsql -o execsql2.pyz -m execsql.__main__:main` produces a single executable `.pyz` that can be dropped anywhere and run with any compatible Python. No install required. Best fit for shared servers, airgapped machines, or sysadmins who want a file they can distribute. Would be an optional artifact in GitHub Releases, built via `just`.

`shiv` (zipapp with bundled deps) is a heavier alternative to zipapp but unnecessary given that DB drivers are optional and platform-specific anyway.

**Decision:** Option A only. `uv tool install execsql2` / `pipx install execsql2` is the supported install path. No zipapp or wrapper artifacts. Keep the modular package structure as-is.

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
| **SCRIPTING** — `BatchLevels`, `IfLevels`, `CounterVars`, `SubVarSet`, `MetaCommand`, `MetaCommandList`, `SqlStmt`, `MetacommandStmt`, `ScriptCmd`, `CommandList`, loops, `ScriptFile`, `ScriptExecSpec`, `GuiSpec` (6254–6974) | `script.py`, `utils/gui.py`                                                                                                                                                                                                                                                                                                                                                                                            |
| **UI** — Tkinter GUI classes (6979–9508)                                                                                                                                                                                        | `utils/gui.py` (stubs/no-ops; Tkinter classes not yet ported)                                                                                                                                                                                                                                                                                                                                                          |
| **PARSERS** — `SourceString`, `CondParser`, `NumericParser`, AST nodes (9512–9821)                                                                                                                                              | `parser.py`                                                                                                                                                                                                                                                                                                                                                                                                            |
| **METACOMMAND FUNCTIONS** — ~200 `x_*` handler functions + registrations (9826–13781)                                                                                                                                           | `metacommands/__init__.py`, `metacommands/conditions.py`, `metacommands/connect.py`, `metacommands/control.py`, `metacommands/data.py`, `metacommands/debug.py`, `metacommands/io.py`, `metacommands/prompt.py`, `metacommands/script_ext.py`, `metacommands/system.py`                                                                                                                                                |
| **CONDITIONAL TESTS** — `xf_*` functions + registrations (13785–14163)                                                                                                                                                          | `metacommands/conditions.py`                                                                                                                                                                                                                                                                                                                                                                                           |
| Utility functions: `chainfuncs`, `write_warning`, `parse_datetime`, `parse_datetimetz` (14164–14371)                                                                                                                            | `utils/errors.py`, `utils/datetime.py`                                                                                                                                                                                                                                                                                                                                                                                 |
| `set_system_vars()`, `substitute_vars()` (14373–14423)                                                                                                                                                                          | `script.py`                                                                                                                                                                                                                                                                                                                                                                                                            |
| `runscripts()`, `current_script_line()`, `read_sqlfile()` (14425–14602)                                                                                                                                                         | `script.py`                                                                                                                                                                                                                                                                                                                                                                                                            |
| Export/import helpers: `write_delimited_file`, `write_query_to_*`, `export_*`, `import*`, `pause`, `get_password` (14604–15874)                                                                                                 | `exporters/delimited.py`, `exporters/json.py`, `exporters/xml.py`, `exporters/html.py`, `exporters/latex.py`, `exporters/ods.py`, `exporters/xls.py`, `exporters/raw.py`, `exporters/feather.py`, `exporters/pretty.py`, `exporters/values.py`, `exporters/duckdb.py`, `exporters/sqlite.py`, `importers/csv.py`, `importers/ods.py`, `importers/xls.py`, `importers/feather.py`, `importers/base.py`, `utils/auth.py` |
| GUI bridge functions: `gui_credentials`, `gui_connect`, `gui_console_*` (15875–16052)                                                                                                                                           | `utils/gui.py`                                                                                                                                                                                                                                                                                                                                                                                                         |
| `wo_quotes`, `get_subvarset`, `db_*` convenience constructors (16053–16134)                                                                                                                                                     | `utils/strings.py`, `db/factory.py`                                                                                                                                                                                                                                                                                                                                                                                    |
| `list_metacommands()`, `list_encodings()` (16135–16229)                                                                                                                                                                         | `cli.py`                                                                                                                                                                                                                                                                                                                                                                                                               |
| `clparser()` — CLI option definitions (16236–16309)                                                                                                                                                                             | `cli.py`                                                                                                                                                                                                                                                                                                                                                                                                               |
| **GLOBAL OBJECTS** — module-level singleton instantiations (16316–16366)                                                                                                                                                        | `state.py`, `cli.py` (main() initialisation)                                                                                                                                                                                                                                                                                                                                                                           |
| `main()` (16372–16627)                                                                                                                                                                                                          | `cli.py`                                                                                                                                                                                                                                                                                                                                                                                                               |

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

### File Sections

| Lines       | Section                                                                                                                                                                                                                                                     |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1–122       | Module header, imports, lazy-global declarations                                                                                                                                                                                                            |
| 123–435     | **GLOBAL VARIABLES** — runtime state, regex patterns, map icons/colors                                                                                                                                                                                      |
| 438–921     | **STATUS RECORDING** — `StatObj`, `ConfigError`, `ConfigData`                                                                                                                                                                                               |
| 926–1218    | **SUPPORT FUNCTIONS AND CLASSES (1)** — regex builders, string utilities                                                                                                                                                                                    |
| 1220–1245   | **ALARM TIMER** — `TimeoutError`, `TimerHandler`                                                                                                                                                                                                            |
| 1250–1292   | **EXPORT METADATA RECORDS** — `ExportRecord`, `ExportMetadata`                                                                                                                                                                                              |
| 1297–2298   | **FILE I/O** — `GetChar`, `FileWriter` (multiprocessing), `EncodedFile`, `WriteableZipfile`, `WriteSpec`, `Logger`, `TempFileMgr`, ODS/XLS/XLSX file classes                                                                                                |
| 2301–2339   | **SIMPLE ENCRYPTION** — `Encrypt` (XOR + base64)                                                                                                                                                                                                            |
| 2344–2454   | **EMAIL** — `Mailer`, `MailSpec`                                                                                                                                                                                                                            |
| 2458–2480   | **TIMER** — `Timer`                                                                                                                                                                                                                                         |
| 2483–2674   | **ERROR HANDLING** — `ErrInfo`, `exception_info()`, `exit_now()`, `fatal_error()`                                                                                                                                                                           |
| 2678–3167   | **DATA TYPES** — `DataType` base + 14 subclasses (Timestamp, Date, Time, Boolean, Integer, Long, Float, Decimal, Character, Varchar, Text, Binary, etc.)                                                                                                    |
| 3171–3412   | **DATABASE TYPES** — `DbTypeError`, `DbType` (per-DBMS type mapping)                                                                                                                                                                                        |
| 3416–3630   | **COLUMNS AND TABLES** — `ColumnError`, `Column`, `DataTableError`, `DataTable`                                                                                                                                                                             |
| 3634–3673   | **JSON SCHEMA TYPES** — `JsonDatatype`                                                                                                                                                                                                                      |
| 3678–5412   | **DATABASE CONNECTIONS** — `Database` base + 9 subclasses, `DatabasePool`                                                                                                                                                                                   |
| 5416–6136   | **CSV FILES** — `LineDelimiter`, `DelimitedWriter`, `CsvWriter`, `CsvFile`, `ZipWriter`                                                                                                                                                                     |
| 6140–6249   | **TEMPLATE-BASED REPORTS/EXPORTS** — `StrTemplateReport`, `JinjaTemplateReport`, `AirspeedTemplateReport`                                                                                                                                                   |
| 6254–6974   | **SCRIPTING** — `BatchLevels`, `IfLevels`, `CounterVars`, `SubVarSet`, `MetaCommand`, `MetaCommandList`, `SqlStmt`, `MetacommandStmt`, `ScriptCmd`, `CommandList`, loops, `ScriptFile`, `ScriptExecSpec`, `GuiSpec`                                         |
| 6979–9508   | **UI** — Tkinter GUI classes: `MsgUI`, `DisplayUI`, `CompareUI`, `MapUI`, `SelectRowsUI`, `ActionUI`, `CredentialsUI`, `ConnectUI`, `ConsoleUI`, `GuiConsole`, `PauseUI`, `EntryFormUI`, `OpenFileUI`, `SaveFileUI`, `GetDirectoryUI`; GUI helper functions |
| 9512–9821   | **PARSERS** — `SourceString`, `CondParser`, `NumericParser`, AST nodes                                                                                                                                                                                      |
| 9826–13781  | **METACOMMAND FUNCTIONS** — ~200 `x_*` handler functions + `metacommandlist.add(...)` registrations                                                                                                                                                         |
| 13785–14163 | **CONDITIONAL TESTS** — `xf_*` functions + `conditionallist.add(...)` registrations                                                                                                                                                                         |
| 14164–14371 | Utility functions: `chainfuncs`, `write_warning`, `parse_datetime`, `parse_datetimetz`                                                                                                                                                                      |
| 14373–14423 | `set_system_vars()`, `substitute_vars()`                                                                                                                                                                                                                    |
| 14425–14602 | `runscripts()`, `current_script_line()`, `read_sqlfile()`                                                                                                                                                                                                   |
| 14604–15874 | Export/import helpers: `write_delimited_file`, `write_query_to_*`, `export_*`, `import*`, `pause`, `get_password`                                                                                                                                           |
| 15875–16052 | GUI bridge functions: `gui_credentials`, `gui_connect`, `gui_console_*`                                                                                                                                                                                     |
| 16053–16134 | `wo_quotes`, `get_subvarset`, `db_*` convenience constructors                                                                                                                                                                                               |
| 16135–16229 | `list_metacommands()`, `list_encodings()`                                                                                                                                                                                                                   |
| 16236–16309 | `clparser()` — CLI option definitions                                                                                                                                                                                                                       |
| 16316–16366 | **GLOBAL OBJECTS** — module-level singleton instantiations                                                                                                                                                                                                  |
| 16372–16627 | `main()`                                                                                                                                                                                                                                                    |

### Class Hierarchy

**Database backends** (`Database` base at line 3691):

```
Database
├── AccessDatabase      (4023)  — win32com/pyodbc, .mdb/.accdb
├── DsnDatabase         (4307)  — ODBC DSN via pyodbc
├── SqlServerDatabase   (4378)  — pyodbc
├── PostgresDatabase    (4468)  — psycopg2
├── OracleDatabase      (4725)  — oracledb
├── SQLiteDatabase      (4871)  — sqlite3
├── DuckDBDatabase      (5018)  — duckdb
├── MySQLDatabase       (5070)  — pymysql
└── FirebirdDatabase    (5231)  — firebird-driver
```

`DatabasePool` (5351) — dict of alias→Database, tracks current active DB.

**Data types** (`DataType` base at line 2693):

```
DataType
├── DT_TimestampTZ / DT_Timestamp / DT_Date / DT_Time / DT_Time_Oracle
├── DT_Boolean
├── DT_Integer / DT_Long / DT_Float / DT_Decimal
└── DT_Character / DT_Varchar / DT_Text / DT_Binary
```

`DbType` (3189) — maps Python `DataType` to per-DBMS SQL type strings for CREATE TABLE.

**Script execution:**

```
CommandList (6775) — ordered list of ScriptCmd objects + execution cursor
├── CommandListWhileLoop (6881)
└── CommandListUntilLoop (6901)
ScriptCmd (6753) — wraps one command with source location
SqlStmt (6660) — SQL string; calls db.execute()
MetacommandStmt (6708) — dispatched through MetaCommandList
```

**Substitution variables:**

```
SubVarSet (6390) — global !!$VAR!! store
├── LocalSubVarSet (6509) — script-local vars
└── ScriptArgSubVarSet (6522) — $ARG_1, $ARG_2, ...
```

### Metacommand Dispatch System

Two linked lists built at module load time (before `main()` is called):

- **`metacommandlist`** (`MetaCommandList`, 6596) — imperative metacommands. Each entry: `MetaCommand(regex, x_func, description, run_in_batch, run_when_false)`. First regex match wins → calls `x_func(**groupdict)`.
- **`conditionallist`** — conditional test functions for IF/ELSEIF. Each entry maps a regex to an `xf_func` returning bool.

Naming conventions:

- `x_<name>` — imperative handler (e.g., `x_export`, `x_import`, `x_connect_pg`)
- `xf_<name>` — conditional test (e.g., `xf_tableexists`, `xf_fileexists`, `xf_equals`)

### Global Variables and Objects

**Variables** (lines 123–435):

| Name                                  | Purpose                                                                      |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| `conf`                                | `ConfigData` — configuration from execsql.conf + CLI                         |
| `commandliststack`                    | Stack of `CommandList` objects being executed                                |
| `savedscripts`                        | Named scripts from BEGIN/END SCRIPT                                          |
| `loopcommandstack`                    | Stack for compiling LOOP bodies                                              |
| `compiling_loop`                      | When True, commands compile into loop instead of executing                   |
| `subvars`                             | `SubVarSet` — global substitution variables (also holds env vars as `&NAME`) |
| `counters`                            | `CounterVars` — named counter variables                                      |
| `err_halt_writespec/email/exec`       | What to do when halting on error                                             |
| `cancel_halt_writespec/mailspec/exec` | What to do when halting on cancel                                            |
| `varlike`                             | regex: `!![$@&~#]?\w+!!` — detects unsubstituted vars                        |
| `defer_rx`                            | regex: `!{somevar}!` — deferred substitution                                 |

**Objects** (lines 16316–16366, instantiated before `main()`):

| Name              | Type              | Purpose                                              |
| ----------------- | ----------------- | ---------------------------------------------------- |
| `status`          | `StatObj`         | Runtime flags (halt_on_err, metacommand_error, etc.) |
| `if_stack`        | `IfLevels`        | IF/ELSE/ENDIF nesting stack                          |
| `subvars`         | `SubVarSet`       | Substitution variables                               |
| `counters`        | `CounterVars`     | Counter variables                                    |
| `timer`           | `Timer`           | Elapsed time for `$TIMER`                            |
| `output`          | `WriteHooks`      | Redirectable stdout                                  |
| `dbs`             | `DatabasePool`    | All open database connections                        |
| `filewriter`      | `FileWriter`      | Async multiprocessing text file writer               |
| `tempfiles`       | `TempFileMgr`     | Temp file registry                                   |
| `export_metadata` | `ExportMetadata`  | Export operation metadata                            |
| `metacommandlist` | `MetaCommandList` | All metacommand handlers                             |
| `conditionallist` | `MetaCommandList` | All conditional test handlers                        |

### CLI Options (`clparser()`, line 16236)

| Flag          | Meaning                                                                                                                |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `-a`          | Assign `$ARG_x` substitution variables                                                                                 |
| `-b`          | Treat 0/1 as bool                                                                                                      |
| `-d`          | Auto-create export directories                                                                                         |
| `-e/-f/-g/-i` | database/script/output/import encoding                                                                                 |
| `-l`          | Use `~/execsql.log`                                                                                                    |
| `-m`          | List metacommands + exit                                                                                               |
| `-n`          | Create new SQLite/Postgres DB                                                                                          |
| `-p`          | DB server port                                                                                                         |
| `-s`          | Lines to scan for IMPORT format detection                                                                              |
| `-t`          | DB type: `a`=Access, `p`=Postgres, `s`=SqlServer, `l`=SQLite, `m`=MySQL, `k`=DuckDB, `o`=Oracle, `f`=Firebird, `d`=DSN |
| `-u`          | DB username                                                                                                            |
| `-v`          | GUI level 0–3                                                                                                          |
| `-w`          | Skip password prompt                                                                                                   |
| `-z`          | Import buffer size (kb)                                                                                                |

### Substitution Variable Prefixes

| Prefix  | Meaning                      |
| ------- | ---------------------------- |
| `$NAME` | System/user-defined variable |
| `&NAME` | Environment variable         |
| `@NAME` | Counter variable             |
| `~NAME` | Script-local variable        |
| `#NAME` | Script argument (`$ARG_x`)   |

Syntax: `!!$VARNAME!!` (immediate) or `!{$varname}!` (deferred).

### Export Formats

Handled by `x_export()` (13565): `csv`, `tsv`, `txt`, `json`, `json-ts`, `xml`, `html`, `cgi-html`, `latex`, `values`, `ods`, `xls`, `xlsx`, `hdf5`, `duckdb`, `sqlite`, `b64`, `raw`, `feather`, `parquet`, `str-template`, `jinja`, `airspeed`.

### Notable Complexity Hot Spots

- `ConfigData` (468–921): ~450 lines of INI parsing
- `PostgresDatabase` (4468–4724): ~257 lines; most complex adapter (schema support, COPY, notify)
- `AccessDatabase` (4023–4306): ~284 lines; win32com DAO-based
- `CsvFile` (5500–6121): ~622 lines; full delimited reader/writer
- `EntryFormUI` (9098–9466): ~369 lines; Tkinter form builder
- `MapUI` (7873–8145): ~273 lines; Tkinter + tkintermapview interactive map
- Conditional test registrations (e.g., `CONTAINS`, `STARTS_WITH`): each generates ~17 regex variants for all quoting combinations

### Quick-Lookup Guide

| Goal                               | How                                                                                 |
| ---------------------------------- | ----------------------------------------------------------------------------------- |
| Find a metacommand implementation  | `grep "def x_<keyword>"`                                                            |
| Find a conditional test            | `grep "def xf_<keyword>"`                                                           |
| Find a DB backend method           | `grep "class <Name>Database"`, read from that line                                  |
| Understand data flow               | `runscripts()` (14425) → `CommandList.run_next()` → `MetacommandStmt.run()` → `x_*` |
| Find where a config option is read | Search `ConfigData` (468–921) or `main()` (16372+)                                  |
| Understand variable substitution   | `substitute_vars()` at 14398, `SubVarSet.substitute_all()` in `SubVarSet` (6390)    |
