# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in execsql2, please report it responsibly:

1. **Do not open a public issue.**
1. Email [grantcaleb22@gmail.com](mailto:grantcaleb22@gmail.com) with details of the vulnerability.
1. Include steps to reproduce, affected versions, and any potential impact.

I will respond to security reports ASAP. Security fixes will be released as patch versions.

## Trust Model

execsql treats the script author as fully trusted. Scripts run with the same OS and database privileges as the invoking user. There is no sandboxing or privilege separation.

**Do not run scripts from untrusted sources.**

For a detailed discussion of security boundaries, credential handling, and known limitations, see the [Security documentation](https://execsql2.readthedocs.io/reference/security/).

## Supported Versions

Security fixes are applied to the latest release only. There is no backport policy for older versions.

| Version  | Supported |
| -------- | --------- |
| latest   | Yes       |
| < latest | No        |
