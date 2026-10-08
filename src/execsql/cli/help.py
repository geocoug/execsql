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
    "_metacommand_entries",
    "_metacommand_json",
    "_print_metacommand",
    "_plugins_data",
    "_print_encodings",
    "_print_keywords_json",
    "_print_keywords_text",
    "_print_metacommands",
    "_print_plugins",
]

_console = Console()
_err_console = Console(stderr=True)


def _init_config_text() -> str:
    """The default execsql.conf template, every option commented out and documented."""
    import importlib.resources

    return importlib.resources.files("execsql.data").joinpath("execsql.conf.template").read_text(encoding="utf-8")


def _init_config() -> None:
    """Print the default execsql.conf template to stdout."""
    import sys

    sys.stdout.write(_init_config_text())


_CATEGORY_ORDER = ("control", "block", "action", "config", "prompt")


def _metacommand_entries() -> list[Any]:
    """Every metacommand's readable entry, by category, then keyword."""
    from execsql.metacommands.reference import metacommands

    order = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    return sorted(metacommands(), key=lambda m: (order.get(m.category, len(order)), m.keyword))


def _metacommand_json(entry: Any) -> dict[str, Any]:
    return {
        "name": entry.keyword,
        "category": entry.category,
        "syntax": entry.forms[0],
        "forms": list(entry.forms),
        "summary": entry.summary,
        "url": entry.url,
    }


def _print_metacommands() -> None:
    """Print every metacommand with its category and one-line summary."""
    table = Table(
        title="execsql Metacommands",
        caption=(
            "Write them in a SQL comment after [bold]-- !x![/bold].  "
            "[bold]execsql list metacommands <KEYWORD>[/bold] shows the syntax of one."
        ),
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=False,
    )
    table.add_column("Metacommand", style="bold green", no_wrap=True)
    table.add_column("Category", style="dim", no_wrap=True)
    table.add_column("Summary", style="white")
    for entry in _metacommand_entries():
        table.add_row(entry.keyword, entry.category, entry.summary)
    _console.print(table)


def _print_metacommand(entry: Any) -> None:
    """Print one metacommand's syntax lines, summary and docs link."""
    from rich.markup import escape

    _console.print(f"[bold green]{escape(entry.keyword)}[/bold green]  [dim]{entry.category}[/dim]")
    _console.print(escape(entry.summary))
    _console.print()
    for form in entry.forms:
        _console.print(f"  -- !x! {escape(form)}", highlight=False)
    _console.print()
    _console.print(f"[dim]{entry.url}[/dim]", highlight=False)


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
    """The full keyword vocabulary: the data behind ``execsql list keywords``.

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
    """Print :func:`_keywords_data` as JSON: ``list keywords --output-format json``, and ``--dump-keywords`` as it always has."""
    import json

    _console.print_json(json.dumps(_keywords_data(), indent=2))


def _print_keywords_text() -> None:
    """Print :func:`_keywords_data` grouped under headings, for reading."""
    import textwrap

    data = _keywords_data()

    def group(title: str, words: list[str]) -> None:
        _console.print(f"[bold]{title}[/bold] ({len(words)})")
        _console.print(textwrap.fill(", ".join(words), width=88, initial_indent="  ", subsequent_indent="  "))
        _console.print()

    for category, words in data["metacommands"].items():
        group(f"Metacommands: {category}", words)
    group("Conditions", data["conditions"])
    group("CONFIG options", data["config_options"])
    group("Export formats", data["export_formats"]["all"])
    group("Database types", data["database_types"])
    _console.print("[bold]Variable patterns[/bold]")
    for name, pattern in data["variable_patterns"].items():
        _console.print(f"  {pattern:<12} {name}")


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
