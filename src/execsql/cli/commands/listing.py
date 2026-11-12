"""The ``list`` command: reference lists, one subcommand each.

``execsql list metacommands|encodings|plugins|keywords``. Each list is its own
command so it can take options of its own. The module is not named ``list``
so importing it never shadows the builtin.
"""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from execsql.cli.application import ExecsqlCommand, ExecsqlSubGroup, app
from execsql.cli.help import (
    _err_console,
    _encoding_names,
    _metacommand_entries,
    _metacommand_json,
    _plugins_data,
    _print_encodings,
    _print_keywords_json,
    _print_keywords_text,
    _print_metacommand,
    _print_metacommands,
    _print_plugins,
)
from execsql.cli.options import OutputFormat, OutputFormatOpt

__all__ = ["list_app"]

list_app = typer.Typer(
    cls=ExecsqlSubGroup,
    name="list",
    help="List metacommands, encodings, plugins or keywords.",
    rich_markup_mode=None,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(list_app, name="list")


def _json(data: object) -> None:
    sys.stdout.write(json.dumps(data, indent=2) + "\n")


@list_app.command(cls=ExecsqlCommand, name="metacommands")
def metacommands_cmd(
    keyword: Annotated[
        list[str] | None,
        typer.Argument(metavar="[KEYWORD]", help="Show one metacommand's syntax, e.g. EXPORT or export query."),
    ] = None,
    output_format: OutputFormatOpt = OutputFormat.text,
) -> None:
    """Every metacommand with a one-line summary, or the syntax of one."""
    if keyword:
        from execsql.metacommands.reference import metacommand

        wanted = " ".join(keyword)
        entry = metacommand(wanted)
        if entry is None:
            import difflib

            names = [m.keyword for m in _metacommand_entries()]
            close = difflib.get_close_matches(wanted.upper(), names, n=3)
            hint = f" Did you mean {', '.join(close)}?" if close else ""
            _err_console.print(f"[bold red]Error:[/bold red] No metacommand {wanted!r}.{hint}", highlight=False)
            raise typer.Exit(code=2)
        if output_format is OutputFormat.json:
            _json(_metacommand_json(entry))
        else:
            _print_metacommand(entry)
    elif output_format is OutputFormat.json:
        _json([_metacommand_json(m) for m in _metacommand_entries()])
    else:
        _print_metacommands()


@list_app.command(cls=ExecsqlCommand, name="encodings")
def encodings_cmd(output_format: OutputFormatOpt = OutputFormat.text) -> None:
    """Every character encoding name -e, -f, -g and -i accept."""
    if output_format is OutputFormat.json:
        _json(_encoding_names())
    else:
        _print_encodings()


@list_app.command(cls=ExecsqlCommand, name="plugins")
def plugins_cmd(output_format: OutputFormatOpt = OutputFormat.text) -> None:
    """Installed plugins: metacommands, exporters, importers."""
    if output_format is OutputFormat.json:
        _json(_plugins_data())
    else:
        _print_plugins()


@list_app.command(cls=ExecsqlCommand, name="keywords")
def keywords_cmd(output_format: OutputFormatOpt = OutputFormat.text) -> None:
    """The full vocabulary: metacommands by category, conditions, CONFIG options,
    export formats, database types, variable patterns. Its JSON is what editor
    tooling reads.
    """
    if output_format is OutputFormat.json:
        _print_keywords_json()
    else:
        _print_keywords_text()
