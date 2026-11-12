# Schema discovery

Inspect database structure without running a script or fetching application rows:

```sh
execsql inspect database --dsn sqlite:///project.sqlite --schema main --table samples
execsql inspect database --dsn postgresql://localhost/project --schema public
```

Output is always JSON. A successful lookup exits with status **0**, including when
no objects match. Connection, catalog-query and cleanup failures exit with status
**1** and include an `error` object. Invalid command arguments exit with status
**2**. Only stdout contains the JSON result; do not combine stderr with it when
parsing output.

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
driver connection. `inspect_schema()` returns a JSON-compatible dictionary with
exactly the same structure as the CLI. Invalid Python arguments raise `ValueError`;
operational failures return `success: false`. Keyboard interrupts and process exits
propagate after owned-connection cleanup.

A connection opened from a URL belongs to this call and is closed afterward.
Existing database files are required; inspection never requests database creation.
A supplied adapter stays open. Inspection issues no commits or rollbacks and does
not change its autocommit setting. Catalog reads may start a driver transaction;
a failed query can leave that transaction aborted, as it would for a direct driver
query. The caller retains responsibility for its borrowed connection's transaction.
Concurrent operations on the same connection are not supported.

Inspection does not run startup scripts or load execsql configuration files.
URL connections never prompt for credentials or consult execsql's keyring. Supply
credentials in the URL or use driver-supported authentication. Keep credential-bearing
URLs out of shell history and process arguments when possible; a Python connection
lets applications use their own credential delivery. Returned errors use fixed,
secret-free messages rather than echoing URLs or driver exception text. Diagnose a
connection problem using the driver separately when more detail is required.

## Filters and scope

`--schema` / `schema=` and `--table` / `table=` each accept one exact,
case-sensitive catalog name. Names are separate components: a dot in a table name
is literal, not a schema separator. Do not add SQL quoting around the name;
ordinary shell quoting is still needed for spaces. Percent signs and underscores
are literal characters, not wildcard patterns. Missing objects return an empty
`tables` array. Empty names and NUL characters are rejected.

Without a schema filter, scope follows the adapter:

| Adapter            | Default scope                                                                                                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PostgreSQL, DuckDB | User schemas in the current database; `pg_catalog`, `information_schema` and `sys` excluded. Attached DuckDB catalogs are excluded.                     |
| MySQL / MariaDB    | The connection's current database. An explicit schema selects another accessible database.                                                              |
| SQL Server         | Accessible schemas in the current database, excluding the system schemas above.                                                                         |
| SQLite             | All attached namespaces, including `main` and `temp` when present; internal `sqlite_` objects excluded.                                                 |
| Oracle             | The session's current schema. An explicit schema selects another accessible owner.                                                                      |
| Firebird           | User tables and views; schema is `null`. A schema filter returns no matches.                                                                            |
| Access / ODBC DSN  | Objects visible through the driver's ODBC catalog APIs. Each table includes its reported catalog, to distinguish identical names in different catalogs. |

Only matching tables/views are included in the detailed results. ODBC drivers
without search-pattern escaping may enumerate additional catalog candidates to
match literal wildcard characters exactly.
Referenced-column names may require reading a referenced table's key metadata;
that does not add the referenced table to the result. No application row values,
row counts, credentials or complete DDL are included. Database permissions still
determine which objects and metadata are visible. Metadata visibility is not proof
that a subsequent SQL operation is permitted.

## JSON contract

The envelope has `schema_version: 1`. Consumers must check this field and
`success` before using `tables`. New optional fields can be added within version
**1**; consumers should ignore unknown fields. Removing/renaming fields or changing
their meaning or type requires a new contract version, independent of the package
version. This initial interface produces only contract version **1**.

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
