Templates for execsql.py
===================================================

Several types of templates are provided that may be useful in conjunction with execsql.py.  These are:

*execsql.conf*
    An annotated version of the configuration file that includes all configuration settings
    and notes on their usage.

*script_template.sql*
    A framework for SQL scripts that make use of several execsql features.  It includes sections
    for custom configuration settings, custom logfile creation, and reporting of unexpected
    script exits (through user cancellation or errors).

*config_settings.sqlite* and *example_config_prompt.sql*
    A SQLite database containing specifications for all settings configurable with the CONFIG
    metacommand, in the form used by the PROMPT ENTRY_FORM metacommand, and a SQL script
    illustrating how this database can be used to prompt the user for some or all of the
    configuration settings.  *execsql* version 1.63.0 or later is needed to use this script.


Functional Scripts for execsql.py
=================================================

These script files provide useful functionality that should be accessed by including these
scripts in other SQL scripts and then calling the sub-scripts that they contain.

Upsert Scripts
------------------------------------------------

These scripts perform automated upsert operations on any tables of
any database in a DBMS that supports the standard
*information_schema* views.  Currently that includes:

* PostgreSQL: pg_upsert.sql;

* MySQL/MariaDB: md_upsert.sql; and

* SQL Server: ss_upsert.sql.

These scripts perform the upsert operation by using standard SQL
UPDATE and INSERT statements rather than DBMS-specific implementations
of the SQL MERGE statement.

Features of these upsert scripts include:

* They can be applied to any table in any database without modification.

* They can be applied to multiple tables simultaneously, and will
  perform the upsert operations in top-down order to maintain
  referential integrity among tables.

* Prior to performing the upsert operation, they check for null
  values in the columns of each staging table that must be non-null in the
  corresponding base table.

* Prior to performing the upsert operation, they check for duplicate
  primary key values in the staging tables.

* Prior to performing the upsert operation, they check foreign keys
  against both base tables and any other appropriate staging tables.

* They will not attempt to perform the upsert operation on any
  table if there are any violations of the non-null
  checks, primary key checks, or foreign key checks.

* They produce a table that either a) summarizes the number of
  rows that violated each type of non-null and foreign-key check,
  or b) summarizes the number of rows updated and the number of
  rows inserted for each table.

* Optionally, they will display all the changes to be made in a
  GUI interface, prompting the user to approve each update and
  insert operation.

* Optionally, they will record all operations carried out in a
  custom log file; this log may include the SQL statements executed
  and the data values that were added or changed.

* If an execsql console is active, they will use the console's
  status bar and progress bar to indicate the activity underway.


Complete documentation is available at
`Read The Docs (execsql-upsert) <https://execsql-upsert.readthedocs.io/en/latest/>`_.


Table Comparison Scripts
----------------------------------------------------------

These scripts generate SQL that can be used to identify differences
in the content of two tables with equivalent structure.  These are
specifically intended to be base and staging tables.  Running the
SQL provided by these scripts will provide different summaries of
the types of changes that would be made to the base tables by
upserting the staging tables.

These scripts work with
any tables of any database in a DBMS that supports the standard
*information_schema* views.  Currently that includes:

* PostgreSQL: pg_compare.sql;

* MySQL/MariaDB: md_compare.sql; and

* SQL Server: ss_compare.sql.

Complete documentation is available at
`Read The Docs (execsql-compare) <https://execsql-compare.readthedocs.io/en/latest/>`_.


Glossary Creation Scripts
------------------------------------------------------------

These scripts create a glossary of column names or other terms
that can be exported to accompany a data summary.  These scripts work with
any tables of any database in a DBMS that supports the standard
*information_schema* views.  Currently that includes:

* PostgreSQL: pg_glossary.sql;

* MySQL/MariaDB: md_glossary.sql; and

* SQL Server: ss_glossary.sql.

Complete documentation is available at
`Read The Docs (execsql-glossary) <https://execsql-compare.readthedocs.io/en/latest/>`_.
