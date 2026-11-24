# execsql list

```text
execsql list metacommands|encodings|plugins|keywords [--output-format text|json]
execsql list metacommands [KEYWORD] [--output-format text|json]
execsql list keywords [--categories | --category NAME] [--output-format text|json]
```

| Command        | Prints                                                                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `metacommands` | Every metacommand with its category and a one-line summary. With a keyword (`execsql list metacommands export query`), that metacommand's syntax lines and a link to its reference section. |
| `encodings`    | Standard-library text codec names and aliases for file I/O. Database charset names depend on the backend. See [Character Encoding](../../guides/encoding.md#encoding).                      |
| `plugins`      | Installed plugins: metacommands, exporters, importers. See [Plugin System](../../dev/architecture.md#plugin-system).                                                                        |
| `keywords`     | The full vocabulary: metacommands by category, conditions, CONFIG options, export formats, database types, variable patterns.                                                               |

Each list is its own command, `execsql list keywords --help` included. With
`--output-format json`, `keywords` prints the JSON that editor tooling such as
the VS Code grammar generator reads.

Use `--categories` to discover metacommand categories or `--category NAME` to
list the keywords in one category. Category names are case-insensitive. Each
filter prints one item per line in text mode and an array of strings in JSON mode.

```bash
execsql list keywords --categories
execsql list keywords --category control --output-format json
```

The full listing includes the combined formats for `EXPORT`, `EXPORT QUERY`,
`SERVE`, and `EXPORT_METADATA`. Its JSON also includes the formats by command.
