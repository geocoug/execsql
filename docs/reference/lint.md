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
execsql lint -f latin1 legacy/                # scripts saved in Latin-1
cat load.sql | execsql lint -                 # one script from stdin, reported as <stdin>
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

The [rules](#rules) below explain each code. `execsql lint` replaced the `--lint` option of `run`, which was removed.

## Reading scripts { #reading }

Scripts are read as UTF-8 unless `-f`/`--script-encoding` names another encoding, or `[encoding] script` is set in a [config file](configuration.md#configuration). Config files are read once, from the system, user and working-directory locations, plus any file passed with `--config` — not from each script's own directory, so pass a script folder's `execsql.conf` with `--config` if it sets the encoding. A script that does not decode is reported as [`P001`](#p001).

`-` in place of a path reads one script from stdin and reports it as `<stdin>`. It cannot be combined with other paths. `INCLUDE` targets in a stdin script are resolved from the working directory.

## Project settings { #config }

`--select` and `--ignore` can live in the `[lint]` section of a
[config file](configuration.md#config_lint), so every run — terminal, CI, the
pre-commit hook — checks the same rules:

```ini
[lint]
ignore = V002
```

A flag replaces the config value rather than adding to it: with the file above,
`execsql lint --ignore F002` reports `V002` again. An unknown code in the file is
a usage error (exit 2), and [`execsql config --validate`](../getting-started/syntax.md#config_validate)
reports it with its line.

## Exit status { #exit_status }

| Status | Meaning                                                                                                                           |
| ------ | --------------------------------------------------------------------------------------------------------------------------------- |
| 0      | No errors. Warnings alone do not fail the run, unless `--strict` is given.                                                        |
| 1      | At least one reported issue is an error — or, with `--strict`, any issue at all — or no `.sql` file was found in the given paths. |
| 2      | Usage error, such as an unknown rule code in `--select` or `--ignore`.                                                            |

`P001` to `P004` are errors; every other rule is a warning. To fail a CI step on warnings as well, add `--strict` (or `strict = yes` in the [`[lint]` section](#config) of a config file); `--no-strict` turns it off for one run.

## Choosing rules { #select }

`--select` reports only the rules it names, and `--ignore` drops rules. Both take a full code (`V001`) or a prefix (`V` for every variable rule), in any case, separated by commas or given more than once:

```sh
execsql lint scripts/ --select V,F
execsql lint scripts/ --select V --select F      # same thing
execsql lint scripts/ --select V --ignore V002   # --ignore wins over --select
```

An entry that matches no rule is a usage error (exit status 2), so a typo in `--ignore` cannot quietly ignore nothing.

`P001` (the script does not parse) is always reported, whatever `--select` and `--ignore` say. A script that does not parse cannot run, so reporting "no issues" for it would be false.

## Output formats { #output }

`--output-format text` (the default) groups issues under each file, as shown above. On a terminal, a message too long for the window wraps under the message column; piped output is never wrapped.

`--output-format github` prints one [GitHub Actions workflow command](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#setting-a-warning-message) per issue and nothing else, so GitHub shows each issue on the pull request; see [CI](#ci).

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

On GitHub Actions, `--output-format github` turns each issue into an annotation
shown on the pull request next to the line it names, and the step still fails on
errors:

```yaml
- run: execsql lint --output-format github scripts/
```

```text
::warning file=scripts/validate_orders.sql,line=10,title=V001 undefined-variable::undefined variable !!output_path!!
```

To fail on warnings too, run `execsql lint --strict scripts/` as its own step.

### Pre-commit { #pre-commit }

The `execsql-lint` [pre-commit](https://pre-commit.com/) hook runs `execsql lint` on every staged `*.sql` file and fails the commit when any has an error. Warnings are reported but do not fail it.

```yaml
repos:
  - repo: https://github.com/geocoug/execsql
    rev: v2.25.0
    hooks:
      - id: execsql-lint
        args: [--ignore, V002] # optional: any execsql lint option
```

## Rules { #rules }

Codes are grouped by subject: `P` parsing, `S` the script as a whole, `V` variables, `I` `INCLUDE` and `EXECUTE SCRIPT` targets, `F` control flow. A code is never renumbered or reused, so `--ignore` lists keep working across upgrades.

| Code          | Name                  | Severity |
| ------------- | --------------------- | -------- |
| [P001](#p001) | `parse-error`         | error    |
| [P002](#p002) | `split-dollar-quote`  | error    |
| [P003](#p003) | `unknown-metacommand` | error    |
| [P004](#p004) | `unknown-condition`   | error    |
| [S001](#s001) | `empty-script`        | warning  |
| [V001](#v001) | `undefined-variable`  | warning  |
| [V002](#v002) | `unused-variable`     | warning  |
| [I001](#i001) | `missing-include`     | warning  |
| [I002](#i002) | `missing-script`      | warning  |
| [F001](#f001) | `constant-condition`  | warning  |
| [F002](#f002) | `unreachable-code`    | warning  |

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

A script that cannot be decoded with the chosen encoding is also reported as `P001`, with the message `cannot decode as utf-8 (...); set -f/--script-encoding`.

Every block-structure error is reported, each on its own line, and every other rule still checks the rest of the script: lint recovers from the error by skipping a closing keyword that has nothing to close, and closing a block that is still open where a closing keyword or the end of the file says it should be. A misspelled block keyword is a common cause, and it shows up as a [`P003`](#p003) next to the `P001` it leads to:

```sql
-- !x! IF(HASROWS(staging.orders))
-- !x! iff(HASROWS(staging.returns))
insert into returns select * from !!source_schema!!.returns;
-- !x! ENDIF
-- !x! ENDIF
-- !x! LOOP WHILE (HASROWS(staging.pending))
delete from staging.pending where id = (select min(id) from staging.pending);
```

```text
load.sql
  2  error    P003  unknown or malformed metacommand: iff(HASROWS(staging.returns))
  3  warning  V001  undefined variable !!source_schema!!
  5  error    P001  ENDIF on line 5 of load.sql has no matching IF
  6  error    P001  Unmatched LOOP block starting on line 6 at end of file load.sql
```

`execsql run` stops at the first of these. Fix the `P001`s first: a finding the recovery leads to can go away once the blocks match.

### P002 `split-dollar-quote` { #p002 }

A dollar-quoted body (`$$ ... $$` or `$tag$ ... $tag$`), such as a PostgreSQL function or `DO` block, contains a line ending in `;`. *execsql* ends a SQL statement at every line that ends in `;`, including lines inside a dollar-quoted body, so the function is sent to the database in pieces. The first piece fails with `unterminated dollar-quoted string`. With `ERROR_HALT OFF` it is worse: the statements inside the body then run on their own, against live data, and the function is never created.

```sql
create or replace function purge_staging() returns void as $body$
begin
    delete from staging.orders;
end;
$body$ language plpgsql;
```

```text
load.sql
  1  error    P002  dollar-quoted body $body$ is split at the first line ending in ';'; put the statement between BEGIN SQL and END SQL
```

Put the statement between [`BEGIN SQL` and `END SQL`](metacommands.md#beginsql), which send everything between them as one statement:

```sql
-- !x! BEGIN SQL
create or replace function purge_staging() returns void as $body$
begin
    delete from staging.orders;
end;
$body$ language plpgsql;
-- !x! END SQL
```

A body that opens and closes on one line, and `$$` inside a comment, a `'...'` literal or a quoted identifier, are not reported. One issue is reported per body, on the line where it opens.

### P003 `unknown-metacommand` { #p003 }

A metacommand that *execsql* does not recognize: the keyword is misspelled, or the keyword is right but the rest of the line fits none of its forms. `execsql run` stops at such a line with `Unknown metacommand`, even with `METACOMMAND_ERROR_HALT OFF`, so a typo in a branch that rarely runs stays hidden until that branch does.

```sql
-- !x! SUBSTITUTE region north
-- !x! EXPORT staging.orders TOO orders.csv AS CSV
-- !x! WRITE "Configuration file not found" halt
```

```text
load.sql
  1  error    P003  unknown or malformed metacommand: SUBSTITUTE region north
  2  error    P003  unknown or malformed metacommand: EXPORT staging.orders TOO orders.csv AS CSV
  3  error    P003  unknown or malformed metacommand: WRITE "Configuration file not found" halt
```

Each metacommand is checked against the same list `execsql run` uses, including metacommands added by installed plugins (`execsql list plugins`; see [Adding metacommands](../dev/adding_metacommands.md)). The [metacommand reference](metacommands.md) gives the forms each one accepts.

A metacommand that contains a substitution variable (`!!var!!`, `!'!var!'!`, `!"!var!"!` or a deferred `!{var}!`) is not checked, because its text is not known until the variable is replaced at run time.

### P004 `unknown-condition` { #p004 }

A condition uses a test *execsql* does not have, such as `hasrowz(...)` for `hasrows(...)`, or cannot be parsed, such as an unbalanced parenthesis or a dangling `and`. Every condition is checked: `IF`, `ELSEIF`, `ANDIF`, `ORIF`, `LOOP WHILE` / `UNTIL`, `EXECUTE SCRIPT ... WHILE` / `UNTIL`, and the conditions in `ASSERT` and `WAIT_UNTIL`.

```sql
-- !x! IF(hasrowz(staging.orders))
-- !x! ANDIF(table_exists(staging.orders) and)
insert into orders select * from staging.orders;
-- !x! ENDIF
-- !x! ASSERT hasrowz(orders) "orders is empty"
```

```text
load.sql
  1  error    P004  unknown or malformed condition: hasrowz(staging.orders)
  2  error    P004  unknown or malformed condition: table_exists(staging.orders) and
  5  error    P004  unknown or malformed condition: hasrowz(orders)
```

A substitution variable in a condition is read as a placeholder value, tried as a boolean, a number and a name, so it fits wherever a variable can go: the whole condition (`IF(!!ready!!)`), a test's argument (`hasrows(!!table!!)`, `ROW_COUNT_EQ(staging.customers, !!row_count!!)`) or text in quotes. A condition that cannot parse with any of them is still reported. There is no `=` comparison, so `ASSERT !!$PG_UPSERT_QA_PASSED!! = TRUE` is an error, and `ASSERT IS_TRUE(!!$PG_UPSERT_QA_PASSED!!)` is the form to use.

`execsql run` stops at an `IF`, `ELSEIF`, `ANDIF`, `ORIF` or `LOOP` whose condition does not parse, even with `METACOMMAND_ERROR_HALT OFF`. In `ASSERT` and `WAIT_UNTIL` it is a metacommand error, so with `METACOMMAND_ERROR_HALT OFF` the run carries on and the `ASSERT` never checks anything. The [`IF` metacommand](metacommands.md#if_cmd) lists every conditional test and its arguments.

Conditions are parsed, never evaluated: lint does not connect to a database, so it cannot tell whether `hasrows(staging.orders)` would be true, only that it is a valid test.

### S001 `empty-script` { #s001 }

The file is empty or contains only whitespace. Usually a file that was created and never filled in, or emptied by mistake.

### V001 `undefined-variable` { #v001 }

A `!!variable!!` is referenced, but nothing in the script defines it. At run time an undefined variable is left in the text as written, so the SQL or metacommand fails, or does something other than intended.

```sql
-- !x! SUB report_dir /tmp/reports
-- !x! EXPORT stale_orders TO !!output_path!!/stale.csv AS CSV
```

A definition is any metacommand in the same file that sets a variable:

- the SUB family: `SUB`, `SUB_EMPTY`, `SUB_ADD`, `SUB_APPEND`, `SUBDATA`, `SUB_LOCAL`, `SUB_TEMPFILE`, `SUB_ENCRYPT`, `SUB_DECRYPT`, the keys of `SUB_QUERYSTRING`, and the keys of a `SUB_INI` file that exists at lint time;
- the prompts that store an answer: `PROMPT ENTER_SUB`, `ASK ... SUB`, `PROMPT ASK ... SUB` (with or without `COMPARE`), `PROMPT OPENFILE SUB`, `PROMPT SAVEFILE SUB` and `PROMPT DIRECTORY SUB` (every variable named after `SUB`), and both variables of `PROMPT CREDENTIALS`.

Definitions inside `BEGIN SCRIPT` blocks that the file runs with `EXECUTE SCRIPT` count too, and so does a definition that comes after the first use.

System variables start with `$` and user variables do not, so the two never stand in for each other: `!!date_tag!!` is reported (the system variable is `!!$DATE_TAG!!`), and so is `!!$region!!` after `SUB region north`.

Not reported:

- System variables (`!!$DATE_TAG!!`, `!!$DB_NAME!!`, …), `!!$ARG_n!!` set with `-a`, and `!!$COUNTER_n!!`.
- References with the `&` (environment), `@` (column), `~` (local), `#` and `+` prefixes, which resolve only at run time.

Variables defined somewhere lint cannot see are reported: in a configuration file, on the command line other than as `$ARG_n`, or in a file pulled in with `INCLUDE` (lint does not read `INCLUDE`d files for definitions). If that is how a library works, `--ignore V001` for those scripts.

### V002 `unused-variable` { #v002 }

A metacommand defines a variable that nothing in the script reads, either as `!!variable!!` or with the `sub_defined(variable)` and `sub_empty(variable)` conditional tests. Almost always one half of a spelling mistake: the example under [V001](#v001) reports `!!report_dir!!` here and `!!output_path!!` there, and together the two warnings point at the typo.

A variable that a script sets for an `INCLUDE`d file, or for whoever `INCLUDE`s it, is also reported, because lint checks each file on its own. Ignore the rule for such files.

### I001 `missing-include` { #i001 }

An `INCLUDE` names a file that does not exist. Lint resolves a relative path against the directory of the script being checked. At run time execsql resolves it against the current working directory, so run execsql from the script's directory, or use absolute paths, for this check to match what a run will do.

Not reported for `INCLUDE IF EXISTS`, or when the path contains a `!!variable!!`, since the file then depends on values known only at run time.

### I002 `missing-script` { #i002 }

`EXECUTE SCRIPT` names a script that no `BEGIN SCRIPT` block in the file defines. Not reported for `EXECUTE SCRIPT IF EXISTS`.

A script defined in an `INCLUDE`d file is reported, because lint does not read `INCLUDE`d files.

### F001 `constant-condition` { #f001 }

An `IF` condition is always true or always false, so one of its branches can never run. Conditions such as `True` and `Yes` are always true; `False` and `No` are always false. `1=1` is not a condition execsql accepts (there is no `=` test), so lint reports it as [`P004`](#p004) instead.

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
