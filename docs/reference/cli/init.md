# execsql init

```text
execsql init [DIR] [--script NAME | --no-script] [--no-config] [--no-pre-commit] [--force]
```

Sets up execsql in `DIR` (default: the current directory, created if missing):

| File                           | Content                                                                              | Skip with         |
| ------------------------------ | ------------------------------------------------------------------------------------ | ----------------- |
| `execsql.conf`                 | The commented template, as `execsql config --init` prints it                         | `--no-config`     |
| `main.sql`, or `--script NAME` | A header: PURPOSE, NOTES, PROJECT, COPYRIGHT, AUTHORS, and HISTORY with today's date | `--no-script`     |
| `.pre-commit-config.yaml`      | The `execsql-format` and `execsql-lint` hooks at this version                        | `--no-pre-commit` |

```text
$ execsql init warehouse --script load
  created     warehouse/execsql.conf
  created     warehouse/load.sql
  created     warehouse/.pre-commit-config.yaml
```

Existing files are never changed unless `--force` is given, and even then
`.pre-commit-config.yaml` is only ever added to: if it exists without the
execsql hooks, they are appended under `repos:` in the file's own
indentation, or — when `repos:` is not the file's last key — printed for you to
add by hand. `.sql` is added to a `--script` name without one, and folders in it
are created. To add a script to an existing project:

```sh
execsql init --no-config --no-pre-commit --script scripts/transform.sql
```

The new script passes the `execsql-format` and `execsql-lint` hooks as written.
