# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in execsql2:

1. **Do not open a public issue.**
1. Email [grantcaleb22@gmail.com](mailto:grantcaleb22@gmail.com) with affected versions, steps to reproduce and potential impact.

The maintainer responds as soon as possible. Security fixes are released as patch versions.

## Trust Model

Scripts run with the OS and database privileges of the invoking user. Run only scripts whose authors and contents you trust. Capability switches and path restrictions reduce specific risks; they do not sandbox a script.

Substitution values can come from arguments, prompts, environment variables or database rows. Use the supported SQL literal/identifier forms for the corresponding context rather than interpolating raw text. Prompted passwords may be saved to the configured keyring after successful authentication unless keyring use is disabled.

The [Security reference](https://execsql2.readthedocs.io/en/stable/reference/security/) is the maintained explanation of quoting, credentials and logging, input limits, TLS, path containment and capability switches. The [transaction reference](https://execsql2.readthedocs.io/en/stable/reference/metacommands/#batch) describes commit/rollback limits by backend and operation.

## Supported Versions

Security fixes apply to the latest release only; older releases have no backport policy.
