"""Human-readable database inspection, using the same metadata as JSON callers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import unicodedata

from rich import box
from rich.table import Table
from rich.text import Text

from execsql.cli.help import _console, _err_console


def _literal(value: object) -> Text:
    """Keep catalog names literal: no Rich markup or terminal control sequences."""
    text = str(value)
    return Text("".join(f"\\x{ord(c):02x}" if unicodedata.category(c) == "Cc" else c for c in text))


def _name(item: dict[str, Any], *, referenced: bool = False) -> str:
    prefix = "referenced_" if referenced else ""
    parts = (
        item.get(prefix + "catalog"),
        item.get(prefix + "schema"),
        item.get("referenced_table" if referenced else "name"),
    )
    return ".".join(str(p) for p in parts if p not in (None, ""))


def _primary_key(item: dict[str, Any]) -> str:
    keys = item["primary_key"]
    return "unavailable" if keys is None else ", ".join(keys) if keys else "none"


def print_inspection(result: dict[str, Any], *, detailed: bool, database_overview: bool = False) -> None:
    """Show a catalog overview, or columns/relationships for selected tables."""
    engine = result["dialect"] or f"{result['adapter']} (dialect unknown)"
    database = result.get("database") if database_overview else None
    if database is not None:
        _console.print(_literal(f"Database: {database['name'] or 'unavailable'}"), style="bold")
        _console.print(_literal(f"Engine: {database['engine'] or engine}"))
        namespaces = result["schemas"]
        if database["namespace_kind"] in ("schema", "attached_database") and namespaces is not None:
            overview = Table(box=box.SIMPLE, show_edge=False)
            for title in (
                "Namespace" if database["namespace_kind"] == "attached_database" else "Schema",
                "Tables",
                "Views",
            ):
                overview.add_column(title, overflow="fold")
            for namespace in namespaces:
                overview.add_row(
                    _literal(namespace["name"] if namespace["name"] is not None else "(no schema)"),
                    str(namespace["table_count"]),
                    str(namespace["view_count"]),
                )
            _console.print(overview)
            _console.print("Counts cover tables/views visible to this connection.")
            if not namespaces:
                _console.print("No visible schemas or namespaces.")
            _console.print("Use execsql inspect schema NAME --dsn URL to inspect its objects.")
            return
        if namespaces is None:
            _console.print("Schema enumeration unavailable; showing visible objects.")
    else:
        _console.print(_literal(engine), style="bold")
    tables = result["tables"]
    if not tables:
        _console.print("No matching tables or views.")
        return
    if detailed:
        for item in tables:
            _print_table(item)
        return
    overview = Table(box=box.SIMPLE, show_edge=False)
    for title in ("Object", "Kind", "Columns", "Primary key", "Foreign keys"):
        overview.add_column(title, overflow="fold")
    for item in tables:
        foreign = item["foreign_keys"]
        overview.add_row(
            _literal(_name(item)),
            _literal(item["kind"]),
            _literal(len(item["columns"])),
            _literal(_primary_key(item)),
            _literal("unavailable" if foreign is None else len(foreign)),
        )
    _console.print(overview)
    _console.print(f"{len(tables)} object(s). Use execsql inspect table NAME --dsn URL [--schema SCHEMA] for details.")


def _print_table(item: dict[str, Any]) -> None:
    _console.print()
    _console.print(_literal(f"{_name(item)} ({item['kind']})"), style="bold")
    columns = Table(box=box.SIMPLE, show_edge=False)
    for title in ("Column", "Type", "Nullable", "Key"):
        columns.add_column(title, overflow="fold")
    primary = item["primary_key"] or []
    foreign = item["foreign_keys"]
    for column in item["columns"]:
        name = column["name"]
        flags = []
        if name in primary:
            flags.append("PK")
        if foreign and any(name in key["columns"] for key in foreign):
            flags.append("FK")
        data_type = column["data_type"]
        type_text = "unavailable" if data_type is None else data_type or "(undeclared)"
        nullable = "unknown" if column["nullable"] is None else "yes" if column["nullable"] else "no"
        columns.add_row(_literal(name), _literal(type_text), _literal(nullable), _literal(", ".join(flags)))
    _console.print(columns)
    _console.print(_literal(f"Primary key: {_primary_key(item)}"))
    if not foreign:
        _console.print("Foreign keys: unavailable" if foreign is None else "Foreign keys: none")
    else:
        _console.print("Foreign keys:")
        for key in foreign:
            source = ", ".join(key["columns"])
            target = ", ".join(c if c is not None else "?" for c in key["referenced_columns"])
            constraint = f" [{key['name']}]" if key["name"] is not None else ""
            _console.print(_literal(f"  ({source}) -> {_name(key, referenced=True)} ({target}){constraint}"))


def print_inspection_error(result: dict[str, Any], dsn: str) -> None:
    """Explain failures without printing credential-bearing URLs or driver text."""
    error = result["error"]
    _err_console.print(_literal(f"Error: {error['message']}"), style="bold red")
    hints = {
        "metadata_error": "Check catalog permissions and the adapter's schema-discovery support.",
        "unsupported_adapter": "Use a supported database adapter; see the schema-discovery reference.",
        "close_error": "The connection could not be closed. Check the database server and driver.",
    }
    hint = hints.get(error["code"])
    if hint is None:
        hint = _connection_hint(dsn)
    _err_console.print(_literal(hint))


def _connection_hint(dsn: str) -> str:
    from execsql.cli.dsn import _parse_connection_string

    try:
        params = _parse_connection_string(dsn)
    except Exception:
        return "Check the URL scheme, host, port and database name. Run execsql inspect database --help for examples."
    file = params["db_file"]
    if file and file != ":memory:":
        try:
            exists = Path(file).is_file()
        except (OSError, ValueError):
            return "Check the database file path and read permissions."
        if not exists:
            return "Check the file path; inspection never creates a database."
        return "Check that the database file is readable and its adapter driver is installed."
    if params["db_type"] in ("l", "k"):
        return "Check that the in-process database driver is installed and the database can be opened."
    return (
        "Check the server, port, database name, installed driver and credentials. "
        "Include the user in the URL and use --prompt-password on a terminal for password authentication, "
        "or --no-passwd for driver/OS authentication."
    )


def print_file_inspection(result: dict[str, Any]) -> None:
    """Render the file contract as literal metadata, never source row values."""
    _console.print(_literal(f"File: {result['file']}"), style="bold")
    _console.print(_literal(f"Format: {result['format']} ({result['format_source']})"))
    if result["encoding"] is not None:
        encoding = result["encoding"]
        _console.print(_literal(f"Encoding: {encoding['name']} ({encoding['source']})"))
    if result["format"] == "delimited":
        _console.print(
            _literal(f"Delimiter: {result['delimiter']!r}; quote: {result['quote']!r} ({result['dialect_source']})"),
        )
    if result["skip_rows"]:
        _console.print(f"Skipped before header: {result['skip_rows']} line(s)/worksheet row(s).")
    if result["worksheets"] is not None and result["sheet"] is None:
        _console.print("Worksheets:")
        for index, name in enumerate(result["worksheets"], 1):
            _console.print(_literal(f"  {index}. {name}"))
        _console.print("Use --sheet NAME to inspect columns.")
    else:
        if result["sheet"] is not None:
            _console.print(_literal(f"Worksheet: {result['sheet']}"))
        scan = result["scan"]
        complete = "complete" if scan["complete"] else "incomplete; inferred types are provisional"
        _console.print(f"Scan: {scan['mode']}, {scan['rows_examined']} data rows examined ({complete}).")
        if not scan["complete"]:
            _console.print(f"Total data rows: {scan['total_rows'] if scan['total_rows'] is not None else 'unknown'}")
        if scan["mode"] == "sample" and scan["source_materialized"]:
            _console.print(
                "This reader materialized the full source; sampling limited inference, not file reads or memory.",
            )
        columns = Table(box=box.SIMPLE, show_edge=False)
        stored = any(column["source_type"] is not None for column in result["columns"])
        for heading in ("Column", "Inferred type", "Nulls"):
            columns.add_column(heading, overflow="fold")
        if stored:
            columns.add_column("Stored type", overflow="fold")
        for column in result["columns"]:
            values: list[Text | str] = [
                _literal(column["name"]),
                _literal(column["inferred_type"]),
                str(column["null_count"]),
            ]
            if stored:
                values.append(_literal(column["source_type"] or "unavailable"))
            columns.add_row(*values)
        _console.print(columns)
    _console.print(
        _literal("Configuration files: " + (", ".join(result["config_files"]) or "none (built-in defaults)")),
    )
    _console.print(
        _literal("Import settings: " + ", ".join(f"{name}={value}" for name, value in result["settings"].items())),
    )
