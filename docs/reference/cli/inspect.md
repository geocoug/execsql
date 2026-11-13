# execsql inspect

Inspect database structure without executing scripts or reading application rows:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --schema main --table samples
execsql inspect schema main --dsn sqlite:///project.sqlite
execsql inspect table samples --schema main --dsn sqlite:///project.sqlite
```

`database` connects to the selected database and prints its identity, engine and
schema/namespace inventory by default, with visible table/view counts. Namespaces
with no visible objects are included. Schema-less databases show objects directly;
unavailable namespace enumeration is labeled explicitly.
With `--schema`, it lists matching tables/views, column counts and key summaries.
With `--table`, it shows ordered columns, catalog types, nullability, primary keys
and outgoing foreign-key relationships. Unknown and unavailable metadata are
marked explicitly. No SQL scripts are run and no application rows are fetched.

| Command               | Scope and text output                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `inspect database`    | Database identity and namespace counts; optional `--schema` and `--table` filters retain object overview/details.  |
| `inspect schema NAME` | Tables/views, column counts and key summaries in one exact schema.                                                 |
| `inspect table NAME`  | Ordered columns, types, nullability, keys and relationships for matching tables/views; optional `--schema` filter. |

`NAME` is required for `schema` and `table`. Names are exact and case-sensitive;
a dot in a name is literal, so use `--schema public` separately from the table
name. Without that filter, table inspection shows every exact match in the
adapter's default scope. Original `inspect database` filters remain supported.

For automation, request the shared versioned JSON contract explicitly:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --output-format json > schema.json
```

`--dsn` and `--connection-string` are interchangeable, as they are for `execsql run`.

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

| Option                                 | Meaning                                                                                                |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `--dsn URL`, `--connection-string URL` | Required connection URL. Include the user for password prompting.                                      |
| `--schema NAME`                        | Optional exact, case-sensitive schema name for `database` and `table`; `schema` takes it positionally. |
| `--table NAME`                         | Optional exact table/view name for `database`; `table` takes it positionally.                          |
| `--output-format text\|json`           | Readable text (default) or versioned JSON.                                                             |
| `-w`, `--no-passwd`                    | Disable password prompting; use supplied or driver credentials.                                        |
| `--prompt-password`                    | Allow a hidden password prompt for a URL user on a terminal, including in JSON mode.                   |

See [schema discovery](../schema.md) for the JSON contract, examples, errors,
connection ownership and adapter coverage. Run `execsql inspect --help` to list
available inspection commands, or `execsql inspect table --help` for a command's arguments and options.

`inspect` is a reserved command name. A script named exactly `inspect`, with no
extension, runs with `execsql run inspect`.
