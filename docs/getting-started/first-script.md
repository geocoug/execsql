# Your first script

Create a small CSV → SQLite → CSV workflow. It needs no server, account, GUI or optional driver. Use a new directory so the example's output files are easy to find.

## Install

```sh
uv tool install execsql2
execsql --version
```

`pipx install execsql2` is an alternative. The package is **execsql2**; the command is **execsql**.

## Create the input

Save this as `sales.csv`:

```csv
product,quantity
book,2
book,3
pen,4
```

Save this as `sales.sql` in the same directory:

```sql
-- Keep product codes as text and require integer quantities.
create table sales (product text, quantity integer);
-- !x! IMPORT TO sales FROM sales.csv
-- !x! ASSERT ROW_COUNT_EQ(sales, 3) "Expected three input rows"

create temporary view totals as
select product, sum(quantity) as quantity
from sales group by product order by product;
-- !x! EXPORT totals TO totals.csv AS CSV
-- !x! WRITE "Created totals.csv"
```

`-- !x!` introduces a metacommand. The SQL creates a target with explicit types; IMPORT converts each value according to those columns. A fractional quantity is an error rather than being rounded into an integer.

## Check and run

Run these commands from the directory containing both files:

```sh
execsql lint sales.sql
execsql run -tl -n sales.sql sales.sqlite
```

`-tl` selects SQLite; `-n` permits creating `sales.sqlite`. The run imports three rows and prints `Created totals.csv`. It creates `sales.sqlite`, `totals.csv` and `execsql.log`. The CSV contains:

```csv
product,quantity
book,5
pen,4
```

This recipe starts with an empty database. Running it again against the same database fails at `CREATE TABLE sales`; it does not silently replace your table. To repeat without keeping a database file, use `execsql run --dsn sqlite:///:memory: sales.sql` instead. EXPORT replaces `totals.csv` on each successful export. IMPORT commits independently under the default autocommit policy; an error later in the script does not undo the loaded rows.

## Add formatting

SQL formatting needs the `formatter` extra:

```sh
uv tool install "execsql2[formatter]"
execsql format --check sales.sql
execsql format --in-place sales.sql
execsql lint sales.sql
```

The first format check may exit 1 because this teaching example is not in the formatter's preferred layout. `--in-place` applies that layout. Installing extras again replaces your previous extra list; retain any others you use.

Continue with the [command reference](../reference/cli/index.md), [safe text arguments](../guides/examples.md#example9), or [editor setup](../guides/editors.md).
