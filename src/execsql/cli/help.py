"""Rich tables and console objects for the execsql CLI.

Contains the metacommand reference table, encoding list, and the shared
``Console`` instances used by the other CLI submodules.
"""

from __future__ import annotations

from encodings.aliases import aliases as codec_dict
from typing import Any

from rich.console import Console
from rich.table import Table

__all__ = [
    "_console",
    "_encoding_names",
    "_err_console",
    "_init_config",
    "_init_config_text",
    "_keywords_data",
    "_metacommand_rows",
    "_plugins_data",
    "_print_encodings",
    "_print_keywords_json",
    "_print_metacommands",
    "_print_plugins",
]

_console = Console()
_err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Metacommand syntax hints — paired with keywords from the dispatch table.
# Keys must match the ``description`` values used in mcl.add() calls.
# Entries here are validated by tests/test_registry.py.
# ---------------------------------------------------------------------------

_SYNTAX: dict[str, tuple[str, str]] = {
    # (display_name, syntax_hint)
    "ASK": ("ASK", '"<question>" SUB <match_string>'),
    "AUTOCOMMIT": ("AUTOCOMMIT", "ON|OFF"),
    "BEGIN BATCH": ("BEGIN BATCH / END BATCH / ROLLBACK BATCH", ""),
    "BEGIN SCRIPT": ("BEGIN SCRIPT / END SCRIPT", ""),
    "BEGIN SQL": ("BEGIN SQL / END SQL", ""),
    "CANCEL_HALT": ("CANCEL_HALT", "ON|OFF"),
    "CD": ("CD", "<directory>"),
    "CONNECT": ("CONNECT", "<alias> [AS <alias_name>]"),
    "COPY": ("COPY", "<source_file> TO <dest_file>"),
    "DEBUG": ("DEBUG", "ON|OFF"),
    "SUB": ("DEFINE SUB", "<variable> [AS] <value>"),
    "EXPORT QUERY": ("EXPORT QUERY", "<queryname> [AS <alias>] ..."),
    "EXPORT": ("EXPORT", "<queryname> TO <format> <filename> ..."),
    "HALT": ("HALT [ON]", "ERROR|CANCEL"),
    "IF": ("IF <condition>", "/ ELSE / ENDIF"),
    "IMPORT_FILE": ("IMPORT FILE", "<filename> [OPTIONS ...]"),
    "IMPORT": ("IMPORT TABLE", "<tablename> FROM FILE <filename> [OPTIONS ...]"),
    "LOOP": ("LOOP <n> TIMES | WHILE | UNTIL", "/ END LOOP"),
    "CONFIG": ("CONFIG", "<option> <value>"),
    "ON CANCEL_HALT": ("ON CANCEL_HALT", "..."),
    "ON ERROR_HALT": ("ON ERROR_HALT", "..."),
    "PAUSE": ("PAUSE", "[<text>]"),
    "PROMPT ACTION": ("PROMPT ACTION", "..."),
    "PROMPT ENTRY_FORM": ("PROMPT ENTRY_FORM", "..."),
    "PROMPT OPENFILE": ("PROMPT OPENFILE", "..."),
    "PROMPT SAVEFILE": ("PROMPT SAVEFILE", "..."),
    "PROMPT DIRECTORY": ("PROMPT DIRECTORY", "..."),
    "PROMPT MAP": ("PROMPT MAP", "..."),
    "ROLLBACK BATCH": ("ROLLBACK", ""),
    "SERVE": ("SERVE", "<queryname> ..."),
    "SYSTEM_CMD": ("SYSTEM_CMD", "(<operating system command line>)"),
    "TIMER": ("TIMER", "ON|OFF"),
    "USE": ("USE", "<alias_name>"),
    "WAIT_UNTIL": ("WAIT_UNTIL", "<Boolean_expression> <HALT|CONTINUE> AFTER <n> SECONDS"),
    "WRITE": ("WRITE", '"<text>" [[TEE] TO <output>]'),
    "WRITE CREATE_TABLE": ("WRITE CREATE_TABLE FROM", "<filename> [TO <output>]"),
    "WRITE SCRIPT": ("WRITE SCRIPT", "<script_name> [[APPEND] TO <output_file>]"),
    "ZIP": ("ZIP", "<filename> [APPEND] TO ZIPFILE <zipfilename>"),
    "SUB_TEMPFILE": ("SUB_TEMPFILE", "<variable>"),
}

# Keys from _SYNTAX that should be skipped when auto-generating from dispatch
# table (they're variants covered by another entry).
_SKIP_FROM_DISPATCH = {
    "END BATCH",
    "END SCRIPT",
    "END SQL",
    "ROLLBACK BATCH",
    "BEGIN SCRIPT",
    "BEGIN SQL",
}


def _init_config_text() -> str:
    """The default execsql.conf template, every option commented out and documented."""
    import importlib.resources

    return importlib.resources.files("execsql.data").joinpath("execsql.conf.template").read_text(encoding="utf-8")


def _init_config() -> None:
    """Print the default execsql.conf template to stdout."""
    import sys

    sys.stdout.write(_init_config_text())


def _metacommand_rows() -> list[tuple[str, str]]:
    """``(name, syntax)`` for every metacommand, in the order they are listed.

    Keyword list is derived from the dispatch table; syntax hints come from
    the ``_SYNTAX`` dict above.  Keywords not in ``_SYNTAX`` get an empty
    syntax hint.
    """
    from execsql.metacommands import DISPATCH_TABLE

    # Collect unique keyword names from the dispatch table.
    seen: set[str] = set()
    keywords: list[str] = []
    for mc in DISPATCH_TABLE:
        if mc.description and mc.description not in seen and mc.description not in _SKIP_FROM_DISPATCH:
            seen.add(mc.description)
            keywords.append(mc.description)
    # Add parser-level keywords not in the dispatch table.
    for extra in ("BEGIN BATCH", "BEGIN SCRIPT", "BEGIN SQL"):
        if extra not in seen:
            seen.add(extra)
            keywords.append(extra)

    rows: list[tuple[str, str]] = []
    for kw in sorted(keywords):
        if kw in _SYNTAX:
            rows.append(_SYNTAX[kw])
        elif kw.startswith("CONFIG ") or kw.startswith("CONSOLE_") or "_" in kw:
            continue  # skip config options / internal entries
        else:
            rows.append((kw, ""))
    return rows


def _print_metacommands() -> None:
    """Print the metacommands table using Rich."""
    table = Table(
        title="execsql Metacommands",
        caption="Embed in SQL comment lines following the [bold]!x![/bold] token.",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=False,
    )
    table.add_column("Metacommand", style="bold green", no_wrap=True)
    table.add_column("Syntax", style="white")
    for name, syntax in _metacommand_rows():
        table.add_row(name, syntax)
    _console.print(table)


def _encoding_names() -> list[str]:
    """Every encoding name Python accepts, sorted."""
    return sorted(codec_dict.keys())


def _print_encodings() -> None:
    """Print available encodings using Rich."""
    enc = _encoding_names()
    table = Table(
        title="Available Encodings",
        show_header=False,
        border_style="dim",
        expand=True,
    )
    table.add_column("Encoding", style="cyan")
    # 4 columns
    cols = 4
    for i in range(0, len(enc), cols):
        row = enc[i : i + cols]
        while len(row) < cols:
            row.append("")
        table.add_row(*row)
    _console.print(table)


def _keywords_data() -> dict[str, Any]:
    """The full keyword vocabulary: the data behind ``--dump-keywords``.

    The VS Code grammar build and ``tests/test_registry.py`` read its JSON
    form, so the shape of this dict is a contract.
    """
    from execsql.metacommands import (
        ALL_EXPORT_FORMATS,
        DATABASE_TYPES,
        DISPATCH_TABLE,
        JSON_VARIANT_FORMATS,
        METADATA_FORMATS,
        QUERY_EXPORT_FORMATS,
        SERVE_FORMATS,
        TABLE_EXPORT_FORMATS,
    )
    from execsql.metacommands.conditions import CONDITIONAL_TABLE

    mc_kw = DISPATCH_TABLE.keywords_by_category()
    cond_kw = CONDITIONAL_TABLE.keywords_by_category()

    data = {
        "metacommands": {
            "control": sorted(mc_kw.get("control", [])),
            "block": sorted(
                mc_kw.get("block", []) + ["BEGIN SCRIPT", "END SCRIPT", "BEGIN SQL", "END SQL"],
            ),
            "action": sorted(mc_kw.get("action", [])),
            "config": sorted(mc_kw.get("config", [])),
            "prompt": sorted(mc_kw.get("prompt", [])),
        },
        "conditions": sorted(cond_kw.get("condition", []) + ["IS_FALSE", "NOT", "OR"]),
        "config_options": sorted(mc_kw.get("config_option", [])),
        "export_formats": {
            "query": sorted(QUERY_EXPORT_FORMATS),
            "table": sorted(TABLE_EXPORT_FORMATS),
            "serve": sorted(SERVE_FORMATS),
            "metadata": sorted(METADATA_FORMATS),
            "json_variants": sorted(JSON_VARIANT_FORMATS),
            "all": sorted(ALL_EXPORT_FORMATS),
        },
        "database_types": sorted(DATABASE_TYPES),
        "variable_patterns": {
            "system": "!!$name!!",
            "environment": "!!&name!!",
            "parameter": "!!#name!!",
            "column": "!!@name!!",
            "local": "!!~name!!",
            "local_alt": "!!+name!!",
            "regular": "!!name!!",
            "deferred": "!{name}!",
        },
    }
    return data


def _print_keywords_json() -> None:
    """Print :func:`_keywords_data` as JSON, exactly as ``--dump-keywords`` always has."""
    import json

    _console.print_json(json.dumps(_keywords_data(), indent=2))


def _plugins_data() -> dict[str, list[str]]:
    """Names of the installed plugins, by kind."""
    from execsql.plugins import (
        EXPORTER_GROUP,
        IMPORTER_GROUP,
        METACOMMAND_GROUP,
        _load_entry_points,
    )

    return {
        "metacommands": [name for name, _ in _load_entry_points(METACOMMAND_GROUP)],
        "exporters": [name for name, _ in _load_entry_points(EXPORTER_GROUP)],
        "importers": [name for name, _ in _load_entry_points(IMPORTER_GROUP)],
    }


def _print_plugins() -> None:
    """Print the installed plugins, or how to write one when there are none."""
    plugins = _plugins_data()
    _console.print("\n[bold cyan]Installed plugins:[/bold cyan]\n")
    if not any(plugins.values()):
        _console.print("  [dim]No plugins found.[/dim]")
        _console.print()
        _console.print(
            "  Plugins are discovered via Python entry points.\n"
            "  See the execsql documentation for how to create plugins.",
        )
    else:
        for kind, names in plugins.items():
            if names:
                _console.print(f"  [bold]{kind.capitalize()}[/bold] ({len(names)}):")
                for name in names:
                    _console.print(f"    - {name}")
    _console.print()
