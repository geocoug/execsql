# execsql-format

`execsql-format` is a code formatter for execsql script files. It normalizes metacommand indentation, uppercases metacommand keywords, and optionally reformats SQL statements. Run it before committing scripts, in CI, or any time you want consistent formatting across a codebase.

## Installation { #installation }

The `execsql-format` command is installed automatically with the `execsql2` package and is available on your PATH after install:

```bash
pip install execsql2
```

The metacommand-indentation and keyword-casing passes work out of the box. **SQL reformatting** (the optional sqlglot pass) requires the `[formatter]` extra, as of execsql2 2.19.0:

```bash
pip install "execsql2[formatter]"
```

Without the extra, `execsql-format` works in `--no-sql` mode (metacommand indentation and keyword casing only); invoking the SQL pass without `[formatter]` installed raises `ModuleNotFoundError: No module named 'sqlglot'`.

## Usage { #usage }

```bash
execsql-format [OPTIONS] FILE_OR_DIR [FILE_OR_DIR ...]
```

Pass one or more files or directories. Directories are searched recursively for `*.sql` files.

By default, formatted output is written to stdout. Use `--in-place` to overwrite files, or `--check` to report which files need changes without modifying them.

### Options { #options }

| Option             | Default  | Description                                                                                                                       |
| ------------------ | -------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `FILE_OR_DIR`      | required | One or more files or directories to format. Directories are searched recursively for `*.sql` files.                               |
| `--check`          | off      | Exit with code 1 if any file would be reformatted. Does not write any changes. Useful in CI.                                      |
| `-i`, `--in-place` | off      | Modify files in place instead of writing to stdout.                                                                               |
| `--no-sql`         | off      | Skip SQL reformatting via sqlglot. Only normalizes metacommand indentation and keyword casing.                                    |
| `--indent N`       | `4`      | Spaces per indent level. Controls both metacommand block depth and SQL indentation (columns, subqueries, etc).                    |
| `--leading-comma`  | off      | Place commas at the start of lines instead of the end (e.g. `  , col2` instead of `col1,`).                                       |
| `--encoding NAME`  | `utf-8`  | Text encoding used to read and write SQL files. Pass `cp1252`, `latin-1`, `shift_jis`, etc. for files saved by non-UTF-8 editors. |

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

SQL statements between metacommands are re-indented to match the current block depth and reformatted using [sqlglot](https://sqlglot.com/) in PostgreSQL dialect with pretty-printing enabled.

The `--indent` flag controls SQL indentation in addition to metacommand depth. For example, `--indent 4` (the default) produces 4-space indented column lists, subqueries, and CASE branches. `--indent 2` gives a more compact style.

#### Comment handling

Comments interleaved within SQL statements (e.g. `--` comments between SELECT columns, or inside CASE expressions) are preserved through formatting using a marker-based round-trip:

1. Each comment line is replaced with a unique inline marker attached to the next SQL line.
1. sqlglot formats the complete statement (no fragmentation).
1. Markers are restored to their original `--` comment style and position.
1. Comments that sqlglot's AST drops (e.g. inside CASE WHEN) are detected and re-inserted at the best matching position.

Block comments (`/* */`) that contain `-- !x!` metacommand markers (e.g. commented-out code blocks) are recognized and passed through without metacommand processing.

#### Variable preservation

execsql substitution variables (`!!varname!!`, `!{varname}!`) are replaced with valid SQL identifiers before formatting, then restored afterward, so the formatter does not corrupt them — including in schema-qualified names (`!!staging!!.!!table!!`), CASE expressions, JOIN conditions, and string concatenation.

#### String literal preservation { #string_literals }

Formatting never changes what a string literal contains. Four mechanisms enforce this:

- PostgreSQL escape strings (`E'...'`) are held out of the sqlglot round trip entirely and restored byte-for-byte, keeping both their backslash escapes and their `E` prefix. This matters because sqlglot consumes backslash escapes inside an escape string without re-emitting them, which would turn `E'\\s+'` (a regex matching whitespace) into `e'\s+'` (a regex matching the letter `s`).
- Indentation is never applied inside a multi-line literal — a dollar-quoted body (`$$...$$`, `$tag$...$tag$`) or an ordinary `'...'` string that spans lines. Leading whitespace on a continuation line is part of the stored value, not layout. The line that *opens* the literal is ordinary SQL and is indented with the statement around it, but every line from there to the closing delimiter is emitted exactly as written. Such a literal therefore keeps its original whitespace regardless of `--indent` or how deeply the statement is nested — which means its body will not line up visually with the statement that contains it. That is unavoidable: indenting it would change the string.
- Commas are never moved into or out of a multi-line literal. `--leading-comma`, and the trailing-comma normalization that precedes it, both skip every line such a literal touches, including the line that opens it. A comma inside a multi-line string is data, so repositioning it would change the value rather than the layout.
- Literals that do pass through sqlglot — ordinary single-line `'...'` strings — are compared before and after. If any fails to come back unchanged, the statement is left unformatted rather than rewritten.

The last check is deliberately conservative: a statement may occasionally be left alone when the rewrite would in fact have been harmless (for example, sqlglot normalizes `interval '1 day'` to `INTERVAL '1 DAY'`, which changes the literal's text but not its meaning). Losing formatting on a statement is recoverable; silently changing what a query does is not.

#### Fallback behavior

If sqlglot cannot parse a SQL statement, or if safety checks detect that formatting would corrupt the SQL — statement count changes, significant content loss, or an altered [string literal](#string_literals) — the original text is preserved unchanged.

Use `--no-sql` to skip SQL reformatting entirely and only normalize metacommands.

## Examples { #examples }

```bash
execsql-format myscript.sql                      # Preview to stdout
execsql-format --in-place myscript.sql           # Rewrite in place
execsql-format --in-place scripts/               # Recurse into a directory
execsql-format --check scripts/                  # Exit 1 if any file would change (for CI)
execsql-format --indent 2 --in-place myscript.sql        # Two-space indent
execsql-format --leading-comma --in-place myscript.sql   # Commas at line start
execsql-format --no-sql --in-place myscript.sql          # Only re-indent metacommands; leave SQL alone
```

`--leading-comma` produces output like:

```sql
SELECT
    a
    , b
    , c
FROM t;
```

## Before and After Example { #before-after }

The following script has inconsistent metacommand casing, no indentation inside the `IF` block, and unformatted SQL.

**Before:**

```sql
-- !x! sub schema "public"

-- !x! if(equal(!!schema!!, "public"))
-- !x! write "Checking public schema..."
select id,name,created_at from users where active = true order by name;
-- !x! endif
```

**After (`execsql-format myscript.sql`):**

```sql
-- !x! SUB schema "public"

-- !x! IF(EQUAL(!!schema!!, "public"))
    -- !x! WRITE "Checking public schema..."
    SELECT
        id,
        name,
        created_at
    FROM users
    WHERE
        active = TRUE
    ORDER BY
        name;
-- !x! ENDIF
```

## Pre-commit Hook { #pre-commit }

`execsql-format` can be used as a [pre-commit](https://pre-commit.com/) hook. Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/geocoug/execsql
    rev: v2.22.6
    hooks:
      - id: execsql-format
```

The hook runs on `*.sql` files and rewrites them in place by default (`args: [--in-place]` is baked into the published hook). To run in CI-style check-only mode that fails without modifying files, override with `args: [--check]`. To combine in-place rewriting with a custom indent width, use `args: [--in-place, --indent, "2"]` — note that any explicit `args:` you supply replaces the default, so include `--in-place` when adding more flags if you still want in-place behavior. Run `pre-commit autoupdate` periodically to bump the `rev`.

## Exit Codes { #exit-codes }

| Code | Meaning                                                                                                           |
| ---- | ----------------------------------------------------------------------------------------------------------------- |
| `0`  | Success. All files formatted (or already up to date in `--check` mode).                                           |
| `1`  | One or more files would be reformatted (`--check` mode), a file could not be read, or no `.sql` files were found. |
