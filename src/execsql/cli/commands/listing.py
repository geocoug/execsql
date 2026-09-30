"""The ``list`` command: reference lists, one subcommand each.

``execsql list metacommands|encodings|plugins|keywords``. Each list is its own
command so it can take options of its own. The module is not named ``list``
so importing it never shadows the builtin.
"""

from __future__ import annotations

import json
import sys

import typer

from execsql.cli.application import ExecsqlCommand, ExecsqlSubGroup, app
from execsql.cli.help import (
    _encoding_names,
    _metacommand_rows,
    _plugins_data,
    _print_encodings,
    _print_keywords_json,
    _print_keywords_text,
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
def metacommands_cmd(output_format: OutputFormatOpt = OutputFormat.text) -> None:
    """Every metacommand and its syntax."""
    if output_format is OutputFormat.json:
        _json([{"name": name, "syntax": syntax} for name, syntax in _metacommand_rows()])
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
