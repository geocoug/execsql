"""Read-only catalog discovery, shared by the Python API and ``inspect database``.

Catalog readers use raw cursors: they never call execute()/select_data(), whose
error paths roll back the caller's transaction. No reader commits or rolls back.
"""

from __future__ import annotations

import re
from typing import Any, cast

from execsql.db.base import Database

__all__ = ["inspect_schema"]


def _rows(db: Database, sql: str, params: list[Any] | None = None) -> list[Any]:
    """Run fixed catalog SQL with bound values and close its cursor."""
    if db.type.dbms_id == "Oracle":
        count = iter(range(1, (sql.count("?") + 1)))
        sql = re.sub(r"\?", lambda _: f":{next(count)}", sql)
    elif db.paramstr == "%s":
        sql = sql.replace("?", "%s")
    if db.type.dbms_id == "MySQL":
        sql = re.sub(r"((?:[ck]\.)?table_(?:schema|name)) = %s", r"BINARY \1 = BINARY %s", sql)
    with db._cursor() as cursor:
        cursor.execute(sql, params or [])
        return list(cursor.fetchall())


def _column(name: str, position: int, data_type: str | None, nullable: bool | None) -> dict[str, Any]:
    return {"name": name, "ordinal_position": position, "data_type": data_type, "nullable": nullable}


def _table(schema: str | None, name: str, kind: str) -> dict[str, Any]:
    return {
        "catalog": None,
        "schema": schema,
        "name": name,
        "kind": kind,
        "columns": [],
        "primary_key": [],
        "foreign_keys": [],
    }


def _foreign_keys(rows: list[Any]) -> list[dict[str, Any]]:
    """Rows: grouping id/name, ordinal, source column, target schema/table/column."""
    groups: dict[Any, dict[str, Any]] = {}
    for key, _ordinal, column, schema, table, target in sorted(rows, key=lambda r: (str(r[0]), r[1])):
        if key not in groups:
            groups[key] = {
                "name": key if isinstance(key, str) else None,
                "columns": [],
                "referenced_catalog": None,
                "referenced_schema": schema,
                "referenced_table": table,
                "referenced_columns": [],
            }
        groups[key]["columns"].append(column)
        groups[key]["referenced_columns"].append(target)
    return list(groups.values())


def _sqlite(db: Database, schema: str | None, table: str | None) -> list[dict[str, Any]]:
    tables = []
    for _, namespace, _ in _rows(db, "PRAGMA database_list"):
        if schema is not None and schema != namespace:
            continue
        quoted = db.quote_identifier(namespace)
        sql = f"SELECT name, type FROM {quoted}.sqlite_master WHERE type IN ('table', 'view')"
        params = []
        if table is not None:
            sql += " AND name = ?"
            params.append(table)
        for name, kind in _rows(db, sql, params):
            if name.startswith("sqlite_") or (table is not None and name != table):
                continue
            item = _table(namespace, name, kind)
            # PRAGMA arguments are identifiers, quoted separately from the schema.
            columns = _rows(db, f"PRAGMA {quoted}.table_xinfo({db.quote_identifier(name)})")
            item["columns"] = [
                _column(c[1], c[0] + 1, c[2], None if c[5] and not c[3] else not bool(c[3])) for c in columns
            ]
            item["primary_key"] = [c[1] for c in sorted(columns, key=lambda c: c[5]) if c[5]]
            links = _rows(db, f"PRAGMA {quoted}.foreign_key_list({db.quote_identifier(name)})")
            # An omitted target column means the parent's primary key. Resolve it
            # from metadata only, including its composite-key ordering.
            targets: dict[str, list[str]] = {}
            for link in links:
                if link[4] is None and link[2] not in targets:
                    parent = _rows(db, f"PRAGMA {quoted}.table_xinfo({db.quote_identifier(link[2])})")
                    targets[link[2]] = [c[1] for c in sorted(parent, key=lambda c: c[5]) if c[5]]
            normalized = []
            for key, ordinal, target_table, column, target_column, *_ in links:
                if target_column is None:
                    pk = targets[target_table]
                    target_column = pk[ordinal] if ordinal < len(pk) else None
                normalized.append((key, ordinal, column, namespace, target_table, target_column))
            item["foreign_keys"] = _foreign_keys(normalized)
            tables.append(item)
    return tables


# These queries select only catalog relations and bind all filter values.
# table_catalog limits DuckDB attached databases and PostgreSQL to the current DB.
_INFO_TABLES = "SELECT table_schema, table_name, table_type FROM information_schema.tables"
_INFO_COLUMNS = """SELECT column_name, ordinal_position, data_type, is_nullable
FROM information_schema.columns WHERE table_schema = ? AND table_name = ?
ORDER BY ordinal_position"""
_INFO_PK = """SELECT k.column_name FROM information_schema.table_constraints c
JOIN information_schema.key_column_usage k
ON c.constraint_catalog = k.constraint_catalog AND c.constraint_schema = k.constraint_schema
AND c.constraint_name = k.constraint_name AND c.table_name = k.table_name
WHERE c.constraint_type = 'PRIMARY KEY' AND c.table_schema = ? AND c.table_name = ?
ORDER BY k.ordinal_position"""
_INFO_FK = """SELECT k.constraint_name, k.ordinal_position, k.column_name,
p.table_schema, p.table_name, p.column_name
FROM information_schema.key_column_usage k
JOIN information_schema.referential_constraints r
ON r.constraint_catalog = k.constraint_catalog AND r.constraint_schema = k.constraint_schema
AND r.constraint_name = k.constraint_name
JOIN information_schema.key_column_usage p
ON p.constraint_catalog = r.unique_constraint_catalog AND p.constraint_schema = r.unique_constraint_schema
AND p.constraint_name = r.unique_constraint_name AND p.ordinal_position = k.position_in_unique_constraint
WHERE k.table_schema = ? AND k.table_name = ?"""
_MYSQL_PK = """SELECT column_name FROM information_schema.key_column_usage
WHERE constraint_name = 'PRIMARY' AND table_schema = ? AND table_name = ? ORDER BY ordinal_position"""
_MYSQL_FK = """SELECT constraint_name, ordinal_position, column_name,
referenced_table_schema, referenced_table_name, referenced_column_name
FROM information_schema.key_column_usage WHERE table_schema = ? AND table_name = ?
AND referenced_table_name IS NOT NULL"""
# SQL Server's key_column_usage has no position_in_unique_constraint.
_MSSQL_FK = """SELECT f.name, fc.constraint_column_id, c.name, ps.name, pt.name, pc.name
FROM sys.foreign_keys f JOIN sys.foreign_key_columns fc ON fc.constraint_object_id = f.object_id
JOIN sys.tables t ON t.object_id = f.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = fc.parent_column_id
JOIN sys.tables pt ON pt.object_id = f.referenced_object_id
JOIN sys.schemas ps ON ps.schema_id = pt.schema_id
JOIN sys.columns pc ON pc.object_id = pt.object_id AND pc.column_id = fc.referenced_column_id
WHERE s.name = ? AND t.name = ?"""


# pg_catalog exposes constraints to SELECT-only roles, unlike the privilege-
# filtered information_schema.table_constraints/referential_constraints views.
_PG_PK = """SELECT a.attname FROM pg_catalog.pg_constraint c
JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
CROSS JOIN LATERAL generate_subscripts(c.conkey, 1) AS pos(i)
JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[pos.i]
WHERE c.contype = 'p' AND n.nspname = ? AND t.relname = ? ORDER BY pos.i"""
_PG_FK = """SELECT c.conname, pos.i, a.attname, parent_namespace.nspname, pt.relname, pa.attname
FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
JOIN pg_catalog.pg_class pt ON pt.oid = c.confrelid
JOIN pg_catalog.pg_namespace parent_namespace ON parent_namespace.oid = pt.relnamespace
CROSS JOIN LATERAL generate_subscripts(c.conkey, 1) AS pos(i)
JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[pos.i]
JOIN pg_catalog.pg_attribute pa ON pa.attrelid = pt.oid AND pa.attnum = c.confkey[pos.i]
WHERE c.contype = 'f' AND n.nspname = ? AND t.relname = ?"""


def _information_schema(db: Database, schema: str | None, table: str | None) -> list[dict[str, Any]]:
    dialect = db.type.dbms_id
    clauses, params = [], []
    if dialect in ("PostgreSQL", "DuckDB"):
        clauses.append("table_catalog = current_database()")
    if schema is not None:
        clauses.append("table_schema = ?")
        params.append(schema)
    elif dialect == "MySQL":
        clauses.append("table_schema = database()")
    else:
        clauses.append("table_schema NOT IN ('information_schema', 'pg_catalog', 'sys')")
    if table is not None:
        clauses.append("table_name = ?")
        params.append(table)
    tables = []
    for namespace, name, kind in _rows(db, _INFO_TABLES + " WHERE " + " AND ".join(clauses), params):
        if not _matches(namespace, name, schema, table):
            continue
        item = _table(namespace, name, "view" if "VIEW" in kind.upper() else "table")
        values = [namespace, name]
        column_sql = _INFO_COLUMNS
        pk_sql = {"PostgreSQL": _PG_PK, "MySQL": _MYSQL_PK}.get(dialect, _INFO_PK)
        if dialect in ("PostgreSQL", "DuckDB"):
            column_sql = column_sql.replace("WHERE ", "WHERE table_catalog = current_database() AND ", 1)
        if dialect == "DuckDB":
            pk_sql = pk_sql.replace("WHERE ", "WHERE c.table_catalog = current_database() AND ", 1)
        item["columns"] = [_column(c, int(p), t, n == "YES") for c, p, t, n in _rows(db, column_sql, values)]
        item["primary_key"] = [r[0] for r in _rows(db, pk_sql, values)]
        fk_sql = {"MySQL": _MYSQL_FK, "SQL Server": _MSSQL_FK, "PostgreSQL": _PG_FK}.get(dialect, _INFO_FK)
        if dialect == "DuckDB":
            fk_sql += " AND k.table_catalog = current_database()"
        item["foreign_keys"] = _foreign_keys(_rows(db, fk_sql, values))
        tables.append(item)
    return tables


_ORACLE_TABLES = """SELECT owner, table_name, 'table' FROM all_tables
UNION ALL SELECT owner, view_name, 'view' FROM all_views"""
_ORACLE_COLUMNS = """SELECT column_name, column_id, data_type, nullable
FROM all_tab_columns WHERE owner = ? AND table_name = ? ORDER BY column_id"""
_ORACLE_PK = """SELECT k.column_name FROM all_constraints c JOIN all_cons_columns k
ON k.owner = c.owner AND k.constraint_name = c.constraint_name
WHERE c.constraint_type = 'P' AND c.owner = ? AND c.table_name = ? ORDER BY k.position"""
_ORACLE_FK = """SELECT c.constraint_name, k.position, k.column_name, p.owner, p.table_name, p.column_name
FROM all_constraints c JOIN all_cons_columns k
ON k.owner = c.owner AND k.constraint_name = c.constraint_name
JOIN all_cons_columns p ON p.owner = c.r_owner AND p.constraint_name = c.r_constraint_name
AND p.position = k.position
WHERE c.constraint_type = 'R' AND c.owner = ? AND c.table_name = ?"""


def _oracle(db: Database, schema: str | None, table: str | None) -> list[dict[str, Any]]:
    sql = "SELECT owner, table_name, kind FROM (" + _ORACLE_TABLES.replace("'table'", "'table' kind") + ")"
    clauses = ["owner = ?" if schema is not None else "owner = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"]
    params = [schema] if schema is not None else []
    if table is not None:
        clauses.append("table_name = ?")
        params.append(table)
    tables = []
    for namespace, name, kind in _rows(db, sql + " WHERE " + " AND ".join(clauses), params):
        if not _matches(namespace, name, schema, table):
            continue
        item = _table(namespace, name, kind)
        values = [namespace, name]
        item["columns"] = [_column(c, int(p), t, n == "Y") for c, p, t, n in _rows(db, _ORACLE_COLUMNS, values)]
        item["primary_key"] = [r[0] for r in _rows(db, _ORACLE_PK, values)]
        item["foreign_keys"] = _foreign_keys(_rows(db, _ORACLE_FK, values))
        tables.append(item)
    return tables


_FIREBIRD_TABLES = """SELECT RDB$RELATION_NAME, RDB$VIEW_BLR FROM RDB$RELATIONS
WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0"""
_FIREBIRD_COLUMNS = """SELECT r.RDB$FIELD_NAME, r.RDB$FIELD_POSITION, t.RDB$TYPE_NAME,
COALESCE(r.RDB$NULL_FLAG, f.RDB$NULL_FLAG, 0), f.RDB$FIELD_SUB_TYPE
FROM RDB$RELATION_FIELDS r JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = r.RDB$FIELD_SOURCE
LEFT JOIN RDB$TYPES t ON t.RDB$FIELD_NAME = 'RDB$FIELD_TYPE' AND t.RDB$TYPE = f.RDB$FIELD_TYPE
WHERE r.RDB$RELATION_NAME = ? ORDER BY r.RDB$FIELD_POSITION"""
_FIREBIRD_PK = """SELECT s.RDB$FIELD_NAME FROM RDB$RELATION_CONSTRAINTS c
JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = c.RDB$INDEX_NAME
WHERE c.RDB$CONSTRAINT_TYPE = 'PRIMARY KEY' AND c.RDB$RELATION_NAME = ? ORDER BY s.RDB$FIELD_POSITION"""
_FIREBIRD_FK = """SELECT c.RDB$CONSTRAINT_NAME, s.RDB$FIELD_POSITION, s.RDB$FIELD_NAME,
p.RDB$RELATION_NAME, ps.RDB$FIELD_NAME FROM RDB$RELATION_CONSTRAINTS c
JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = c.RDB$INDEX_NAME
JOIN RDB$REF_CONSTRAINTS r ON r.RDB$CONSTRAINT_NAME = c.RDB$CONSTRAINT_NAME
JOIN RDB$RELATION_CONSTRAINTS p ON p.RDB$CONSTRAINT_NAME = r.RDB$CONST_NAME_UQ
JOIN RDB$INDEX_SEGMENTS ps ON ps.RDB$INDEX_NAME = p.RDB$INDEX_NAME
AND ps.RDB$FIELD_POSITION = s.RDB$FIELD_POSITION
WHERE c.RDB$RELATION_NAME = ?"""


def _firebird(db: Database, schema: str | None, table: str | None) -> list[dict[str, Any]]:
    if schema is not None:  # No schema namespace exists in Firebird.
        return []
    sql = _FIREBIRD_TABLES + (" AND RDB$RELATION_NAME = ?" if table is not None else "")
    tables = []
    for raw_name, view in _rows(db, sql, [table] if table is not None else []):
        name = raw_name.rstrip()
        if table is not None and name != table:
            continue
        item = _table(None, name, "view" if view is not None else "table")
        item["columns"] = [
            _column(
                c.rstrip(),
                int(p) + 1,
                {1: "NUMERIC", 2: "DECIMAL"}.get(sub, t.strip())
                if t and t.strip() in ("SHORT", "LONG", "INT64", "INT128")
                else (t.strip() if t else None),
                not bool(n),
            )
            for c, p, t, n, sub in _rows(db, _FIREBIRD_COLUMNS, [name])
        ]
        item["primary_key"] = [r[0].rstrip() for r in _rows(db, _FIREBIRD_PK, [name])]
        links = [
            (k.rstrip(), p, c.rstrip(), None, t.rstrip(), r.rstrip())
            for k, p, c, t, r in _rows(db, _FIREBIRD_FK, [name])
        ]
        item["foreign_keys"] = _foreign_keys(links)
        tables.append(item)
    return tables


def _optional_catalog(cursor: Any, method: str, **filters: Any) -> list[Any] | None:
    """Only ODBC's explicit unsupported-operation states mean unavailable."""
    try:
        return list(getattr(cursor, method)(**filters))
    except Exception as exc:
        if exc.args and exc.args[0] in ("IM001", "HYC00"):
            return None
        raise


def _literal_pattern(name: str | None, escape: str) -> str | None:
    """Escape an exact name for an ODBC pattern argument, not an identifier."""
    if name is None:
        return None
    if not escape:
        # A driver with no escape support cannot express a literal wildcard.
        # Enumerate candidates instead and retain the exact identity below.
        return None if any(c in name for c in "%_") else name
    return "".join(escape + c if c in escape + "%_" else c for c in name)


def _odbc(db: Database, schema: str | None, table: str | None) -> list[dict[str, Any]]:
    from execsql.db.access import AccessDatabase

    if isinstance(db, AccessDatabase):
        db.dao_flush_check()
    try:
        # SQL_SEARCH_PATTERN_ESCAPE (ODBC SQLGetInfo constant, independent of
        # optional pyodbc imports so catalog-row tests need no installed driver).
        escape = db.conn.getinfo(14)
    except Exception as exc:
        if not (exc.args and exc.args[0] in ("IM001", "HYC00")):
            raise
        escape = ""
    if not isinstance(escape, str) or len(escape) > 1:
        raise ValueError("Invalid ODBC catalog search-pattern escape.")
    tables = []
    with db._cursor() as cursor:
        found = list(
            cursor.tables(
                table=_literal_pattern(table, escape),
                schema=_literal_pattern(schema, escape),
                tableType="TABLE,VIEW",
            ),
        )
        for row in found:
            namespace, name, kind = row[1], row[2], row[3]
            if not _matches(namespace, name, schema, table):
                continue
            item = _table(namespace, name, "view" if "VIEW" in kind.upper() else "table")
            item["catalog"] = row[0]
            # Pattern-based catalog methods may return extra objects. Filter the
            # returned identities exactly before accepting any of their metadata.
            cols = list(
                cursor.columns(
                    table=_literal_pattern(name, escape),
                    schema=_literal_pattern(namespace, escape),
                    catalog=row[0],
                ),
            )
            item["columns"] = [
                _column(c[3], int(c[16]), c[5], None if c[10] == 2 else bool(c[10]))
                for c in cols
                if tuple(c[:3]) == tuple(row[:3])
            ]
            pk = _optional_catalog(cursor, "primaryKeys", table=name, schema=namespace, catalog=row[0])
            item["primary_key"] = (
                None if pk is None else [c[3] for c in sorted(pk, key=lambda c: c[4]) if tuple(c[:3]) == tuple(row[:3])]
            )
            fk = _optional_catalog(
                cursor,
                "foreignKeys",
                foreignTable=name,
                foreignSchema=namespace,
                foreignCatalog=row[0],
            )
            # Unnamed ODBC foreign keys cannot be grouped unambiguously if two
            # constraints target the same table. Report the relationships as
            # unavailable rather than inventing or merging constraints.
            if fk is None or any(c[11] is None for c in fk):
                item["foreign_keys"] = None
            else:
                item["foreign_keys"] = _foreign_keys(
                    [(c[11], c[8], c[7], c[1], c[2], c[3]) for c in fk if tuple(c[4:7]) == tuple(row[:3])],
                )
            if item["foreign_keys"] is not None:
                assert fk is not None
                for link in item["foreign_keys"]:
                    link["referenced_catalog"] = next(c[0] for c in fk if c[11] == link["name"])
            tables.append(item)
    return tables


def _matches(namespace: str | None, name: str, schema: str | None, table: str | None) -> bool:
    return (schema is None or schema == namespace) and (table is None or table == name)


_READERS = {
    "SQLite": _sqlite,
    "DuckDB": _information_schema,
    "PostgreSQL": _information_schema,
    "MySQL": _information_schema,
    "SQL Server": _information_schema,
    "Oracle": _oracle,
    "Firebird": _firebird,
    "Access": _odbc,
    "DSN": _odbc,
}


def inspect_schema(
    *,
    dsn: str | None = None,
    connection: Database | None = None,
    schema: str | None = None,
    table: str | None = None,
) -> dict[str, Any]:
    """Return JSON-compatible metadata; see the schema discovery reference.

    Supply exactly one of *dsn* or an existing execsql adapter *connection*.
    Filters are exact, case-sensitive names, not SQL or wildcard expressions.
    Owned connections close on every exit; borrowed connections are never closed,
    committed or rolled back. Driver exceptions are deliberately not echoed, as
    their messages can contain credentials. KeyboardInterrupt/SystemExit propagate.
    """
    from execsql.api import _connect_from_dsn, _LibraryConfig
    from execsql.exceptions import ScriptExit
    from execsql.state import RuntimeContext, active_context

    if (dsn is None) == (connection is None):
        raise ValueError("Provide exactly one of 'dsn' or 'connection'.")
    for name, value in (("schema", schema), ("table", table)):
        if value is not None and (not isinstance(value, str) or not value or "\x00" in value):
            raise ValueError(f"{name} must be a nonempty name without NUL characters.")
    result: dict[str, Any] = {
        "schema_version": 1,
        "success": False,
        "dialect": None,
        "adapter": None,
        "capabilities": {},
        "tables": [],
        "error": None,
    }
    ctx = RuntimeContext()
    ctx.conf = cast(Any, _LibraryConfig())
    phase = "connection"
    db = connection
    with active_context(ctx):
        try:
            if db is None:
                assert dsn is not None
                db = _connect_from_dsn(dsn, prompt_password=False)
            phase = "metadata"
            dialect = db.type.dbms_id
            result["adapter"] = dialect
            result["dialect"] = None if dialect == "DSN" else dialect
            if dialect not in _READERS:
                result["error"] = {
                    "code": "unsupported_adapter",
                    "message": "Schema discovery is unavailable for this adapter.",
                }
                return result
            keys = dialect not in ("Access", "DSN")
            result["capabilities"] = {"tables": True, "columns": True, "primary_key": keys, "foreign_keys": keys}
            tables = _READERS[dialect](db, schema, table)
            if dialect in ("Access", "DSN"):
                for field in ("primary_key", "foreign_keys"):
                    result["capabilities"][field] = all(t[field] is not None for t in tables) if tables else None
            for item in tables:
                item["columns"].sort(key=lambda c: c["ordinal_position"])
            result["tables"] = sorted(tables, key=lambda t: (t["catalog"] or "", t["schema"] or "", t["name"]))
            result["success"] = True
        except (Exception, ScriptExit):
            result["error"] = {"code": f"{phase}_error", "message": f"Schema discovery {phase} failed."}
        finally:
            if dsn is not None and db is not None:
                try:
                    db.close()
                except Exception:
                    result["success"] = False
                    result["tables"] = []
                    result["error"] = {"code": "close_error", "message": "Schema discovery connection cleanup failed."}
    return result
