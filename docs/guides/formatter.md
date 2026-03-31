# execsql-format

`execsql-format` is a code formatter for execsql script files. It normalizes metacommand indentation, uppercases metacommand keywords, and optionally reformats SQL statements. Run it before committing scripts, in CI, or any time you want consistent formatting across a codebase.

## Installation { #installation }

`execsql-format` is installed automatically as part of the `execsql2` package — no extra steps required.

```bash
pip install execsql2
```

After installation, the `execsql-format` command is available on your PATH.

## Usage { #usage }

```bash
execsql-format [OPTIONS] FILE_OR_DIR [FILE_OR_DIR ...]
```

Pass one or more files or directories. Directories are searched recursively for `*.sql` files.

By default, formatted output is written to stdout. Use `--in-place` to overwrite files, or `--check` to report which files need changes without modifying them.

### Options { #options }

| Option             | Default  | Description                                                                                         |
| ------------------ | -------- | --------------------------------------------------------------------------------------------------- |
| `FILE_OR_DIR`      | required | One or more files or directories to format. Directories are searched recursively for `*.sql` files. |
| `--check`          | off      | Exit with code 1 if any file would be reformatted. Does not write any changes. Useful in CI.        |
| `-i`, `--in-place` | off      | Modify files in place instead of writing to stdout.                                                 |
| `--no-sql`         | off      | Skip SQL reformatting via sqlglot. Only normalizes metacommand indentation and keyword casing.      |
| `--indent N`       | `4`      | Number of spaces per indent level.                                                                  |

## What Gets Formatted { #what-gets-formatted }

### Metacommand keyword casing { #keyword-casing }

All metacommand keywords are uppercased. Arguments after the keyword are preserved exactly as written.

```sql
-- before
-- !x! if(!!myvar!! = "yes")
-- !x! sub_add mykey myvalue

-- after
-- !x! IF(!!myvar!! = "yes")
-- !x! SUB_ADD mykey myvalue
```

### Metacommand indentation { #indentation }

Metacommands that open a block (`IF`, `LOOP`, `BEGIN SCRIPT`, `BEGIN BATCH`, `BEGIN SQL`, `CREATE SCRIPT`) increase the indent level for everything that follows. Their matching close keywords (`ENDIF`, `END LOOP`, `END SCRIPT`, `END BATCH`, `END SQL`) are dedented back to the opening level.

`ELSE` and `ELSEIF` pivot at the same depth as their `IF`. `ANDIF` and `ORIF` are emitted at one level above the current depth without changing the depth counter.

```sql
-- !x! IF(!!status!! = "active")
    -- !x! SUB_ADD result "found"
-- !x! ELSE
    -- !x! SUB_ADD result "not found"
-- !x! ENDIF
```

### SQL block formatting { #sql-formatting }

SQL statements between metacommands are re-indented to match the current block depth and reformatted using [sqlglot](https://sqlglot.com/) in PostgreSQL dialect with pretty-printing enabled. Comment-only lines (single-line `--` and block `/* */` comments) are passed through without being sent to sqlglot.

execsql substitution variables (`!!varname!!`, `!{varname}!`) are replaced with valid SQL identifiers before formatting, then restored afterward, so the formatter does not corrupt them.

If sqlglot cannot parse a SQL statement, the original text is preserved unchanged.

Use `--no-sql` to skip SQL reformatting entirely and only normalize metacommands.

## Examples { #examples }

### Format to stdout

Preview what a file will look like after formatting without modifying it:

```bash
execsql-format myscript.sql
```

### Format a file in place

```bash
execsql-format --in-place myscript.sql
```

### Format all scripts in a directory

```bash
execsql-format --in-place scripts/
```

This recurses into subdirectories and formats every `*.sql` file found.

### Check mode for CI

Use `--check` in a CI pipeline to fail the build if any script is not formatted:

```bash
execsql-format --check scripts/
```

Exit code is `0` if all files are already formatted, `1` if any file would change.

### Use a two-space indent

```bash
execsql-format --indent 2 --in-place myscript.sql
```

### Skip SQL reformatting

Format only metacommand indentation and casing, leaving SQL statements untouched:

```bash
execsql-format --no-sql --in-place myscript.sql
```

## Before and After Example { #before-after }

The following script has inconsistent metacommand casing, no indentation inside the `IF` block, and unformatted SQL.

**Before:**

```sql
-- !x! sub_add schema "public"

-- !x! if(!!schema!! = "public")
-- !x! write Checking public schema...
select id,name,created_at from users where active = true order by name;
-- !x! endif

-- !x! loop while !!count!! < 3
-- !x! sub_add count !!#count + 1!!
-- !x! endloop
```

**After (`execsql-format myscript.sql`):**

```sql
-- !x! SUB_ADD schema "public"

-- !x! IF(!!schema!! = "public")
    -- !x! WRITE Checking public schema...
    SELECT
      id,
      name,
      created_at
    FROM users
    WHERE
      active = TRUE
    ORDER BY name;
-- !x! ENDIF

-- !x! LOOP WHILE !!count!! < 3
    -- !x! SUB_ADD count !!#count + 1!!
-- !x! END LOOP
```

## Pre-commit Hook { #pre-commit }

`execsql-format` can be used as a [pre-commit](https://pre-commit.com/) hook. Add the following to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/geocoug/execsql
    rev: v2.4.2
    hooks:
      - id: execsql-format
        args: [--in-place]
```

The hook runs on `*.sql` files. Pass any CLI options via `args`:

```yaml
# Check-only (CI — fail if files need formatting)
- id: execsql-format
  args: [--check]

# Auto-fix in place, skip SQL reformatting
- id: execsql-format
  args: [--in-place, --no-sql]

# Custom indent width
- id: execsql-format
  args: [--in-place, --indent, "2"]
```

## Exit Codes { #exit-codes }

| Code | Meaning                                                                                                           |
| ---- | ----------------------------------------------------------------------------------------------------------------- |
| `0`  | Success. All files formatted (or already up to date in `--check` mode).                                           |
| `1`  | One or more files would be reformatted (`--check` mode), a file could not be read, or no `.sql` files were found. |
