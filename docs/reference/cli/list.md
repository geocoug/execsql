# execsql list

```text
execsql list metacommands|encodings|plugins|keywords [--output-format text|json]
execsql list metacommands [KEYWORD] [--output-format text|json]
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
