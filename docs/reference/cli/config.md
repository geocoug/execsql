# execsql config

```text
execsql config [SQL_SCRIPT] [--init | --validate] [--config FILE] [--output-format text|json]
```

Lists every configuration option: its current value, its default, and the
file that set it. Config files are read from the same places a run reads
them, in the same order. Passwords are shown as `***`.

```sh
execsql config                       # system, user and working-directory files
execsql config scripts/etl.sql       # also scripts/execsql.conf, as `run scripts/etl.sql` would
execsql config --config ci.conf      # also ci.conf, loaded last
execsql config --output-format json  # {"files_read": [...], "options": [...]}
execsql config --init > execsql.conf # start a new config file from the template
```

```text
Config files read, in order:
  /home/etl/.config/execsql.conf
  /home/etl/project/scripts/execsql.conf

[connect]
  server    db.example.com  /home/etl/.config/execsql.conf
  db_type   p               /home/etl/project/scripts/execsql.conf
  port                      default
```

Each JSON option has `section`, `key`, `type`, `value`, `default` and
`source` (`null` when the default applies).

## Validating config files { #config_validate }

A run stops at the first invalid value in a config file, and silently ignores
anything it does not recognize, so a misspelled key simply does nothing.
`--validate` checks every file a run would read — the same files, including
any a `config_file` setting chains to — and reports every problem with its
file and line:

```sh
execsql config --validate                   # the files a run from here would read
execsql config --validate scripts/etl.sql   # plus scripts/execsql.conf
execsql config --validate --config ci.conf  # plus ci.conf
```

```text
~/.config/execsql.conf
  2  warning  unknown key 'sever' in [connect]; did you mean 'server'?
  3  error    db_type = q: Invalid database type: q
  5  warning  unknown section [conect]; did you mean [connect]?
  8  warning  scan_lines belongs in [input], not [interface]

Found 4 problems in 1 file: 1 error, 3 warnings (2 config files checked)
```

| Severity  | Problem                                                                                                                                                        |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `error`   | An invalid value; a missing `[include_required]` file; a file that cannot be parsed (no section header, a key set twice, a bare `%`). A run fails on these.    |
| `warning` | An unknown section or key, with the likely intended name; a key in the wrong section; a `config_file` that names a missing file. A run ignores these silently. |

Values are checked by the same code a run uses, so `--validate` and a run
never disagree about a value. It exits `1` when any error is found; warnings
alone exit `0`. With `--output-format json` it prints
`{"files_checked": [...], "problems": [...]}`, each problem with `file`,
`line`, `severity` and `message`.
