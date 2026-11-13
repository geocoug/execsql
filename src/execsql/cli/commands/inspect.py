"""Read-only inspection of databases, schemas and tables."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from execsql.cli.application import ExecsqlCommand, ExecsqlSubGroup, app
from execsql.cli.options import NoPasswdOpt, OutputFormat, OutputFormatOpt, RequiredDsnOpt

inspect_app = typer.Typer(
    cls=ExecsqlSubGroup,
    name="inspect",
    help="Inspect database structure without executing scripts or reading rows.",
    rich_markup_mode=None,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(inspect_app, name="inspect")

_SchemaOpt = Annotated[str | None, typer.Option("--schema", help="Exact schema name (case-sensitive).")]
_PromptPasswordOpt = Annotated[
    bool,
    typer.Option("--prompt-password", help="Allow a password prompt on a terminal, including with JSON output."),
]


@inspect_app.command(cls=ExecsqlCommand, name="database")
def database_cmd(
    dsn: RequiredDsnOpt,
    output_format: OutputFormatOpt = OutputFormat.text,
    no_passwd: NoPasswdOpt = False,
    prompt_password: _PromptPasswordOpt = False,
) -> None:
    """Show database identity and namespaces with visible table/view counts."""
    _inspect(
        dsn=dsn,
        schema=None,
        table=None,
        output_format=output_format,
        no_passwd=no_passwd,
        prompt_password=prompt_password,
        database_overview=True,
    )


@inspect_app.command(cls=ExecsqlCommand, name="schema")
def schema_cmd(
    name: Annotated[str, typer.Argument(metavar="NAME", help="Exact schema name (case-sensitive).")],
    dsn: RequiredDsnOpt,
    output_format: OutputFormatOpt = OutputFormat.text,
    no_passwd: NoPasswdOpt = False,
    prompt_password: _PromptPasswordOpt = False,
) -> None:
    """List tables/views and key summaries within one schema. Text by default."""
    _inspect(
        dsn=dsn,
        schema=name,
        table=None,
        output_format=output_format,
        no_passwd=no_passwd,
        prompt_password=prompt_password,
    )


@inspect_app.command(cls=ExecsqlCommand, name="table")
def table_cmd(
    name: Annotated[str, typer.Argument(metavar="NAME", help="Exact table or view name (case-sensitive).")],
    dsn: RequiredDsnOpt,
    schema: _SchemaOpt = None,
    output_format: OutputFormatOpt = OutputFormat.text,
    no_passwd: NoPasswdOpt = False,
    prompt_password: _PromptPasswordOpt = False,
) -> None:
    """Inspect columns, types, keys and relationships for a table or view."""
    _inspect(
        dsn=dsn,
        schema=schema,
        table=name,
        output_format=output_format,
        no_passwd=no_passwd,
        prompt_password=prompt_password,
    )


def _inspect(
    *,
    dsn: str,
    schema: str | None,
    table: str | None,
    output_format: OutputFormat,
    no_passwd: bool,
    prompt_password: bool,
    database_overview: bool = False,
) -> None:
    """Apply one connection, prompting and output policy to every catalog scope."""
    from execsql.schema import inspect_schema

    from execsql.cli.inspection import print_inspection, print_inspection_error

    if prompt_password and no_passwd:
        raise typer.BadParameter("--prompt-password and --no-passwd cannot be combined.")
    terminal = _terminal_available()
    if prompt_password and not terminal:
        raise typer.BadParameter("Password prompting requires an interactive terminal.")
    allow_prompt = not no_passwd and terminal and (prompt_password or output_format is OutputFormat.text)
    try:
        result = inspect_schema(
            dsn=dsn,
            schema=schema,
            table=table,
            prompt_password=allow_prompt,
            include_database=database_overview,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_format is OutputFormat.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    elif result["success"]:
        print_inspection(result, detailed=table is not None, database_overview=database_overview)
    else:
        print_inspection_error(result, dsn)
    if not result["success"]:
        raise typer.Exit(code=1)


def _terminal_available() -> bool:
    """Never let an automatic password prompt consume redirected input."""
    return sys.stdin is not None and sys.stdin.isatty()
