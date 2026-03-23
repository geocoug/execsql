# Syntax and Options

execsql.py should be run at the operating-system command line -- i.e., at a shell prompt in Linux or in a command window in Windows. Python may or may not need to be explicitly invoked, and the .py extension may or may not need to be included, depending on your operating system, operating system settings, and how execsql is [installed](installation.md#installation).

execsql.py runs under both Python 2.7 and Python 3.x.

For Linux users: The execsql.py file contains a shebang line pointing to /usr/bin/python, so there should be no need to invoke the Python interpreter. Depending on how execsql.py was obtained and installed, it may need to be made executable with the *chmod* command.

For Windows users: If you are unfamiliar with running Python programs at the command prompt, see <https://docs.python.org/2/faq/windows.html>.

The syntax for command-line options and arguments is described below. In these syntax descriptions, angle brackets identify required replaceable elements, and square brackets identify optional replaceable elements.

```
Commands:
   execsql.py -tp [other options] <sql_script_file> <Postgres_host> <Postgres_db>
   execsql.py -tl [other options] <sql_script_file> <SQLite_db>
   execsql.py -tf [other options] <sql_script_file> <Firebird_host> <Firebird_db>
   execsql.py -ta [other options] <sql_script_file> <Access_db>
   execsql.py -tm [other options] <sql_script_file> <MySQL_host> <MySQL_db>
   execsql.py -ts [other options] <sql_script_file> <SQL_Server_host> <SQL_Server_db>
   execsql.py -to [other options] <sql_script_file> <Oracle_host> <Oracle_service_name>
   execsql.py -td [other options] <sql_script_file> <DSN_name>
Arguments:
   <sql_script_file>
      The name of a text file of SQL commands to be executed.
      Required argument.
   <Postgres_host>
      The name of the Postgres host (server) against which to
      run the SQL.
   <Postgres_db>
      The name of the Postgres database against which to run
      the SQL.
   <SQLite_db>
      The name of the SQLite database against which to run the
      SQL.
   <Firebird_host>
      The name of the Firebird host (server) against which to
      run the SQL.
   <Firebird_db>
      The name of the Firebird database against which to run
      the SQL.
   <MySQL_host>
      The name of the MySQL or MariaDB host (server) against
      which to run the SQL.
   <MySQL_db>
      The name of the MySQL or MariaDB database against which
      to run the SQL.
   <Oracle_host>
      The name of the Oracle host (server) against which to run
      the SQL.
   <Oracle_service_name>
      The Oracle service name (database) against which to run
      the SQL.
   <SQL_Server_host>
      The name of the SQL Server host (server) against which to
      run the SQL.
   <SQL_Server_db>
      The name of the SQL Server database against which to run
      the SQL.
   <Access_db>
      The name of the Access database against which to run the
      SQL.
   <DSN_name>
      The name of a DSN data source against which to run the SQL.
Options:
   -a <value>  Define the replacement for a substitution variable
               $ARG_x.
   -b <value>  Control whether input data columns containing only
               0 and 1 are treated as Boolean or integer:
               'y'-Yes (default); 'n'-No.
   -d <value>  Make directories used by the EXPORT metacommand:
               'n'-No (default); 'y'-Yes.
   -e <value>  Character encoding of the database.  Only used for
               some database types.
   -f <value>  Character encoding of the script file.
   -g <value>  Character encoding to use for output of the WRITE
               and EXPORT metacommands.
   -i <value>  Character encoding to use for data files imported
               with the IMPORT metacommand.
   -l          Use an execsql.log file in the user's home
               directory.
   -m          Display the allowable metacommands, and exit.
   -n          Create a new SQLite or Postgres database if the
               specified database does not exist.
   -o          Open the online help in the default browser.
   -p <value>  The port number to use for client-server databases.
   -s <value>  The number of lines of an IMPORTed file to scan to
               diagnose the quote and delimiter characters.
   -t <value>  Type of database: 'p'-Postgres, 'l'-SQLite,
               'k'-DuckDB, 'f'-Firebird, 'm'-MySQL, 's'-SQL Server,
               'a'-Access, 'd'-DSN.
   -u <value>  The database user name.
   -v <value>  Use a GUI for interactive prompts.
   -w          Do not prompt for the password when the user is
               specified.
   -y          List all valid character encodings and exit.
   -z <value>  Buffer size, in kb, to use with the IMPORT metacommand
               (the default is 32).
```

Most command-line options and arguments can be specified in [configuration files](configuration.md#configuration) instead of on the command line. If the database type and connection information is specified in a configuration file, then the database type option and the server and database name can be omitted from the command line. The absolute minimum information that must be specified on the command line is the name of the script file to run.

If a server-based database is used (i.e., Postgres, Firebird, MySQL/MariaDB, or SQL Server), then if only one command-line argument is provided in addition to the script file name, that argument will be interpreted as the database name if the server name has been set in a configuration file and the database name has not; otherwise that single argument will be interpreted as the server name.

Following are additional details on some of the command-line options:

`-a`

:   This option should be followed by text that is to be assigned to a [substitution variable](substitution_vars.md#substitution_vars). Substitution variables can be defined on the command line to provide data or control parameters to a script. The "-a" option can be used repeatedly to define multiple substitution variables. The value provided with each instance of the "-a" option should be a replacement string. execsql will automatically assign the substitution variable names. The substitution variable names will be "$ARG_1", "$ARG_2", etc., for as many variables are defined on the command line. Use of the "-a" option is illustrated in [Example 9](examples.md#example9). Command-line substitution variable assignments are [logged](logging.md#logging).

`-e, -f, -g, -i`

:   These options should each be followed by the name of a [character encoding](encoding.md#encoding). Valid names for character encodings can be displayed using the "-y" option.

`-p`

:   A port number should be provided if the DBMS is using a port different from the default. The default port numbers are:

    > - Postgres: 5432
    > - SQL Server: 1433
    > - MySQL: 3306
    > - Firebird: 3050

`-u`

:   The name of the database user should be provided with this option for password-protected databases; execsql will prompt for a password if a user name is provided, unless the "-w" option is also specified.

`-v`

:   This option should be followed by an integer indicating the level of GUI interaction that execsql should use. The values allowed are:

    > - 0: Use the terminal for all prompts (the default).
    > - 1: Use a GUI dialog for password prompts and the [PAUSE](metacommands.md#pause) metacommand.
    > - 2: Additionally, use a GUI dialog for any message to be displayed with the [HALT](metacommands.md#halt) metacommand, and use a GUI dialog to prompt for the initial database to use if no other specifications are provided.
    > - 3: Additionally, open a GUI [console](metacommands.md#console) when execsql starts.

    The prompt for a database password, and the prompt produced by the [PAUSE](metacommands.md#pause) [metacommand](metacommands.md#metacommands), are both displayed on the terminal by default. When the "-v1" option is used, or the GUI [console](metacommands.md#console) is open, both of these prompts will appear in GUI dialogs instead. If the "-v2" option is specified, then the [HALT](metacommands.md#halt) metacommand, if used with a message, will also be displayed in a GUI dialog. In addition, if the "-v2" or "-v3" option is used, and no server name or database name are specified either in a configuration file or on the command line, then execsql will use a GUI dialog to prompt for this information when it starts up.

`-w`

:   Ordinarily if a user name is specified (with the "-u" option), execsql will prompt for a password for that user. When this option is used, execsql will not prompt for entry of a password.
