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


def print_inspection(result: dict[str, Any], *, detailed: bool) -> None:
    """Show a catalog overview, or columns/relationships for selected tables."""
    engine = result["dialect"] or f"{result['adapter']} (dialect unknown)"
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
    _console.print(f"{len(tables)} object(s). Use --table NAME to inspect columns and relationships.")


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
