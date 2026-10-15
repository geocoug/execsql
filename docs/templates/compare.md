# Compare Scripts { #compare }

The compare templates generate SQL SELECT statements that compare the data in a staging table with the corresponding base table. They are meant to show what an upsert of the staging table would change, before you do it. The scripts read the primary key and attribute (non-key) columns of the base table from the `information_schema` views, so they work on any table without modification.

| DBMS            | File             |
| --------------- | ---------------- |
| PostgreSQL      | `pg_compare.sql` |
| MySQL / MariaDB | `md_compare.sql` |
| SQL Server      | `ss_compare.sql` |

Get the file from the `templates/` folder of the repository; see the [overview](index.md#using). The scripts are tested on PostgreSQL, MySQL 8, MariaDB 11 and SQL Server 2022 and require [execsql2](../getting-started/installation.md).

## Usage { #usage }

1. Create and populate a staging table that has all the primary key columns, and at least one attribute column, of the base table.
1. INCLUDE the compare file for your DBMS.
1. Call the comparison scripts you want with EXECUTE SCRIPT, passing the required arguments and, optionally, `include_cols` or `exclude_cols`.
1. Use the SQL stored in the variable you named in `sql_var` to summarize the data as you like.

The generated SQL has no terminating semicolon, so you can use it as a subquery or in a `CREATE VIEW`. If you capture it in a local (`~`) substitution variable, define the variable first and pass its name with a `+` prefix: `sql_var=+changed_sql`.

The scripts create temporary tables and views whose names start with `cmp_`. Do not use that prefix in objects of your own; a clash can lose data. MySQL and MariaDB have no temporary views, so the "temporary" objects are permanent until the script ends normally; if it ends abnormally, for example on a data type mismatch between base and staging tables, they stay until the next normal completion.

## Scripts { #scripts }

`COMPARE_COMMON`
:   Includes the primary key values present in **both** tables. Each attribute column is tagged `Same`, `Different`, `Old` (a value in the base table, null in staging) or `New` (null in the base table, a value in staging).

`COMPARE_COMMON_VALS`
:   Includes the primary key values present in both tables. For each attribute, two columns show the base value and the staging value, named with the suffixes `_old` and `_new`. The primary key columns are shown once.

`COMPARE_CHANGES`
:   Includes every primary key in the **staging** table, with a column named `changes`: `NewRow` (not in the base table), `Changed` (at least one attribute differs) or `Unchanged`.

`COMPARE_CHANGED`
:   Includes every primary key in the **base** table, with a column named `changed`: `NoNewRow` (not in the staging table), `Changed` or `Unchanged`.

Rows with a key in only one table are left out of `COMPARE_COMMON` and `COMPARE_COMMON_VALS`.

## Arguments { #arguments }

All four scripts take the same arguments. The call differs by DBMS because MySQL and MariaDB have no schemas inside a database.

PostgreSQL and SQL Server: `(base_schema, staging, table, sql_var, include_cols="", exclude_cols="")`

MySQL and MariaDB: `(stage_pfx, table, sql_var, include_cols="", exclude_cols="")`

`base_schema`
:   The schema of the base table (PostgreSQL, SQL Server).

`staging`
:   The schema of the staging table (PostgreSQL, SQL Server). The table name is the same in both schemas.

`stage_pfx`
:   The prefix of staging table names (MySQL, MariaDB). If the base table is `person` and the staging table `stg_person`, the prefix is `stg_`.

`table`
:   The name of the base table.

`sql_var`
:   The name of the substitution variable that receives the generated SQL.

`include_cols`
:   Optional, default empty. A comma-separated list of single-quoted attribute column names; **only** these are compared. For example `include_cols="'price', 'category'"`.

`exclude_cols`
:   Optional, default empty. A comma-separated list of single-quoted attribute column names to leave out of the comparison, for example `exclude_cols="'updated_at', 'updated_by'"`. If both are given, `include_cols` wins and `exclude_cols` is ignored.

## Example { #example }

This compares a base `books` table with a staging copy. First, the tables:

```sql
create table public.books (
    title text not null,
    category text not null,
    price numeric(8,2) not null,
    constraint pk_books primary key (title)
);
create table staging.books (like public.books including all);

insert into public.books values
    ('Dune', 'Fiction', 9.99),
    ('Emma', 'Fiction', 4.50),
    ('Cosmos', 'Science', 12.00);

insert into staging.books values
    ('Dune', 'Fiction', 10.99),
    ('Emma', 'Fiction', 4.50),
    ('Silent Spring', 'Science', 11.00);
```

Then compare them (PostgreSQL form). Each script is called, the generated SQL is wrapped in a view, and the view is shown in a dialog:

```sql
-- !x! include templates/pg_compare.sql

-- COMPARE_COMMON: Same/Different tags for keys in both tables
-- !x! execute script compare_common with (base_schema=public, staging=staging, table=books, sql_var=cmn_sql)
create or replace temporary view cmn as !!cmn_sql!!;
-- !x! prompt message "COMPARE_COMMON" display cmn

-- COMPARE_COMMON_VALS: old and new values side by side
-- !x! execute script compare_common_vals with (base_schema=public, staging=staging, table=books, sql_var=vals_sql)
create or replace temporary view vals as !!vals_sql!!;
-- !x! prompt message "COMPARE_COMMON_VALS" display vals

-- COMPARE_CHANGES: every staging row is NewRow, Changed or Unchanged
-- !x! execute script compare_changes with (base_schema=public, staging=staging, table=books, sql_var=changes_sql)
create or replace temporary view changes as !!changes_sql!!;
-- !x! prompt message "COMPARE_CHANGES" display changes

-- COMPARE_CHANGED: every base row, using a local variable for the SQL
-- !x! sub_empty ~changed_sql
-- !x! execute script compare_changed with (base_schema=public, staging=staging, table=books, sql_var=+changed_sql)
create or replace temporary view changed as !!~changed_sql!!;
-- !x! prompt message "COMPARE_CHANGED" display changed
```

With these data, `COMPARE_CHANGES` reports Dune as `Changed` (the price differs), Emma as `Unchanged` and Silent Spring as `NewRow`. `COMPARE_CHANGED` reports Cosmos as `NoNewRow`.

The same comparison with an attribute left out, on MySQL or MariaDB, where staging tables are `stg_books`:

```sql
-- !x! include templates/md_compare.sql
-- !x! execute script compare_changes with (stage_pfx=stg_, table=books, sql_var=changes_sql, exclude_cols="'category'")
create or replace view books_changes as !!changes_sql!!;
-- !x! prompt message "Changes" display books_changes
```

On SQL Server, use the PostgreSQL call form with `ss_compare.sql`, and create a temporary table (`select * into #changes from (!!changes_sql!!) as t`) or a view in place of the PostgreSQL temporary view.

## Comparison rules { #rules }

- A value that is null in one table and not in the other counts as a difference; two nulls count as the same.
- On MySQL, MariaDB and SQL Server, text values are compared **case- and accent-sensitively**, so a value that changes only in letter case (`y` to `Y`) is reported as a change. Primary keys are matched using the database's own comparison rules.
- PostgreSQL compares text exactly as the column collation does.
- `md_compare.sql` reads columns from the current database only.

## Limitations { #limitations }

- The staging table must have all the base table's primary key columns, populated, and the base table must have a primary key; otherwise the script halts with a "has no primary key columns" message.
- Table and column names must not need quoting.
- Use the case the DBMS stores for names, because the scripts look them up in `information_schema`.

## Authors and license { #authors }

The compare scripts were written by R. Dreas Nielsen and revised for execsql2 by Caleb Grant. They are licensed under the GNU General Public License, version 3 or later; each script's history is in its file header. This page is adapted from the original documentation at <https://execsql-compare.readthedocs.io>.
