# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries prior to `2.0.0a1` are from the upstream
[execsql](https://execsql.readthedocs.io/) project by R.Dreas Nielsen.

______________________________________________________________________

## [Unreleased]

______________________________________________________________________

## [2.0.1] - 2026-03-23

### Fixed

- Fixed `PermissionError` on Windows when exporting to HTML in append mode: the file descriptor returned by `tempfile.mkstemp()` is now closed before the file is opened for writing.
- Fixed `PermissionError` on Windows when exporting to LaTeX: the file descriptor returned by `tempfile.mkstemp()` is now closed before `EncodedFile` opens the same path.

______________________________________________________________________

## [2.0.0] - 2026-03-23

### Changed

- Forked from execsql by R.Dreas Nielsen; repackaged as execsql2 with Python 3.13 support and modern tooling.
- Added support for Python 3.10, 3.11, 3.12, and 3.13; dropped Python 2 compatibility.
- Distributed as the `execsql2` package on PyPI; CLI entry point remains `execsql`.

______________________________________________________________________

## [1.130.0] - 2024-12-18

### Added

- Variable substitution to the `config_file` settings read from `execsql.conf`.

## [1.129.0] - 2024-05-21

### Added

- `PROMPT MESSAGE` metacommand that only displays a message in a dialog box.

## [1.128.0] - 2024-05-12

### Added

- Sash between the tables displayed by the `PROMPT COMPARE` metacommand so they can be resized.

## [1.127.0] - 2024-04-09

### Added

- Menu item to table displays allowing columns to be hidden or shown.

## [1.126.1] - 2024-02-16

### Added

- Templates and scripts to the distribution, to be placed in the `execsql_extras` directory.

### Changed

- Improved sorting in tables shown by the `PROMPT DISPLAY` and other metacommands.

### Fixed

- Width specification for listboxes in the `PROMPT ENTRY_FORM` metacommand.

## [1.126.0] - 2024-02-15

### Added

- Horizontal scrollbar to listboxes used with the `PROMPT ENTRY_FORM` metacommand.
- Radio button support for the `PROMPT ENTRY_FORM` metacommand.

## [1.125.3] - 2024-02-09

### Fixed

- Spurious warnings when running under Python 3.12.

## [1.125.0] - 2023-12-13

### Added

- Command-line and configuration settings to use an `execsql.log` file in the user's home directory.

## [1.124.0] - 2023-12-12

### Added

- Optional `HELP` clauses for most metacommands that produce GUI dialogs.

## [1.123.0] - 2023-08-22

### Added

- `RESET DIALOG_CANCELED` metacommand.

## [1.122.0] - 2023-07-27

### Added

- `FREE` keyword to the `PROMPT DISPLAY` metacommand.
- `$SCRIPT_START_TIME_UTC` and `$CURRENT_TIME_UTC` substitution variables.

## [1.120.0] - 2023-07-16

### Changed

- Extended the `PROMPT ENTRY_FORM` specifications to allow listboxes, specification of height for listboxes and text areas, and specification of columns to create a multi-column form.

## [1.119.0] - 2023-07-15

### Changed

- `WRITE` metacommand now runs in a separate process.

## [1.118.0] - 2023-07-09

### Added

- 'Save as' menu items to the `PROMPT COMPARE` UI.

### Changed

- Performance improvement for the data type evaluator used by `IMPORT` and `COPY` metacommands.

## [1.117.0] - 2023-06-10

### Added

- Support for DuckDB databases.
- `EXPORT` metacommand extended to export data to SQLite and DuckDB databases.

## [1.115.0] - 2023-04-06

### Added

- Export of multiple tables to an ODS workbook with a single `EXPORT` metacommand.

## [1.114.0] - 2023-04-01

### Added

- `DELETE_EMPTY_COLUMNS` configuration metacommand and setting.

## [1.113.0] - 2023-03-26

### Added

- `BREAK` metacommand to allow early exit of loops and sub-scripts.

## [1.112.0] - 2023-03-20

### Added

- `!"!` replacement delimiter for substitution variables.

## [1.111.0] - 2023-01-09

### Added

- `PROMPT CREDENTIALS` metacommand.

## [1.110.0] - 2022-12-20

### Added

- `$SHEETS_IMPORTED`, `$SHEETS_TABLES`, and `$SHEETS_TABLES_VALUES` system variables.

## [1.109.0] - 2022-12-13

### Added

- `CONFIG WRITE_PREFIX` and `CONFIG WRITE_SUFFIX` metacommands and configuration settings.

## [1.108.0] - 2022-11-17

### Changed

- Renamed the `EMIT` metacommand to `SERVE`.

## [1.107.0] - 2022-11-02

### Added

- `CGI-HTML` type for the `EXPORT` metacommand.
- `SUB_QUERYSTRING` and `EMIT` metacommands to support use of execsql as a CGI script.

## [1.106.0] - 2022-10-27

### Changed

- `table_exists()` and `view_exists()` conditionals for Postgres now only look for tables in the temporary-table schema or in a schema on Postgres' search path.

## [1.105.0] - 2022-10-19

### Added

- `CD` metacommand.

## [1.104.0] - 2022-10-15

### Added

- `trim_column_headers` configuration setting and configuration metacommand.

## [1.103.0] - 2022-07-23

### Changed

- Extended the `EXPORT_METADATA` metacommand to insert metadata into a database table.

## [1.102.0] - 2022-06-21

### Added

- Import from data files in Feather format.

## [1.101.0] - 2022-06-18

### Added

- Import from data files in Parquet format.

## [1.100.3] - 2022-04-30

### Fixed

- `PROMPT ENTRY_FORM` no longer closes the form when the 'Enter' key is pressed while a checkbox has focus.

## [1.100.1] - 2022-02-22

### Added

- Bottom border to the header row and top-alignment of body cells to ODS export.

## [1.100.0] - 2022-02-20

### Added

- `INITIALLY` clause to the `PROMPT ENTER_SUB` metacommand.

## [1.99.0] - 2022-02-19

### Added

- Variant `IMPORT` metacommands that use a `SHEETS MATCHING <regex>` clause to import multiple sheets from an OpenDocument or Excel workbook in one step.

## [1.98.0] - 2022-01-12

### Added

- `FOLD_COLUMN_HEADERS` configuration setting.

### Changed

- Column header cleaning now adds an underscore to the beginning of any column header that starts with a digit.

## [1.97.0] - 2022-01-08

### Added

- `CONTAINS`, `ENDS_WITH`, and `STARTS_WITH` conditional tests.

### Changed

- `textarea` control in an `ENTRY_FORM` now allows newlines to be inserted and strips trailing newlines.
- SQL statement evaluator now ignores multiple terminating semicolons.

## [1.96.0] - 2022-01-03

### Changed

- Reading of `.xlsx` files now uses the `openpyxl` library (new requirement).

## [1.95.0] - 2021-12-03

### Changed

- `SYSTEM_CMD` metacommand now logs the command to `execsql.log`.

## [1.94.0] - 2021-10-19

### Added

- `$PATHSEP` system variable.

### Changed

- `INCLUDE` and `IMPORT` metacommands now recognize leading tildes on the filename.

## [1.93.0] - 2021-10-02

### Added

- `USER` variant of the `CONNECT` metacommand.

## [1.92.0] - 2021-09-19

### Added

- `TRIM_STRINGS` and `REPLACE_NEWLINES` settings.

## [1.91.0] - 2021-09-16

### Added

- `DIALOG_CANCELED()` conditional.

## [1.90.0] - 2021-08-08

### Changed

- Metacommand patterns are now dynamically re-ordered to match usage.

## [1.89.1] - 2021-05-18

### Changed

- Column name `user` renamed to `username` in the output of the `EXPORT_METADATA` metacommand.

## [1.89.0] - 2021-03-17

### Added

- `TEE` clause to the `HALT` metacommand.

## [1.88.0] - 2021-02-13

### Added

- `EXPORT_METADATA` metacommand.

## [1.87.0] - 2021-02-10

### Added

- `ZIP` metacommand.

## [1.86.0] - 2021-02-09

### Added

- `create_column_headers` configuration setting and configuration metacommand.

## [1.85.0] - 2021-02-09

### Added

- `zip_buffer_mb` configuration setting and configuration metacommand.

## [1.84.0] - 2021-02-06

### Added

- `EXPORT` directly to a zip file for most export formats.

## [1.83.0] - 2021-01-09

### Changed

- Interpretation of both `config_file` and `linux_config_file` settings now expands a leading `~` to the user's home directory.

## [1.82.0] - 2020-11-14

### Added

- Console window size configuration options in `execsql.conf`.

### Changed

- Console height and width configuration metacommands now change settings for any future console windows as well as any currently open console.

## [1.81.0] - 2020-11-08

### Added

- `only_strings` configuration setting and metacommand.

## [1.80.0] - 2020-10-26

### Added

- `linux_config_file` and `win_config_file` configuration settings.

## [1.79.0] - 2020-08-29

### Added

- `ENCODING` clause to the `WRITE CREATE_TABLE` metacommand for text files.

## [1.78.0] - 2020-08-08

### Changed

- `PROMPT SELECT_ROWS` metacommand now sets a grey background on selected rows.

## [1.77.0] - 2020-07-29

### Added

- `$STARTING_SCRIPT_REVTIME` system variable.

## [1.76.0] - 2020-07-18

### Added

- Configuration option and metacommand to deduplicate repeated column headers in IMPORTed data.

### Changed

- Column header cleaning now strips leading and trailing spaces.

## [1.75.0] - 2020-07-16

### Added

- More quoting characters for the `WRITE` metacommand.

## [1.74.3] - 2020-07-11

### Fixed

- `ASK` metacommand under Python 3 on Windows.

## [1.74.1] - 2020-07-08

### Added

- `import_row_buffer` setting and `CONFIG IMPORT_ROW_BUFFER` metacommand to allow buffer size customization.

### Changed

- `IMPORT` metacommand now buffers input rows for slightly better performance.

## [1.73.0] - 2020-05-01

### Changed

- `execsql.log` is now set to read-only on exit.

## [1.72.2] - 2020-03-31

### Fixed

- Correction to 2020-03-30 modification.

## [1.72.0] - 2020-03-30

### Added

- `export_row_buffer` setting and `CONFIG EXPORT_ROW_BUFFER` metacommand to allow buffer size customization.

### Changed

- Export buffer size modified for better performance.

## [1.71.2] - 2020-03-29

### Added

- Encoding name translations to allow more encoding name aliases when using the `EXPORT` metacommand with Postgres.

## [1.71.0] - 2020-03-21

### Added

- `CONFIG LOG_DATAVARS` metacommand and `log_datavars` configuration setting.

## [1.70.0] - 2020-03-14

### Added

- `"!'!"` substitution delimiter.
- `SUB_EMPTY` conditional test.

## [1.69.0] - 2020-03-07

### Added

- Export to HDF5 files.

## [1.68.0] - 2020-03-03

### Added

- `IF EXISTS` clause to the `EXECUTE SCRIPT` metacommand.

## [1.67.0] - 2020-02-22

### Added

- `EXTEND SCRIPT WITH SQL` and `EXTEND SCRIPT WITH METACOMMAND` metacommands.
- `APPEND SCRIPT` aliased to `EXTEND SCRIPT...WITH SCRIPT`.

## [1.66.0] - 2020-02-22

### Added

- `DISCONNECT` metacommand.

## [1.65.0] - 2020-02-22

### Added

- `CONFIG SCAN_LINES` and `CONFIG GUI_LEVEL` metacommands.

## [1.64.0] - 2020-02-22

### Added

- `LOCAL` and `USER` keywords to the `DEBUG LOG SUBVARS` metacommand.

## [1.63.0] - 2020-02-15

### Changed

- `CONFIG` metacommands now accept `0` or `1` as arguments.

## [1.62.0] - 2020-02-13

### Added

- `CONFIG DAO_FLUSH_DELAY_SECS` metacommand and `dao_flush_delay_secs` configuration file setting.

## [1.61.0] - 2020-02-05

### Added

- `PROMPT PAUSE` metacommand.
- execsql version number is now written to `execsql.log`.

## [1.60.0] - 2020-02-01

### Added

- `LOOP` metacommand.

## [1.59.0] - 2020-01-31

### Added

- `$STARTING_PATH` and `$CURRENT_PATH` system variables.

## [1.58.0] - 2020-01-28

### Changed

- `PAUSE` and `ASK` metacommands now allow apostrophes and square brackets as string delimiters.

## [1.57.0] - 2020-01-25

### Changed

- Evaluation of conditionals now accepts Boolean literals.

## [1.56.0] - 2019-12-27

### Added

- `ROLE_EXISTS` conditional.

## [1.55.0] - 2019-12-26

### Added

- `CONTINUE` keyword to the `SYSTEM_CMD` metacommand.

## [1.54.0] - 2019-12-20

### Added

- `BEGIN`/`END SQL` metacommands.

## [1.53.0] - 2019-10-27

### Added

- Oracle database support.

## [1.52.0] - 2019-10-11

### Added

- Export to XML.

## [1.51.0] - 2019-10-10

### Added

- `WHILE` and `UNTIL` loop control to `EXECUTE SCRIPT`.
- Deferred variable substitution.

## [1.50.0] - 2019-10-05

### Added

- Numeric expression parser for the `SUB_ADD` and `SET COUNTER` metacommands.

## [1.49.0] - 2019-10-04

### Added

- Conditional expression parser for the `IF` metacommands.

## [1.48.0] - 2019-09-27

### Added

- `CONFIG EMPTY_ROWS` metacommand and `empty_rows` configuration setting.

## [1.47.0] - 2019-09-21

### Added

- `FROM` keyword to `PROMPT OPENFILE`, `SAVEFILE`, and `DIRECTORY` metacommands.

## [1.46.0] - 2019-09-04

### Added

- `COMPACT` keyword to the `PROMPT ACTION` metacommand.

## [1.45.0] - 2019-09-01

### Added

- `SCRIPT_EXISTS` conditional.
- `PROMPT ACTION` metacommand.

## [1.43.0] - 2019-08-27

### Added

- `PROMPT SELECT_ROWS` metacommand.

## [1.42.1] - 2019-08-22

### Fixed

- `EXPORT...AS VALUES` now correctly writes `NULL` for null data.

## [1.42.0] - 2019-08-18

### Added

- `APPEND SCRIPT` metacommand.

## [1.41.0] - 2019-08-17

### Added

- Export option to produce a JSON table schema.

## [1.40.0] - 2019-08-16

### Added

- `USER` keyword to the `DEBUG WRITE SUBVARS` metacommand.

## [1.39.0] - 2019-08-16

### Added

- `SUB_INI` metacommand.

## [1.38.8] - 2019-06-30

### Added

- Input and output filename prompt options to the entry form specifications.

## [1.37.7] - 2019-05-10

### Fixed

- Error messages containing bad data are now protected from encoding errors.

## [1.37.6] - 2019-05-07

### Changed

- Removed Unicode conversion of data when loaded into Tkinter Treeview control.
- Added `MARS_Connection=Yes` to SQL Server ODBC connections.

## [1.37.4] - 2019-05-04

### Added

- SQL Server ODBC drivers 13.1 and 17.

### Changed

- Improved efficiency of `COPY` metacommand.

### Fixed

- `int`/`long` conversion for Python 3 with Access.

## [1.37.0] - 2019-03-16

### Added

- `PASSWORD` keyword to the `CONNECT` metacommand for SQL Server.

## [1.36.0] - 2019-03-11

### Changed

- Switched to three-part semantic version number.

## [1.35.2.0] - 2019-02-27

### Added

- `WITH COMMIT|ROLLBACK` clause to the `AUTOCOMMIT ON` metacommand.

## [1.35.1.0] - 2019-02-23

### Added

- Warning if a SQL statement is incomplete when a metacommand is encountered.
- Error if a SQL statement is incomplete at the end of a script file.
- `CONFIG WRITE_WARNINGS` metacommand.

## [1.35.0.0] - 2019-02-21

### Changed

- Substitution metacommands now accept a `+` prefix to reference local variables in outer scopes.

## [1.34.9.0] - 2019-02-18

### Added

- `ON ERROR_HALT EXECUTE SCRIPT` and `ON CANCEL_HALT EXECUTE SCRIPT` metacommands.

## [1.34.8.0] - 2019-02-12

### Changed

- Improved reporting of origin lines of mismatched `IF` conditionals.

## [1.34.7.0] - 2019-02-09

### Added

- System variables for execsql's primary, secondary, and tertiary version numbers.
- Script name can now be specified on the `END SCRIPT` metacommand.

### Changed

- Quotes are now optional on the arguments to the `is_true`, `equal`, and `identical` conditionals.

## [1.34.4.0] - 2019-02-08

### Added

- Configuration option to clean IMPORTed column headers of non-alphanumeric characters.

## [1.34.2.0] - 2019-02-03

### Added

- Raises an exception if there is an incomplete SQL statement at `END SCRIPT`.
- Issues a warning if `IF` levels are unbalanced within a script.
- Issues a warning if a command appears to have an unsubstituted variable.

## [1.34.0.0] - 2019-02-02

### Added

- Optional `WITH ARGUMENTS` extension to the `EXECUTE SCRIPT` metacommand.
- Optional `WITH PARAMETERS` extension to the `BEGIN SCRIPT` metacommand.

## [1.33.0.0] - 2019-01-19

### Added

- `PROMPT ASK...COMPARE` metacommand.

### Changed

- All `ASK` metacommands and the `SUBDATA` metacommand can now set local variables.

## [1.32.0.0] - 2018-12-16

### Added

- Export to the Feather file format.

## [1.31.13.0] - 2018-11-07

### Added

- `quote_all_text` output setting and `CONFIG QUOTE_ALL_TEXT` metacommand.

## [1.31.12.0] - 2018-11-03

### Added

- `CONSOLE WIDTH` and `CONSOLE HEIGHT` metacommands.

### Changed

- `PROMPT ENTRY_FORM` now recognizes local variables.
- All `CONFIG` metacommands that take Boolean arguments now recognize both `Yes`/`No` and `On`/`Off`.

## [1.31.10.0] - 2018-10-30

### Added

- Asterisks to denote required entries on `PROMPT ENTRY_FORM`.

## [1.31.9.0] - 2018-10-29

### Added

- Fifth variable to `PROMPT OPENFILE` and `PROMPT SAVEFILE` to get the base filename without path or extension.

## [1.31.8.0] - 2018-10-25

### Changed

- `RM_FILE` metacommand now accepts wildcards.

## [1.31.7.0] - 2018-10-23

### Added

- Optional second, third, and fourth substitution variable names to `PROMPT SAVEFILE` for filename-only, path-only, and extension.

## [1.31.6.0] - 2018-10-22

### Added

- Optional third and fourth substitution variable names to `PROMPT OPENFILE` for path-only and extension.

## [1.31.5.0] - 2018-10-15

### Added

- Optional second substitution variable name to `PROMPT OPENFILE` for filename without path.

## [1.31.4.0] - 2018-10-14

### Added

- `ENCODING` clause to the `IMPORT...FROM EXCEL` metacommand.

## [1.31.3.0] - 2018-10-14

### Added

- Sorting of tabular displays by clicking on column headers.

### Changed

- All path separators returned by `PROMPT OPENFILE`, `SAVEFILE`, and `DIRECTORY` are converted from `/` to `\\` on Windows.

## [1.31.1.0] - 2018-10-09

### Added

- `LOCAL` clause to `DEBUG WRITE SUBVARS`.

## [1.31.0.0] - 2018-10-07

### Added

- Local variables.

## [1.30.6.0] - 2018-09-30

### Added

- Button to show unmatched rows in the `PROMPT COMPARE` display.
- `IF EXISTS` clause to the `INCLUDE` metacommand.
- `IF CONSOLE_ON` conditional test.

## [1.30.3.0] - 2018-09-29

### Added

- `IN <alias>` clauses to the `PROMPT COMPARE` metacommand.
- Checkbox to the `PROMPT COMPARE` GUI to allow highlighting of matches in both tables.

## [1.30.1.0] - 2018-09-23

### Changed

- `PROMPT COMPARE` command now highlights all matching rows in the other table, not just the first.

## [1.30.0.0] - 2018-09-22

### Changed

- Binary data length is now written as a description when binary data are used with `PROMPT DISPLAY` or `EXPORT AS TXT`.

## [1.29.3.0] - 2018-09-22

### Changed

- `WRITE` metacommand now uses the `make_export_dirs` configuration setting.

## [1.29.2.0] - 2018-09-19

### Added

- `SUB_ADD` metacommand.

### Changed

- `WITH` keyword is now optional in the `IMPORT` metacommand.

## [1.29.0.0] - 2018-09-12

### Added

- `IMPORT_FILE` metacommand.

## [1.28.0.0] - 2018-08-19

### Added

- Python 3.x compatibility (in addition to 2.7).

## [1.27.4.0] - 2018-08-19

### Changed

- Python version number is now written to `execsql.log`.

## [1.27.3.0] - 2018-07-31

### Changed

- Configuration files are now read from both the script directory and the starting directory, if different.

## [1.27.2.0] - 2018-07-30

### Added

- `SUB_EMPTY` metacommand.

## [1.27.1.0] - 2018-07-29

### Changed

- `ON ERROR_HALT WRITE` and `ON CANCEL_HALT WRITE` metacommands now allow single quotes and square brackets.

## [1.27.0.0] - 2018-07-29

### Changed

- Internal script processing routines rewritten.

## [1.26.8.0] - 2018-07-25

### Changed

- `WRITE` metacommand now allows single quotes and square brackets.
- Data format evaluation used by `IMPORT` now takes account of the `empty_strings` configuration setting.

### Fixed

- Stripping of extra spaces from input data when input is not strings.

## [1.26.5.0] - 2018-07-20

### Added

- `$PYTHON_EXECUTABLE` system variable.

### Changed

- Strings of only spaces are now treated as empty strings when `empty_strings=False`.

### Fixed

- Trailing space is now trimmed from the last column header of an IMPORTed CSV file.

## [1.26.4.3] - 2018-07-12

### Fixed

- Handling of double-quoted filenames by the `ON ERROR_HALT WRITE` and `ON CANCEL_HALT WRITE` metacommands.

## [1.26.4.2] - 2018-07-09

### Fixed

- Handling of double-quoted filenames by the `WRITE` and `RM_FILE` metacommands.

## [1.26.4.0] - 2018-06-27

### Added

- `$STARTING_SCRIPT_NAME` and `$CURRENT_SCRIPT_NAME` system variables.
- `IS_TRUE` conditional.

## [1.26.2.0] - 2018-06-25

### Added

- `$CURRENT_SCRIPT_PATH` system variable that returns the path only of the current script file.

## [1.26.1.0] - 2018-06-13

### Changed

- `HALT` metacommands now set the exit code to 3.

### Fixed

- Hang on uppercase counter references.

## [1.26.0.0] - 2018-06-13

### Added

- `ON CANCEL_HALT WRITE` and `ON CANCEL_HALT EMAIL` metacommands.

## [1.25.0.0] - 2018-06-10

### Added

- `PROMPT COMPARE` metacommand.

## [1.24.12.0] - 2018-06-09

### Added

- `MAKE_EXPORT_DIRS` metacommand.

### Changed

- All metacommands corresponding to configuration options are grouped under a common `CONFIG` prefix.
- Configuration file size and date are now written to `execsql.log` when a configuration file is read.

## [1.24.9.0] - 2018-06-03

### Changed

- `IMPORT` metacommand now writes the file name, file size, and file date to `execsql.log`.

## [1.24.8.0] - 2018-06-03

### Changed

- Added filename to error message when the `IMPORT` metacommand cannot find a file.
- `SUBDATA` now only removes the substitution variable (rather than raising an exception) when there are no rows in the specified table or view.

### Fixed

- `is_null()`, `equals()`, and `identical()` now correctly strip quotes.

## [1.24.7.0] - 2018-04-03

### Added

- `$SYSTEM_CMD_EXIT_STATUS` system variable.

## [1.24.6.0] - 2018-04-01

### Added

- `B64` format to the `EXPORT` and `EXPORT_QUERY` metacommands.

## [1.24.5.0] - 2018-03-15

### Added

- `textarea` entry type to the `PROMPT ENTRY_FORM` metacommand.

## [1.24.4.0] - 2017-12-31

### Added

- `-o` command-line option to display online help.

### Changed

- `CREATE SCRIPT` is now an alias for `BEGIN SCRIPT`.
- `DEBUG WRITE SCRIPT` is now an alias for `WRITE SCRIPT`.

## [1.24.2.0] - 2017-12-30

### Added

- `TYPE` and `LCASE`/`UCASE` keywords to the `PROMPT ENTER_SUB` metacommand.

### Changed

- Modified characters allowed in user names for Postgres and ODBC connections.

## [1.24.0.0] - 2017-11-04

### Added

- `include_required` and `include_optional` configuration settings.

## [1.23.3.0] - 2017-11-03

### Added

- `CONSOLE_WAIT_WHEN_ERROR_HALT` setting, associated metacommand, and system variable.

## [1.23.2.0] - 2017-11-02

### Added

- `$ERROR_MESSAGE` system variable.

## [1.23.1.0] - 2017-10-20

### Added

- `ASK` metacommand.

## [1.23.0.0] - 2017-10-09

### Added

- `ON ERROR_HALT EMAIL` metacommand.

## [1.22.0.0] - 2017-10-07

### Added

- `ON ERROR_HALT WRITE` metacommand.

## [1.21.13.0] - 2017-09-29

### Added

- `SUB_APPEND` and `WRITE SCRIPT` metacommands.

### Changed

- All metacommand messages now allow multiline text.

## [1.21.12.0] - 2017-09-24

### Added

- `PG_VACUUM` metacommand.

## [1.21.11.0] - 2017-09-23

### Changed

- Error message content and format.

## [1.21.10.0] - 2017-09-12

### Added

- `error_response` configuration setting for encoding mismatches.

## [1.21.9.0] - 2017-09-06

### Changed

- Now handles trailing comments on SQL script lines.

## [1.21.8.0] - 2017-08-11

### Changed

- `CONNECT` metacommand for MySQL now allows a password to be specified.

## [1.21.7.0] - 2017-08-05

### Added

- `DEBUG` metacommands.

### Changed

- `IMPORT` metacommand now allows CSV files with more columns than the target table.

## [1.21.1.0] - 2017-07-04

### Changed

- Column headers are now passed to template processors as a separate object.

## [1.21.0.0] - 2017-07-01

### Added

- `EXPORT` metacommand extended to allow several different template processors to be used.

## [1.20.0.0] - 2017-06-30

### Added

- `EMAIL`, `SUB_ENCRYPT`, and `SUB_DECRYPT` metacommands.
- Configuration properties to support emailing.
- `METACOMMAND_ERROR_HALT` metacommand.
- `$METACOMMAND_ERROR_HALT_STATE` system variable.
- `METACOMMAND_ERROR()` conditional.

## [1.18.0.0] - 2017-06-24

### Changed

- Improved speed of import of CSV files to Postgres and MySQL/MariaDB.
- `EXPORT...APPEND...AS HTML` metacommand now appends tables inside the first `</body>` tag.

## [1.17.0.0] - 2017-05-28

### Changed

- `PROMPT ENTRY_FORM` specifications extended to allow checkboxes.

## [1.16.9.0] - 2017-05-27

### Added

- `DESCRIPTION` keyword to the `EXPORT` metacommands.

## [1.16.8.0] - 2017-05-20

### Added

- `VALUES` export format.

## [1.16.7.0] - 2017-05-20

### Added

- `BOOLEAN_INT` and `BOOLEAN_WORDS` metacommands.
- `console_wait_when_done` configuration parameter.

### Changed

- `PAUSE` metacommand now accepts fractional timeout arguments.
- Server name is now added to the password prompt.

## [1.16.3.0] - 2017-04-23

### Added

- Configuration option allowing specification of additional configuration files to read.
- `MAX_INT` configuration parameter and metacommand.

## [1.16.0.0] - 2017-03-25

### Added

- `BEGIN SCRIPT`, `END SCRIPT`, and `EXECUTE SCRIPT` metacommands.

## [1.15.0.0] - 2017-03-09

### Added

- `TEE` keyword to the `WRITE`, `EXPORT`, and `EXPORT QUERY` metacommands.

## [1.13.0.0] - 2017-03-05

### Added

- `LOG_WRITE_MESSAGES` metacommand and configuration parameter.

## [1.12.0.0] - 2017-03-04

### Added

- `boolean_words` configuration option.
- Reading of CSV files with newlines within delimited text data.
- `SKIP` keyword to the `IMPORT` metacommand for CSV, ODS, and Excel data.
- `COLUMN_EXISTS` conditional.

## [1.8.15.0] - 2017-01-14

### Added

- `$LAST_ROWCOUNT` system variable.

## [1.8.14.0] - 2016-11-13

### Added

- Evaluation of numeric types in input.
- `empty_strings` configuration parameter and metacommand.

### Fixed

- Corrections to `IMPORT` metacommand for Firebird.

## [1.8.13.0] - 2016-11-07

### Added

- `-b` command-line option and configuration parameter.

## [1.8.12.0] - 2016-10-22

### Added

- `RM_SUB` metacommand.

## [1.8.11.0] - 2016-10-19

### Added

- `SET COUNTER` metacommand.

## [1.8.10.2] - 2016-10-17

### Added

- `$RUN_ID` system variable.

### Changed

- Now recognizes as text any imported data that contains only numeric values where the first digit of any value is a zero.

## [1.8.8.0] - 2016-09-28

### Added

- `$CURRENT_ALIAS`, `$RANDOM`, and `$UUID` system variables.

## [1.8.4.0] - 2016-08-13

### Added

- Import from MS-Excel.

### Changed

- Logging of database close when autocommit is off.

### Fixed

- Parsing of numeric time zones.

## [1.7.3.0] - 2016-08-05

### Added

- `$OS` system variable.

## [1.7.2.0] - 2016-06-11

### Added

- `DIRECTORY_EXISTS` conditional.
- Option to automatically make directories used by the `EXPORT` metacommand.

## [1.7.0.0] - 2016-05-20

### Added

- `NEWER_DATE` and `NEWER_FILE` conditionals.

## [1.6.0.0] - 2016-05-15

### Added

- `CONSOLE SAVE` metacommand.
- DSN connections.
- `COPY QUERY` and `EXPORT QUERY` metacommands.

## [1.4.4.0] - 2016-05-02

### Added

- `CONSOLE HIDE`/`SHOW` metacommands.

### Changed

- `CONSOLE WAIT` metacommand now accepts `<Enter>` to continue without closing.

## [1.4.2.0] - 2016-05-02

### Added

- "Save as..." menu to the GUI console.

### Changed

- `PAUSE` and `HALT` metacommands now use a GUI if the console is on.

## [1.4.0.0] - 2016-04-30

### Added

- GUI console with a status bar and progress bar to which `WRITE` output and exported text will be written.

## [1.3.3.0] - 2016-04-09

### Added

- Additional 'Save as...' options in `PROMPT DISPLAY` metacommand.
- Date/time values exported to ODS.

## [1.3.2.0] - 2016-02-28

### Added

- Backslash as a line continuation character for SQL statements.

## [1.3.1.0] - 2016-02-20

### Added

- `PROMPT ENTRY_FORM` and `LOG` metacommands.

## [1.2.15.0] - 2016-02-14

### Added

- `$DB_NAME`, `$DB_NEED_PWD`, `$DB_SERVER`, and `$DB_USER` system variables.
- `RAW` export format for binary data.
- `PASSWORD` keyword to the `PROMPT ENTER_SUB` metacommand.
- Password support in the `CONNECT` metacommand for Access.

## [1.2.10.0] - 2016-01-23

### Added

- `ENCODING` keyword to `IMPORT` metacommand.
- `TIMER` metacommand and `$TIMER` system variable.

## [1.2.8.2] - 2016-01-21

### Fixed

- Extra quoting in drop table method.
- `str` coercion in TXT export.

## [1.2.8.0] - 2016-01-11

### Changed

- Column headers are suppressed when EXPORTing to CSV and TSV with `APPEND`.
- Eliminated `%H%M` pattern to match time values in IMPORTed data.

## [1.2.7.1] - 2016-01-03

### Added

- `AUTOCOMMIT` metacommand.

### Changed

- Modified import of integers to Postgres.
- `BATCH` metacommand modified.
- Now explicitly rolls back any uncommitted changes on exit.

### Fixed

- Miscellaneous bug fixes.

## [1.2.4.6] - 2015-12-19

### Changed

- Modified quoting of column names for the `COPY` and `IMPORT` metacommands.

## [1.2.4.5] - 2015-12-17

### Fixed

- Asterisks in `PROMPT ENTER_SUB`.

## [1.2.4.4] - 2015-12-14

### Fixed

- Regexes for quoted filenames.

## [1.2.4.3] - 2015-12-13

### Fixed

- `-y` option display.
- Parsing of `WRITE CREATE_TABLE` comment option.
- Parsing of backslashes in substitution strings on Windows.

## [1.2.4.0] - 2015-11-21

### Added

- Connections to PostgreSQL, SQL Server, MySQL, MariaDB, SQLite, and Firebird.
- Numerous metacommands and conditional tests.
- Reading of configuration files.

## [0.4.4.0] - 2010-06-20

### Added

- `INCLUDE`, `WRITE`, `EXPORT`, `SUB`, `EXECUTE`, `HALT`, and `IF` (`HASROWS`, `SQL_ERROR`) metacommands.

## [0.3.1.0] - 2008-12-19

### Added

- Internal documentation.

## [0.3.0.0] - 2008-05-20

### Added

- `cp1252` encoding for data read from Access.

## [0.2.0.0] - 2008-04-26

### Added

- Creation and deletion of temporary views (queries).
- Export of final query to Excel.

## [0.1.2.0] - 2008-04-22

### Changed

- Added regular expressions to match `create temp view...` SQL command preface.

## [0.1.1.0] - 2008-04-20

### Changed

- Converted to use DAO instead of the dbconnect library.

## [0.1.0.0] - 2008-01-01

### Added

- Writing of the output of the last SQL command to a CSV file.

## [0.0.1.0] - 2007-11-11

### Added

- Initial release; executes SQL against Access.
