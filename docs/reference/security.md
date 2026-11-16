# Security

This page describes the trust model, security boundaries, and known limitations of execsql. Read it before deploying execsql in environments where scripts consume external input, run as a service account, or handle sensitive credentials.

## Trust Model { #trust_model }

execsql treats the script author as fully trusted. Scripts run with the same OS and database privileges as the user who invoked `execsql`. There is no sandboxing or privilege separation. Capability switches and path-containment settings restrict specific operations, but a script can otherwise read and write files, execute OS commands, connect to databases and send email with the running user’s permissions.

**Do not run scripts from untrusted sources.**

## SYSTEM_CMD Command Execution { #system_cmd }

The [`SYSTEM_CMD`](metacommands.md#system_cmd) metacommand executes arbitrary OS commands via Python's `subprocess`. No allowlist, blocklist, or command restriction exists.

Variable substitution is applied to the command string before execution, so any substitution variable (`!!VAR!!`) embedded in the command is expanded first. The subprocess is invoked using a list of arguments (not `shell=True`), which mitigates classic shell injection attacks — an attacker cannot inject shell operators like `;`, `|`, or `&&` through variable values alone. However, **argument injection is still possible** if a variable contains untrusted data and the target program interprets certain argument patterns as flags or paths.

```sql
-- !x! sub outdir /safe/export/path
-- !x! SYSTEM_CMD (pg_dump -Fc mydb -f !!outdir!!/backup.dump)
```

If `outdir` is derived from user input, validate or sanitize it before use in a `SYSTEM_CMD` command.

!!! note "Windows `.bat`/`.cmd` files"

    On Windows, when the target of a `SYSTEM_CMD` is a `.bat` or `.cmd` file, Windows may invoke `cmd.exe` to interpret it. In this case, the `&` character in arguments can be interpreted as a command separator by `cmd.exe`, even though the subprocess is not launched with `shell=True`. Avoid passing untrusted data containing `&` to batch files on Windows.

### Disabling SYSTEM_CMD { #disable_system_cmd }

To prevent scripts from executing OS commands entirely, use the `--no-system-cmd` CLI flag:

```bash
execsql run --no-system-cmd script.sql mydb
```

Any script that uses `SYSTEM_CMD` will fail with an error. This is useful for CI pipelines, shared execution environments, or running semi-trusted scripts where shell access is not appropriate.

The same restriction can be set permanently in `execsql.conf`:

```ini
[config]
allow_system_cmd = No
```

The library API provides the same control:

```python
import execsql
result = execsql.run("script.sql", dsn="sqlite:///my.db", allow_system_cmd=False)
```

The `--no-system-cmd` CLI flag always takes precedence — if the flag is passed, `SYSTEM_CMD` is disabled regardless of the config file setting.

## Credential Handling { #credentials }

### Interactive password prompts

When execsql needs a database password and none is stored or configured, it prompts interactively. In terminal mode, the prompt uses `getpass` (input is not echoed). In GUI mode, a dialog with a hidden-text entry field is used. With keyring use disabled, execsql keeps prompted passwords in process memory. With an installed keyring backend and `use_keyring = Yes`, a password is saved to that backend after it successfully authenticates; see below for storage and opt-out settings.

<a id="keyring_setup"></a>

### OS credential store (keyring)

When the optional `keyring` package is installed (`uv tool install "execsql2[auth]"`), execsql checks the OS credential store before prompting. A password typed at the prompt is stored once the connection succeeds with it; a mistyped password is never stored. Keyring service names follow the pattern:

```text
execsql/<db_type>/<server>:<port>/<database>     # PostgreSQL, MySQL, SQL Server, Oracle, Firebird
execsql/<db_type>/local/<database>               # Access, ODBC DSN
```

The port is part of the name, so two servers reached through one host, such as a local database on 5432 and an SSH tunnel to another server on 15432, keep separate passwords. An entry stored by an earlier version, without the port, is used only for a connection on the database's default port (5432, 3306, 1433, 1521 or 3050), and is saved under the new name once it works.

When the server rejects a stored password (it was changed), execsql deletes the entry, prompts for the current password and stores that one once it works. This applies only to the entry that connection read: a `CONNECT` that reuses the password from an earlier connection never deletes or stores a keyring entry, even when the server rejects it. Any other connection failure (a timeout, a closed port, a database that does not exist) is reported as an error and the stored password is kept, so an unattended run never stops at a password prompt because the server was briefly unreachable. PostgreSQL reports a rejected password only in its message text; a server set to report messages in another language is treated like any other failure, and you remove the stale entry yourself (for example with `keyring del "execsql/PostgreSQL/host:5432/db" user`).

To disable keyring integration, set `use_keyring = No` in the `[connect]` section of `execsql.conf`.

macOS, Windows, and desktop Linux (with GNOME Keyring or KWallet running) use the OS-native credential store automatically. On headless Linux, the file backends require `execsql2[auth-encrypted]` or `execsql2[auth-plaintext]` and explicit backend selection. Installing an extra makes its backends available; it does not select one.

#### Plaintext keyring on a shared Linux server { #plaintext-keyring-setup }

Each person performs this setup under their own Unix account. A shared execsql installation can use separate per-user password files. People sharing one Unix login also share access to that account's passwords.

Before changing an existing installation, run `type -a execsql` to find the command your shell uses, including any alias or function. `uv tool list` lists tools managed by your current uv setup; an absent `execsql2` entry does not mean execsql is missing. It may be installed through pipx, in a virtual environment, or as a shared system installation. Use the installation you already run when adding dependencies or diagnosing keyring support.

1. **Check plaintext support in the Python environment running execsql.** For example, if `type -a execsql` reports `/opt/venvs/dataman/bin/execsql`, check the shared virtual environment:

    ```sh
    /opt/venvs/dataman/bin/python -c 'import keyring; import keyrings.alt.file; print("Plaintext backend available")'
    ```

    If this succeeds, no installation change is needed: each coworker can proceed with their own configuration below. If an import fails, ask the shared environment's administrator to install `keyring` and `keyrings.alt` there. Substitute your actual virtual environment path in these examples; no activation or `sudo` is needed to run the checks.

    For a new personal installation using PostgreSQL:

    ```sh
    uv tool install "execsql2[postgres,auth-plaintext]"
    ```

    With pipx, use `pipx install --force "execsql2[postgres,auth-plaintext]"`. Retain all existing database and feature extras when changing an installation. Installing keyring packages into an unrelated environment will not enable keyring support in execsql.

1. **Select the backend for your account.** Create or edit `~/.config/python_keyring/keyringrc.cfg`, merging this section with any existing configuration:

    ```ini
    [backend]
    default-keyring=keyrings.alt.file.PlaintextKeyring
    ```

    Create the parent directory first if needed: `mkdir -p ~/.config/python_keyring`. This is Python keyring's configuration, separate from `execsql.conf`. It affects other applications using Python keyring under your account, too.

    For selection limited to one command, omit the config-file change and prefix the command with `PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring`. This environment variable overrides the config file; an exported value also affects child processes. See the [keyring configuration reference](https://keyring.readthedocs.io/en/latest/#configuring).

    Verify the selected backend under your own Unix account, using execsql's Python interpreter:

    ```sh
    /opt/venvs/dataman/bin/python -c 'import keyring; k = keyring.get_keyring(); print(type(k).__module__ + "." + type(k).__name__)'
    ```

    Expected output: `keyrings.alt.file.PlaintextKeyring`. This prints only the backend class, without retrieving a password. A shared installation does not make one user's backend selection apply to every coworker.

1. **Restrict access to your password-storage directory:**

    ```sh
    mkdir -p ~/.local/share/python_keyring
    chmod 700 ~/.local/share/python_keyring
    ```

    These are the default Linux paths. If set, `XDG_CONFIG_HOME` replaces `~/.config` for keyring configuration, and `XDG_DATA_HOME` replaces `~/.local/share` for password storage. Use those locations in the commands above. Keep these directories in your own account's storage, outside shared project directories.

1. **Enable password lookup and prompting in execsql.** Both settings default to `Yes`. If they were disabled, merge these settings into `[connect]` in `~/.config/execsql.conf`:

    ```ini
    [connect]
    use_keyring=Yes
    password_prompt=Yes
    ```

    The execsql user configuration remains `~/.config/execsql.conf`; the keyring XDG overrides above do not relocate it. Script-directory, working-directory, or explicitly supplied execsql configuration can override these settings. Do not use `--no-passwd`: it disables both prompting and keyring lookup.

1. **Connect interactively once, then verify reuse.** Substitute your connection details and an existing SQL script:

    ```sh
    execsql run --dsn 'postgresql://alice@dbhost:5432/mydb' script.sql
    ```

    Enter the database password at the hidden prompt. execsql saves it only after authentication succeeds. The plaintext backend has no separate unlock password; execsql's warning about cleartext storage is expected. Restrict the created file:

    ```sh
    chmod 600 ~/.local/share/python_keyring/keyring_pass.cfg
    ```

    Run the same command again; it should reuse the saved password without prompting. Passwords are keyed by database type, server, port, database, and username, so use the same connection details when checking reuse.

For scheduled jobs, run as the same Unix account with the same home directory and XDG paths. A job using the environment-variable selection must also receive `PYTHON_KEYRING_BACKEND`; cron does not normally load your interactive shell configuration. Using `keyringrc.cfg` avoids relying on a shell export.

If reuse fails, check that `execsql` resolves to the intended installation, that its environment contains both `keyring` and `keyrings.alt`, and that no configuration disables keyring lookup. For a personal Linux installation managed by uv, inspect the keyring paths without retrieving a password:

```sh
"$(uv tool dir)/execsql2/bin/python" -m keyring diagnose
```

For a shared virtual environment, use its interpreter instead:

```sh
/opt/venvs/dataman/bin/python -m keyring diagnose
```

The reported config path and data root belong to the Unix account running the command. They show where keyring looks for configuration and stores data; they do not confirm which backend is active or that a password has been saved. Use the backend check in step 2 to confirm selection. For other installation methods, run `python -m keyring diagnose` using the Python interpreter from execsql's environment. Do not use `keyring get` or print the password file to diagnose setup: both expose credentials.

For encrypted file storage instead, install `auth-encrypted` and select `keyrings.alt.file.EncryptedKeyring` in the same `[backend]` setting. It uses a separate password file and asks for a master password when unlocking; it does not encrypt or migrate an existing plaintext password file.

!!! warning "Plaintext keyring backend"

    `keyrings.alt.file.PlaintextKeyring` stores recoverable passwords without encryption. Directory mode `700` and file mode `600` restrict ordinary users' access; they do not protect passwords from administrators or anyone controlling your account. Disk encryption protects data at rest, not from users who can read the file on a running server. Prefer an encrypted backend when possible. execsql warns about plaintext storage when saving a password (once per run). To opt out of keyring storage and lookup in execsql, set `use_keyring = No` in `[connect]`.

### `enc_password` in execsql.conf

!!! warning "Obfuscation only — not encryption"

    The `enc_password` configuration value is produced by a simple XOR operation using keys that are embedded in the execsql source code. Anyone with access to the installed package can decode any password stored this way. Treat `enc_password` values as **plaintext-equivalent**.

Use OS credential stores or environment variables for meaningful credential protection. Storing passwords in configuration files — whether as `password` (plaintext) or `enc_password` (obfuscated) — provides no meaningful security if the configuration file is readable by an attacker.

```ini
[email]
# Avoid this in production:
password = <plaintext password here>
enc_password = <base64 obfuscated value here>
```

### Passwords in command-line arguments

A password embedded in a `--dsn` URL can be visible in process listings, shell history and process accounting. The CLI warns about this; log redaction does not remove those external copies. Prefer a password-less DSN with a prompt or OS keyring. Other command-line arguments can also be exposed by the operating system.

ODBC connection-string attribute values containing `;` or beginning with `{` are brace-quoted, doubling embedded closing braces, to keep a password or DSN value from adding connection attributes. This does not make a caller-supplied connection string trustworthy.

### Environment variables and log redaction { #env_redaction }

execsql seeds every readable environment variable into the substitution-variable pool as `&NAME` so SQL scripts can reference them. To keep obvious secrets out of the pool — and out of `~/execsql.log` when `-l` / `--user-logfile` is enabled — env-var names whose uppercased form contains any of the following substrings are skipped:

```text
SECRET   TOKEN   PASSWORD   PASSWD   PRIVATE_KEY   CREDENTIAL
_KEY     APIKEY  API_KEY    DSN      WEBHOOK
```

This catches mainstream cloud, payment, observability, and VCS conventions: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `STRIPE_KEY`, `SENTRY_DSN`, `SLACK_WEBHOOK`, etc.

**Known gaps.** Substring matching is a denylist; it cannot catch every convention:

- `GITHUB_PAT` and other `…_PAT` suffixes are NOT filtered (the substring `PAT` would also match `PATH`, `_PATCH`, `NODE_PATH`, etc., breaking legitimate substitutions). Use `GITHUB_TOKEN` instead.
- `DATABASE_URL` and other URL-encoded DSNs (`postgresql://user:pass@host/db`) are NOT filtered. Use `*_DSN` or `*_SECRET` naming when the URL contains credentials.
- Any custom secret name that doesn't match a listed substring (e.g. `MY_MAGIC_VALUE`) passes through. Rename it or wrap your script in a process that strips it from the environment before invoking execsql.

`-a` (positional `$ARG_n`) assignments are always redacted to `***` in the log — `$ARG_n` is a positional name with no naming convention to denylist, and the value is opaque user input that may contain any high-entropy secret. The value is still passed to the substitution machinery normally; only the log line hides it. The `run` record that opens each run in the log lists only how many `-a` values were given (`sub_vars: 2 value(s)`), never the values.

Beyond `-a`, every secret a run handles is registered with the log as it arrives, and any later log record that contains it — a SQL statement logged with `LOG_SQL ON`, a `SYSTEM_CMD` echo, an error message, the `HALT MESSAGE` text and script path in the `exit` record, an exported file name, a connection name — shows `***` in its place:

| Secret                                | Registered when                          |
| ------------------------------------- | ---------------------------------------- |
| `-a` and `--var` values               | the run starts                           |
| Database password in a `--dsn` URL    | the run starts                           |
| `[email]` SMTP password               | the run starts                           |
| Database password typed at the prompt | it is entered (or read from the keyring) |
| `PROMPT ENTER_SUB ... PASSWORD`       | the value is entered                     |
| `PROMPT CREDENTIALS` password         | the value is entered                     |
| `SUB_DECRYPT` result                  | the value is decrypted                   |

The same replacement applies to the console warning about a possibly un-substituted variable, which echoes the command. Replacement is by value: any text in the log that happens to equal a registered secret is masked too, so a password that is also the user name or database name hides those as well. Only a record's text fields are masked, never its record type, run identifier, timestamp, sequence number or line number, so a short value such as `-a 2024` leaves the log's structure readable.

On POSIX, execsql attempts to restrict its active log file to mode `0600` after opening it. This is best-effort; verify filesystem permissions for sensitive runs. The normal log is `execsql.log` in the working directory, unless configured otherwise. Redaction cannot recognize every secret or remove sensitive data exported to other files.

## Input limits and regular expressions { #input-limits }

All substitution forms reject NUL bytes. Expanded substitutions also have a configurable [`max_substitution_bytes`](configuration.md#max_substitution_bytes) limit (10 MB by default), which limits expansion size rather than validating the resulting SQL or command.

XLSX readers and writers inspect ZIP metadata before parsing an existing workbook. The default limits reject more than 500 MB of declared uncompressed content or a member compression ratio above 100:1. These checks reduce decompression-bomb risk; they do not bound every possible parser allocation. ODS has separate configurable archive, XML, row, column and cell limits; see [ODS resource limits](configuration.md#spreadsheet-input-limits).

Spreadsheet `IMPORT … SHEETS MATCHING` selectors compile the supplied regular expression with Python's standard `re` engine. There is no regex timeout or complexity cap: a pathological pattern can cause excessive matching time. Use trusted patterns and bounded inputs. String predicates such as `CONTAINS`, `STARTSWITH` and `ENDSWITH` perform literal comparisons; they are not user-regex interfaces.

## File System Access { #filesystem }

By default, execsql can read and write any file that the process user has permission to access. Configure containment roots for shared or semi-trusted environments; otherwise path arguments may resolve outside the current directory.

The [`INCLUDE`](metacommands.md#include) metacommand executes a script from any accessible path unless `include_root` is set. If the included path is constructed from a variable, an attacker who controls that variable can cause execsql to execute an arbitrary script file.

```sql
-- Risky: included path derived from a variable
-- !x! sub script_path !!&USER_INPUT!!
-- !x! INCLUDE !!script_path!!
```

Validate any variable used to construct file paths before use in file-related metacommands.

### Network paths and the static tools { #network_paths }

`execsql lint`, `execsql format` and the language server read scripts and
`execsql.conf` files that someone else may have written, such as a cloned
repository. On Windows, even checking whether a path written as
`\\host\share\file.sql` (or `//host/share/file.sql`) exists makes Windows
connect to that host and offer your login. So these tools never touch a path
written that way, in an `INCLUDE`, a `SUB_INI`, a config `config_file` /
`win_config_file` chain or an `[include_required]` / `[include_optional]`
entry: lint does not check it (no I001), and the language server does not
follow it for completion, hover or links. A relative path in a script that is
itself on a share is still followed; it reaches only the host you opened.
`execsql run` is unchanged: running a script that `INCLUDE`s from a share is a
choice you make.

## Path containment roots { #path-containment-roots }

Containment roots are opt-in. When configured, paths must resolve under the configured root; attempts to escape with `../`, absolute paths, drive letters, or UNC paths are rejected.

An `INCLUDE` refused by `include_root` stops the run even with [`METACOMMAND_ERROR_HALT OFF`](metacommands.md#metacommanderrorhalt): the refusal is a security boundary, not a script error to carry on from, so the statements after it never run without the file they expected.

| Setting         | Applies to                                | Default      |
| --------------- | ----------------------------------------- | ------------ |
| `include_root`  | `INCLUDE` files                           | unrestricted |
| `serve_root`    | `SERVE` targets                           | unrestricted |
| `template_root` | Jinja2 and `string.Template` loader paths | unrestricted |

These roots do not contain every filesystem operation. `--output-dir DIR` separately confines EXPORT targets, including absolute paths, to the resolved root. An escaping `..` or symlink target is refused. ZIP archive paths and member names are also checked; `stdout` is exempt. WRITE is not constrained by `--output-dir` and can write wherever the process user has permission. See the [option reference](../getting-started/syntax.md#options).

## Email (SMTP) { #smtp }

TLS is off by default. The relevant `execsql.conf` settings are:

```ini
[email]
host = mail.example.com
port = 587
use_tls = yes
use_ssl = no
# Certificate verification is on by default.
verify_certificate = yes
# Set only if your relay uses an internal CA.
# ca_file = /etc/ssl/certs/corp-root-ca.pem
```

The block above uses STARTTLS on port 587. For implicit TLS, use this alternative instead; do not enable both modes:

```ini
[email]
host = mail.example.com
port = 465
use_ssl = yes
use_tls = no
verify_certificate = yes
```

With either TLS mode, execsql verifies the server's certificate: it must chain to a trusted certificate authority and match `host`, or the `EMAIL` metacommand fails before the SMTP password is sent. For a relay with an internal or self-signed certificate, point `ca_file` at its CA certificate. `verify_certificate = no` turns the check off, which lets anyone on the network path pose as the server; use it only for a test relay. For production deployments:

- Prefer `use_ssl = yes` (implicit TLS, port 465) over `use_tls = yes` (STARTTLS, port 587).
- Ensure your SMTP server is configured to reject unauthenticated relay.
- Do not store SMTP passwords in `execsql.conf` unless the file has strict filesystem permissions.

## SQL and Variable Substitution { #sql_injection }

execsql substitution variables (`!!VAR!!`) insert values directly into SQL text with no escaping or parameterization. This is by design — execsql is a scripting tool for trusted authors, not an application framework that handles end-user input.

```sql
-- !x! sub target_schema public
SELECT * FROM !!target_schema!!.mytable;
-- Expands to: SELECT * FROM public.mytable;
```

If a variable value is derived from external input (command-line arguments, environment variables, `PROMPT` responses, or data read from a file), the script author is responsible for quoting or validating that value before it is substituted into SQL.

The `!'!varname!'!` dereferencing form wraps the value in single quotes and doubles any embedded apostrophes (and, on MySQL/MariaDB, backslashes, so `\'` cannot end the literal there), which helps when inserting text values into SQL literals:

```sql
-- !x! sub author_name !!&AUTHOR!!
SELECT * FROM documents WHERE author = !'!author_name!'!;
```

Use the literal form as a complete SQL value, without additional surrounding quotes. Identifier and SQL-fragment contexts need their own quoting or validation; the literal form does not make arbitrary SQL structure safe. Backslash handling follows the active adapter and string context rather than one universal escape rule.

## Recommendations { #recommendations }

1. **Use a dedicated service account.** Run execsql under an account with only the database roles and filesystem permissions needed for the specific script. Do not run as a database superuser or as `root`.

1. **Do not run untrusted scripts.** execsql provides no sandbox. Any script you run has the same capabilities as your user account.

1. **Use OS credential stores instead of config-file passwords.** Install `execsql2[auth]` and rely on the keyring integration rather than storing passwords in `execsql.conf`.

1. **Enable TLS for SMTP.** Choose one mode: `use_ssl = yes, use_tls = no` (implicit TLS) or `use_tls = yes, use_ssl = no` (STARTTLS). Do not send credentials over an unencrypted SMTP connection.

1. **Audit scripts that use `SYSTEM_CMD` or `INCLUDE` with variable-derived paths.** Trace where each variable originates. If any value comes from outside the script (environment, prompt, file content), validate it before use in a command that touches the filesystem or executes a process.

1. **Restrict access to `execsql.conf`.** Configuration files may contain usernames, SMTP settings, and obfuscated passwords. Ensure file permissions prevent reads by other users (`chmod 600 execsql.conf` on Linux/macOS).

## ODS resource limits

ODS IMPORT checks total XML size and each archive member's compression ratio before opening the workbook. It also bounds materialized rows, columns, padded cells, characters per cell and total text before expanding repetition/span attributes. Defaults and overrides are listed in [spreadsheet input limits](configuration.md#spreadsheet-input-limits); `0` disables the named limit. Rejected sheets leave their targets unchanged. All matched sheets are checked before a multi-sheet import changes any target.

The archive check bounds XML input to odfpy's in-memory parser; the logical checks bound the subsequent spreadsheet expansion. XLSX continues to use its existing archive checks; the shared `import_max_*` logical settings currently apply to ODS only.
