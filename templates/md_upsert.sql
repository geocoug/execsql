-- md_upsert.sql
--
-- PURPOSE
--	A set of execsql scripts to check data in a staging table, or
--	a set of staging tables, and then update and insert rows of a base table
--	or base tables from the staging table(s) of the same name.
--
--	This script contains code specific to MariaDB/MySQL.
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
--			PKQA_ONE		: Perform primary key checks on one staging table.
--			FKQA_ONE		: Perform foreign key checks on one staging table.
--			UPSERT_ONE		: Load data from one staging table.
--		This file contains other scripts that are intended to be used
--		only by one of the scripts listed above, and not called
--		directly by the user.
--	2. These scripts query the information schema to obtain
--		the information needed to perform the checks and changes.
--	3. These scripts create and delete tables in the active database.
--		Because MariaDB/MySQL does not (currently) support temporary
--		views, or views on temporary tables, most of the views and
--		tables that are created are potentially visible to other
--		database operations.  See the header notes for invdividual
--		execsql scripts for names of the tables and views used.
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
--	Elizabeth Shea (ES)
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
--	2019-02-03	Edits from 2019-02-03 pg version for MariaDB/MySQL
--				compatibility.  RDN.
--	2019-02-05	Edits for MariaDB: conversion of staging schema to
--				a staging prefix.  RDN.
--	2019-02-14	Added where clause conditions for schema name equal
--				to the current database to prevent multiple null
--				checks when there are multiple databases with the
--				same table and column names.  RDN.
--	2019-02-15	Modified all internal table and view names to use a
--				prefix of "ups_".  RDN.
--	2019-02-16	Modified to include in the list of ordered tables all
--				tables that are not part of any foreign key relationship.
--				Modified to use an 'exclude_null_checks' setting.  RDN.
--	2019-02-17	Corrected the check to display changes in UPSERT_ONE.  RDN.
--	2019-02-21	Modified QA_ALL_NULLLOOP and QA_ALL_FKLOOP to use local
--				variables and the new outer scope referent prefix for
--				the return values.  RDN.
--	2019-03-02	Changed to use 'autocommit with commit'.  Modified
--				recursive CTE to order dependencies to protect against
--				multi-table cycles.  RDN.
--	2019-03-02	Modified to show the number of rows with each invalid
--				foreign key value, in both the GUI display and the
--				logfile.  RDN.
--	2019-03-03	Added the 'do_commit' argument to LOAD_STAGING.  RDN.
--	2019-03-09	Added FKQA_ONE with related changes from SS version
--				by ES.  Modified addition of solo tables to the set
--				of ordered tables per ES revisions.  Other fixes
--				following ES changes to pg_upsert.sql.  Revised
--				recursive CTE for FK ordering to eliminate
--				hangs on referential cycles of >2 tables.  RDN.
--	2019-03-15	Added VALIDATE_ONE and calls to it.  RDN.
--	2019-03-24	Added constraints to PKQA_ONE to limit to the
--				current database.  RDN.
--	2019-06-08	Began addition of PK updating scripts.  Complete
--				through QA check 8. RDN.
--	2019-06-16	Nominally complete revisions of PK updating scripts. RDN.
--	2019-06-23	Completed debugging of PK updating scripts.  RDN.
--	2020-04-28	Explicitly rolled back the changes if 'do_commit' = "No".  RDN.
--	2020-05-09	Moved the assignment of 'upsert_progress_denom' out of the
--				'update_console_qa' script.  RDN.
-- ==================================================================



-- ################################################################
--			Script VALIDATE_ONE
-- ===============================================================
--
-- Utility script to validate both base and staging versions of one table.
-- Halts script processing if either of the tables are not present.
--
-- Input parameters:
--		stage_pfx		: The prefix for staging tables.
--		table_name  	: The name of the table.
--		script          : The name of the script in which the
--							schemas and table were referenced
--							(for error reporting).
--		script_line		: The script line in which they were referenced
--							(for error reporting).
-- ===============================================================
-- !x! BEGIN SCRIPT VALIDATE_ONE with parameters (stage_pfx, table, script, script_line)

-- Initialize the strings used to compile error information
-- !x! sub_empty ~err_info
-- !x! sub_empty ~error_list


-- !x! if(table_exists(ups_invl_table))
	drop table if exists ups_invl_table cascade;
-- !x! endif
create table ups_invl_table
select
	group_concat(concat(tt.table_name, ' (', tt.schema_type, ')') order by tt.table_name separator ';') as schema_table
from
	(
	select
		'base' as schema_type,
		'!!#table!!' as table_name
	union
	select

		'staging' as schema_type,
		'!!#stage_pfx!!!!#table!!' as table_name
	) as tt
	left join information_schema.tables as iss on tt.table_name=iss.table_name
where
	iss.table_name is null
	and iss.table_schema = '!!$DB_NAME!!'
having count(*) > 0
;

-- !x! if(hasrows(ups_invl_table))
	-- !x! subdata ~err_info ups_invl_table
	-- !x! sub ~error_list Non-existent table: !!~err_info!!
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

	-- !x! sub_append ~error_message Script: !!#script!!; Line: !!#script_line!!  -- !x! sub_append ~error_message !!~error_list!!  -- !x! halt message "!!~error_message!!"

-- !x! endif

-- !x! if(table_exists(ups_invl_table))
	drop table if exists ups_invl_table cascade;
-- !x! endif

-- !x! END SCRIPT
-- ####################  End of VALIDATE_ONE  #####################
-- ################################################################



-- ################################################################
--			Script VALIDATE_CONTROL
-- ===============================================================
--
-- Utility script to validate contents of control table against about
--	base and staging schema
--
-- Required input arguments:
--		stage_pfx		: The name of the staging schema.
--		control_table  	: The name of a temporary table as created by the
--							script STAGED_TO_LOAD.
--		script          : The name of the script in which the
--							schemas and control table were referenced
--							(for error reporting).
--		script_line		: The script line in which they were referenced
--							(for error reporting).
-- ===============================================================
-- !x! BEGIN SCRIPT VALIDATE_CONTROL with parameters (stage_pfx, control_table, script, script_line)

-- Initialize the strings used to compile error information
-- !x! sub_empty ~err_info
-- !x! sub_empty ~error_list

-- !x! if(table_exists(ups_validate_control))
	drop table if exists ups_validate_control cascade;
-- !x! endif
create table ups_validate_control
select
	table_name,
	False as base_exists,
	False as staging_exists
from !!#control_table!!
;

-- Update the validation table
update ups_validate_control as vc, information_schema.tables as bt
set vc.base_exists = True
where
	vc.table_name=bt.table_name
	and bt.table_type='BASE TABLE'
	and bt.table_schema = '!!$DB_NAME!!'
;

update ups_validate_control as vc, information_schema.tables as st
set vc.staging_exists = True
where
	st.table_name= concat('!!#stage_pfx!!', vc.table_name)
	and st.table_type='BASE TABLE'
	and st.table_schema = '!!$DB_NAME!!'
;

-- !x! if(table_exists(ups_ctrl_invl_table))
	drop table if exists ups_ctrl_invl_table cascade;
-- !x! endif
create table ups_ctrl_invl_table
select
		group_concat(schema_table order by it.schema_table separator '; ') as schema_table
from
		(
		select table_name as schema_table
		from ups_validate_control
		where not base_exists
		union
		select concat('!!#stage_pfx!!', table_name) as schema_table
		from ups_validate_control
		where not staging_exists
		) as it
having count(*) > 0
;

-- Any table is invalid
-- !x! if(hasrows(ups_ctrl_invl_table))
	-- !x! subdata ~err_info ups_validate_control
	-- !x! sub ~error_list Non-existent table(s): !!~err_info!!
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

-- !x! if(table_exists(ups_validate_control))
	drop table if exists ups_validate_control cascade;
-- !x! endif
-- !x! if(table_exists(ups_ctrl_invl_table))
	drop table if exists ups_ctrl_invl_table cascade;
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
--		control_table	: The name of the table to be created.
--							In MariaDB/MySQL, this must *not* be a
--							temporary table.
--		table_list		: A string of comma-separated table names,
--							identifying the staging tables to be
--							checked or loaded.
--
-- Columns in the table created:
--		table_name		: The name of a base table that has a
--							corresponding table in a staging schema
--							containing data to be used to modify
--							the base table.
--		exclude_cols	: Contains a comma-separated list of columns
--							in the base table that are not to be
--							updated from the staging table.  This is
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

create table !!#control_table!! (
	table_name varchar(150) not null unique,
	exclude_cols varchar(255),
	exclude_null_checks varchar(255),
	display_changes varchar(3) not null default 'Yes',
	display_final varchar(3) not null default 'No',
	null_errors varchar(255),
	pk_errors varchar(255),
	fk_errors varchar(255),
	rows_updated integer,
	rows_inserted integer,
	constraint ck_chgyn check (display_changes in ('Yes', 'No')),
	constraint ck_finalyn check (display_final in ('Yes', 'No'))
);

insert into !!#control_table!!
	(table_name)
with recursive itemtable as (
		select
			trim(substring_index(data, ',', 1)) as table_name,
			right(data, length(data) - locate(',', data, 1)) as data
		from (select '!!#table_list!!' as data) as input
		union
		select
			trim(substring_index(data, ',', 1)) as table_name,
			right(data, length(data) - locate(',', data, 1)) as data
		from itemtable
	)
select table_name as item
from itemtable;


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
-- QA checks, loading is not attempted.  If the loading step is
-- carried out, it is done within a transaction.
--
-- The "null_errors" and "fk_errors" columns of the control table
-- will be updated to identify any errors that occur, so that this
-- information is available to the caller.
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
--		stage_pfg		: The prefix on staging tables that distinguish
--							them from the corresponding based table
--							(e.g., "stg_").
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
--		ups_qa_fails				: view
-- ===============================================================

-- !x! BEGIN SCRIPT LOAD_STAGING with parameters (stage_pfx, control_table, do_commit)

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


-- Run null checks, PK checks, and FK checks.
-- !x! execute script QA_ALL with arguments (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)
-- !x! if(view_exists(ups_qa_fails))
	drop view if exists ups_qa_fails cascade;
-- !x! endif
create view ups_qa_fails as
select *
from !!#control_table!!
where null_errors is not null or pk_errors is not null or fk_errors is not null;
-- !x! if(not hasrows(ups_qa_fails))
	-- !x! sub ~preautocommit !!$autocommit_state!!
	-- !x! autocommit off
	-- !x! execute script UPSERT_ALL with arguments (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)
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

-- Clean up.
drop view if exists ups_qa_fails cascade;

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
--		stage_pfx		: The name of the staging schema.
--		table			: The table name--same for base and staging.
-- Optional input arguments:
--		exclude_null_checks : A comma-separated list of singly-quoted
--								column names to be excluded from null checks.
--
--	Output parameters:
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
--		ups_nonnull_columns		: table
--		ups_next_column			: view
--		ups_null_error_list		: view
--		ups_qa_nonnull_col		: view
-- ===============================================================

-- !x! BEGIN SCRIPT NULLQA_ONE with parameters (stage_pfx, table, error_list)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Non-null QA checks on table !!#stage_pfx!!!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting non-null QA checks on table !!#stage_pfx!!!!#table!!"

-- Validate input table specifications.
-- !x! execute script validate_one with args (stage_pfx=!!#stage_pfx!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)

-- Initialize the return value to empty (no foreign key errors)
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
-- !x! if(table_exists(ups_nonnull_columns))
	drop table if exists ups_nonnull_columns cascade;
-- !x! endif
create table ups_nonnull_columns
select
	column_name,
	0 as null_rows,
	0 as processed
from
	information_schema.columns
where
	table_schema = '!!$DB_NAME!!'
	and table_name = '!!#table!!'
	and is_nullable = 'NO'
	and column_default is null
	!!~omitnull!!
	;

-- Create a view to select one column to process.
create or replace view ups_next_column as
select column_name
from ups_nonnull_columns
where processed = 0
limit 1;

-- Process all non-nullable columns.
-- !x! execute script nullqa_one_innerloop with (stage_pfx=!!#stage_pfx!!, table=!!#table!!)

-- Create the return value.
create or replace view ups_null_error_list as
select
	group_concat(concat(column_name, ' (', cast(null_rows as varchar(100)), ')') separator ', ') as null_errors
from
	ups_nonnull_columns
where
	coalesce(null_rows, 0) > 0;
-- !x! if(hasrows(ups_null_error_list))
	-- !x! subdata !!#error_list!! ups_null_error_list
-- !x! endif

-- Clean up.
drop view if exists ups_null_error_list;
drop view if exists ups_next_column cascade;
drop table if exists ups_nonnull_columns cascade;

-- !x! END SCRIPT
-- End of          NULLQA_ONE
-- ****************************************************************
-- ****************************************************************
--			Script NULLQA_ONE_INNERLOOP
-- ---------------------------------------------------------------
-- !x! BEGIN SCRIPT NULLQA_ONE_INNERLOOP with parameters (stage_pfx, table)

-- !x! if(hasrows(ups_next_column))
	-- !x! subdata ~column_name ups_next_column

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking column !!~column_name!!." to !!logfile!!
	-- !x! endif

	create or replace view ups_qa_nonnull_col as
	select nrows
	from (
		select count(*) as nrows
		from !!#stage_pfx!!!!#table!!
		where !!~column_name!! is null
		) as nullcount
	where nrows > 0
	limit 1;
	-- !x! if(hasrows(ups_qa_nonnull_col))
		-- !x! subdata ~nullrows ups_qa_nonnull_col
		-- !x! write "    Column !!~column_name!! has !!~nullrows!! nulls."
		-- !x! if(sub_defined(logfile))
			-- !x! write "    Column !!~column_name!! has !!~nullrows!! nulls." to !!logfile!!
		-- !x! endif
		update ups_nonnull_columns
		set null_rows = (select nrows from ups_qa_nonnull_col limit 1)
		where column_name = '!!~column_name!!';
	-- !x! endif

	-- Mark this constraint as processed.
	update ups_nonnull_columns
	set processed = 1
	where column_name = '!!~column_name!!';

	-- Loop.
	-- !x! execute script nullqa_one_innerloop with (stage_pfx=!!#stage_pfx!!, table=!!#table!!)

-- !x! endif

-- Clean up.
-- !x! if(view_exists(ups_qa_nonnull_col))
	drop view if exists ups_qa_nonnull_col;
-- !x! endif


-- !x! END SCRIPT
-- ###################  End of NULL_QA_ONE  #######################
-- ################################################################



-- ################################################################
--			Script PKQA_ONE
--
-- Check data in a staging table for violations of the primary key
-- of the corresponding base table.
-- Reports any PK violations found to the console and optionally
-- to a log file.
--
-- Input parameters:
--		stage_pfx		: The name of the staging schema.
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
--		ups_primary_key_columns		: table
--		ups_pk_check				: table
--		ups_ercnt					: view
-- ===============================================================

-- !x! BEGIN SCRIPT PKQA_ONE with parameters (stage_pfx, table, display_errors, error_list)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Primary key QA checks on table !!#stage_pfx!!!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting primary key QA checks on table !!#stage_pfx!!!!#table!!"

-- Validate input table specifications.
-- !x! execute script validate_one with args (stage_pfx=!!#stage_pfx!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)

-- Initialize the return value to False (no primary key errors)
-- !x! sub_empty !!#error_list!!

-- Create a table of primary key columns on this table
-- !x! if(table_exists(ups_primary_key_columns))
	drop table ups_primary_key_columns cascade;
-- !x! endif
create table ups_primary_key_columns
select k.constraint_name, k.column_name, k.ordinal_position
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
	and tc.constraint_schema = '!!$db_name!!'
order by k.ordinal_position
;

-- !x! if(hasrows(ups_primary_key_columns))
	-- !x! subdata ~constraint_name ups_primary_key_columns

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking constraint !!~constraint_name!!." to !!logfile!!
	-- !x! endif

	-- Get a comma-delimited list of primary key columns to build SQL selection for duplicate keys
	-- !x! sub_empty ~pkcollist
	-- !x! if(view_exists(ups_pkcollist))
		drop view if exists ups_pkcollist cascade;
	-- !x! endif
	create view ups_pkcollist as
	select   group_concat(column_name separator ', ') as col_list
	from     ups_primary_key_columns
	order by ordinal_position;
	-- !x! subdata ~pkcollist ups_pkcollist

	-- Construct a query to test for duplicate values for pk columns.
	-- !x! sub            ~pk_check   select !!~pkcollist!!, count(*) as row_count
	-- !x! sub_append     ~pk_check   from !!#stage_pfx!!!!#table!! as s
	-- !x! sub_append     ~pk_check   group by !!~pkcollist!!
	-- !x! sub_append     ~pk_check   having count(*) > 1

	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "SQL for primary key check:" to !!logfile!!
		-- !x! write [!!~pk_check!!] to !!logfile!!
	-- !x! endif

	-- Run the check.
	-- !x! if(table_exists(ups_pk_check))
		drop table if exists ups_pk_check cascade;
	-- !x! endif
	create table ups_pk_check
	!!~pk_check!!;
	-- !x! if(hasrows(ups_pk_check))
		-- !x! write "    Duplicate key error on columns: !!~pkcollist!!."
		-- !x! if(view_exists(ups_ercnt))
			drop view if exists ups_ercnt cascade;
		-- !x! endif
		create view ups_ercnt
		select count(*) as errcnt, sum(row_count) as total_rows
		from ups_pk_check;
		-- !x! select_sub ups_ercnt
		-- !x! sub !!#error_list!! !!@errcnt!! duplicated key(s) (!!@total_rows!! rows)
		-- !x! if(sub_defined(logfile))
			-- !x! write "Duplicate primary key values in !!#table!!" to !!logfile!!
			-- !x! if(sub_defined(log_errors))
			-- !x! andif(is_true(!!log_errors!!))
				-- !x! export ups_pk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Primary key violations in !!stage_pfx!!!!#table!!" display ups_pk_check
		-- !x! endif
	-- !x! endif
-- !x! endif

-- Clean up.
drop view if exists ups_pkcollist cascade;
drop table if exists ups_primary_key_columns cascade;
drop table if exists ups_pk_check cascade;
-- !x! if(view_exists(ups_ercnt))
	drop view if exists ups_ercnt cascade;
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
--		stage_pfx		: The prefix for staging table names.
--		table			: The table name--same for base and staging.
--		display_errors	: A value of 'Yes' or 'No' to indicate whether
--							unrecognized values should be displayed
--							in a GUI.  If not defined, unrecognized
--							values are not displayed.
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
--		ups_foreign_key_columns		: table
--		ups_sel_fks					: table
--		ups_fk_constraints			: table
--		ups_next_constraint			: view
--		ups_error_list				: view
--		ups_one_fk					: table
--		ups_fk_joins				: view
--		ups_fk_check				: view
--		ups_ercnt					: view
-- ===============================================================

-- !x! BEGIN SCRIPT FKQA_ONE with parameters (stage_pfx, table, display_errors, error_list)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Foreign key QA checks on table !!#stage_pfx!!!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting foreign key QA checks on table !!#stage_pfx!!!!#table!!"

-- Validate input table specifications.
-- !x! execute script validate_one with args (stage_pfx=!!#stage_pfx!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)

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
	create table ups_foreign_key_columns
	select
		rc.constraint_name,
		cu.table_schema,
		cu.table_name,
		cu.column_name,
		cu.ordinal_position,
		cu_uq.table_schema as uq_schema,
		cu_uq.table_name as uq_table,
		cu_uq.column_name as uq_column,
		cu_uq.ordinal_position as uq_position
	from
		(select constraint_catalog, constraint_schema, constraint_name,
			table_name,
			unique_constraint_catalog, unique_constraint_schema, unique_constraint_name,
            referenced_table_name
			from information_schema.referential_constraints
			where constraint_schema = '!!$db_name!!'
			) as rc
		inner join (select * from information_schema.table_constraints
			where constraint_type = 'FOREIGN KEY' and constraint_schema = '!!$db_name!!'
			) as tc
			on tc.constraint_catalog = rc.constraint_catalog
			and tc.constraint_schema = rc.constraint_schema
			and tc.constraint_name = rc.constraint_name
            and tc.table_name = rc.table_name
		inner join (select * from information_schema.table_constraints
			where constraint_type not in ('FOREIGN KEY', 'CHECK')
			and constraint_schema = '!!$db_name!!'
			) as tc_uq
			on tc_uq.constraint_catalog = rc.unique_constraint_catalog
			and tc_uq.constraint_schema = rc.unique_constraint_schema
			and tc_uq.constraint_name = rc.unique_constraint_name
            and tc_uq.table_name = rc.referenced_table_name
		inner join information_schema.key_column_usage as cu
			on cu.constraint_catalog = tc.constraint_catalog
			and cu.constraint_schema = tc.constraint_schema
			and cu.constraint_name = tc.constraint_name
            and cu.table_schema = tc.table_schema
			and cu.table_name = tc.table_name
		inner join information_schema.key_column_usage as cu_uq
			on cu_uq.constraint_catalog = tc_uq.constraint_catalog
			and cu_uq.constraint_schema = tc_uq.constraint_schema
			and cu_uq.constraint_name = tc_uq.constraint_name
			and cu_uq.table_schema = tc_uq.table_schema
            and cu_uq.table_name = tc_uq.table_name
			and cu_uq.ordinal_position = cu.ordinal_position
		;
-- !x! endif

-- Create a temporary table of just the foreign key relationships for the base
-- table corresponding to the staging table to check.
-- !x! if(table_exists(ups_sel_fks))
	drop table if exists ups_sel_fks cascade;
-- !x! endif
create table ups_sel_fks
select
	constraint_name, table_schema, table_name, column_name,
	ordinal_position,
	uq_schema, uq_table, uq_column
from
	ups_foreign_key_columns
where
	table_schema = '!!$DB_NAME!!'
	and table_name = '!!#table!!';

-- Create a table of all unique constraint names for
-- this table, with an integer column to be populated with the
-- number of rows failing the foreign key check, and a 'processed'
-- 	flag to control looping.
-- !x! if(table_exists(ups_fk_constraints))
	drop table if exists ups_fk_constraints cascade;
-- !x! endif
create table ups_fk_constraints
select distinct
	constraint_name,
	0 as fkerror_values,
	0 as processed
from ups_sel_fks;

-- Create a view to select one constraint to process.
create or replace view ups_next_constraint as
select constraint_name
from ups_fk_constraints
where processed = 0
limit 1;

-- Process all constraints: check every foreign key.
-- !x! execute script fk_qa_one_innerloop with (stage_pfx=!!#stage_pfx!!, table=!!#table!!, display_errors=!!#display_errors!!)

-- Create the return value.
create or replace view ups_error_list as
select
	group_concat(concat(constraint_name, ' (', fkerror_values, ')') separator ', ') as fk_errors
from
	ups_fk_constraints
where
	coalesce(fkerror_values, 0) > 0;
-- !x! if(hasrows(ups_error_list))
	-- !x! subdata !!#error_list!! ups_error_list
-- !x! endif

-- Clean up.
drop view if exists ups_error_list cascade;
drop view if exists ups_next_constraint cascade;
drop table if exists ups_fk_constraints cascade;
drop table if exists ups_sel_fks;

-- !x! END SCRIPT
-- End of          FK_QA_ONE
-- ****************************************************************
-- ****************************************************************
--			Script FK_QA_ONE_INNERLOOP
-- ----------------------------------------------------------------
-- !x! BEGIN SCRIPT FK_QA_ONE_INNERLOOP with parameters (stage_pfx, table, display_errors)

-- !x! if(hasrows(ups_next_constraint))
	-- !x! subdata constraint_name ups_next_constraint

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking constraint !!constraint_name!!." to !!logfile!!
	-- !x! endif

	-- !x! if(table_exists(ups_one_fk))
		drop table if exists ups_one_fk cascade;
	-- !x! endif
	create table ups_one_fk
	select column_name, ordinal_position, uq_schema, uq_table, uq_column
	from ups_sel_fks
	where constraint_name = '!!constraint_name!!';

	-- Get the unique table schema and name into data variables.
	-- !x! select_sub ups_one_fk

	-- Create join expressions from staging table (s) to unique table (u)
	-- and to staging table equivalent to unique table (su) (though we
	-- don't know yet if the latter exists).  Also create a 'where'
	-- condition to ensure that all columns being matched are non-null.
	-- Also create a comma-separated list of the columns being checked.
	create or replace view ups_fk_joins as
	select
		group_concat(concat('s.', column_name, ' = u.', uq_column) separator ' and ') as u_join,
		group_concat(concat('s.', column_name, ' = su.', uq_column) separator ' and ') as su_join,
		group_concat(concat('s.', column_name, ' is not null') separator ' and ') as s_not_null,
		group_concat(concat('s.', column_name) separator ', ') as s_checked
	from
		(select * from ups_one_fk order by ordinal_position) as fkcols;
	-- !x! select_sub ups_fk_joins

	-- Determine whether a staging-table equivalent of the unique table exists.
	-- !x! sub su_exists No
	-- !x! if(table_exists(!!#stage_pfx!!!!@uq_table!!))
		-- !x! sub su_exists Yes
	-- !x! endif

	-- Construct a query to test for missing unique values for fk columns.
	-- !x! sub            ~fk_check   select !!@s_checked!!, count(*) as row_count
	-- !x! sub_append     ~fk_check   from !!#stage_pfx!!!!#table!! as s
	-- !x! sub_append     ~fk_check   left join !!@uq_table!! as u on !!@u_join!!
	-- !x! if(is_true(!!su_exists!!))
		-- !x! sub_append ~fk_check   left join !!#stage_pfx!!!!@uq_table!! as su on !!@su_join!!
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
		-- !x! write [!!~fk_check!!] to !!logfile!!
	-- !x! endif

	-- Run the check.
	create or replace view ups_fk_check as !!~fk_check!!;
	-- !x! if(hasrows(ups_fk_check))
		-- !x! write "    Foreign key error referencing !!@uq_table!!."
		create or replace view ups_ercnt as select count(*) from ups_fk_check;
		-- !x! subdata ~errcnt ups_ercnt
		update ups_fk_constraints
		set fkerror_values = !!~errcnt!!
		where constraint_name = '!!constraint_name!!';
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
	set processed = 1
	where constraint_name = '!!constraint_name!!';

	-- Loop.
	-- !x! execute script fk_qa_one_innerloop with (stage_pfx=!!#stage_pfx!!, table=!!#table!!, display_errors=!!#display_errors!!)

-- !x! endif

-- Clean up.
-- !x! if(view_exists(ups_fk_check))
	drop view if exists ups_fk_check cascade;
-- !x! endif
-- !x! if(view_exists(ups_fk_joins))
	drop view if exists ups_fk_joins cascade;
-- !x! endif
-- !x! if(table_exists(ups_foreign_key_columns))
	drop table if exists ups_foreign_key_columns cascade;
-- !x! endif

-- Clean up.
-- !x! if(table_exists(ups_one_fk))
	drop table if exists ups_one_fk cascade;
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
--		stage_pfx		: The name of the staging schema.
--		table			: The table name--same for base and staging.
--		exclude_cols	: A comma-delimited list of single-quoted
--							column names identifying the columns
--							of the base table that are not to be
--							modified.  These may be autonumber
--							columns or columns filled by triggers.
--		display_changes	: A boolean variable indicating whether
--							or not the changes to be made to the
--							base table should be displayed in a GUI.
--							Optional.  If not defined, the changes
--							will be defined.
--		display_final	: A boolean variable indicating whether or
--							not the base table should be displayed
--							after updates and inserts are completed.
--							Optional.  If not defined, the final
--							base table will not be displayed.
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
--		ups_cols				: table
--		ups_pks					: table
--		ups_allcollist			: temporary view
--		ups_allbasecollist		: temporary view
--		ups_allstgcollist		: temporary view
--		ups_pkcollist			: temporary view
--		ups_joinexpr			: temporary view
--		ups_basematches			: temporary view
--		ups_stgmatches			: temporary view
--		ups_assexpr				: temporary view
--		ups_newrows				: temporary view
-- ===============================================================

-- !x! BEGIN SCRIPT UPSERT_ONE with parameters (stage_pfx, table, exclude_cols, display_changes, display_final, updcntvar, inscntvar)

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
	-- !x! write "!!$current_time!! -- Performing upsert on table !!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Performing upsert on table !!#table!!"

-- Validate input table specifications.
-- !x! execute script validate_one with args (stage_pfx=!!#stage_pfx!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)

-- Populate a (temporary) table with the names of the columns
-- in the base table that are to be updated from the staging table.
-- !x! if(is_null("!!#exclude_cols!!"))
	-- !x! sub_empty ~col_excl
-- !x! else
	-- !x! sub ~col_excl and column_name not in (!!#exclude_cols!!)
-- !x! endif
-- !x! if(table_exists(ups_cols))
	drop table if exists ups_cols cascade;
-- !x! endif
create table ups_cols
select column_name
from information_schema.columns
where
	table_name = '!!#stage_pfx!!!!#table!!'
	and table_schema = '!!$DB_NAME!!'
	!!~col_excl!!
order by ordinal_position;


-- Populate a (temporary) table with the names of the primary key
-- columns of the base table.
-- !x! if(table_exists(ups_pks))
	drop table if exists ups_pks cascade;
-- !x! endif
create table ups_pks
select k.column_name
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
	and k.table_schema = '!!$DB_NAME!!'
order by k.ordinal_position;

-- Get all base table columns that are to be updated into a comma-delimited list.
-- !x! if(view_exists(ups_allcollist))
	drop view ups_allcollist cascade;
-- !x! endif
create view ups_allcollist as
select group_concat(column_name separator ', ')
from ups_cols;
-- !x! subdata ~allcollist ups_allcollist;


-- Get all base table columns that are to be updated into a comma-delimited list
-- with a "b." prefix.
-- !x! if(view_exists(ups_allbasecollist))
	drop view ups_allbasecollist cascade;
-- !x! endif
create view ups_allbasecollist as
select group_concat(concat('b.', column_name) separator ', ')
from ups_cols;
-- !x! subdata ~allbasecollist ups_allbasecollist;

-- Get all staging table column names for columns that are to be updated
-- into a comma-delimited list with an "s." prefix.
-- !x! if(view_exists(ups_allstgcollist))
	drop view ups_allstgcollist cascade;
-- !x! endif
create view ups_allstgcollist as
select group_concat(concat('s.', column_name) separator ', ')
from ups_cols;
-- !x! subdata ~allstgcollist ups_allstgcollist;


-- Get the primary key columns in a comma-delimited list.
-- !x! if(view_exists(ups_pkcollist))
	drop view ups_pkcollist cascade;
-- !x! endif
create view ups_pkcollist as
select group_concat(column_name separator ', ')
from ups_pks;
-- !x! subdata ~pkcollist ups_pkcollist;


-- Create a join expression for key columns of the base (b) and
-- staging (s) tables.
-- !x! if(view_exists(ups_joinexpr))
	drop view ups_joinexpr cascade;
-- !x! endif
create view ups_joinexpr as
select
	group_concat(concat('b.', column_name, ' = s.', column_name) separator ' and ')
from
	ups_pks;
-- !x! subdata ~joinexpr ups_joinexpr


-- Create a FROM clause for an inner join between base and staging
-- tables on the primary key column(s).
-- !x! sub ~fromclause FROM !!#table!! as b INNER JOIN !!#stage_pfx!!!!#table!! as s ON !!~joinexpr!!

-- Create SELECT queries to pull all columns with matching keys from both
-- base and staging tables.
-- !x! if(view_exists(ups_basematches))
	drop view ups_basematches cascade;
-- !x! endif
create view ups_basematches as select !!~allbasecollist!! !!~fromclause!!;

-- !x! if(view_exists(ups_stgmatches))
	drop view ups_stgmatches cascade;
-- !x! endif
create view ups_stgmatches as select !!~allstgcollist!! !!~fromclause!!;

-- Get non-key columns to be updated.
-- !x! if(view_exists(ups_nk))
	drop view if exists ups_nk cascade;
-- !x! endif
create view ups_nk as
select cols.column_name
from
	ups_cols as cols
	left join ups_pks as pks on pks.column_name = cols.column_name
where
	pks.column_name is null;

-- Prompt user to examine matching data and commit, don't commit, or quit.
-- !x! if(hasrows(ups_stgmatches))
-- !x! andif(hasrows(ups_nk))
	-- !x! if(is_true(!!#display_changes!!))
		-- !x! prompt ask "Do you want to make these changes? For table !!#table!!, new data are shown in the top table below; existing data are in the lower table." sub ~do_updates compare ups_stgmatches and ups_basematches key (!!~pkcollist!!)
	-- !x! endif

	-- !x! if(is_true(!!~do_updates!!))
		-- Create an assignment expression to update non-key columns of the
		-- base table (un-aliased) from columns of the staging table (as s).
		-- !x! if(view_exists(ups_assexpr))
			drop view ups_assexpr cascade;
		-- !x! endif
		create view ups_assexpr as
		select
			group_concat(concat('b.', column_name, ' = s.', column_name) separator ', ') as col
		from
			ups_nk;
		-- !x! subdata ~assexpr ups_assexpr

		-- Create an UPDATE statement to update the base table with
		-- non-key columns from the staging table.  No semicolon terminating generated SQL.
		-- !x! sub ~updatestmt UPDATE !!#table!! as b, !!#stage_pfx!!!!#table!! as s SET !!~assexpr!! WHERE !!~joinexpr!!
	-- !x! endif
-- !x! endif


-- Create a select statement to find all rows of the staging table
-- that are not in the base table.
-- !x! if(view_exists(ups_newrows))
	drop view ups_newrows cascade;
-- !x! endif
create view ups_newrows as
with newpks as (
	select !!~pkcollist!! from !!#stage_pfx!!!!#table!!
	except
	select !!~pkcollist!! from !!#table!!
	)
select
	s.*
from
	!!#stage_pfx!!!!#table!! as s
	inner join newpks using (!!~pkcollist!!);


-- Prompt user to examine new data and continue or quit.
-- !x! if(hasrows(ups_newrows))
	-- !x! if(is_true(!!#display_changes!!))
		-- !x! prompt ask "Do you want to add these new data to the !!#table!! table?" sub ~do_inserts display ups_newrows
	-- !x! endif

	-- !x! if(is_true(!!~do_inserts!!))
		-- Create an insert statement.  No semicolon terminating generated SQL.
		-- !x! sub ~insertstmt INSERT INTO !!#table!! (!!~allcollist!!) SELECT !!~allcollist!! FROM ups_newrows
	-- !x! endif
-- !x! endif


-- Run the update and insert statements.

-- !x! if(sub_defined(~updatestmt))
-- !x! andif(is_true(!!~do_updates!!))
	-- !x! write "Updating !!#table!!"
	-- !x! if(sub_defined(logfile))
		-- !x! write "" to !!logfile!!
		-- !x! if(sub_defined(log_sql))
		-- !x! andif(is_true(!!log_sql!!))
			-- !x! write "UPDATE statement for !!#table!!:" to !!logfile!!
			-- !x! write [!!~updatestmt!!] to !!logfile!!
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
		-- !x! write "!!$last_rowcount!! rows of !!#table!! updated." to !!logfile!!
	-- !x! endif
	-- !x! write "    !!$last_rowcount!! rows updated."
-- !x! endif


-- !x! if(sub_defined(~insertstmt))
-- !x! andif(is_true(!!~do_inserts!!))
	-- !x! write "Adding data to !!#table!!"
	-- !x! if(sub_defined(logfile))
		-- !x! write "" to !!logfile!!
		-- !x! if(sub_defined(log_sql))
		-- !x! andif(is_true(!!log_sql!!))
			-- !x! write "INSERT statement for !!#table!!:" to !!logfile!!
			-- !x! write [!!~insertstmt!!] to !!logfile!!
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
		-- !x! write "!!$last_rowcount!! rows added to !!#table!!." to !!logfile!!
	-- !x! endif
	-- !x! write "    !!$last_rowcount!! rows added."
-- !x! endif


-- !x! if(is_true(!!#display_final!!))
	-- !x! prompt message "Table !!#table!! after updates and inserts." display !!#table!!
-- !x! endif

-- Clean up.
drop view if exists ups_newrows cascade;
-- !x! if(view_exists(ups_assexpr))
	drop view ups_assexpr cascade;
-- !x! endif
drop view if exists ups_stgmatches cascade;
drop view if exists ups_basematches cascade;
drop view if exists ups_joinexpr cascade;
drop view if exists ups_pkcollist cascade;
drop view if exists ups_allstgcollist cascade;
drop view if exists ups_allbasecollist cascade;
drop view if exists ups_allcollist cascade;
drop view if exists ups_nk cascade;
drop table if exists ups_pks cascade;
drop table if exists ups_cols cascade;


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
--		stage_pfx		: The name of the staging schema.
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
--
-- Tables and view used:
--		ups_dependencies			: table
--		ups_ordered_tables			: table
--		ups_proctables				: table
--		ups_toprocess				: view
--		ups_upsert_rows				: view
-- ===============================================================

-- !x! BEGIN SCRIPT UPSERT_ALL with parameters (stage_pfx, control_table)

-- Validate contents of control table
-- !x! execute script validate_control with (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!, script=!!$CURRENT_SCRIPT_NAME!!, script_line=!!$SCRIPT_LINE!!)

-- Initialize the status and progress bars if the console is running.
-- !x! if(console_on)
	-- !x! reset counter 221585944
	-- !x! console status "Merging data"
	-- !x! console progress 0
	-- !x! if(view_exists(ups_upsert_rows))
		drop view if exists ups_upsert_rows;
	-- !x! endif
	create view ups_upsert_rows as
	select count(*) + 1 as upsert_rows
	from !!#control_table!!;
	-- !x! subdata upsert_progress_denom ups_upsert_rows
-- !x! endif


-- Get a table of all dependencies for the base schema.
-- !x! if(table_exists(ups_dependencies))
	drop table if exists ups_dependencies cascade;
-- !x! endif
create table ups_dependencies
select distinct
	tc.table_name as child,
	tc_uq.table_name as parent
from
	(select distinct constraint_catalog, constraint_schema, constraint_name,
		table_name,
		unique_constraint_catalog, unique_constraint_schema, unique_constraint_name,
        referenced_table_name
		from information_schema.referential_constraints
		where constraint_schema = '!!$DB_NAME!!') as rc
	inner join (select * from information_schema.table_constraints
			where constraint_type = 'FOREIGN KEY') as tc
		on tc.constraint_catalog = rc.constraint_catalog
		and tc.constraint_schema = rc.constraint_schema
		and tc.constraint_name = rc.constraint_name
        and tc.table_name = rc.table_name
	inner join (select * from information_schema.table_constraints
			where constraint_type not in ('FOREIGN KEY', 'CHECK') ) as tc_uq
		on tc_uq.constraint_catalog = rc.unique_constraint_catalog
		and tc_uq.constraint_schema = rc.unique_constraint_schema
		and tc_uq.constraint_name = rc.unique_constraint_name
		and tc_uq.table_name = rc.referenced_table_name
	;

-- Create a list of tables in the base schema ordered by dependency.
-- !x! if(table_exists(ups_ordered_tables))
	drop table if exists ups_ordered_tables cascade;
-- !x! endif
create table ups_ordered_tables
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
from (
	-- All parents
	select
		dd.parent as table_name,
		max(lvl) as table_order
	from
		dep_depth as dd
	group by
		table_name
	union
	-- Children that are not parents
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
	-- Neither parents nor children
	select distinct
		t.table_name,
		0 as level
	from
		information_schema.tables as t
		left join ups_dependencies as p on t.table_name=p.parent
		left join ups_dependencies as c on t.table_name=c.child
	where
		t.table_schema = '!!$DB_NAME!!'
		and t.table_type = 'BASE TABLE'
		and p.parent is null
		and c.child is null
	) as all_levels;


-- Create a list of the selected tables with ordering information.
-- !x! if(table_exists(ups_proctables))
	drop table if exists ups_proctables cascade;
-- !x! endif
create table ups_proctables
select
	ot.table_order,
	tl.table_name,
	tl.exclude_cols,
	tl.display_changes,
	tl.display_final,
	tl.rows_updated,
	tl.rows_inserted,
	0 as processed
from
	!!#control_table!! as tl
	inner join ups_ordered_tables as ot on ot.table_name = tl.table_name
	;

-- Create a view returning a single unprocessed table, in order.
-- !x! if(view_exists(ups_toprocess))
	drop view if exists ups_toprocess cascade;
-- !x! endif
create view ups_toprocess as
select
	table_name, exclude_cols,
	display_changes, display_final,
	rows_updated, rows_inserted
from ups_proctables
where processed = 0
order by table_order
limit 1;

-- Process all tables in order.
-- !x! execute script upsert_all_innerloop with (stage_pfx=!!#stage_pfx!!)

-- Move the update/insert counts back into the control table.
update !!#control_table!! as ct, ups_proctables as pt
set
	ct.rows_updated = pt.rows_updated,
	ct.rows_inserted = pt.rows_inserted
where
	pt.table_name = ct.table_name;


-- Clean up
drop table if exists ups_proctables cascade;
drop view if exists ups_toprocess cascade;
drop table if exists ups_ordered_tables cascade;
drop table if exists ups_dependencies cascade;
-- !x! if(view_exists(ups_upsert_rows))
	drop view if exists ups_upsert_rows;
-- !x! endif


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

-- !x! BEGIN SCRIPT UPSERT_ALL_INNERLOOP with parameters (stage_pfx)

-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- Create variables to store the row counts from updates and inserts.
	-- !x! sub ~rows_updated 0
	-- !x! sub ~rows_inserted 0

	-- !x! select_sub ups_toprocess
	-- !x! execute script upsert_one with (stage_pfx=!!#stage_pfx!!, table=!!@table_name!!, exclude_cols="!!@exclude_cols!!", display_changes=!!@display_changes!!, display_final=!!@display_final!!, updcntvar=+rows_updated, inscntvar=+rows_inserted)

	update ups_proctables
	set rows_updated = !!~rows_updated!!,
		rows_inserted = !!~rows_inserted!!
	where table_name = '!!@table_name!!';

	update ups_proctables
	set processed = 1
	where table_name = '!!@table_name!!';
	-- !x! execute script upsert_all_innerloop with (stage_pfx=!!#stage_pfx!!)
-- !x! endif

-- !x! END SCRIPT
-- ###############  End of UPSERT_ALL_INNERLOOP  ##################
-- ################################################################




-- ################################################################
--			Script QA_ALL
--
-- Conducts null, primary key, and foreign key checks on multiple
-- staging tables containing new or revised data for staging tables,
-- using the NULLQA_ONE, PKQA_ONE, and FKQA_ONE scripts.
--
-- Input parameters:
--		stage_pfx			: The name of the staging schema.
--		control_table	: The name of a table containing at least the
--							following four columns:
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
--													count for the duplicated
--													keys.
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
--		ups_proctables				: temporary table
--		ups_toprocess				: temporary table
--		ups_upsert_rows				: temporary table
--
-- Counters used:
--		221585944					: Progress bar position
--
-- Global variables modified:
--		upsert_progress_denom		: Created or redefined.
--
-- ===============================================================

-- !x! BEGIN SCRIPT QA_ALL with parameters (stage_pfx, control_table)

-- Get denominator for progress bar if console is on.
-- !x! if(console_on)
	-- !x! if(view_exists(ups_upsert_rows))
		drop view if exists ups_upsert_rows;
	-- !x! endif
	create view ups_upsert_rows as
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
-- !x! if(table_exists(ups_proctables))
	drop table if exists ups_proctables cascade;
-- !x! endif
create table ups_proctables
select
	tl.table_name,
	tl.exclude_null_checks,
	tl.display_changes,
	0 as processed
from
	!!#control_table!! as tl
	;

-- Create a view returning a single unprocessed table, in order.
-- !x! if(table_exists(ups_toprocess))
	drop view if exists ups_toprocess;
-- !x! endif
create view ups_toprocess as
select table_name, exclude_null_checks, display_changes
from ups_proctables
where processed = 0
limit 1;

-- Perform null QA checks on all tables.
-- !x! execute script update_console_qa with args (check_type=NULL)
-- !x! execute script qa_all_nullloop with (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)

-- Perform primary key QA checks on all tables.
update ups_proctables set processed = 0;
-- !x! execute script update_console_qa with args (check_type="primary key")
-- !x! execute script qa_all_pkloop with (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)

-- Perform foreign key QA checks on all tables.
update ups_proctables set processed = 0;
-- !x! execute script update_console_qa with args (check_type=foreign key)
-- !x! execute script qa_all_fkloop with (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)


-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console status "Data QA checks complete"
	-- !x! console progress 0
-- !x! endif

-- Clean up.
drop table if exists ups_proctables cascade;
drop view if exists ups_toprocess;
-- !x! if(view_exists(ups_upsert_rows))
	drop view if exists ups_upsert_rows;
-- !x! endif


-- !x! END SCRIPT
--					QA_ALL
-- ****************************************************************
-- ****************************************************************
--		Script QA_ALL_NULLLOOP
-- ---------------------------------------------------------------

-- !x! BEGIN SCRIPT QA_ALL_NULLLOOP with parameters (stage_pfx, control_table)

-- !x! sub_empty ~ups_null_error_list

-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- !x! select_sub ups_toprocess
	-- !x! if(is_null("!!@exclude_null_checks!!"))
		-- !x! execute script nullqa_one with (stage_pfx=!!#stage_pfx!!, table=!!@table_name!!, error_list=+ups_null_error_list)
	-- !x! else
		-- !x! execute script nullqa_one with (stage_pfx=!!#stage_pfx!!, table=!!@table_name!!, error_list=+ups_null_error_list, exclude_null_checks=[!!@exclude_null_checks!!])
	-- !x! endif
	-- !x! if(not is_null("!!~ups_null_error_list!!"))
		update !!#control_table!!
		set null_errors = '!!~ups_null_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update ups_proctables
	set processed = 1
	where table_name = '!!@table_name!!';
	-- !x! execute script qa_all_nullloop with (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)
-- !x! endif

-- !x! END SCRIPT
--					QA_ALL_NULLLOOP
-- ****************************************************************
-- ****************************************************************
--		Script QA_ALL_PKLOOP
-- ---------------------------------------------------------------

-- !x! BEGIN SCRIPT QA_ALL_PKLOOP with parameters (stage_pfx, control_table)

-- !x! sub_empty ~ups_pk_error_list
-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- !x! select_sub ups_toprocess
	-- !x! execute script pkqa_one with (stage_pfx=!!#stage_pfx!!, table=!!@table_name!!, display_errors=!!@display_changes!!, error_list=+ups_pk_error_list)
	-- !x! if(not is_null("!!~ups_pk_error_list!!"))
		update !!#control_table!!
		set pk_errors = '!!~ups_pk_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update ups_proctables
	set processed = 1
	where table_name = '!!@table_name!!';
	-- !x! execute script qa_all_pkloop with (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)
-- !x! endif


-- !x! END SCRIPT
--					QA_ALL_PKLOOP
-- ****************************************************************
-- ****************************************************************
--		Script QA_ALL_FKLOOP
-- ---------------------------------------------------------------

-- !x! BEGIN SCRIPT QA_ALL_FKLOOP with parameters (stage_pfx, control_table)

-- !x! sub_empty ~ups_error_list

-- Update the status bar if the console is running.
-- !x! if(console_on)
	-- !x! console progress !!$counter_221585944!! / !!upsert_progress_denom!!
-- !x! endif

-- !x! if(hasrows(ups_toprocess))
	-- !x! select_sub ups_toprocess
	-- !x! execute script fkqa_one with (stage_pfx=!!#stage_pfx!!, table=!!@table_name!!, display_errors=!!@display_changes!!, error_list=+ups_error_list)
	-- !x! if(not is_null("!!~ups_error_list!!"))
		update !!#control_table!!
		set fk_errors = '!!~ups_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update ups_proctables
	set processed = 1
	where table_name = '!!@table_name!!';
	-- !x! execute script qa_all_fkloop with (stage_pfx=!!#stage_pfx!!, control_table=!!#control_table!!)
-- !x! endif

-- !x! END SCRIPT
-- #####################  End of QA_ALL  ###########################
-- #################################################################




-- ################################################################
--			Script UPDTPK_ONE
--
-- Updates primary keys in the base table, based on new and existing
-- values of PK columns in a staging table, using UPDATE
-- statements.  Displays data to be modified to the
-- user before any modifications are done.  Reports the changes
-- made to the console and optionally to a log file.
--
-- Input parameters:
--		stage_pfx		: The prefix to the name of the staging table.
--		table			: The table name--same for base and staging,
--							except for the prefix on the staging table.
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
--		ups_pkcol_info			: temporary table
--		ups_pkupdates			: temporary table
--		ups_pkupdate_strings	: temporary view
--		ups_pkupdates			: temporary table
-- ===============================================================

-- !x! BEGIN SCRIPT UPDTPK_ONE with parameters (stage_pfx, table, display_errors, display_changes)

-- !x! if(console_on)
	-- !x! console status "Primary key updates"
-- !x! endif


-- Validate inputs: base/staging schemas and table
-- !x! execute script validate_one with args (stage_pfx=!!#stage_pfx!!, table=!!#table!!, script=!!$CURRENT_SCRIPT!!, script_line=!!$SCRIPT_LINE!!)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- Performing primary key updates on table !!#table!! from !!#stage_pfx!!!!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Performing primary key updates on table !!#table!! from !!#stage_pfx!!!!#table!!"

-- Create a temp table to store the results of the PK update QA checks
-- !x! if(table_exists(ups_pkqa_errors))
	drop table if exists ups_pkqa_errors cascade;
-- !x! endif
create table ups_pkqa_errors (
	error_code varchar(40),
	error_description varchar(500)
);


-- Populate a (temporary) table with the names of the primary key columns of the base table.
-- Get the old and new primary key columns from staging table into various formats
-- to use later to construct SQL statement to select records in various ways for both updates and QA checks.
-- Include column lists, join expression, and where clause
-- !x! if(table_exists(ups_pkcol_info))
	drop table if exists ups_pkcol_info cascade;
-- !x! endif
create table ups_pkcol_info
select
	k.table_schema,
	k.table_name,
	k.column_name,
	cast(concat('b.', column_name) as varchar(2000)) as base_aliased,
	cast(concat('s.', column_name) as varchar(2000)) as staging_aliased,
	cast(concat('s.', column_name, ' as staging_', column_name) as varchar(2000)) as staging_aliased_prefix,
	cast(concat('b.', column_name, ' = s.', column_name) as varchar(2000)) as join_expr,
	cast(concat('new_', column_name) as varchar(2000)) as newpk_col,
	cast(concat('s.new_', column_name) as varchar(2000)) as newpk_col_aliased,
	cast(concat('new_', column_name, ' is null') as varchar(2000)) as newpk_col_empty,
	cast(concat('new_', column_name, ' is not null') as varchar(2000)) as newpk_col_not_empty,
	cast(concat('b.', column_name, ' = s.new_', column_name) as varchar(2000)) as assmt_expr,
	cast(concat('b.', column_name, ' = s.new_', column_name) as varchar(2000)) as join_expr_oldnew,
	cast(concat('s.new_', column_name, ' = b.new_', column_name) as varchar(2000)) as join_expr_new,
	k.ordinal_position
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
	and k.table_schema = '!!$DB_NAME!!'
;


-- Run QA checks
-- !x! execute script UPDTPKQA_ONE with arguments(stage_pfx=!!#stage_pfx!!, table=!!#table!!, pkinfo_table=ups_pkcol_info, qaerror_table=ups_pkqa_errors, display_errors=!!#display_errors!!)


-- Run the PK update ONLY if QA check script returned no errors
-- !x! if(not hasrows(ups_pkqa_errors))
	-- !x! rm_sub ~updatestmt

	-- !x! sub ~do_updates Yes

	-- !x! if(sub_defined(logfile))
		-- !x! write "" to !!logfile!!
		-- !x! write "==================================================================" to !!logfile!!
		-- !x! write "!!$current_time!! -- Performing primary key update on table !!#table!!" to !!logfile!!
	-- !x! endif

	-- !x! if(console_on)
		-- !x! console status "Performing PK updates"
		-- !x! console progress 0
	-- !x! endif

	-- !x! write "Performing primary key update on table !!#table!!"

	-- Create strings necessary to construct SQL to perform the updates
	-- !x! if(view_exists(ups_pkupdate_strings))
		drop view if exists ups_pkupdate_strings cascade;
	-- !x! endif
	create view ups_pkupdate_strings as
	select
		group_concat(base_aliased order by ordinal_position separator ', ') as oldpk_cols,
		group_concat(newpk_col order by ordinal_position separator ', ') as newpk_cols,
		group_concat(join_expr order by ordinal_position separator ' and ') as joinexpr,
		group_concat(newpk_col_not_empty order by ordinal_position separator ' and ') as all_newpk_col_not_empty,
		group_concat(assmt_expr order by ordinal_position separator ', ') as assmt_expr
	from ups_pkcol_info
	group by table_name
	;
	-- !x! select_sub ups_pkupdate_strings

	-- Create a FROM clause for an inner join between base and staging
	-- tables on the primary key column(s).
	-- !x! sub ~fromclause FROM !!#table!! as b INNER JOIN !!#stage_pfx!!!!#table!! as s ON !!@joinexpr!!

	-- Create a WHERE clause for the rows to include in the selection (only those having new PK columns populated in the staging table)
	-- !x! sub ~whereclause WHERE !!@all_newpk_col_not_empty!!

	-- Select all matches for PK update into temp table
	-- !x! if(table_exists(ups_pkupdates))
		drop table if exists ups_pkupdates cascade;
	-- !x! endif
	create table ups_pkupdates
	select
		!!@oldpk_cols!!,
		!!@newpk_cols!!
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
			-- !x! sub ~updatestmt UPDATE !!#table!! as b, !!#stage_pfx!!!!#table!! as s SET !!@assmt_expr!! WHERE !!@joinexpr!! and !!@all_newpk_col_not_empty!!

			-- !x! write "Updating !!#table!!"
			-- !x! if(sub_defined(logfile))
				-- !x! write "" to !!logfile!!
				-- !x! if(sub_defined(log_sql))
				-- !x! andif(is_true(!!log_sql!!))
					-- !x! write "UPDATE statement for !!#table!!:" to !!logfile!!
					-- !x! write [!!~updatestmt!!] to !!logfile!!
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
				-- !x! write "!!$last_rowcount!! rows of !!#table!! updated." to !!logfile!!
			-- !x! endif
			-- !x! write "    !!$last_rowcount!! rows updated."
		-- !x! endif
	-- !x! else
		--!x! write "No primary key updates specified for existing records in !!#table!!"
	-- !x! endif
-- !x! endif


-- !x! if(table_exists(ups_pkqa_errors))
	drop table if exists ups_pkqa_errors cascade;
-- !x! endif
-- !x! if(table_exists(ups_pkcol_info))
	drop table if exists ups_pkcol_info cascade;
-- !x! endif
-- !x! if(view_exists(ups_pkupdate_strings))
	drop view if exists ups_pkupdate_strings cascade;
-- !x! endif
-- !x! if(table_exists(ups_pkupdates))
	drop table if exists ups_pkupdates cascade;
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
--		stage_pfx		: The prefix to the staging table name.
--		table			: The table name--same for base and staging,
--							except for the prefix of the staging table.
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

-- !x! BEGIN SCRIPT UPDTPKQA_ONE with parameters (stage_pfx, table, pkinfo_table, qaerror_table, display_errors)

-- Write an initial header to the logfile.
-- !x! if(sub_defined(logfile))
	-- !x! write "" to !!logfile!!
	-- !x! write "==================================================================" to !!logfile!!
	-- !x! write "!!$current_time!! -- QA checks for primary key updates on table !!#table!!" to !!logfile!!
-- !x! endif

-- !x! write "Conducting QA checks on table !!#stage_pfx!!!!#table!! for primary key updates to table !!#table!!"

-- Initialize the status and progress bars if the console is running.
-- !x! if(console_on)
	-- !x! console status "QA checks for PK updates on !!#table!!"
-- !x! endif


-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
-- Check 1 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
-- No primary key constraint on base table
-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
-- !x! if(not hasrows(!!#pkinfo_table!!))

	-- !x! sub ~error_description No primary key constraint on base table !!#table!!
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
	-- !x! if(table_exists(ups_missing_pk_cols))
		drop table if exists ups_missing_pk_cols cascade;
	-- !x! endif
	create table ups_missing_pk_cols
	select
		group_concat(newpk_col order by ordinal_position separator ', ') as missing_newpk_cols
	from
		--Base table PK columns, with expected name in staging table ("new_" prepended to column name)
		!!#pkinfo_table!! as pk
		--Staging table columns
		left join
			(
			select table_name, column_name
			from information_schema.columns
			where
				table_schema = '!!$DB_NAME!!'
				and table_name = '!!#stage_pfx!!!!#table!!'
			) as stag on  pk.newpk_col=stag.column_name
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
		-- !x! sub ~base_table !!#table!!

		-- Just staging table
		-- !x! sub ~staging_table !!#stage_pfx!!!!#table!!

		-- !x! if(table_exists(ups_pkqa_str_lib))
			drop table if exists ups_pkqa_str_lib;
		-- !x! endif
		create table ups_pkqa_str_lib
		select
			group_concat(column_name order by ordinal_position separator ', ') as old_pkcol,
			group_concat(staging_aliased order by ordinal_position separator ', ') as old_pkcol_aliased,
			group_concat(staging_aliased_prefix order by ordinal_position separator ', ') as old_pkcol_aliased_prefix,
			group_concat(newpk_col order by ordinal_position separator ', ') as new_pkcol,
			group_concat(newpk_col_aliased order by ordinal_position separator ', ') as new_pkcol_aliased,
			group_concat(join_expr order by ordinal_position separator ' and ') as joincond_origorig,
			group_concat(join_expr_oldnew order by ordinal_position separator ' and ') as joincond_oldnew,
			group_concat(join_expr_new order by ordinal_position separator ' and ') as joincond_newnew,
			group_concat(newpk_col_not_empty order by ordinal_position separator ' or ') as any_newpk_col_not_empty,
			group_concat(newpk_col_not_empty order by ordinal_position separator ' and ') as all_newpk_col_not_empty,
			group_concat(newpk_col_empty order by ordinal_position separator ' or ') as any_newpk_col_empty,
			group_concat(newpk_col_empty order by ordinal_position separator ' and ') as all_newpk_col_empty
		from !!#pkinfo_table!!
		;
		-- !x! select_sub ups_pkqa_str_lib



		-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
		-- Check 3 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
		-- There are any rows with PK updates specified.
		-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

		-- Find any populated new PK columns in staging table
		-- !x! if(table_exists(ups_any_pk_cols))
			drop table if exists ups_any_pk_cols cascade;
		-- !x! endif
		create table ups_any_pk_cols
		select *
		from !!~staging_table!!
		where !!@any_newpk_col_not_empty!!
		;
		-- !x! if(not hasrows(ups_any_pk_cols))
			-- !x! sub ~error_description No primary key updates specified in !!#stage_pfx!!!!#table!!
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
			-- !x! if(table_exists(ups_empty_pk_cols))
				drop table if exists ups_empty_pk_cols cascade;
			-- !x! endif
			create table ups_empty_pk_cols
			select
				!!@old_pkcol!!,
				!!@new_pkcol!!
			from
				!!~staging_table!!
			where
				not (!!@all_newpk_col_empty!!)
				and (!!@any_newpk_col_empty!!)
			;

			-- !x! if(hasrows(ups_empty_pk_cols))
				-- !x! if(view_exists(ups_empty_pk_cols_rwcnt))
					drop view if exists ups_empty_pk_cols_rwcnt cascade;
				-- !x! endif
				create view ups_empty_pk_cols_rwcnt as
				select count(*) as rwcnt
				from ups_empty_pk_cols
				;
				-- !x! subdata ~rowcount ups_empty_pk_cols_rwcnt
				-- !x! sub ~error_description Missing values in new PK columns in !!#stage_pfx!!!!#table!!: !!~rowcount!! row(s)
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
					-- !x! prompt message "Missing values in new PK columns in !!#stage_pfx!!!!#table!!" display ups_empty_pk_cols
				-- !x! endif
			-- !x! endif

			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 5 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Where any "new" PK column is populated in the staging table, the value of the original PK for that row is valid
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- New PK col in staging table are not empty
			-- !x! if(table_exists(ups_old_pks_wc))
				drop table if exists ups_old_pks_wc cascade;
			-- !x! endif
			create table ups_old_pks_wc
			select base_aliased
			from !!#pkinfo_table!!
			order by ordinal_position
			limit 1;
			-- !x! subdata ~old_pk_firstcol ups_old_pks_wc

			-- !x! if(table_exists(ups_invalid_old_pks))
				drop table if exists ups_invalid_old_pks cascade;
			-- !x! endif
			create table ups_invalid_old_pks
			select
				!!@old_pkcol_aliased!!,
				!!@new_pkcol!!
			from !!~staging_table!! as s
					left join !!~base_table!! as b on !!@joincond_origorig!!
			where !!@all_newpk_col_not_empty!! and !!~old_pk_firstcol!! is null
			;

			-- !x! if(hasrows(ups_invalid_old_pks))
				-- !x! if(view_exists(ups_invalid_pk_rwcnt))
					drop view if exists ups_invld_pk_rwcnt cascade;
				-- !x! endif
				create view ups_invld_pk_rwcnt as
				select count(*) as rwcnt
				from ups_invalid_old_pks
				;
				-- !x! subdata ~rowcount ups_invld_pk_rwcnt
				-- !x! sub ~error_description Invalid original PK in !!#stage_pfx!!!!#table!!: !!~rowcount!! row(s)
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
					-- !x! prompt message "Invalid original PK in !!#stage_pfx!!!!#table!!" display ups_invalid_old_pks
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 6 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- None of the "new" PK values already exist in the base table
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- !x! if(table_exists(ups_existing_new_pks))
				drop table if exists ups_existing_new_pks cascade;
			-- !x! endif
			create table ups_existing_new_pks
			select
				!!@old_pkcol_aliased_prefix!!,
				!!@new_pkcol!!,
				b.*
			from !!~staging_table!! as s
					inner join !!~base_table!! as b on !!@joincond_oldnew!!
			;

			-- !x! if(hasrows(ups_existing_new_pks))
				-- !x! if(view_exists(ups_exst_nwpk_rwcnt))
					drop view if exists ups_exst_nwpk_rwcnt cascade;
				-- !x! endif
				create view ups_exst_nwpk_rwcnt as
				select count(*) as rwcnt
				from ups_existing_new_pks
				;
				-- !x! subdata ~rowcount ups_exst_nwpk_rwcnt
				-- !x! sub ~error_description New PK already exists in !!#table!!: !!~rowcount!! row(s)
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
					-- !x! prompt message "New PK already exists in !!#table!!" display ups_existing_new_pks
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 7 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- No two (or more) original PK values map to same new PK value
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- !x! if(table_exists(ups_pk_mapping_conflict))
				drop table if exists ups_pk_mapping_conflict cascade;
			-- !x! endif
			create table ups_pk_mapping_conflict
			select
				!!@old_pkcol_aliased!!,
				!!@new_pkcol_aliased!!
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
				-- !x! if(view_exists(ups_map_conf_rwcnt))
					drop view if exists ups_map_conf_rwcnt cascade;
				-- !x! endif
				create view ups_map_conf_rwcnt as
				select count(*) as rwcnt
				from ups_pk_mapping_conflict
				;
				-- !x! subdata ~rowcount ups_map_conf_rwcnt
				-- !x! sub ~error_description Multiple original PKs mapped to same new PK in !!#stage_pfx!!!!#table!!: !!~rowcount!! row(s)
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
					-- !x! prompt message "Multiple original PKs mapped to same new PK in !!#stage_pfx!!!!#table!!" display ups_pk_mapping_conflict
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 8 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- No single original PK value maps to multiple new PK values
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- !x! if(table_exists(ups_pk_duplicate_keys))
				drop table if exists ups_pk_duplicate_keys cascade;
			-- !x! endif
			create table ups_pk_duplicate_keys
			select
				!!@old_pkcol_aliased!!,
				!!@new_pkcol_aliased!!
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
				-- !x! if(view_exists(ups_dup_key_rwcnt))
					drop view if exists ups_dup_key_rwcnt cascade;
				-- !x! endif
				create view ups_dup_key_rwcnt as
				select count(*) as rwcnt
				from ups_pk_duplicate_keys
				;
				-- !x! subdata ~rowcount ups_dup_key_rwcnt
				-- !x! sub ~error_description Original PK mapped to multiple new PKs in !!#stage_pfx!!!!#table!!: !!~rowcount!! row(s)
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
					-- !x! prompt message "Original PK mapped to multiple new PKs in !!#stage_pfx!!!!#table!!" display ups_pk_duplicate_keys
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 9 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- If any of the PK columns reference a parent table, all the "new" values of that column are valid
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- Get ALL foreign key column references for the base table
			-- !x! if(table_exists(ups_fkcol_refs))
				drop table if exists ups_fkcol_refs cascade;
			-- !x! endif
			create table ups_fkcol_refs
			select
				rc.constraint_name as fk_constraint,
				cu.table_schema,
				cu.table_name,
				cu.column_name,
				cu.ordinal_position,
				cu_uq.table_schema as parent_schema,
				cu_uq.table_name as parent_table,
				cu_uq.column_name as parent_column,
				cu_uq.ordinal_position as parent_position
			from
				(select constraint_catalog, constraint_schema, constraint_name,
					table_name,
					unique_constraint_catalog, unique_constraint_schema, unique_constraint_name,
            		referenced_table_name
					from information_schema.referential_constraints
					where constraint_schema = '!!$db_name!!'
					) as rc
				inner join (select * from information_schema.table_constraints
					where constraint_type = 'FOREIGN KEY' and constraint_schema = '!!$db_name!!'
					) as tc
					on tc.constraint_catalog = rc.constraint_catalog
					and tc.constraint_schema = rc.constraint_schema
					and tc.constraint_name = rc.constraint_name
            		and tc.table_name = rc.table_name
				inner join (select * from information_schema.table_constraints
					where constraint_type not in ('FOREIGN KEY', 'CHECK')
					and constraint_schema = '!!$db_name!!'
					) as tc_uq
					on tc_uq.constraint_catalog = rc.unique_constraint_catalog
					and tc_uq.constraint_schema = rc.unique_constraint_schema
					and tc_uq.constraint_name = rc.unique_constraint_name
            		and tc_uq.table_name = rc.referenced_table_name
				inner join information_schema.key_column_usage as cu
					on cu.constraint_catalog = tc.constraint_catalog
					and cu.constraint_schema = tc.constraint_schema
					and cu.constraint_name = tc.constraint_name
            		and cu.table_schema = tc.table_schema
					and cu.table_name = tc.table_name
				inner join information_schema.key_column_usage as cu_uq
					on cu_uq.constraint_catalog = tc_uq.constraint_catalog
					and cu_uq.constraint_schema = tc_uq.constraint_schema
					and cu_uq.constraint_name = tc_uq.constraint_name
					and cu_uq.table_schema = tc_uq.table_schema
            		and cu_uq.table_name = tc_uq.table_name
					and cu_uq.ordinal_position = cu.ordinal_position
			where
				rc.table_name = '!!#table!!'
				;

			-- Narrow the list down to ONLY dependencies that affect PK columns
			-- Include not just the PK columns themselves, but ALL columns included in FKs
			-- that include ANY PK columns (probably rare/unlikely that a non-PK column would be
			-- part of the same foreign key as a PK column, but this ensures that ALL columns of the FK
			-- are included, whether or not the column is part of the PK)
			-- !x! if(table_exists(ups_pkcol_deps))
				drop table if exists ups_pkcol_deps cascade;
			-- !x! endif
			create table ups_pkcol_deps
			select
				refs.*
			from
				ups_fkcol_refs as refs
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
			-- !x! if(table_exists(ups_pkfk_ctrl))
				drop table if exists ups_pkfk_ctrl cascade;
			-- !x! endif
			create table ups_pkfk_ctrl
			select
				fk_constraint,
				table_name, parent_table,
				min(parent_column) as any_referenced_column,
				'!!@old_pkcol_aliased!!' as old_pkcol_aliased,
				'!!@new_pkcol!!' as new_pkcol,
				'!!@all_newpk_col_not_empty!!' as all_newpk_col_not_empty,
				False as processed
			from ups_pkcol_deps
			group by
				fk_constraint, table_name, parent_table
			;

			-- Create a view to select one constraint to process.
			-- !x! if(view_exists(ups_next_fk))
				drop view if exists ups_next_fk cascade;
			-- !x! endif
			create view ups_next_fk as
			select *
			from ups_pkfk_ctrl
			where not processed
			limit 1
			;

			--Process all constraints: check every foreign key
			--!x! execute script updtpkqa_one_innerloop with (stage_pfx=!!#stage_pfx!!, qaerror_table=!!#qaerror_table!!, display_errors=!!#display_errors!!)
		-- !x! endif
	-- !x! endif
-- !x! endif

-- !x! if(table_exists(ups_missing_pk_cols))
	drop table if exists ups_missing_pk_cols cascade;
-- !x! endif
-- !x! if(table_exists(ups_pkqa_str_lib))
	drop table if exists ups_pkqa_str_lib;
-- !x! endif
-- !x! if(table_exists(ups_any_pk_cols))
	drop table if exists ups_any_pk_cols cascade;
-- !x! endif
-- !x! if(table_exists(ups_empty_pk_cols))
	drop table if exists ups_empty_pk_cols cascade;
-- !x! endif
-- !x! if(view_exists(ups_empty_pk_cols_rwcnt))
	drop view if exists ups_empty_pk_cols_rwcnt cascade;
-- !x! endif
-- !x! if(table_exists(ups_old_pks_wc))
	drop table if exists ups_old_pks_wc cascade;
-- !x! endif
-- !x! if(table_exists(ups_invalid_old_pks))
	drop table if exists ups_invalid_old_pks cascade;
-- !x! endif
-- !x! if(view_exists(ups_invalid_pk_rwcnt))
	drop view if exists ups_invld_pk_rwcnt cascade;
-- !x! endif
-- !x! if(table_exists(ups_existing_new_pks))
	drop table if exists ups_existing_new_pks cascade;
-- !x! endif
-- !x! if(view_exists(ups_exst_nwpk_rwcnt))
	drop view if exists ups_exst_nwpk_rwcnt cascade;
-- !x! endif
-- !x! if(table_exists(ups_pk_mapping_conflict))
	drop table if exists ups_pk_mapping_conflict cascade;
-- !x! endif
-- !x! if(view_exists(ups_map_conf_rwcnt))
	drop view if exists ups_map_conf_rwcnt cascade;
-- !x! endif
-- !x! if(table_exists(ups_pk_duplicate_keys))
	drop table if exists ups_pk_duplicate_keys cascade;
-- !x! endif
-- !x! if(view_exists(ups_dup_key_rwcnt))
	drop view if exists ups_dup_key_rwcnt cascade;
-- !x! endif
-- !x! if(table_exists(ups_fkcol_refs))
	drop table if exists ups_fkcol_refs cascade;
-- !x! endif
-- !x! if(table_exists(ups_pkcol_deps))
	drop table if exists ups_pkcol_deps cascade;
-- !x! endif
-- !x! if(table_exists(ups_pkfk_ctrl))
	drop table if exists ups_pkfk_ctrl cascade;
-- !x! endif
-- !x! if(view_exists(ups_next_fk))
	drop view if exists ups_next_fk cascade;
-- !x! endif

-- !x! END SCRIPT
-- ###################  UPDTPKQA_ONE  ########################
-- ################################################################
--			Script UPDTPKQA_ONE_INNERLOOP
-- ----------------------------------------------------------------
-- !x! BEGIN SCRIPT UPDTPKQA_ONE_INNERLOOP with parameters(stage_pfx, qaerror_table, display_errors)
-- !x! if(hasrows(ups_next_fk))

	-- !x! select_sub ups_next_fk

	-- Compile FK info for the selected constraint
	-- !x! if(table_exists(ups_sel_fk_cols))
		drop table if exists ups_sel_fk_cols cascade;
	-- !x! endif
	create table ups_sel_fk_cols
	select
		fk_constraint, table_name,
		parent_table,
		group_concat(parent_column order by column_name separator ', ') as referenced_cols,
		group_concat('s.new_' || column_name || '=' || 'b.' || parent_column order by column_name separator ' and ') as join_condition
	from ups_pkcol_deps
	where fk_constraint='!!@fk_constraint!!'
	group by
		fk_constraint, table_name,
		parent_table
	;
	-- !x! select_sub ups_sel_fk_cols

	-- Construct SQL to check the selected FK
	-- !x! sub ~select_stmt create table ups_pk_fk_check select !!@old_pkcol_aliased!!, !!@new_pkcol!! from !!#stage_pfx!!!!@table_name!! as s
	-- !x! sub ~join_stmt left join !!@parent_table!! as b on !!@join_condition!!
	-- !x! sub ~where_clause where !!@all_newpk_col_not_empty!! and b.!!@any_referenced_column!! is null

	-- !x! sub ~fk_check !!~select_stmt!!
	-- !x! sub_append ~fk_check !!~join_stmt!!
	-- !x! sub_append ~fk_check !!~where_clause!!

	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "" to !!logfile!!
		-- !x! write "SQL for checking foreign key !!@fk_constraint!! for PK update to !!@table_name!!:" to !!logfile!!
		-- !x! write [!!~fk_check!!] to !!logfile!!
	-- !x! endif

	-- Run the check
	-- !x! if(table_exists(ups_pk_fk_check))
		drop table if exists ups_pk_fk_check cascade;
	-- !x! endif

	!!~fk_check!!;

	-- !x! if(hasrows(ups_pk_fk_check))

		-- !x! if(view_exists(ups_pk_fk_check_rwcnt))
			drop view if exists ups_pk_fk_check_rwcnt cascade;
		-- !x! endif
		create or replace view ups_pk_fk_check_rwcnt as
		select count(*) as rwcnt
		from ups_pk_fk_check
		;

		-- !x! subdata ~rowcount ups_pk_fk_check_rwcnt
		-- !x! sub ~error_description !!@parent_table!! (!!@referenced_cols!!): !!~rowcount!! row(s)

		-- !x! write "    Violation of foreign key !!@fk_constraint!! in new primary key columns in !!@stag_pfx!!!!@table_name!! referencing !!@parent_table!!: !!~rowcount!! row(s)"

		-- !x! if(view_exists(pk_fk_qa_error))
			drop view if exists ups_pk_fk_qa_error cascade;
		-- !x! endif
		create or replace view ups_pk_fk_qa_error as
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
			-- !x! write "Violation of foreign key !!@fk_constraint!! in new primary key columns in !!@stage_pfx!!!!@table_name!! referencing !!@parent_table!!: !!~rowcount!! row(s)" to !!logfile!!
			-- !x! if(sub_defined(log_errors))
			-- !x! andif(is_true(!!log_errors!!))
				-- !x! export ups_pk_fk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Violation of foreign key !!@fk_constraint!! in  new primary key columns in !!@stage_pfx!!!!@table_name!! referencing !!@parent_table!!" display ups_pk_fk_check
		-- !x! endif

	-- !x! endif

	-- Mark constraint as processed
	update ups_pkfk_ctrl
	set processed=True
	where fk_constraint='!!@fk_constraint!!';

	-- !x! if(table_exists(ups_sel_fk_cols))
		drop table if exists ups_sel_fk_cols cascade;
	-- !x! endif
	-- !x! if(table_exists(ups_pk_fk_check))
		drop table if exists ups_pk_fk_check cascade;
	-- !x! endif
	-- !x! if(view_exists(ups_pk_fk_check_rwcnt))
		drop view if exists ups_pk_fk_check_rwcnt cascade;
	-- !x! endif
	-- !x! if(view_exists(pk_fk_qa_error))
		drop view if exists ups_pk_fk_qa_error cascade;
	-- !x! endif

	--LOOP
	-- !x! execute script updtpkqa_one_innerloop with (stage_pfx=!!#stage_pfx!!, qaerror_table=!!#qaerror_table!!, display_errors=!!#display_errors!!)

-- !x! endif

-- !x! END SCRIPT
-- ####################  End of UPDTPKQA_ONE  ########################
-- ################################################################
