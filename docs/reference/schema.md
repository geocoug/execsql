# Schema discovery

Inspect database structure without running a script or fetching application rows:

```sh
execsql inspect database --dsn sqlite:///project.sqlite
execsql inspect schema public --dsn postgresql://localhost/project
execsql inspect table samples --schema main --dsn sqlite:///project.sqlite
```

`--dsn` and `--connection-string` accept the same connection URL.

The CLI prints readable text by default. `inspect database` shows
database identity, engine and a schema/namespace overview with visible table/view
counts. Empty namespaces appear too. Schema-less databases show their objects
directly. `inspect schema NAME` lists matching tables/views, column counts and key
summaries; table inspection shows ordered columns and relationships.
Missing metadata is labeled unavailable or unknown.

Each command owns one level of inspection. `inspect database` has no schema/table
filters. Use `inspect schema NAME` for that schema's objects, or
`inspect table NAME [--schema SCHEMA]` for column/key details. All three share
connection/password options, exit codes and the JSON contract.
Table inspection accepts views too. Without `--schema`, it returns every exact
table/view match within the adapter's default scope, rather than choosing one
schema; supply `--schema` to disambiguate.

For the versioned JSON contract described below, add `--output-format json`:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --output-format json
execsql inspect table samples --dsn sqlite:///project.sqlite --output-format json
```

A successful lookup exits with status **0**, including when no objects match.
Connection, catalog-query and cleanup failures exit with status **1**. Text mode
reports errors and diagnostic hints on stderr; JSON mode returns an `error` object
on stdout. Invalid command arguments exit with status **2**. Do not combine stderr
with stdout when parsing JSON.

## Python

```python
from execsql import inspect_schema

metadata = inspect_schema(
    dsn="sqlite:///project.sqlite",
    schema="main",
    table="samples",
)
if not metadata["success"]:
    raise RuntimeError(metadata["error"]["code"])
for table in metadata["tables"]:
    print(table["name"], table["columns"])
```

Supply exactly one of `dsn=` or `connection=`. The latter accepts an existing
execsql `Database` adapter, including Access and ODBC DSN adapters. It is not a raw
driver connection. `inspect_schema()` returns a JSON-compatible dictionary using
the CLI's shared output contract. Invalid Python arguments raise `ValueError`;
operational failures return `success: false`. Keyboard interrupts and process exits
propagate after owned-connection cleanup.

To request the same database overview metadata as the database CLI:

```python
metadata = inspect_schema(dsn="sqlite:///project.sqlite", include_database=True)
print(metadata["database"])
print(metadata["schemas"])
```

`include_database=True` requires unfiltered inspection: combining it with
`schema=` or `table=` raises `ValueError`. Its default is `False`, preserving
existing Python results and catalog queries. The CLI enables it only for
`inspect database`.

A connection opened from a URL belongs to this call and is closed afterward.
Existing database files are required; inspection never requests database creation.
A supplied adapter stays open. Inspection issues no commits or rollbacks and does
not change its autocommit setting. Catalog reads may start a driver transaction;
a failed query can leave that transaction aborted, as it would for a direct driver
query. The caller retains responsibility for its borrowed connection's transaction.
Concurrent operations on the same connection are not supported.

Inspection does not run startup scripts or load execsql configuration files.
The Python API does not prompt by default and never consults execsql's keyring.
`prompt_password=True` explicitly enables hidden password prompting for a URL
that includes a user; an interactive stdin is required. The CLI automatically
allows that prompt for text output on a terminal. `--no-passwd` disables it;
`--prompt-password` explicitly allows it with JSON output. JSON and redirected
stdin never prompt automatically. Otherwise, supply credentials in the URL or use
driver-supported authentication. Keep credential-bearing
URLs out of shell history and process arguments when possible; a Python connection
lets applications use their own credential delivery. Returned errors use fixed,
secret-free messages rather than echoing URLs or driver exception text. Diagnose a
connection problem using the driver separately when more detail is required.

## Filters and scope

Schema/table positional names, table inspection's `--schema`, and Python
`schema=` / `table=` each accept one exact,
case-sensitive catalog name. Names are separate components: a dot in a table name
is literal, not a schema separator. Do not add SQL quoting around the name;
ordinary shell quoting is still needed for spaces. Percent signs and underscores
are literal characters, not wildcard patterns. Missing objects return an empty
`tables` array. Empty names and NUL characters are rejected.

Without a schema filter, scope follows the adapter:

| Adapter           | Default scope                                                                                                                                           |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PostgreSQL        | User schemas in the current database; reserved `pg_*` schemas, `information_schema` and `sys` excluded.                                                 |
| DuckDB            | User schemas in the current database; `pg_catalog`, `information_schema` and `sys` excluded. Attached DuckDB catalogs are excluded.                     |
| MySQL / MariaDB   | The connection's current database. An explicit schema selects another accessible database.                                                              |
| SQL Server        | Accessible schemas in the current database, excluding the system schemas above.                                                                         |
| SQLite            | All attached namespaces, including `main` and `temp` when present; internal `sqlite_` objects excluded.                                                 |
| Oracle            | The session's current schema. An explicit schema selects another accessible owner.                                                                      |
| Firebird          | User tables and views; schema is `null`. A schema filter returns no matches.                                                                            |
| Access / ODBC DSN | Objects visible through the driver's ODBC catalog APIs. Each table includes its reported catalog, to distinguish identical names in different catalogs. |

Only matching tables/views are included in the detailed results. ODBC drivers
without search-pattern escaping may enumerate additional catalog candidates to
match literal wildcard characters exactly.
Referenced-column names may require reading a referenced table's key metadata;
that does not add the referenced table to the result. No application row values,
row counts, credentials or complete DDL are included. Database permissions still
determine which objects and metadata are visible. Metadata visibility is not proof
that a subsequent SQL operation is permitted.

PostgreSQL reserves schema names beginning with the literal `pg_` prefix for
system use. Default discovery excludes that prefix in both namespace and table
catalog queries, including `pg_temp_*`, `pg_toast_temp_*` and `pg_toast`.
An explicit schema name bypasses the default exclusion, for example
`execsql inspect schema pg_catalog --dsn URL` or Python `schema="pg_catalog"`.
The prefix rule applies only to PostgreSQL. See [PostgreSQL schemas](https://www.postgresql.org/docs/current/ddl-schemas.html).

### Database overview scope

Namespace enumeration reads catalogs independently of the table list, so a
namespace with no visible tables or views still appears. Counts are **visible
object counts**, not application-row counts; zero means no matching objects are
visible to this connection. The existing table visibility and default scope above
are unchanged.

| Adapter            | Database identity and namespace inventory                                                                                                                                                                                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| PostgreSQL, DuckDB | Current database and visible non-system schemas from `information_schema.schemata`, restricted to the current catalog.                                                                                                                                                                                                   |
| SQL Server         | `DB_NAME()` and visible schemas from `information_schema.schemata`, excluding system schemas.                                                                                                                                                                                                                            |
| SQLite             | Main database filename (or `:memory:`) and attached namespaces from `PRAGMA database_list`, including empty attachments and `temp` when present.                                                                                                                                                                         |
| Oracle             | Database name and current schema from `SYS_CONTEXT`; the scope remains the current owner, including when it has no visible objects.                                                                                                                                                                                      |
| MySQL / MariaDB    | Current database from `database()`. Schema and database are the same scope, so the overview shows objects directly.                                                                                                                                                                                                      |
| Firebird           | Database identity from `RDB$GET_CONTEXT`; no schema namespace, so objects are shown directly.                                                                                                                                                                                                                            |
| Access             | Driver-reported database identity and a flat object overview.                                                                                                                                                                                                                                                            |
| ODBC DSN           | Driver-reported identity/engine and schema support via `SQLGetInfo`; schema names via `SQLTables` enumeration where supported. Names are aggregated across the catalogs visible to the existing table reader, since schema enumeration supplies no catalog association. Detailed table identities retain their catalogs. |

ODBC's explicit unsupported-information/catalog responses produce unavailable
metadata; genuine driver/query errors fail inspection. If namespace enumeration
is unavailable, text says so and shows visible objects. Identity never comes from
a raw DSN/connection string. These extra catalog reads retain the same connection
ownership and transaction rules as table inspection.
See the driver's [SQLTables schema-enumeration contract](https://learn.microsoft.com/en-us/sql/odbc/reference/syntax/sqltables-function)
for the catalog-association limitation.

## JSON contract

The envelope has `schema_version: 1`. Consumers must check this field and
`success` before using `tables`. New optional fields can be added within version
**1**; consumers should ignore unknown fields. Removing/renaming fields or changing
their meaning or type requires a new contract version, independent of the package
version. This initial interface produces only contract version **1**.

Database overviews add optional fields without changing the existing `tables`
array or contract version:

- `database`: `name`, `engine` (strings or `null` when unavailable), and
    `namespace_kind` (`schema`, `attached_database`, `none` or `unknown`).
- `schemas`: a sorted array of `{name, table_count, view_count}` entries. `name`
    may be `null` for visible objects without a schema. An empty array with
    `namespace_kind: "none"` means a flat database; `null` means enumeration is
    unavailable. Counts aggregate visible tables/views by namespace name.
- `capabilities.schemas`: whether namespace availability is known, including a
    known schema-less database. Check `namespace_kind` to distinguish that case.

The fields are omitted when the overview is not requested. Failed overview
requests return `database: null` and `schemas: null`; always check `success`
before using metadata.

For a `samples` table referencing `locations.id`, an abbreviated result is:

```json
{
  "schema_version": 1,
  "success": true,
  "adapter": "PostgreSQL",
  "dialect": "PostgreSQL",
  "capabilities": {
    "tables": true,
    "columns": true,
    "primary_key": true,
    "foreign_keys": true
  },
  "tables": [{
    "catalog": null,
    "schema": "public",
    "name": "samples",
    "kind": "table",
    "columns": [{
      "name": "location_id",
      "ordinal_position": 1,
      "data_type": "integer",
      "nullable": false
    }],
    "primary_key": [],
    "foreign_keys": [{
      "name": "samples_location_id_fkey",
      "columns": ["location_id"],
      "referenced_catalog": null,
      "referenced_schema": "public",
      "referenced_table": "locations",
      "referenced_columns": ["id"]
    }]
  }],
  "error": null
}
```

- `adapter` identifies execsql's adapter. `dialect` identifies the database family;
    it is `null` for a generic DSN whose underlying SQL dialect is not determined.
    No dialect is inferred from a DSN's name.
- `capabilities` reports availability of tables, columns, primary-key columns and
    foreign keys. `true` means implemented/available, not a permission guarantee.
    ODBC key capabilities are determined from the selected objects: `false` means
    unavailable for at least one selected object, and `null` means no object was
    selected so support was not established. Check individual tables as well.
- Tables sort by catalog, schema and name. `kind` is `table` or `view`. `catalog`
    and each relationship's `referenced_catalog` are ODBC-reported catalogs, otherwise `null`; `schema` is `null` when the
    backend has no schema namespace. Columns sort by one-based ordinal position.
- `data_type` is the backend's catalog type name, not a portable type or complete
    SQL declaration. Length, precision, scale, domains and array details are not
    reconstructed. Unknown type names or nullability are `null`. SQLite primary
    keys whose nullability cannot be established from the column catalog use
    `nullable: null` rather than guessing from the key declaration.
- `primary_key` lists column names in key order. `foreign_keys` lists outgoing
    relationships, with source and referenced columns in corresponding key order.
    Names are `null` when unavailable (SQLite). A missing referenced SQLite column
    remains `null` if the parent's key cannot be resolved. `[]` means no reported
    keys; `null` means unavailable. Incoming relationships and unique/check
    constraints are not included.

Failure leaves `tables: []` and returns an error such as:

```json
{"code": "metadata_error", "message": "Schema discovery metadata failed."}
```

Codes are `connection_error`, `metadata_error`, `close_error` and
`unsupported_adapter`. A failure before connecting has `adapter` and `dialect`
set to `null` and `capabilities: {}`. Real query failures are never converted into
successful empty results or unsupported capabilities.

## Adapter support and verification

All three CLI commands are exercised through real URL connections, in both text
and JSON modes, for SQLite, DuckDB, PostgreSQL, MySQL, MariaDB and SQL Server.
Server-backed cases run in integration CI; unavailable optional local servers
are skipped. Oracle and Firebird inspection currently has catalog-row mock tests,
not live CLI/server coverage. Access and generic ODBC inspection is available
through Python `connection=` only: the CLI URL parser has no schemes for those
adapters, and their inspection tests use mocked catalog rows.

| Adapter         | Tables, views, columns and types             | Primary / foreign keys                                 | Verification                        |
| --------------- | -------------------------------------------- | ------------------------------------------------------ | ----------------------------------- |
| SQLite          | Native catalog and `table_xinfo`             | Native PRAGMAs; composite and implicit referenced keys | Live tests                          |
| DuckDB          | Current database's information schema        | Information schema                                     | Live tests                          |
| PostgreSQL      | Information schema                           | `pg_catalog`, including for SELECT-only roles          | Live tests in integration CI        |
| MySQL / MariaDB | Current database's information schema        | Information schema                                     | Live tests in integration CI        |
| SQL Server      | Information schema                           | Information schema / `sys` catalogs                    | Live tests in integration CI        |
| Oracle          | `all_tables`, `all_views`, `all_tab_columns` | `all_constraints`, `all_cons_columns`                  | Catalog-row tests; best effort      |
| Firebird        | `RDB$` system catalogs                       | Constraint/index catalogs                              | Catalog-row tests; best effort      |
| Access          | ODBC catalog APIs                            | Available when the driver implements the catalog calls | Catalog-row tests; best effort      |
| ODBC DSN        | ODBC catalog APIs                            | Available when the driver implements the catalog calls | Catalog-row tests; driver dependent |

ODBC reports an unavailable optional key operation only for SQLSTATE `IM001` or
`HYC00`. Authentication, permission and other catalog errors fail inspection.
Unnamed ODBC foreign keys cannot always be grouped into distinct composite
constraints; their relationships are reported unavailable rather than combined
incorrectly. The adapter's regular [support tier](../getting-started/requirements.md#support-tiers)
also applies.
