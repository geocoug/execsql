-- make_config_db.sql
--
-- PURPOSE
--	Make a SQLite data table that can be used to drive a dialog box
--	to modify settings.
--
-- NOTES
--	1. The initial connection should be made to the SQLite
--		database to be used.
--
-- AUTHOR
--	Dreas Nielsen (RDN)
--
-- HISTORY
--	 Date		 Remarks
--	----------	-----------------------------------------------------
--	2020-02-15	Created.  RDN.
--	2020-02-22	Added settings for GUI_LEVEL and SCAN_LINES.  RDN.
--	2020-07-08	Added setting for IMPORT_ROW_BUFFER.  RDN.
--	2020-07-18	Added setting for DEDUP_COLUMN_HEADERS.  RDN.
--	2020-11-08	Added settings for ONLY_STRINGS.  RDN.
--	2020-11-14	Added settings for CONFIG CONSOLE HEIGHT and ...WIDTH.  RDN.
--	2021-02-15	Added settings for CREATE_COLUMN_HEADERS and ZIP_BUFFER_MB.  RDN.
--	2021-09-19	Added settings for REPLACE_NEWLINES and TRIM_STRINGS.  RDN.
--	2023-08-25	Added settings for DELETE_EMPTY_COLUMNS, FOLD_COLUMN_HEADERS,
--				TRIM_COLUMN_HEADERS, WRITE_PREFIX, and WRITE_SUFFIX.  RDN.
-- ==================================================================



drop table if exists configspecs;
create table configspecs (
	sub_var text not null,
	prompt text not null,
	initial_value text,
	entry_type text,
	width integer,
	validation_regex text,
	sequence integer,
	constraint pk_conf primary key (sub_var)
	);

insert into configspecs
	(sub_var, prompt, initial_value, entry_type, validation_regex, sequence)
values
	('~boolean_int', 'Values of 0 and 1 are considered Boolean on import',
		1, 'checkbox', null, 1),
	('~boolean_words', 'Values of Y, N, T, and F are considered Boolean on import',
		1, 'checkbox', null, 2),
	('~clean_column_headers', 'Replace non-alphanumerics in column headers with underscores on import',
		0, 'checkbox', null, 3),
	('~trim_col_hdrs', 'Remove spaces and underscores from column headers (none, left, right, both)',
		'none', null, null, 4),
	('~create_column_headers', 'Create missing column headers',
		0, 'checkbox', null, 5),
	('~delete_empty_columns', 'Delete entire columns that are missing column headers',
		0, 'checkbox', null, 6),
	('~dedup_col_hdrs', 'Make repeated column headers unique by appending an underscore and column number on import',
		0, 'checkbox', null, 7),
	('~import_common', 'Import only columns present in both source and destination',
		0, 'checkbox', null, 8),
	('~empty_strings', 'Empty strings ('''') in imported data will be preserved, not replaced with NULL',
		1, 'checkbox', null, 9),
	('~empty_rows', 'Empty rows in imported data will be preserved',
		1, 'checkbox', null, 10),
	('~fold_col_hdrs', 'Fold column headers of imported data (no, lower, or upper)',
		'no', null, null, 11),
	('~replace_newlines', 'Newlines in imported data will be replaced with a space.',
		0, 'checkbox', null, 12),
	('~trim_strings', 'Leading and trailing whitespace on imported strings will be removed.',
		0, 'checkbox', null, 13),
	('~scan_lines', 'Number of lines of a text file to scan for delimiters during import',
		100, null, '[1-9][0-9]*', 14),
	('~import_row_buffer', 'Number of rows of input data to buffer for the IMPORT metacommand',
		1000, null, '[1-9][0-9]*', 15),
	('~make_dirs', 'Create directories if necessary for export files',
		0, 'checkbox', null, 16),
	('~quote_all', 'Quote all text values on output',
		0, 'checkbox', null, 17),
	('~export_row_buffer', 'Number of data rows to buffer during export',
		1000, null, '[1-9][0-9]*', 18),
	('~hdf5_len', 'Length of text columns for HDF5 output',
		1000, null, null, 18),
	('~console_height', 'Approximate height of a console window',
		25, null, '[1-9][0-9]*', 20),
	('~console_width', 'Approximate width of a console window',
		100, null, '[1-9][0-9]*', 21),
	('~console_wait_done', 'Leave execsql''s console open when script is complete',
		0, 'checkbox', null, 22),
	('~console_wait_err', 'Leave execsql''s console open when an error occurs',
		0, 'checkbox', null, 23),
	('~log_write', 'Echo all output of the ''write'' metacommand to execsql.log',
		0, 'checkbox', null, 24),
	('~gui_level', 'Use GUI dialogs for user interaction',
		0, null, '[0-2]', 25),
	('~only_strings', 'Import all data columns as text',
		0, 'checkbox', null, 26),
	('~write_prefix', 'Text that will be prefixed to all output of the WRITE metacommand',
		null, null, null, 27),
	('~write_suffix', 'Text that will be suffixed to all output of the WRITE metacommand',
		null, null, null, 28),
	('~write_warnings', 'Write warning messages to the console as well as to execsql.log',
		0, 'checkbox', null, 29),
	('~log_datavars', 'Write data variable assignments to execsql.log',
		1, 'checkbox', null, 30),
	('~zip_buffer_mb', 'Buffer size for zipped exports, in Mb.',
		10, null, '[1-9][0-9]*', 31),
	('~dao_flush', 'Delay, in seconds, between use of DAO and ODBC with Access',
		'5.0', null, '[0-9]*\.?[0-9]+', 32)
	;
update configspecs set width = 5
	where sub_var in ('~scan_lines', '~dao_flush', '~console_width', '~console_height',
		'~replace_newlines', '~trim_strings', '~zip_buffer_mb');
update configspecs set width = 7 where sub_var in ('~import_row_buffer', '~export_row_buffer', '~hdf5_len');
update configspecs set width = 2 where sub_var = '~gui_level';

drop table if exists configusage;
create table configusage (
	usage text not null,
	sub_var text not null,
	constraint pk_usage primary key (usage, sub_var)
	);

insert into configusage
	(usage, sub_var)
values
	('All', '~boolean_int'),
	('All', '~boolean_words'),
	('All', '~clean_column_headers'),
	('All', '~create_column_headers'),
	('All', '~dedup_col_hdrs'),
	('All', '~delete_empty_columns'),
	('All', '~import_common'),
	('All', '~empty_strings'),
	('All', '~empty_rows'),
	('All', '~fold_col_hdrs'),
	('All', '~replace_newlines'),
	('All', '~trim_strings'),
	('All', '~trim_col_hdrs'),
	('All', '~scan_lines'),
	('All', '~console_height'),
	('All', '~console_width'),
	('All', '~console_wait_done'),
	('All', '~console_wait_err'),
	('All', '~log_write'),
	('All', '~make_dirs'),
	('All', '~quote_all'),
	('All', '~import_row_buffer'),
	('All', '~export_row_buffer'),
	('All', '~hdf5_len'),
	('All', '~gui_level'),
	('All', '~write_prefix'),
	('All', '~write_suffix'),
	('All', '~write_warnings'),
	('All', '~log_datavars'),
	('All', '~dao_flush'),
	('All', '~only_strings'),
	('All', '~zip_buffer_mb'),


	('AllButDAO', '~boolean_int'),
	('AllButDAO', '~boolean_words'),
	('AllButDAO', '~clean_column_headers'),
	('AllButDAO', '~create_column_headers'),
	('AllButDAO', '~dedup_col_hdrs'),
	('AllButDAO', '~delete_empty_columns'),
	('AllButDAO', '~import_common'),
	('AllButDAO', '~empty_strings'),
	('AllButDAO', '~empty_rows'),
	('AllButDAO', '~fold_col_hdrs'),
	('AllButDAO', '~replace_newlines'),
	('AllButDAO', '~trim_strings'),
	('AllButDAO', '~trim_col_hdrs'),
	('AllButDAO', '~scan_lines'),
	('AllButDAO', '~console_height'),
	('AllButDAO', '~console_width'),
	('AllButDAO', '~console_wait_done'),
	('AllButDAO', '~console_wait_err'),
	('AllButDAO', '~log_write'),
	('AllButDAO', '~make_dirs'),
	('AllButDAO', '~quote_all'),
	('AllButDAO', '~import_row_buffer'),
	('AllButDAO', '~export_row_buffer'),
	('AllButDAO', '~hdf5_len'),
	('AllButDAO', '~gui_level'),
	('AllButDAO', '~write_prefix'),
	('AllButDAO', '~write_suffix'),
	('AllButDAO', '~write_warnings'),
	('AllButDAO', '~log_datavars'),
	('AllButDAO', '~only_strings'),
	('AllButDAO', '~zip_buffer_mb'),

	('Import', '~boolean_int'),
	('Import', '~boolean_words'),
	('Import', '~clean_column_headers'),
	('Import', '~create_column_headers'),
	('Import', '~dedup_col_hdrs'),
	('Import', '~delete_empty_columns'),
	('Import', '~empty_strings'),
	('Import', '~empty_rows'),
	('Import', '~fold_col_hdrs'),
	('Import', '~replace_newlines'),
	('Import', '~trim_strings'),
	('Import', '~trim_col_hdrs'),
	('Import', '~import_common'),
	('Import', '~import_row_buffer'),
	('Import', '~scan_lines'),
	('Import', '~only_strings'),

	('Export', '~make_dirs'),
	('Export', '~quote_all'),
	('Export', '~export_row_buffer'),
	('Export', '~hdf5_len'),
	('Export', '~zip_buffer_mb')
	;

drop view if exists all_config;
create view all_config as
select cs.*
from configspecs cs inner join configusage cu
	on cu.sub_var = cs.sub_var
where
	usage = 'All';

drop view if exists allbutdao_config;
create view allbutdao_config as
select cs.*
from configspecs cs inner join configusage cu
	on cu.sub_var = cs.sub_var
where
	usage = 'AllButDAO';

drop view if exists import_config;
create view import_config as
select cs.*
from configspecs cs inner join configusage cu
	on cu.sub_var = cs.sub_var
where
	usage = 'Import';

drop view if exists export_config;
create view export_config as
select cs.*
from configspecs cs inner join configusage cu
	on cu.sub_var = cs.sub_var
where
	usage = 'Export';
