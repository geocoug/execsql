"""The ``format`` command, and its hidden ``fmt`` alias."""

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
    in_place: bool = typer.Option(False, "-i", "--in-place", help="Modify files in place."),
    no_sql: bool = typer.Option(False, "--no-sql", help="Skip SQL reformatting via sqlglot."),
    indent: int = typer.Option(4, "--indent", metavar="N", help="Spaces per indent level."),
    leading_comma: bool = typer.Option(
        False,
        "--leading-comma",
        help="Place commas at the start of lines instead of the end.",
    ),
    script_encoding: ScriptEncodingOpt = None,
    # The old spelling of --script-encoding, kept working but out of --help.
    encoding: str | None = typer.Option(None, "--encoding", metavar="NAME", hidden=True),
    config_file: ConfigFileOpt = None,
) -> None:
    """Normalize metacommand keywords, block indentation, and SQL layout.

    SQL reformatting needs the [formatter] extra; --no-sql works without it.
    """
    from execsql.cli.run import _configured_script_encoding
    from execsql.format import run_formatter

    if Path("-") in targets:
        if len(targets) > 1:
            raise typer.BadParameter("- (stdin) cannot be combined with other paths.", param_hint="FILE_OR_DIR")
        if in_place:
            raise typer.BadParameter("stdin cannot be formatted in place; drop -i.", param_hint="'-i'")
    if config_file and not Path(config_file).is_file():
        _err_console.print(f"[bold red]Error:[/bold red] Config file {config_file!r} does not exist.")
        raise typer.Exit(code=2)

    raise typer.Exit(
        code=run_formatter(
            targets,
            check=check,
            in_place=in_place,
            no_sql=no_sql,
            indent=indent,
            leading_comma=leading_comma,
            encoding=script_encoding or encoding or _configured_script_encoding(config_file) or "utf-8",
        ),
    )


# One function, two names: `fmt` cannot drift from `format`.
app.command(cls=ExecsqlCommand, name="format")(format_cmd)
app.command(cls=ExecsqlCommand, name="fmt", hidden=True, help="Alias for format.")(format_cmd)
