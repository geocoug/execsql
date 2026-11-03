# Reports and external commands

[All examples](../examples.md) · [First script](../../getting-started/first-script.md)

## Choose an export format { #example8 }

**Illustrative PostgreSQL/desktop recipe.** Requires `some_data`, the `formats` extra for ODS, and `pandoc` plus a PDF engine for the PDF option. Save as `choose_view.sql` and run against the source database. It replaces selected output files and launches the desktop viewer (`xdg-open` on Linux); adapt viewer commands for your platform.

This example illustrates how the [PROMPT SELECT_SUB](../../reference/metacommands.md#prompt_selsub) metacommand can be used to prompt the user to select among several options. In this example, the options allow the user to choose a format in which to (export and) view a data table or view. For this example, there must be a data table or view in the database named some_data.

```sql
drop table if exists formats;
create temporary table formats ( format varchar(4) );
insert into formats (format)
values ('csv'), ('tsv'), ('ods'), ('html'), ('txt'), ('pdf'), ('GUI');

-- !x! sub data_table some_data
-- !x! prompt select_sub formats message "Choose the output format you want."
-- !x! if(equals("!!@format!!", "GUI"))
-- !x!   prompt message "Selected data." display !!data_table!!
-- !x! else
-- !x!   sub outfile outfile_!!$DATETIME_TAG!!.!!@format!!
-- !x!   if(equals("!!@format!!", "pdf"))
-- !x!     sub txtfile outfile_!!$DATETIME_TAG!!.txt
-- !x!     write "# Data Table" to !!txtfile!!
-- !x!     export !!data_table!! append to !!txtfile!! as txt
-- !x!     system_cmd(pandoc !!txtfile!! -o !!outfile!!)
-- !x!   else
-- !x!     export !!data_table!! to !!outfile!! as !!@format!!
-- !x!   endif
-- !x!   system_cmd(xdg-open !!outfile!!)
-- !x! endif
```

This example also illustrates that, because the text ("txt") output format of the [EXPORT](../../reference/metacommands.md#export) metacommand creates a Markdown-compatible table, this type of text output can be combined with output of [WRITE](../../reference/metacommands.md#write) metacommands and converted to Portable Document Format (PDF). This example also illustrates how the [SYSTEM_CMD](../../reference/metacommands.md#system_cmd) metacommand can be used to immediately open and display a data file that was just exported. (Note that the `xdg-open` command is available in most Linux desktop environments. In Windows, the `start` command is equivalent.)

This example also illustrates how substitution variables can be used to parameterize code to support modularization and code re-use. In this example the substitution variable data_table is assigned a value at the beginning of the script. Alternatively, this variable might be assigned different values at different locations in a main script, and the commands in the remainder of this example placed in a second script that is INCLUDEEd where appropriate to allow the export and display of several different data tables or views. [Example 10](control-flow.md#example10) illustrates this usage.

## Render a MediaWiki table with Jinja { #example22 }

**Runnable SQLite recipe with the `formats` extra.** Install with `uv tool install "execsql2[formats]"` (retain any other extras you use). Save this as `table.wiki.j2`:

```jinja
{| class="wikitable"
|-
{% for name in headers %}! scope="col" | {{ name }}
{% endfor %}{% for row in datatable %}|-
{% for name in headers %}| {{ row[name] }}
{% endfor %}{% endfor %}|}
```

Save as `wiki.sql` in the same directory:

```sql
create table planets (name text, moons integer);
insert into planets values ('Earth', 1), ('Mars', 2);
-- !x! EXPORT planets TO planets.wiki WITH TEMPLATE table.wiki.j2
```

Save this as `wiki.conf`:

```ini
[output]
template_processor = jinja
```

Run `execsql run --config wiki.conf --dsn sqlite:///:memory: wiki.sql`. The file `planets.wiki` is created (replaced on another run):

```text
{| class="wikitable"
|-
! scope="col" | name
! scope="col" | moons
|-
| Earth
| 1
|-
| Mars
| 2
|}
```

`headers` holds the column names; `datatable` contains row dictionaries. This template is for simple text/numeric cells. Escape MediaWiki markup separately when rendering arbitrary data; the template does not sanitize that format.

## Create a report glossary { #example26 }

The [glossary guide](../../templates/glossary.md) shows how to create a glossary of the columns used in a report, using a master glossary table and a list of source tables. It includes the PostgreSQL, MySQL/MariaDB and SQL Server call forms, prerequisites and output objects.

Download the matching `pg_glossary.sql`, `md_glossary.sql` or `ss_glossary.sql` separately from the repository; these libraries do not arrive with the Python package.

## Run a Windows crosstab batch file { #example29 }

Although *execsql* is designed so that it can be used as part of a toolchain that is controlled by a shell script (on Linux) or a batch file (on Windows), this approach can also be inverted: execsql can create and run a system script, for example to pre- or post-process data.

**Illustrative Windows fragment.** Install `xtab.py` separately and supply the omitted SQL that creates/populates `tt_allresults`. Save as `crosstab.sql`; run against your source database. The script writes and deletes a batch file and intermediate CSV/error files; it creates `output.csv`.

In this example, execsql creates and runs a Windows batch file that crosstabs data, producing output with multi-row column headers. Any errors that occur during the crosstabbing operation are imported by execsql and displayed to the user. The crosstabbing operation is carried out by [xtab.py](http://pypi.org/project/xtab/); the *xtab* command used here corresponds to Example 2 in the *xtab* documentation.

```sql
-- Create a temporary table that contains all desired results.
create temporary table tt_allresults ( ...

insert into tt_allresults ....

-- Create and run a batch file to crosstab the results
-- !x! rm_file xtab_all.bat
-- !x! write "@echo off" to xtab_all.bat
-- !x! export tt_allresults to allresults.csv as csv
-- !x! write "if exist xtab_errors.txt del xtab_errors.txt" to xtab_all.bat
-- !x! write "if exist xtab_errs.txt del xtab_errs.txt" to xtab_all.bat
-- !x! write "xtab.py -d3 -i allresults.csv -o output.csv -r location_id sample_date -c analyte units meas_basis -v value quals -e xtab_errs.txt" to xtab_all.bat
-- !x! write "del allresults.csv" to xtab_all.bat
-- !x! write "if exist xtab_errs.txt (" to xtab_all.bat
-- !x! write "echo errors>xtab_errors.txt" to xtab_all.bat
-- !x! write "type xtab_errs.txt >>xtab_errors.txt" to xtab_all.bat
-- !x! write "del xtab_errs.txt" to xtab_all.bat
-- !x! write ")" to xtab_all.bat
-- !x! system_cmd (xtab_all.bat)
-- !x! rm_file xtab_all.bat
-- !x! if(file_exists(xtab_errors.txt))
    -- !x! import to replacement staging.errorlist from xtab_errors.txt with quote none delimiter us
    -- !x! prompt message "Errors occurred while crostabbing results:" display staging.errorlist
    -- !x! rm_file xtab_errs.txt
    -- !x! rm_file xtab_errors.txt
    drop table staging.errorlist;
-- !x! endif
```

Any error message produced by *xtab.py* is written to a text file, but that file does not have a column name on the first line, as required by the [IMPORT](../../reference/metacommands.md#import) metacommand, so following steps append the error message to another text file that contains a column name. An alternate approach would be to use the IMPORT_FILE metacommand to import the error message file just as it was created by *xtab.py*.

## Number output from serial runs { #example33 }

**Illustrative recipe for serial runs only.** Save as `number_output.sql` and run against a database connection. It rewrites `DB_run.conf` and creates output directories/files. Concurrent runs can choose the same number; use a database sequence or another allocator when runs overlap.

Unique numbering of script output is useful when a script is to be run repeatedly, when it will produce different output each time, and when all of the output files are to be retained.

This example illustrates one way in which this can be done. The features of this process are:

- All output is created in subdirectories of a "parent" output directory. In this example, the parent output directory is named "DB_output", which is created under the current directory.
- Each output-specific subdirectory has a name of the form "Run_nnn_yyyymmdd" where "nnn" is the run number, and "yyyymmdd" is the date of the run.
- The user may be prompted for a run description, based on a setting in the script. If a run description is provided it is saved as a text file in the output directory. All run numbers and run descriptions are also saved in a CSV file in the current directory named "DB_run_descriptions.csv".
- A substitution variable named "output_dir" is created that should be used in file/path names for output of the [EXPORT](../../reference/metacommands.md#export) and [WRITE](../../reference/metacommands.md#write) metacommands.

```sql
-- !x! CONFIG MAKE_EXPORT_DIRS Yes

-- The "output_dir" variable will be set to a run-specific directory name
-- that is dynamically created and is different for each run of this
-- script. The run-specific output directories will be created underneath
-- a parent directory. The path to that parent directory is specified
-- here. By default, the parent directory is named "DB_output" and is
-- under the current directory.
-- !x! SUB output_parent DB_output

-- Create a unique number for every run, with corresponding output
-- directories and optionally a narrative description.
-- !x! SUB do_run_numbering True
-- Prompt for a run description?
-- !x! SUB get_run_description True

-- Set up the run number and optionally get a run description and
-- save it. A run number is always assigned, but it is used for the
-- output directory only if the 'do_run_numbering' option is True.
-- !x! IF(FILE_EXISTS(DB_run.conf))
    -- !x! SUB_INI FILE DB_run.conf SECTION run
-- !x! ENDIF
-- !x! IF(NOT SUB_DEFINED(run_no))
    -- !x! SUB run_no 0
-- !x! ENDIF
-- !x! SUB_ADD run_no 1

-- Rewrite the config file with the new run number.
-- !x! RM_FILE DB_run.conf
-- !x! WRITE "# Automatically-generated database run number setting. Do not edit." TO DB_run.conf
-- !x! WRITE "[run]" TO DB_run.conf
-- !x! WRITE "run_no=!!run_no!!" TO DB_run.conf

-- Zero-pad the run number to 3 digits for the directory name.
-- !x! SUB run_tag !!run_no!!
-- !x! IF(NOT IS_GT(!!run_no!!, 9))
    -- !x! SUB run_tag 0!!run_tag!!
-- !x! ENDIF
-- !x! IF(NOT IS_GT(!!run_no!!, 99))
    -- !x! SUB run_tag 0!!run_tag!!
-- !x! ENDIF

-- Build the output directory path.
-- !x! IF(!!do_run_numbering!!)
    -- !x! SUB output_dir !!output_parent!!!!$pathsep!!Run_!!run_tag!!_!!$date_tag!!
    -- !x! IF(!!get_run_description!!)
        -- !x! PROMPT ENTER_SUB run_description MESSAGE "Please enter a description for this run (!!run_tag!!)."
        -- !x! IF(NOT SUB_EMPTY(run_description))
            -- !x! WRITE "!!run_description!!" TO !!output_dir!!!!$pathsep!!run_description.txt
            -- !x! EXPORT QUERY <<select !!run_no!! as "Run_no", !'!run_description!'! as "Description";>> APPEND TO DB_run_descriptions.csv AS CSV
        -- !x! ENDIF
    -- !x! ENDIF
-- !x! ELSE
    -- Use just a date-tagged directory name for "output_dir".
    -- !x! SUB output_dir !!output_parent!!!!$pathsep!!!!$date_tag!!
-- !x! ENDIF
```

The "output_dir" variable that is created by this script can be used in the following way:

```sql
-- !x! EXPORT summary_query TO !!output_dir!!!!$pathsep!!output_file.csv AS CSV
```

This example is also incorporated into the SQL script template [separately downloaded script template](../../templates/index.md#other). The script template also uses the run number for custom logfiles.

## Export data files and a ZIP bundle { #example41 }

**Illustrative export recipe.** Supply `product_sales` and install `formats` for Parquet/XLSX. Save as `export_sales.sql` and run against that database. It replaces the named JSON, Parquet, XLSX and ZIP files; later ZIP members use APPEND.

The [EXPORT](../../reference/metacommands.md#export) metacommand supports modern interchange formats alongside the classic delimited ones, and can write files directly into a ZIP archive. One query's results can be published in several forms:

```sql
-- Machine-readable formats.
-- !x! EXPORT product_sales TO sales.json AS JSON
-- !x! EXPORT product_sales TO sales.parquet AS PARQUET

-- A spreadsheet for people, built from a query instead of a table.
-- !x! EXPORT QUERY << select product, sum(amount) as total_sales from product_sales group by product; >> TO summary.xlsx AS XLSX

-- Bundle several files into one ZIP archive. The first EXPORT creates
-- the archive; subsequent members need APPEND, otherwise the archive
-- is overwritten and only the last file survives.
-- !x! EXPORT product_sales TO sales.csv IN ZIPFILE report_bundle.zip AS CSV
-- !x! EXPORT QUERY << select * from product_sales order by amount desc; >> APPEND TO ranked.csv IN ZIPFILE report_bundle.zip AS CSV
```

Notes:

- Parquet, Feather and XLSX exports require the `formats` extra (`pip install "execsql2[formats]"`), which provides Polars.
- When writing into a ZIP archive, the `TO` name is the *member* name inside the archive and `IN ZIPFILE` names the archive itself.
- `APPEND` means "add a member to the archive" in the ZIP form; without a ZIP archive it means "append rows to the file". Formats that cannot be streamed (Feather, DuckDB) cannot be written into a ZIP archive.
- The full format list and per-format behavior are documented under [EXPORT](../../reference/metacommands.md#export).

## Run foreground and background helpers { #example43 }

**Illustrative OS-process recipe.** Supply the Python helper files named below and a Python executable on PATH. Save as `run_helpers.sql` and use a disposable working directory. Foreground commands wait; background helpers can outlive the execsql run. No helper code is supplied here.

The [SYSTEM_CMD](../../reference/metacommands.md#system_cmd) metacommand runs an operating-system command from a script. It has a foreground form that waits and records the exit code, and a background form (`CONTINUE`) that launches the command and moves on immediately.

```sql
-- Foreground: the script waits, and the exit code is stored in
-- $SYSTEM_CMD_EXIT_STATUS. A nonzero exit code is not an error by
-- itself — scripts branch on it explicitly.
-- !x! SYSTEM_CMD (python3 fetch_latest.py)
-- !x! IF(IS_GT(!!$SYSTEM_CMD_EXIT_STATUS!!, 0))
    -- !x! WRITE "fetch_latest.py failed with exit status !!$SYSTEM_CMD_EXIT_STATUS!!"
    -- !x! HALT
-- !x! ENDIF

-- Background: CONTINUE launches the command and stores its process id
-- in $SYSTEM_CMD_PID. The script does not wait, and the process may
-- outlive the script.
-- !x! SYSTEM_CMD (python3 rebuild_search_index.py) CONTINUE
-- !x! WRITE "Index rebuild running as PID !!$SYSTEM_CMD_PID!!"
```

Foreground commands can be given a time limit with the `system_cmd_timeout` configuration option (seconds; default 0 = no limit), set in `execsql.conf`:

```ini
[config]
system_cmd_timeout=300
```

When the limit is exceeded, execsql stops the command, sets `$SYSTEM_CMD_EXIT_STATUS` to `124`, and raises a metacommand error (which halts the script unless [METACOMMAND_ERROR_HALT](../../reference/metacommands.md#metacommanderrorhalt) is `OFF`). Background (`CONTINUE`) commands are not affected by the timeout. For locked-down environments, the `--no-system-cmd` CLI flag (or `allow_system_cmd=No` in the config) disables the metacommand entirely.
