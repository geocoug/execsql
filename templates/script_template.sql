-- .sql
--
-- PURPOSE
--
--
-- NOTES
--	1.
--	2.
--
-- PROJECT
--
--
-- COPYRIGHT
--	Copyright (c) 202x,
--
-- AUTHORS
--
--
-- HISTORY
--	 Date		 Remarks
--	----------	-----------------------------------------------------------------
--
-- ==============================================================================


-- !x! if(False)
	ERROR -- This script must be run using execsql.py;
-- !x! endif


-- ##############################################################################
--		Configuration
-- ==============================================================================

-- ------------------------------------------------------------------------------
--		General configuration
-- These settings ordinarily shouldn't need to be changed.
-- ------------------------------------------------------------------------------
-- !x! config make_export_dirs Yes
-- !x! config write_warnings Yes
-- !x! config console wait_when_done Yes
-- !x! config console wait_when_error Yes

-- !x! on cancel_halt execute script canceled
-- !x! on error_halt execute script crashed


-- ------------------------------------------------------------------------------
--		Script-specific configuration
-- These settings may need to be changed for some uses of the script.
-- ------------------------------------------------------------------------------

-- The "output_dir" variable will be set to a run-specific directory name that
-- is dynamically created and is different for each run of this script.  The
-- run-specific output directories will be created underneath a parent directory.
-- The path to that parent directory is specified here.  By default, the parent
-- directory is named "DB_output" and is under the current directory.
-- !x! sub output_parent DB_output

-- Create a unique number for every run, with corresponding output
-- directories and optionally a narrative descriptions.
-- !x! sub do_run_numbering True
-- Prompt for a run description?
-- !x! sub get_run_description True

-- Path to the SQL script library.
---- !x! sub script_library /path/to/sql/library

-- Change the base filename of the logfile as appropriate.
-- If run numbering is enabled, the logfile path and name that are set here
-- will be changed in the initialization section of this script.
-- !x! sub logfile logfiles/logfile_!!$date_tag!!.txt

-- Flag to control whether the custom logfile is rewritten each time.
-- If run numbering is enabled, this ordinarily will have no effect because
-- a new logfile will be created for each run.
-- !x! sub clean_logfile No

-- The actions to be carried out by this script; this information will be
-- included in documentation.
-- !x! sub script_purpose SCRIPT PURPOSE IS MISSING
-- The name of the person who requested this work.
-- !x! sub requested_by REQUESTOR NAME IS MISSING
-- The date that the request was made.
-- !x! sub request_date REQUEST DATE IS MISSING
-- Project number
-- !x! sub project_number PROJECT NUMBER IS MISSING
-- Additional metadata text that, if defined, will be included in the logfile prologue.
---- !x! sub metadata_comment

-- Define a user-specific staging schema.  This prevents multiple users from
-- creating conflicting staging tables.  Not all DBMSs support schemas.
-- !x! sub staging stg_!!$db_user!!
-- The current user must have permission to create a schema.  Errors are
-- ignored because not all DBMSs support schemas.
-- !x! error_halt off
create schema if not exists !!staging!!;
-- !x! error_halt on

-- !x! if(not !!do_run_numbering!!)
	-- Use an date-tagged directory name for "output_dir".
	-- !x! sub output_dir !!output_parent!!!!$pathsep!!!!$date_tag!!
-- !x! endif


-- Allow settings from a custom configuration file, 'custom.conf',
-- to add to or replace configuration settings.
-- !x! if(file_exists(custom.conf)) {sub_ini custom.conf section execsql}
-- Any configuration file may define an additional section to read.
-- !x! if(sub_defined(additional_conf))
	-- !x! sub_ini custom.conf section !!additional_conf!!
-- !x! endif


-- ------------------------------------------------------------------------------
--		Database-specific configuration
-- ------------------------------------------------------------------------------


-- ------------------------------------------------------------------------------
--		Dataset-specific configuration
-- ------------------------------------------------------------------------------


-- ------------------------------------------------------------------------------
-- ------------------------------------------------------------------------------
--		Run-specific configuration
-- ------------------------------------------------------------------------------
-- Flag to control the amount of information displayed.
-- !x! sub verbose Yes

-- Flag to control whether cleanup actions are carried out when the script finishes.
-- This may be set to "No" during development and testing, to assist with
-- diagnostics and debugging, and set to "Yes" for production uses.
-- Cleanu actions should be specified in the "cleanup" script at the end if this file.
-- !x! sub do_cleanup Yes

-- Flag to control whether transactions are to be committed.
-- !x! sub do_commit Yes

-- Flag to control execution of debugging code.
-- !x! sub do_debug No


-- ------------------------------------------------------------------------------



-- ##############################################################################
--		Library scripts to be used
-- ==============================================================================

-- For example:
---- !x! include !!script_library!!/pg_upsert.sql

-- ------------------------------------------------------------------------------




-- ##############################################################################
--		Initialization
-- ==============================================================================

-- ------------------------------------------------------------------------------
--		Set up the run number, get a run description, and save it.
-- A run number is always assigned, but it is used for the output directory
-- and logfile prefix only if the option is specified.
-- - - - - - - -  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
-- !x! if(file_exists(DB_run.conf))
	-- !x! sub_ini file DB_run.conf section run
-- !x! endif
-- !x! if(not sub_defined(run_no))
	-- !x! sub run_no 0
-- !x! endif
-- !x! sub_add run_no 1
-- !x! rm_file DB_run.conf
-- !x! write "# Automatically-generated database run number setting.  Do not edit." to DB_run.conf
-- !x! write "[run]" to DB_run.conf
-- !x! write "run_no=!!run_no!!" to DB_run.conf
-- !x! sub run_tag !!run_no!!
-- !x! if(not is_gt(!!run_no!!, 9))
	-- !x! sub run_tag 0!!run_tag!!
-- !x! endif
-- !x! if(not is_gt(!!run_no!!, 99))
	-- !x! sub run_tag 0!!run_tag!!
-- !x! endif
-- !x! if(!!do_run_numbering!!)
	-- !x! sub output_dir !!output_parent!!!!$pathsep!!Run_!!run_tag!!_!!$date_tag!!
	-- !x! sub logfile logfiles!!$pathsep!!Run_!!run_tag!!_logfile.txt
	-- !x! if(!!get_run_description!!)
		-- !x! prompt enter_sub run_description message "Please enter a description for this run (!!run_tag!!)"
		-- !x! if(not sub_empty(run_description))
			-- !x! write "!!run_description!!" to !!output_dir!!!!$pathsep!!run_description.txt
			-- !x! export query <<select !!run_no!! as "Run_no", '!!run_description!!' as "Description";>> append to DB_run_descriptions.csv as csv
		-- !x! endif
	-- !x! endif
-- !x! endif
-- ------------------------------------------------------------------------------



-- !x! console on

-- !x! if(!!clean_logfile!!) {rm_file !!logfile!!}

-- Write a prologue to the logfile.
-- !x! if(file_exists(!!logfile!!))
	-- !x! write "" to !!logfile!!
	-- !x! write "" to !!logfile!!
-- !x! endif
-- !x! write "==============================================================" to !!logfile!!
-- !x! if(sub_defined(script_purpose))
    -- !x! write "!!script_purpose!!" tee to !!logfile!!
    -- !x! write "--------------------------------------------------------------" to !!logfile!!
    -- !x! write " " to !!logfile!!
-- !x! endif
-- !x! write "Requested by:     !!requested_by!!" to !!logfile!!
-- !x! write "Requested on:      !!request_date!!" to !!logfile!!
-- !x! write "Project No.:      !!project_number!!" to !!logfile!!
-- !x! write "Working dir:      !!$CURRENT_DIR!!" to !!logfile!!
-- !x! write "Starting script:  !!$STARTING_SCRIPT!!" to !!logfile!!
-- !x! write "Script rev time:  !!$STARTING_SCRIPT_REVTIME!!" to !!logfile!!
-- !x! write "Current script:   !!$CURRENT_SCRIPT!!" to !!logfile!!
-- !x! write "Database:         !!$CURRENT_DATABASE!!" to !!logfile!!
-- !x! write "User:             !!$DB_USER!!" to !!logfile!!
-- !x! write "Run at:           !!$CURRENT_TIME!!" to !!logfile!!
-- !x! write "Run ID:           !!$RUN_ID!!" to !!logfile!!
-- !x! write "Committing:       !!do_commit!! to !!logfile!!
-- !x! write "Cleaning up:      !!do_cleanup!! to !!logfile!!
-- !x! if(sub_defined(metadata_comment))
	-- !x! write "" to !!logfile!!
	-- !x! write "!!metadata_comment!!" to !!logfile!!
-- !x! endif
-- !x! write " " to !!logfile!!

-- ------------------------------------------------------------------------------





-- <The script body goes here.>






-- ------------------------------------------------------------------------------

-- ##############################################################################
--		Clean up and exit
-- ==============================================================================
-- !x! execute script cleanup

-- !x! write "" tee to !!logfile!!
-- !x! write "Done." tee to !!logfile!!
-- !x! write "--------------------------------------------------------------" tee to !!logfile!!
-- !x! write "" to !!logfile!!
-- !x! write "" to !!logfile!!


-- No SQL statements or metacommands should be below this point, only scripts and comments.



-- ##############################################################################
--		Scripts
-- ==============================================================================

-- !x! begin script cleanup
	-- !x! if(!!do_cleanup!!)
		-- !x! write ""
		-- !x! write "Cleaning up."
		-- <Script-specific cleanup steps go here>
		-- <or they may be appended using an EXTEND SCRIPT metacommand.>
		-- !x! write "" to !!logfile!!
	-- !x! endif
-- !x! end script cleanup

-- !x! begin script canceled
	-- !x! write "" tee to !!logfile!!
	-- !x! write "Script canceled by user." tee to !!logfile!!
	-- !x! execute script cleanup
	-- !x! write "" to !!logfile!!
-- !x! end script canceled

-- !x! begin script crashed
	-- !x! write "" tee to !!logfile!!
	-- !x! write "Script halted by an error." tee to !!logfile!!
	-- !x! execute script cleanup
	-- !x! write "" to !!logfile!!
-- !x! end script crashed


--
-- End of script_template.sql
--
