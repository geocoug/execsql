# Glossary Scripts { #glossary }

The glossary templates build a custom glossary to accompany a data summary: a list of terms, such as column names, and their definitions. Terms come from a master glossary table or are given directly.

| DBMS            | File              |
| --------------- | ----------------- |
| PostgreSQL      | `pg_glossary.sql` |
| MySQL / MariaDB | `md_glossary.sql` |
| SQL Server      | `ss_glossary.sql` |

Get the file from the `templates/` folder of the repository; see the [overview](index.md#using). The scripts are tested on PostgreSQL, MySQL 8, MariaDB 11 and SQL Server 2022 and require [execsql2](../getting-started/installation.md).

You can add terms to the custom glossary in three ways:

- all columns of a table or view, by naming it;
- a specific term and definition;
- a list of terms that are in the master glossary.

The custom glossary has one definition per term, even if a term is requested several ways (for example, by adding two tables that share a column). Once a term is in the glossary, later requests for it have no effect. The scripts create a view named `glossary` that returns the custom glossary sorted by term.

## Master glossary table { #master }

The master glossary table has a column for the term (for example, a column name), a column for its definition, and optionally a column with a URL for more information. It may be in a different database from the one you are summarizing, but the two must be the same DBMS type. For example:

```sql
create table master_glossary (
    term varchar(40) primary key,
    definition varchar(200),
    url varchar(200)
);
insert into master_glossary (term, definition) values
    ('site_id', 'Site identifier'),
    ('sample_date', 'Date the sample was collected'),
    ('result', 'Measured value');
```

## Usage { #usage }

1. If the master glossary is in another database, connect to it with CONNECT and an alias. If it is in the current database, use the alias `initial`.
1. Call `INIT_GLOSSARY` to describe the master glossary.
1. Call `ADD_GLOSSARY_TABLE`, `ADD_GLOSSARY_ITEM` and `ADD_GLOSSARY_LIST` to fill the custom glossary.
1. Use the `glossary` view to display or export the result.

```sql
-- !x! include templates/pg_glossary.sql

-- Connect to the master glossary database.
-- !x! connect to postgresql(server=dbhost, db=reference, user=analyst, need_pwd=True) as refdb

-- Describe the master glossary.
-- !x! execute script init_glossary with (glossary_db_alias=refdb, glossary_table=master_glossary, name_col=term, def_col=definition)

-- A data summary.
create temporary view samples_summary as
select 'Round 1' as event, site_id, sample_date, result
from   samples;

-- Add definitions for its columns that are in the master glossary.
-- The schema is empty because this is a temporary view.
-- !x! execute script add_glossary_table with (schema='', table='samples_summary')

-- Add a term that is not in the master glossary.
-- !x! execute script add_glossary_item with (item=event, definition="Sampling event")

-- Export the data summary and then the glossary.
-- !x! export samples_summary to summary.ods as ods
-- !x! export glossary append to summary.ods as ods
```

Columns of the view that the master glossary does not define (here `event`) are not added by `ADD_GLOSSARY_TABLE`; add them with `ADD_GLOSSARY_ITEM`, as the example does.

## Scripts and arguments { #scripts }

### INIT_GLOSSARY { #init_glossary }

`INIT_GLOSSARY (glossary_db_alias, glossary_table, name_col, def_col, def_url="")`

Identifies the master glossary table, creates the custom glossary table and the `glossary` view, and defines the substitution variables the other scripts use. Call it first.

`glossary_db_alias`
:   The alias, set with CONNECT, of the database containing the master glossary table.

`glossary_table`
:   The name of the master glossary table.

`name_col`
:   The column of the master glossary table that holds the term.

`def_col`
:   The column that holds the definition.

`def_url`
:   Optional. The column that holds a URL for more information. When given, the custom glossary and the `glossary` view carry that column too.

### ADD_GLOSSARY_TABLE { #add_glossary_table }

Adds the master-glossary definitions of the columns of a table or view. Columns the master glossary does not define are skipped.

PostgreSQL and SQL Server: `ADD_GLOSSARY_TABLE (schema, table)`

MySQL and MariaDB: `ADD_GLOSSARY_TABLE (table)`

`schema`
:   The schema of the table or view. For a temporary table or view, give an empty string (`schema=''`).

`table`
:   The table or view name. On MySQL and MariaDB the schema argument does not exist because a schema is a database, and the table must be a permanent table or view: those DBMSs do not list the columns of temporary objects in `information_schema`.

```sql
-- PostgreSQL and SQL Server
-- !x! execute script add_glossary_table with (schema=public, table=samples)

-- MySQL and MariaDB
-- !x! execute script add_glossary_table with (table=samples)
```

### ADD_GLOSSARY_ITEM { #add_glossary_item }

`ADD_GLOSSARY_ITEM (item, definition, def_url="")`

Adds one term and definition, for a term that is not in the master glossary or that needs a custom definition. `def_url` is optional and is kept in the glossary's URL column if you initialized it with one.

```sql
-- !x! execute script add_glossary_item with (item=lab, definition="Laboratory name", def_url="https://example.org/labs")
```

### ADD_GLOSSARY_LIST { #add_glossary_list }

`ADD_GLOSSARY_LIST (column_list)`

Adds the master-glossary definitions of the terms in a comma-delimited string. Terms the master glossary does not have are not added.

```sql
-- !x! execute script add_glossary_list with (column_list="site_id, sample_date")
```

## Customizing entries { #customizing }

To give a term a custom definition even though the master glossary has one, call `ADD_GLOSSARY_ITEM` for it **before** `ADD_GLOSSARY_TABLE` or `ADD_GLOSSARY_LIST`; the later request is ignored.

You can also insert rows with ordinary SQL. The custom glossary table is named `gls_glossary`, is created in the database of the initial connection, and has the same columns as the master glossary table plus a primary key on the term, so a term cannot have two definitions.

## Side effects { #side_effects }

The scripts create two objects in the database of the initial connection:

- a table `gls_glossary` with the custom glossary; and
- a view `glossary` that returns it.

On PostgreSQL both are temporary. On MySQL, MariaDB and SQL Server they are permanent and are not removed when the scripts finish. While running, the scripts also create temporary tables and views in the initial and master glossary databases, and several global substitution variables. Everything uses the prefix `gls_`, except the `glossary` view.

## Limitations { #limitations }

- Do not use the `gls_` prefix for your own variables, tables or views.
- Table and column names for the master and custom glossary tables must not need quoting.
- Use the case the DBMS stores for names, because the scripts look them up in `information_schema`.
- The connection to the master glossary database must be allowed to create tables and views, regular and temporary, there. The master glossary table itself needs only SELECT.
- On MySQL and MariaDB, `ADD_GLOSSARY_TABLE` cannot add columns from a temporary table or view.

## Authors and license { #authors }

The glossary scripts were written by R. Dreas Nielsen (with Elizabeth Shea for the SQL Server version) and revised for execsql2 by Caleb Grant. They are licensed under the GNU General Public License, version 3 or later; each script's history is in its file header. This page is adapted from the original documentation at <https://execsql-glossary.readthedocs.io>.
