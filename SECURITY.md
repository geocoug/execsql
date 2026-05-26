# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in execsql2, please report it responsibly:

1. **Do not open a public issue.**
1. Email [grantcaleb22@gmail.com](mailto:grantcaleb22@gmail.com) with details of the vulnerability.
1. Include steps to reproduce, affected versions, and any potential impact.

I will respond to security reports ASAP. Security fixes will be released as patch versions.

## Trust Model

execsql2 treats the script author as fully trusted. Scripts run with the same OS and database privileges as the invoking user. There is no sandboxing or privilege separation.

**Do not run scripts from untrusted sources.**

The trust boundary inside the runtime is the **substitution variable**: values fed via `-a`, `PROMPT`, `SUBDATA`, environment variables, or DB rows are user-controlled and reach SQL through the substitution engine. execsql2 ships several defenses to limit the blast radius of an untrusted substitution value, but a malicious script author can still do anything the OS user can do.

For a full discussion of security boundaries, credential handling, and known limitations, see the [Security documentation](https://execsql2.readthedocs.io/reference/security/).

## Defense-in-Depth

The following protections are on by default. They can be tuned or disabled via `execsql.conf` and CLI flags — see [`docs/reference/configuration.md`](https://execsql2.readthedocs.io/reference/configuration/).

### Substitution variables

- `!'!var!'!` wraps the value as a SQL string literal, doubling embedded `'` and escaping `\` (always, on all hosts) so MySQL default-mode and PostgreSQL E-string literals stay closed.
- `!"!var!"!` wraps the value as a SQL quoted identifier, doubling embedded `"`.
- All three substitution forms reject values containing NUL bytes (most DBMS wire protocols silently truncate or reject them).
- `substitute_vars()` aborts when expanded output exceeds 10 MB (configurable via `max_substitution_bytes`) to stop exponential-expansion bombs.

### Path containment

- `--output-dir` is a containment boundary, not a prefix: absolute paths and `..` traversals that escape the configured root are rejected.
- `include_root`, `serve_root`, and `template_root` config keys confine `INCLUDE` / `EXECUTE SCRIPT`, `SERVE`, and Jinja2 / `string.Template` loaders to a named directory tree.
- `--no-rm-file`, `--no-serve`, `--no-system-cmd` CLI flags disable the corresponding metacommands entirely.

### SQL injection

- `Database.quote_literal()` and `Database.quote_identifier()` helpers on every adapter (MySQL native backticks, SQL Server brackets, ANSI for the rest).
- SQLite and DuckDB exporters identifier-quote the destination table name and parameter-bind existence-check literals.
- ODBC DSN connections brace-quote the DSN/UID/PWD attribute values with `{…}` so a password containing `;` cannot inject additional connection-string attributes (CWE-91).

### File format defenses

- XLSX importers and exporters pre-inspect the OOXML zip directory and reject decompression-bomb files (compression ratio > 100:1 per member or aggregate size > 500 MB by default).
- ODS importers and exporters call `defusedxml.defuse_stdlib()` so odfpy can't be tricked into processing billion-laughs or external-entity XML attacks.
- CSV, XLSX, and ODS exporters prefix string cell values starting with `=`, `+`, `-`, `@`, or tab with `'` so the cell imports as text instead of executing as a formula on open in Excel / LibreOffice Calc (toggle via `csv_safe_formulas`).

### Credentials and logging

- `~/execsql.log` is created with mode `0o600` on POSIX so the substituted SQL, `-a` values, env vars, and DSN URLs it captures are not world-readable.
- The env-var-seeding pass at startup skips any variable whose name contains `PASSWORD`, `SECRET`, `TOKEN`, `PASSWD`, `PRIVATE_KEY`, or `CREDENTIAL`. The same filter redacts `-a` log entries.
- A warning is printed when `--dsn` URLs contain an embedded password (visible in `ps`, shell history, process accounting).
- A warning is printed when the active OS keyring backend stores secrets in cleartext (`keyrings.alt.file.PlaintextKeyring` on headless Linux).

### Known limitations

- The `xf_*` regex predicates and `IMPORT … PATTERN <regex>` compile user-supplied patterns. Catastrophic backtracking (ReDoS) is possible — re2 is not stdlib so the complexity cap is not enforced.
- On Oracle, MySQL, SQL Server, and MS Access the driver implicitly commits DDL. `Database.auto_commits_ddl()` returns `True` for those adapters so callers can detect the asymmetry, but `BATCH` rollback after a DDL crosses a transaction boundary is a silent no-op on those engines.
- DDL inside a `BATCH` block on the auto-commit adapters above will not be rolled back on error. Use the per-DBMS capability hooks if your script needs strict transactional guarantees.

## Supported Versions

Security fixes are applied to the latest release only. There is no backport policy for older versions.

| Version  | Supported |
| -------- | --------- |
| latest   | Yes       |
| < latest | No        |
