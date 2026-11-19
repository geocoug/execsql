# Try execsql inspect

Run these commands from a repository checkout. Use `execsql` in place of
`uv run execsql` if you installed the command separately.

## Create the example data

```sh
uv run python templates/inspect/make_demo.py /tmp/execsql-inspect-demo
export EXECSQL_DEMO_DIR=/tmp/execsql-inspect-demo
export EXECSQL_DEMO_DSN="sqlite:///$EXECSQL_DEMO_DIR/inspection.sqlite"
```

The directory must be new; the generator never overwrites existing files.
It contains six synthetic water samples, three stations, CSV/TSV/JSON/JSONL
files and a ready-to-use SQLite database. No server or credentials are needed.
The database has `stations` and `samples` tables with primary/foreign keys,
a nonnegative-result check, a Boolean default, and a `detected_samples` view.
The sample rows include dates, numbers, Boolean values, NULLs and quoted commas.

For Excel (two sheets), typed Parquet/Feather files and a DuckDB database
with a `lab` schema, generate a different directory with the optional extras:

```sh
uv run --extra formats --extra duckdb python templates/inspect/make_demo.py /tmp/execsql-inspect-extended --extended
```

## 1. Database: identity and namespaces

```sh
uv run execsql inspect database --dsn "$EXECSQL_DEMO_DSN"
uv run execsql inspect database --dsn "$EXECSQL_DEMO_DSN" --output-format json
uv run execsql inspect database --dsn "$EXECSQL_DEMO_DSN" --show-settings --show-config
```

SQLite's namespace is `main`. The database summary counts objects; it does not
show their columns or keys. `--connection-string` is an alias for `--dsn` on
all three database commands.

## 2. Schema: tables and views

```sh
uv run execsql inspect schema main --dsn "$EXECSQL_DEMO_DSN"
uv run execsql inspect schema main --dsn "$EXECSQL_DEMO_DSN" --output-format json
uv run execsql inspect schema main --dsn "$EXECSQL_DEMO_DSN" --show-settings --show-config
```

For the extended DuckDB example, `lab` is an application schema:

```sh
uv run execsql inspect database --dsn duckdb:////tmp/execsql-inspect-extended/inspection.duckdb
uv run execsql inspect schema lab --dsn duckdb:////tmp/execsql-inspect-extended/inspection.duckdb
```

## 3. Table: columns, keys, relationships and SQL

```sh
uv run execsql inspect table samples --schema main --dsn "$EXECSQL_DEMO_DSN"
uv run execsql inspect table samples --schema main --dsn "$EXECSQL_DEMO_DSN" --output-format json
uv run execsql inspect table samples --schema main --dsn "$EXECSQL_DEMO_DSN" --show-settings --show-config
uv run execsql inspect table samples --schema main --dsn "$EXECSQL_DEMO_DSN" --output-format sql
uv run execsql inspect table detected_samples --schema main --dsn "$EXECSQL_DEMO_DSN" --output-format sql
```

Look for the `sample_id` primary key, the `station_id` foreign key and nullable
`result_mg_l`/`notes` columns. SQL is the source database's CREATE definition;
it does not translate SQLite definitions into PostgreSQL. A view or foreign-key
definition can reference other objects: those dependencies are not scripted.

## 4. File: inferred types and destination SQL

```sh
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.csv"
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.tsv"
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.json"
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.jsonl"
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.csv" --output-format json
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.csv" --sample-rows 3
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.csv" --show-settings --show-config
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.csv" --output-format sql --dialect postgres --schema staging --table-name samples
uv run execsql inspect file "$EXECSQL_DEMO_DIR/samples.csv" --output-format sql --dialect sqlite --table-name samples
```

File SQL requires both `--dialect` and `--table-name` and a full scan.
`--schema` is the destination namespace here. Inferred NOT NULL and type/length
limits describe the observed file; no primary or foreign keys are invented.
Neither SQL-output command executes its generated SQL. To save it, redirect
stdout to a new `.sql` filename. Do not combine SQL output with sample or
settings/config display flags.

Inspect the extended formats and choose a workbook sheet explicitly:

```sh
uv run execsql inspect file /tmp/execsql-inspect-extended/samples.xlsx
uv run execsql inspect file /tmp/execsql-inspect-extended/samples.xlsx --sheet Samples
uv run execsql inspect file /tmp/execsql-inspect-extended/samples.xlsx --sheet Stations --output-format json
uv run execsql inspect file /tmp/execsql-inspect-extended/samples.xlsx --sheet Samples --output-format sql --dialect postgres --table-name samples
uv run execsql inspect file /tmp/execsql-inspect-extended/samples.parquet
uv run execsql inspect file /tmp/execsql-inspect-extended/samples.feather
```

## Use an existing PostgreSQL connection

Replace the URL's user, host and database with your own values. Omit the password
to use configured keyring lookup or terminal prompting in text mode:

```sh
export EXECSQL_DEMO_PG_DSN=postgresql://analyst@localhost/project
uv run execsql inspect database --dsn "$EXECSQL_DEMO_PG_DSN"
uv run execsql inspect schema public --dsn "$EXECSQL_DEMO_PG_DSN"
uv run execsql inspect table samples --schema public --dsn "$EXECSQL_DEMO_PG_DSN"
uv run execsql inspect table samples --schema public --dsn "$EXECSQL_DEMO_PG_DSN" --output-format sql --prompt-password
```

Use the table's actual name and schema. JSON/SQL output does not prompt
automatically; `--prompt-password` allows it when stdin is a terminal.
