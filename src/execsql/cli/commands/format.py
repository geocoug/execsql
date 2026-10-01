"""The ``format`` command."""

from __future__ import annotations

from pathlib import Path

import typer

from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _err_console
from execsql.cli.options import ConfigFileOpt, ScriptEncodingOpt

__all__ = ["format_cmd"]


def format_cmd(
    targets: list[Path] = typer.Argument(
        ...,
        metavar="FILE_OR_DIR...",
        help=(
            "Files or directories to format. Directories are searched recursively for *.sql files. "
            "- reads one script from stdin and writes the result to stdout."
        ),
    ),
    check: bool = typer.Option(False, "--check", help="Exit 1 if any file needs changes; write nothing."),
    diff: bool = typer.Option(
        False,
        "--diff",
        help="Print a unified diff of each file that would change; write nothing. Exits 1 if any would.",
    ),
    in_place: bool = typer.Option(False, "-i", "--in-place", help="Modify files in place."),
    # The three layout options default to None — "not given" — so that
    # [format] in a config file applies unless the command line says otherwise,
    # in either direction.
    sql: bool | None = typer.Option(
        None,
        "--sql/--no-sql",
        help="Reformat SQL with sqlglot, or only metacommands. Default: [format] sql, else --sql.",
        show_default=False,
    ),
    indent: int | None = typer.Option(
        None,
        "--indent",
        metavar="N",
        help="Spaces per indent level. Default: [format] indent, else 4.",
        show_default=False,
    ),
    leading_comma: bool | None = typer.Option(
        None,
        "--leading-comma/--no-leading-comma",
        help="Commas at the start of lines instead of the end. Default: [format] leading_comma, else off.",
        show_default=False,
    ),
    script_encoding: ScriptEncodingOpt = None,
    # The old spelling of --script-encoding, kept working but out of --help.
    encoding: str | None = typer.Option(None, "--encoding", metavar="NAME", hidden=True),
    config_file: ConfigFileOpt = None,
) -> None:
    """Normalize metacommand keywords, block indentation, and SQL layout.

    SQL reformatting needs the [formatter] extra; --no-sql works without it.
    Layout options not given here come from [format] in a config file.
    """
    from execsql.cli.run import _configured_script_encoding, _tool_config
    from execsql.format import _require_sqlglot, run_formatter

    if Path("-") in targets:
        if len(targets) > 1:
            raise typer.BadParameter("- (stdin) cannot be combined with other paths.", param_hint="FILE_OR_DIR")
        if in_place:
            raise typer.BadParameter("stdin cannot be formatted in place; drop -i.", param_hint="'-i'")
    if diff and in_place:
        raise typer.BadParameter("--diff writes nothing, so it cannot be combined with -i.", param_hint="'--diff'")
    if config_file and not Path(config_file).is_file():
        _err_console.print(f"[bold red]Error:[/bold red] Config file {config_file!r} does not exist.")
        raise typer.Exit(code=2)

    conf = _tool_config(config_file)
    no_sql = not (conf.format_sql if sql is None else sql)
    if not no_sql:
        try:
            _require_sqlglot()
        except ImportError as exc:
            _err_console.print(f"[bold red]Error:[/bold red] {exc}", highlight=False)
            raise typer.Exit(code=1) from exc
    raise typer.Exit(
        code=run_formatter(
            targets,
            check=check,
            diff=diff,
            in_place=in_place,
            no_sql=no_sql,
            indent=conf.format_indent if indent is None else indent,
            leading_comma=conf.format_leading_comma if leading_comma is None else leading_comma,
            encoding=script_encoding or encoding or _configured_script_encoding(conf) or "utf-8",
        ),
    )


app.command(cls=ExecsqlCommand, name="format")(format_cmd)
