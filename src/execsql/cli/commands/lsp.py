"""The ``lsp`` command: the language server editors start for ``.sql`` files."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

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


class LogLevel(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"


def _configure_logging(level: LogLevel, log_file: Path | None) -> None:
    """Send the server's log (execsql's and pygls's) to stderr, which editors show, or to *log_file*.

    stdout carries the protocol, so nothing may be logged there.
    """
    handler: logging.Handler = (
        logging.FileHandler(log_file, encoding="utf-8") if log_file is not None else logging.StreamHandler()
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level.value.upper())
    # pygls logs every message it sends at info, script text included: only debug shows them.
    logging.getLogger("pygls").setLevel(logging.DEBUG if level is LogLevel.debug else logging.WARNING)


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
    log_level: LogLevel = typer.Option(
        LogLevel.warning,
        "--log-level",
        envvar="EXECSQL_LSP_LOG_LEVEL",
        case_sensitive=False,
        help="How much the server logs: error, warning, info (adds a startup record and each folder's config files) "
        "or debug (adds every protocol message).",
    ),
    log_file: Path | None = typer.Option(
        None,
        "--log-file",
        dir_okay=False,
        help="Append the log to this file instead of stderr, for an editor that does not show the server's stderr.",
    ),
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
    _configure_logging(log_level, log_file)
    create_server().start_io()
