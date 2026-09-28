"""Options shared by more than one command, each defined once.

A command declares a shared option by annotating a parameter with one of the
types below, so ``run`` and ``ping`` cannot drift apart on a flag's spelling,
metavar or help text. Options that belong to a single command stay in that
command's module.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer

__all__ = [
    "ConfigFileOpt",
    "DbTypeOpt",
    "DsnOpt",
    "NoPasswdOpt",
    "OutputFormat",
    "OutputFormatOpt",
    "PortOpt",
    "UserOpt",
]

# -- Connection (run, ping) ----------------------------------------------------

DbTypeOpt = Annotated[
    str | None,
    typer.Option(
        "-t",
        "--type",
        metavar="{a,d,p,s,l,m,k,o,f}",
        help=(
            "Database type: a=MS-Access, p=PostgreSQL, "
            "s=SQL Server, l=SQLite, m=MySQL/MariaDB, "
            "k=DuckDB, o=Oracle, f=Firebird, "
            "d=DSN."
        ),
    ),
]

DsnOpt = Annotated[
    str | None,
    typer.Option(
        "--dsn",
        "--connection-string",
        metavar="URL",
        help=(
            "Database connection URL, e.g. postgresql://user:pass@host:5432/db. "
            "Supported schemes: postgresql, mysql, mssql, oracle, firebird, sqlite, duckdb. "
            "Overrides -t/-u/-p and positional server/db args."
        ),
    ),
]

UserOpt = Annotated[str | None, typer.Option("-u", "--user", help="Database user name.")]

PortOpt = Annotated[int | None, typer.Option("-p", "--port", help="Database server port.")]

NoPasswdOpt = Annotated[
    bool,
    typer.Option("-w", "--no-passwd", help="Skip password prompt when user is specified."),
]

# -- Configuration (run, ping, config) -----------------------------------------

ConfigFileOpt = Annotated[
    str | None,
    typer.Option(
        "--config",
        metavar="FILE",
        help=(
            "Path to an execsql configuration file. "
            "Loaded after the implicit search paths so its values take precedence. "
            "The file may chain additional configs via its [config] section."
        ),
    ),
]

# -- Machine-readable output (ping, config, list) ------------------------------


class OutputFormat(str, Enum):
    """Output formats for commands that report data rather than check files."""

    text = "text"
    json = "json"


OutputFormatOpt = Annotated[
    OutputFormat,
    typer.Option("--output-format", help="text for people; json for tools."),
]
