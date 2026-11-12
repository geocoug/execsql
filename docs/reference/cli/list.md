# execsql list

```text
execsql list metacommands|encodings|plugins|keywords [--output-format text|json]
execsql list metacommands [KEYWORD] [--output-format text|json]
execsql list schema --dsn URL [--schema NAME] [--table NAME]
```

| Command        | Prints                                                                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `metacommands` | Every metacommand with its category and a one-line summary. With a keyword (`execsql list metacommands export query`), that metacommand's syntax lines and a link to its reference section. |
| `encodings`    | Every character encoding name accepted by `-e`, `-f`, `-g` and `-i`.                                                                                                                        |
| `plugins`      | Installed plugins: metacommands, exporters, importers. See [Plugin System](../../dev/architecture.md#plugin-system).                                                                        |
| `keywords`     | The full vocabulary: metacommands by category, conditions, CONFIG options, export formats, database types, variable patterns.                                                               |

Each list is its own command, `execsql list keywords --help` included. With
`--output-format json`, `keywords` prints the JSON that editor tooling such as
the VS Code grammar generator reads.

`schema` connects to the selected database and always prints versioned JSON.
Use exact schema and table names to limit the returned metadata; no application
rows are fetched. See [schema discovery](../schema.md) for examples, errors,
connection ownership and adapter capabilities.
