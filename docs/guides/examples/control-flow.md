# Control flow and reusable scripts

[All examples](../examples.md) · [First script](../../getting-started/first-script.md)

## Repeat a task with LOOP { #example6 }

**Runnable without a server or GUI.** Save as `repeat.sql`:

```sql
-- !x! SUB iteration 1
-- !x! LOOP WHILE (NOT IS_GT(!!iteration!!, 3))
    -- !x! WRITE "Iteration !!iteration!!"
    -- !x! SUB_ADD iteration 1
-- !x! END LOOP
```

Run `execsql run --dsn sqlite:///:memory: repeat.sql`. Output:

```text
Iteration 1
Iteration 2
Iteration 3
```

For a reusable task, define it once with [BEGIN SCRIPT](../../reference/metacommands.md#beginscript), then call it using [EXECUTE SCRIPT](../../reference/metacommands.md#executescript) inside the loop. An `INCLUDE` may load those definitions once. A file cannot repeatedly `INCLUDE` itself: active include cycles are rejected. Named-script calls and file inclusion are different operations.

## End a selection loop with Cancel { #example10 }

**Illustrative PostgreSQL/GUI recipe.** Requires views in `public`, the three files named below, and the desktop export tools used by [the format chooser](reports.md#example8). Save the files together; run `execsql run -tp view_views.sql SERVER DATABASE`. It exports files chosen by the user.

This example illustrates the use of the [CANCEL_HALT](../../reference/metacommands.md#cancel_halt) metacommand during user interaction with dialogs. Ordinarily when a user presses the "Cancel" button on a dialog, execsql treats this as an indication that a necessary response was not received, and that further script processing could have adverse consequences---and therefore execsql halts script processing. However, there are certain cases when the "Cancel" button is appropriately used to terminate a user interaction without stopping script processing.

The scripts in this example presents the user with a list of all views in the database, allows the user to select one, and then prompts the user to choose how to see the data. Three scripts are used:

> - `view_views.sql`: This is the initial script that starts the process. It turns the [CANCEL_HALT](../../reference/metacommands.md#cancel_halt) flag off at the start of the process, and turns it back on again at the end.
> - `view_views2.sql`: This script is included once by view_views.sql and contains an inner loop, repeatedly presenting the user with a list of all the views in the database. The "Cancel" button on this dialog is used to terminate the overall process. If the user selects a view, rather than canceling the process, then the choose_view.sql script is [INCLUDEEd](../../reference/metacommands.md#include) to allow the user to choose how to see the data.
> - `choose_view.sql`: This script presents the dialog that allows the user to choose how to see the data from the selected view. This is the same script used in [Example 8](reports.md#example8), except that the data_table variable is defined in the `view_views2.sql` script instead of in `choose_view.sql`.

`view_views.sql` :

```sql
create temporary view all_views as
select table_schema || '.' || table_name as table_name
from information_schema.views
where table_schema = 'public';

-- !x! cancel_halt off
-- !x! include view_views2.sql
-- !x! cancel_halt on
```

`view_views2.sql` :

```sql
-- !x! LOOP WHILE (TRUE)
-- !x! prompt select_sub all_views message "Select the item you would like to view or export; Cancel to quit."
-- !x! if(sub_defined(@table_name))
-- !x!    sub data_table !!@table_name!!
-- !x!    include choose_view.sql
-- !x! else
-- !x!    BREAK
-- !x! endif
-- !x! END LOOP
```

The `choose_view.sql` script can be seen in [Example 8](reports.md#example8).

The CONTINUE keyword of the [PROMPT SELECT_SUB](../../reference/metacommands.md#prompt_selsub) metacommand can also be used to close the dialog without canceling the script.

## Number report sections with counters { #example11 }

**Illustrative PostgreSQL reporting fragment.** Requires `qa_results`, each `qa_tbl_N`, and an `outfile` variable. Save the shown body as `number_sections.sql` and call/include it for the QA checks to report. It appends Markdown text/tables; the surrounding iteration and source data are external.

This example illustrates how counter variables can be used to automatically number items. This example shows automatic numbering of components of a Markdown document, but the technique can also be used to number database objects such as tables and views.

This example creates a report of the results of a set of QA checks, where the information about the checks is contained in a table with the following columns:

> - `check_number`: An integer that uniquely identifies each QA check that is conducted.
> - `test_description`: A narrative description of the scope or operation of the check.
> - `comment_text`: A narrative description of the results of the check.

The results of each check are also represented by tabular output that is saved in a table named qa_tbl_x where x is the check number.

```sql
-- !x! sub section !!$counter_1!!
-- !x! sub check_no !!$counter_3!!
-- !x! write "# Section !!section!!. QA Check !!check_no!!" to !!outfile!!
-- !x! reset counter 2
-- !x! write "## Subsection !!section!!.!!$counter_2!!. Test" to !!outfile!!
create or replace temporary view descript as
select test_description from qa_results where check_number = !!check_no!!;
-- !x! export descript append to !!outfile!! as plain
-- !x! write "## Subsection !!section!!.!!$counter_2!!. Results" to !!outfile!!
create or replace temporary view comment as
select comment_text from qa_results where check_number = !!check_no!!;
-- !x! export comment append to !!outfile!! as plain
-- !x! write "Table !!check_no!!." to !!outfile!!
-- !x! write "" to !!outfile!!
-- !x! export qa_tbl_!!check_no!! append to !!outfile!! as txt-and
-- !x! write "" to !!outfile!!
```

A script like this one could be [INCLUDEEd](../../reference/metacommands.md#include) as many times as there are sets of QA results to report.

This example also illustrates how the value of a counter variable can be preserved for repeated use by assigning it to a user-defined substitution variable.

## Run a trusted script from a database { #example14 }

**Illustrative PostgreSQL recipe for trusted script libraries.** Requires the `scriptlib` table described below, containing scripts you have reviewed. Save as `run_library.sql`. It writes a temporary SQL file and executes its contents with your privileges; the library data are not supplied here.

Despite the advantages of storing scripts on the file system, in some cases storing a set of scripts in a library database may be appropriate. Consider a table named scriptlib that is used to store SQL scripts, and that has the following columns:

> - `script_name`: A name used as a unique identifier for each script; the primary key of the table.
> - `script_group`: A name used to associate related scripts.
> - `group_master`: A Boolean used to flag the first script in a group that is to be executed.
> - `script_text`: The text of the SQL script.

A single script from such a library database can be run using another script like the following:

```sql
-- !x! sub_tempfile scriptfile
create temporary view to_run as
select script_text from scriptlib
where script_name = 'check_sdg';
-- !x! export to_run to !!scriptfile!! as plain
-- !x! include !!scriptfile!!
```

This technique could be combined with a prompt for the script to run, using the method illustrated in [Example 8](reports.md#example8), to create a tool that allows interactive selection and execution of SQL scripts.

This technique can be extended to export all scripts with the same script_group value, and then to run the master script for that group. To use this approach, the filename used with the [IMPORT](../../reference/metacommands.md#import) metacommand in each script must be a substitution variable that is to be replaced with the name of a temporary file created with the [SUB_TEMPFILE](../../reference/metacommands.md#sub_tempfile) metacommand.

## Collect several dialog selections { #example15 }

**Illustrative PostgreSQL/GUI recipe.** Requires `e_sampmaterial(sample_material, description)` and `d_sampmain(sample_material, ...)`. Save as `choose_materials.sql` and run against that database. It creates only temporary selection objects and displays matching samples.

Instead of building a quoted `IN` list, store each choice in a temporary table. `Cancel` ends selection; it does not halt this script because `CANCEL_HALT` is off during the loop.

```sql
create temporary table chosen_materials (sample_material text primary key);
create temporary view available_materials as
select sample_material, description from e_sampmaterial
where sample_material not in (select sample_material from chosen_materials);

-- !x! CANCEL_HALT OFF
-- !x! LOOP WHILE (HASROWS(available_materials))
    -- !x! PROMPT SELECT_SUB available_materials MESSAGE "Choose a material; Cancel to finish."
    -- !x! IF (NOT SUB_DEFINED(@sample_material))
        -- !x! BREAK
    -- !x! ENDIF
    insert into chosen_materials values (!'!@sample_material!'!);
-- !x! END LOOP
-- !x! CANCEL_HALT ON

create temporary view selected_samples as
select * from d_sampmain
where sample_material in (select sample_material from chosen_materials);
-- !x! IF (HASROWS(chosen_materials))
    -- !x! PROMPT MESSAGE "Selected samples" DISPLAY selected_samples
-- !x! ENDIF
```

Each material can be selected once. Selecting all available materials also ends the loop. If another part of your script intentionally keeps `CANCEL_HALT OFF`, restore that policy instead of the `ON` used here.
