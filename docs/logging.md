# Logging

*execsql* automatically logs certain actions, conditions, and errors that occur during the processing of a script file. Although a script file provides good documentation of database operations, there are circumstances in which a script file is not a definitive record of what operations were, or were not, carried out. These circumstances include:

> - Errors
> - Choices made by the user in response to a [PROMPT](metacommands.md#prompt) metacommand.
> - Cancellation of the script in response to a [PAUSE](metacommands.md#pause) metacommand or password prompt from the [CONNECT](metacommands.md#connect) metacommand.

Information is logged into a tab-delimited text file named `execsql.log`. By default, this file is located in the directory from which the script file was run. If either the "-l" command-line option or the "user_logfile" [configuration](configuration.md#configuration) option is used, this file will be located in the user's home directory.

!!! note

    Prior to version 1.28.0.5 (2018-09-10), the log file was created in the directory of the starting script.

This file contains several different record types. The first value on each line of the file identifies the record type. The second value on each line is a run identifier. All records that are logged during a single run of *execsql* have the same run identifier. The run identifier is a compact representation of the date and time at which the run started. The record types and the values that each record of that type contains are:

> **run**---Information about the run as a whole:
>
> > - Record type
> > - Run identifier
> > - Script name
> > - Script path
> > - Script file revision date
> > - Script file size in bytes
> > - User name
> > - Command-line options
>
> **run_db_file**---Information about the file-based database used (Access or SQLite):
>
> > - Record type
> > - Run identifier
> > - Database file name with full path
>
> **run_db_server**---Information about the server-based database used (Postgres, MySQL, MariaDB, Firebird, or SQL Server):
>
> > - Record type
> > - Run identifier
> > - Server name
> > - Database name
>
> **connect**---The type and name of a database to which a connection has been established; this may be either a client-server or file-based database:
>
> > - Record type
> > - Run identifier
> > - DBMS type and database identifiers
>
> **action**---Significant actions carried out by the script, primarily those that affect the results.
>
> > - Record type
> >
> > - Run identifier
> >
> > - Sequence number---The order of actions, status messages, and errors. Automatically generated.
> >
> > - Action type---One of the following values:
> >
> >     > - export---Execution of an [EXPORT](metacommands.md#export) metacommand.
> >     > - prompt_quit---The user's choice resulting from a [Prompt](PROMPT.md#PROMPT) metacommand.
> >
> > - Line number---The script line number where the action takes place.
> >
> > - Description---Free text describing the action.
>
> **status**---Status messages; frequently these are errors
>
> > - Record type
> >
> > - Run identifier
> >
> > - Sequence number---The order of actions, status messages, and errors. Automatically generated.
> >
> > - Status type---One of the following values:
> >
> >     > - exception
> >     > - error
> >
> > - Description---Free text describing the status.
>
> **exit**---Program status at exit.
>
> > - Record type
> >
> > - Run identifier
> >
> > - Exit type---One of the following values:
> >
> >     > - end_of_script---A normal exit; the entire script has been processed.
> >     > - prompt_quit---The user chose to cancel the script in response to a PROMPT metacommand.
> >     > - halt---A [HALT](metacommands.md#halt) metacommand was executed.
> >     > - error---An error occurred.
> >     > - exception---An exception occurred.
> >
> > - Line number---The script line number from which the exit was triggered (may be null).
> >
> > - Description---Free text describing the exit condition.

The messages for each run are appended to the end of the log file. The log file is set to read-only when *execsql* exits.

Although logging is performed automatically by *execsql*, there are three ways to make use of the log file in custom scripts:

> - The [LOG](metacommands.md#log) metacommand provides a way to write additional messages into the log file.
> - The [LOG_WRITE_MESSAGES](metacommands.md#logwritemessages) metacommand causes the output of all [WRITE](metacommands.md#write) metacommands to be echoed to the log file.
> - The $RUN_ID [system variable](substitution_vars.md#system_vars) provides a way to link other information (e.g., status or error messages) to the run that is identified in the log file.
