"""Read-only CREATE statements and IMPORT-based file declarations."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from execsql.db.base import Database
from execsql.models import DataTable
from execsql.types import DbType


class SqlDialect(str, Enum):
    """Explicit destination dialects for inferred file SQL."""

    sqlite = "sqlite"
    duckdb = "duckdb"
    postgres = "postgres"
    mysql = "mysql"
    mssql = "mssql"
    oracle = "oracle"
    firebird = "firebird"
    access = "access"


class DdlError(Exception):
    """A fixed, nonsecret explanation for unavailable SQL output."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _quote(name: str, dialect: str) -> str:
    opening, closing = (
        ("`", "`") if dialect == "MySQL" else ("[", "]") if dialect in ("SQL Server", "Access") else ('"', '"')
    )
    return opening + name.replace(closing, closing * 2) + closing


class _FileDialect(DbType):
    """Share IMPORT declarations, preserving its unquoted-name folding."""

    def __init__(self, source: DbType):
        super().__init__(source.dbms_id)
        self.source = source
        self.dialect = source.dialect

    def spec_type(self, data_type: Any) -> Any:
        return self.source.spec_type(data_type)

    def quoted(self, dbms_object: str) -> str:
        if not re.search(r"\W", dbms_object):
            if not dbms_object.isascii():
                # Let the engine apply its existing locale/Unicode folding.
                return self.source.quoted(dbms_object)
            if self.dbms_id == "PostgreSQL":
                dbms_object = dbms_object.lower()
            elif self.dbms_id in ("Oracle", "Firebird"):
                dbms_object = dbms_object.upper()
        return _quote(dbms_object, self.dbms_id)


def file_sql(table: DataTable, dialect: str, schema: str | None, name: str) -> str:
    """Use the existing type and observed-nullability inference, without rescanning."""
    from execsql import types

    target = {
        "sqlite": types.dbt_sqlite,
        "duckdb": types.dbt_duckdb,
        "postgres": types.dbt_postgres,
        "mysql": types.dbt_mysql,
        "mssql": types.dbt_sqlserver,
        "oracle": types.dbt_oracle,
        "firebird": types.dbt_firebird,
        "access": types.dbt_access,
    }[dialect]
    if not table.cols:
        raise DdlError("sql_error", "SQL output requires at least one inferred column.")
    if any(not isinstance(column.name, str) or not column.name or "\x00" in column.name for column in table.cols):
        raise DdlError("sql_error", "Inferred SQL column names must be nonempty and contain no NUL characters.")
    return table.create_table(_FileDialect(target), schema, name, pretty=True) + "\n"


SUPPORTED_TABLE_SQL = {"SQLite", "DuckDB", "MySQL", "PostgreSQL"}


def _statement(sql: Any) -> str:
    if not isinstance(sql, str) or not sql.strip() or "\x00" in sql:
        raise DdlError("sql_error", "The database did not return a complete object definition.")
    text = sql.rstrip()
    # A final line comment must not consume an appended statement terminator.
    return text + ("\n" if text.endswith(";") else "\n;\n")


def table_sql(db: Database, tables: list[dict[str, Any]]) -> str:
    """Read exactly one selected object's definition; never fetch its data."""
    from execsql.schema import _rows

    if not tables:
        raise DdlError("object_not_found", "SQL output requires one matching table or view; none was found.")
    if len(tables) != 1:
        raise DdlError(
            "ambiguous_object",
            "SQL output requires one matching table or view; use --schema to qualify it.",
        )
    item = tables[0]
    namespace, name, kind = item["schema"], item["name"], item["kind"]
    dialect = db.type.dbms_id
    if dialect == "SQLite":
        rows = _rows(
            db,
            f"SELECT sql FROM {db.quote_identifier(namespace)}.sqlite_master WHERE name = ? AND type = ?",
            [name, kind],
        )
        return _statement(rows[0][0] if rows else None)
    if dialect == "DuckDB":
        function, column = ("duckdb_views", "view_name") if kind == "view" else ("duckdb_tables", "table_name")
        rows = _rows(
            db,
            f"SELECT sql FROM {function}() WHERE database_name = current_database() AND schema_name = ? AND {column} = ?",
            [namespace, name],
        )
        return _statement(rows[0][0] if rows else None)
    if dialect == "MySQL":
        mode, collation, timezone, system_timezone = _rows(
            db,
            "SELECT @@sql_mode, @@collation_connection, @@time_zone, @@system_time_zone",
        )[0]
        if set(mode.upper().split(",")) & {"NO_FIELD_OPTIONS", "NO_KEY_OPTIONS", "NO_TABLE_OPTIONS"}:
            raise DdlError("unsupported_sql_feature", "Current MySQL/MariaDB SQL mode omits definition details.")
        if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_,]*", value) for value in (mode, collation)):
            raise DdlError("sql_error", "The database returned invalid SQL session metadata.")
        if timezone == "SYSTEM":
            # An abbreviation cannot recover historical daylight-saving rules,
            # and SYSTEM on the destination may refer to a different zone.
            if system_timezone not in ("UTC", "GMT"):
                raise DdlError(
                    "unsupported_sql_feature",
                    "SQL output requires an explicit MySQL/MariaDB session time_zone or a UTC system time zone.",
                )
            timezone = "+00:00"
        if not isinstance(timezone, str) or not re.fullmatch(r"[A-Za-z0-9_+:/-]+", timezone):
            raise DdlError("sql_error", "The database returned invalid SQL session metadata.")
        command = "VIEW" if kind == "view" else "TABLE"
        rows = _rows(db, f"SHOW CREATE {command} {db.quote_identifier(namespace)}.{db.quote_identifier(name)}")
        sql = _statement(rows[0][1] if rows else None)
        if kind == "view" and len(rows[0]) >= 4:
            collation = rows[0][3]  # The view's creation context, not this session's default.
        if not isinstance(collation, str) or not re.fullmatch(r"[A-Za-z0-9_]+", collation):
            raise DdlError("sql_error", "The database returned invalid SQL session metadata.")
        # Leave client encoding to the destination driver. SET NAMES would change
        # the server's decoder without updating that driver's own text encoder.
        return (
            f"SET SESSION sql_mode = '{mode}';\nSET collation_connection = '{collation}';\n"
            f"SET SESSION time_zone = '{timezone}';\n" + sql
        )
    if dialect == "PostgreSQL":
        return _postgres_sql(db, namespace, name)
    raise DdlError("unsupported_sql", "SQL output supports SQLite, DuckDB, MySQL/MariaDB and PostgreSQL tables/views.")


_PG_DEFINITION = """SELECT to_jsonb(c), n.nspname, am.amname, pg_catalog.current_schemas(true),
COALESCE((SELECT jsonb_agg(to_jsonb(a) || jsonb_build_object(
    'type_sql', pg_catalog.format_type(a.atttypid, a.atttypmod),
    'default_sql', pg_catalog.pg_get_expr(d.adbin, d.adrelid, false),
    'base_storage', t.typstorage,
    'collation_schema', cn.nspname, 'collation_name', co.collname,
    'different_collation', a.attcollation <> t.typcollation,
    'sequence', (SELECT to_jsonb(s) FROM pg_catalog.pg_sequence s
        JOIN pg_catalog.pg_depend dep ON dep.objid = s.seqrelid AND dep.classid = 'pg_catalog.pg_class'::regclass
        WHERE dep.refclassid = 'pg_catalog.pg_class'::regclass AND dep.refobjid = c.oid
        AND dep.refobjsubid = a.attnum AND dep.deptype = 'i')) ORDER BY a.attnum)
    FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
    LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    LEFT JOIN pg_catalog.pg_collation co ON co.oid = a.attcollation
    LEFT JOIN pg_catalog.pg_namespace cn ON cn.oid = co.collnamespace
    WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped), '[]'::jsonb),
COALESCE((SELECT jsonb_agg(to_jsonb(k) || jsonb_build_object(
    'definition', pg_catalog.pg_get_constraintdef(k.oid, false)) ORDER BY k.conname)
    FROM pg_catalog.pg_constraint k WHERE k.conrelid = c.oid), '[]'::jsonb),
CASE WHEN c.relkind = 'v' THEN pg_catalog.pg_get_viewdef(c.oid, false) END,
EXISTS(SELECT 1 FROM pg_catalog.pg_inherits i WHERE i.inhrelid = c.oid OR i.inhparent = c.oid),
(SELECT jsonb_object_agg(setting, pg_catalog.current_setting(setting)) FROM unnest(ARRAY[
    'DateStyle', 'IntervalStyle', 'standard_conforming_strings', 'lc_monetary',
    'TimeZone', 'backslash_quote', 'extra_float_digits']) AS settings(setting))
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_am am ON am.oid = c.relam
WHERE n.nspname = ? AND c.relname = ?"""


def _postgres_sql(db: Database, namespace: str, name: str) -> str:
    from execsql.schema import _rows

    if int(_rows(db, "SELECT pg_catalog.current_setting('server_version_num')")[0][0]) < 140000:
        raise DdlError("unsupported_sql_feature", "PostgreSQL SQL output requires PostgreSQL 14 or newer.")
    rows = _rows(db, _PG_DEFINITION, [namespace, name])
    if len(rows) != 1:
        raise DdlError("sql_error", "The selected object changed during SQL inspection; retry the command.")
    relation, namespace, access_method, search_path, columns, constraints, view, inherited, settings = rows[0]
    if int(settings["extra_float_digits"]) <= 0:
        raise DdlError(
            "unsupported_sql_feature",
            "PostgreSQL SQL output requires extra_float_digits greater than zero to preserve floating-point literals.",
        )
    kind = relation["relkind"]
    if kind not in ("r", "v") or relation.get("relispartition") or int(relation["reloftype"]) or inherited:
        raise DdlError(
            "unsupported_sql_feature",
            "PostgreSQL SQL output covers ordinary tables and views, not partitioned, inherited, typed, foreign or materialized objects.",
        )
    temporary = relation["relpersistence"] == "t"
    if temporary and kind == "r":
        raise DdlError(
            "unsupported_sql_feature",
            "PostgreSQL temporary-table ON COMMIT policy is unavailable through read-only catalog inspection.",
        )
    qualified = db.quote_identifier(name) if temporary else db.quote_qualified_identifier(namespace, name)
    # Keep server-decompiled expressions resolved as in the source, without SET
    # on the inspected connection. Required dependency objects are not recreated.
    paths = ["pg_temp" if path.startswith("pg_temp_") else path for path in search_path]
    context = "SET search_path TO " + ", ".join(db.quote_identifier(path) for path in paths) + ";\n"
    for setting, value in settings.items():
        # E strings with doubled backslashes/quotes work regardless of the
        # destination's standard_conforming_strings setting.
        literal = value.replace("\\", "\\\\").replace("'", "''")
        context += f"SET {setting} TO E'{literal}';\n"
    if kind == "v":
        view_options = []
        for option in relation["reloptions"] or []:
            key, _, value = option.partition("=")
            if key not in ("security_barrier", "security_invoker", "check_option") or value not in (
                "true",
                "false",
                "local",
                "cascaded",
            ):
                raise DdlError("unsupported_sql_feature", "This PostgreSQL view has unsupported creation options.")
            view_options.append(f"{key}={value}")
        names = ", ".join(db.quote_identifier(column["attname"]) for column in columns)
        header = f"CREATE {'TEMP ' if temporary else ''}VIEW {qualified}" + (f" ({names})" if names else "")
        if view_options:
            header += " WITH (" + ", ".join(view_options) + ")"
        return context + _statement(header + " AS\n" + view)
    if (
        relation["reloptions"]
        or int(relation["reltablespace"])
        or access_method != "heap"
        or relation["relrowsecurity"]
        or relation["relforcerowsecurity"]
        or relation["relreplident"] != "d"
    ):
        raise DdlError(
            "unsupported_sql_feature",
            "This PostgreSQL table has storage, row-security or replica-identity settings outside CREATE output's supported scope.",
        )
    if any(
        not constraint["convalidated"] or constraint["contype"] not in ("p", "u", "f", "c", "x", "n")
        for constraint in constraints
    ):
        raise DdlError("unsupported_sql_feature", "This PostgreSQL table has an unsupported or unvalidated constraint.")
    named_not_null = {
        number for constraint in constraints if constraint["contype"] == "n" for number in constraint["conkey"]
    }
    declarations = []
    for column in columns:
        if column["attstorage"] != column["base_storage"] or column.get("attcompression"):
            raise DdlError(
                "unsupported_sql_feature",
                "This PostgreSQL column has unsupported storage or compression options.",
            )
        datatype = column["type_sql"]
        if datatype.endswith("[]") and column["attndims"] > 1:
            datatype += "[]" * (column["attndims"] - 1)
        declaration = db.quote_identifier(column["attname"]) + " " + datatype
        if column["different_collation"]:
            declaration += " COLLATE " + db.quote_qualified_identifier(
                column["collation_schema"],
                column["collation_name"],
            )
        identity, generated = column.get("attidentity"), column.get("attgenerated")
        if identity:
            sequence = column["sequence"]
            if identity not in ("a", "d") or not sequence:
                raise DdlError("unsupported_sql_feature", "The PostgreSQL identity definition is unavailable.")
            options = " ".join(
                f"{label} {int(sequence[key])}"
                for label, key in (
                    ("START WITH", "seqstart"),
                    ("INCREMENT BY", "seqincrement"),
                    ("MINVALUE", "seqmin"),
                    ("MAXVALUE", "seqmax"),
                    ("CACHE", "seqcache"),
                )
            )
            options += " CYCLE" if sequence["seqcycle"] else " NO CYCLE"
            declaration += f" GENERATED {'ALWAYS' if identity == 'a' else 'BY DEFAULT'} AS IDENTITY ({options})"
        elif generated:
            if generated not in ("s", "v") or not column["default_sql"]:
                raise DdlError("unsupported_sql_feature", "The PostgreSQL generated-column definition is unavailable.")
            declaration += (
                f" GENERATED ALWAYS AS ({column['default_sql']}) {'STORED' if generated == 's' else 'VIRTUAL'}"
            )
        elif column["default_sql"] is not None:
            declaration += " DEFAULT " + column["default_sql"]
        if column["attnotnull"] and column["attnum"] not in named_not_null:
            declaration += " NOT NULL"
        declarations.append(declaration)
    declarations += ["CONSTRAINT " + db.quote_identifier(c["conname"]) + " " + c["definition"] for c in constraints]
    modifier = "TEMP " if temporary else "UNLOGGED " if relation["relpersistence"] == "u" else ""
    return context + f"CREATE {modifier}TABLE {qualified} (\n    " + ",\n    ".join(declarations) + "\n);\n"
