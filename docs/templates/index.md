# Templates { #templates }

The `templates/` folder of the [execsql2 repository](https://github.com/geocoug/execsql/tree/main/templates) holds ready-to-use execsql scripts. Most are libraries of named scripts (see [BEGIN SCRIPT](../reference/metacommands.md#beginscript)) that you read into your own script with [INCLUDE](../reference/metacommands.md#include) and then run with [EXECUTE SCRIPT](../reference/metacommands.md#executescript). They are driven by the database's `information_schema` views, so each one works on any table without modification.

The templates are **not installed with the package**. Download or clone the repository, then either copy the file you need next to your own scripts or INCLUDE it straight from a checkout.

## Using a template { #using }

1. Copy the template file you need (for example `md_compare.sql`) to a convenient location, or note its path in a checkout.
1. In your driver script, INCLUDE the file. This only defines the scripts; it does not run anything.
1. Call the scripts you need with EXECUTE SCRIPT, passing the arguments each one declares.

```sql
-- !x! include templates/ss_compare.sql

-- !x! execute script compare_changes with (base_schema=dbo, staging=staging, table=books, sql_var=chg_sql)
```

Every script's notes sit right after its `BEGIN SCRIPT` line, so you can read its parameters without opening the file. Once a template is included, `SHOW SCRIPTS` lists the scripts it defines, and `SHOW SCRIPTS <name>` shows one script's parameters, defaults and notes. The [language server](../guides/editors.md) shows the same text when you hover over a script name.

```sql
-- !x! include templates/md_upsert.sql
-- !x! show scripts load_staging
```

See [SHOW SCRIPTS](../reference/metacommands.md#show_scripts).

## Functional scripts { #functional }

Each family has one file per DBMS. The prefix says which: `pg_` for PostgreSQL, `md_` for MySQL and MariaDB, `ss_` for SQL Server.

| Family                  | PostgreSQL              | MySQL / MariaDB   | SQL Server        | What it does                                                                   |
| ----------------------- | ----------------------- | ----------------- | ----------------- | ------------------------------------------------------------------------------ |
| [Upsert](upsert.md)     | `PG_UPSERT` metacommand | `md_upsert.sql`   | `ss_upsert.sql`   | QA-check staging tables, then update and insert the matching base tables.      |
| [Compare](compare.md)   | `pg_compare.sql`        | `md_compare.sql`  | `ss_compare.sql`  | Generate SQL that compares a staging table with its base table.                |
| [Glossary](glossary.md) | `pg_glossary.sql`       | `md_glossary.sql` | `ss_glossary.sql` | Build a glossary of column names and definitions from a master glossary table. |

!!! note

    There is no PostgreSQL upsert template. `pg_upsert.sql` was retired in favour of the [`PG_UPSERT`](../reference/metacommands.md#pg_upsert) metacommand, which does the same job with the pg-upsert package.

The MySQL/MariaDB scripts (`md_`) take a staging-table **prefix** (`stage_pfx`) because those DBMSs have no schemas inside a database. The PostgreSQL and SQL Server scripts take a `base_schema` and a `staging` schema instead. Each family page shows both call forms.

## Other templates { #other }

`script_template.sql`
:   A framework for new scripts: a configuration section (`CONFIG` settings), custom log file creation, and reporting of unexpected exits through user cancellation or errors. Copy it and fill in the blanks.

`config_settings.sqlite`, `example_config_prompt.sql`, `make_config_db.sql`
:   A SQLite database that holds a specification of every setting configurable with the [CONFIG](../reference/metacommands.md#config) metacommand, in the form the `PROMPT ENTRY_FORM` metacommand uses, plus an example script that prompts the user for some or all of the settings. `make_config_db.sql` rebuilds the database. To use the prompt in your own script, include the `prompt_config` script defined in `example_config_prompt.sql` and either connect to the database with the alias `config_db` or set the `sub_config` variable to its path.

For an annotated list of every configuration option, run `execsql config --init > execsql.conf` instead; see [Configuration](../reference/configuration.md).

## Tests { #tests }

The glossary, compare and upsert scripts are tested in CI against live PostgreSQL, MySQL 8, MariaDB 11 and SQL Server 2022 servers, and every template file is linted and checked to INCLUDE cleanly. The tests are in `tests/templates/` of the repository; run them with `just test-templates`, which starts throwaway database containers.

Other versions of those DBMSs may work but are not tested.

## Authors and license { #authors }

The scripts were written by R. Dreas Nielsen, with Elizabeth Shea for parts of the upsert scripts. Caleb Grant revised them for execsql2. They are licensed under the GNU General Public License, version 3 or later; the header of each file names its authors and gives the full notice. Each script's history is in its file header.
