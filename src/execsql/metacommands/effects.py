"""What a matched metacommand touches: files it reads, writes or deletes, and connections.

Used by ``run --manifest``, which records the metacommands a run executed.
It classifies from the handler a metacommand dispatched to and the groups its
regex captured, so any other reader of a script (a static inspector) can share
the same answer.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Effect", "effects"]


@dataclass(frozen=True)
class Effect:
    """One thing a metacommand touches.

    Attributes:
        role: ``"read"``, ``"write"`` or ``"delete"`` for a file;
            ``"connect"`` or ``"use"`` for a database.
        target: The file path, or for a connection ``alias: server/db`` or
            ``alias: file``.
        detail: For a connection, the DBMS and user. Never a password.
    """

    role: str
    target: str
    detail: str = ""


_IMPORTS = (
    "x_import",
    "x_import_file",
    "x_import_feather",
    "x_import_json",
    "x_import_ods",
    "x_import_ods_pattern",
    "x_import_parquet",
    "x_import_xls",
    "x_import_xls_pattern",
    "x_sub_ini",
    "x_serve",
)
_EXPORTS = (
    "x_export",
    "x_export_query",
    "x_export_metadata",
    "x_export_with_template",
    "x_export_query_with_template",
    "x_export_ods_multiple",
    "x_export_xlsx_multiple",
)
_WRITES = (
    "x_write",
    "x_writescript",
    "x_consolesave",
    "x_cancel_halt_write",
    "x_error_halt_write",
    "x_debug_write_config",
    "x_debug_write_metacommands",
    "x_debug_write_odbc_drivers",
    "x_debug_write_subvars",
)

#: Handler name → {regex group: role}. Groups not listed (passwords,
#: encodings, prompt paths) are never reported.
FILE_ROLES: dict[str, dict[str, str]] = {
    **{name: {"filename": "read"} for name in _IMPORTS},
    **{name: {"filename": "write", "zipfilename": "write", "template": "read"} for name in _EXPORTS},
    **{name: {"filename": "write"} for name in _WRITES},
    **{
        name: {"filename": "read", "outfile": "write"}
        for name in ("x_write_create_table", "x_write_create_table_ods", "x_write_create_table_xls")
    },
    "x_write_create_table_alias": {"filename": "read"},
    **{
        name: {"att_file": "read", "msg_file": "read"}
        for name in ("x_email", "x_cancel_halt_email", "x_error_halt_email")
    },
    "x_zip": {"filename": "read", "zipfilename": "write"},
    "x_rm_file": {"filename": "delete"},
}

DBMS = {
    "pg": "PostgreSQL",
    "mysql": "MySQL",
    "ssvr": "SQL Server",
    "ora": "Oracle",
    "fb": "Firebird",
    "sqlite": "SQLite",
    "duckdb": "DuckDB",
    "access": "MS Access",
    "dsn": "ODBC DSN",
}


def _connection(handler: str, groups: dict[str, str | None]) -> Effect | None:
    if handler == "x_use":
        return Effect("use", groups.get("db_alias") or "")
    if not handler.startswith("x_connect_"):
        return None
    kind = handler.removeprefix("x_connect_").removeprefix("user_")
    target = groups.get("filename") or groups.get("dsn") or ""
    if groups.get("server"):
        target = f"{groups['server']}/{groups.get('db_name') or ''}"
    detail = DBMS.get(kind, kind)
    if groups.get("user"):
        detail += f", user {groups['user']}"
    return Effect("connect", f"{groups.get('db_alias') or ''}: {target}".strip(), detail)


def effects(handler: str, groups: dict[str, str | None]) -> list[Effect]:
    """Everything a metacommand dispatched to *handler* with *groups* touches."""
    connection = _connection(handler, groups)
    if connection is not None:
        return [connection]
    found = []
    for group, role in FILE_ROLES.get(handler, {}).items():
        value = groups.get(group)
        if value:
            found.append(Effect(role, value.strip().strip('"')))
    return found
