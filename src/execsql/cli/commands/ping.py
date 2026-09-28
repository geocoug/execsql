"""The ``ping`` command: test a database connection."""

from __future__ import annotations

from pathlib import Path

import typer

from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _err_console
from execsql.cli.options import (
    ConfigFileOpt,
    DbTypeOpt,
    DsnOpt,
    NoPasswdOpt,
    OutputFormat,
    OutputFormatOpt,
    PortOpt,
    UserOpt,
)
from execsql.cli.run import _run

__all__ = ["ping_cmd"]


@app.command(cls=ExecsqlCommand, name="ping")
def ping_cmd(
    args: list[str] | None = typer.Argument(
        None,
        metavar="[SERVER DATABASE | DATABASE_FILE]",
        help=(
            "Server and database name (client-server DBs) or a database file path "
            "(file-based DBs). Optional when --dsn or a config file names the database."
        ),
    ),
    db_type: DbTypeOpt = None,
    dsn: DsnOpt = None,
    user: UserOpt = None,
    port: PortOpt = None,
    no_passwd: NoPasswdOpt = False,
    config_file: ConfigFileOpt = None,
    output_format: OutputFormatOpt = OutputFormat.text,
) -> None:
    """Test a database connection and print the server version.

    Connects, prints the DBMS, its version and where it is, and disconnects.
    Exits 0 when the connection succeeds and 1 when it fails. No script is
    read, and a ping never creates a database, even when a config file sets
    new_db = yes.
    """
    if config_file and not Path(config_file).is_file():
        _err_console.print(f"[bold red]Error:[/bold red] Config file {config_file!r} does not exist.")
        raise typer.Exit(code=2)
    if db_type and db_type not in ("a", "d", "p", "s", "l", "m", "k", "o", "f"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid database type {db_type!r}. Choose from: a, d, p, s, l, m, k, o, f",
        )
        raise typer.Exit(code=2)

    _run(
        positional=list(args or []),
        sub_vars=None,
        boolean_int=None,
        make_dirs=None,
        database_encoding=None,
        script_encoding=None,
        output_encoding=None,
        import_encoding=None,
        user_logfile=False,
        new_db=False,
        port=port,
        scanlines=None,
        db_type=db_type,
        user=user,
        use_gui=None,
        no_passwd=no_passwd,
        dsn=dsn,
        ping=True,
        config_file=config_file,
        ping_format=output_format.value,
        ping_may_create_db=False,
    )
