"""The ``shell`` command: an interactive session for SQL and metacommands."""

from __future__ import annotations

from pathlib import Path

import typer

from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _err_console
from execsql.cli.options import ConfigFileOpt, DbTypeOpt, DsnOpt, NoPasswdOpt, PortOpt, UserOpt
from execsql.cli.run import _run

__all__ = ["shell_cmd"]


@app.command(cls=ExecsqlCommand, name="shell")
def shell_cmd(
    args: list[str] | None = typer.Argument(
        None,
        metavar="[SERVER DATABASE | DATABASE_FILE]",
        help=(
            "The database, as for run. When nothing names one — here, in --dsn or in a config file — "
            "the shell opens an in-memory SQLite database."
        ),
    ),
    db_type: DbTypeOpt = None,
    dsn: DsnOpt = None,
    user: UserOpt = None,
    port: PortOpt = None,
    no_passwd: NoPasswdOpt = False,
    new_db: bool = typer.Option(
        False,
        "-n",
        "--new-db",
        help="Create the SQLite, DuckDB or PostgreSQL database if it does not exist, as run -n does.",
    ),
    config_file: ConfigFileOpt = None,
) -> None:
    """Open an interactive session for SQL and metacommands.

    Type SQL ending with ;, or a metacommand as in a script (-- !x! ... or
    !x! ...). SELECT results are shown as tables. Blocks such as IF ... ENDIF
    stay open until closed. .help lists the shell's own commands.
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
        new_db=new_db,
        port=port,
        scanlines=None,
        db_type=db_type,
        user=user,
        use_gui=None,
        no_passwd=no_passwd,
        dsn=dsn,
        config_file=config_file,
        shell=True,
    )
