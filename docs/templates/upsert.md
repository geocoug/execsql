# Upsert Scripts { #upsert }

"Upsert" is a colloquial term for the standard SQL [MERGE](<https://en.wikipedia.org/wiki/Merge_(SQL)>) operation. The upsert templates `md_upsert.sql` (MySQL and MariaDB) and `ss_upsert.sql` (SQL Server) QA-check a set of staging tables and then update and insert rows of the matching base tables, using ordinary UPDATE and INSERT statements.

!!! note

    **PostgreSQL has no upsert template.** `pg_upsert.sql` was retired. On PostgreSQL, use the [`PG_UPSERT`](../reference/metacommands.md#pg_upsert) metacommand, which does the same with the pg-upsert package. The rest of this page applies to MySQL, MariaDB and SQL Server only.

"Automated" means the operation is driven by the database's [information schema](https://en.wikipedia.org/wiki/Information_schema). All you do is list the tables to update and say where the base and staging tables are. The scripts provide features that native MERGE or `INSERT ... ON CONFLICT` statements lack:

- They can be applied to any table in any database without modification.
- They can be applied to several tables at once, and upsert them in top-down foreign key order to maintain referential integrity.
- Before upserting, they check each staging table for nulls in columns that must be non-null, for duplicate primary key values, and for foreign key values that match neither the base table nor another staging table.
- They do not upsert any table if any check fails.
- They record either the number of rows that failed each check, or the number of rows updated and inserted, for each table.
- Optionally, they display every change in a GUI dialog and ask you to approve each update and insert.
- Optionally, they write a log file, including the SQL executed and the values added or changed.
- If an execsql console is active, they report progress in its status bar and progress bar.

They do not replicate every feature of a DBMS's own MERGE. They are an alternative that makes QA and loading simple when the upsert can be done with UPDATE and INSERT alone. A separate pair of scripts updates the primary key columns of a table; see [Updating primary keys](#updtpk).

## Setup { #setup }

The scripts are in `md_upsert.sql` and `ss_upsert.sql` in the `templates/` folder of the repository; see the [overview](index.md#using) for how to get and include them. They require [execsql2](../getting-started/installation.md). They are tested on MySQL 8, MariaDB 11 and SQL Server 2022.

## Usage { #usage }

1. Prepare the data in staging tables that have the same structure as the base tables.
1. In a driver script, INCLUDE the upsert file.
1. Optionally define the [logging variables](#logging).
1. Run `STAGED_TO_LOAD` to create the [control table](#control_table).
1. Optionally edit the control table.
1. Run `LOAD_STAGING` to do the QA checks and, if they all pass, the upsert.
1. Check the control table for QA failures or row counts.

You can also create the control table some other way and call only `LOAD_STAGING`, or call the lower-level scripts (`QA_ALL`, `UPSERT_ALL`, `NULLQA_ONE` and so on) yourself if you need extra checks or a different order of operations.

### SQL Server { #usage_ss }

Staging tables have the same names as the base tables but live in a separate schema. The control table **must be a temporary table**: its name must start with `#`. `STAGED_TO_LOAD` runs a `TEMPTABLE_ISVALID` check and halts with an error if the name has no `#` prefix.

```sql
-- !x! include templates/ss_upsert.sql

-- Log to a file.
-- !x! sub logfile     upsert_log.txt
-- !x! sub log_sql     No
-- !x! sub log_errors  Yes
-- !x! sub log_changes No

-- Create the control table (a temporary table: note the '#').
-- !x! execute script staged_to_load with (control_table=#ups_control, table_list="authors, books")

-- Do not open a GUI dialog for each table.
update #ups_control set display_changes = 'No';

-- Run all QA checks and upsert if they all passed.
-- !x! execute script load_staging with (base_schema=dbo, staging=staging, control_table=#ups_control, do_commit=Yes)

-- Halt if any check failed.
select table_name, null_errors, pk_errors, fk_errors
into #ups_errors
from #ups_control
where null_errors is not null or pk_errors is not null or fk_errors is not null;
-- !x! if(hasrows(#ups_errors)) {halt message "Upsert errors:" display #ups_errors}
```

### MySQL and MariaDB { #usage_md }

MySQL and MariaDB have no schemas inside a database, so staging tables are in the same database as the base tables, with a common name prefix (here `stg_`). The scripts read the current database only. The control table must **not** be a temporary table.

```sql
-- !x! include templates/md_upsert.sql

-- !x! sub logfile     upsert_log.txt
-- !x! sub log_errors  Yes

-- !x! execute script staged_to_load with (control_table=ups_control, table_list="authors, books")

-- Do not open a GUI dialog for each table.
update ups_control set display_changes = 'No';

-- Staging tables are stg_authors and stg_books.
-- !x! execute script load_staging with (stage_pfx=stg_, control_table=ups_control, do_commit=Yes)

create view ups_errors as
select table_name, null_errors, pk_errors, fk_errors
from ups_control
where null_errors is not null or pk_errors is not null or fk_errors is not null;
-- !x! if(hasrows(ups_errors)) {halt message "Upsert errors:" display ups_errors}
```

### Unattended runs { #unattended }

!!! warning

    The control table's `display_changes` column defaults to `'Yes'`. `LOAD_STAGING` then opens a GUI dialog for every table, asking you to approve the updates and inserts. For an unattended or scripted run, set it to `'No'` after `STAGED_TO_LOAD`, as the examples above do.

### Script arguments { #arguments }

`STAGED_TO_LOAD (control_table, table_list)`
:   Creates the control table. `table_list` is a comma-separated list of base table names; quote it if it has more than one.

`LOAD_STAGING`
:   SQL Server: `(base_schema, staging, control_table, do_commit)`. MySQL/MariaDB: `(stage_pfx, control_table, do_commit)`.

`base_schema`
:   The schema containing the base tables (SQL Server only).

`staging`
:   The schema containing the staging tables (SQL Server).

`stage_pfx`
:   The name prefix that identifies staging tables (MySQL and MariaDB). The staging table for `books` is `stg_books` if the prefix is `stg_`.

`control_table`
:   The control table made by `STAGED_TO_LOAD`, or by you.

`do_commit`
:   `Yes` or `No`; see [do_commit](#do_commit).

### do_commit { #do_commit }

SQL Server
:   `do_commit=Yes` commits the load. `do_commit=No` rolls the whole load back, so the base tables are unchanged, but the row counts stay in the control table (`rows_updated` and `rows_inserted`), so a dry run reports what would change.

MySQL and MariaDB
:   Only `do_commit=Yes` is accepted. These DBMSs commit at every CREATE and DROP, which the load runs, so a load cannot be rolled back. With `do_commit=No`, `LOAD_STAGING` halts before it changes anything. To check staging tables without loading them, run `QA_ALL` instead:

```sql
-- !x! execute script staged_to_load with (control_table=ups_control, table_list="authors, books")
-- !x! execute script qa_all with (stage_pfx=stg_, control_table=ups_control)
select * from ups_control;
```

## The control table { #control_table }

The control table lists the base tables to upsert, holds per-table settings, and records the results. Its columns are:

`table_name`
:   The base table to update. Filled in by `STAGED_TO_LOAD`.

`exclude_cols`
:   A comma-separated list of single-quoted names of base table columns that must not be updated, such as `'id', 'created_at'`.

`exclude_null_checks`
:   A comma-separated list of single-quoted names of non-null columns for which null checks are skipped. Use it for columns filled by triggers or autonumbering; see [auto-filled columns](#autofill).

`display_changes`
:   `Yes` or `No`: whether `LOAD_STAGING` shows the rows to be added and updated for each table and asks you to continue or cancel. Initialized to `Yes`. Set it to `No` for unattended runs.

`display_final`
:   `Yes` or `No`: whether each whole table is shown after the update and insert, with a prompt to continue or cancel. Initialized to `No`.

`null_errors`
:   Set by the null check. Lists each column that has nulls in the staging table but cannot be null in the base table, with the number of null rows in parentheses.

`pk_errors`
:   Set by the primary key check. The number of primary key values that are duplicated in the staging table, and the number of rows containing duplicates.

`fk_errors`
:   Set by the foreign key check. Lists each foreign key constraint with invalid values, with the number of distinct invalid values in parentheses. The number of rows per invalid value is in the log file and the GUI display, if enabled.

`rows_updated`
:   Set by the upsert. The number of rows that had one or more values updated.

`rows_inserted`
:   Set by the upsert. The number of rows added.

You can edit the control table after `STAGED_TO_LOAD` and before `LOAD_STAGING`:

```sql
update #ups_control
set    exclude_cols = '''id'', ''loaded_at''',
       exclude_null_checks = '''id''',
       display_changes = 'No'
where  table_name = 'books';
```

`LOAD_STAGING` clears the result columns (`null_errors`, `pk_errors`, `fk_errors`, `rows_updated`, `rows_inserted`) at the start of each run, so a control table can be reused.

## Staging tables { #staging }

Prepare the new data in staging tables before running the scripts. With SQL Server, the staging tables have the same names as the base tables, in a separate schema. With MySQL and MariaDB, they have the same names with a common prefix.

A staging table must be consistent with its base table:

- Column names are identical to the base table's.
- Column types are compatible, so no explicit cast is needed on insert or update.
- All primary key columns of the base table are present and populated.
- All columns with a non-null constraint and no default are present.
- All columns with a foreign key into another table are present.

A staging table may have fewer columns than its base table if the missing columns can be null, are not part of a primary key or foreign key, and carry no data to load.

For example, with base tables `authors (id, name)` and `books (id, author_id, title)`:

```sql
create table staging.authors (id integer, name varchar(20));
create table staging.books   (id integer, author_id integer, title varchar(20));
-- MySQL / MariaDB: create table stg_authors ...; create table stg_books ...;
```

## Order of operations { #order }

`LOAD_STAGING` does the following, in order:

1. Checks every staging table for nulls in non-null columns.
1. Checks every staging table for duplicate primary key values.
1. Checks every staging table for valid foreign keys.
1. If there are no violations, upserts all tables in foreign key order.

All checks run on all tables even after a violation, so one run reports every error. When the upsert runs, it is done within a transaction (see [do_commit](#do_commit)). For every row that exists in both tables, all columns that are in both are updated; the scripts do not test whether a value changed. To stop at the first failure instead, call the lower-level scripts yourself.

## Auto-filled columns { #autofill }

Some tables have non-null columns that the DBMS fills in (autonumbering, triggers). Do not populate these from the staging table, and do not check them for nulls. Either:

- leave them out of the staging table and list them in `exclude_null_checks`; or
- include them in the staging table and list them in both `exclude_cols` and `exclude_null_checks`.

If such columns form the primary key (identity columns), the staging table must contain real values for them, because the scripts compare primary keys to decide between update and insert.

## Logging { #logging }

The scripts write a log file when you define these global [substitution variables](../reference/substitution_vars.md) before calling them. If none are defined, nothing is logged.

`logfile`
:   The text file to write status and outcome information to.

`log_sql`
:   `Yes` or `No`: write the SQL (the foreign key checks, UPDATE and INSERT statements) to the log.

`log_errors`
:   `Yes` or `No`: write the data values that violate checks, such as invalid foreign key values.

`log_changes`
:   `Yes` or `No`: write the updated and inserted data to the log.

Logging errors or changes can produce a lot of output and slow the script, but gives the detail needed to fix errors and a permanent record of changes. The values shown for updates are the new data, not the old.

## Scripts reference { #scripts }

The file defines these scripts for direct use. `SHOW SCRIPTS <name>` shows the full notes for each. The signatures below are for SQL Server; on MySQL/MariaDB, drop `base_schema` and `staging` and add `stage_pfx` as the first parameter.

| Script           | Parameters (SQL Server)                                                                           | Purpose                                                                                                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `STAGED_TO_LOAD` | `control_table, table_list`                                                                       | Create and initialize the control table.                                                                                                                                      |
| `LOAD_STAGING`   | `base_schema, staging, control_table, do_commit`                                                  | All QA checks, then the upsert if they pass.                                                                                                                                  |
| `QA_ALL`         | `base_schema, staging, control_table`                                                             | Null, primary key and foreign key checks on every table in the control table.                                                                                                 |
| `UPSERT_ALL`     | `base_schema, staging, control_table`                                                             | Upsert every table in the control table, in foreign key order. Fills `rows_updated` and `rows_inserted`.                                                                      |
| `NULLQA_ONE`     | `base_schema, staging, table, error_list`                                                         | Null check on one table. Takes an optional `exclude_null_checks` argument: single-quoted, comma-separated column names to skip, e.g. `exclude_null_checks="'isbn', 'notes'"`. |
| `PKQA_ONE`       | `base_schema, staging, table, display_errors, error_list`                                         | Duplicate primary key check on one table.                                                                                                                                     |
| `FKQA_ONE`       | `base_schema, staging, table, display_errors, error_list`                                         | Foreign key check on one table, against the base table and any staging table that mirrors it.                                                                                 |
| `UPSERT_ONE`     | `base_schema, staging, table, exclude_cols, display_changes, display_final, updcntvar, inscntvar` | Upsert one table.                                                                                                                                                             |
| `UPDTPK_ONE`     | `base_schema, staging, table, display_errors, display_changes`                                    | Update primary keys of one table.                                                                                                                                             |
| `UPDTPKQA_ONE`   | `base_schema, staging, table, pkinfo_table, qaerror_table, display_errors`                        | QA checks for primary key updates.                                                                                                                                            |

The `_ONE` scripts do not use the control table, so they are useful for checking or loading a single table.

`error_list`
:   The name of a substitution variable that receives a description of the errors found: for `NULLQA_ONE`, the non-null columns that have nulls, each followed by its null row count; for `PKQA_ONE`, the number of duplicated key values and rows; for `FKQA_ONE`, the foreign key names with the number of rows with an invalid value.

`display_errors`
:   `Yes` or `No`: show the offending values in a GUI.

`updcntvar`, `inscntvar`
:   Names of variables set to the numbers of rows updated and inserted.

```sql
-- Null and key checks on one table, then load it without a control table.
-- !x! execute script nullqa_one with (base_schema=dbo, staging=staging, table=books, error_list=null_err)
-- !x! execute script upsert_one with (base_schema=dbo, staging=staging, table=books, exclude_cols="'id'", display_changes=No, display_final=No, updcntvar=n_upd, inscntvar=n_ins)
-- !x! write "Updated !!n_upd!!, inserted !!n_ins!! rows."
```

## Updating primary keys { #updtpk }

`UPDTPK_ONE` updates the primary key values of one base table from a staging table. It is like `UPSERT_ONE` but only updates primary key columns and inserts nothing. There is no multi-table equivalent, because QA for simultaneous key changes with cascading updates is not feasible. `UPDTPKQA_ONE` runs the QA checks and is called by `UPDTPK_ONE`.

The staging table has a different layout from other upsert staging tables. It needs:

- columns identical to the base table's primary key columns (same names and types), holding the current key values; and
- a second set of equivalent columns, each named with a `new_` prefix, holding the new key values.

The staging table needs no primary key of its own. `UPDTPK_ONE` requires that:

- the base table has a primary key;
- the staging table has a `new_` column for every primary key column;
- the staging table has at least one row specifying an update;
- if any `new_` column is filled on a row, all are;
- the current key values exist in the base table;
- none of the new key values exist in the base table;
- no two staging rows give the same new key, and no two rows with the same original key give different new keys; and
- every foreign key from the new key values into other base tables is valid.

```sql
-- staging.books_pk has columns (id, new_id)
-- !x! execute script updtpk_one with (base_schema=dbo, staging=staging, table=books, display_errors=Yes, display_changes=No)
```

## Limitations { #limitations }

- **Quoted identifiers.** Schema, table and column names must not need quoting.
- **Check constraints** are not checked by the scripts.
- **Reserved names.** The scripts create temporary tables and views whose names start with `ups_`. Do not use that prefix in your own objects: a clash can cause data loss if a base table or view uses it. On MySQL and MariaDB these objects are created as permanent objects (those DBMSs have no temporary views, or views on temporary tables) and are dropped when the scripts end normally. If a script ends abnormally, for example on a data type mismatch between base and staging tables, they remain until the next normal completion.
- **Primary key requirements.** Staging tables must contain all primary key columns with real values; the scripts compare primary keys to decide between update and insert. If the base table's key is an autonumber or identity column, assign values in the staging table first.
- **Primary key updates.** An ordinary upsert cannot change primary key values; use [UPDTPK_ONE](#updtpk).
- **Referential cycles.** To order tables parents-first, the scripts break multi-table cycles (A is a parent of B, B of C, C of A). All tables are included, but the order of the checks and the upserts within the cycle is arbitrary, and whether that matters depends on the data.
- **Multiple schemas.** Ordering considers only foreign keys among tables in the base schema. Constraints to tables in other schemas may leave the upserts in the wrong order.
- **Commits.** MySQL and MariaDB cannot roll a load back; see [do_commit](#do_commit).

## Messages { #messages }

### Console messages { #console_messages }

While `LOAD_STAGING` runs it writes progress messages to the terminal or console: each table as its null, primary key and foreign key checks start, the non-null columns that contain nulls, duplicate primary keys, and the tables referenced by invalid foreign keys. For example (SQL Server form):

```text
Conducting non-null QA checks on table staging.sampatt
    Column attribute has 1 nulls.
Conducting primary key QA checks on table staging.sampsplit
    Duplicate key error on columns: study_id, sample_id, sample_no.
Conducting foreign key QA checks on table staging.sampatt
    Foreign key error referencing e_sampatt.
    Foreign key error referencing sample.
```

On MySQL and MariaDB the table is shown as the prefix plus name (for example `stg_sampatt`).

### Prompts { #prompts }

If `display_changes` is `Yes` in the control table, QA failures and the data to update or insert are displayed interactively. Choosing Cancel in a QA failure display halts the whole script, so nothing else is checked, added or modified. Choosing No in an update or insert display skips that operation but the script continues. Skipping can cause the DBMS to report an integrity error when other tables are loaded.

### Log file messages { #logfile_messages }

When `logfile` is defined, the log file records each QA check on each staging table, and details of failures. It has more information than the console, so it is the best resource for finding what to fix in the staging tables. This shows the form of the QA results (the optional SQL is omitted):

```text
==================================================================
2026-03-24 10:01 -- Primary key QA checks on table staging.sampsplit
Checking constraint pk_sampsplit.
Duplicate primary key values in staging.sampsplit
  study_id | sample_id | sample_no | row_count
 ----------|-----------|-----------|-----------
  C        | W004      | W004-DUP  | 2

==================================================================
2026-03-24 10:01 -- Foreign key QA checks on table staging.sampatt
Checking constraint fk_sampattatt for table dbo.sampatt.
 Foreign key errors in sampatt referencing e_sampatt
  attribute | row_count
 -----------|-----------
  colour    | 3
  sheeen    | 1
```

As each base table is upserted, the log records the updates and inserts. With `log_changes` set to `Yes` it includes the values; for updates these are the new values:

```text
==================================================================
2026-03-24 06:03 -- Performing upsert on table dbo.location

Updates:
  location | description
 ----------|---------------
  WC-017   | WC station 17

1 rows of dbo.location updated.

New data:
  location | description
 ----------|---------------
  GC-7451  | Station WT NE

1 rows added to dbo.location.

==================================================================
2026-03-24 06:04 -- CHANGES COMMITTED.
```

If a load is not committed (SQL Server, `do_commit=No`) the log ends with `CHANGES NOT COMMITTED ('do_commit' argument = No)` instead.

## Authors and license { #authors }

The upsert scripts were written by R. Dreas Nielsen and Elizabeth Shea (who wrote the SQL Server version) and revised for execsql2 by Caleb Grant. They are licensed under the GNU General Public License, version 3 or later; each file's header gives the notice and its history. This page is adapted from the original documentation at <https://execsql-upsert.readthedocs.io>.
