-- example_config_prompt.sql
--
-- PURPOSE
--	Illustrate the use of the 'config_settings.sqlite' database
--	to prompt for configuration settings.
--
-- NOTES
--	1. The initial connection is assumed to have been made to some
--		database other than the configuration database.
--	2. The 'prompt_config' script defined in this file will connect
--		to the configuration database using the alias "config_db"
--		if that alias exists, or it will connect to the (SQLite)
--		configuration database if the "config_db" substitution
--		variable contains a valid path and name to the configuration
--		database.
--	3. This requires excecsql.py version 1.63.0 or greater.
--	4. To replicate this example (or something like it) in production code:
--		a. Include the "prompt_config" script (defined below) in
--			your own script.
--		b. Either define the "sub_config" variable so that it contains
--			the path and filename of the configuration database,
--			or use the CONNECT metacommand to connect to that database
--			yourself with an alias of "config_db".
--		c. Possibly change the 'usage' argument for the 'prompt_config"
--			script to be "Import", "Export", or "AllButDAO" instead of "All."
--
-- AUTHOR
--	Dreas Nielsen (RDN)
--
-- HISTORY
--	 Date		 Remarks
--	----------	-----------------------------------------------------
--	2020-02-15	Created.  RDN.
--	2020-02-16	Modified documentation.  RDN.
--	2020-02-16	Corrected assignments.  RDN.
--	2020-02-22	Added SCAN_LINES and GUI_LEVEL.  RDN.
--	2020-03-22	Added HDF5_TEXT_LEN and LOG_DATAVARS.  RDN.
--	2020-03-30	Added EXPORT_ROW_BUFFER.  RDN.
--	2020-07-30	Added DEDUP_COLUMN_HEADERS.  RDN.
--	2020-11-08	Added ONLY_STRINGS.  RDN.
--	2020-11-14	Added CONSOLE HEIGHT and CONSOLE WIDTH.  These are
--				not subcommands of the CONFIG metacommand, but they
--				now affect future consoles, and so function similarly.  RDN.
--	2021-02-15	Added CREATE_COL_HEADERS and ZIP_BUFFER_MB.  RDN.
--	2021-09-19	Added TRIM_STRINGS and REPLACE_NEWLINES.  RDN.
--	2023-08-25	Changed names of a couple of sub vars.  Added
--				DELETE_EMPTY_COLUMNS, FOLD_COLUMN_HEADERS, TRIM_COLUMN_HEADERS,
--				WRITE_PREFIX, and WRITE_SUFFIX.  RDN.
-- ==================================================================


-- ##################################################################
--		Configuration
-- ==================================================================

-- Path and name of the configuration settings database.
-- !x! sub config_db ./config_settings.sqlite


-- ##################################################################
--		Usage illustration
-- ==================================================================
-- This makes use of the 'prompt_config' script, defined below.

-- Prompt the user
-- !x! execute script prompt_config with arguments (usage=All)
-- Display all configuration settings (including settings not set interactively).
-- !x! debug write config





-- ##################################################################
--		Scripts
-- ==================================================================


-- -----------------------------------------------------------------
--		prompt_config
--
-- Creates and displays prompts for configuration settings,
-- modifying the global settings per the user's input.
--
-- Argument
--	usage	: Values of the 'usage' column in the 'configusage'
--				table of the configuration settings database.
--				This should be 'All', 'AllButDAO', 'Import', or 'Export'.
--				Other values may be used if they have been added
--				to the 'configusage' table
--
-- Effects
--	1. Modifies global settings.
--	2. Creates a temporary table with a UUID as a name in the configuration database.
--
-- Requirements
--	Either:
--		* An existing connection to the configuration database
--			with an alias of "config_db"; or
--		* A substitution variable named "config_db" that defines
--			the path and filename to the (SQLite) configuration
--			database.
-- -----------------------------------------------------------------

-- !x! begin script prompt_config with parameters (usage)
	-- !x! sub entry_db !!$current_alias!!
	-- !x! if(alias_defined(config_db))
		-- !x! use config_db
	-- !x! else
		-- !x! if(sub_defined(config_db))
			-- !x! connect to sqlite(file=!!config_db!!) as config_db
			-- !x! use config_db
		-- !x! else
			-- !x! halt message "The configuration settings database is not open and its name is not specified."
		-- !x! endif
	-- !x! endif
	-- The following SQL syntax is for SQLite.  A UUID is used for the table name
	-- for portability to a multi-user DBMS.
	-- !x! sub ~spectbl !!$uuid!!
	create temporary table "!!~spectbl!!" as
	select cs.*
	from configspecs cs inner join configusage cu
		on cu.sub_var = cs.sub_var
	where
		usage = '!!#usage!!';
	-- !x! prompt entry_form !!~spectbl!! message "You may change any of the configuration settings below."
	-- !x! if(sub_defined(~boolean_int)) {config boolean_int !!~boolean_int!!}
	-- !x! if(sub_defined(~boolean_words)) {config boolean_words !!~boolean_words!!}
	-- !x! if(sub_defined(~clean_column_headers)) {config clean_column_headers !!~clean_column_headers!!}
	-- !x! if(sub_defined(~create_column_headers)) {config create_column_headers !!~create_column_headers!!}
	-- !x! if(sub_defined(~dedup_col_hdrs)) {config dedup_column_headers !!~dedup_col_hdrs!!}
	-- !x! if(sub_defined(~delete_empty_columns)) {config delete_empty_columns !!~delete_empty_columns!!}
	-- !x! if(sub_defined(~empty_strings)) {config empty_strings !!~empty_strings!!}
	-- !x! if(sub_defined(~fold_col_hdrs)) {config fold_column_headers !!~fold_col_hdrs!!}
	-- !x! if(sub_defined(~trim_col_hdrs)) {config trim_column_headers !!~trim_col_hdrs!!}
	-- !x! if(sub_defined(~only_strings)) {config only_strings !!~only_strings!!}
	-- !x! if(sub_defined(~empty_rows)) {config empty_rows !!~empty_rows!!}
	-- !x! if(sub_defined(~trim_strings)) {config trim_strings !!~trim_strings!!}
	-- !x! if(sub_defined(~replace_newlines)) {config replace_newlines !!~replace_newlines!!}
	-- !x! if(sub_defined(~scan_lines)) {config scan_lines !!~scan_lines!!}
	-- !x! if(sub_defined(~import_common)) {config import_common_columns_only !!~import_common!!}
	-- !x! if(sub_defined(~console_height)) {console height !!~console_height!!}
	-- !x! if(sub_defined(~console_width)) {console width !!~console_width!!}
	-- !x! if(sub_defined(~console_wait_done)) {config console wait_when_done !!~console_wait_done!!}
	-- !x! if(sub_defined(~console_wait_err)) {config console wait_when_error !!~console_wait_err!!}
	-- !x! if(sub_defined(~log_write)) {config log_write_messages !!~log_write!!}
	-- !x! if(sub_defined(~quote_all)) {config quote_all_text !!~quote_all!!}
	-- !x! if(sub_defined(~export_row_buffer)) {config export_row_buffer !!~export_row_buffer!!}
	-- !x! if(sub_defined(~hdf5_len)) {config hdf5_text_len !!~hdf5_len!!}
	-- !x! if(sub_defined(~gui_level)) {config gui_level !!~gui_level!!}
	-- !x! if(sub_defined(~write_prefix)) {config write_prefix !!~write_prefix!!}
	-- !x! if(sub_defined(~write_suffix)) {config write_suffix !!~write_suffix!!}
	-- !x! if(sub_defined(~write_warnings)) {config write_warnings !!~write_warnings!!}
	-- !x! if(sub_defined(~log_datavars)) {config log_datavars !!~log_datavars!!}
	-- !x! if(sub_defined(~dao_flush)) {config dao_flush_delay_secs !!~dao_flush!!}
	-- !x! if(sub_defined(~zip_buffer_mb)) {config zip_buffer_mb !!~zip_buffer_mb!!}
	-- !x! use !!entry_db!!
-- !x! end script prompt_config
