"""The ``lsp`` command: the language server editors start for ``.sql`` files."""

from __future__ import annotations

import typer
from rich.markup import escape

from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _err_console
from execsql.utils.errors import install_hint

__all__ = ["lsp_cmd"]


def _lsp_libraries_installed() -> bool:
    """Whether pygls and lsprotocol are installed (whether or not this execsql can use them)."""
    from importlib.util import find_spec

    return all(find_spec(name) is not None for name in ("pygls", "lsprotocol"))


def _pygls_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("pygls")
    except PackageNotFoundError:
        return "unknown"


@app.command(
    cls=ExecsqlCommand,
    name="lsp",
    help=(
        "Run the execsql language server on stdin/stdout, for an editor to start. "
        "Shows execsql lint findings as you type, completes metacommands, "
        "conditional tests and variables, explains them on hover, and finds where variables, "
        "SCRIPTs and included files are defined, offers quick fixes, and formats documents. Requires the lsp "
        "extra; --check reports whether it is installed."
    ),
)
def lsp_cmd(
    # Editors' language clients pass --stdio (VS Code always does); stdio is the only transport.
    stdio: bool = typer.Option(False, "--stdio", hidden=True),
    check: bool = typer.Option(False, "--check", help="Report whether the language server can start, and exit."),
) -> None:
    """The ``lsp`` command; its user-facing help is the decorator's ``help``."""
    try:
        from execsql.lsp.server import create_server
    except ImportError as exc:
        if _lsp_libraries_installed():
            # pygls is there but this execsql cannot use it (another major version, a broken install).
            message = (
                f"execsql lsp cannot use the installed pygls {_pygls_version()} ({exc}). "
                f"It needs pygls 2.x, which the lsp extra installs. {install_hint('lsp')}"
            )
        else:
            message = f"execsql lsp needs the lsp extra. {install_hint('lsp')}"
        _err_console.print(f"[bold red]Error:[/bold red] {escape(message)}", highlight=False)
        raise typer.Exit(code=1) from exc
    if check:
        typer.echo(f"execsql lsp is ready (pygls {_pygls_version()}).")
        return
    create_server().start_io()
