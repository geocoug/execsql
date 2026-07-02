# Remediation Change Summary - branch `audit-fixes`

_Review with `git diff main..audit-fixes` (base recorded in the ledger). One entry
per commit._

## Changes made

### [F-DATA-001] Preserve exact mixed-scale decimals · High · commit a3e01b3

- **What changed:** mixed-scale decimal columns infer exact numeric types instead of falling through to float.
- **Files:** `src/execsql/models.py`, `tests/test_models.py`, `CHANGELOG.md`
- **Docs updated:** `CHANGELOG.md`
- **Verified:** `just check` baseline passed after reset.
- **Test it yourself:** import or infer values like `1.2`, `3.45`, and `6.789`; the inferred type should remain decimal/numeric.
- **Heads-up:** existing commit was present before this ledger was created.

### [F-CONC-001] Propagate RuntimeContext into Textual worker · High · commit adb27f6

- **What changed:** Textual console script execution uses the initialized main-thread runtime context in the worker.
- **Files:** `src/execsql/cli/run.py`, `tests/cli/test_cli_run.py`
- **Docs updated:** none.
- **Verified:** `just check` baseline passed after reset.
- **Test it yourself:** run Textual console execution with an initialized DB/config and confirm worker-side execution sees the same runtime context.
- **Heads-up:** existing commit was present before this ledger was created.

### [F-SEC-001 / F-DOC-003] Add run() controls for RM_FILE and SERVE · Medium · commit 4e6f67f

- **What changed:** `execsql.run()` accepts `allow_rm_file` and `allow_serve` and wires them into library runtime config.
- **Files:** `src/execsql/api.py`, `tests/test_api.py`, `CHANGELOG.md`
- **Docs updated:** `CHANGELOG.md`
- **Verified:** `just check` baseline passed after reset.
- **Test it yourself:** call `execsql.run(..., allow_rm_file=False)` or `allow_serve=False` with a script using the matching metacommand; expect the metacommand to be blocked.
- **Heads-up:** existing commit was present before this ledger was created.

### [F-DOC-001 / F-DOC-004] Correct CLI naming and path containment guidance · High · commit 15d519f

- **What changed:** installation, divergence, and architecture docs now say the package is `execsql2` but the executable remains `execsql`; the security reference now documents path containment roots.
- **Files:** `docs/getting-started/installation.md`, `docs/about/divergence.md`, `docs/dev/architecture.md`, `docs/reference/security.md`
- **Docs updated:** same files.
- **Verified:** targeted docs checks passed; commit hooks passed.
- **Test it yourself:** `rg "execsql2 script|execsql2 command|invoked as either" docs README.md` should return no stale executable claims, and `docs/reference/security.md` should contain `#path-containment-roots`.
- **Heads-up:** none.

## Blocked (need a human)

- None yet.

## Deferred (your decision)

- **[F-DATA-004 / F-CONC-002]** Replacement import/copy durability policy - needs a design decision on atomic/staged behavior versus documented destructive compatibility.
- **[F-DATA-002]** Structured import streaming - requires a broader importer contract change.
- **[F-DATA-003]** COPY source double execution - requires copy/schema inference architecture work.
- **[F-CONC-003]** SYSTEM_CMD timeout/background ownership - needs policy on whether background children are detached or owned.
- **[F-OPS-003]** Access real-driver release gating - release policy decision.
- **[F060]** Textual dependency scope - packaging/product decision.
- **[F061]** Runtime dependency constraint policy - packaging/product decision.

## Rejected (not real issues on inspection)

- None yet.

## Side effects to action before merge

- None known yet.
