"""Read-only inspection commands for databases and future script preflight."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from execsql.cli.application import ExecsqlCommand, ExecsqlSubGroup, app
from execsql.cli.options import NoPasswdOpt, OutputFormat, OutputFormatOpt

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
    dsn: Annotated[str, typer.Option("--dsn", help="Database connection URL, e.g. postgresql://user@host/database.")],
    schema: Annotated[str | None, typer.Option("--schema", help="Exact schema name (case-sensitive). ")] = None,
    table: Annotated[str | None, typer.Option("--table", help="Exact table or view name (case-sensitive). ")] = None,
    output_format: OutputFormatOpt = OutputFormat.text,
    no_passwd: NoPasswdOpt = False,
    prompt_password: Annotated[
        bool,
        typer.Option("--prompt-password", help="Allow a password prompt on a terminal, including with JSON output."),
    ] = False,
) -> None:
    """Inspect tables, columns and keys without reading rows. Text by default."""
    from execsql.schema import inspect_schema

    from execsql.cli.inspection import print_inspection, print_inspection_error

    if prompt_password and no_passwd:
        raise typer.BadParameter("--prompt-password and --no-passwd cannot be combined.")
    terminal = _terminal_available()
    if prompt_password and not terminal:
        raise typer.BadParameter("Password prompting requires an interactive terminal.")
    allow_prompt = not no_passwd and terminal and (prompt_password or output_format is OutputFormat.text)
    try:
        result = inspect_schema(dsn=dsn, schema=schema, table=table, prompt_password=allow_prompt)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_format is OutputFormat.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    elif result["success"]:
        print_inspection(result, detailed=table is not None)
    else:
        print_inspection_error(result, dsn)
    if not result["success"]:
        raise typer.Exit(code=1)


def _terminal_available() -> bool:
    """Never let an automatic password prompt consume redirected input."""
    return sys.stdin is not None and sys.stdin.isatty()
