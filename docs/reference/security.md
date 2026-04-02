# Security

This page describes the trust model, security boundaries, and known limitations of execsql. Read it before deploying execsql in environments where scripts consume external input, run as a service account, or handle sensitive credentials.

## Trust Model { #trust_model }

execsql treats the script author as fully trusted. Scripts run with the same OS and database privileges as the user who invoked `execsql`. There is no sandboxing, privilege separation, or policy enforcement of any kind. A script can read and write files, execute OS commands, connect to databases, and send email — subject only to the permissions of the running user.

**Do not run scripts from untrusted sources.**

## SYSTEM_CMD Command Execution { #system_cmd }

The [`SYSTEM_CMD`](metacommands.md#system_cmd) metacommand executes arbitrary OS commands via Python's `subprocess`. No allowlist, blocklist, or command restriction exists.

Variable substitution is applied to the command string before execution, so any substitution variable (`!!VAR!!`) embedded in the command is expanded first. The subprocess is invoked using a list of arguments (not `shell=True`), which mitigates classic shell injection attacks — an attacker cannot inject shell operators like `;`, `|`, or `&&` through variable values alone. However, **argument injection is still possible** if a variable contains untrusted data and the target program interprets certain argument patterns as flags or paths.

```sql
-- !x! sub outdir /safe/export/path
-- !x! SYSTEM_CMD (pg_dump -Fc mydb -f !!outdir!!/backup.dump)
```

If `outdir` is derived from user input, validate or sanitize it before use in a `SYSTEM_CMD` command.

## Credential Handling { #credentials }

### Interactive password prompts

When execsql needs a database password and none is stored or configured, it prompts interactively. In terminal mode, the prompt uses `getpass` (input is not echoed). In GUI mode, a dialog with a hidden-text entry field is used. Passwords entered interactively are held in process memory only and are not written to disk by execsql.

### OS credential store (keyring)

When the optional `keyring` package is installed (`pip install execsql2[auth]`), execsql checks the OS credential store before prompting. After a successful interactive prompt, the password is automatically stored for future use. Keyring service names follow the pattern:

```text
execsql/<db_type>/<server>/<database>
```

To disable keyring integration, set `use_keyring = No` in the `[connect]` section of `execsql.conf`.

#### Platform setup { #keyring_setup }

**macOS** — Works out of the box. Keyring uses the macOS Keychain automatically.

**Windows** — Works out of the box. Keyring uses the Windows Credential Manager automatically.

**Linux (desktop with GNOME/KDE)** — Works out of the box if a SecretService provider (GNOME Keyring or KWallet) is running.

**Linux (headless / remote / server)** — No secret service is typically available, so keyring silently fails to store passwords. You need to configure a file-based backend. There are two options:

##### Option A: Encrypted file backend (recommended) { #keyring_encrypted }

Passwords are stored encrypted on disk. Requires a master password the first time keyring is used per session.

```bash
pip install keyrings.alt pycryptodome
mkdir -p ~/.config/python_keyring
cat > ~/.config/python_keyring/keyringrc.cfg << 'EOF'
[backend]
default-keyring=keyrings.alt.file.EncryptedKeyring
EOF
```

The encrypted keyring file is stored at `~/.local/share/python_keyring/crypted_pass.cfg`. You will be prompted for a master password once per session (e.g., when you first run execsql after logging in).

##### Option B: Plaintext file backend (no prompts) { #keyring_plaintext }

Passwords are stored in plain text on disk. No master password is needed — execsql will never prompt for a password after the first successful entry.

```bash
pip install keyrings.alt
mkdir -p ~/.config/python_keyring
cat > ~/.config/python_keyring/keyringrc.cfg << 'EOF'
[backend]
default-keyring=keyrings.alt.file.PlaintextKeyring
EOF
```

Passwords are stored at `~/.local/share/python_keyring/keyring_pass.cfg`. Restrict access to this file:

```bash
chmod 600 ~/.local/share/python_keyring/keyring_pass.cfg
```

!!! warning "Plaintext storage"

    The plaintext backend stores passwords without encryption. Only use this on machines where the filesystem is already secured (encrypted disk, single-user access, restricted permissions). Prefer the encrypted backend when possible.

##### Verifying keyring setup { #keyring_verify }

After configuring a backend, verify it works:

```bash
python -c "import keyring; keyring.set_password('test', 'user', 'pw'); print(keyring.get_password('test', 'user'))"
```

This should print `pw` without errors. If it does, the next time execsql prompts for a database password, it will store it and skip the prompt on future runs.

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

## File System Access { #filesystem }

execsql can read and write any file that the process user has permission to access. There is no base-directory restriction, no path allowlist, and no protection against `../` traversal sequences in output paths specified by `EXPORT`, `WRITE`, or `INCLUDE` metacommands.

The [`INCLUDE`](metacommands.md#include) metacommand executes a script from any accessible path with full privileges. If the included path is constructed from a variable, an attacker who controls that variable can cause execsql to execute an arbitrary script file.

```sql
-- Risky: included path derived from a variable
-- !x! sub script_path !!&USER_INPUT!!
-- !x! INCLUDE !!script_path!!
```

Validate any variable used to construct file paths before use in file-related metacommands.

## Email (SMTP) { #smtp }

TLS is off by default. The relevant `execsql.conf` settings are:

```ini
[email]
host = mail.example.com
port = 587
use_tls = yes   # STARTTLS after initial plaintext connection
use_ssl = yes   # implicit TLS from connection start (preferred)
```

When `use_tls = yes` is set, execsql calls `STARTTLS` but does not explicitly verify the server certificate (Python's default `smtplib` behavior). For production deployments:

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

The `!'!` dereferencing form doubles apostrophes in the replacement value, which helps when inserting text data values into SQL literals:

```sql
-- !x! sub author_name !!&AUTHOR!!
SELECT * FROM documents WHERE author = '!'!author_name!'!';
```

This does not constitute full SQL escaping. For untrusted string input, validate the value before substitution.

## Recommendations { #recommendations }

1. **Use a dedicated service account.** Run execsql under an account with only the database roles and filesystem permissions needed for the specific script. Do not run as a database superuser or as `root`.

1. **Do not run untrusted scripts.** execsql provides no sandbox. Any script you run has the same capabilities as your user account.

1. **Use OS credential stores instead of config-file passwords.** Install `execsql2[auth]` and rely on the keyring integration rather than storing passwords in `execsql.conf`.

1. **Enable TLS for SMTP.** Set `use_ssl = yes` in the `[email]` section, or at minimum `use_tls = yes`. Do not send credentials over an unencrypted SMTP connection.

1. **Audit scripts that use `SHELL` or `INCLUDE` with variable-derived paths.** Trace where each variable originates. If any value comes from outside the script (environment, prompt, file content), validate it before use in a command that touches the filesystem or executes a process.

1. **Restrict access to `execsql.conf`.** Configuration files may contain usernames, SMTP settings, and obfuscated passwords. Ensure file permissions prevent reads by other users (`chmod 600 execsql.conf` on Linux/macOS).
