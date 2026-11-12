# execsql inspect

Inspect resources before execution. Database inspection is currently available:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --schema main --table samples
```

`database` connects to the selected database and prints readable tables by default.
Without `--table`, it lists matching tables/views, column counts and key summaries.
With `--table`, it shows ordered columns, catalog types, nullability, primary keys
and outgoing foreign-key relationships. Unknown and unavailable metadata are
marked explicitly. No SQL scripts are run and no application rows are fetched.

For automation, request the shared versioned JSON contract explicitly:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --output-format json > schema.json
```

For a server requiring a password, include the user but omit the password:

```sh
execsql inspect database --dsn postgresql://analyst@localhost/project --schema public
```

Text mode on an interactive terminal can prompt for that user's password using
hidden input. Passwords are not stored in the keyring. Use `--no-passwd` for
OS/driver authentication. JSON mode and redirected stdin never prompt automatically;
`--prompt-password` explicitly allows prompting for JSON output when stdin is a
terminal. The two password flags cannot be combined.

Failures exit with status 1. Text mode puts errors and diagnostic hints on stderr;
JSON mode returns the API's structured error on stdout. Driver exception text and
credential-bearing URLs are not echoed.

| Option                       | Meaning                                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------- |
| `--dsn URL`                  | Required connection URL. Include the user for password prompting.                         |
| `--schema NAME`              | Optional exact, case-sensitive schema name.                                               |
| `--table NAME`               | Optional exact, case-sensitive table or view name; shows column/key details in text mode. |
| `--output-format text\|json` | Readable text (default) or versioned JSON.                                                |
| `-w`, `--no-passwd`          | Disable password prompting; use supplied or driver credentials.                           |
| `--prompt-password`          | Allow a hidden password prompt for a URL user on a terminal, including in JSON mode.      |

See [schema discovery](../schema.md) for the JSON contract, examples, errors,
connection ownership and adapter coverage. Run `execsql inspect --help` to list
available inspection commands, or `execsql inspect database --help` for options.

`inspect` is a reserved command name. A script named exactly `inspect`, with no
extension, runs with `execsql run inspect`.
