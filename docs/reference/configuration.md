# Configuration Files

In addition to, or as an alternative to, command-line options and arguments, configuration files can be used to specify most of the same information, plus some additional information. Most of the command-line options and arguments can be specified in a configuration file, with the exception of the script name. The script name must always be specified on the command line.

*execsql* will automatically read information from up to four configuration files in different standard locations, if they are present. The four locations are:

> - The system-wide application data directory. This is `/etc` on Linux, and `%APPDATA%` on Windows.
> - The user-specific configuration directory. This is a directory named `.config` under the user's home directory on both Linux and Windows.
> - The directory where the script file is located.
> - The directory from which *execsql* was started.

The name of the configuration file, in all locations, is `execsql.conf`.

Configuration data is read from these files in the order listed above. Information in later files may augment or replace information in earlier files. Options and arguments specified on the command line will further augment or override information specified in the configuration files.

An explicit configuration file can also be specified with the `--config FILE` command-line option. This file is loaded **after** all four implicit search paths, so its values take precedence over system, user, script-directory, and working-directory config files. CLI arguments still override everything. The `--config` file may chain additional configs via its `[config]` section, just like any other config file.

To generate a starter configuration file with all options commented out and documented, use:

```bash
execsql --init-config > execsql.conf
```

In addition, *execsql* will read additional configuration files if they are specified in any of the standard configuration files ([see below](#config_config)).

Configuration files use the [INI](https://en.wikipedia.org/wiki/INI_file) file format. Section names are case sensitive and must be all in lowercase. Property names are not case sensitive. Property values are read as-is and may or may not be case sensitive, depending on their use. Comments can be included in configuration files; each comment line must start with the "#" character.

The section and property names that may be used in a configuration file are listed below.

## Section `connect` { #config_connect }

`db_type`
:   The type of database. This is equivalent to the "-t" command-line option, and the same list of single-character codes are the only valid property values.

`server`
:   The database server name. This is equivalent to the second command-line argument for client-server databases.

`db`
:   The database name. This is equivalent to the third command-line argument for client-server databases. The alias `database` is also accepted.

`db_file`
:   The name of the database file. This is equivalent to the second command-line argument for file-based databases.

`port`
:   The port number for the client-server database. This is equivalent to the "-p" command-line option.

`username`
:   The name of the database user, for client-server databases. This is equivalent to the "-u" command-line option.

`access_username`
:   The name of the database user, for MS-Access databases only. When using MS-Access, a password will be prompted for only if this configuration option is set or the "-u" command-line option is used, regardless of the setting of the username configuration parameter.

`password_prompt`
:   Indicates whether or not *execsql* should prompt for the user's password. The property value should be either "Yes" or "No". The default is "Yes". This is equivalent to the "-w" command-line option.

`use_keyring`
:   When set to "Yes" (the default) and the `keyring` Python package is installed, *execsql* checks the OS credential store (macOS Keychain, Windows Credential Manager, or Linux SecretService) before prompting for a password. After a successful interactive prompt the password is automatically stored in the keyring for future use. Set to "No" to disable keyring integration entirely. Install with `pip install execsql2[auth]`.

`new_db`
:   Indicates whether or not *execsql* should create a new PostgreSQL or SQLite database to connect to.

## Section `encoding`

`database`

:   The database encoding to use. This is equivalent to the `-e` command-line option.

`script`

:   The script encoding to use. This is equivalent to the `-f` command-line option.

`import`

:   Character encoding for data imported with the IMPORT metacommand. This is equivalent to the `-i` command-line option.

`output`

:   Character encoding for data exported with the EXPORT metacommand. This is equivalent to the `-g` command-line option.

`error_response`

:   How to handle conditions where input or output files have incompatible encodings. If not specified, incompatible encodings will cause an error to occur, and *execsql* will halt. The property values you can use for this setting are:

    - "ignore": The inconvertible character will be omitted.
    - "replace": The inconvertible character will be replaced with a question mark.
    - "xmlcharrefreplace": The inconvertible character will be replaced with the equivalent HTML entity.
    - "backslashreplace": The inconvertible character will be replaced with an escape sequence consisting of decimal digits, preceded by a backslash.

## Section `input` { #config_input }

`access_use_numeric`

:   Whether or not to translate decimal (numeric) data types to double precision when the [IMPORT](metacommands.md#import) or [COPY](metacommands.md#copy) metacommands construct a CREATE TABLE statement for MS-Access. This property value should be either "Yes" or "No." The default value is "No".

`boolean_int`

:   Whether or not to consider integer values of 0 and 1 as Booleans when scanning data during import or copying. The property value should be either "Yes" or "No". The default value is "Yes". By default, if a data column contains only values of 0 and 1, it will be considered to have a Boolean data type. By setting this value to "No", such a column will be considered to have an integer data type. This is equivalent to the "-b" command-line option.

`boolean_words`

:   Whether or not to recognize only full words as Booleans. If this value is "No" (the default), then values of "Y", "N", "T", and "F" will be recognized as Booleans. If this value is "Yes", then only "Yes", "No", "True", and "False" will be recognized as Booleans. This setting is independent of the `boolean_int` setting.

`clean_column_headers`

:   Whether or not to replace non-alphanumeric characters in column headers with the underscore character when data are IMPORTed. The default value is "No". If this is set to "Yes", any characters in a column header except letters, digits, and the underscore character will be replaced by the underscore character.

    This setting is also applied to the conversion of spreadsheet names to table names when multiple worksheets are [IMPORTed](metacommands.md#import).

`create_column_headers` { #create_column_headers }

:   Whether or not to create column headers if they are missing from an input file. The default value is "No". If this is set to "Yes", missing column headers will be created as "Col" followed by the column number. If the `delete_empty_columns` value is set to "Yes", empty columns will be deleted and so no column headers will be synthesized regardless of this setting.

`dedup_column_headers`

:   Whether or not to make duplicated column headers unique by appending an underscore and the column number. Evaluation of the equivalence of column headers is case-insensitive. The default value is "No".

`delete_empty_columns` { #setting_del_empty_cols }

:   Whether or not to delete entire columns from imported data tables when the column headers are missing. The value should be either "Yes" or "No". The default is "No". Column headers are considered to be missing when they are absent or consist only of spaces.

`empty_rows`

:   Determines whether empty rows in the input are added to a data table by the [IMPORT](metacommands.md#import) and [COPY](metacommands.md#copy) metacommands. The property value should be either "Yes" or "No". The default, "Yes", allows empty rows to be added to a table (subject to non-null and check constraints on the table). When this is set to "No", rows that contain no data will not be added to the table. An empty string is considered to be data, so when this is used, the `empty_strings` setting will ordinarily also have to be used. The metacommand [CONFIG EMPTY_ROWS](metacommands.md#empty_rows) can also be used to change this configuration item.

`empty_strings`

:   Determines whether empty strings in the input are preserved or, alternatively, will be replaced by NULL. The property value should be either "Yes" or "No". The default, "Yes", indicates that empty strings are allowed. A value of "No" will cause all empty strings to be replaced by NULL. When this is set to "No", a string value consisting of a sequence of zero or more space characters will be considered to be an empty string. There is no command-line option corresponding to this configuration parameter, but the metacommand [CONFIG EMPTY_STRINGS](metacommands.md#empty_strings) can also be used to change this configuration item.

`fold_column_headers` { #setting_fold_column_headers }

:   Whether or not to fold (convert) the case of all column headers to lowercase or uppercase, or to leave them unchanged when data are [IMPORTed](metacommands.md#import). Valid values are "No" (the default), "Lower", and "Upper". Case does not matter in the specification.

    This setting is also applied to the conversion of spreadsheet names to table names when multiple worksheets are [IMPORTed](metacommands.md#import).

`import_buffer`

:   The size of the import buffer, in kilobytes, to use with the IMPORT metacommand. This is equivalent to the `-z` command-line option. This value is only used when the fast file reading capability of PostgreSQL is used.

`import_progress_interval` { #import_progress_interval }

:   Controls how often row-count progress is written to the execution log during IMPORT operations. Set to a positive integer N to log a status line every N rows (e.g. `import_progress_interval = 10000`). The default is `0` (silent). When enabled, a final completion line (e.g. "IMPORT into schema.table complete: 1000000 rows imported.") is also written. Supported for all database adapters.

`import_common_columns_only` { #import_only_common }

:   Determines whether the [IMPORT](metacommands.md#import) metacommand will import data from a CSV file when the file has more data columns than the target table. The property value should be either "Yes" or "No". The default, "No", indicates that the target table must have all of the columns present in the CSV file; if the target table has fewer columns, an error will result. A property value of "Yes" will result in import of only the columns in common between the CSV file and the target table. The legacy alias `import_only_common_columns` is also accepted.

`import_row_buffer`

:   The number of data rows to be buffered from a data source when importing data using the [IMPORT](metacommands.md#import) metacommand, and when a DBMS-specific fast file importing method can't be used. The setting value must be a positive integer greater than zero. The default value is 1000 rows.

`max_int`

:   Establishes the maximum value that will be assigned an integer data type when the IMPORT or COPY metacommands create a new data table. Any column with integer values less than or equal to this value (`max_int`) and greater than or equal to `-1 × max_int - 1` will be considered to have an 'integer' type. Any column with values outside this range will be considered to have a 'bigint' type. The default value for `max_int` is 2147483647. The `max_int` value can also be altered within a script using the [CONFIG MAX_INT](metacommands.md#max_int) metacommand.

`only_strings`

:   Determines whether data imported with the [IMPORT](metacommands.md#import) metacommand and the NEW or REPLACEMENT keywords will have their data types evaluated (the default) or whether all the data columns will be treated as text (character, character varying, or text). The default value is "No"; if this is set to "Yes", data will be imported as text.

`replace_newlines`

:   Replaces newline characters that are in text values on [IMPORT](metacommands.md#import). Every sequence of a newline and any surrounding whitespace is replaced with a single space character.

`show_progress`

:   Whether or not to display a rich progress bar during long-running IMPORT operations. The property value should be either "Yes" or "No". The default is "No". This can also be enabled via the `--progress` CLI flag or the `CONFIG SHOW_PROGRESS` metacommand. Requires the `rich` Python package.

`scan_lines` { #scan_lines }

:   The number of lines of a data file to scan to determine the quoting character and delimiter character used. This is equivalent to the `-s` command-line option. The default value is 100.

`trim_column_headers`

:   Whether or not to remove leading and/or trailing spaces and underscores from column headers when data are IMPORTed. Valid values are 'none', "both", "left", and "right". The default value is "none". Trimming is done after any cleaning of column headers. Trimming a leading underscore may invalidate a column header that would otherwise start with a digit.

`trim_strings`

:   Removes any leading and trailing whitespace from text data on [IMPORT](metacommands.md#import).

## Section `output` { #config_output }

`log_write_messages`
:   Specifies whether output of the [WRITE](metacommands.md#write) metacommand will also be written to *execsql*'s log file. The property value should be either "Yes" or "No". The default is "No". This configuration property can also be controlled within a script with the [CONFIG LOG_WRITE_MESSAGES](metacommands.md#logwritemessages) metacommand.

`make_export_dirs`
:   The output directories used in the [EXPORT](metacommands.md#export) and [WRITE](metacommands.md#write) metacommands will be automatically created if they do not exist (and the user has the necessary permission). The property value should be either "Yes" or "No". This is equivalent to the "-d" command-line option.

`quote_all_text`
:   Controls whether all text values written to a delimited text file by the [EXPORT](metacommands.md#export) metacommand will be quoted. The property value should be either "Yes" or "No"--the default is "No".

`outfile_open_timeout` { #setting_outfile_open_timeout }
:   When the [WRITE](metacommands.md#write) metacommand writes to a file, the file is opened in a separate process to try to avoid access conflicts that may occur if that file has been temporarily opened by some other user or process (such as a backup or syncing process). If the WRITE process cannot immediately open the file, the WRITE process will continue trying to open the file for the number of seconds specified by this setting. The WRITE process will buffer multiple output to a blocked file until the file is opened or this timeout period has expired. The WRITE process can also write to other files during the timeout period. If a file cannot be opened before the timeout expires, or before *execsql* finishes processing the script, all pending output to that file will be lost, and an error message will be written to *stderr*. The default value for this setting is 600.

`export_row_buffer` { #setting_export_row_buffer }
:   The number of data rows to be buffered from the database when exporting data. Larger values result in faster exports, up to a point, and at a diminishing rate of return. Larger values also require more memory. The setting value must be a positive integer greater than zero. The default value is 1000 rows. This value cannot be customized when using DuckDB.

`hdf5_text_len`
:   The length to be assigned to columns that have the 'text' data type when data are exported in the HDF5 format. The default is `1000`.

`css_file`
:   The URI of a CSS file to be included in the header of an HTML file created with the [EXPORT](metacommands.md#export) metacommand. If this is specified, it will replace the CSS styles that *execsql* would otherwise use.

`css_styles`
:   A set of CSS style specifications to be included in the header of an HTML file created with the [EXPORT](metacommands.md#export) metacommand. If this is specified, it will replace the CSS styles that *execsql* would otherwise use. Both css_file and css_style may be specified; if they are, they will be included in the header of the HTML file in that order.

`template_processor`
:   The name of the template processor that will be used with the [EXPORT](metacommands.md#export) and [EXPORT QUERY](metacommands.md#export_query) metacommands when a template file is specified. The only valid value for this property is "jinja". When set to "jinja", execsql renders the template file using [Jinja2](https://jinja.palletsprojects.com/), passing the full result set as two context variables — `headers` (a list of column names) and `datatable` (a list of row dicts) — so the template can loop, filter, and format the data freely. If this property is not specified, execsql uses Python's built-in `string.Template` processor instead, which applies the template individually to each row using `$column_name` placeholders. Use `jinja` when you need conditionals, loops, or more than simple per-row substitution in your output. Requires the `jinja2` Python package (`pip install jinja2`).

`zip_buffer_mb` { #zip_buffer_mb }
:   The size of the internal buffer used when the [EXPORT](metacommands.md#export) metacommand exports data to a zipfile, in Mb. The default value is 10. The buffer should be at least as large as the largest data row to be exported. This value typically has little effect on performance, and only affects memory usage.

!!! note "CLI-only output options"

    The [`--output-dir`](../getting-started/syntax.md) option sets a default base directory for EXPORT output files. Relative paths in EXPORT metacommands are automatically joined to this directory; absolute paths and `stdout` are unaffected. This option is **only available on the command line** — there is no equivalent configuration file setting.

## Section `interface`

`console_height`

:   Specifies the approximate height, in lines of text, for a console window that is created with the [CONSOLE ON](metacommands.md#console) metacommand.

`console_wait_when_done`

:   Controls the persistence of any [console window](metacommands.md#console) at the completion of the script when the script completes normally. If the property value is set to "Yes" (the default value is "No"), the console window will remain open until explicitly closed by the user. The message "Script complete; close the console window to exit execsql." will be displayed in the status bar. This setting has the same effect as a [CONFIG CONSOLE
    WAIT_WHEN_DONE](metacommands.md#console_wait_when_done) metacommand.

`console_wait_when_error_halt`

:   Controls the persistence of any [console window](metacommands.md#console) at the completion of the script if an error occurs. If the property value is set to "Yes" (the default value is "No"), the console window will remain open until explicitly closed by the user after an error occurs. The message "Script error; close the console window to exit execsql." will be displayed in the status bar. This setting has the same effect as a [CONFIG CONSOLE WAIT_WHEN_ERROR](metacommands.md#console_wait_when_error) metacommand.

`console_width`

:   Specifies the approximate width, in characters, for a console window that is created with the [CONSOLE ON](metacommands.md#console) metacommand.

`write_warnings` { #write_warnings }

:   Determines whether warning messages are written to the console as well as to the log file. The default value is "No", indicating that warnings will not be written to the console. If it is set to "Yes", warnings will be written to the console.

`write_prefix`

:   Text that will be prefixed to any output from the WRITE metacommand, with a space separator. If substitution variables are used, deferred substitution may be appropriate.

`write_suffix`

:   Text that will be appended to any output from the WRITE metacommand, with a space separator. If substitution variables are used, deferred substitution may be appropriate.

`gui_level` { #gui_level }

:   The level of interaction with the user that should be carried out using GUI dialogs. The property value must be 0, 1, 2, or 3. The meanings of these values are:

    - 0: Do not use any optional GUI dialogs.
    - 1: Use GUI dialogs for password prompts and for the [PAUSE](metacommands.md#pause) metacommand.
    - 2: Also use a GUI dialog if a message is included with the [HALT](metacommands.md#halt) metacommand, and prompt for the initial database to use if no database connection parameters are specified in a configuration file or on the command line.
    - 3: Additionally, open a GUI console when *execsql* starts.

`gui_framework` { #gui_framework }

:   The GUI framework to use when `gui_level` is greater than 0. The property value must be either `tkinter` (the default) or `textual`. `tkinter` uses native desktop dialogs via Tk; `textual` provides a terminal-based UI that works in headless/SSH environments. This can also be set via the `--gui-framework` command-line option.

## Section `email`

`host`

:   The SMTP host name to be used to transmit email messages sent using the [EMAIL](metacommands.md#email) metacommand. A host name must be specified to use the [EMAIL](metacommands.md#email) metacommand.

`port`

:   The port number of the SMTP host to use. If this is omitted, port 25 will be used unless either the `use_ssl` or `use_tls` configuration properties is also specified, in which case ports 465 or 587 may be used.

`username`

:   The name of the user if the SMTP server requires login authentication.

`password`

:   An unencrypted password to be used if the SMTP server requires login authentication.

`enc_password`

:   An encrypted password to be used if the SMTP server required login authentication. The encrypted version of a password should be exactly as produced by the [SUB_ENCRYPT](metacommands.md#sub_encrypt) metacommand. A suitably encrypted version of a password can be produced by running the script:

    ```sql
    -- !x! prompt enter_sub pw password message "Enter a password to encrypt"
    -- !x! sub_encrypt enc_pw !!pw!!
    -- !x! write "The encrypted password is: !!enc_pw!!"
    ```

    If both the `password` and `enc_password` configuration properties are used, the `enc_password` property will take precedence and will be used for SMTP authentication.

    !!! warning "Obfuscation only — not real encryption"

        The `enc_password` value is produced by a simple XOR operation using
        keys that are embedded in the execsql source code. Anyone with
        access to the source or the installed package can decode the
        password. Treat `enc_password` values in `execsql.conf` as
        **plaintext-equivalent**.

        For production deployments, prefer OS credential stores (e.g. macOS
        Keychain, Windows Credential Manager, `secret-tool` on Linux) or
        environment variables rather than storing passwords in configuration
        files.

`use_ssl`

:   SSL/TLS encryption will be used from the initiation of the connection.

`use_tls`

:   SSL/TLS encryption will be used after the initial connection is made using unencrypted text.

`email_format`

:   Specifies whether the message will be sent as plain text or as HTML email. The only valid values for this property are "plain" and "html". If not specified, emails will be sent in plain text.

`message_css`

:   A set of CSS rules to be applied to HTML email.

## Section `config` { #config_config }

`config_file`
:   The full name or path to an additional configuration file to be read. If only a path is specified, the name of the configuration file should be `execsql.conf`. The configuration file specified will be read immediately following the configuration file in which it is named. No configuration file will be read more than once. If the name or path are invalid, this setting will be silently ignored. This setting may include [substitution variables](substitution_vars.md#substitution_vars); at the time that configuration files are read, however, only environment variables and system variables related to the script name and path are defined.

`dao_flush_delay_secs`
:   The number of seconds that *execsql* should wait between the time that a query is created in Access (which uses DAO) and the time that the next statement is executed using ODBC. This value must be greater than or equal to 5.0. The default is `5.0`.

`linux_config_file`
:   The full name or path to an additional configuration file to be read if *execsql* is running on Linux (`sys.platform == "linux"`). If only a path is specified, the name of the configuration file should be `execsql.conf`. The configuration file specified will be read immediately following the configuration file in which it is named. No configuration file will be read more than once. If the name or path are invalid, this setting will be silently ignored. This setting may include [substitution variables](substitution_vars.md#substitution_vars); at the time that configuration files are read, however, only environment variables and system variables related to the script name and path are defined.

`macos_config_file`
:   The full name or path to an additional configuration file to be read if *execsql* is running on macOS (`sys.platform == "darwin"`). Behaves identically to `linux_config_file` but is only active on macOS. Tilde expansion (`~`) is supported.

`log_sql` { #log_sql }
:   When set to "Yes", all executed SQL statements are written to the log file with a `sql` record type, including the database name, line number, and query text. The property value should be either "Yes" or "No". The default is "No". This can also be enabled via the `CONFIG LOG_SQL` metacommand.

`max_log_size_mb` { #max_log_size_mb }
:   Maximum size of the log file in megabytes before it is rotated. When set to a positive integer, the log file is rotated to `.1` before a new run appends to it if the file size exceeds the configured threshold. The default is `0` (disabled — no rotation).

`allow_system_cmd` { #allow_system_cmd }
:   When set to "No", the `SYSTEM_CMD` (SHELL) metacommand is disabled. Any script that attempts to execute an OS command will fail with an error. The default is "Yes". This can also be set via the `--no-system-cmd` CLI flag or `allow_system_cmd=False` in the library API. See [Security — Disabling SYSTEM_CMD](security.md#disable_system_cmd) for details.

`log_datavars` { #conf_log_datavars }
:   A value of 'Yes' or 'No' to control whether data variables that are created by the [SELECT_SUB](metacommands.md#select_sub), [PROMPT SELECT_SUB](metacommands.md#prompt_selsub) and [PROMPT ACTION](metacommands.md#prompt_action) metacommands are written to *execsql*'s [log file](../guides/logging.md#logging). By default, this is set to 'Yes', so that all data variable assignments are logged. The performance of scripts that make extensive use of these metacommands (e.g., [Example 27](../guides/examples.md#example27)) can be improved by setting this to 'No'.

`win_config_file`
:   The full name or path to an additional configuration file to be read if *execsql* is running on Windows. If only a path is specified, the name of the configuration file should be `execsql.conf`. The configuration file specified will be read immediately following the configuration file in which it is named. No configuration file will be read more than once. If the name or path are invalid, this setting will be silently ignored. This setting may include [substitution variables](substitution_vars.md#substitution_vars); at the time that configuration files are read, however, only environment variables and system variables related to the script name and path are defined.

`user_logfile`
:   Uses an *execsql.log* file in the user's home directory instead of in the directory from which the script was run. This setting may need to be used if multiple users will be running scripts from the same directory.

## Section `variables`

There are no fixed properties for this section. All property names and their values that are specified in this section will be used to define substitution variables, just as if a series of SUB metacommands had been used at the beginning of the script. All variables defined in this section will be global.

## Section `include_required`

This section lists additional script files that should be automatically included before the main script is run, without the use of any explicit [INCLUDE](metacommands.md#include) metacommand in the main script.

Each property in this section should be an integer, and the property value should be a filename. The integers specify the order in which the files should be included. If any integer is listed more than once, only the last filename associated with that integer in this configuration section will be included. If any of the specified files does not exist, an error will occur and *execsql* will stop. Each file may be included only once.

Files specified in this section will be included before any files specified in the `include_optional` section. This priority ordering applies to lists of required and optional files specified in all configuration files that are read.

The order in which these files are imported is also affected by the order in which multiple configuration files (if they exist) are read.

## Section `include_optional`

This section lists additional script files that will, if they exist, be automatically included before the main script is run, without the use of any explicit [INCLUDE](metacommands.md#include) metacommand in the main script.

Each property in this section should be an integer, and the property value should be a filename. The integers specify the order in which the files should be included. If any integer is listed more than once, only the last filename associated with that integer in this configuration section will be included. If any of the specified files does not exist, it will be ignored. Each file may be included only once.

Files specified in this section will be included after any files specified in the `include_required` section. This priority ordering applies to lists of required and optional files specified in all configuration files that are read.

The order in which these files are imported is also affected by the order in which multiple configuration files (if they exist) are read.
