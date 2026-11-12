"""Read-only inspection commands for databases and future script preflight."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from execsql.cli.application import ExecsqlCommand, ExecsqlSubGroup, app

inspect_app = typer.Typer(
    cls=ExecsqlSubGroup,
    name="inspect",
    help="Inspect database structure without executing scripts or reading rows.",
    rich_markup_mode=None,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(inspect_app, name="inspect")


@inspect_app.command(cls=ExecsqlCommand, name="database")
def database_cmd(
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
