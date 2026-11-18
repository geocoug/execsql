"""Read-only inspection of database structure and importable files."""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import Annotated

import typer

from execsql.cli.application import ExecsqlCommand, ExecsqlSubGroup, app
from execsql.cli.options import NoPasswdOpt, OutputFormat, OutputFormatOpt
from execsql.cli.options import ConfigFileOpt
from execsql.file_inspection import FileFormat
from execsql.ddl import SqlDialect


class SqlOutputFormat(str, Enum):
    """Only table and file inspection support executable SQL output."""

    text = "text"
    json = "json"
    sql = "sql"


_SqlOutputFormatOpt = Annotated[
    SqlOutputFormat,
    typer.Option("--output-format", help="Readable text, versioned JSON or copyable SQL."),
]

inspect_app = typer.Typer(
    cls=ExecsqlSubGroup,
    name="inspect",
    help="Inspect database structure or importable files without executing scripts.",
    rich_markup_mode=None,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(inspect_app, name="inspect")

_SchemaOpt = Annotated[str | None, typer.Option("--schema", help="Exact schema name (case-sensitive).")]
_PromptPasswordOpt = Annotated[
    bool,
    typer.Option("--prompt-password", help="Allow a password prompt on a terminal, including with JSON or SQL output."),
]

_InspectionDsnOpt = Annotated[
    str | None,
    typer.Option(
        "--dsn",
        "--connection-string",
        metavar="URL",
        help="Database connection URL; omit to use [connect] configuration defaults.",
    ),
]
_ShowSettingsOpt = Annotated[bool, typer.Option("--show-settings", help="Include applicable settings in text output.")]
_ShowConfigOpt = Annotated[
    bool,
    typer.Option("--show-config", help="Include loaded configuration files in text output."),
]


@inspect_app.command(cls=ExecsqlCommand, name="database")
def database_cmd(
    dsn: _InspectionDsnOpt = None,
    config_file: ConfigFileOpt = None,
    show_settings: _ShowSettingsOpt = False,
    show_config: _ShowConfigOpt = False,
    output_format: OutputFormatOpt = OutputFormat.text,
    no_passwd: NoPasswdOpt = False,
    prompt_password: _PromptPasswordOpt = False,
) -> None:
    """Show database identity and namespaces with visible table/view counts."""
    _inspect(
        dsn=dsn,
        config_file=config_file,
        show_settings=show_settings,
        show_config=show_config,
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
    dsn: _InspectionDsnOpt = None,
    config_file: ConfigFileOpt = None,
    show_settings: _ShowSettingsOpt = False,
    show_config: _ShowConfigOpt = False,
    output_format: OutputFormatOpt = OutputFormat.text,
    no_passwd: NoPasswdOpt = False,
    prompt_password: _PromptPasswordOpt = False,
) -> None:
    """List tables/views and key summaries within one schema. Text by default."""
    _inspect(
        dsn=dsn,
        config_file=config_file,
        show_settings=show_settings,
        show_config=show_config,
        schema=name,
        table=None,
        output_format=output_format,
        no_passwd=no_passwd,
        prompt_password=prompt_password,
    )


@inspect_app.command(cls=ExecsqlCommand, name="table")
def table_cmd(
    name: Annotated[str, typer.Argument(metavar="NAME", help="Exact table or view name (case-sensitive).")],
    dsn: _InspectionDsnOpt = None,
    config_file: ConfigFileOpt = None,
    show_settings: _ShowSettingsOpt = False,
    show_config: _ShowConfigOpt = False,
    schema: _SchemaOpt = None,
    output_format: _SqlOutputFormatOpt = SqlOutputFormat.text,
    no_passwd: NoPasswdOpt = False,
    prompt_password: _PromptPasswordOpt = False,
) -> None:
    """Inspect columns, types, keys and relationships for a table or view."""
    _inspect(
        dsn=dsn,
        config_file=config_file,
        show_settings=show_settings,
        show_config=show_config,
        schema=schema,
        table=name,
        output_format=SqlOutputFormat.sql
        if output_format is SqlOutputFormat.sql
        else OutputFormat(output_format.value),
        no_passwd=no_passwd,
        prompt_password=prompt_password,
    )


def _inspect(
    *,
    dsn: str | None,
    config_file: str | None,
    show_settings: bool,
    show_config: bool,
    schema: str | None,
    table: str | None,
    output_format: OutputFormat | SqlOutputFormat,
    no_passwd: bool,
    prompt_password: bool,
    database_overview: bool = False,
) -> None:
    """Apply one connection, prompting and output policy to every catalog scope."""
    from execsql.schema import inspect_schema

    from execsql.cli.inspection import print_inspection, print_inspection_error, print_inspection_context

    sql_requested = output_format is SqlOutputFormat.sql
    if sql_requested and (show_settings or show_config):
        raise typer.BadParameter("SQL output cannot be combined with --show-settings or --show-config.")
    if prompt_password and no_passwd:
        raise typer.BadParameter("--prompt-password and --no-passwd cannot be combined.")
    terminal = _terminal_available()
    if prompt_password and not terminal:
        raise typer.BadParameter("Password prompting requires an interactive terminal.")
    allow_prompt: bool | None = False
    if terminal and not no_passwd:
        if prompt_password:
            allow_prompt = True
        elif output_format is OutputFormat.text:
            allow_prompt = None  # Follow the configured password-prompt preference.
    try:
        result = inspect_schema(
            dsn=dsn,
            config_file=config_file,
            schema=schema,
            table=table,
            prompt_password=allow_prompt,
            include_database=database_overview,
            include_details=not (sql_requested or (database_overview and output_format is OutputFormat.text)),
            include_sql=sql_requested,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_format is OutputFormat.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    elif result["success"] and sql_requested:
        sys.stdout.write(result["sql"])
    elif result["success"]:
        print_inspection(result, detailed=table is not None, database_overview=database_overview)
        print_inspection_context(result, show_settings=show_settings, show_config=show_config)
    else:
        print_inspection_error(result, dsn)
    if not result["success"]:
        raise typer.Exit(code=1)


def _terminal_available() -> bool:
    """Never let an automatic password prompt consume redirected input."""
    return sys.stdin is not None and sys.stdin.isatty()


@inspect_app.command(cls=ExecsqlCommand, name="file")
def file_cmd(
    path: Annotated[
        str,
        typer.Argument(metavar="PATH", help="Local file to inspect without loading it into a database."),
    ],
    file_format: Annotated[
        FileFormat | None,
        typer.Option("--format", help="Override the filename's format hint."),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option("--sheet", help="Worksheet name or 1-based number; omit to list sheets."),
    ] = None,
    sample_rows: Annotated[
        int | None,
        typer.Option("--sample-rows", min=1, help="Infer from at most N data rows; default scans all rows."),
    ] = None,
    encoding: Annotated[
        str | None,
        typer.Option("--encoding", help="Text or legacy XLS encoding; overrides import configuration."),
    ] = None,
    delimiter: Annotated[
        str | None,
        typer.Option("--delimiter", help="One delimiter character, TAB, US or SPACE; defaults quote to double quote."),
    ] = None,
    quote: Annotated[
        str | None,
        typer.Option("--quote", help="Quote character or 'none'; requires --delimiter."),
    ] = None,
    skip_rows: Annotated[
        int,
        typer.Option("--skip-rows", min=0, help="Skip leading lines/worksheet rows before the header."),
    ] = 0,
    config_file: ConfigFileOpt = None,
    show_settings: _ShowSettingsOpt = False,
    show_config: _ShowConfigOpt = False,
    output_format: _SqlOutputFormatOpt = SqlOutputFormat.text,
    dialect: Annotated[
        SqlDialect | None,
        typer.Option("--dialect", help="Required destination dialect for SQL output."),
    ] = None,
    table_name: Annotated[
        str | None,
        typer.Option("--table-name", help="Required destination table name for SQL output."),
    ] = None,
    schema: Annotated[str | None, typer.Option("--schema", help="Optional destination schema for SQL output.")] = None,
) -> None:
    """Inspect import formats, columns and inferred types; full scan by default."""
    from execsql.file_inspection import inspect_file
    from execsql.cli.inspection import print_file_inspection
    from execsql.cli.help import _err_console
    from execsql.cli.inspection import _literal

    sql_requested = output_format is SqlOutputFormat.sql
    if sql_requested and (dialect is None or not table_name):
        raise typer.BadParameter("SQL output requires both --dialect and --table-name.")
    if sql_requested and (show_settings or show_config or sample_rows is not None):
        raise typer.BadParameter("SQL output requires a full scan and cannot use --show-settings or --show-config.")
    if not sql_requested and any(value is not None for value in (dialect, table_name, schema)):
        raise typer.BadParameter("--dialect, --table-name and --schema require --output-format sql.")
    try:
        result = inspect_file(
            path,
            file_format=file_format.value if file_format else None,
            sheet=sheet,
            sample_rows=sample_rows,
            encoding=encoding,
            delimiter=delimiter,
            quote=quote,
            skip_rows=skip_rows,
            config_file=config_file,
            dialect=dialect.value if dialect else None,
            table_name=table_name,
            schema=schema,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_format is SqlOutputFormat.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    elif result["success"] and sql_requested:
        sys.stdout.write(result["sql"])
    elif result["success"]:
        print_file_inspection(result, show_settings=show_settings, show_config=show_config)
    else:
        _err_console.print(_literal(f"Error: {result['error']['message']}"), style="bold red")
    if not result["success"]:
        raise typer.Exit(code=1)
