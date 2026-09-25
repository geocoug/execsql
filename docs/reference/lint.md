# Lint Rules { #lint }

`execsql lint` checks scripts without connecting to a database or running anything. It finds the problems that otherwise surface halfway through a run against a live database: a block that is never closed, a variable spelled two different ways, an `INCLUDE` of a file that is not there.

```sh
execsql lint scripts/                         # every *.sql file under scripts/, recursively
execsql lint load.sql transform.sql           # specific files
execsql lint scripts/ --ignore V002           # skip one rule
execsql lint scripts/ --select F              # only the control-flow rules
execsql lint scripts/ --output-format concise # one path:line line per issue
execsql lint scripts/ --output-format json    # for tools and CI annotations
execsql lint scripts/ --statistics            # how often each rule fired
```

Issues are grouped under each file, in line order, and every issue names its rule code:

```text
scripts/validate_orders.sql
   2  warning  V002  variable !!report_dir!! is never used
  10  warning  V001  undefined variable !!output_path!!

scripts/sub/flow.sql
  1  warning  F001  IF(True) is always true; its ELSE never runs
  7  warning  F002  unreachable: HALT on line 6 ends the script

Found 4 issues in 2 files: 4 warnings (12 files checked)
```

The [rules](#rules) below explain each code. The `--lint` option of `run` applies the same checks to the one script it is given, in the same layout, but has no `--select`, `--ignore`, or output-format options.

## Exit status { #exit_status }

| Status | Meaning                                                                                  |
| ------ | ---------------------------------------------------------------------------------------- |
| 0      | No errors. Warnings alone do not fail the run.                                           |
| 1      | At least one reported issue is an error, or no `.sql` file was found in the given paths. |
| 2      | Usage error, such as an unknown rule code in `--select` or `--ignore`.                   |

Only `P001` is an error today; every other rule is a warning. To fail a CI step on warnings as well, use JSON output and test for an empty array (see [CI](#ci)).

## Choosing rules { #select }

`--select` reports only the rules it names, and `--ignore` drops rules. Both take a full code (`V001`) or a prefix (`V` for every variable rule), in any case, separated by commas or given more than once:

```sh
execsql lint scripts/ --select V,F
execsql lint scripts/ --select V --select F      # same thing
execsql lint scripts/ --select V --ignore V002   # --ignore wins over --select
```

An entry that matches no rule is a usage error (exit status 2), so a typo in `--ignore` cannot quietly ignore nothing.

`P001` (the script does not parse) is always reported, whatever `--select` and `--ignore` say. A script that does not parse has not been checked, so reporting "no issues" for it would be false.

## Output formats { #output }

`--output-format text` (the default) groups issues under each file, as shown above. On a terminal, a message too long for the window wraps under the message column; piped output is never wrapped.

`--output-format concise` prints one line per issue, which suits `grep` and editors that jump to `path:line`:

```text
$ execsql lint scripts/ --output-format concise
scripts/validate_orders.sql:2: V002 variable !!report_dir!! is never used
scripts/validate_orders.sql:10: V001 undefined variable !!output_path!!

Found 2 issues in 1 file: 2 warnings (12 files checked)
```

`--output-format json` writes a single JSON array to stdout and nothing else, covering every file checked. Each element has these fields:

| Field      | Value                                                             |
| ---------- | ----------------------------------------------------------------- |
| `file`     | The script's path, as given or found under a directory.           |
| `line`     | 1-based line number, or `null` when the issue has no single line. |
| `code`     | Rule code, e.g. `"V001"`.                                         |
| `rule`     | Rule name, e.g. `"undefined-variable"`.                           |
| `severity` | `"error"` or `"warning"`.                                         |
| `message`  | The same text the text format shows.                              |

```json
[
  {
    "file": "scripts/validate_orders.sql",
    "line": 2,
    "code": "V002",
    "rule": "unused-variable",
    "severity": "warning",
    "message": "variable !!report_dir!! is never used"
  }
]
```

No issues gives `[]`. Issues are grouped by file, and ordered by line within each file.

`--statistics` replaces the issue list with a count per rule, most frequent first. With `--output-format json` it is an array of `{"code", "rule", "severity", "count"}` objects.

```text
$ execsql lint scripts/ --statistics
  14  V001  undefined-variable
   3  V002  unused-variable
   1  F002  unreachable-code

Found 18 issues in 7 files: 18 warnings (12 files checked)
```

## CI { #ci }

Run `execsql lint` as its own step. It needs no database, and it exits 1 only on errors:

```yaml
- run: execsql lint scripts/
```

To turn each issue into a GitHub annotation on the pull request, convert the JSON:

```yaml
- run: |
    execsql lint scripts/ --output-format json > lint.json || true
    jq -r '.[] | "::\(.severity) file=\(.file),line=\(.line // 1),title=\(.code)::\(.message)"' lint.json
    test "$(jq 'map(select(.severity == "error")) | length' lint.json)" -eq 0
```

Replace the last line with `test "$(jq length lint.json)" -eq 0` to fail on warnings too.

## Rules { #rules }

Codes are grouped by subject: `P` parsing, `S` the script as a whole, `V` variables, `I` `INCLUDE` and `EXECUTE SCRIPT` targets, `F` control flow. A code is never renumbered or reused, so `--ignore` lists keep working across upgrades.

| Code          | Name                 | Severity |
| ------------- | -------------------- | -------- |
| [P001](#p001) | `parse-error`        | error    |
| [S001](#s001) | `empty-script`       | warning  |
| [V001](#v001) | `undefined-variable` | warning  |
| [V002](#v002) | `unused-variable`    | warning  |
| [I001](#i001) | `missing-include`    | warning  |
| [I002](#i002) | `missing-script`     | warning  |
| [F001](#f001) | `constant-condition` | warning  |
| [F002](#f002) | `unreachable-code`   | warning  |

### P001 `parse-error` { #p001 }

The script cannot be parsed. The usual cause is a block that is opened and never closed, or closed without being opened: `IF` without `ENDIF`, `LOOP` without `END LOOP`, `BEGIN BATCH` without `END BATCH`, `BEGIN SCRIPT` without `END SCRIPT`, or an `END SCRIPT` whose name does not match its `BEGIN SCRIPT`.

```sql
-- !x! IF(HASROWS(staging.orders))
insert into orders select * from staging.orders;
-- the ENDIF is missing
```

```text
load.sql
  1  error    P001  Unmatched IF block starting on line 1 at end of file load.sql
```

No other rule runs on a script that does not parse. Fix this one first.

### S001 `empty-script` { #s001 }

The file is empty or contains only whitespace. Usually a file that was created and never filled in, or emptied by mistake.

### V001 `undefined-variable` { #v001 }

A `!!variable!!` is referenced, but nothing in the script defines it. At run time an undefined variable is left in the text as written, so the SQL or metacommand fails, or does something other than intended.

```sql
-- !x! SUB report_dir /tmp/reports
-- !x! EXPORT stale_orders TO !!output_path!!/stale.csv AS CSV
```

A definition is any SUB-family metacommand in the same file: `SUB`, `SUB_EMPTY`, `SUB_ADD`, `SUB_APPEND`, `SUBDATA`, `SUB_LOCAL`, `SUB_TEMPFILE`, `SUB_ENCRYPT`, `SUB_DECRYPT`, `SUB_QUERYSTRING`, and the keys of a `SUB_INI` file that exists at lint time. Definitions inside `BEGIN SCRIPT` blocks that the file runs with `EXECUTE SCRIPT` count too, and so does a definition that comes after the first use.

Not reported:

- System variables (`!!$DATE_TAG!!`, `!!$DB_NAME!!`, …), `!!$ARG_n!!` set with `-a`, and `!!$COUNTER_n!!`.
- References with the `&` (environment), `@` (column), `~` (local), `#` and `+` prefixes, which resolve only at run time.

Variables defined somewhere lint cannot see are reported: in a configuration file, on the command line other than as `$ARG_n`, or in a file pulled in with `INCLUDE` (lint does not read `INCLUDE`d files for definitions). If that is how a library works, `--ignore V001` for those scripts.

### V002 `unused-variable` { #v002 }

A SUB-family metacommand defines a variable that nothing in the script references. Almost always one half of a spelling mistake: the example under [V001](#v001) reports `!!report_dir!!` here and `!!output_path!!` there, and together the two warnings point at the typo.

A variable that a script sets for an `INCLUDE`d file, or for whoever `INCLUDE`s it, is also reported, because lint checks each file on its own. Ignore the rule for such files.

### I001 `missing-include` { #i001 }

An `INCLUDE` names a file that does not exist. Lint resolves a relative path against the directory of the script being checked. At run time execsql resolves it against the current working directory, so run execsql from the script's directory, or use absolute paths, for this check to match what a run will do.

Not reported for `INCLUDE IF EXISTS`, or when the path contains a `!!variable!!`, since the file then depends on values known only at run time.

### I002 `missing-script` { #i002 }

`EXECUTE SCRIPT` names a script that no `BEGIN SCRIPT` block in the file defines. Not reported for `EXECUTE SCRIPT IF EXISTS`.

A script defined in an `INCLUDE`d file is reported, because lint does not read `INCLUDE`d files.

### F001 `constant-condition` { #f001 }

An `IF` condition is always true or always false, so one of its branches can never run. Conditions such as `True`, `1=1` and `Yes` are always true; `False`, `1=0`, `0=1` and `No` are always false.

```sql
-- !x! IF(True)
select 'always';
-- !x! ELSE
select 'never';
-- !x! ENDIF
```

`IF(True)` is a reasonable thing to write while developing a script. Leaving it in means the `ELSE` branch no longer runs, without anything saying so.

An always-true `IF` with no `ELSEIF` or `ELSE` is not reported: nothing is unreachable. Neither is an `IF` with an `ANDIF` or `ORIF`, whose result depends on more than the constant.

### F002 `unreachable-code` { #f002 }

A statement follows an unconditional `HALT` in the same block, so it can never run.

```sql
-- !x! HALT
drop table staging.orders;
```

`HALT DISPLAY` is not treated as final, because the person running the script can cancel it.
