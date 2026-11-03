# Data movement and validation

[All examples](../examples.md) · [First script](../../getting-started/first-script.md)

## Validate before committing { #validate-before-commit }

**Runnable SQLite failure example.** Save as `validate_batch.sql` and run `execsql run -tl -n validate_batch.sql validation.sqlite` in a fresh directory. It creates an empty `validated` table, then tries to add an invalid row inside a batch:

```sql
create table validated (quantity integer);
create temporary view invalid_rows as select * from validated where quantity < 0;
-- !x! BEGIN BATCH
insert into validated values (-1);
-- !x! ASSERT NOT HASROWS(invalid_rows) "Quantity must not be negative"
-- !x! END BATCH
```

The assertion sees the uncommitted insert on the same connection and halts with status 1. The batch is rolled back; `validated` exists with zero rows. Change `-1` to `2` and use a fresh database (or the in-memory DSN) for a successful commit. This example holds ordinary SQL. Independently committing operations such as IMPORT/COPY are outside that promise; see [batch limits](../../reference/metacommands.md#batch).

## Write QA failures to a report { #example3 }

**Illustrative PostgreSQL recipe.** Supply the three `stage_*` tables and matching `e_*` dictionaries. Save as `qa_results.sql` and run against that database. It creates temporary views and appends failures to a dated text file. Input data are deliberately external.

This example illustrates a script that creates several temporary queries to check the codes that are used in a set of staging tables against the appropriate dictionary tables, and, if there are unrecognized codes, writes them out to a text file.

```sql
create temporary view qa_pty1 as
select distinct stage_party.party_type
from   stage_party
       left join e_partytype
         on stage_party.party_type=e_partytype.party_type
where  e_partytype.party_type is null;

-- !x! if(hasrows(qa_pty1))
-- !x!   write "Unrecognized party types:" to Staging_QA_!!$DATE_TAG!!.txt
-- !x!   export qa_pty1 append to Staging_QA_!!$DATE_TAG!!.txt as tab
-- !x! endif

create temporary view qa_prop1 as
select distinct stage_property.property_type
from   stage_property
       left join e_propertytype
         on stage_property.property_type=e_propertytype.property_type
where  e_propertytype.property_type is null;

-- !x! if(hasrows(qa_prop1))
-- !x!   write "Unrecognized property types:" to Staging_QA_!!$DATE_TAG!!.txt
-- !x!   export qa_prop1 append to Staging_QA_!!$DATE_TAG!!.txt as tab
-- !x! endif

create temporary view qa_partyprop1 as
select distinct stage_partyprop.property_rel
from   stage_partyprop
       left join e_partyproprel
         on stage_partyprop.property_rel=e_partyproprel.property_rel
where  e_partyproprel.property_rel is null;

-- !x! if(hasrows(qa_partyprop1))
-- !x!   write "Unrecognized party-property relationship types:" to Staging_QA_!!$DATE_TAG!!.txt
-- !x!   export qa_partyprop1 append to Staging_QA_!!$DATE_TAG!!.txt as tab
-- !x! endif
```

## Review QA failures in a dialog { #example4 }

**Illustrative PostgreSQL/GUI recipe.** Requires the staging and dictionary tables used below. Save as `qa_prompt.sql` and run against that database with `execsql run -tp qa_prompt.sql SERVER DATABASE`. It creates a temporary result table and displays only failures; Cancel stops the run with the default `CANCEL_HALT ON`.

This example illustrates a script that compiles the results of several QA queries into a single temporary table, then displays the temporary table if it has any rows (i.e., any errors were found), and prompts the user to cancel or continue the script.

```sql
create temporary table qa_results (
  table_name varchar(64) not null,
  column_name varchar(64) not null,
  severity varchar(20) not null,
  data_value varchar(255) not null,
  description varchar(255) not null,
  time_check_run timestamp not null
  );

insert into qa_results
  (table_name, column_name, severity, data_value, description, time_check_run)
select distinct
       'stage_party',
       'party_type',
       'Fatal',
       stage_party.party_type,
       'Unrecognized party type',
       current_timestamp
from   stage_party
       left join e_partytype
         on stage_party.party_type=e_partytype.party_type
where  e_partytype.party_type is null;

insert into qa_results
  (table_name, column_name, severity, data_value, description, time_check_run)
select distinct
      'stage_property',
      'property_type',
      'Fatal',
      stage_property.property_type,
      'Unrecognized property type',
      current_timestamp
from  stage_property
      left join e_propertytype
        on stage_property.property_type=e_propertytype.property_type
where e_propertytype.property_type is null;

insert into qa_results
  (table_name, column_name, severity, data_value, description, time_check_run)
select distinct
      'stage_partyprop',
      'property_rel',
      'Fatal',
      stage_partyprop.property_rel,
      'Unrecognized property relationship type',
      current_timestamp
from  stage_partyprop
      left join e_partyproprel
        on stage_partyprop.property_rel=e_partyproprel.property_rel
where  e_partyproprel.property_rel is null;

-- !x! if(hasrows(qa_results))
-- !x!     prompt message "QA failures; Cancel to stop loading." display qa_results
-- !x! endif
```

## Edit an inferred table definition { #example12 }

**Illustrative PostgreSQL/editor recipe.** Requires `storm_tracks.csv`, the `staging` schema and `vim` on PATH. Save as `edit_structure.sql` and run against that database. It opens an editor, creates `staging.storm_data`, and loads its rows; that target should not already exist.

This example illustrates how the structure of a table that would be created by the [IMPORT](../../reference/metacommands.md#import) metacommand can be customized during the import process. Customization may be necessary because the data types that are automatically selected for the columns of the new table need to be modified. This may occur when:

> - A column is entirely null. In this case, execsql will create the column with a text data type, whereas a different data type may be more appropriate.
> - A column contains only integers of 1 and 0; execsql will create this column with a Boolean data type, whereas an integer type may be more appropriate.
> - A column contains only integers, whereas a floating-point type may be more appropriate.

The technique shown here first writes the CREATE TABLE statement to a temporary file, and then opens that file in an editor so that you can make changes. After the file is edited and closed, the file is [INCLUDEEd](../../reference/metacommands.md#include) to create the table structure, and then the data are loaded into that table.

```sql
-- !x! sub input_file storm_tracks.csv
-- !x! sub target staging.storm_data

-- !x! sub_tempfile tmpedit
-- !x! write create_table !!target!! from !!input_file!! comment "Modify the structure as needed." to !!tmpedit!!
-- !x! system_cmd(vim !!tmpedit!!)
-- !x! include !!tmpedit!!
-- !x! import to !!target!! from !!input_file!!
```

Changes to data types that are incompatible with the data to be loaded will result in an error during the import process. Changes to column names will also prevent the data from being imported.

Although this example shows this process applied to only a single file/table, multiple CREATE TABLE statements can be written into a single file and edited all at once.

This example illustrates the use of a temporary file for the CREATE TABLE statement, although you may wish to save the edited form of this statement in a permanent file to keep a record of all data-handling operations.

## Import a directory of CSV files { #example13 }

**Illustrative PostgreSQL/Linux recipe.** Requires the `staging` schema, CSV files with usable table names, a directory prompt and a POSIX shell. Save both blocks together, with the named-script definition before its call. It replaces `staging.csvlist` and one staging table per CSV. The shell command assumes simple paths without shell metacharacters; use a controlled directory.

When a group of related data files are to be loaded together into a database, they can all be loaded automatically with this script if they are first placed in the same directory. This example script operates by:

> - Prompting for the directory containing the CSV files to load.
> - Creating a text file with the names of all of the CSV files in that directory.
> - Importing the text file into a database table.
> - Adding columns to that table for the name of the table into which each CSV file is imported and the time of import. The main file name of each CSV file is used as the table name.
> - Looping over the list of CSV files, choosing one that does not have an import time, importing that file, and setting the import time.

Define `import_csv` before its invocation. Save both blocks, in this order, as `import_directory.sql`:

```sql
-- !x! begin script import_csv
    -- !x! select_sub unloaded
    -- !x! write "    !!@tablename!!"
    -- !x! import to replacement staging.!!@tablename!! from !!@csvfile!!
    update staging.csvlist
    set import_date = current_timestamp
    where tablename = !'!@tablename!'!;
-- !x! end script import_csv
```

Then add the main processing block:

```sql
-- !x! prompt directory sub dir
-- !x! sub_tempfile csvlist
-- Create the complete manifest synchronously in one foreground process.
-- !x! system_cmd(sh -c 'printf "csvfile\n" > "!!csvlist!!"; ls "!!dir!!"/*.csv >> "!!csvlist!!"')
-- !x! import to replacement staging.csvlist from !!csvlist!!

alter table staging.csvlist
    add tablename character varying(64),
    add import_date timestamp with time zone;

update staging.csvlist
set tablename = replace(substring(csvfile from E'[^/]+\.csv$'), '.csv', '');

create temporary view unloaded as
select * from staging.csvlist
where import_date is null
limit 1;

-- !x! write "Importing CSV files from !!dir!!"
-- !x! execute script import_csv while (hasrows(unloaded))
```

Run against PostgreSQL with `execsql run -tp import_directory.sql SERVER DATABASE`. The foreground shell command writes both the manifest header and filenames; it does not depend on a background WRITE finishing before an external append. This recipe assumes a controlled directory and filenames that do not need CSV escaping.

## Expand PostGIS points into columns { #example19 }

*Example contributed by E. Shea.*

**Illustrative PostgreSQL/PostGIS recipe.** Save the two named files together and supply `sample_points` as described below. Run `expand_geom.sql` against that database. It replaces `tt_samp_loc_points` and creates temporary output with one longitude/latitude pair per point. Coordinates retain the source SRID: they are geographic longitude/latitude only when that SRID uses those units. No coordinate transformation is performed.

This example illustrates automatic (scripted) revisions to a table structure, wherein a number of additional columns are added to a table; the number of columns added is determined by the data. The case illustrated here is of a Postgres table containing a PostGIS multipoint geometry column. The purpose of this script is to extract the coordinate points from the geometry column and store each point as a pair of columns containing latitude and longitude values. The number of points in the multipoint column varies from row to row, and the maximum number of points across all rows is not known (and need not be known) when this script is run.

This example assumes the existence of a database table named `sample_points` that contains the following two columns:

> - `sample`: a text value uniquely identifying each row.
> - `locations`: a multi-point PostGIS geometry value.

This operation is carried out using two scripts, named `expand_geom.sql` and `expand_geom2.sql`. The first of these calls the second. A loop and an explicit point index create and fill as many additional columns as are needed to contain all the point coordinates.

`expand_geom.sql` :

```sql
create temporary view vw_pointcount as
select coalesce(max(ST_NumGeometries(locations)), 0) as point_len
from sample_points;

--!x! subdata point_len vw_pointcount

drop table if exists tt_samp_loc_points;
create temporary table tt_samp_loc_points (
    sample text,
    locations geometry,
    location_srid integer,
    point_count integer
    );

insert into tt_samp_loc_points
    (sample, locations, location_srid, point_count)
select
    sample, locations, ST_SRID(locations), ST_NumGeometries(locations)
from sample_points;

--!x! include expand_geom2.sql
```

`expand_geom2.sql` :

```sql
-- !x! SUB point_number 1
-- !x! LOOP WHILE (NOT IS_GT(!!point_number!!, !!point_len!!))

alter table tt_samp_loc_points
    add column point_!!point_number!!_longitude double precision,
    add column point_!!point_number!!_latitude double precision;

update tt_samp_loc_points
set
    point_!!point_number!!_longitude = ST_X(ST_GeometryN(locations, !!point_number!!)),
    point_!!point_number!!_latitude = ST_Y(ST_GeometryN(locations, !!point_number!!))
where
    point_count>=!!point_number!!;

-- !x! SUB_ADD point_number 1
-- !x! END LOOP
```

## Log data-quality issues { #example20 }

**Illustrative issue-logging library.** Supply the input CSV and QA views in the calling block below. Save `log_issue.sql` separately and include it at each reporting site. It creates/updates a persistent SQLite issue log and can copy issue-detail tables; it is not a read-only check.

This example illustrates how data quality issues that are encountered during data loading or cleaning operations can be logged for later evaluation and resolution. Issues are logged in a SQLite database in the working directory. This database is named issue_log.sqlite and is automatically created if necessary. The database contains one table named issue_log in which all issues are recorded. The issue log database may also contain additional tables that provide data to illustrate the issues. Each of these additional tables has a name that starts with "issue\_", followed by an automatically-assigned issue number.

The script that logs the issues is named `log_issue.sql`. It should be included in the main script at every point where an issue is to be logged. Three substitution variables are used to pass information to this script:

> - `dataset`: The name of the data set to which this issue applies.
> - `issue`: A description of the issue.
> - `issue_data`: The name of a table or view containing a data summary that illustrates the issue. This substitution variable need not be defined if no illustrative data are necessary or applicable (use the [RM_SUB](../../reference/metacommands.md#rm_sub) metacommand to un-define this variable if it has been previously used).

Each issue is logged only once. The issue_log table is created with additional columns that may be used to record the resolution of each issue, and these are not overwritten if an issue is encountered repeatedly.

The `log_issue.sql` script uses several substitution variables with names that start with "iss\_", and uses counter variable 15503. Other parts of the loading and cleaning scripts should avoid collisions with these values.

`log_issue.sql` :

```sql
-- ------------------------------------------------------------------
-- Save the current alias to allow switching back from the SQLite issue log.
-- ------------------------------------------------------------------
-- !x! sub iss_calleralias !!$CURRENT_ALIAS!!

-- ------------------------------------------------------------------
-- Connect to the issue log.  Create it if it doesn't exist.
-- ------------------------------------------------------------------
-- !x! if(alias_defined(iss_log))
-- !x!  use iss_log
-- !x! else
-- !x!  if(file_exists(issue_log.sqlite))
-- !x!      connect to sqlite(file=issue_log.sqlite) as iss_log
-- !x!      use iss_log
        create temporary view if not exists iss_no_max as
        select max(issue_no) from issue_log;
-- !x!      subdata iss_max iss_no_max
-- !x!      set counter 15503 to !!iss_max!!
-- !x!  else
-- !x!      connect to sqlite(file=issue_log.sqlite, new) as iss_log
-- !x!      use iss_log
        create table issue_log (
            issue_no integer,
            data_set text,
            issue_summary text,
            issue_details text,
            resolution_strategy text,
            resolution_reviewer text,
            reviewer_comments text,
            final_resolution text,
            resolution_implemented date,
            resolution_script text
            );
-- !x!  endif
-- !x! endif

-- ------------------------------------------------------------------
-- Add the new issue if it does not already exist.
-- ------------------------------------------------------------------
drop view if exists check_issue;
create temporary view check_issue as
    select issue_no
    from issue_log
    where data_set=!'!dataset!'!
        and issue_summary=!'!issue!'!;

-- !x! if(not hasrows(check_issue))
-- !x!  sub iss_no !!$counter_15503!!
    insert into issue_log
        (issue_no, data_set, issue_summary)
    values (
        !!iss_no!!,
        !'!dataset!'!,
        !'!issue!'!
        );
-- !x! else
-- !x!  subdata iss_no check_issue
-- !x! endif

-- ------------------------------------------------------------------
-- Save the issue data if there is any and it has not already
-- been saved.
-- ------------------------------------------------------------------
-- !x! if(sub_defined(issue_data))
-- !x!  sub iss_table issue_!!iss_no!!
-- !x!  if(not table_exists(!!iss_table!!))
-- !x!      copy !!issue_data!! from !!iss_calleralias!! to replacement !!iss_table!! in iss_log
-- !x!  endif
-- !x! endif

-- ------------------------------------------------------------------
-- Restore the caller alias
-- ------------------------------------------------------------------
-- !x! use !!iss_calleralias!!
```

This script would be used during a data loading or cleaning process as illustrated in the following code snippet.

```sql
-- ------------------------------------------------------------------
-- Define the data set both for import and for issue logging.
-- ------------------------------------------------------------------
-- !x! sub dataset data_set_524.csv
-- !x! write "Importing data."
-- !x! import to replacement data524 from !!dataset!!

-- ------------------------------------------------------------------
--  Check for multiple stations per sample.
-- ------------------------------------------------------------------
-- !x! write "Checking for multiple stations per sample."
create temporary view samploc as
    select distinct loc_name, sample_name
    from data524;

create temporary view dupsamplocs as
    select sample_name
    from samploc
    group by sample_name
    having count(*) > 1;

create or replace temporary view allsampdups as
    select samploc.sample_name, loc_name
    from samploc
        inner join dupsamplocs as d on d.sample_name=samploc.sample_name
    order by samploc.sample_name;

-- !x! if(hasrows(dupsamplocs))
-- !x!  sub issue Multiple locations for a sample.
-- !x!  sub issue_data allsampdups
-- !x!  include log_issue.sql
-- !x! endif
```

## Apply updates across connections { #example21 }

**Illustrative PostgreSQL fragment.** Supply three disposable databases, the real server/user and the update statements at the marked placeholder. This script changes persistent data. Save as `update_databases.sql` and run with a PostgreSQL initial connection. The initial connection holds the control table; three additional connections hold the updates.

Updates are staged with `AUTOCOMMIT OFF`, but commits happen **one database at a time**. This is not an atomic distributed transaction. If a later commit fails, earlier commits remain stored; recovery must reconcile those databases. `BEGIN BATCH` does not provide distributed atomicity either. Set error halting explicitly so update failures do not proceed to the commit phase, and plan rollback/recovery for every still-open connection.

```sql
-- =========================================================
--      Setup
-- Put database names in a table so that we can loop through
-- the list and process the databases one by one.
-- ---------------------------------------------------------
create temporary table dblist (
    database text,
    db_alias text,
    updated boolean default false
    );

insert into dblist
    (database)
values
    ('db1'), ('db2'), ('db3');

update dblist
set db_alias = 'conn_' || database;

create temporary view unupdated as
select *
from dblist
where not updated
limit 1;
-- =========================================================


-- =========================================================
--        Script: Update a single database
-- Data variables @database and @db_alias should be defined.
-- ---------------------------------------------------------
-- !x! BEGIN SCRIPT update_database
-- !x! connect to postgresql(server=myserver, db=!!@database!!, user=!!$db_user!!, need_pwd=True) as !!@db_alias!!
-- !x! use !!@db_alias!!

-- Begin a transaction
begin;

-- Replace this comment with the SQL updates for one database.

-- !x! use initial
-- !x! END SCRIPT
-- =========================================================


-- =========================================================
--        Script: Update all databases
-- ---------------------------------------------------------
-- !x! BEGIN SCRIPT update_all_dbs
-- !x! select_sub unupdated
-- !x! if(sub_defined(@database))
    -- !x! write "Updating !!@database!!"
    -- !x! execute script update_database
    update dblist set updated=True where database=!'!@database!'!;
    -- !x! execute script update_all_dbs
-- !x! endif
-- !x! END SCRIPT
-- =========================================================


-- =========================================================
--        Script: Commit changes to all databases
-- ---------------------------------------------------------
-- !x! BEGIN SCRIPT commit_all_dbs
-- !x! select_sub unupdated
-- !x! if(sub_defined(@db_alias))
    -- !x! write "Committing changes to !!@database!!"
    -- !x! use !!@db_alias!!
    commit;
    -- !x! use initial
    update dblist set updated=True where database=!'!@database!'!;
    -- !x! execute script commit_all_dbs
-- !x! endif
-- !x! END SCRIPT
-- =========================================================


-- =========================================================
--        Update all databases
-- ---------------------------------------------------------
-- !x! ERROR_HALT ON
-- !x! METACOMMAND_ERROR_HALT ON
-- !x! autocommit off
-- !x! execute script update_all_dbs

-- If there was an error during updating of any database,
-- the error should halt execsql, and the following code
-- will not run.
update dblist set updated=False;
-- !x! execute script commit_all_dbs
-- =========================================================
```

## Choose an upsert implementation { #example25 }

Use [PG_UPSERT](../../reference/metacommands.md#pg_upsert) with the `upsert` extra for PostgreSQL. There is no current `pg_upsert.sql` download; the metacommand replaced that template.

For MySQL/MariaDB and SQL Server, download `md_upsert.sql` or `ss_upsert.sql` from the repository, then follow the [upsert guide](../../templates/upsert.md) for arguments, QA checks and limitations. Template files are separate downloads; installing `execsql2` does not install them. These operations update persistent tables, so start with disposable staging/base tables.

## Order tables by foreign-key dependencies { #example28 }

**External historical example.** This section points to a third-party article rather than a self-contained recipe. Review the linked script, dialect and prerequisites before running it; it was not executed as part of this documentation verification.

An execsql script to convert a table of parent:child dependencies into a list of tables ordered by dependency is posted at [Splinter of the Singularity](http://splinterofthesingularity.blogspot.com/2017/12/ordering-database-tables-by-foreign-key.html).

## Compare staging and base tables { #example31 }

Use the [comparison guide](../../templates/compare.md) for fixtures, four comparison methods and DBMS-specific call forms. Download `pg_compare.sql`, `md_compare.sql` or `ss_compare.sql` from the repository; the Python package does not install these files. The guide distinguishes generating comparison SQL from executing it and describes the temporary/persistent objects involved.

## Import multiple worksheets { #example34 }

**Illustrative spreadsheet recipe.** Install `formats`, supply `lookups.ods`, and create `stg` on a DBMS with schemas such as PostgreSQL. Save as `load_lookups.sql`. It replaces matching staging tables and opens a display for each; workbook data are not supplied here.

This example illustrates commands to import multiple sheets from a workbook into staging tables. This uses the [IMPORT](../../reference/metacommands.md#import) metacommand and the system variables that are created when the SHEETS MATCHING clause is used. Each imported staging table is then displayed.

This example illustrates import of a set of lookup tables from an OpenDocument workbook named "lookups.ods", where each lookup table is on a sheet with a name starting with "l\_", and the sheet names match table names. The sheets are imported into tables in a staging schema named "stg" (on a DBMS with schemas, such as PostgreSQL or DuckDB). SHEETS MATCHING takes a regular expression, so `^l_` selects the sheets whose names start with "l\_".

`$SHEETS_TABLES_VALUES` holds the new tables' names ready for an `INSERT ... VALUES` statement, here `('stg.l_units'),('stg.l_methods')` in workbook order. Loading them into a table gives the script a list to work through: a script displays the first table in the list and removes it, and runs again while any remain.

```sql
-- !x! IMPORT TO REPLACEMENT TABLES IN stg FROM lookups.ods SHEETS MATCHING ^l_

-- The tables just created, one row each, and the first one not yet shown.
create table imported (table_name varchar(100));
insert into imported (table_name) values !!$SHEETS_TABLES_VALUES!!;
create view next_table as select table_name from imported order by table_name limit 1;

-- Display each imported table, removing it from the list once shown.
-- !x! BEGIN SCRIPT show_next
-- !x! SELECT_SUB next_table
-- !x! EXPORT !!@table_name!! TO stdout AS TXT
delete from imported where table_name = !'!@table_name!'!;
-- !x! END SCRIPT
-- !x! EXECUTE SCRIPT show_next WHILE (HAS_ROWS(imported))
```

## Validate a staging load { #example35 }

**Illustrative PostgreSQL loading fragment.** Supply the dated CSV, `staging`/`production` schemas, compatible `production.customers`, and an `environment` variable. It replaces staging and inserts production rows. The row count read back from staging is not an independent reconciliation of the source; use an externally expected count for that check.

The [ASSERT](../../reference/metacommands.md#assert) metacommand evaluates a condition and halts the script with an error if the condition is false. It accepts any condition that `IF` accepts, and takes an optional quoted failure message. Use it to encode data quality contracts directly in the script so violations surface as explicit errors rather than silent bad data.

This example loads a staging table from a CSV file and then verifies structural and content assumptions before proceeding with the load.

```sql
-- Load staging data.
-- !x! SUB source_file data/customers_!!$DATE_TAG!!.csv
-- !x! IMPORT TO REPLACEMENT staging.customers FROM !!source_file!!

-- Verify the staging table was created successfully.
-- !x! ASSERT TABLE_EXISTS(staging.customers) "Customer staging table was not created"

-- Count the rows loaded and store in a substitution variable.
create temporary view vw_count as
    select count(*) as n from staging.customers;
-- !x! SUBDATA row_count vw_count

-- Require at least one row.
-- !x! ASSERT ROW_COUNT_EQ(staging.customers, !!row_count!!) "Row count mismatch after import"
-- !x! ASSERT IS_GT(!!row_count!!, 0) "Source file !!source_file!! contains no rows"

-- Verify a required configuration variable was set before calling this script.
-- !x! ASSERT EQUALS(!!environment!!, production) "Variable 'environment' must be set to 'production'"

-- If all assertions pass, proceed with the production load.
-- !x! WRITE "All assertions passed. Loading !!row_count!! rows."
insert into production.customers
    select * from staging.customers;
```

ASSERT uses the same condition engine as [IF](../../reference/metacommands.md#if_cmd), so any condition available for IF — `TABLE_EXISTS`, `HASROWS`, `ROW_COUNT_EQ`, `EQUALS`, `IS_GT`, `FILE_EXISTS`, and all others — is valid. When a condition fails, the failure message is reported in the error output and the script halts with exit code 1.

## Copy data between databases { #example40 }

**Illustrative cross-database recipe.** Requires an initial database containing `product_sales(product, amount)`. Save as `copy_sales.sql` and run with that initial connection. It creates a separate SQLite deliverable and copies/summarizes rows. Use a fresh destination path; source data are not supplied here.

The [COPY](../../reference/metacommands.md#copy) metacommand moves data directly between two open database connections — including connections to *different* DBMSs. A common pattern is publishing a self-contained SQLite deliverable from a production PostgreSQL warehouse: connect to both, then copy whole tables or query results.

```sql
-- Open a second connection to a brand-new SQLite file. The startup
-- connection (here, PostgreSQL) always has the alias "initial".
-- !x! CONNECT TO SQLITE(FILE=deliverable.sqlite, NEW) AS deliverable

-- Copy an entire table.
-- !x! COPY product_sales FROM initial TO NEW product_sales IN deliverable

-- Copy the result of a query. REPLACEMENT drops and re-creates the
-- target table if it already exists; NEW errors if it exists.
-- (Each metacommand must be written on a single line.)
-- !x! COPY QUERY << select product, sum(amount) as total_sales from product_sales group by product; >> FROM initial TO REPLACEMENT sales_summary IN deliverable

-- Verify the copy on the target connection, then switch back.
-- !x! USE deliverable
-- !x! IF(HASROWS(sales_summary))
    -- !x! WRITE "sales_summary delivered to deliverable.sqlite"
-- !x! ENDIF
-- !x! USE initial
```

The table structure is created automatically on the target, with column types translated between the two DBMSs' type systems. Because `COPY` reads from one live connection and writes to another, no intermediate export file is needed. To copy into a *server* database instead, open the second connection with the corresponding [CONNECT](../../reference/metacommands.md#connect) form (e.g. `CONNECT TO POSTGRESQL(...) AS ...`).
