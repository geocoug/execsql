# execsql inspect

Inspect database structure or importable files without executing scripts:

```sh
execsql inspect database --dsn sqlite:///project.sqlite
execsql inspect schema main --dsn sqlite:///project.sqlite
execsql inspect table samples --schema main --dsn sqlite:///project.sqlite
execsql inspect file results.csv
```

`database` connects to the selected database and prints its identity, engine and
schema/namespace inventory by default, with visible table/view counts. Namespaces
with no visible objects are included. Count headings say `Visible tables` and
`Visible views`; permissions and the adapter's default scope determine visibility. Schema-less databases show objects directly;
unavailable namespace enumeration is labeled explicitly.
`schema NAME` lists matching tables/views, column counts and key summaries.
`table NAME` shows ordered columns, catalog types, nullability, primary keys
and outgoing foreign-key relationships. Unknown and unavailable metadata are
marked explicitly. No SQL scripts are run. Database inspection fetches no
application rows; file inspection reads source data for inference.

| Command               | Scope and text output                                                                                                      |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `inspect database`    | Database identity and namespace counts; no schema/table filters.                                                           |
| `inspect schema NAME` | Tables/views, column counts and key summaries in one exact schema.                                                         |
| `inspect table NAME`  | Ordered columns, types, nullability, keys and relationships for matching tables/views; optional `--schema` filter.         |
| `inspect file PATH`   | File format, columns and IMPORT-inferred types; list workbook sheets or select one with `--sheet`. No database connection. |

The following connection options and catalog rules apply to database/schema/table
inspection. File inspection has its own [options and reference](../files.md),
including configuration, encoding, sampling and worksheet selection.

`NAME` is required for `schema` and `table`. Names are exact and case-sensitive;
a dot in a name is literal, so use `--schema public` separately from the table
name. Without that filter, table inspection shows every exact match in the
adapter's default scope. `database` has no `--schema` or `--table` flags.
PostgreSQL's reserved `pg_*` schemas are excluded by default; explicitly naming
one with `schema NAME` or `table NAME --schema SCHEMA` permits inspection.

For automation, request the shared versioned JSON contract explicitly:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --output-format json > schema.json
```

`--dsn` and `--connection-string` are interchangeable, as they are for `execsql run`.
Omit the URL to use `[connect]` configuration defaults. `--config FILE` reads
an additional configuration file after the normal system/user/working-directory
search and local chains. An explicit URL determines the target and identity;
connection controls such as encoding, certificate handling and keyring preferences
still apply. Inspection never creates a database or executes startup scripts.

For a server requiring a password, include the user but omit the password:

```sh
execsql inspect schema public --dsn postgresql://analyst@localhost/project
```

Text mode on an interactive terminal follows the configured `password_prompt`
preference for the connection's user, with hidden input and configured keyring
lookup/storage. Use `--no-passwd` to disable prompting and keyring use for
OS/driver authentication. JSON mode and redirected stdin never prompt automatically;
`--prompt-password` explicitly allows prompting for JSON output when stdin is a
terminal. The two password flags cannot be combined.

Failures exit with status 1. Text mode puts errors and diagnostic hints on stderr;
JSON mode returns the API's structured error on stdout. Driver exception text and
credential-bearing URLs are not echoed.

| Option                                 | Meaning                                                                                             |
| -------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `--dsn URL`, `--connection-string URL` | Optional connection URL; omit to use `[connect]` defaults. Include the user for password prompting. |
| `--config FILE`                        | Additional configuration file; connection controls apply even with a DSN.                           |
| `--show-settings`                      | Include nonsecret connection controls in text output; hidden by default.                            |
| `--show-config`                        | Include loaded configuration files in text output; hidden by default.                               |
| `--schema NAME`                        | Optional exact, case-sensitive schema name for `table`; `schema` takes it positionally.             |
| `--output-format text\|json`           | Readable text (default) or versioned JSON.                                                          |
| `-w`, `--no-passwd`                    | Disable password prompting; use supplied or driver credentials.                                     |
| `--prompt-password`                    | Override the configured prompt preference on a terminal, including in JSON mode.                    |

See [schema discovery](../schema.md) for the JSON contract, examples, errors,
connection ownership and adapter coverage. Run `execsql inspect --help` to list
available inspection commands, or `execsql inspect table --help` for a command's arguments and options.

The display flags also apply to `inspect file`, where settings describe import
and inference controls. JSON and Python always retain `settings` and
`config_files`, independently of these text flags.

`inspect` is a reserved command name. A script named exactly `inspect`, with no
extension, runs with `execsql run inspect`.
