"""JSON catalog metadata through the existing ``list`` command group."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from execsql.cli.application import ExecsqlCommand
from execsql.cli.commands.listing import list_app


@list_app.command(cls=ExecsqlCommand, name="schema")
def schema_cmd(
    dsn: Annotated[str, typer.Option("--dsn", help="Connection URL; inspection never prompts for a password.")],
    schema: Annotated[str | None, typer.Option("--schema", help="Exact schema name (case-sensitive). ")] = None,
    table: Annotated[str | None, typer.Option("--table", help="Exact table or view name (case-sensitive). ")] = None,
) -> None:
    """Inspect tables, columns and keys as versioned JSON without reading rows."""
    from execsql.schema import inspect_schema

    try:
        result = inspect_schema(dsn=dsn, schema=schema, table=table)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    if not result["success"]:
        raise typer.Exit(code=1)
