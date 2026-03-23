-- ss_upsert.sql
--
-- PURPOSE
--	A set of execsql scripts to check data in a staging table, or
--	a set of staging tables, and then update and insert rows of a base table
--	or base tables from the staging table(s) of the same name.
--
--	This script contains code specific to Microsoft SQL Server. It was developed
--	and tested using SQL Server 2017 Developer, and also tested against SQL Server 2016.
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
--	3. These scripts were developed for Microsoft SQL Server; they were developed
--		and tested using SQL Server 2017 Developer Edition, and also tested using
--		Microsoft SQL Server 2016 Professional; they will likely require
--		modification to run on other DBMSs, or with earlier versions of SQL Server.
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
--	8. These scripts create temporary tables.  All of these
--		have prefixes of "ups_".  Scripts that include this file
--		should not use this prefix to avoid possible conflicts.
--
-- COPYRIGHT AND LICENSE
--	Copyright (c) 2019, Elizabeth Shea
--	This program is free software: you can redistribute it and/or modify it
--	under the terms of the GNU General Public License as published by the
--	Free Software Foundation, either version 3 of the License, or (at your
--	option) any later version. This program is distributed in the hope that
--	it will be useful, but WITHOUT ANY WARRANTY; without even the implied
--	warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
--	GNU General Public License for more details. The GNU General Public
--	License is available at http://www.gnu.org/licenses/.

-- AUTHORS
--  Elizabeth Shea (ES)
--	Dreas Nielsen (RDN)
--
-- VERSION
--	2.0.0
--
-- HISTORY
--	 Date		 Remarks
--	-----------	 -----------------------------------------------------
--  2019-02-17	 Created. Began adapting from pg_upsert.sql (version
--				 for PostgresSQL). ES.
--  2019-03-03	 Completed first draft. ES.
--	2019-03-07	Added primary key check and fixed console progress bar
--				for QA checks. ES.
--  2019-03-08	Updated header. ES.
--	2019-03-09	Minor updates and corrections to address RDN comments.
--				ES.
--	2019-03-13	Added definition and execution of validation scripts
--				to validate base and staging schemas and tables. ES.
--	2019-03-14	Streamlined execution of validation scripts. ES.
--	2019-05-01	Replaced one instance of 'trim()' with 'rtrim(ltrim())'.  RDN.
--  2019-05-08	Added notes on primary key update script to header
--				and added script UPDATEPK_ONE.
--				Made edit to selection of #ups_cols in script UPSERT_ONE
--				to prevent an error if the staging table contains any
--				columns that are not in the base table (e.g., "new" cols
--				for PK updates). ES.
--	2019-05-10	Changed name of PK update script; added header notes for
--				PK update QA script. Changed table_name length in
--				control table from 8000 to 1700, max key length for a
--				nonclustered index. ES.
--	2019-05-14	Added script UPDTPKQA_ONE and some (not all) QA checks. ES.
--  2019-05-21	Completed first draft of UPDTPKQA_ONE. ES.
--  2019-05-22	Rearranged, organized, and standardized variable names
--				in UPDTPKQA_ONE. ES.
--	2019-05-29	Corrections to comments. ES.
--	2019-06-03	Correction to logging in UPDTPKQA_ONE_INNERLOOP. ES.
--	2020-04-28	Explicitly rolled back the changes if 'do_commit' = "No".  RDN.
--	2020-05-09	Moved the assignment of 'upsert_progress_denom' out of the
--				'update_console_qa' script.  RDN.
-- ==================================================================

-- ################################################################
--			Script TEMPTABLE_ISVALID
-- ===============================================================
--
-- Utility script to validate SQL Server temp table name.
-- Confirms that the name passed by the user is prefixed with a '#',
-- and raises an error if not
--
-- Input parameters:
--		temptable_name	: The name of the temporary table to be created.
--
-- Columns in the table created:
--		temptbl_name	 : The name of the temp table to be created by
--						  the calling script.
--
--
-- Example:
--		-- !x! execute script temp_table_isvalid with (temptable_name=#stagingtables)
-- ===============================================================
-- !x! BEGIN SCRIPT TEMPTABLE_ISVALID with parameters (temptable_name)

-- Take the user-provided temp_table argument and validate syntax
if object_id('tempdb..#tmptbl_name') is not null drop table #tmptbl_name;
select
	case when left('!!#temptable_name!!',1) = '#'
		then 1
		else 0
		end as temptbl_name
into #tmptbl_name
;
-- !x! subdata ~valid_tmptable #tmptbl_name
-- !x! if(is_zero(!!~valid_tmptable!!))
	-- !x! sub ~message Error in SQL Server temporary table name assignment, script !!$CURRENT_SCRIPT!!, line !!$SCRIPT_LINE!!.
	-- !x! sub_append ~message The name "!!#temptable_name!!" is not a valid SQL Server temporary table name.
	-- !x! sub_append ~message Temporary table names must include a '#' prefix (e.g., '#mytable')
	-- !x! halt message "!!~message!!"
-- !x! endif

-- !x! END SCRIPT
-- ##################  End of TEMPTABLE_ISVALID  #####################
-- ################################################################


-- ################################################################
--			Script STRING_AGG
-- ===============================================================
--
-- Utility script to perform string aggregation
-- Beginning with 2017 edition, SQL Server *does* include the string_agg()
-- function, but earlier versions do not.
--
-- Input parameters:
--		table_name	: The name of the table containing the column to be aggregated.
--						This may be a temp table containing pre-processed strings.
--		string_col  : The name of the column to be aggregated.
--		order_col   : The name of the column to order by
--      delimiter   : Character to be used as a delimiter
--		string_var  : Name of variable to which aggregated string will be assigned
--
--	Output parameters:
--		string_var	: The name of the variable to receive the aggregated string.
--
--
-- Example:
--		-- !x! execute script string_agg with (table_name=#nonnulcols, string_col=null_errors, order_col=null_errors, delimiter=", ", string_var=+nullcols)
-- ===============================================================
-- !x! BEGIN SCRIPT STRING_AGG with parameters (table_name, string_col, order_col, delimiter, string_var)

if object_id('tempdb..#agg_string') is not null drop table #agg_string;
with enum as
	(
	select
		cast(!!#string_col!! as varchar(max)) as agg_string,
		row_number() over (order by !!#order_col!!) as row_num
	from
		!!#table_name!!
	),
agg as
	(
	select
		one.agg_string,
		one.row_num
	from
		enum as one
	where
		one.row_num=1
	UNION ALL
	select
		agg.agg_string + '!!#delimiter!!' + enum.agg_string as agg_string,
		enum.row_num
	from
		agg, enum
	where
		enum.row_num=agg.row_num+1
	)
select
agg_string
into #agg_string
from agg
where row_num=(select max(row_num) from agg);
-- !x! if(hasrows(#agg_string))
	-- !x! subdata !!#string_var!! #agg_string
-- !x! endif

-- !x! END SCRIPT
-- ##################  End of STRING_AGG  #####################
-- ################################################################


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

if object_id('tempdb..#ups_ctrl_invl_schema') is not null drop table #ups_ctrl_invl_schema;
select
	schemas.schema_name,
	schemas.schema_type,
	schemas.schema_name + ' (' + schema_type + ')' as schema_string
into #ups_ctrl_invl_schema
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
;

-- !x! if(hasrows(#ups_ctrl_invl_schema))
	-- !x! execute script string_agg with (table_name=#ups_ctrl_invl_schema, string_col=schema_string, order_col=schema_type, delimiter='; ', string_var=!!#error_list!!)
-- !x! endif

-- !x! END SCRIPT
-- ####################  End of VALIDATE_SCHEMAS  #################
-- ################################################################


-- ################################################################
--			Script VALIDATE_ONE
-- ===============================================================
--
-- Utility script to validate one table in both base and staging schema
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
	if object_id('tempdb..#ups_invl_table') is not null drop table #ups_invl_table;
	select
		tt.schema_name,
		tt.schema_type,
		tt.schema_name + '.' + tt.table_name + ' (' + tt.schema_type + ')' as schema_table
	into #ups_invl_table
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
	;

	-- !x! if(hasrows(#ups_invl_table))
		-- !x! execute script string_agg with (table_name=#ups_invl_table, string_col=schema_table, order_col=schema_table, delimiter='; ', string_var=+err_info)
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
-- Utility script to validate contents of control table against about
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
	if object_id('tempdb..#ups_validate_control') is not null drop table #ups_validate_control;
	select
		'!!#base_schema!!' as base_schema,
		'!!#staging!!' as staging_schema,
		table_name,
		cast(0 as bit) as base_exists,
		cast(0 as bit) as staging_exists
	into #ups_validate_control
	from !!#control_table!!
	;

	-- Update the control table
	update vc
		set base_exists = cast(case when bt.table_name is null then 0 else 1 end as bit),
			staging_exists = cast(case when st.table_name is null then 0 else 1 end as bit)
	from #ups_validate_control as vc
			left join information_schema.tables as bt on vc.base_schema=bt.table_schema and vc.table_name=bt.table_name
				and bt.table_type='BASE TABLE'
			left join information_schema.tables as st on vc.staging_schema=st.table_schema and vc.table_name=st.table_name
				and st.table_type='BASE TABLE'
	;

	if object_id('tempdb..#ups_ctrl_invl_table') is not null drop table #ups_ctrl_invl_table;
		select
			schema_table
	into #ups_ctrl_invl_table
	from
			(
			select base_schema + '.' + table_name as schema_table
			from #ups_validate_control
			where not base_exists=1
			union
			select staging_schema + '.' + table_name as schema_table
			from #ups_validate_control
			where not staging_exists=1
			) as it
	;

	-- Any table is invalid
	-- !x! if(hasrows(#ups_ctrl_invl_table))
		-- !x! execute script string_agg with (table_name=#ups_ctrl_invl_table, string_col=schema_table, order_col=schema_table, delimiter='; ', string_var=+err_info)
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
--							In SQL Server, this *must* include a '#'
--							prefix. A validation step will raise
--							an error if an invalid temp table name is passed.
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
--		-- !x! execute script staged_to_load with (control_table=#stagingtables, table_list="tbla, tblb, tblc")
-- ===============================================================

-- !x! BEGIN SCRIPT STAGED_TO_LOAD with parameters (control_table, table_list)

-- Run script to validate that control table name is valid temp table name
-- !x! execute script temptable_isvalid with args (temptable_name=!!#control_table!!)


if object_id('tempdb..!!#control_table!!') is not null drop table !!#control_table!!;
create table !!#control_table!! (
	table_name varchar(1700) not null unique,
	exclude_cols varchar(8000),
	exclude_null_checks varchar(8000),
	display_changes varchar(3) not null default 'Yes',
	display_final varchar(3) not null default 'No',
	null_errors varchar(8000),
	pk_errors varchar(8000),
	fk_errors varchar(8000),
	rows_updated integer,
	rows_inserted integer,
	check (display_changes in ('Yes', 'No')),
	check (display_final in ('Yes', 'No'))
);


-- Recursive CTE to parse table list argument
-- NOTE: SQL Server 2017 includes the trim() function, but SQL Server 2016 does not,
-- so a combination of ltrim and rtrim is used here instead.
with itemtable as (
	select
		case when charindex(',',  table_string) = 0
			then rtrim(ltrim(table_string))
			else rtrim(ltrim(substring(table_string, 1,charindex(',', table_string)-1)))
			end as table_name,
		case when charindex(',',  table_string) = 0
			then NULL
			else rtrim(ltrim(substring(table_string, charindex(',', table_string)+1, len(table_string))))
			end as remaining_list
	from
		(select '!!#table_list!!' as table_string) as ts
	UNION ALL
	select
		case when charindex(',', remaining_list) = 0
			then rtrim(ltrim(remaining_list))
			else rtrim(ltrim(substring(remaining_list, 1,charindex(',', remaining_list)-1)))
			end as table_name,
		case when charindex(',',  remaining_list) = 0
			then NULL
			else rtrim(ltrim(substring(remaining_list, charindex(',', remaining_list)+1, len(remaining_list))))
			end as remaining_list
	from
		itemtable
	where
		remaining_list is not null
		--Guards against entries with trailing commas:
		-- e.g,  'table1, table2,'
		and rtrim(ltrim(remaining_list))<>''
	)
insert into !!#control_table!!
	(table_name)
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
--		control_table	: The name of a temporary table as created by the
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
--		#ups_qa_fails			: temporary table
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
if object_id('tempdb..#ups_qa_fails') is not null drop table #ups_qa_fails;
select *
into #ups_qa_fails
from !!#control_table!!
where null_errors is not null or pk_errors is not null or fk_errors is not null;
-- !x! if(not hasrows(#ups_qa_fails))
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
--		#ups_nonnull_cols		: temporary table
--		#ups_next_column		: temporary table
--		#ups_null_error_list	: temporary table
--		#ups_qa_nonnull_col		: temporary table
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
if object_id('tempdb..#ups_nonnull_cols') is not null drop table #ups_nonnull_cols;
select
	column_name,
	cast(0 as integer) as null_rows,
	cast(0 as bit) as processed
into
	#ups_nonnull_cols
from
	information_schema.columns
where
	table_schema = '!!#base_schema!!'
	and table_name = '!!#table!!'
	and is_nullable = 'NO'
	and column_default is null
	!!~omitnull!!
;


-- Create a script to select one column to process.
-- !x! begin script ups_get_next_column
if object_id('tempdb..#ups_next_column') is not null drop table #ups_next_column;
select top 1 column_name
into #ups_next_column
from #ups_nonnull_cols
where not processed=1;
-- !x! end script

-- Process all non-nullable columns.
-- !x! execute script nullqa_one_innerloop with (staging=!!#staging!!, table=!!#table!!)

-- Create the return value
if object_id('tempdb..#ups_null_error_list') is not null drop table #ups_null_error_list;
select
	column_name + ' (' + cast(null_rows as varchar(max)) + ')' as prepped_col
into #ups_null_error_list
from
	#ups_nonnull_cols
where
	coalesce(null_rows, 0) > 0
;
-- !x! execute script string_agg with (table_name="#ups_null_error_list", string_col=prepped_col, order_col=prepped_col, delimiter=", ", string_var=!!#error_list!!)


-- !x! END SCRIPT
-- End of          NULLQA_ONE
-- ****************************************************************
-- ****************************************************************
-- ****************************************************************
--			Script NULLQA_ONE_INNERLOOP
-- ---------------------------------------------------------------
-- !x! BEGIN SCRIPT NULLQA_ONE_INNERLOOP with parameters (staging, table)

-- !x! execute script ups_get_next_column
-- !x! if(hasrows(#ups_next_column))
	-- !x! subdata ~column_name #ups_next_column

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking column !!~column_name!!." to !!logfile!!
	-- !x! endif

	if object_id('tempdb..#ups_qa_nonnull_col') is not null drop table #ups_qa_nonnull_col;
	select top 1 nrows
	into #ups_qa_nonnull_col
	from (
		select count(*) as nrows
		from !!#staging!!.!!#table!!
		where !!~column_name!! is null
		) as nullcount
	where nrows > 0;
	-- !x! if(hasrows(#ups_qa_nonnull_col))
		-- !x! subdata ~nullrows #ups_qa_nonnull_col
		-- !x! write "    Column !!~column_name!! has !!~nullrows!! nulls."
		-- !x! if(sub_defined(logfile))
			-- !x! write "    Column !!~column_name!! has !!~nullrows!! nulls." to !!logfile!!
		-- !x! endif
		update #ups_nonnull_cols
		set null_rows = (select top 1 nrows from #ups_qa_nonnull_col)
		where column_name = '!!~column_name!!';
	-- !x! endif


	-- Mark this constraint as processed.
	update #ups_nonnull_cols
	set processed = 1
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
--		#ups_primary_key_columns		: temporary table
--		#ups_pk_check					: temporary table
--		#ups_ercnt						: temporary table
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
if object_id('tempdb..#ups_primary_key_columns') is not null drop table #ups_primary_key_columns;
select k.constraint_name, k.column_name, k.ordinal_position
into #ups_primary_key_columns
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

-- !x! if(hasrows(#ups_primary_key_columns))
	-- !x! subdata ~constraint_name #ups_primary_key_columns

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking constraint !!~constraint_name!!." to !!logfile!!
	-- !x! endif

	-- Get a comma-delimited list of primary key columns to build SQL selection for duplicate keys
	-- !x! sub_empty ~pkcollist
	-- !x! execute script string_agg with (table_name=#ups_primary_key_columns, string_col=column_name, order_col=ordinal_position, delimiter=", ", string_var=+pkcollist)

	-- Construct a query to test for duplicate values for pk columns.
	-- !x! sub 			  ~pk_check   if object_id('tempdb..#ups_pk_check') is not null drop table #ups_pk_check;
	-- !x! sub_append     ~pk_check   select !!~pkcollist!!, count(*) as row_count
	-- !x! sub_append     ~pk_check   into #ups_pk_check
	-- !x! sub_append     ~pk_check   from !!#staging!!.!!#table!! as s
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
	!!~pk_check!!;
	-- !x! if(hasrows(#ups_pk_check))
		-- !x! write "    Duplicate key error on columns: !!~pkcollist!!."
		if object_id('tempdb..#ups_ercnt') is not null drop table #ups_ercnt;
		select count(*) as errcnt, sum(row_count) as total_rows
		into #ups_ercnt
		from #ups_pk_check;
		-- !x! select_sub #ups_ercnt
		-- !x! sub !!#error_list!! !!@errcnt!! duplicated key(s) (!!@total_rows!! rows)
		-- !x! if(sub_defined(logfile))
			-- !x! write "Duplicate primary key values in !!#staging!!.!!#table!!" to !!logfile!!
			-- !x! if(sub_defined(log_errors))
			-- !x! andif(is_true(!!log_errors!!))
				-- !x! export #ups_pk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Primary key violations in !!#table!!" display #ups_pk_check
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
--		ups_next_constraint			: temporary table
--		ups_fk_error_list			: temporary table
--		ups_one_fk					: temporary table
--		ups_fk_joins				: temporary table
--		ups_fk_check				: temporary table
--		ups_ercnt					: temporary table
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
if object_id('tempdb..#ups_foreign_key_columns') is null
select
	rc.constraint_name,
	cu.table_schema,
	cu.table_name,
	cu.column_name,
	cu.ordinal_position,
	cu_uq.table_schema as uq_schema,
	cu_uq.table_name as uq_table,
	cu_uq.column_name as uq_column
into #ups_foreign_key_columns
from
	(select distinct constraint_catalog, constraint_schema, constraint_name,
		unique_constraint_catalog, unique_constraint_schema, unique_constraint_name
		from information_schema.referential_constraints) as rc
	inner join (select * from information_schema.table_constraints
		where constraint_type = 'FOREIGN KEY') as tc
		on tc.constraint_catalog = rc.constraint_catalog
		and tc.constraint_schema = rc.constraint_schema
		and tc.constraint_name = rc.constraint_name
	inner join (select * from information_schema.table_constraints
		where constraint_type not in ('FOREIGN KEY', 'CHECK') ) as tc_uq
		on tc_uq.constraint_catalog = rc.unique_constraint_catalog
		and tc_uq.constraint_schema = rc.unique_constraint_schema
		and tc_uq.constraint_name = rc.unique_constraint_name
	inner join information_schema.key_column_usage as cu
		on cu.constraint_catalog = tc.constraint_catalog
		and cu.constraint_schema = tc.constraint_schema
		and cu.constraint_name = tc.constraint_name
		and cu.table_catalog = tc.table_catalog
		and cu.table_schema = tc.table_schema
		and cu.table_name = tc.table_name
	inner join information_schema.key_column_usage as cu_uq
		on cu_uq.constraint_catalog = tc_uq.constraint_catalog
		and cu_uq.constraint_schema = tc_uq.constraint_schema
		and cu_uq.constraint_name = tc_uq.constraint_name
		and cu_uq.table_catalog = tc_uq.table_catalog
		and cu_uq.table_schema = tc_uq.table_schema
		and cu_uq.ordinal_position = cu.ordinal_position
;


-- Create a temporary table of just the foreign key relationships for the base
-- table corresponding to the staging table to check.
if object_id('tempdb..#ups_sel_fks') is not null drop table #ups_sel_fks;
select
	constraint_name, column_name,
	ordinal_position,
	uq_schema, uq_table, uq_column
into #ups_sel_fks
from
	#ups_foreign_key_columns
where
	table_schema = '!!#base_schema!!'
	and table_name = '!!#table!!';

-- Create a temporary table of all unique constraint names for
-- this table, with an integer column to be populated with the
-- number of rows failing the foreign key check, and a 'processed'
-- 	flag to control looping.
if object_id('tempdb..#ups_fk_constraints') is not null drop table #ups_fk_constraints;
select distinct
	constraint_name,
	cast(0 as integer) as fkerror_rows,
	cast(0 as bit) as processed
into #ups_fk_constraints
from #ups_sel_fks;

-- Create a script to select one constraint to process
-- !x! begin script ups_get_next_constraint
if object_id('tempdb..#ups_next_constraint') is not null drop table #ups_next_constraint;
select top 1 constraint_name
into #ups_next_constraint
from #ups_fk_constraints
where not processed=1;
-- !x! end script


-- Process all constraints: check every foreign key.
-- !x! execute script fk_qa_one_innerloop with (staging=!!#staging!!, table=!!#table!!, display_errors=!!#display_errors!!)

-- Create the return value.
if object_id('tempdb..#ups_fk_error_list') is not null drop table #ups_fk_error_list;
select
	constraint_name + ' (' + cast(fkerror_rows as varchar(max)) + ')' as fkc_errors,
	constraint_name
into #ups_fk_error_list
from #ups_fk_constraints
where coalesce(fkerror_rows, 0) > 0;

-- !x! execute script string_agg with (table_name=#ups_fk_error_list, string_col=fkc_errors, order_col=constraint_name, delimiter=", ", string_var=!!#error_list!!)

-- !x! END SCRIPT
-- End of          FKQA_ONE
-- ****************************************************************
-- ****************************************************************
--			Script FK_QA_ONE_INNERLOOP
-- ----------------------------------------------------------------
-- !x! BEGIN SCRIPT FK_QA_ONE_INNERLOOP with parameters (staging, table, display_errors)

-- !x! execute script ups_get_next_constraint
-- !x! if(hasrows(#ups_next_constraint))
	-- !x! subdata ~constraint_name #ups_next_constraint

	-- !x! if(sub_defined(logfile))
		-- !x! write "Checking constraint !!~constraint_name!!." to !!logfile!!
	-- !x! endif


	if object_id('tempdb..#ups_one_fk') is not null drop table #ups_one_fk;
	select column_name, uq_schema, uq_table, uq_column, ordinal_position
	into #ups_one_fk
	from #ups_sel_fks
	where
		constraint_name = '!!~constraint_name!!';

	-- Get the unique table schema and name into data variables.
	-- !x! select_sub #ups_one_fk

	-- Create join expressions from staging table (s) to unique table (u)
	-- and to staging table equivalent to unique table (su) (though we
	-- don't know yet if the latter exists).  Also create a 'where'
	-- condition to ensure that all columns being matched are non-null.
	-- Also create a comma-separated list of the columns being checked.
	if object_id('tempdb..#ups_fk_joins') is not null drop table #ups_fk_joins;
	select
		cast('s.' + column_name + ' = u.' + uq_column as varchar(max)) as u_join,
		cast('s.' + column_name + ' = su.' + uq_column as varchar(max)) as su_join,
		cast('s.' + column_name + ' is not null' as varchar(max)) as s_not_null,
		cast('s.' + column_name as varchar(max)) as s_checked,
		ordinal_position
	into #ups_fk_joins
	from
		#ups_one_fk;

	-- Create local variables for the different parts of the join expressions
	-- !x! sub_empty ~u_join
	-- !x! sub_empty ~su_join
	-- !x! sub_empty ~s_not_null
	-- !x! sub_empty ~s_checked

	-- Then populate them using the string aggregation script
	-- !x! execute script string_agg with(table_name=#ups_fk_joins, string_col=u_join, order_col=ordinal_position, delimiter =" and ", string_var=+u_join)
	-- !x! execute script string_agg with(table_name=#ups_fk_joins, string_col=su_join, order_col=ordinal_position, delimiter =" and ", string_var=+su_join)
	-- !x! execute script string_agg with(table_name=#ups_fk_joins, string_col=s_not_null, order_col=ordinal_position, delimiter =" and ", string_var=+s_not_null)
	-- !x! execute script string_agg with(table_name=#ups_fk_joins, string_col=s_checked, order_col=ordinal_position, delimiter =", ", string_var=+s_checked)


	-- Determine whether a staging-table equivalent of the unique table exists.
	-- !x! sub su_exists No
	-- !x! if(table_exists(!!#staging!!.!!@uq_table!!))
		-- !x! sub su_exists Yes
	-- !x! endif

	-- Construct a query to test for missing unique values for fk columns.
	-- !x! sub 			  ~fk_check   if object_id('tempdb..#ups_fk_check') is not null drop table #ups_fk_check;
	-- !x! sub_append     ~fk_check   select !!~s_checked!!, count(*) as row_count
	-- !x! sub_append     ~fk_check   into #ups_fk_check
	-- !x! sub_append     ~fk_check   from !!#staging!!.!!#table!! as s
	-- !x! sub_append     ~fk_check   left join !!@uq_schema!!.!!@uq_table!! as u on !!~u_join!!
	-- !x! if(is_true(!!su_exists!!))
		-- !x! sub_append ~fk_check   left join !!#staging!!.!!@uq_table!! as su on !!~su_join!!
	-- !x! endif
	-- !x! sub_append     ~fk_check   where u.!!@uq_column!! is null
	-- !x! if(is_true(!!su_exists!!))
		-- !x! sub_append ~fk_check   and su.!!@uq_column!! is null
	-- !x! endif
	-- !x! sub_append     ~fk_check   and !!~s_not_null!!
	-- !x! sub_append     ~fk_check   group by !!~s_checked!!

	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "SQL for foreign key check:" to !!logfile!!
		-- !x! write [!!~fk_check!!] to !!logfile!!
	-- !x! endif

	-- Run the check.
	!!~fk_check!!;
	-- !x! if(hasrows(#ups_fk_check))
		-- !x! write "    Foreign key error referencing !!@uq_table!!."
		if object_id('tempdb..#ups_ercnt') is not null drop table #ups_ercnt;
		select count(*) as ercnt
		into #ups_ercnt
		from #ups_fk_check;
		-- !x! subdata ~errcnt #ups_ercnt
		update #ups_fk_constraints
		set fkerror_rows = !!~errcnt!!
		where constraint_name = '!!~constraint_name!!';
		-- !x! if(sub_defined(logfile))
			-- !x! write " Foreign key errors in !!#table!! referencing !!@uq_table!!" to !!logfile!!
			-- !x! if(sub_defined(log_errors))
			-- !x! andif(is_true(!!log_errors!!))
				-- !x! export #ups_fk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Foreign key errors in !!#table!! referencing !!@uq_table!!" display #ups_fk_check
		-- !x! endif
	-- !x! endif


	-- Mark this constraint as processed.
	update #ups_fk_constraints
	set processed = 1
	where constraint_name = '!!~constraint_name!!';

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
--							column names within enclosing double quotes,
--							identifying the columns
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
--		ups_allcollist			: temporary table
--		ups_allbasecollist		: temporary table
--		ups_allstgcollist		: temporary table
--		ups_pkcollist			: temporary table
--		ups_joinexpr			: temporary table
--		ups_basematches			: temporary table
--		ups_stgmatches			: temporary table
--		ups_nk					: temporary table
--		ups_assexpr				: temporary table
--		ups_newrows				: temporary table
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
if object_id('tempdb..#ups_cols') is not null drop table #ups_cols;
select s.column_name, s.ordinal_position
into #ups_cols
from
	information_schema.columns as s
	inner join information_schema.columns as b on s.column_name=b.column_name
where
	s.table_schema = '!!#staging!!'
	and s.table_name = '!!#table!!'
	and b.table_schema = '!!#base_schema!!'
	and b.table_name = '!!#table!!'
	!!~col_excl!!
;


-- Populate a (temporary) table with the names of the primary key
-- columns of the base table.
if object_id('tempdb..#ups_pks') is not null drop table #ups_pks;
select k.column_name, k.ordinal_position
into #ups_pks
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

-- Get all base table columns that are to be updated into a comma-delimited list.
if object_id('tempdb..#ups_allcollist') is not null drop table #ups_allcollist;
select
	cast(column_name as varchar(max)) as column_list,
	ordinal_position
into #ups_allcollist
from #ups_cols
;
-- !x! sub_empty ~allcollist
-- !x! execute script string_agg with(table_name=#ups_allcollist, string_col=column_list, order_col=ordinal_position, delimiter=", ", string_var=+allcollist)


-- Get all base table columns that are to be updated into a comma-delimited list
-- with a "b." prefix.
if object_id('tempdb..#ups_allbasecollist') is not null drop table #ups_allbasecollist;
select
	cast('b.' + column_name as varchar(max)) as column_list,
	ordinal_position
into #ups_allbasecollist
from #ups_cols;
-- !x! sub_empty ~allbasecollist
-- !x! execute script string_agg with(table_name=#ups_allbasecollist, string_col=column_list, order_col=ordinal_position, delimiter=", ", string_var=+allbasecollist)


-- Get all staging table column names for columns that are to be updated
-- into a comma-delimited list with an "s." prefix.
if object_id('tempdb..#ups_allstgcollist') is not null drop table #ups_allstgcollist;
select
	cast('s.' + column_name as varchar(max)) as column_list,
	ordinal_position
into #ups_allstgcollist
from #ups_cols;
-- !x! sub_empty ~allstgcollist
-- !x! execute script string_agg with(table_name=#ups_allstgcollist, string_col=column_list, order_col=ordinal_position, delimiter=", ", string_var=+allstgcollist)


-- Get the primary key columns in a comma-delimited list.
if object_id('tempdb..#ups_pkcollist') is not null drop table #ups_pkcollist;
select
	cast(column_name as varchar(max)) as column_list,
	ordinal_position
into #ups_pkcollist
from #ups_pks;
-- !x! sub_empty ~pkcollist
-- !x! execute script string_agg with(table_name=#ups_pkcollist, string_col=column_list, order_col=ordinal_position, delimiter=", ", string_var=+pkcollist)


-- Create a join expression for key columns of the base (b) and
-- staging (s) tables.
if object_id('tempdb..#ups_joinexpr') is not null drop table #ups_joinexpr;
select
	cast('b.' + column_name + ' = s.' + column_name as varchar(max)) as column_list,
	ordinal_position
into #ups_joinexpr
from
	#ups_pks;
-- !x! sub_empty ~joinexpr
-- !x! execute script string_agg with(table_name=#ups_joinexpr, string_col=column_list, order_col=ordinal_position, delimiter=" and ", string_var=+joinexpr)


-- Create a FROM clause for an inner join between base and staging
-- tables on the primary key column(s).
-- !x! sub ~fromclause FROM !!#base_schema!!.!!#table!! as b INNER JOIN !!#staging!!.!!#table!! as s ON !!~joinexpr!!


-- Create SELECT queries to pull all columns with matching keys from both
-- base and staging tables.
if object_id('tempdb..#ups_basematches') is not null drop table #ups_basematches;
select !!~allbasecollist!!
into #ups_basematches
!!~fromclause!!;

if object_id('tempdb..#ups_stgmatches') is not null drop table #ups_stgmatches;
select !!~allstgcollist!!
into #ups_stgmatches
!!~fromclause!!;

--Get non-key columns to be updated
if object_id('tempdb..#ups_nk') is not null drop table #ups_nk;
select column_name
into #ups_nk
from
		(
		select column_name from #ups_cols
		except
		select column_name from #ups_pks
		) as nk
;


-- Prompt user to examine matching data and commit, don't commit, or quit.
-- !x! if(hasrows(#ups_stgmatches))
-- !x! andif(hasrows(#ups_nk))
	-- Prompt user to examine matching data and commit, don't commit, or quit.
	-- !x! if(is_true(!!#display_changes!!))
		-- !x! prompt ask "Do you want to make these changes? For table !!#table!!, new data are shown in the top table below; existing data are in the lower table." sub ~do_updates compare #ups_stgmatches and #ups_basematches key (!!~pkcollist!!)
	-- !x! endif
	-- !x! if(is_true(!!~do_updates!!))
		-- Create an assignment expression to update non-key columns of the
		-- base table (as b) from columns of the staging table (as s).
		if object_id('tempdb..#ups_assexpr') is not null drop table #ups_assexpr;
		select
			cast('b.' + column_name + ' = s.' + column_name as varchar(max)) as column_list
		into #ups_assexpr
		from #ups_nk;
		-- !x! sub_empty ~assexpr
		-- !x! execute script string_agg with(table_name=#ups_assexpr, string_col=column_list, order_col=column_list, delimiter=", ", string_var=+assexpr)
		-- Create an UPDATE statement to update the base table with
		-- non-key columns from the staging table.  No semicolon terminating generated SQL.
		-- !x! sub ~updatestmt UPDATE b SET !!~assexpr!! FROM !!#base_schema!!.!!#table!! as b INNER JOIN !!#staging!!.!!#table!! as s on !!~joinexpr!!
	-- !x! endif
-- !x! endif

-- Create a select statement to find all rows of the staging table
-- that are not in the base table.
if object_id('tempdb..#ups_newrows') is not null drop table #ups_newrows;
with newpks as (
	select !!~pkcollist!! from !!#staging!!.!!#table!!
	except
	select !!~pkcollist!! from !!#base_schema!!.!!#table!!
	)
select
	--s.*
	!!~allstgcollist!!
into #ups_newrows
from
	!!#staging!!.!!#table!! as s
	inner join newpks as b on !!~joinexpr!!;

-- Prompt user to examine new data and continue or quit.
-- !x! if(hasrows(#ups_newrows))
	-- !x! if(is_true(!!#display_changes!!))
		-- !x! prompt ask "Do you want to add these new data to the !!#base_schema!!.!!#table!! table?" sub ~do_inserts display #ups_newrows
	-- !x! endif

	-- !x! if(is_true(!!~do_inserts!!))
		-- Create an insert statement.  No semicolon terminating generated SQL.
		-- !x! sub ~insertstmt INSERT INTO !!#base_schema!!.!!#table!! (!!~allcollist!!) SELECT !!~allcollist!! FROM #ups_newrows
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
			-- !x! write [!!~updatestmt!!] to !!logfile!!
		-- !x! endif
		-- !x! if(sub_defined(log_changes))
		-- !x! andif(is_true(!!log_changes!!))
			-- !x! write "Updates:" to !!logfile!!
			-- !x! export #ups_stgmatches append to !!logfile!! as txt
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
			-- !x! write [!!~insertstmt!!] to !!logfile!!
		-- !x! endif
		-- !x! if(sub_defined(log_changes))
		-- !x! andif(is_true(!!log_changes!!))
			-- !x! write "New data:" to !!logfile!!
			-- !x! export #ups_newrows append to !!logfile!! as txt
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
--		ups_upsert_rows			: temporary table
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
	if object_id('tempdb..#ups_upsert_rows') is not null drop table #ups_upsert_rows;
	select count(*) + 1 as upsert_rows
	into #ups_upsert_rows
	from !!#control_table!!;
	-- !x! subdata upsert_progress_denom #ups_upsert_rows
-- !x! endif

-- Get a table of all dependencies for the base schema.
if object_id('tempdb..#ups_dependencies') is not null drop table #ups_dependencies;
select
	tc.table_name as child,
	tp.table_name as parent
into #ups_dependencies
from
	information_schema.table_constraints as tc
	inner join information_schema.referential_constraints as cu on tc.constraint_name=cu.constraint_name
	inner join information_schema.table_constraints as tp on tp.constraint_name=cu.unique_constraint_name
where
	tc.constraint_type = 'FOREIGN KEY'
	and tc.table_schema = '!!#base_schema!!'
	--Exclude cases where parent and child are same table (to protect against infinite recursion in table ordering)
	and tc.table_name<>tp.table_name;


-- Create a list of tables in the base schema ordered by dependency.
if object_id('tempdb..#ups_ordered_tables') is not null drop table #ups_ordered_tables;
with dep_depth as (
	select
		dep.child as first_child,
  		dep.child,
  		dep.parent,
  		1 as lvl
	from
		#ups_dependencies as dep
	union all
	select
		dd.first_child,
		dep.child,
		dep.parent,
		dd.lvl + 1 as lvl
	from
		dep_depth as dd
		inner join #ups_dependencies as dep on dep.parent = dd.child
			and dep.child <> dd.parent
			and not (dep.parent = dd.first_child and dd.lvl > 2)
 	)
select
	table_name,
	table_order
into
	#ups_ordered_tables
from
	(
	--All parents
	select
		dd.parent as table_name,
		max(lvl) as table_order
	from
		dep_depth as dd
	group by
		dd.parent
	union
	--Children that are not parents
	select
		dd.child as table_name,
		max(lvl) + 1 as level
	from
		dep_depth as dd
		left join #ups_dependencies as dp on dp.parent = dd.child
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
		left join #ups_dependencies as p on t.table_name=p.parent
		left join #ups_dependencies as c on t.table_name=c.child
	where
		t.table_schema = '!!#base_schema!!'
		and t.table_type = 'BASE TABLE'
		and p.parent is null
		and c.child is null
	) as all_levels;


-- Create a list of the selected tables with ordering information.
if object_id('tempdb..#ups_proctables') is not null drop table #ups_proctables;
select
	ot.table_order,
	tl.table_name,
	tl.exclude_cols,
	tl.display_changes,
	tl.display_final,
	tl.rows_updated,
	tl.rows_inserted,
	cast(0 as bit) as processed
into
	#ups_proctables
from
	!!#control_table!! as tl
	inner join #ups_ordered_tables as ot on ot.table_name = tl.table_name
	;


-- Create a selection (this would be a view if temp views were allowed) returning a single unprocessed table, in order.
-- !x! begin script ups_get_toprocess
if object_id('tempdb..#ups_toprocess') is not null drop table #ups_toprocess;
select top 1
	table_name, exclude_cols,
	display_changes, display_final,
	rows_updated, rows_inserted
into #ups_toprocess
from #ups_proctables
where not processed=1
order by table_order;
-- !x! end script


-- Process all tables in order.
-- !x! execute script upsert_all_innerloop with (base_schema=!!#base_schema!!, staging=!!#staging!!)

-- Move the update/insert counts back into the control table.
update ct
set
	rows_updated = pt.rows_updated,
	rows_inserted = pt.rows_inserted
from !!#control_table!! as ct
inner join #ups_proctables as pt
on pt.table_name = ct.table_name;


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

-- !x! execute script ups_get_toprocess
-- !x! if(hasrows(#ups_toprocess))
	-- Create local variables to store the row counts from updates and inserts.
	-- !x! sub ~rows_updated 0
	-- !x! sub ~rows_inserted 0

	-- !x! select_sub #ups_toprocess
	-- !x! execute script upsert_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, exclude_cols=[!!@exclude_cols!!], display_changes=!!@display_changes!!, display_final=!!@display_final!!, updcntvar=+rows_updated, inscntvar=+rows_inserted)

	update #ups_proctables
	set rows_updated = !!~rows_updated!!,
		rows_inserted = !!~rows_inserted!!
	where table_name = '!!@table_name!!';

	update #ups_proctables
	set processed = cast(1 as bit)
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

-- !x! BEGIN SCRIPT QA_ALL with parameters (base_schema, staging, control_table)

-- Get denominator for progress bar if console is on.
-- !x! if(console_on)
	if object_id('tempdb..#ups_upsert_rows') is not null drop table #ups_upsert_rows;
	select count(*) + 1 as upsert_rows
	into #ups_upsert_rows
	from !!#control_table!!;
	-- !x! subdata upsert_progress_denom #ups_upsert_rows
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
if object_id('tempdb..#ups_proctables ') is not null drop table #ups_proctables ;
select
	tl.table_name,
	tl.exclude_null_checks,
	tl.display_changes,
	cast(0 as bit) as processed
into #ups_proctables
from
	!!#control_table!! as tl
;

-- Create a script returning a single unprocessed table, in order
-- !x! begin script ups_qa_get_toprocess
if object_id('tempdb..#ups_toprocess') is not null drop table #ups_toprocess;
select top 1
	table_name, exclude_null_checks, display_changes
into #ups_toprocess
from #ups_proctables
where not processed=1
;
-- !x! end script

-- Perform null QA checks on all tables.
-- !x! execute script update_console_qa with args (check_type=NULL)
-- !x! execute script qa_all_nullloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)


-- Perform primary QA checks on all tables.
update #ups_proctables set processed = 0;
-- !x! execute script update_console_qa with args (check_type=primary key)
-- !x! execute script qa_all_pkloop with (base_schema=!!#base_schema!!, staging=!!#staging!!, control_table=!!#control_table!!)

-- Perform foreign key QA checks on all tables.
update #ups_proctables set processed = 0;
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

-- !x! execute script ups_qa_get_toprocess
-- !x! if(hasrows(#ups_toprocess))
	-- !x! select_sub #ups_toprocess
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

	update #ups_proctables
	set processed = 1
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

-- !x! execute script ups_qa_get_toprocess
-- !x! if(hasrows(#ups_toprocess))
	-- !x! select_sub #ups_toprocess
	-- !x! execute script pkqa_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, display_errors=!!@display_changes!!, error_list=+ups_pk_error_list)
	-- !x! if(not is_null("!!~ups_pk_error_list!!"))
		update !!#control_table!!
		set pk_errors = '!!~ups_pk_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update #ups_proctables
	set processed = 1
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

-- !x! execute script ups_qa_get_toprocess
-- !x! if(hasrows(#ups_toprocess))
	-- !x! select_sub #ups_toprocess
	-- !x! execute script fkqa_one with (base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!@table_name!!, display_errors=!!@display_changes!!, error_list=+ups_error_list)
	-- !x! if(not is_null("!!~ups_error_list!!"))
		update !!#control_table!!
		set fk_errors = '!!~ups_error_list!!'
		where table_name = '!!@table_name!!';
	-- !x! endif

	update #ups_proctables
	set processed = 1
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
if object_id('tempdb..#ups_pkqa_errors') is not null drop table #ups_pkqa_errors;
create table #ups_pkqa_errors (
	error_code varchar(40),
	error_description varchar(500)
);

-- Populate a (temporary) table with the names of the primary key columns of the base table.
-- Get the old and new primary key columns from staging table into various formats
-- to use later to construct SQL statement to select records in various ways for both updates and QA checks.
-- Include column lists, join expression, and where clause
if object_id('tempdb..#ups_pkcol_info') is not null drop table #ups_pkcol_info;
select
	k.table_schema,
	k.table_name,
	k.column_name,
	cast('b.' + column_name as varchar(max)) as base_aliased,
	cast('s.' + column_name as varchar(max)) as staging_aliased,
	cast('s.' + column_name + ' as staging_' + column_name as varchar(max)) as staging_aliased_prefix,
	cast('b.' + column_name + ' = s.' + column_name as varchar(max)) as join_expr,
	cast('new_' + column_name as varchar(max)) as newpk_col,
	cast('s.new_' + column_name as varchar(max)) as newpk_col_aliased,
	cast('new_' + column_name + ' is null' as varchar(max)) as newpk_col_empty,
	cast('new_' + column_name + ' is not null' as varchar(max)) as newpk_col_not_empty,
	cast('b.' + column_name + ' = s.new_' + column_name as varchar(max)) as assmt_expr,
	cast('s.new_' + column_name + ' = b.new_' + column_name as varchar(max)) as join_expr_new,
	k.ordinal_position
into #ups_pkcol_info
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
-- !x! execute script UPDTPKQA_ONE with arguments(base_schema=!!#base_schema!!, staging=!!#staging!!, table=!!#table!!, pkinfo_table=#ups_pkcol_info, qaerror_table=#ups_pkqa_errors, display_errors=!!#display_errors!!)


-- Run the PK update ONLY if QA check script returned no errors
-- !x! if(not hasrows(#ups_pkqa_errors))
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

	-- Get list of old primary key columns prefixed with alias
	-- !x! sub_empty ~oldpk_cols
	-- !x! execute script string_agg with(table_name=#ups_pkcol_info, string_col=base_aliased, order_col=ordinal_position, delimiter=", ", string_var=+oldpk_cols)

	-- Get list of columns containing new primary key values
	-- !x! sub_empty ~newpk_cols
	-- !x! execute script string_agg with(table_name=#ups_pkcol_info, string_col=newpk_col, order_col=ordinal_position, delimiter=", ", string_var=+newpk_cols)

	-- Create a join expression for an inner join between base and staging
	-- !x! sub_empty ~joinexpr
	-- !x! execute script string_agg with(table_name=#ups_pkcol_info, string_col=join_expr, order_col=ordinal_position, delimiter=" and ", string_var=+joinexpr)

	-- Create a FROM clause for an inner join between base and staging
	-- tables on the primary key column(s).
	-- !x! sub ~fromclause FROM !!#base_schema!!.!!#table!! as b INNER JOIN !!#staging!!.!!#table!! as s ON !!~joinexpr!!


	-- Create a WHERE clause for the rows to include in the selection (only those having new PK columns populated in the staging table)
	-- !x! sub_empty ~wherecondition
	-- !x! execute script string_agg with(table_name=#ups_pkcol_info, string_col=newpk_col_not_empty, order_col=ordinal_position, delimiter=" and ", string_var=+wherecondition)
	-- !x! sub ~whereclause WHERE !!~wherecondition!!


	-- Select all matches for PK update into temp table
	if object_id('tempdb..#ups_pkupdates') is not null drop table #ups_pkupdates;
	select
		!!~oldpk_cols!!,
		!!~newpk_cols!!
	into #ups_pkupdates
	!!~fromclause!!
	!!~whereclause!!
	;


	-- Prompt user to examine matching data and commit, don't commit, or quit.
	-- !x! if(hasrows(#ups_pkupdates))
		-- !x! if(is_true(!!#display_changes!!))
			-- !x! prompt ask "Do you want to make these changes to primary key values for table !!#table!!?" sub ~do_updates display #ups_pkupdates
		-- !x! endif
		-- !x! if(is_true(!!~do_updates!!))
			-- Create an assignment expression to update key columns of the
			-- base table (as b) from "new_" columns of the staging table (as s).
			-- !x! sub_empty ~assmt_expr
			-- !x! execute script string_agg with(table_name=#ups_pkcol_info, string_col=assmt_expr, order_col=ordinal_position, delimiter=", ", string_var=+assmt_expr)

			-- Create an UPDATE statement to update PK columns of the base table with
			-- "new" PK columns from the staging table.  No semicolon terminating generated SQL.
			-- !x! sub ~updatestmt UPDATE b SET !!~assmt_expr!! FROM !!#base_schema!!.!!#table!! as b INNER JOIN !!#staging!!.!!#table!! as s on !!~joinexpr!! !!~whereclause!!


			-- !x! write "Updating !!#base_schema!!.!!#table!!"
			-- !x! if(sub_defined(logfile))
				-- !x! write "" to !!logfile!!
				-- !x! if(sub_defined(log_sql))
				-- !x! andif(is_true(!!log_sql!!))
					-- !x! write "UPDATE statement for !!#base_schema!!.!!#table!!:" to !!logfile!!
					-- !x! write [!!~updatestmt!!] to !!logfile!!
				-- !x! endif
				-- !x! if(sub_defined(log_changes))
				-- !x! andif(is_true(!!log_changes!!))
					-- !x! write "Updates:" to !!logfile!!
					-- !x! export #ups_pkupdates append to !!logfile!! as txt
				-- !x! endif
				-- !x! write "" to !!logfile!!
			-- !x! endif
			!!~updatestmt!!;
			-- -- !x! sub !!#updcntvar!! !!$last_rowcount!!
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
--		ups_any_pk_cols				: temporary table
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
	if object_id('tempdb..#ups_missing_pk_cols') is not null drop table #ups_missing_pk_cols;
	select
		newpk_col, ordinal_position
	into #ups_missing_pk_cols
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
	;

	-- !x! if(hasrows(#ups_missing_pk_cols))

		-- !x! sub_empty ~error_info
		-- !x! execute script string_agg with(table_name=#ups_missing_pk_cols, string_col=newpk_col, order_col=ordinal_position, delimiter=", ", string_var=+error_info)

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

		-- "Old" PK columns, column names only
		-- !x! sub_empty ~old_pkcol
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=column_name, order_col=ordinal_position, delimiter=", ", string_var=+old_pkcol)

		-- "Old" PK columns from aliased staging table
		-- !x! sub_empty ~old_pkcol_aliased
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=staging_aliased, order_col=ordinal_position, delimiter=", ", string_var=+old_pkcol_aliased)

		-- "Old" PK columns from aliased staging table, with a prefix indicating they're from staging table
		-- !x! sub_empty ~old_pkcol_aliased_prefix
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=staging_aliased_prefix, order_col=ordinal_position, delimiter=", ", string_var=+old_pkcol_aliased_prefix)

		-- "New" PK columns from staging table
		-- !x! sub_empty ~new_pkcol
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=newpk_col, order_col=ordinal_position, delimiter=", ", string_var=+new_pkcol)

		-- "NEW" PK columns from aliased staging table
		-- !x! sub_empty ~new_pkcol_aliased
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=newpk_col_aliased, order_col=ordinal_position, delimiter=", ", string_var=+new_pkcol_aliased)

		-- Just base table
		-- !x! sub ~base_table !!#base_schema!!.!!#table!!

		-- Just staging table
		-- !x! sub ~staging_table !!#staging!!.!!#table!!

		-- Join condition: Base to staging on original (not "new_") PK columns
		-- !x! sub_empty ~joincond_origorig
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=join_expr, order_col=ordinal_position, delimiter=" and ", string_var=+joincond_origorig)

		-- Join condition: Base ORIG PK to staging NEW PK
		-- !x! sub_empty ~joincond_oldnew
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=assmt_expr, order_col=ordinal_position, delimiter=" and ", string_var=+joincond_oldnew)

		-- Join condition: Two instances of NEW PK columns from staging table
		-- !x! sub_empty ~joincond_newnew
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=join_expr_new, order_col=ordinal_position, delimiter=" and ", string_var=+joincond_newnew)

		-- Clause: ANY new PK cols populated
		-- !x! sub_empty ~any_newpk_col_not_empty
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=newpk_col_not_empty, order_col=ordinal_position, delimiter=" or ", string_var=+any_newpk_col_not_empty)

		-- Clause: ALL new PK cols populated
		-- !x! sub_empty ~all_newpk_col_not_empty
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=newpk_col_not_empty, order_col=ordinal_position, delimiter=" and ", string_var=+all_newpk_col_not_empty)

		-- Clause: ANY new PK cols empty
		-- !x! sub_empty ~any_newpk_col_empty
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=newpk_col_empty, order_col=ordinal_position, delimiter=" or ", string_var=+any_newpk_col_empty)

		-- Clause: ALL new PK cols empty
		-- !x! sub_empty ~all_newpk_col_empty
		-- !x! execute script string_agg with(table_name=!!#pkinfo_table!!, string_col=newpk_col_empty, order_col=ordinal_position, delimiter=" and ", string_var=+all_newpk_col_empty)

		-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
		-- Check 3 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
		-- There are any rows with PK updates specified.
		-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

		-- Find any populated new PK columns in staging table
		if object_id('tempdb..#ups_any_pk_cols') is not null drop table #ups_any_pk_cols;
		select * into #ups_any_pk_cols
		from !!~staging_table!!
		where !!~any_newpk_col_not_empty!!;
		-- !x! if(not hasrows(#ups_any_pk_cols))
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
			if object_id('tempdb..#ups_empty_pk_cols') is not null drop table #ups_empty_pk_cols;
			select
				!!~old_pkcol!!,
				!!~new_pkcol!!
			into #ups_empty_pk_cols
			from
				!!~staging_table!!
			where
				not (!!~all_newpk_col_empty!!)
				and (!!~any_newpk_col_empty!!)
			;

			-- !x! if(hasrows(#ups_empty_pk_cols))
				if object_id('tempdb..#ups_empty_pk_cols_rwcnt') is not null drop table #ups_empty_pk_cols_rwcnt;
				select count(*) as rwcnt
				into #ups_empty_pk_cols_rwcnt
				from #ups_empty_pk_cols
				;
				-- !x! subdata ~rowcount #ups_empty_pk_cols_rwcnt
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
						-- !x! export #ups_empty_pk_cols append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Missing values in new PK columns in !!#staging!!.!!#table!!" display #ups_empty_pk_cols
				-- !x! endif
			-- !x! endif

			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 5 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Where any "new" PK column is populated in the staging table, the value of the original PK for that row is valid
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- New PK col in staging table are not empty
			if object_id('tempdb..#ups_old_pks_wc') is not null drop table #ups_old_pks_wc;
			select top 1 base_aliased
			into #ups_old_pks_wc
			from !!#pkinfo_table!!
			order by ordinal_position;
			-- !x! subdata ~old_pk_firstcol #ups_old_pks_wc


			if object_id('tempdb..#ups_invalid_old_pks') is not null drop table #ups_invalid_old_pks;
			select
				!!~old_pkcol_aliased!!,
				!!~new_pkcol!!
			into #ups_invalid_old_pks
			from !!~staging_table!! as s
					left join !!~base_table!! as b on !!~joincond_origorig!!
			where !!~all_newpk_col_not_empty!! and !!~old_pk_firstcol!! is null
			;

			-- !x! if(hasrows(#ups_invalid_old_pks))
				if object_id('tempdb..#ups_invld_pk_rwcnt') is not null drop table #ups_invld_pk_rwcnt;
				select count(*) as rwcnt
				into #ups_invld_pk_rwcnt
				from #ups_invalid_old_pks
				;
				-- !x! subdata ~rowcount #ups_invld_pk_rwcnt
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
						-- !x! export #ups_invalid_old_pks append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Invalid original PK in !!#staging!!.!!#table!!" display #ups_invalid_old_pks
				-- !x! endif
			-- !x! endif

			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 6 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- None of the "new" PK values already exist in the base table
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			if object_id('tempdb..#ups_existing_new_pks') is not null drop table #ups_existing_new_pks;
			select
				!!~old_pkcol_aliased_prefix!!,
				!!~new_pkcol!!,
				b.*
			into #ups_existing_new_pks
			from !!~staging_table!! as s
					inner join !!~base_table!! as b on !!~joincond_oldnew!!
			;

			-- !x! if(hasrows(#ups_existing_new_pks))
				if object_id('tempdb..#ups_exst_nwpk_rwcnt') is not null drop table #ups_exst_nwpk_rwcnt;
				select count(*) as rwcnt
				into #ups_exst_nwpk_rwcnt
				from #ups_existing_new_pks
				;
				-- !x! subdata ~rowcount #ups_exst_nwpk_rwcnt
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
						-- !x! export #ups_existing_new_pks append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "New PK already exists in !!#base_schema!!.!!#table!!" display #ups_existing_new_pks
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 7 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- No two (or more) original PK values map to same new PK value
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			if object_id('tempdb..#ups_pk_mapping_conflict') is not null drop table #ups_pk_mapping_conflict;
			select
				!!~old_pkcol_aliased!!,
				!!~new_pkcol_aliased!!
			into #ups_pk_mapping_conflict
			from !!~staging_table!! as s
				inner join
				(
				select
					!!~new_pkcol!!
				from
				(select distinct !!~old_pkcol!!, !!~new_pkcol!! from !!~staging_table!! where !!~all_newpk_col_not_empty!!) as a
				group by
					!!~new_pkcol!!
				having count(*) >1
				) as b on !!~joincond_newnew!!
			;

			-- !x! if(hasrows(#ups_pk_mapping_conflict))
				if object_id('tempdb..#ups_map_conf_rwcnt') is not null drop table #ups_map_conf_rwcnt;
				select count(*) as rwcnt
				into #ups_map_conf_rwcnt
				from #ups_pk_mapping_conflict
				;
				-- !x! subdata ~rowcount #ups_map_conf_rwcnt
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
						-- !x! export #ups_pk_mapping_conflict append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Multiple original PKs mapped to same new PK in !!#staging!!.!!#table!!" display #ups_pk_mapping_conflict
				-- !x! endif
			-- !x! endif


			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 8 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- No single original PK value maps to multiple new PK values
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			if object_id('tempdb..#ups_pk_duplicate_keys') is not null drop table #ups_pk_duplicate_keys;
			select
				!!~old_pkcol_aliased!!,
				!!~new_pkcol_aliased!!
			into #ups_pk_duplicate_keys
			from !!~staging_table!! as s
				inner join
				(
				select
					!!~old_pkcol!!
				from
				(select distinct !!~old_pkcol!!, !!~new_pkcol!! from !!~staging_table!! where !!~all_newpk_col_not_empty!!) as a
				group by
					!!~old_pkcol!!
				having count(*)>1
				) as b on !!~joincond_origorig!!
			;

			-- !x! if(hasrows(#ups_pk_duplicate_keys))
				if object_id('tempdb..#ups_dup_key_rwcnt') is not null drop table #ups_dup_key_rwcnt;
				select count(*) as rwcnt
				into #ups_dup_key_rwcnt
				from #ups_pk_duplicate_keys
				;
				-- !x! subdata ~rowcount #ups_dup_key_rwcnt
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
						-- !x! export #ups_pk_duplicate_keys append to !!logfile!! as txt
					-- !x! endif
				-- !x! endif
				-- !x! if(is_true(!!#display_errors!!))
					-- !x! prompt message "Original PK mapped to multiple new PKs in !!#staging!!.!!#table!!" display #ups_pk_duplicate_keys
				-- !x! endif
			-- !x! endif

			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- Check 9 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			-- If any of the PK columns reference a parent table, all the "new" values of that column are valid
			-- ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

			-- Get ALL column references for the base table
			if object_id('tempdb..#ups_fkcol_refs') is not null drop table #ups_fkcol_refs;
			select
				object_name(fk.constraint_object_id) as fk_constraint,
				'!!#staging!!' as staging_schema,
				schema_name(t.schema_id) as table_schema,
				t.name as table_name,
				cc.name as column_name,
				cc.column_id,
				schema_name(op.schema_id) as parent_schema,
				object_name(referenced_object_id) as parent_table,
				cp.name as parent_column,
				cp.column_id as parent_column_id
			into #ups_fkcol_refs
			from
				sys.tables as t
				inner join sys.foreign_key_columns as fk on fk.parent_object_id=t.object_id
				inner join sys.columns as cc on fk.parent_object_id=cc.object_id and fk.parent_column_id=cc.column_id
				inner join sys.columns as cp on fk.referenced_object_id=cp.object_id and fk.referenced_column_id=cp.column_id
				inner join sys.objects as op on op.object_id=cp.object_id
			where
				schema_name(t.schema_id)='!!#base_schema!!'
				and t.name = '!!#table!!'
			;

			-- Narrow the list down to ONLY dependencies that affect PK columns
			-- Include not just the PK columns themselves, but ALL columns included in FKs
			-- that include ANY PK columns (probably rare/unlikely that a non-PK column would be
			-- part of the same foreign key as a PK column, but this ensures that ALL columns of the FK
			-- are included, whether or not the column is part of the PK)
			if object_id('tempdb..#ups_pkcol_deps') is not null drop table #ups_pkcol_deps;
			select
				refs.*
			into #ups_pkcol_deps
			from
				#ups_fkcol_refs as refs
				inner join
				--Distinct list of FK constraints on the table that include ANY PK columns
				(
				select distinct
					fk_constraint, r.table_schema, r.table_name
				from
					#ups_fkcol_refs as r
					inner join 	#ups_pkcol_info as p on r.table_schema=p.TABLE_SCHEMA and r.table_name=p.table_name and r.column_name=p.column_name
				) as const on refs.fk_constraint=const.fk_constraint and refs.table_schema=const.table_schema and refs.table_name=const.table_name
			;

			-- Create a control table for looping to check each fk
			-- Include (for later use) some of the constructed strings that apply to the entire PK (not
			-- just the FK being checked)
			if object_id('tempdb..#ups_pkfk_ctrl') is not null drop table #ups_pkfk_ctrl;
			select
				fk_constraint,
				staging_schema, table_schema, table_name, parent_schema, parent_table,
				min(parent_column) as any_referenced_column,
				'!!~old_pkcol_aliased!!' as old_pkcol_aliased,
				'!!~new_pkcol!!' as new_pkcol,
				'!!~all_newpk_col_not_empty!!' as all_newpk_col_not_empty,
				cast(0 as bit) as processed
			into #ups_pkfk_ctrl
			from #ups_pkcol_deps
			group by
				fk_constraint,
				staging_schema, table_schema, table_name, parent_schema, parent_table;

			-- Create a script to select one constraint to process
			-- !x! begin script ups_get_next_fk
			if object_id('tempdb..#ups_next_fk') is not null drop table #ups_next_fk;
			select top 1 *
			into #ups_next_fk
			from #ups_pkfk_ctrl
			where not processed=1;
			-- !x! end script

			--Process all constraints: check every foreign key
			--!x! execute script updtpkqa_one_innerloop with (qaerror_table=!!#qaerror_table!!, display_errors=!!#display_errors!!)
		-- !x! endif
	-- !x! endif
-- !x! endif
-- !x! END SCRIPT
-- ###################  UPDTPKQA_ONE  ########################
-- ################################################################
--			Script UPDTPKQA_ONE_INNERLOOP
-- ----------------------------------------------------------------
-- !x! BEGIN SCRIPT UPDTPKQA_ONE_INNERLOOP with parameters(qaerror_table, display_errors)

-- !x! execute script ups_get_next_fk
-- !x! if(hasrows(#ups_next_fk))

	-- !x! select_sub #ups_next_fk

	-- Compile FK info for the selected constraint
	if object_id('tempdb..#ups_sel_fk_cols') is not null drop table #ups_sel_fk_cols;
	select
		staging_schema, fk_constraint, table_schema, table_name, column_name, column_id, parent_schema,
		parent_table, parent_column, parent_column_id,
		's.new_' + column_name + '=' + 'b.' + parent_column as join_condition
	into #ups_sel_fk_cols
	from #ups_pkcol_deps
	where fk_constraint='!!@fk_constraint!!'
	;

	-- Construct SQL to check the selected FK

	-- !x! sub_empty ~referenced_cols
	-- !x! execute script string_agg with (table_name=#ups_sel_fk_cols, string_col=parent_column, order_col=column_id, delimiter=", ", string_var=+referenced_cols)

	-- !x! sub_empty ~join_condition
	-- !x! execute script string_agg with (table_name=#ups_sel_fk_cols, string_col=join_condition, order_col=column_id, delimiter=" and ", string_var=+join_condition)


	-- !x! sub ~select_stmt select !!@old_pkcol_aliased!!, !!@new_pkcol!! into #ups_pk_fk_check from !!@staging_schema!!.!!@table_name!! as s
	-- !x! sub ~join_stmt left join !!@parent_schema!!.!!@parent_table!! as b on !!~join_condition!!
	-- !x! sub ~where_clause where !!@all_newpk_col_not_empty!! and b.!!@any_referenced_column!! is null

	-- !x! sub ~fk_check if object_id('tempdb..#ups_pk_fk_check') is not null drop table #ups_pk_fk_check;
	-- !x! sub_append ~fk_check !!~select_stmt!!
	-- !x! sub_append ~fk_check !!~join_stmt!!
	-- !x! sub_append ~fk_check !!~where_clause!!

	-- Write the SQL to the log file if requested.
	-- !x! if(sub_defined(logfile))
	-- !x! andif(sub_defined(log_sql))
	-- !x! andif(is_true(!!log_sql!!))
		-- !x! write "" to !!logfile!!
		-- !x! write "SQL for checking foreign key !!@fk_constraint!! for PK update to !!@table_schema!!.!!@table_name!!:" to !!logfile!!
		-- !x! write [!!~fk_check!!] to !!logfile!!
	-- !x! endif

	-- Run the check
	!!~fk_check!!;

	-- !x! if(hasrows(#ups_pk_fk_check))

		if object_id('tempdb..#ups_pk_fk_check_rwcnt') is not null drop table #ups_pk_fk_check_rwcnt;
		select count(*) as rwcnt
		into #ups_pk_fk_check_rwcnt
		from #ups_pk_fk_check
		;
		-- !x! subdata ~rowcount #ups_pk_fk_check_rwcnt
		-- !x! sub ~error_description !!@parent_schema!!.!!@parent_table!! (!!~referenced_cols!!): !!~rowcount!! row(s)

		-- !x! write "    Violation of foreign key !!@fk_constraint!! in new primary key columns in !!@staging_schema!!.!!@table_name!! referencing !!@parent_schema!!.!!@parent_table!!: !!~rowcount!! row(s)"

		if object_id('tempdb..#ups_pk_fk_qa_error') is not null drop table #ups_pk_fk_qa_error;
		select
			error_code, error_description
		into #ups_pk_fk_qa_error
		from !!#qaerror_table!!
		where error_code='Invalid reference to parent table(s)';
		-- !x! if(hasrows(#ups_pk_fk_qa_error))
			update !!#qaerror_table!!
			set error_description=error_description + '; !!~error_description!!'
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
				-- !x! export #ups_pk_fk_check append to !!logfile!! as txt
			-- !x! endif
		-- !x! endif
		-- !x! if(is_true(!!#display_errors!!))
			-- !x! prompt message "Violation of foreign key !!@fk_constraint!! in  new primary key columns in !!@staging_schema!!.!!@table_name!! referencing !!@parent_schema!!.!!@parent_table!!" display #ups_pk_fk_check
		-- !x! endif

	-- !x! endif

	-- Mark constraint as processed
	update #ups_pkfk_ctrl
	set processed=1
	where fk_constraint='!!@fk_constraint!!';

	--LOOP
	-- !x! execute script updtpkqa_one_innerloop with (qaerror_table=!!#qaerror_table!!, display_errors=!!#display_errors!!)

-- !x! endif

-- !x! END SCRIPT
-- ####################  End of UPDTPKQA_ONE  ########################
-- ################################################################
