# execsql inspect

Inspect resources before execution. Database inspection is currently available:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --schema main --table samples
```

`database` connects to the selected database and always prints versioned JSON
metadata: tables/views, columns and catalog types, primary-key columns and outgoing
foreign-key relationships. It does not run SQL scripts or fetch application rows.

| Option          | Meaning                                                                         |
| --------------- | ------------------------------------------------------------------------------- |
| `--dsn URL`     | Required connection URL. Uses supplied or driver credentials without prompting. |
| `--schema NAME` | Optional exact, case-sensitive schema name.                                     |
| `--table NAME`  | Optional exact, case-sensitive table or view name.                              |

See [schema discovery](../schema.md) for the JSON contract, examples, errors,
connection ownership and adapter coverage. Run `execsql inspect --help` to list
available inspection commands, or `execsql inspect database --help` for options.

`inspect` is a reserved command name. A script named exactly `inspect`, with no
extension, runs with `execsql run inspect`.
