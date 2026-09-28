"""The ``format`` command, and its hidden ``fmt`` alias."""

from __future__ import annotations

from pathlib import Path

import typer

from execsql.cli.application import ExecsqlCommand, app

__all__ = ["fmt_cmd", "format_cmd"]


@app.command(cls=ExecsqlCommand, name="format")
def format_cmd(
    targets: list[Path] = typer.Argument(
        ...,
        metavar="FILE_OR_DIR...",
        help="Files or directories to format. Directories are searched recursively for *.sql files.",
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
    encoding: str = typer.Option(
        "utf-8",
        "--encoding",
        metavar="NAME",
        help="Text encoding used to read and write SQL files.",
    ),
) -> None:
    """Normalize metacommand keywords, block indentation, and SQL layout.

    SQL reformatting needs the [formatter] extra; --no-sql works without it.
    """
    from execsql.format import run_formatter

    raise typer.Exit(
        code=run_formatter(
            targets,
            check=check,
            in_place=in_place,
            no_sql=no_sql,
            indent=indent,
            leading_comma=leading_comma,
            encoding=encoding,
        ),
    )


@app.command(cls=ExecsqlCommand, name="fmt", hidden=True)
def fmt_cmd(
    targets: list[Path] = typer.Argument(..., metavar="FILE_OR_DIR..."),
    check: bool = typer.Option(False, "--check"),
    in_place: bool = typer.Option(False, "-i", "--in-place"),
    no_sql: bool = typer.Option(False, "--no-sql"),
    indent: int = typer.Option(4, "--indent", metavar="N"),
    leading_comma: bool = typer.Option(False, "--leading-comma"),
    encoding: str = typer.Option("utf-8", "--encoding", metavar="NAME"),
) -> None:
    """Alias for format."""
    format_cmd(
        targets,
        check=check,
        in_place=in_place,
        no_sql=no_sql,
        indent=indent,
        leading_comma=leading_comma,
        encoding=encoding,
    )
