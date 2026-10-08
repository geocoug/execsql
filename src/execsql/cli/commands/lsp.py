"""The ``lsp`` command: the language server editors start for ``.sql`` files."""

from __future__ import annotations

import typer

from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _err_console

__all__ = ["lsp_cmd"]


@app.command(
    cls=ExecsqlCommand,
    name="lsp",
    help=(
        "Run the execsql language server on stdin/stdout, for an editor to start. "
        "Shows execsql lint findings as you type and completes metacommands, "
        "conditional tests and variables. Needs the lsp extra: "
        'uv tool install "execsql2[lsp]".'
    ),
)
def lsp_cmd() -> None:
    """The ``lsp`` command; its user-facing help is the decorator's ``help``."""
    try:
        from execsql.lsp.server import create_server
    except ImportError as exc:
        _err_console.print(
            "[bold red]Error:[/bold red] execsql lsp needs the lsp extra: "
            'uv tool install "execsql2\\[lsp]" (or pip install "execsql2\\[lsp]").',
            highlight=False,
        )
        raise typer.Exit(code=1) from exc
    create_server().start_io()
