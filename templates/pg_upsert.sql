-- pg_upsert.sql
--
-- PURPOSE
--	A set of execsql scripts to check data in a staging table, or
--	a set of staging tables, and then update and insert rows of a base table
--	or base tables from the staging table(s) of the same name.
--
-- HOW TO USE THESE SCRIPTS
--	In the following steps, "call" means to use an execsql "execute script"
--	metacommand.  Script names are displayed in uppercase to distinguish
--	them below, but execsql is not case-sensitive.
--
--	The simplest usage is:
--		1. Call STAGED_TO_LOAD to create and initially populate a table
--			with the names of staging tables to be loaded, and initial
--			control variables used by other scripts.
--		2. Call LOAD_STAGING to perform QA checks for erroneous nulls,
--			duplicated primary keys, and missing foreign keys, and to
--			load the data using update and insert statements if there were
--			no QA errors.
--
--	The control table that is produced in step 1 above can be edited to
--	add a list of columns to exclude from the update, or to change the
--	defaults for display of changed data.  See the header notes for the
--	STAGED_TO_LOAD script.
--
--	The processes of performing QA checks and performing the upsert operations
--	can be further broken down into individual steps.  See Note #1 below
--	for the other scripts that can be used to carry out these steps.
--
-- NOTES
--	1. The scripts contained in this file that are intended to be called
--		directly by the user are:
--			STAGED_TO_LOAD	: Initialize a control table to load multiple tables.
--			LOAD_STAGING	: Perform all QA checks and load data from all staging tables.
--			QA_ALL			: Perform null and foreign key checks on all staging tables.
--			UPSERT_ALL		: Load data from all staging tables.
--			NULLQA_ONE		: Perform null column checks on one staging table.
--			PKQA_ONE		: Perform primary key check on one staging table.
--			FKQA_ONE		: Perform foreign key checks on one staging table.
--			UPSERT_ONE		: Load data from one staging table.
--			UPDTPK_ONE		: Perform PK updates for one table.
--			UPDTPKQA_ONE	: Perform QA checks related to PK updates, for one table.
--		This file contains other scripts that are intended to be used
--		only by one of the scripts listed above, and not called
--		directly by the user.
--	2. These scripts query the information schema to obtain
--		the information needed to perform the checks and changes.
--	3. These scripts were developed for PostgreSQL, and are likely to
--		need modification to run on other DBMSs.
--	4. These scripts take arguments that control their functions.  They
--		also use global variables pertinent to logging, if they are
--		defined.  The logging-control variables are global because
--		they may also be used by other code that uses these scripts,
--		and some of that code may be older and only recognize global
--		variables rather than script arguments; logging is intended
--		to be compatible with them.
--	5. The control table that is used to drive the loading of multiple
--		staging tables will be updated by the QA scripts with information
--		about any QA failures.  This information consists of a list of
--		the names of the columns or constraints that failed the check,
--		with the number of failing rows in parentheses following the name.
--	6. The control table that is used to drive the loading of multiple
--		staging tables will be updated by the upsert operation with
--		a count of the number of rows of the base table that are updated,
--		and a count of the number of rows that were inserted into the
--		base table.
--	7. All of these scripts assume that schema, table, and column
--		names need not be quoted.
--	8. These scripts create temporary tables and views.  All of these
--		have prefixes of "ups_".  Scripts that include this file
--		should not use this prefix to avoid possible conflicts.
--
-- COPYRIGHT AND LICENSE
--	Copyright (c) 2019, R. Dreas Nielsen
--	This program is free software: you can redistribute it and/or modify it
--	under the terms of the GNU General Public License as published by the
--	Free Software Foundation, either version 3 of the License, or (at your
--	option) any later version. This program is distributed in the hope that
--	it will be useful, but WITHOUT ANY WARRANTY; without even the implied
--	warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
--	GNU General Public License for more details. The GNU General Public
--	License is available at http://www.gnu.org/licenses/.

-- AUTHORS
--	Dreas Nielsen (RDN)
--  Elizabeth Shea (ES)
--	Tom Schulz (TS)
--
-- VERSION
--	2.0.0
--
-- HISTORY
--	 Date		 Remarks
--	----------	-----------------------------------------------------
--	2019-01-15	Began first component scripts.  RDN.
--	2019-01-30	Integrated separate scripts into this one file and
--				began modifications to set parameters and arguments.  RDN.
--	2019-01-31	Editing.  RDN.
--	2019-02-01	Completed revisions to set parameters and arguments.
--				Added scripts "staged_to_load", "upsert_all", and
--				"load_staging".
--				Added and modified documentation.  RDN.
--	2019-02-02	Debugging edits.  RDN.
--	2019-02-03	Added to script documentation.  Modified NULLQA_ONE
--				to always drop and recreate tt_nonnull_columns.
--				Corrected calls to foreign key check scripts. RDN.
--	2019-02-06	Fixed some erroneous argument variable references.
--				Modified to initially nullify the columns with return
--				values in the control table.  RDN.
--	2019-02-09	Modified to update the status bar if the console is
--				being used.  RDN.
--	2019-02-15	Modified all internal table and view names to use a
--				prefix of "ups_".  RDN.
--	2019-02-16	Modified to include in the list of ordered tables all
--				tables that are not part of any foreign key relationship.
--				Modified to use an 'exclude_null_checks' setting.  RDN.
--	2019-02-17	Corrected the check to display changes in UPSERT_ONE.  RDN.
--	2019-02-21	Modified QA_ALL_NULLLOOP and QA_ALL_FKLOOP to use
--				local variables and the new outer scope referent prefix
--				for the return values.  RDN.
--	2019-02-28	Changed to use system catalog to get foreign key columns.
--				Changed to use 'autocommit with commit'.  RDN.
--	2019-03-02	Modified recursive CTE to order dependencies to protect
--				against multi-table cycles.  RDN.
--	2019-03-02	Modified to show the number of rows with each invalid
--				foreign key value, in both the GUI display and the
--				logfile.  RDN.
--	2019-03-03	Added the 'do_commit' argument to LOAD_STAGING.  RDN.
--  2019-03-08	Made the following changes. ES.
--				o In UPSERT_ALL, changed ups_proctables from a permanent
--				  to a temp table.
--				o Edits to header notes to include PK check.
--				o Added logging of commit status to LOAD_STAGING.
--				o Modified UPSERT_ONE to create update statement only
--				  if there are any non-key columns in the base table.
--	2019-03-09 Made the following changes. ES.
--				o In UPSERT_ALL, removed duplication of parents with
--				  no children in ups_ordered_tables (lvls 1 and 0).
--				o In QA_ALL made progress bar progress specific to
--				  check type.
--				o Added primary key check.
--	2019-03-14	Modified regexp_split_to_table when populating control_table.
--				"Escape's leading \ will need to be doubled when entering the
--				pattern as an SQL string constant."  TS.
--  2019-03-15	Added definition and execution of validation scripts to
--				validate base and staging schemas and tables. ES.
--	2019-03-15	Modified ups_validate_control to cast base_schema and
--				staging_schema as text. TS.
--	2019-05-28	Corrected selection for ups_cols in script UPSERT_ONE to
--				include only columns that are also in base table (i.e.,
--				exclude any columns that are only in staging table, such
--				as any "new_" PK columns to be used for PK updates). ES.
--	2019-05-29	Added script UPDTPK_ONE. ES.
--  2019-05-30	Added UPDTPKQA_ONE through check #8. ES.
--	2019-06-03	Completed UPDTPKQA_ONE and added UPDTPKQA_ONE_INNERLOOP. ES.
--	2020-04-28	Explicitly rolled back the changes if 'do_commit' = "No".  RDN.
--	2020-05-09	Moved the assignment of 'upsert_progress_denom' out of the
--				'update_console_qa' script.  RDN.
--	2021-04-27	Added a semicolon to the end of all SQL statements that are
--				written to the logfile.  RDN.
--	2021-04-29	Modified to log the SQL for null checks as well, and so
--				that the "select" keyword of all checks is the first word
--				on a line of the logfile, for easier extraction.  RDN.
-- ==================================================================


-- ################################################################
--			Script VALIDATE_SCHEMAS
-- ===============================================================
--
-- Utility script to validate base and staging schema
--
-- Required input arguments:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--
--	Required output arguments:
--		error_list		: The name of the variable to receive a comma-
--							delimited list of the names of invalid
--							schema names.
-- ===============================================================
-- !x! BEGIN SCRIPT VALIDATE_SCHEMAS with parameters (base_schema, staging, error_list)

drop table if exists ups_ctrl_invl_schema cascade;
select
	string_agg(schemas.schema_name || ' (' || schema_type || ')', '; ' order by schema_type) as schema_string
into temporary table ups_ctrl_invl_schema
from
	(
	select
		'!!#base_schema!!' as schema_name,
		'base' as schema_type
	union
	select

		'!!#staging!!' as schema_name,
		'staging' as schema_type
	) as schemas
	left join information_schema.schemata as iss on schemas.schema_name=iss.schema_name
where
	iss.schema_name is null
--This is required in Postgres, otherwise, string_agg will return one row with NULL
having count(*)>0
;

-- !x! if(hasrows(ups_ctrl_invl_schema))
	-- !x! subdata !!#error_list!! ups_ctrl_invl_schema
-- !x! endif

-- !x! END SCRIPT
-- ####################  End of VALIDATE_SCHEMAS  #################
-- ################################################################



-- ################################################################
--			Script VALIDATE_ONE
-- ===============================================================
--
-- Utility script to validate one table in both base and staging schema.
-- Halts script processing if any either of the schemas are non-existent,
--  or if either of the tables are not present within those schemas.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table_name  	: The name of the table.
--		script          : The name of the script in which the
--							schemas and table were referenced
--							(for error reporting).
--		script_line		: The script line in which they were referenced
--							(for error reporting).
-- ===============================================================
-- !x! BEGIN SCRIPT VALIDATE_ONE with parameters (base_schema, staging, table, script, script_line)

-- Initialize the strings used to compile error information
-- !x! sub_empty ~err_info
-- !x! sub_empty ~error_list


-- Validate schemas
-- !x! execute script validate_schemas with args (base_schema=!!#base_schema!!, staging=!!#staging!!, error_list=+err_info)


-- If no schemas are invalid, check tables
-- !x! if(is_null("!!~err_info!!"))
	drop table if exists ups_invl_table cascade;
	select
		string_agg(tt.schema_name || '.' || tt.table_name || ' (' || tt.schema_type || ')', '; ' order by tt.schema_name, tt.table_name) as schema_table
	into temporary table ups_invl_table
	from
		(
		select
			'!!#base_schema!!' as schema_name,
			'base' as schema_type,
			'!!#table!!' as table_name
		union
		select

			'!!#staging!!' as schema_name,
			'staging' as schema_type,
			'!!#table!!' as table_name
		) as tt
		left join information_schema.tables as iss on tt.schema_name=iss.table_schema and tt.table_name=iss.table_name
	where
		iss.table_name is null
	--This is required in Postgres, otherwise, string_agg will return one row with NULL
	having count(*)>0
	;

	-- !x! if(hasrows(ups_invl_table))
		-- !x! subdata ~err_info ups_invl_table
		-- !x! sub ~error_list Non-existent table: !!~err_info!!
	-- !x! endif

-- !x! else
	-- !x! sub ~error_list Non-existent schema(s): !!~err_info!!
-- !x! endif


-- Halt script if any schemas or tables were found to be invalid
-- !x! if(not is_null("!!~error_list!!"))

	-- !x! sub ~error_message ERROR - INVALID OBJECT IN SCRIPT ARGUMENT

	-- !x! if(sub_defined(log_changes))
	-- !x! andif(is_true(!!log_changes!!))
		-- !x! write "==================================================================" to !!logfile!!
		-- !x! write "!!$current_time!! -- !!~error_message!!" to !!logfile!!
		-- !x! write "Script: !!#script!!; Line: !!#script_line!!" to !!logfile!!
		-- !x! write "!!~error_list!!" to !!logfile!!
	-- !x! endif

	-- !x! sub_append ~error_message Script: !!#script!!; Line: !!#script_line!!
	-- !x! sub_append ~error_message !!~error_list!!
	-- !x! halt message "!!~error_message!!"

-- !x! endif


-- !x! END SCRIPT
-- ####################  End of VALIDATE_ONE  #####################
-- ################################################################



-- ################################################################
--			Script VALIDATE_CONTROL
-- ===============================================================
--
-- Utility script to validate contents of control table against
--	base and staging schema
--
-- Required input arguments:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		control_table  	: The name of a temporary table as created by the
--							script STAGED_TO_LOAD.
--		script          : The name of the script in which the
--							schemas and control table were referenced
--							(for error reporting).
--		script_line		: The script line in which they were referenced
--							(for error reporting).
-- ===============================================================
-- !x! BEGIN SCRIPT VALIDATE_CONTROL with parameters (base_schema, staging, control_table, script, script_line)

-- Initialize the strings used to compile error information
-- !x! sub_empty ~err_info
-- !x! sub_empty ~error_list

-- !x! execute script validate_schemas with args (base_schema=!!#base_schema!!, staging=!!#staging!!, error_list=+err_info)


-- If no schemas are invalid, check tables
-- !x! if(is_null("!!~err_info!!"))
	drop table if exists ups_validate_control cascade;
	select
		cast('!!#base_schema!!' as text) as base_schema,
		cast('!!#staging!!' as text) as staging_schema,
		table_name,
		False as base_exists,
		False as staging_exists
	into temporary table ups_validate_control
	from !!#control_table!!
	;

	-- Update the control table
	update ups_validate_control as vc
		set base_exists = True
	from information_schema.tables as bt
	where
		vc.base_schema=bt.table_schema and vc.table_name=bt.table_name
		and bt.table_type= cast('BASE TABLE' as text)
	;

	update ups_validate_control as vc
		set staging_exists = True
	from information_schema.tables as st
	where
		vc.staging_schema=st.table_schema and vc.table_name=st.table_name
		and st.table_type= cast('BASE TABLE' as text)
	;

	drop table if exists ups_ctrl_invl_table cascade;
	select
			string_agg(schema_table, '; ' order by it.schema_table) as schema_table
	into temporary table ups_ctrl_invl_table
	from
			(
			select base_schema || '.' || table_name as schema_table
			from ups_validate_control
			where not base_exists
			union
			select staging_schema || '.' || table_name as schema_table
			from ups_validate_control
			where not staging_exists
			) as it
	--This is required in Postgres, otherwise, string_agg will return one row with NULL
	having count(*)>0
	;

	-- Any table is invalid
	-- !x! if(hasrows(ups_ctrl_invl_table))
		-- !x! subdata ~err_info ups_validate_control
		-- !x! sub ~error_list Non-existent table(s): !!~err_info!!
	-- !x! endif

-- !x! else
	-- !x! sub ~error_list Non-existent schema(s): !!~err_info!!
-- !x! endif


-- Halt script if any invalid objects found in control table
-- !x! if(not is_null("!!~error_list!!"))

	-- !x! sub ~error_message ERROR - INVALID OBJECTS IN CONTROL TABLE

	-- !x! if(sub_defined(log_changes))
	-- !x! andif(is_true(!!log_changes!!))
		-- !x! write "==================================================================" to !!logfile!!
		-- !x! write "!!$current_time!! -- !!~error_message!!" to !!logfile!!
		-- !x! write "Script: !!#script!!; Line: !!#script_line!!" to !!logfile!!
		-- !x! write "!!~error_list!!" to !!logfile!!
	-- !x! endif

	-- !x! sub_append ~error_message Script: !!#script!!; Line: !!#script_line!!
	-- !x! sub_append ~error_message !!~error_list!!
	-- !x! halt message "!!~error_message!!"

-- !x! endif


-- !x! END SCRIPT
-- ####################  End of VALIDATE_CONTROL  #################
-- ################################################################


-- ################################################################
--			Script STAGED_TO_LOAD
-- ===============================================================
--
-- Creates a table having the structure that is used to drive other
-- scripts that perform QA checks and the upsert operation on multiple
-- staging tables.
--
-- Input parameters:
--		control_table	: The name of the temporary table to be created.
--		table_list		: A string of comma-separated table names,
--							identifying the staging tables to be
--							checked or loaded.
--
-- Columns in the table created:
--		table_name		: The name of a base table that has a
--							corresponding table in a staging schema
--							containing data to be used to modify
--							the base table.
--		exclude_cols	: Contains a comma-separated list of single-quoted
--							column names in the base table that are not to
--							be updated from the staging table.  This is
--							uninitialized.
--		exclude_null_checks :
--						  Contains a comma-separated list of single-quoted
--							column names identifying column in the
--							staging table for which null checks
--							should not be performed.  This is
--							uninitialized.
--		display_changes	: A Boolean indicating whether the 'upsert'
--							operation should display the changes to
--							be made to the base table.  A separate
--							GUI display is used for updates and inserts.
--							Initialized to True.
--		display_final	: A Boolean indicating whether the 'upsert'
--							operation should display the entire base
--							table after updates and inserts have been
--							made.  Initialized to False.
--		null_errors		: Will contain a comma-separated list of
--							columns that are non-nullable in the base
--							table but that have nulls in the staging
--							table.  Initialized to null; may be filled
--							by the QA routines.
--		pk_errors		: Will contain a count of the number of distinct
--							primary key values having duplicate rows,
--							followed by the total row count for the
--							duplicated keys. Initialized to null; may
--							be filled by the QA routines.
--		fk_errors		: Will contain a comma-separated list of
--							foreign-key constraint names that are
--							not met by data in the staging table.
--							Initialized to null; may be filled by the
--							QA routines.
--		rows_updated	: Will contain a count of the rows updated
--							in the table by the upsert operation.
--		rows_inserted	: Will contain a count of the rows inserted
--							in the table by the upsert operation.
--
-- Example:
--		-- !x! execute script staged_to_load with (control_table=stagingtables, table_list="tbla, tblb, tblc")
-- ===============================================================

-- !x! BEGIN SCRIPT STAGED_TO_LOAD with parameters (control_table, table_list)

drop table if exists !!#control_table!! cascade;

create temporary table !!#control_table!! (
	table_name text not null unique,
	exclude_cols text,
	exclude_null_checks text,
	display_changes text not null default 'Yes',
	display_final text not null default 'No',
	null_errors text,
	pk_errors text,
	fk_errors text,
	rows_updated integer,
	rows_inserted integer,
	constraint ck_chgyn check (display_changes in ('Yes', 'No')),
	constraint ck_finalyn check (display_final in ('Yes', 'No'))
);

insert into !!#control_table!!
	(table_name)
select
	trim(regexp_split_to_table('!!#table_list!!', E'\\s*,\\s*')) as table_name;


-- !x! END SCRIPT
-- ##################  End of STAGED_TO_LOAD  #####################
-- ################################################################



-- ################################################################
--			Script LOAD_STAGING
-- ===============================================================
--
-- Performs QA checks for nulls in non-null columns, for duplicated
-- primary key values, and for invalid foreign keys in a set of staging
-- tables to be loaded into base tables.  If there are failures in the
-- QA checks, loading is not attempted.  If the loading step is carried
-- out, it is done within a transaction.
--
-- The "null_errors", "pk_errors", and "fk_errors" columns of the
-- control table will be updated to identify any errors that occur,
-- so that this information is available to the caller.
--
-- The "rows_updated" and "rows_inserted" columns of the control table
-- will be updated with counts of the number of rows affected by the
-- upsert operation for each table.
--
-- When the upsert operation updates the base table, all columns of the
-- base table that are also in the staging table are updated.  The
-- update operation does not test to see if column contents are different,
-- and so does not update only those values that are different.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		control_table	: The name of a table as created by the
--							script STAGED_TO_LOAD.
--		do_commit		: Whether or not the script should commit
--							the changes; should be 'Yes' or 'No'.
-- Global variables:
--		logfile			: The name of a log file to which error
--							messages will be written.  Optional.
--		log_sql			: A value of 'Yes' or 'No' to indicate whether
--							the SQL that is generated for each foreign
--							key check, and for each update and insert
--							statement, is written to the logfile.  Optional.
--		log_errors		: A value of 'Yes' or 'No' to indicate whether
--							foreign key errors are written to the logfile.
--							Optional.
--		log_changes		: A value of 'Yes' or 'No' indicating whether
--							the updated and inserted data should be
--							written to the logfile.  Optional.
--
-- Tables and views created or modified:
--		ups_qa_fails			: temporary view
-- ===============================================================

-- !x! BEGIN SCRIPT LOAD_STAGING with parameters (base_schema, staging, control_table, do_commit)

-- Clear the columns of return values from the control table, in case this control
-- table has been used previously.
update !!#control_table!!
set
	null_errors = null,
	pk_errors = null,
	fk_errors = null,
	rows_updated = null,
	rows_inserted = null
	;

-- Run QA checks.
-- !x! execute script QA_ALL with arguments (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)
drop view if exists ups_qa_fails cascade;
create temporary view ups_qa_fails as
select *
from !!#control_table!!
where null_errors is not null or pk_errors is not null or fk_errors is not null;
-- !x! if(not hasrows(ups_qa_fails))
	-- !x! sub ~preautocommit !!$autocommit_state!!
	-- !x! autocommit off
	-- Run the UPSERT operation.
	-- !x! execute script UPSERT_ALL with arguments (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)
	-- Commit the changes and then restore the previous autocommit state.
	-- !x! if(is_true(!!#do_commit!!))
		-- !x! autocommit on with commit
		-- !x! write "CHANGES COMMITTED."
		-- !x! if(sub_defined(log_changes))
		-- !x! andif(is_true(!!log_changes!!))
			-- !x! write "" to !!logfile!!
			-- !x! write "==================================================================" to !!logfile!!
			-- !x! write "!!$current_time!! -- CHANGES COMMITTED." to !!logfile!!
		-- !x! endif
	-- !x! else
		-- !x! autocommit on with rollback
		-- !x! write "CHANGES NOT COMMITTED ('do_commit' argument = !!#do_commit!!)"
		-- !x! if(sub_defined(log_changes))
		-- !x! andif(is_true(!!log_changes!!))
			-- !x! write "" to !!logfile!!
			-- !x! write "==================================================================" to !!logfile!!
			-- !x! write "!!$current_time!! -- CHANGES NOT COMMITTED ('do_commit' argument = !!#do_commit!!)" to !!logfile!!
		-- !x! endif
	-- !x! endif
	-- !x! autocommit !!~preautocommit!!
-- !x! endif

-- !x! END SCRIPT
-- ###################  End of LOAD_STAGING  ######################
-- ################################################################




-- ################################################################
--			Script NULLQA_ONE
-- ===============================================================
--
-- Checks that non-nullable columns are fully populated in a
-- staging table that is an image of the base table.
-- Reports any non-conforming columns to the console and optionally
-- to a log file.
--
-- Required input arguments:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The table name--same for base and staging.
-- Optional input arguments:
--		exclude_null_checks : A comma-separated list of singly-quoted
--								column names to be excluded from null checks.
--
--	Required output arguments:
--		error_list		: The name of the variable to receive a comma-
--							delimited list of the names of non-null
--							columns that contain nulls; each column name
--							will be followed by the number of rows with
--							nulls, in parentheses.
--
-- Global variables:
--		logfile			: The name of a log file to which error
--							messages will be written.  Optional.
--
-- Tables and views created or modified:
--		ups_nonnull_cols		: temporary table
--		ups_next_column			: temporary view
--		ups_null_error_list		: temporary view
--		ups_qa_nonnull_col		: temporary view
-- ===============================================================

-- !x! BEGIN SCRIPT NULLQA_ONE with parameters (base_schema, staging, table, error_list)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Non-null QA checks on table !!#staging!!.!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting non-null QA checks on table !!#staging!!.!!#table!!"

-- Validate inputs: base/staging schemas and table
-- !x! execute script validate_one with args (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)


-- Initialize the return value to empty (no null errors)
-- !x! sub_empty !!#error_list!!

-- Create a table listing the columns of the base table that must
-- be non-null and that do not have a default expression.
-- Include a column for the number of rows with nulls in the staging table.
-- Include a 'processed' column for loop control.
-- !x! if(sub_defined(#exclude_null_checks))
	-- !x! sub ~omitnull and column_name not in (!!#exclude_null_checks!!)
-- !x! else
	-- !x! sub_empty ~omitnull
-- !x! endif
drop table if exists ups_nonnull_cols cascade;
select
	column_name,
	0::integer as null_rows,
	False as processed
into
	temporary table ups_nonnull_cols
from
	information_schema.columns
where
	table_schema = '!!#base_schema!!'
	and table_name = '!!#table!!'
	and is_nullable = 'NO'
	and column_default is null
	!!~omitnull!!
	;

-- Create a view to select one column to process.
create or replace temporary view ups_next_column as
select column_name
from ups_nonnull_cols
where not processed
limit 1;

-- Process all non-nullable columns.
-- !x! execute script nullqa_one_innerloop with (staging=!!#staging!!, table=!!#table!!)

-- Create the return value.
create or replace temporary view ups_null_error_list as
select
	string_agg(column_name || ' (' || null_rows || ')', ', ') as null_errors
from
	ups_nonnull_cols
where
	coalesce(null_rows, 0) > 0;
-- !x! if(hasrows(ups_null_error_list))
	-- !x! subdata !!#error_list!! ups_null_error_list
-- !x! endif


-- !x! END SCRIPT
-- End of          NULLQA_ONE
-- ****************************************************************
-- ****************************************************************
--			Script NULLQA_ONE_INNERLOOP
-- ---------------------------------------------------------------
-- !x! BEGIN SCRIPT NULLQA_ONE_INNERLOOP with parameters (staging, table)

-- !x! if(hasrows(ups_next_column))
	-- !x! subdata ~column_name ups_next_column

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking column !!~column_name!!." to !!logfile!!
	-- !x! endif

	-- !x! sub     		  ~null_check   select nrows
	-- !x! sub_append     ~null_check   from (
	-- !x! sub_append     ~null_check       select count(*) as nrows
	-- !x! sub_append     ~null_check       from !!#staging!!.!!#table!!
	-- !x! sub_append     ~null_check       where !!~column_name!! is null
	-- !x! sub_append     ~null_check       ) as nullcount
	-- !x! sub_append     ~null_check   where nrows > 0
	-- !x! sub_append     ~null_check   limit 1

	create or replace temporary view ups_qa_nonnull_col as
	!!~null_check!!;
	/*
	select nrows
	from (
		select count(*) as nrows
		from !!#staging!!.!!#table!!
		where !!~column_name!! is null
		) as nullcount
	where nrows > 0
	limit 1;
	*/
	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "SQL for null check of !!~column_name!!:" to !!logfile!!
		-- !x! write [!!~null_check!!;] to !!logfile!!
	-- !x! endif


	-- !x! if(hasrows(ups_qa_nonnull_col))
		-- !x! subdata ~nullrows ups_qa_nonnull_col
		-- !x! write "    Column !!~column_name!! has !!~nullrows!! nulls."
		-- !x! if(sub_defined(logfile))
			-- !x! write "    Column !!~column_name!! has !!~nullrows!! nulls." to !!logfile!!
		-- !x! endif
		update ups_nonnull_cols
		set null_rows = (select nrows from ups_qa_nonnull_col limit 1)
		where column_name = '!!~column_name!!';
	-- !x! endif

	-- Mark this constraint as processed.
	update ups_nonnull_cols
	set processed = True
	where column_name = '!!~column_name!!';

	-- Loop.
	-- !x! execute script nullqa_one_innerloop with (staging=!!#staging!!, table=!!#table!!)

-- !x! endif

-- !x! END SCRIPT
-- ###################  End of NULL_QA_ONE  #######################
-- ################################################################



-- ################################################################
--			Script PKQA_ONE
--
-- Check data a staging table for violations of the primary key
-- of the corresponding base table.
-- Reports any PK violations found to the console and optionally
-- to a log file.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The table name--same for base and staging.
--		display_errors	: A value of 'Yes' or 'No' to indicate whether
--							unrecognized values should be displayed
--							in a GUI.
--	Output parameters:
--		error_list		: The name of the variable to receive a count
--							of the total number of distinct PK values
--							having violations, followed by a count of
--							the total rows associated with each.
--
-- Global variables:
--		logfile			: The name of a log file to which update
--							messages will be written.  Optional.
--		log_sql			: A value of 'Yes' or 'No' to indicate whether
--							the SQL that is generated for each foreign
--							key check is written to the logfile.  Optional.
--		log_errors		: A value of 'Yes' or 'No' to indicate whether
--							foreign key errors are written to the logfile.
--							Optional.
--
-- Tables and views created or modified:
--		ups_primary_key_columns		: temporary table
--		ups_pk_list					: temporary view
--		ups_pk_check				: temporary view
--		ups_ercnt					: temporary view
-- ===============================================================

-- !x! BEGIN SCRIPT PKQA_ONE with parameters (base_schema, staging, table, display_errors, error_list)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Primary key QA checks on table !!#staging!!.!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting primary key QA checks on table !!#staging!!.!!#table!!"

-- Validate inputs: base/staging schemas and table
-- !x! execute script validate_one with args (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)

-- Initialize the return value to False (no primary key errors)
-- !x! sub_empty !!#error_list!!

-- Create a table of primary key columns on this table
drop table if exists ups_primary_key_columns cascade;
select k.constraint_name, k.column_name, k.ordinal_position
into temporary table ups_primary_key_columns
from information_schema.table_constraints as tc
inner join information_schema.key_column_usage as k
    on tc.constraint_type = 'PRIMARY KEY'
    and tc.constraint_name = k.constraint_name
    and tc.constraint_catalog = k.constraint_catalog
    and tc.constraint_schema = k.constraint_schema
    and tc.table_schema = k.table_schema
    and tc.table_name = k.table_name
	and tc.constraint_name = k.constraint_name
where
	k.table_name = '!!#table!!'
	and k.table_schema = '!!#base_schema!!'
order by k.ordinal_position
;


-- !x! if(hasrows(ups_primary_key_columns))
	-- !x! subdata ~constraint_name ups_primary_key_columns

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking constraint !!~constraint_name!!." to !!logfile!!
	-- !x! endif

	-- Get a comma-delimited list of primary key columns to build SQL selection for duplicate keys
	create or replace temporary view ups_pk_list as
	select
		string_agg(column_name, ', ' order by ordinal_position) as pkcollist
	from ups_primary_key_columns
	;
	--!x! subdata ~pkcollist ups_pk_list

	-- Construct a query to test for duplicate values for pk columns.
	-- !x! sub     		  ~pk_check   select !!~pkcollist!!, count(*) as row_count
	-- !x! sub_append     ~pk_check   from !!#staging!!.!!#table!! as s
	-- !x! sub_append     ~pk_check   group by !!~pkcollist!!
	-- !x! sub_append     ~pk_check   having count(*) > 1

	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "SQL for primary key check:" to !!logfile!!
		-- !x! write [!!~pk_check!!;] to !!logfile!!
	-- !x! endif

	-- Run the check.
	drop view if exists ups_pk_check cascade;
	create or replace temporary view ups_pk_check as
	!!~pk_check!!;
	-- !x! if(hasrows(ups_pk_check))
		-- !x! write "    Duplicate key error on columns: !!~pkcollist!!."
		drop view if exists ups_ercnt cascade;
		create temporary view ups_ercnt as
		select
			count(*) as errcnt, sum(row_count) as total_rows
		from ups_pk_check;
		-- !x! select_sub ups_ercnt
		-- !x! sub !!#error_list!! !!@errcnt!! duplicated key(s) (!!@total_rows!! rows)
		-- !x! if(sub_defined(logfile))
			-- !x! write "Duplicate primary key values in !!#staging!!.!!#table!!" to !!logfile!!
			-- !x! if(sub_defined(log_errors))
			-- !x! andif(is_true(!!log_errors!!))
				-- !x! export ups_pk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Primary key violations in !!#table!!" display ups_pk_check
		-- !x! endif
	-- !x! endif
-- !x! endif


-- !x! END SCRIPT
-- ####################  End of PKQA_ONE  ########################
-- ################################################################



-- ################################################################
--			Script FKQA_ONE
--
-- Checks foreign keys from a staging table against a base table
-- and, if it exists, another staging table that is an image of the
-- base table.
-- Reports any bad references found to the console and optionally
-- to a log file.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The table name--same for base and staging.
--		display_errors	: A value of 'Yes' or 'No' to indicate whether
--							unrecognized values should be displayed
--							in a GUI.
--	Output parameters:
--		error_list		: The name of the variable to receive a comma-
--							delimited list of the names of foreign key
--							constraints that are not met.
--
-- Global variables:
--		logfile			: The name of a log file to which update
--							messages will be written.  Optional.
--		log_sql			: A value of 'Yes' or 'No' to indicate whether
--							the SQL that is generated for each foreign
--							key check is written to the logfile.  Optional.
--		log_errors		: A value of 'Yes' or 'No' to indicate whether
--							foreign key errors are written to the logfile.
--							Optional.
--
-- Tables and views created or modified:
--		ups_foreign_key_columns		: temporary table
--		ups_sel_fks					: temporary table
--		ups_fk_constraints			: temporary table
--		ups_next_constraint			: temporary view
--		ups_error_list				: temporary view
--		ups_one_fk					: temporary table
--		ups_fk_joins				: temporary view
--		ups_fk_check				: temporary view
--		ups_ercnt					: temporary view
-- ===============================================================

-- !x! BEGIN SCRIPT FKQA_ONE with parameters (base_schema, staging, table, display_errors, error_list)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Foreign key QA checks on table !!#staging!!.!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting foreign key QA checks on table !!#staging!!.!!#table!!"

-- Validate inputs: base/staging schemas and table
-- !x! execute script validate_one with args (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)


-- Initialize the return value to False (no foreign key errors)
-- !x! sub_empty !!#error_list!!


-- Create a table of *all* foreign key dependencies in this database.
-- Because this may be an expensive operation (in terms of time), the
-- table is not re-created if it already exists.  "Already exists"
-- means that a table with the expected name exists.  No check is
-- done to ensure that this table has the correct structure.  The
-- goal is to create the table of all foreign keys only once to
-- minimize the time required if QA checks are to be run on multiple
-- staging tables.
-- !x! if(not table_exists(ups_foreign_key_columns))
	select
    	fkinf.constraint_name,
    	fkinf.table_schema,
    	fkinf.table_name,
    	att1.attname as column_name,
    	fkinf.uq_schema,
    	cls.relname as uq_table,
    	att2.attname as uq_column
	into
		temporary table ups_foreign_key_columns
	from
   	(select
        	ns1.nspname as table_schema,
        	cls.relname as table_name,
        	unnest(cons.conkey) as uq_table_id,
        	unnest(cons.confkey) as table_id,
        	cons.conname as constraint_name,
        	ns2.nspname as uq_schema,
        	cons.confrelid,
        	cons.conrelid
    	from
		pg_constraint as cons
        	inner join pg_class as cls on cls.oid = cons.conrelid
        	inner join pg_namespace ns1 on ns1.oid = cls.relnamespace
        	inner join pg_namespace ns2 on ns2.oid = cons.connamespace
    	where
		cons.contype = 'f'
   	) as fkinf
   	inner join pg_attribute att1 on
       	att1.attrelid = fkinf.conrelid and att1.attnum = fkinf.uq_table_id
   	inner join pg_attribute att2 on
       	att2.attrelid = fkinf.confrelid and att2.attnum = fkinf.table_id
   	inner join pg_class cls on cls.oid = fkinf.confrelid;
-- !x! endif

-- Create a temporary table of just the foreign key relationships for the base
-- table corresponding to the staging table to check.
drop table if exists ups_sel_fks cascade;
select
	constraint_name, table_schema, table_name, column_name,
	--ordinal_position,
	uq_schema, uq_table, uq_column
into
	temporary table ups_sel_fks
from
	ups_foreign_key_columns
where
	table_schema = '!!#base_schema!!'
	and table_name = '!!#table!!';

-- Create a temporary table of all unique constraint names for
-- this table, with an integer column to be populated with the
-- number of rows failing the foreign key check, and a 'processed'
-- 	flag to control looping.
drop table if exists ups_fk_constraints cascade;
select distinct
	constraint_name, table_schema, table_name,
	0::integer as fkerror_values,
	False as processed
into temporary table ups_fk_constraints
from ups_sel_fks;

-- Create a view to select one constraint to process.
create or replace temporary view ups_next_constraint as
select constraint_name, table_schema, table_name
from ups_fk_constraints
where not processed
limit 1;

-- Process all constraints: check every foreign key.
-- !x! execute script fk_qa_one_innerloop with (staging=!!#staging!!, table=!!#table!!, display_errors=!!#display_errors!!)

-- Create the return value.
create or replace temporary view ups_error_list as
select
	string_agg(constraint_name || ' (' || fkerror_values || ')', ', ') as fk_errors
from
	ups_fk_constraints
where
	coalesce(fkerror_values, 0) > 0;
-- !x! if(hasrows(ups_error_list))
	-- !x! subdata !!#error_list!! ups_error_list
-- !x! endif


-- !x! END SCRIPT
-- End of          FKQA_ONE
-- ****************************************************************
-- ****************************************************************
--			Script FK_QA_ONE_INNERLOOP
-- ----------------------------------------------------------------
-- !x! BEGIN SCRIPT FK_QA_ONE_INNERLOOP with parameters (staging, table, display_errors)

-- !x! if(hasrows(ups_next_constraint))
	-- !x! select_sub ups_next_constraint

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking constraint !!@constraint_name!! for table !!@table_schema!!.!!@table_name!!." to !!logfile!!
	-- !x! endif

	drop table if exists ups_one_fk cascade;
	select column_name, uq_schema, uq_table, uq_column
	into temporary table ups_one_fk
	from ups_sel_fks
	where
		constraint_name = '!!@constraint_name!!'
		and table_schema = '!!@table_schema!!'
		and table_name = '!!@table_name!!';

	-- Get the unique table schema and name into data variables.
	-- !x! select_sub ups_one_fk

	-- Create join expressions from staging table (s) to unique table (u)
	-- and to staging table equivalent to unique table (su) (though we
	-- don't know yet if the latter exists).  Also create a 'where'
	-- condition to ensure that all columns being matched are non-null.
	-- Also create a comma-separated list of the columns being checked.
	create or replace temporary view ups_fk_joins as
	select
		string_agg('s.' || column_name || ' = u.' || uq_column, ' and ') as u_join,
		string_agg('s.' || column_name || ' = su.' || uq_column, ' and ') as su_join,
		string_agg('s.' || column_name || ' is not null', ' and ') as s_not_null,
		string_agg('s.' || column_name, ', ') as s_checked
	from
		(select * from ups_one_fk) as fkcols;
	-- !x! select_sub ups_fk_joins

	-- Determine whether a staging-table equivalent of the unique table exists.
	-- !x! sub su_exists No
	-- !x! if(table_exists(!!#staging!!.!!@uq_table!!))
		-- !x! sub su_exists Yes
	-- !x! endif

	-- Construct a query to test for missing unique values for fk columns.
	-- !x! sub            ~fk_check   select !!@s_checked!!, count(*) as row_count
	-- !x! sub_append     ~fk_check   from !!#staging!!.!!#table!! as s
	-- !x! sub_append     ~fk_check   left join !!@uq_schema!!.!!@uq_table!! as u on !!@u_join!!
	-- !x! if(is_true(!!su_exists!!))
		-- !x! sub_append ~fk_check   left join !!#staging!!.!!@uq_table!! as su on !!@su_join!!
	-- !x! endif
	-- !x! sub_append     ~fk_check   where u.!!@uq_column!! is null
	-- !x! if(is_true(!!su_exists!!))
		-- !x! sub_append ~fk_check   and su.!!@uq_column!! is null
	-- !x! endif
	-- !x! sub_append     ~fk_check   and !!@s_not_null!!
	-- !x! sub_append     ~fk_check   group by !!@s_checked!!

	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "SQL for foreign key check:" to !!logfile!!
		-- !x! write [!!~fk_check!!;] to !!logfile!!
	-- !x! endif

	-- Run the check.
	drop view if exists ups_fk_check cascade;
	create or replace temporary view ups_fk_check as
	!!~fk_check!!;
	-- !x! if(hasrows(ups_fk_check))
		-- !x! write "    Foreign key error referencing !!@uq_table!!."
		drop view if exists ups_ercnt cascade;
		create temporary view ups_ercnt as
		select count(*) from ups_fk_check;
		-- !x! subdata ~errcnt ups_ercnt
		update ups_fk_constraints
		set fkerror_values = !!~errcnt!!
		where
			constraint_name = '!!@constraint_name!!'
			and table_schema = '!!@table_schema!!'
			and table_name = '!!@table_name!!';
		-- !x! if(sub_defined(logfile))
			-- !x! write " Foreign key errors in !!#table!! referencing !!@uq_table!!" to !!logfile!!
			-- !x! if(sub_defined(log_errors))
			-- !x! andif(is_true(!!log_errors!!))
				-- !x! export ups_fk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Foreign key errors in !!#table!! referencing !!@uq_table!!" display ups_fk_check
		-- !x! endif
	-- !x! endif


	-- Mark this constraint as processed.
	update ups_fk_constraints
	set processed = True
	where
		constraint_name = '!!@constraint_name!!'
		and table_schema = '!!@table_schema!!'
		and table_name = '!!@table_name!!';

	-- Loop.
	-- !x! execute script fk_qa_one_innerloop with (staging=!!#staging!!, table=!!#table!!, display_errors=!!#display_errors!!)

-- !x! endif

-- !x! END SCRIPT
-- ####################  End of FK_QA_ONE  ########################
-- ################################################################




-- ################################################################
--			Script UPSERT_ONE
--
-- Adds data from a staging table to a base table, using UPDATE
-- and INSERT statements.  Displays data to be modified to the
-- user before any modifications are done.  Reports the changes
-- made to the console and optionally to a log file.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The table name--same for base and staging.
--		exclude_cols	: A comma-delimited list of single-quoted
--							column names identifying the columns
--							of the base table that are not to be
--							modified.  These may be autonumber
--							columns or columns filled by triggers.
--		display_changes	: A boolean variable indicating whether
--							or not the changes to be made to the
--							base table should be displayed in a GUI.
--		display_final	: A boolean variable indicating whether or
--							not the base table should be displayed
--							after updates and inserts are completed.
--		updcntvar		: The name of a substitution variable that
--							will be set to the number of rows updated.
--		inscntvar		: The name of a substitution variable that
--							will be set to the number of rows inserted.
--
--	Global variables:
--		logfile			: The name of a log file to which update
--							messages will be written.  Optional.
--		log_sql			: A value of 'Yes' or 'No' indicating whether
--							the update and insert statements should
--							also be written to the logfile.  Optional.
--		log_changes		: A value of 'Yes' or 'No' indicating whether
--							the updated and inserted data should be
--							written to the logfile.  Optional.
--
-- Tables and views created or modified:
--		ups_cols				: temporary table
--		ups_pks					: temporary table
--		ups_allcollist			: temporary view
--		ups_allbasecollist		: temporary view
--		ups_allstgcollist		: temporary view
--		ups_pkcollist			: temporary view
--		ups_joinexpr			: temporary view
--		ups_basematches			: temporary view
--		ups_stgmatches			: temporary view
--		ups_nk					: temporary view
--		ups_assexpr				: temporary view
--		ups_newrows				: temporary view
-- ===============================================================

-- !x! BEGIN SCRIPT UPSERT_ONE with parameters (base_schema, staging, table, exclude_cols, display_changes, display_final, updcntvar, inscntvar)

-- Remove substitution variables that will contain the generated
-- update and insert statements so that the existence of valid
-- statements can be later tested based on the existence of these variables.
-- !x! rm_sub ~updatestmt
-- !x! rm_sub ~insertstmt

-- !x! sub ~do_updates Yes
-- !x! sub ~do_inserts Yes

-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Performing upsert on table !!#base_schema!!.!!#table!!" to !!logfile!!
-- !x! endif


-- !x! write "Performing upsert on table !!#base_schema!!.!!#table!!"


-- Validate inputs: base/staging schemas and table
-- !x! execute script validate_one with args (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)


-- Populate a (temporary) table with the names of the columns
-- in the base table that are to be updated from the staging table.
-- Include only those columns from staging table that are also in base table.
-- !x! if(is_null("!!#exclude_cols!!"))
	-- !x! sub_empty ~col_excl
-- !x! else
	-- !x! sub ~col_excl and column_name not in (!!#exclude_cols!!)
-- !x! endif
drop table if exists ups_cols cascade;
select s.column_name
into temporary table ups_cols
from information_schema.columns as s
	inner join information_schema.columns as b on s.column_name=b.column_name
where
	s.table_schema = '!!#staging!!'
	and s.table_name = '!!#table!!'
	and b.table_schema = '!!#base_schema!!'
	and b.table_name = '!!#table!!'
	!!~col_excl!!
order by s.ordinal_position;


-- Populate a (temporary) table with the names of the primary key
-- columns of the base table.
drop table if exists ups_pks cascade;
select k.column_name
into temporary table ups_pks
from information_schema.table_constraints as tc
inner join information_schema.key_column_usage as k
    on tc.constraint_type = 'PRIMARY KEY'
    and tc.constraint_name = k.constraint_name
    and tc.constraint_catalog = k.constraint_catalog
    and tc.constraint_schema = k.constraint_schema
    and tc.table_schema = k.table_schema
    and tc.table_name = k.table_name
	and tc.constraint_name = k.constraint_name
where
	k.table_name = '!!#table!!'
	and k.table_schema = '!!#base_schema!!'
order by k.ordinal_position;

-- Get all base table columns that are to be updated into a comma-delimited list.
drop view if exists ups_allcollist cascade;
create temporary view ups_allcollist as
select string_agg(column_name, ', ')
from ups_cols;
-- !x! subdata ~allcollist ups_allcollist;


-- Get all base table columns that are to be updated into a comma-delimited list
-- with a "b." prefix.
drop view if exists ups_allbasecollist cascade;
create temporary view ups_allbasecollist as
select string_agg('b.' || column_name, ', ')
from ups_cols;
-- !x! subdata ~allbasecollist ups_allbasecollist;

-- Get all staging table column names for columns that are to be updated
-- into a comma-delimited list with an "s." prefix.
drop view if exists ups_allstgcollist cascade;
create temporary view ups_allstgcollist as
select string_agg('s.' || column_name, ', ')
from ups_cols;
-- !x! subdata ~allstgcollist ups_allstgcollist;


-- Get the primary key columns in a comma-delimited list.
drop view if exists ups_pkcollist cascade;
create temporary view ups_pkcollist as
select string_agg(column_name, ', ')
from ups_pks;
-- !x! subdata ~pkcollist ups_pkcollist;


-- Create a join expression for key columns of the base (b) and
-- staging (s) tables.
drop view if exists ups_joinexpr cascade;
create temporary view ups_joinexpr as
select
	string_agg('b.' || column_name || ' = s.' || column_name, ' and ')
from
	ups_pks;
-- !x! subdata ~joinexpr ups_joinexpr


-- Create a FROM clause for an inner join between base and staging
-- tables on the primary key column(s).
-- !x! sub ~fromclause FROM !!#base_schema!!.!!#table!! as b INNER JOIN !!#staging!!.!!#table!! as s ON !!~joinexpr!!


-- Create SELECT queries to pull all columns with matching keys from both
-- base and staging tables.
drop view if exists ups_basematches cascade;
create temporary view ups_basematches as select !!~allbasecollist!! !!~fromclause!!;

drop view if exists ups_stgmatches cascade;
create temporary view ups_stgmatches as select !!~allstgcollist!! !!~fromclause!!;


--Get non-key columns to be updated
drop view if exists ups_nk cascade;
create temporary view ups_nk as
select column_name from ups_cols
except
select column_name from ups_pks
;

-- Prompt user to examine matching data and commit, don't commit, or quit.
-- !x! if(hasrows(ups_stgmatches))
-- !x! andif(hasrows(ups_nk))
	-- Prompt user to examine matching data and commit, don't commit, or quit.
	-- !x! if(is_true(!!#display_changes!!))
		-- !x! prompt ask "Do you want to make these changes? For table !!#table!!, new data are shown in the top table below; existing data are in the lower table." sub ~do_updates compare ups_stgmatches and ups_basematches key (!!~pkcollist!!)
	-- !x! endif
	-- !x! if(is_true(!!~do_updates!!))
		-- Create an assignment expression to update non-key columns of the
		-- base table (un-aliased) from columns of the staging table (as s).
		drop view if exists ups_assexpr cascade;
		create temporary view ups_assexpr as
		select
				string_agg(column_name || ' = s.' || column_name, ', ') as col
		from ups_nk;
		-- !x! subdata ~assexpr ups_assexpr
		-- Create an UPDATE statement to update the base table with
		-- non-key columns from the staging table.  No semicolon terminating generated SQL.
		-- !x! sub ~updatestmt UPDATE !!#base_schema!!.!!#table!! as b SET !!~assexpr!! FROM !!#staging!!.!!#table!! as s WHERE !!~joinexpr!!
	-- !x! endif
-- !x! endif


-- Create a select statement to find all rows of the staging table
-- that are not in the base table.
drop view if exists ups_newrows cascade;
create temporary view ups_newrows as
with newpks as (
	select !!~pkcollist!! from !!#staging!!.!!#table!!
	except
	select !!~pkcollist!! from !!#base_schema!!.!!#table!!
	)
select
	s.*
from
	!!#staging!!.!!#table!! as s
	inner join newpks using (!!~pkcollist!!);


-- Prompt user to examine new data and continue or quit.
-- !x! if(hasrows(ups_newrows))
	-- !x! if(is_true(!!#display_changes!!))
		-- !x! prompt ask "Do you want to add these new data to the !!#base_schema!!.!!#table!! table?" sub ~do_inserts display ups_newrows
	-- !x! endif

	-- !x! if(is_true(!!~do_inserts!!))
		-- Create an insert statement.  No semicolon terminating generated SQL.
		-- !x! sub ~insertstmt INSERT INTO !!#base_schema!!.!!#table!! (!!~allcollist!!) SELECT !!~allcollist!! FROM ups_newrows
	-- !x! endif
-- !x! endif


-- Run the update and insert statements.

-- !x! if(sub_defined(~updatestmt))
-- !x! andif(is_true(!!~do_updates!!))
	-- !x! write "Updating !!#base_schema!!.!!#table!!"
	-- !x! if(sub_defined(logfile))
		-- !x! write "" to !!logfile!!
		-- !x! if(sub_defined(log_sql))
		-- !x! andif(is_true(!!log_sql!!))
			-- !x! write "UPDATE statement for !!#base_schema!!.!!#table!!:" to !!logfile!!
			-- !x! write [!!~updatestmt!!;] to !!logfile!!
		-- !x! endif
		-- !x! if(sub_defined(log_changes))
		-- !x! andif(is_true(!!log_changes!!))
			-- !x! write "Updates:" to !!logfile!!
			-- !x! export ups_stgmatches append to !!logfile!! as txt
		-- !x! endif
		-- !x! write "" to !!logfile!!
	-- !x! endif
	!!~updatestmt!!;
	-- !x! sub !!#updcntvar!! !!$last_rowcount!!
	-- !x! if(sub_defined(logfile))
		-- !x! write "!!$last_rowcount!! rows of !!#base_schema!!.!!#table!! updated." to !!logfile!!
	-- !x! endif
	-- !x! write "    !!$last_rowcount!! rows updated."
-- !x! endif


-- !x! if(sub_defined(~insertstmt))
-- !x! andif(is_true(!!~do_inserts!!))
	-- !x! write "Adding data to !!#base_schema!!.!!#table!!"
	-- !x! if(sub_defined(logfile))
		-- !x! write "" to !!logfile!!
		-- !x! if(sub_defined(log_sql))
		-- !x! andif(is_true(!!log_sql!!))
			-- !x! write "INSERT statement for !!#base_schema!!.!!#table!!:" to !!logfile!!
			-- !x! write [!!~insertstmt!!;] to !!logfile!!
		-- !x! endif
		-- !x! if(sub_defined(log_changes))
		-- !x! andif(is_true(!!log_changes!!))
			-- !x! write "New data:" to !!logfile!!
			-- !x! export ups_newrows append to !!logfile!! as txt
		-- !x! endif
		-- !x! write "" to !!logfile!!
	-- !x! endif
	!!~insertstmt!!;
	-- !x! sub !!#inscntvar!! !!$last_rowcount!!
	-- !x! if(sub_defined(logfile))
		-- !x! write "!!$last_rowcount!! rows added to !!#base_schema!!.!!#table!!." to !!logfile!!
	-- !x! endif
	-- !x! write "    !!$last_rowcount!! rows added."
-- !x! endif


-- !x! if(is_true(!!#display_final!!))
	-- !x! prompt message "Table !!#base_schema!!.!!#table!! after updates and inserts." display !!#base_schema!!.!!#table!!
-- !x! endif


-- !x! END SCRIPT
-- ###################  End of UPSERT_ONE  ########################
-- ################################################################




-- ################################################################
--			Script UPSERT_ALL
--
-- Updates multiple base tables with new or revised data from
-- staging tables, using the UPSERT_ONE script.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		control_table	: The name of a table containing at least the
--							following four columns:
--								table_name	: The name of a table
--												  to be updated.
--								exclude_cols	: A comma-delimited
--													list of single-
--													quoted column
--													names, as required
--													by UPDATE_ANY.
--								display_changes	: A value of "Yes" or
--													"No" indicating
--													whether the changes
--													for the table should
--													be displayed.
--								display_final	: A value of "Yes" or
--													"No" indicating
--													whether the final
--													state of the table
--													should be displayed.
--							A table with these columns will be created
--							by the script STAGED_TO_LOAD.
--
-- Global variables:
--		logfile			: The name of a log file to which update
--							messages will be written.  Optional.
--		log_sql			: A boolean variable indicating whether
--							the update and insert statements should
--							also be written to the logfile.
--		upsert_progress_denom	: Created or modified.
--
-- Tables and views used:
--		ups_dependencies		: temporary table
--		ups_ordered_tables		: temporary table
--		ups_upsert_rows			: temporary view
--
-- Counter variables:
--		221585944		: Progress indicator.
--
-- ===============================================================

-- !x! BEGIN SCRIPT UPSERT_ALL with parameters (base_schema, staging, control_table)


-- Validate contents of control table
-- !x! execute script validate_control with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!, script=!!$CURRENT_SCRIPT_NAME!!, script_line=!!$SCRIPT_LINE!!)


-- Initialize the status and progress bars if the console is running.
-- !x! if(console_on)
	-- !x! reset counter 221585944
	-- !x! console status "Merging data"
	-- !x! console progress 0
	drop view if exists ups_upsert_rows;
	create temporary view ups_upsert_rows as
	select count(*) + 1 as upsert_rows
	from !!#control_table!!;
	-- !x! subdata upsert_progress_denom ups_upsert_rows
-- !x! endif


-- Get a table of all dependencies for the base schema.
drop table if exists ups_dependencies cascade;
create temporary table ups_dependencies as
select
	tc.table_name as child,
	tu.table_name as parent
from
	information_schema.table_constraints as tc
	inner join information_schema.constraint_table_usage as tu
    	on tu.constraint_name = tc.constraint_name
where
	tc.constraint_type = 'FOREIGN KEY'
	and tc.table_name <> tu.table_name
	and tc.table_schema = '!!#base_schema!!';


-- Create a list of tables in the base schema ordered by dependency.
drop table if exists ups_ordered_tables cascade;
with recursive dep_depth as (
	select
		dep.child as first_child,
  		dep.child,
  		dep.parent,
  		1 as lvl
	from
		ups_dependencies as dep
	union all
	select
		dd.first_child,
		dep.child,
		dep.parent,
		dd.lvl + 1 as lvl
	from
		dep_depth as dd
		inner join ups_dependencies as dep on dep.parent = dd.child
			and dep.child <> dd.parent
			and not (dep.parent = dd.first_child and dd.lvl > 2)
 	)
select
	table_name,
	table_order
into
	temporary table ups_ordered_tables
from (
	--All parents
	select
		dd.parent as table_name,
		max(lvl) as table_order
	from
		dep_depth as dd
	group by
		table_name
	union
	--Children that are not parents
	select
		dd.child as table_name,
		max(lvl) + 1 as level
	from
		dep_depth as dd
		left join ups_dependencies as dp on dp.parent = dd.child
	where
		dp.parent is null
	group by
		dd.child
	union
	--Neither parents nor children
	select distinct
		t.table_name,
		0 as level
	from
		information_schema.tables as t
		left join ups_dependencies as p on t.table_name=p.parent
		left join ups_dependencies as c on t.table_name=c.child
	where
		t.table_schema = '!!#base_schema!!'
		and t.table_type = 'BASE TABLE'
		and p.parent is null
		and c.child is null
	) as all_levels;


-- Create a list of the selected tables with ordering information.
drop table if exists ups_proctables cascade;
select
	ot.table_order,
	tl.table_name,
	tl.exclude_cols,
	tl.display_changes,
	tl.display_final,
	tl.rows_updated,
	tl.rows_inserted,
	False::boolean as processed
into
	temporary table ups_proctables
from
	!!#control_table!! as tl
	inner join ups_ordered_tables as ot on ot.table_name = tl.table_name
	;

-- Create a view returning a single unprocessed table, in order.
drop view if exists ups_toprocess cascade;
create temporary view ups_toprocess as
select
	table_name, exclude_cols,
	display_changes, display_final,
	rows_updated, rows_inserted
from ups_proctables
where not processed
order by table_order
limit 1;

-- Process all tables in order.
-- !x! execute script upsert_all_innerloop with (base_schema=!!#base_schema!!, staging=!!#staging!!)

-- Move the update/insert counts back into the control table.
update !!#control_table!! as ct
set
	rows_updated = pt.rows_updated,
	rows_inserted = pt.rows_inserted
from
	ups_proctables as pt
where
	pt.table_name = ct.table_name;


-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console status "Data merge complete"
	-- !x! console progress 0
-- !x! endif


-- !x! END SCRIPT
--					UPSERT_ALL
-- ****************************************************************
-- ****************************************************************
--		Script UPSERT_ALL_INNERLOOP
-- ---------------------------------------------------------------

-- !x! BEGIN SCRIPT UPSERT_ALL_INNERLOOP with parameters (base_schema, staging)

-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- Create variables to store the row counts from updates and inserts.
	-- (These should be changed to local variables after an outer-scope-referent prefix is implemented.)
	-- !x! sub ~rows_updated 0
	-- !x! sub ~rows_inserted 0

	-- !x! select_sub ups_toprocess
	-- !x! execute script upsert_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, exclude_cols=[!!@exclude_cols!!], display_changes=!!@display_changes!!, display_final=!!@display_final!!, updcntvar=+rows_updated, inscntvar=+rows_inserted)

	update ups_proctables
	set rows_updated = !!~rows_updated!!,
		rows_inserted = !!~rows_inserted!!
	where table_name = '!!@table_name!!';

	update ups_proctables
	set processed = True
	where table_name = '!!@table_name!!';
	-- !x! execute script upsert_all_innerloop with (base_schema=!!#base_schema!!, staging=!!#staging!!)
-- !x! endif

-- !x! END SCRIPT
-- ###############  End of UPSERT_ALL_INNERLOOP  ##################
-- ################################################################




-- ################################################################
--			Script QA_ALL
--
-- Conducts null and foreign key checks on multiple staging tables
-- containing new or revised data for staging tables, using the
-- NULLQA_ONE, PKQA_ONE, and FKQA_ONE scripts.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		control_table	: The name of a table containing at least the
--							following three columns:
--								table_name		: The name of a table
--												  to be updated.
--								null_errors		: For a comma-separated
--													list of columns that
--													are non-nullable in
--													the base table but
--													null in the staging
--													table.
--								pk_errors		: For a count of the number
--													of distinct primary key
--													values that are duplicated,
--													followed by the total row
--													count for the duplicated keys.
--								fk_errors		: For a comma-separated
--													list of foreign-key
--													constraint names that
--													are not met by the
--													staging table.
--							A table with these columns will be created
--							by the script STAGED_TO_LOAD.
--
-- Global variables:
--		logfile			: The name of a log file to which error
--							messages will be written.  Optional.
--		log_sql			: A value of 'Yes' or 'No' to indicate whether
--							the SQL that is generated for each foreign
--							key check is written to the logfile.  Optional.
--		log_errors		: A value of 'Yes' or 'No' to indicate whether
--							foreign key errors are written to the logfile.
--							Optional.
--
-- Tables and views used:
--		ups_proctables				: table
--		ups_toprocess				: temporary view
--		ups_upsert_rows				: temporary view
--
-- Counters used:
--		221585944					: Progress bar position
--
-- Global variables modified:
--		upsert_progress_denom		: Created or redefined.
--
-- ===============================================================

-- !x! BEGIN SCRIPT QA_ALL with parameters (base_schema, staging, control_table)

-- Get denominator for progress bar if console is on.
-- !x! if(console_on)
	drop view if exists ups_upsert_rows;
	create temporary view ups_upsert_rows as
	select count(*) + 1 as upsert_rows
	from !!#control_table!!;
	-- !x! subdata upsert_progress_denom ups_upsert_rows
-- !x! endif

-- Initialize the status and progress bars if the console is running.
-- !x! begin script update_console_qa with parameters (check_type)
-- !x! if(console_on)
	-- !x! reset counter 221585944
	-- !x! console status "Performing !!#check_type!! QA checks"
	-- !x! console progress 0
-- !x! endif
-- !x! end script

-- Create a list of the selected tables with a loop control flag.
drop table if exists ups_proctables cascade;
select
	tl.table_name,
	tl.exclude_null_checks,
	tl.display_changes,
	False::boolean as processed
into
	temporary table ups_proctables
from
	!!#control_table!! as tl
	;

-- Create a view returning a single unprocessed table, in order.
drop view if exists ups_toprocess cascade;
create temporary view ups_toprocess as
select table_name, exclude_null_checks, display_changes
from ups_proctables
where not processed
limit 1;

-- Perform null QA checks on all tables.
-- !x! execute script update_console_qa with args (check_type=NULL)
-- !x! execute script qa_all_nullloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)


-- Perform primary QA checks on all tables.
update ups_proctables set processed = False;
-- !x! execute script update_console_qa with args (check_type=primary key)
-- !x! execute script qa_all_pkloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)


-- Perform foreign key QA checks on all tables.
update ups_proctables set processed = False;
-- !x! execute script update_console_qa with args (check_type=foreign key)
-- !x! execute script qa_all_fkloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)

-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console status "Data QA checks complete"
	-- !x! console progress 0
-- !x! endif

-- !x! END SCRIPT
--					QA_ALL
-- ****************************************************************
-- ****************************************************************
--		Script QA_ALL_NULLLOOP
-- ---------------------------------------------------------------

-- !x! BEGIN SCRIPT QA_ALL_NULLLOOP with parameters (base_schema, staging, control_table)

-- !x! sub_empty ~ups_null_error_list

-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- !x! select_sub ups_toprocess
	-- !x! if(is_null("!!@exclude_null_checks!!"))
		-- !x! execute script nullqa_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, error_list=+ups_null_error_list)
	-- !x! else
		-- !x! execute script nullqa_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, error_list=+ups_null_error_list, exclude_null_checks=[!!@exclude_null_checks!!])
	-- !x! endif
	-- !x! if(not is_null("!!~ups_null_error_list!!"))
		update !!#control_table!!
		set null_errors = '!!~ups_null_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update ups_proctables
	set processed = True
	where table_name = '!!@table_name!!';
	-- !x! execute script qa_all_nullloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)
-- !x! endif

-- !x! END SCRIPT
--					QA_ALL_NULLLOOP
-- ****************************************************************
-- ****************************************************************
--		Script QA_ALL_PKLOOP
-- ---------------------------------------------------------------

-- !x! BEGIN SCRIPT QA_ALL_PKLOOP with parameters (base_schema, staging, control_table)

-- !x! sub_empty ~ups_pk_error_list
-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- !x! select_sub ups_toprocess
	-- !x! execute script pkqa_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, display_errors=!!@display_changes!!, error_list=+ups_pk_error_list)
	-- !x! if(not is_null("!!~ups_pk_error_list!!"))
		update !!#control_table!!
		set pk_errors = '!!~ups_pk_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update ups_proctables
	set processed = True
	where table_name = '!!@table_name!!';

	-- !x! execute script qa_all_pkloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)
-- !x! endif


-- !x! END SCRIPT
--					QA_ALL_PKLOOP
-- ****************************************************************
-- ****************************************************************
--		Script QA_ALL_FKLOOP
-- ---------------------------------------------------------------

-- !x! BEGIN SCRIPT QA_ALL_FKLOOP with parameters (base_schema, staging, control_table)

-- !x! sub_empty ~ups_error_list

-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- !x! select_sub ups_toprocess
	-- !x! execute script fkqa_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, display_errors=!!@display_changes!!, error_list=+ups_error_list)
	-- !x! if(not is_null("!!~ups_error_list!!"))
		update !!#control_table!!
		set fk_errors = '!!~ups_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update ups_proctables
	set processed = True
	where table_name = '!!@table_name!!';
	-- !x! execute script qa_all_fkloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)
-- !x! endif

-- !x! END SCRIPT
-- #####################  End of QA_ALL  ###########################
-- #################################################################



-- ################################################################
--			Script UPDTPK_ONE
--
-- Updates primary keys in base table, based on new and older
-- values of PK columns in a staging table, using UPDATE
-- statements.  Displays data to be modified to the
-- user before any modifications are done.  Reports the changes
-- made to the console and optionally to a log file.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The table name--same for base and staging.
--		display_errors	: A value of 'Yes' or 'No' to indicate whether
--							any errors should be displayed in a GUI.
--		display_changes	: A value of 'Yes' or 'No' to indicate whether
--							or not the changes to be made to the
--							base table should be displayed in a GUI.
--
--	Global variables:
--		logfile			: The name of a log file to which update
--							messages will be written.  Optional.
--		log_sql			: A value of 'Yes' or 'No' indicating whether
--							the update and insert statements should
--							also be written to the logfile.  Optional.
--		log_changes		: A value of 'Yes' or 'No' indicating whether
--							the updated and inserted data should be
--							written to the logfile.  Optional.
--
-- Tables and views created or modified:
--		ups_pkqa_errors			: temporary table
--		ups_pkcollinfo			: temporary table
--		ups_pkupdates			: temporary table
--		ups_pkupdate_strings	: temporary view
--		ups_pkupdates			: temporary table
-- ===============================================================

-- !x! BEGIN SCRIPT UPDTPK_ONE with parameters (base_schema, staging, table, display_errors, display_changes)

-- !x! if(console_on)
	-- !x! console status "Primary key updates"
-- !x! endif


-- Validate inputs: base/staging schemas and table
-- !x! execute script validate_one with args (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Performing primary key updates on table !!#base_schema!!.!!#table!! from !!#staging!!.!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Performing primary key updates on table !!#base_schema!!.!!#table!! from !!#staging!!.!!#table!!"

-- Create a temp table to store the results of the PK update QA checks
drop table if exists ups_pkqa_errors cascade;
create temporary table ups_pkqa_errors (
	error_code varchar(40),
	error_description varchar(500)
);


-- Populate a (temporary) table with the names of the primary key columns of the base table.
-- Get the old and new primary key columns from staging table into various formats
-- to use later to construct SQL statement to select records in various ways for both updates and QA checks.
-- Include column lists, join expression, and where clause
drop table if exists ups_pkcol_info cascade;
select
	k.table_schema,
	k.table_name,
	k.column_name,
	cast('b.' || column_name as text) as base_aliased,
	cast('s.' || column_name as text) as staging_aliased,
	cast('s.' || column_name || ' as staging_' || column_name as text) as staging_aliased_prefix,
	cast('b.' || column_name || ' = s.' || column_name as text) as join_expr,
	cast('new_' || column_name as text) as newpk_col,
	cast('s.new_' || column_name as text) as newpk_col_aliased,
	cast('new_' || column_name || ' is null' as text) as newpk_col_empty,
	cast('new_' || column_name || ' is not null' as text) as newpk_col_not_empty,
	cast(column_name || ' = s.new_' || column_name as text) as assmt_expr,
	cast('b.' || column_name || ' = s.new_' || column_name as text) as join_expr_oldnew,
	cast('s.new_' || column_name || ' = b.new_' || column_name as text) as join_expr_new,
	k.ordinal_position
into temporary table ups_pkcol_info
from information_schema.table_constraints as tc
inner join information_schema.key_column_usage as k
	on tc.constraint_type = 'PRIMARY KEY'
	and tc.constraint_name = k.constraint_name
	and tc.constraint_catalog = k.constraint_catalog
	and tc.constraint_schema = k.constraint_schema
	and tc.table_schema = k.table_schema
	and tc.table_name = k.table_name
	and tc.constraint_name = k.constraint_name
where
	k.table_name = '!!#table!!'
	and k.table_schema = '!!#base_schema!!'
;


-- Run QA checks
-- !x! execute script UPDTPKQA_ONE with arguments(base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!#table!!, pkinfo_table=ups_pkcol_info, qaerror_table=ups_pkqa_errors, display_errors=!!#display_errors!!)


-- Run the PK update ONLY if QA check script returned no errors
-- !x! if(not hasrows(ups_pkqa_errors))
	-- !x! rm_sub ~updatestmt

	-- !x! sub ~do_updates Yes

	-- !x! if(sub_defined(logfile))
		-- !x! write "" to !!logfile!!
		-- !x! write "==================================================================" to !!logfile!!
		-- !x! write "!!$current_time!! -- Performing primary key update on table !!#base_schema!!.!!#table!!" to !!logfile!!
	-- !x! endif

	-- !x! if(console_on)
		-- !x! console status "Performing PK updates"
		-- !x! console progress 0
	-- !x! endif

	-- !x! write "Performing primary key update on table !!#base_schema!!.!!#table!!"

	-- Create strings necessary to construct SQL to perform the updates
	drop view if exists ups_pkupdate_strings cascade;
	create temporary view ups_pkupdate_strings as
	select
		string_agg(base_aliased, ', ' order by ordinal_position) as oldpk_cols,
		string_agg(newpk_col, ', ' order by ordinal_position) as newpk_cols,
		string_agg(join_expr, ' and ' order by ordinal_position) as joinexpr,
		string_agg(newpk_col_not_empty, ' and ' order by ordinal_position) as all_newpk_col_not_empty,
		string_agg(assmt_expr, ', ' order by ordinal_position) as assmt_expr
	from ups_pkcol_info
	group by table_schema, table_name
	;
	-- !x! select_sub ups_pkupdate_strings

	-- Create a FROM clause for an inner join between base and staging
	-- tables on the primary key column(s).
	-- !x! sub ~fromclause FROM !!#base_schema!!.!!#table!! as b INNER JOIN !!#staging!!.!!#table!! as s ON !!@joinexpr!!

	-- Create a WHERE clause for the rows to include in the selection (only those having new PK columns populated in the staging table)
	-- !x! sub ~whereclause WHERE !!@all_newpk_col_not_empty!!

	-- Select all matches for PK update into temp table
	drop table if exists ups_pkupdates cascade;
	select
		!!@oldpk_cols!!,
		!!@newpk_cols!!
	into temporary table ups_pkupdates
	!!~fromclause!!
	!!~whereclause!!
	;

	-- Prompt user to examine matching data and commit, don't commit, or quit.
	-- !x! if(hasrows(ups_pkupdates))
		-- !x! if(is_true(!!#display_changes!!))
			-- !x! prompt ask "Do you want to make these changes to primary key values for table !!#table!!?" sub ~do_updates display ups_pkupdates
		-- !x! endif
		-- !x! if(is_true(!!~do_updates!!))

			-- Create an UPDATE statement to update PK columns of the base table with
			-- "new" PK columns from the staging table.  No semicolon terminating generated SQL.
			-- !x! sub ~updatestmt UPDATE !!#base_schema!!.!!#table!! as b SET !!@assmt_expr!! FROM !!#staging!!.!!#table!! as s WHERE !!@joinexpr!! and !!@all_newpk_col_not_empty!!

			-- !x! write "Updating !!#base_schema!!.!!#table!!"
			-- !x! if(sub_defined(logfile))
				-- !x! write "" to !!logfile!!
				-- !x! if(sub_defined(log_sql))
				-- !x! andif(is_true(!!log_sql!!))
					-- !x! write "UPDATE statement for !!#base_schema!!.!!#table!!:" to !!logfile!!
					-- !x! write [!!~updatestmt!!;] to !!logfile!!
				-- !x! endif
				-- !x! if(sub_defined(log_changes))
				-- !x! andif(is_true(!!log_changes!!))
					-- !x! write "Updates:" to !!logfile!!
					-- !x! export ups_pkupdates append to !!logfile!! as txt
				-- !x! endif
				-- !x! write "" to !!logfile!!
			-- !x! endif
			!!~updatestmt!!;
			-- !x! if(sub_defined(logfile))
				-- !x! write "!!$last_rowcount!! rows of !!#base_schema!!.!!#table!! updated." to !!logfile!!
			-- !x! endif
			-- !x! write "    !!$last_rowcount!! rows updated."
		-- !x! endif
	-- !x! else
		--!x! write "No primary key updates specified for existing records in !!#base_schema!!.!!#table!!"
	-- !x! endif
-- !x! endif


-- !x! END SCRIPT
-- ###################  End of UPDTPK_ONE  ########################
-- ################################################################


-- ################################################################
--			Script UPDTPKQA_ONE
--
-- Performs QA checks on requested primary key updates to a table,
-- based on old and new values of the table's primary key columns
-- in a staging table.
--
-- Input parameters:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The table name--same for base and staging.
--		pkinfo_table	: The name of a temporary table to be passed by
--							the caller that contains information about the table PK,
--							including strings to be used in constructing
--							SQL for checks
--		qaerror_table  	: The name of a temporary table to
--							store any errors found by QA checks.
--		display_errors	: A value of 'Yes' or 'No' to indicate whether
--							any errors should be displayed in a GUI.
--	Output parameters:
--		error_list		: The name of the variable to receive FILL IN.
--
--	Global variables:
--		logfile			: The name of a log file to which update
--							messages will be written.  Optional.
--		log_sql			: A value of 'Yes' or 'No' indicating whether
--							the update and insert statements should
--							also be written to the logfile.  Optional.
--							Currently only writes SQL for foreign key checks
--							(final check) to log.
--		log_errors		: A value of 'Yes' or 'No' to indicate whether
--							errors are written to the logfile. Optional.
--
-- Tables and views created or modified:
--		ups_missing_pk_cols			: temporary table
--		ups_pkqa_str_lib			: tempoarary table
--		ups_any_pk_cols				: temporary table
--		ups_empty_pk_cols			: temporary table
--		ups_empty_pk_cols_rwcnt		: temporary view
--		ups_old_pks_wc				: temporary table
--		ups_invalid_old_pks			: temporary table
--		ups_invld_pk_rwcnt			: temporary view
--		ups_existing_new_pks		: temporary table
--		ups_exst_nwpk_rwcnt			: temporary view
--		ups_pk_mapping_conflict		: temporary table
--		ups_map_conf_rwcnt			: temporary view
--		ups_pk_duplicate_keys		: temporary table
--		ups_dup_key_rwcnt			: temporary view
--		ups_fkcol_refs				: temporary table
--		ups_pkcol_deps				: temporary table
--		ups_pkfk_ctrl				: temporary table
-- ===============================================================

-- !x! BEGIN SCRIPT UPDTPKQA_ONE with parameters (base_schema, staging, table, pkinfo_table, qaerror_table, display_errors)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- QA checks for primary key updates on table !!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting QA checks on table !!#staging!!.!!#table!! for primary key updates to table !!#base_schema!!.!!#table!!"

-- Initialize the status and progress bars if the console is running.
-- !x! if(console_on)
	-- !x! console status "QA checks for PK updates on !!#base_schema!!.!!#table!!"
-- !x! endif


-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
-- Check 1 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
-- No primary key constraint on base table
-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
-- !x! if(not hasrows(!!#pkinfo_table!!))

	-- !x! sub ~error_description No primary key constraint on base table !!#base_schema!!.!!#table!!
	-- !x! write "    !!~error_description!!"
	-- !x! if(sub_defined(logfile))
		-- !x! write "" to !!logfile!!
		-- !x! write "!!~error_description!!" to !!logfile!!
	-- !x! endif
	insert into !!#qaerror_table!! (error_code, error_description)
	values ('No PK on base table', '!!~error_description!!')
	;

-- No other QA checks are conducted if this check fails:
-- Remaining QA checks are conducted ONLY if base table has PK
-- !x! else

	-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	-- Check 2 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	-- A "new" PK column exists in staging table for every PK column of base table
	-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

	-- Find any MISSING PK columns in staging table
	drop table if exists ups_missing_pk_cols cascade;
	select
		string_agg(newpk_col, ', ' order by ordinal_position) as missing_newpk_cols
	into temporary table ups_missing_pk_cols
	from
		--Base table PK columns, with expected name in staging table ("new_" prepended to column name)
		!!#pkinfo_table!! as pk
		--Staging table columns
		left join
			(
			select table_name, column_name
			from information_schema.columns
			where
				table_schema = '!!#staging!!'
			) as stag on pk.table_name=stag.table_name and pk.newpk_col=stag.column_name
	where
		stag.column_name is null
	having count(*)>0
	;

	-- !x! if(hasrows(ups_missing_pk_cols))

		-- !x! subdata ~error_info ups_missing_pk_cols

		-- !x! sub ~error_description New primary key column(s) missing from staging table: !!~error_info!!

		-- !x! write "    !!~error_description!!"
		-- !x! if(sub_defined(logfile))
			-- !x! write "" to !!logfile!!
			-- !x! write "!!~error_description!!" to !!logfile!!
		-- !x! endif
		insert into !!#qaerror_table!! (error_code, error_description)
		values ('Missing new PK column(s)', '!!~error_description!!')
		;

	-- No other QA checks are conducted if this check fails:
	-- Remaining QA checks are all conducted ONLY if all expected "new PK" columns exist in staging table
	-- !x! else

		-- Library of aggregated strings used to construct SQL for the remaining checks

		-- Just base table
		-- !x! sub ~base_table !!#base_schema!!.!!#table!!

		-- Just staging table
		-- !x! sub ~staging_table !!#staging!!.!!#table!!

		drop table if exists ups_pkqa_str_lib;
		select
			string_agg(column_name, ', ' order by ordinal_position) as old_pkcol,
			string_agg(staging_aliased, ', ' order by ordinal_position) as old_pkcol_aliased,
			string_agg(staging_aliased_prefix, ', ' order by ordinal_position) as old_pkcol_aliased_prefix,
			string_agg(newpk_col, ', ' order by ordinal_position) as new_pkcol,
			string_agg(newpk_col_aliased, ', ' order by ordinal_position) as new_pkcol_aliased,
			string_agg(join_expr, ' and ' order by ordinal_position) as joincond_origorig,
			string_agg(join_expr_oldnew, ' and ' order by ordinal_position) as joincond_oldnew,
			string_agg(join_expr_new, ' and ' order by ordinal_position) as joincond_newnew,
			string_agg(newpk_col_not_empty, ' or ' order by ordinal_position) as any_newpk_col_not_empty,
			string_agg(newpk_col_not_empty, ' and ' order by ordinal_position) as all_newpk_col_not_empty,
			string_agg(newpk_col_empty, ' or ' order by ordinal_position) as any_newpk_col_empty,
			string_agg(newpk_col_empty, ' and ' order by ordinal_position) as all_newpk_col_empty
		into temporary table ups_pkqa_str_lib
		from !!#pkinfo_table!!
		;
		-- !x! select_sub ups_pkqa_str_lib



		-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
		-- Check 3 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
		-- There are any rows with PK updates specified.
		-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

		-- Find any populated new PK columns in staging table
		drop table if exists ups_any_pk_cols cascade;
		select * into temporary table ups_any_pk_cols
		from !!~staging_table!!
		where !!@any_newpk_col_not_empty!!
		;
		-- !x! if(not hasrows(ups_any_pk_cols))
			-- !x! sub ~error_description No primary key updates specified in !!#staging!!.!!#table!!
			-- !x! write "    !!~error_description!!"
			-- !x! if(sub_defined(logfile))
				-- !x! write "" to !!logfile!!
				-- !x! write "!!~error_description!!" to !!logfile!!
			-- !x! endif
			insert into !!#qaerror_table!! (error_code, error_description)
			values ('No PK updates specified in staging table', '!!~error_description!!')
			;
		-- No other QA checks are conducted if this check fails
		-- !x! else

			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 4 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Where any "new" PK column is populated in the staging table, they are all populated.
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- Construct SQL statement looking for any NULLs in "new" PK columns in rows where any PK columns are populated
			-- Find any EMPTY PK columns in staging table
			drop table if exists ups_empty_pk_cols cascade;
			select
				!!@old_pkcol!!,
				!!@new_pkcol!!
			into temporary table ups_empty_pk_cols
			from
				!!~staging_table!!
			where
				not (!!@all_newpk_col_empty!!)
				and (!!@any_newpk_col_empty!!)
			;

			-- !x! if(hasrows(ups_empty_pk_cols))
				drop view if exists ups_empty_pk_cols_rwcnt cascade;
				create temporary view ups_empty_pk_cols_rwcnt as
				select count(*) as rwcnt
				from ups_empty_pk_cols
				;
				-- !x! subdata ~rowcount ups_empty_pk_cols_rwcnt
				-- !x! sub ~error_description Missing values in new PK columns in !!#staging!!.!!#table!!: !!~rowcount!! row(s)
				-- !x! write "    !!~error_description!!"
				insert into !!#qaerror_table!! (error_code, error_description)
				values ('Incomplete mapping', '!!~error_description!!')
				;
				-- !x! if(sub_defined(logfile))
					-- !x! write "" to !!logfile!!
					-- !x! write "!!~error_description!!" to !!logfile!!
					-- !x! if(sub_defined(log_errors))
					-- !x! andif(is_true(!!log_errors!!))
						-- !x! export ups_empty_pk_cols append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Missing values in new PK columns in !!#staging!!.!!#table!!" display ups_empty_pk_cols
				-- !x! endif
			-- !x! endif

			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 5 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Where any "new" PK column is populated in the staging table, the value of the original PK for that row is valid
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- New PK col in staging table are not empty
			drop table if exists ups_old_pks_wc cascade;
			select base_aliased
			into temporary table ups_old_pks_wc
			from !!#pkinfo_table!!
			order by ordinal_position
			limit 1;
			-- !x! subdata ~old_pk_firstcol ups_old_pks_wc

			drop table if exists ups_invalid_old_pks cascade;
			select
				!!@old_pkcol_aliased!!,
				!!@new_pkcol!!
			into temporary table ups_invalid_old_pks
			from !!~staging_table!! as s
					left join !!~base_table!! as b on !!@joincond_origorig!!
			where !!@all_newpk_col_not_empty!! and !!~old_pk_firstcol!! is null
			;

			-- !x! if(hasrows(ups_invalid_old_pks))
				drop view if exists ups_invld_pk_rwcnt cascade;
				create temporary view ups_invld_pk_rwcnt as
				select count(*) as rwcnt
				from ups_invalid_old_pks
				;
				-- !x! subdata ~rowcount ups_invld_pk_rwcnt
				-- !x! sub ~error_description Invalid original PK in !!#staging!!.!!#table!!: !!~rowcount!! row(s)
				-- !x! write "    !!~error_description!!"
				insert into !!#qaerror_table!! (error_code, error_description)
				values ('Invalid old PK value', '!!~error_description!!')
				;
				-- !x! if(sub_defined(logfile))
					-- !x! write "" to !!logfile!!
					-- !x! write "!!~error_description!!" to !!logfile!!
					-- !x! if(sub_defined(log_errors))
					-- !x! andif(is_true(!!log_errors!!))
						-- !x! export ups_invalid_old_pks append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Invalid original PK in !!#staging!!.!!#table!!" display ups_invalid_old_pks
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 6 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- None of the "new" PK values already exist in the base table
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			drop table if exists ups_existing_new_pks cascade;
			select
				!!@old_pkcol_aliased_prefix!!,
				!!@new_pkcol!!,
				b.*
			into temporary table ups_existing_new_pks
			from !!~staging_table!! as s
					inner join !!~base_table!! as b on !!@joincond_oldnew!!
			;

			-- !x! if(hasrows(ups_existing_new_pks))
				drop view if exists ups_exst_nwpk_rwcnt cascade;
				create temporary view ups_exst_nwpk_rwcnt as
				select count(*) as rwcnt
				from ups_existing_new_pks
				;
				-- !x! subdata ~rowcount ups_exst_nwpk_rwcnt
				-- !x! sub ~error_description New PK already exists in !!#base_schema!!.!!#table!!: !!~rowcount!! row(s)
				-- !x! write "    !!~error_description!!"
				insert into !!#qaerror_table!! (error_code, error_description)
				values ('Existing new PK value', '!!~error_description!!')
				;
				-- !x! if(sub_defined(logfile))
					-- !x! write "" to !!logfile!!
					-- !x! write "!!~error_description!!" to !!logfile!!
					-- !x! if(sub_defined(log_errors))
					-- !x! andif(is_true(!!log_errors!!))
						-- !x! export ups_existing_new_pks append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "New PK already exists in !!#base_schema!!.!!#table!!" display ups_existing_new_pks
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 7 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- No two (or more) original PK values map to same new PK value
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			drop table if exists ups_pk_mapping_conflict cascade;
			select
				!!@old_pkcol_aliased!!,
				!!@new_pkcol_aliased!!
			into temporary table ups_pk_mapping_conflict
			from !!~staging_table!! as s
				inner join
				(
				select
					!!@new_pkcol!!
				from
				(select distinct !!@old_pkcol!!, !!@new_pkcol!! from !!~staging_table!! where !!@all_newpk_col_not_empty!!) as a
				group by
					!!@new_pkcol!!
				having count(*) >1
				) as b on !!@joincond_newnew!!
			;

			-- !x! if(hasrows(ups_pk_mapping_conflict))
				drop view if exists ups_map_conf_rwcnt cascade;
				create temporary view ups_map_conf_rwcnt as
				select count(*) as rwcnt
				from ups_pk_mapping_conflict
				;
				-- !x! subdata ~rowcount ups_map_conf_rwcnt
				-- !x! sub ~error_description Multiple original PKs mapped to same new PK in !!#staging!!.!!#table!!: !!~rowcount!! row(s)
				-- !x! write "    !!~error_description!!"
				insert into !!#qaerror_table!! (error_code, error_description)
				values ('Mapping conflict', '!!~error_description!!')
				;
				-- !x! if(sub_defined(logfile))
					-- !x! write "" to !!logfile!!
					-- !x! write "!!~error_description!!" to !!logfile!!
					-- !x! if(sub_defined(log_errors))
					-- !x! andif(is_true(!!log_errors!!))
						-- !x! export ups_pk_mapping_conflict append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Multiple original PKs mapped to same new PK in !!#staging!!.!!#table!!" display ups_pk_mapping_conflict
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 8 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- No single original PK value maps to multiple new PK values
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			drop table if exists ups_pk_duplicate_keys cascade;
			select
				!!@old_pkcol_aliased!!,
				!!@new_pkcol_aliased!!
			into temporary table ups_pk_duplicate_keys
			from !!~staging_table!! as s
				inner join
				(
				select
					!!@old_pkcol!!
				from
				(select distinct !!@old_pkcol!!, !!@new_pkcol!! from !!~staging_table!! where !!@all_newpk_col_not_empty!!) as a
				group by
					!!@old_pkcol!!
				having count(*)>1
				) as b on !!@joincond_origorig!!
			;

			-- !x! if(hasrows(ups_pk_duplicate_keys))
				drop view if exists ups_dup_key_rwcnt cascade;
				create temporary view ups_dup_key_rwcnt as
				select count(*) as rwcnt
				from ups_pk_duplicate_keys
				;
				-- !x! subdata ~rowcount ups_dup_key_rwcnt
				-- !x! sub ~error_description Original PK mapped to multiple new PKs in !!#staging!!.!!#table!!: !!~rowcount!! row(s)
				-- !x! write "    !!~error_description!!"
				insert into !!#qaerror_table!! (error_code, error_description)
				values ('Duplicate keys', '!!~error_description!!')
				;
				-- !x! if(sub_defined(logfile))
					-- !x! write "" to !!logfile!!
					-- !x! write "!!~error_description!!" to !!logfile!!
					-- !x! if(sub_defined(log_errors))
					-- !x! andif(is_true(!!log_errors!!))
						-- !x! export ups_pk_duplicate_keys append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Original PK mapped to multiple new PKs in !!#staging!!.!!#table!!" display ups_pk_duplicate_keys
				-- !x! endif
			-- !x! endif

			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 9 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- If any of the PK columns reference a parent table, all the "new" values of that column are valid
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- Get ALL column references for the base table
			drop table if exists ups_fkcol_refs cascade;
			select
				fk_constraint,
				staging_schema,
				fkinf.table_schema,
				fkinf.table_name,
				att1.attname as column_name,
				fkinf.column_id,
				ns2.nspname as parent_schema,
				cls2.relname as parent_table,
				att2.attname as parent_column,
				fkinf.parent_column_id
			into temporary table ups_fkcol_refs
			from
			(
				select
					cons.conname as fk_constraint,
					'!!#staging!!' as staging_schema,
					ns1.nspname as table_schema,
					cls1.relname as table_name,
					cons.conrelid as table_id,
					unnest(cons.conkey) as column_id,
					cons.confrelid as parent_table_id,
					unnest(cons.confkey) as parent_column_id
				from
					pg_constraint as cons
					inner join pg_class as cls1 on cls1.oid=cons.conrelid
					inner join pg_namespace ns1 on ns1.oid = cls1.relnamespace

				where
					cons.contype='f'
					and ns1.nspname  = '!!#base_schema!!'
					and cls1.relname = '!!#table!!'
			) as fkinf
			inner join pg_class as cls2 on cls2.oid=fkinf.parent_table_id
			inner join pg_namespace ns2 on ns2.oid = cls2.relnamespace
			inner join pg_attribute att1 on att1.attrelid = fkinf.table_id and att1.attnum = fkinf.column_id
			inner join pg_attribute att2 on att2.attrelid = fkinf.parent_table_id and att2.attnum = fkinf.parent_column_id
			;

			-- Narrow the list down to ONLY dependencies that affect PK columns
			-- Include not just the PK columns themselves, but ALL columns included in FKs
			-- that include ANY PK columns (probably rare/unlikely that a non-PK column would be
			-- part of the same foreign key as a PK column, but this ensures that ALL columns of the FK
			-- are included, whether or not the column is part of the PK)
			drop table if exists ups_pkcol_deps cascade;
			select
				refs.*
			into temporary table ups_pkcol_deps
			from ups_fkcol_refs as refs
			inner join
			--Distinct list of FK constraints on the table that include ANY PK columns
			(
			select distinct
				fk_constraint, r.table_schema, r.table_name
			from
				ups_fkcol_refs as r
				inner join ups_pkcol_info as p on r.table_schema=p.table_schema and r.table_name=p.table_name and r.column_name=p.column_name
			) as const on refs.fk_constraint=const.fk_constraint and refs.table_schema=const.table_schema and refs.table_name=const.table_name
			;

			-- Create a control table for looping to check each fk
			-- Include (for later use) some of the constructed strings that apply to the entire PK (not
			-- just the FK being checked)
			drop table if exists ups_pkfk_ctrl cascade;
			select
				fk_constraint,
				staging_schema, table_schema, table_name, parent_schema, parent_table,
				min(parent_column) as any_referenced_column,
				'!!@old_pkcol_aliased!!' as old_pkcol_aliased,
				'!!@new_pkcol!!' as new_pkcol,
				'!!@all_newpk_col_not_empty!!' as all_newpk_col_not_empty,
				False::boolean as processed
			into temporary table ups_pkfk_ctrl
			from ups_pkcol_deps
			group by
				fk_constraint,
				staging_schema, table_schema, table_name, parent_schema, parent_table
			;

			-- Create a view to select one constraint to process.
			drop view if exists ups_next_fk cascade;
			create temporary view ups_next_fk as
			select *
			from ups_pkfk_ctrl
			where not processed
			limit 1
			;

			--Process all constraints: check every foreign key
			--!x! execute script updtpkqa_one_innerloop with (qaerror_table=!!#qaerror_table!!, display_errors=!!#display_errors!!)
		-- !x! endif
	-- !x! endif
-- !x! endif
-- !x! END SCRIPT
-- #####################  UPDTPKQA_ONE  ###########################
-- ################################################################
--			Script UPDTPKQA_ONE_INNERLOOP
-- ----------------------------------------------------------------
-- !x! BEGIN SCRIPT UPDTPKQA_ONE_INNERLOOP with parameters(qaerror_table, display_errors)
-- !x! if(hasrows(ups_next_fk))

	-- !x! select_sub ups_next_fk

	-- Compile FK info for the selected constraint
	drop table if exists ups_sel_fk_cols cascade;
	select
		staging_schema, fk_constraint, table_schema, table_name, parent_schema,
		parent_table,
		string_agg(parent_column, ', ' order by column_id) as referenced_cols,
		string_agg('s.new_' || column_name || '=' || 'b.' || parent_column, ' and ' order by column_id) as join_condition
	into temporary table ups_sel_fk_cols
	from ups_pkcol_deps
	where fk_constraint='!!@fk_constraint!!'
	group by
		staging_schema, fk_constraint, table_schema, table_name, parent_schema,
		parent_table
	;
	-- !x! select_sub ups_sel_fk_cols

	-- Construct SQL to check the selected FK
	-- !x! sub ~select_stmt select  !!@old_pkcol_aliased!!, !!@new_pkcol!! into temporary table ups_pk_fk_check from !!@staging_schema!!.!!@table_name!! as s
	-- !x! sub ~join_stmt left join !!@parent_schema!!.!!@parent_table!! as b on !!@join_condition!!
	-- !x! sub ~where_clause where !!@all_newpk_col_not_empty!! and b.!!@any_referenced_column!! is null

	-- !x! sub ~fk_check drop table if exists ups_pk_fk_check cascade;
	-- !x! sub_append ~fk_check !!~select_stmt!!
	-- !x! sub_append ~fk_check !!~join_stmt!!
	-- !x! sub_append ~fk_check !!~where_clause!!

	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "" to !!logfile!!
		-- !x! write "SQL for checking foreign key !!@fk_constraint!! for PK update to !!@table_schema!!.!!@table_name!!:" to !!logfile!!
		-- !x! write [!!~fk_check!!;] to !!logfile!!
	-- !x! endif

	-- Run the check
	!!~fk_check!!;


	-- !x! if(hasrows(ups_pk_fk_check))

		drop view if exists ups_pk_fk_check_rwcnt cascade;
		create temporary view ups_pk_fk_check_rwcnt as
		select count(*) as rwcnt
		from ups_pk_fk_check
		;

		-- !x! subdata ~rowcount ups_pk_fk_check_rwcnt
		-- !x! sub ~error_description !!@parent_schema!!.!!@parent_table!! (!!@referenced_cols!!): !!~rowcount!! row(s)

		-- !x! write "    Violation of foreign key !!@fk_constraint!! in new primary key columns in !!@staging_schema!!.!!@table_name!! referencing !!@parent_schema!!.!!@parent_table!!: !!~rowcount!! row(s)"

		drop view if exists ups_pk_fk_qa_error cascade;
		create temporary view ups_pk_fk_qa_error as
		select
			error_code, error_description
		from !!#qaerror_table!!
		where error_code='Invalid reference to parent table(s)';
		-- !x! if(hasrows(ups_pk_fk_qa_error))
			update !!#qaerror_table!!
			set error_description=error_description || '; !!~error_description!!'
			where error_code='Invalid reference to parent table(s)';

		-- !x! else
			insert into !!#qaerror_table!! (error_code, error_description)
			values ('Invalid reference to parent table(s)', '!!~error_description!!')
			;
		-- !x! endif


		-- !x! if(sub_defined(logfile))
			-- !x! write "" to !!logfile!!
			-- !x! write "Violation of foreign key !!@fk_constraint!! in new primary key columns in !!@staging_schema!!.!!@table_name!! referencing !!@parent_schema!!.!!@parent_table!!: !!~rowcount!! row(s)" to !!logfile!!
			-- !x! if(sub_defined(log_errors))
			-- !x! andif(is_true(!!log_errors!!))
				-- !x! export ups_pk_fk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Violation of foreign key !!@fk_constraint!! in  new primary key columns in !!@staging_schema!!.!!@table_name!! referencing !!@parent_schema!!.!!@parent_table!!" display ups_pk_fk_check
		-- !x! endif

	-- !x! endif

	-- Mark constraint as processed
	update ups_pkfk_ctrl
	set processed=True
	where fk_constraint='!!@fk_constraint!!';

	--LOOP
	-- !x! execute script updtpkqa_one_innerloop with (qaerror_table=!!#qaerror_table!!, display_errors=!!#display_errors!!)

-- !x! endif

-- !x! END SCRIPT
-- ####################  End of UPDTPKQA_ONE  ########################
-- ###################################################################
