
# Documenting Script Actions

One of the primary goals of execsql is to facilitate, and even encourage, comprehensive documentation of all actions taken upon a database. Two fundamental aspects of execsql that support this goal are:

> - The use of [script files](using_scripts.md#scripting), which require that SQL statements be saved in a file rather than executed interactively, and which also allow copious comments to be included; and
> - Automatic logging of information about the database(s) used, the script file(s) run, and user choices in response to interactive prompts.

Other features of execsql that also support this goal are:

> - The [LOG](metacommands.md#log) metacommand, which writes a user-provided message to the standard log file;
> - The [WRITE](metacommands.md#write) metacommand, which makes it easy to issue progress and status messages to the terminal or to a file.
> - The [LOG_WRITE_MESSAGES](metacommands.md#logwritemessages) metacommand, which automatically echoes all output of the [WRITE](metacommands.md#write) metacommand to the standard log file;
> - The TEE clause of the [WRITE](metacommands.md#write) metacommand, which makes it easy to write progress and status messages to a custom documentation file in addition to the console;
> - The \$RUN_ID [system variable](substitution_vars.md#system_vars), which can be written into a custom documentation file to establish a correspondence between the information in that file and the information in the standard log file;
> - Other [system variables](substitution_vars.md#system_vars) such as \$CURRENT_DATABASE, \$DB_NAME, \$CURRENT_DIR, \$CURRENT_SCRIPT, \$CURRENT_TIME, \$LAST_ROWCOUNT, \$LAST_SQL, and \$USER, which provide useful contextual and status information that can be written into a custom documentation file;
> - The TXT output format of the [EXPORT](metacommands.md#export) metacommand, which displays (or writes to a file) a table or query in the format of a Markdown pipe table, which is an inherently readable format if included in a custom documentation file;
> - The [CONSOLE SAVE](metacommands.md#console) metacommand, which allows the entire contents of a GUI console window to be written to a custom documentation file; and
> - The \$DATE_TAG, \$DATETIME_TAG, and \$RUN_ID [system variables
>](substitution_vars.md#system_vars), which can be used to construct file names for custom documentation files.

Using these features when writing script files allows easy generation of documentation that can be valuable for establishing exactly what, and how, changes were made to a database.

An example of such a use is the creation of a custom log file to document the actions of a script. A custom log file might be initialized as follows:

```txt
-- ***********************************************************************
--          Create a custom log file
-- Input substitution variables:
--     CUSTOM_LOG     : The name of the log file to be created.  Required.
--     SCRIPT_PURPOSE : A narrative description of the script's purpose.
--                      Optional.
-- ***********************************************************************
-- !x! rm_file !!CUSTOM_LOG!!
-- !x! write "====================================================" to !!CUSTOM_LOG!!
-- !x! if(sub_defined(SCRIPT_PURPOSE))
    -- !x! write "!!SCRIPT_PURPOSE!!" to !!CUSTOM_LOG!!
    -- !x! write "----------------------------------------------------" to !!CUSTOM_LOG!!
    -- !x! write " " to !!CUSTOM_LOG!!
-- !x! endif
-- !x! write "Working dir: !!$CURRENT_DIR!!" to !!CUSTOM_LOG!!
-- !x! write "Script:      !!$CURRENT_SCRIPT!!" to !!CUSTOM_LOG!!
-- !x! write "Database:    !!$CURRENT_DATABASE!!" to !!CUSTOM_LOG!!
-- !x! write "User:        !!$DB_USER!!" to !!CUSTOM_LOG!!
-- !x! write "Run at:      !!$CURRENT_TIME!!" to !!CUSTOM_LOG!!
-- !x! write "Run ID:      !!$RUN_ID!!" to !!CUSTOM_LOG!!
-- !x! write " " to !!CUSTOM_LOG!!
```

Subsequently, throughout the script, WRITE metacommands can be used to append information to the custom log file.

As an alternative to writing documentation to a text file, documentation could be saved to a database that serves as an activity log. [Example 20](examples.md#example20) illustrates how this can be done for data issues, and a similar technique can be used to record ordinary progress and status information.
