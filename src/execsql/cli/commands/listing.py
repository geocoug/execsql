"""The ``list`` command: reference lists of metacommands, encodings, plugins and keywords.

The module is not named ``list`` so importing it never shadows the builtin.
"""

from __future__ import annotations

import json
import sys
from enum import Enum

import typer

from execsql.cli.application import ExecsqlCommand, app
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

__all__ = ["Listing", "list_cmd", "print_listing"]


class Listing(str, Enum):
    """What ``execsql list`` can print."""

    metacommands = "metacommands"
    encodings = "encodings"
    plugins = "plugins"
    keywords = "keywords"


def print_listing(thing: Listing, output_format: OutputFormat) -> None:
    """Print one reference list. The hidden ``run`` aliases call this too."""
    if output_format is OutputFormat.text:
        {
            Listing.metacommands: _print_metacommands,
            Listing.encodings: _print_encodings,
            Listing.plugins: _print_plugins,
            Listing.keywords: _print_keywords_text,
        }[thing]()
        return
    if thing is Listing.keywords:
        # Byte-for-byte what --dump-keywords has always printed.
        _print_keywords_json()
        return
    data: object
    if thing is Listing.metacommands:
        data = [{"name": name, "syntax": syntax} for name, syntax in _metacommand_rows()]
    elif thing is Listing.encodings:
        data = _encoding_names()
    else:
        data = _plugins_data()
    sys.stdout.write(json.dumps(data, indent=2) + "\n")


@app.command(cls=ExecsqlCommand, name="list")
def list_cmd(
    thing: Listing = typer.Argument(..., metavar="THING", help="metacommands, encodings, plugins or keywords."),
    output_format: OutputFormatOpt = OutputFormat.text,
) -> None:
    """List metacommands, encodings, plugins or keywords.

    keywords is the full vocabulary (metacommands by category, conditions,
    export formats, database types, variable patterns); its JSON form is what
    editor tooling reads.
    """
    print_listing(thing, output_format)
