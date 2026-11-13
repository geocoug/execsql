# Roadmap

Updated 2026-11-13. This is the consolidated direction for execsql2: product
features, engineering work and compatibility proposals. [GitHub issues](https://github.com/geocoug/execsql/issues)
remain the actionable backlog; this document records priorities, dependencies and
completion criteria. Approving the roadmap accepts its priorities; implementation
still requires approval of a specific change's scope. It assigns no release dates.

**Current focus: targeted improvements to existing logs, the run manifest and Python results.**
Performance work can proceed alongside the product milestones. Each change needs
an agreed scope; once approved, carry it through commits, PR, CI, required review
and merge under [AGENTS.md](AGENTS.md).

## Delivered: schema discovery (A1)

Agents need database facts before authoring SQL. Build on the existing database
adapters, JSON lint output, Python `execsql.run()` API, run manifest and dry-run
parser rather than adding a separate execution engine.

Schema discovery is available through `execsql inspect database` and Python
`execsql.inspect_schema()` ([#190](https://github.com/geocoug/execsql/issues/190)).
The [schema discovery reference](docs/reference/schema.md) defines its contract
and adapter coverage. The CLI prints readable text by default and exposes the
shared machine contract with `--output-format json`. It provides:

- Filtered metadata for a selected schema or table: tables, columns, types, keys,
    relationships and database dialect, without requiring the whole catalog in the
    caller's context.
- A documented JSON contract shared by Python and CLI callers. The contract uses `schema_version: 1`; filters are exact, case-sensitive
    schema/table names.
- A capability/support matrix accounting for every existing adapter. Use each
    adapter's available metadata capabilities and explicitly mark unavailable
    fields; distinguish those from empty results and real query failures. The reference documents native catalogs, ODBC capability detection and
    live versus catalog-row verification.
- Metadata-only inspection. Row sampling is an optional future extension with
    explicit opt-in; it is not part of A1's completion gate. Connection credentials
    stay out of results and diagnostics.
- Tests and examples for filtering, identifiers, supported metadata, unavailable
    capabilities and query failures across the adapter support matrix.

**Completion gate met:** a caller can inspect a selected schema or table, understand
which metadata is available, and consume a documented JSON contract with a
versioning policy, without executing a SQL script or requesting row data.

## Inspection extensions

Retain `execsql inspect database` and its existing filters. Schema/table inspection
commands are delivered; file inspection remains a proposal:

Unfiltered database inspection shows identity, engine and namespaces with visible
table/view counts, including namespaces without visible objects. Schema-less
adapters show objects directly; unavailable namespace discovery is explicit.
Filtered database forms and existing JSON fields remain compatible.

| Command                                        | Status and output                                                                                              |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `execsql inspect schema NAME`                  | Delivered: tables/views within the selected schema.                                                            |
| `execsql inspect table NAME [--schema SCHEMA]` | Delivered: columns, types, nullability, primary key and relationships for matching tables/views.               |
| `execsql inspect file PATH`                    | Proposed: file format, encoding and delimiter where applicable, column names and inferred types before import. |

Use readable text by default and `--output-format json` for automation. Database
commands share the existing inspection API and connection options. File inspection
should reuse the import readers and type inference; its scoped design must define
supported formats, sampling limits and how uncertain detection is reported.
File inspection requires its own scope approval before implementation.

## Product track: agents and automation

The order below expresses feature priority, not a strict serial implementation
schedule. Dependencies determine what can proceed independently. Build on
interfaces that already exist; each milestone must be useful independently.

| Milestone                            | Outcome and completion criteria                                                                                                                                                                                                             | Dependencies                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **A1. Schema discovery (delivered)** | Filtered, read-only JSON metadata with explicit adapter capabilities and errors; see the interface above.                                                                                                                                   | Existing database adapters.                                                                 |
| **A5. Optional MCP interface**       | Expose schema inspection, script validation and execution of explicitly selected scripts through the established APIs and result schemas. Keep the integration optional and define execution permissions separately from inspection access. | Existing Python API/manifest plus A1; reconsider scope without A3/A4 before implementation. |

**Decisions, 2026-11-13:** skip A3's unattended mode; no current workflow justifies
the additional prompt-answer and credential machinery. Skip A4's `inspect script`;
existing `--parse-tree` and `--dry-run` cover current preview needs. Neither remains
an implementation prerequisite for A5.

Explicit run context is not a prerequisite for these milestones. Each interface must respect
existing run and connection-ownership constraints.

## Reporting direction

**Decision, 2026-11-13:** drop A2's separate versioned execution report and detailed
per-command/transaction trace. No current consumer justifies another reporting
interface or its collection and maintenance costs.

Improve `execsql.log`, the existing `--manifest` output and Python `ScriptResult`
where a concrete bug or caller need warrants it. Preserve existing interfaces,
secret redaction and execution behavior. Measure the cost of any new
instrumentation before enabling it. The remaining automation milestones build on
these existing interfaces; a separate report is not a prerequisite.

## Engineering track: performance and execution architecture

Work in the order below when measurements justify it. First extend the relevant
behavior coverage, then retain a reproducible benchmark and compare the proposed
change with the current implementation. The older 2026-10-17 measurements are
historical; their benchmark scripts were not retained, so they are not current
performance claims or release targets. Each scoped performance task chooses its
representative workloads and measurable success criteria before implementation.

| Order                                   | Work                                                                                                                                                                                                                                   | Evidence required before shipping                                                                                                                                                                                                                                                                                                         |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **E1. Loop and control-flow overhead**  | Profile `EXECUTE SCRIPT` body copying, per-command path resolution and unequal `EQUAL()` comparisons. Optimize the measured cost.                                                                                                      | Preserve script-body snapshot/mutation behavior, including runtime script extension; do not assume AST structures are immutable. Preserve path-variable behavior across `CD`, includes and inline scripts. Compare `EQUAL()` across value pairs before changing conversion order: integer, date and Boolean interpretations can disagree. |
| **E2. Type-scan memoization**           | Reuse per-column type checks for repeated values.                                                                                                                                                                                      | The scan's golden corpus must keep the same inferred types. Length, precision and scale calculations still see every value. Measure memory use and high-cardinality inputs as well as repeated codes and dates.                                                                                                                           |
| **E3. DuckDB bulk loading**             | Evaluate Arrow registration plus `INSERT … SELECT`, including whether existing format dependencies provide a usable path without a mandatory new Arrow dependency. Keep the current loader when the optional fast path is unavailable. | Differential tests across every source-value type × destination-column type, including errors, must show identical stored values. A speedup never justifies a changed value.                                                                                                                                                              |
| **E4. Explicit run context**            | Continue passing the existing `RuntimeContext` explicitly through remaining handlers; evaluate a per-run library object.                                                                                                               | Preserve independent/reentrant library calls, cleanup, transaction state and the existing plugin handler contract. Define a compatible plugin transition rather than unconditionally adding arguments to handlers. This prepares for a separately scoped parallel-execution feature.                                                      |
| **E5. Driver autocommit investigation** | Investigate avoiding a separate commit round trip for every statement.                                                                                                                                                                 | This remains gated on cross-backend transaction coverage: SQL-level `BEGIN`/`COMMIT`, `AUTOCOMMIT OFF`, batches, interruptions and metacommands that commit independently must retain their outcomes. If parity cannot be shown, retain the current path and recommend explicit batching.                                                 |

Extend the existing script behavior corpus and generated transaction model where
coverage is missing. The corpus harness already exists; do not rebuild it. The
generated model currently covers SQLite, and its larger scheduled run already
exists; additional backends remain possible extensions.

Startup and general `EXPORT` throughput are not current optimization priorities.
Fresh measurements can change that decision.

## Additional 2.x feature proposals

These proposals are retained alongside the agent track. Their syntax and design
still need a scoped decision before implementation.

| Proposal                                          | Intended behavior                                                                                                                                    | Compatibility requirement                                                                                                                                                                                                        |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Typed variables and bound SQL parameters**      | Add an opt-in form that sends typed values as driver parameters, with an explicit distinction between bound values and raw SQL/identifier fragments. | Existing `!!var!!` textual substitution keeps its behavior in 2.x. Reduce value-interpolation risks without silently changing existing scripts.                                                                                  |
| **Schema-first imports and visible inferred DDL** | Add opt-in declared schemas and source-query types for new tables, and expose inferred DDL before a load.                                            | Existing-table loads already convert by destination type. Preserve the existing new-table inference default in 2.x; changing that default belongs to an approved 3.0 plan. Validate conversions and errors with the load corpus. |
| **One declarative metacommand grammar**           | Generate parsing, syntax references, editor completions and the VS Code grammar from shared command definitions.                                     | Build a corpus of accepted forms before replacing regex dispatch. Preserve supported 2.x forms; any later removal of quirks needs a migration plan.                                                                              |
| **Named TOML connection profiles**                | Add an optional configuration file with named profiles and documented precedence alongside existing INI configuration and connection URLs.           | Keep existing configuration and CLI forms in 2.x. Choose an unambiguous profile-selector spelling: `--profile` already enables execution profiling.                                                                              |

## Compatibility policy and 3.0 candidates

New opt-in features and behavior-preserving optimizations can ship in 2.x.
Deliberate released behavior changes need maintainer approval, a minor release,
documentation and a `Changed` changelog entry. Removing a metacommand, option or
CLI form waits for 3.0. Python 3.10 support remains a requirement.

The following are **candidates for a separate major-version plan**, not approved
removals or a promised 3.0 scope. Each needs a migration path and explicit approval.

| Candidate                                                           | Prerequisite and migration concern                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bound parameters become the default.                                | Deliver the opt-in parameter form first. Existing scripts that paste table names, clauses or SQL fragments need an explicit raw-text form; final token syntax is undecided.                                                                                                 |
| Declared/source-query types become the default for new-table loads. | Deliver schema-first loading first. Existing scripts may create different column types when inference is no longer the default.                                                                                                                                             |
| One configuration format and connection URLs replace legacy forms.  | Deliver additive TOML profiles first, then plan migration from per-OS INI files, DBMS letter codes and positional connection arguments.                                                                                                                                     |
| Best-effort adapters move to optional plugin packages.              | Evaluate Access, Firebird, Oracle and ODBC packaging and test coverage. A documented assessment must show that a 2.x packaging move preserves supported installation and usage, including extras, connection/CLI forms and public APIs; otherwise it stays a 3.0 candidate. |
| Retire the Tkinter backend and remove implied `run`.                | Plan migration to Textual/console and require the explicit `execsql run` form. These removals have not been approved by consolidating this roadmap.                                                                                                                         |
| Stop accepting legacy grammar quirks.                               | Complete the accepted-form inventory and declarative grammar first; document each removed form and its replacement.                                                                                                                                                         |

## Delivered foundations and prior priorities

The previous brainstorm's five ranked priorities have been completed. They are
recorded here so they do not reappear as unfinished work.

| Delivered work                                                                                            | Record                                                                                                                                 |
| --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Catalog-query failures fail their batches.                                                                | [#166](https://github.com/geocoug/execsql/pull/166), addressing #136.                                                                  |
| Unevaluable `ASSERT`/`WAIT_UNTIL` conditions stop execution; condition diagnostics explain syntax errors. | [#167](https://github.com/geocoug/execsql/pull/167) and [#174](https://github.com/geocoug/execsql/pull/174), addressing #117 and #118. |
| Firebird catalog checks and DDL commit failures honor transaction boundaries.                             | [#168](https://github.com/geocoug/execsql/pull/168), addressing #138.                                                                  |
| Deferred `INCLUDE` filenames resolve on each loop pass.                                                   | [#173](https://github.com/geocoug/execsql/pull/173), addressing #114.                                                                  |
| Nested substitution uses an overlapping candidate scan while preserving replacement order and errors.     | [#187](https://github.com/geocoug/execsql/pull/187); reproducible benchmark: `scripts/benchmarks/substitution.py`.                     |

Borrowed-connection cleanup coverage, scheduled transaction-model checks and
explicit dynamic-block diagnostics are also delivered
([#172](https://github.com/geocoug/execsql/pull/172),
[#181](https://github.com/geocoug/execsql/pull/181)). Recent native Tk and
file-writer test stabilization is recorded in
[#186](https://github.com/geocoug/execsql/pull/186) and
[#188](https://github.com/geocoug/execsql/pull/188).

## Delivery rules

- GitHub issues hold agreed implementation tasks and acceptance criteria. Keep
    this roadmap current when a milestone completes or priorities change.
- Expand existing behavior/corpus coverage before significant rewrites. Every
    deliberate upstream divergence remains visible in the accepted corpus record
    and `docs/about/divergence.md`.
- `IMPORT`, `EXPORT` and `COPY` must never silently change stored data. Preserve
    value conversion and error behavior with golden/differential tests.
- Retain benchmark scripts and record the revision, environment, workload and
    measured result; distinguish microbenchmarks from whole-script performance.
- Follow [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md) for supported
    Python versions, quality gates, documentation, changelog and review requirements.

Metacommands inside SQL comments (`-- !x!`) remain part of the design so scripts
stay valid SQL for other tools. Runtime generation of complete block commands is
not a current feature priority: #119 delivered actionable refusals, and a future
implementation needs a concrete use case and its own scope.
