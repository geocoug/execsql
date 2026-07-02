# Audit Remediation Ledger

- Branch: audit-fixes (base: `main` @ d96f9546763ce3f37cb3e0b59e6628a374901fec)
- Verification command: `just check`
- Baseline: green (`5247 passed, 10 skipped`; coverage 85.50%; 28 warnings)
- Commit mode: approve-each
- Audit date: unavailable in AUDIT.md (commits behind HEAD at start: not computed)
- Started: 2026-07-02 | Last updated: 2026-07-02
- Scope: Now + Next bounded fixes; Later skipped by default; kill-list skipped unless requested

| ID                                | Title                                                      | Severity | Status   | Commit  | Note                                                           |
| --------------------------------- | ---------------------------------------------------------- | -------- | -------- | ------- | -------------------------------------------------------------- |
| F-DATA-001                        | Preserve exact mixed-scale decimals                        | High     | done     | a3e01b3 | Existing commit on branch at remediation reset                 |
| F-CONC-001                        | Propagate RuntimeContext into Textual worker               | High     | done     | adb27f6 | Existing commit on branch at remediation reset                 |
| F-SEC-001 / F-DOC-003             | Add run() controls for RM_FILE and SERVE                   | Medium   | done     | 4e6f67f | Existing commit on branch at remediation reset                 |
| F-DOC-001 / F-DOC-004             | Correct executable-name and path-containment docs          | High     | done     | 15d519f | Adds executable-name correction and path containment matrix    |
| F-DOC-002 / F-DOC-005 / F-DOC-006 | Correct dependency and CI-enforcement docs drift           | Medium   | done     | 01bbd69 | Corrects PostgreSQL, Feather, and CI/pre-commit docs           |
| F-SEC-002                         | Centralize/redact expanded SQL and command logs            | Medium   | done     | 95c492d | Logger redacts registered values, DSNs, and token-like strings |
| F-OPS-001 / F-OPS-002             | Add CI gates for pre-commit and docs                       | Medium   | pending  | -       | Typecheck gate deferred because current baseline does not pass |
| F-DATA-004 / F-CONC-002           | Replacement import/copy durability policy                  | Medium   | deferred | -       | Needs design decision on atomic/staged replacement semantics   |
| F-DATA-002                        | Stream non-CSV structured imports                          | Medium   | deferred | -       | Architectural import-contract change                           |
| F-DATA-003                        | Avoid double execution for COPY NEW/REPLACEMENT            | Medium   | deferred | -       | Architectural copy/schema inference change                     |
| F-CONC-003                        | Bound and track SYSTEM_CMD processes                       | Medium   | deferred | -       | Needs timeout/background ownership policy                      |
| F-SEC-003                         | Plugin disable/allowlist controls                          | Low      | skipped  | -       | Later tier skipped by default                                  |
| F-OPS-003                         | Decide Access real-driver release gating                   | Medium   | deferred | -       | Maintainer release policy decision                             |
| F-OPS-004 / F062                  | Supply-chain audit/SBOM/dependency automation              | Low      | skipped  | -       | Later tier skipped by default                                  |
| F060                              | Move Textual to optional extra or document base dependency | Medium   | deferred | -       | Maintainer packaging policy decision                           |
| F061                              | Decide runtime dependency constraint policy                | Medium   | deferred | -       | Maintainer packaging policy decision                           |
| Typecheck CI gate                 | Burn down existing mypy baseline before enforcing in CI    | Medium   | deferred | -       | `uv run mypy src/execsql/` reports 1246 existing errors        |
| K-001..K-004                      | Ignored local cleanup batches                              | -        | skipped  | -       | No tracked source deletion candidates; local disk cleanup only |

Pre-existing failures (excluded from pass/fail): none.
