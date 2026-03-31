"""Command-line interface for execsql.

Parses arguments via Typer, then delegates to :func:`_run` for state
initialisation, database connection, and script execution.

Submodules:

- :mod:`execsql.cli.help`  — Rich-formatted help output & console objects
- :mod:`execsql.cli.dsn`   — Connection-string (DSN URL) parser
- :mod:`execsql.cli.run`   — Core execution logic
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

import typer

from execsql import __version__
from execsql.cli.dsn import _parse_connection_string, _SCHEME_TO_DBTYPE  # noqa: F401 — re-export
from execsql.cli.help import _console, _err_console, _print_encodings, _print_metacommands  # noqa: F401 — re-export
from execsql.cli.run import _connect_initial_db, _run  # noqa: F401 — re-export
from execsql.exceptions import ConfigError, ErrInfo

__all__ = [
    "_SCHEME_TO_DBTYPE",
    "_connect_initial_db",
    "_console",
    "_err_console",
    "_legacy_main",
    "_parse_connection_string",
    "_print_encodings",
    "_print_metacommands",
    "_run",
    "app",
    "main",
]


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="execsql",
    help="Run a SQL script against a database with metacommand support.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        _console.print(f"execsql [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def main(
    ctx: typer.Context,
    # Positional args collected manually (script + optional server/db/file)
    args: list[str] | None = typer.Argument(
        None,
        metavar="SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]",
        help=(
            "SQL script file to execute. Optionally followed by server and database "
            "name (client-server DBs) or a database file path (file-based DBs)."
        ),
    ),
    # Named options — grouped to mirror the original argparse interface
    sub_vars: list[str] | None = typer.Option(
        None,
        "-a",
        "--assign-arg",
        metavar="VALUE",
        help="Define the replacement string for a substitution variable [cyan]\\$ARG_x[/cyan].",
    ),
    boolean_int: str | None = typer.Option(
        None,
        "-b",
        "--boolean-int",
        metavar="{0,1,t,f,y,n}",
        help="Treat integers 0 and 1 as boolean values.",
    ),
    make_dirs: str | None = typer.Option(
        None,
        "-d",
        "--directories",
        metavar="{0,1,t,f,y,n}",
        help="Auto-create directories for EXPORT metacommand. [dim]n=no (default), y=yes[/dim]",
    ),
    database_encoding: str | None = typer.Option(
        None,
        "-e",
        "--database-encoding",
        help="Character encoding used in the database.",
    ),
    script_encoding: str | None = typer.Option(
        None,
        "-f",
        "--script-encoding",
        help="Character encoding of the script file. [dim]Default: UTF-8[/dim]",
    ),
    output_encoding: str | None = typer.Option(
        None,
        "-g",
        "--output-encoding",
        help="Encoding for WRITE and EXPORT output.",
    ),
    import_encoding: str | None = typer.Option(
        None,
        "-i",
        "--import-encoding",
        help="Encoding for data files used with IMPORT.",
    ),
    user_logfile: bool = typer.Option(
        False,
        "-l",
        "--user-logfile",
        help="Write a log file to [cyan]~/execsql.log[/cyan].",
    ),
    metacommands: bool = typer.Option(
        False,
        "-m",
        "--metacommands",
        help="List metacommands and exit.",
    ),
    new_db: bool = typer.Option(
        False,
        "-n",
        "--new-db",
        help="Create a new SQLite or Postgres database if it does not exist.",
    ),
    online_help: bool = typer.Option(
        False,
        "-o",
        "--online-help",
        help="Open the online documentation in the default browser.",
    ),
    port: int | None = typer.Option(
        None,
        "-p",
        "--port",
        help="Database server port.",
    ),
    scanlines: int | None = typer.Option(
        None,
        "-s",
        "--scan-lines",
        metavar="N",
        help="Lines to scan for IMPORT format detection. [dim]0 = scan entire file.[/dim]",
    ),
    db_type: str | None = typer.Option(
        None,
        "-t",
        "--type",
        metavar="{a,d,p,s,l,m,k,o,f}",
        help=(
            "Database type: [bold]a[/bold]=MS-Access, [bold]p[/bold]=PostgreSQL, "
            "[bold]s[/bold]=SQL Server, [bold]l[/bold]=SQLite, [bold]m[/bold]=MySQL/MariaDB, "
            "[bold]k[/bold]=DuckDB, [bold]o[/bold]=Oracle, [bold]f[/bold]=Firebird, "
            "[bold]d[/bold]=DSN."
        ),
    ),
    user: str | None = typer.Option(
        None,
        "-u",
        "--user",
        help="Database user name.",
    ),
    use_gui: str | None = typer.Option(
        None,
        "-v",
        "--visible-prompts",
        metavar="{0,1,2,3}",
        help=(
            "GUI level: [bold]0[/bold]=none (default), [bold]1[/bold]=GUI for password/pause, "
            "[bold]2[/bold]=GUI for password/pause + DB selection, [bold]3[/bold]=full GUI console."
        ),
    ),
    gui_framework: str | None = typer.Option(
        None,
        "--gui-framework",
        metavar="{tkinter,textual}",
        help="GUI framework to use with [cyan]--visible-prompts[/cyan]. [dim]Default: tkinter[/dim]",
    ),
    no_passwd: bool = typer.Option(
        False,
        "-w",
        "--no-passwd",
        help="Skip password prompt when user is specified.",
    ),
    encodings: bool = typer.Option(
        False,
        "-y",
        "--encodings",
        help="List available encoding names and exit.",
    ),
    import_buffer: int | None = typer.Option(
        None,
        "-z",
        "--import-buffer",
        metavar="KB",
        help="Import buffer size in KB. [dim]Default: 32[/dim]",
    ),
    command: str | None = typer.Option(
        None,
        "-c",
        "--command",
        metavar="SCRIPT",
        help=(
            "Execute an inline SQL/metacommand script string instead of a script file. "
            "Use shell [cyan]$'line1\\nline2'[/cyan] syntax for multi-line scripts."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=("Parse the script and print the command list without connecting to a database or executing anything."),
    ),
    dsn: str | None = typer.Option(
        None,
        "--dsn",
        "--connection-string",
        metavar="URL",
        help=(
            "Database connection URL, e.g. [cyan]postgresql://user:pass@host:5432/db[/cyan]. "
            "Supported schemes: postgresql, mysql, mssql, oracle, firebird, sqlite, duckdb. "
            "Overrides [cyan]-t[/cyan]/[cyan]-u[/cyan]/[cyan]-p[/cyan] and positional server/db args."
        ),
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        metavar="DIR",
        help=(
            "Default base directory for EXPORT output files. "
            "Relative paths in EXPORT metacommands are joined to this directory. "
            "Absolute paths and [cyan]stdout[/cyan] are unaffected."
        ),
    ),
    progress: bool = typer.Option(
        False,
        "--progress",
        help="Show a progress bar for long-running IMPORT operations.",
    ),
    dump_keywords: bool = typer.Option(
        False,
        "--dump-keywords",
        help="Dump all metacommand keywords as JSON and exit.",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Run [bold]SQL_SCRIPT[/bold] against the specified database.

    [dim]Positional arguments after the script file:[/dim]

    [green]Client-server databases:[/green]
      execsql script.sql [SERVER] [DATABASE]

    [green]File-based databases (SQLite, DuckDB, Access):[/green]
      execsql script.sql [DATABASE_FILE]
    """
    # ------------------------------------------------------------------
    # Early exits (no script file needed)
    # ------------------------------------------------------------------
    if metacommands:
        _print_metacommands()
        raise typer.Exit()

    if encodings:
        _print_encodings()
        raise typer.Exit()

    if dump_keywords:
        import json as _json

        from execsql.metacommands import (
            ALL_EXPORT_FORMATS,
            DATABASE_TYPES,
            DISPATCH_TABLE,
            JSON_VARIANT_FORMATS,
            METADATA_FORMATS,
            QUERY_EXPORT_FORMATS,
            SERVE_FORMATS,
            TABLE_EXPORT_FORMATS,
        )
        from execsql.metacommands.conditions import CONDITIONAL_TABLE

        mc_kw = DISPATCH_TABLE.keywords_by_category()
        cond_kw = CONDITIONAL_TABLE.keywords_by_category()

        data = {
            "metacommands": {
                "control": sorted(mc_kw.get("control", [])),
                "block": sorted(
                    mc_kw.get("block", []) + ["BEGIN SCRIPT", "END SCRIPT", "BEGIN SQL", "END SQL"],
                ),
                "action": sorted(mc_kw.get("action", [])),
                "config": sorted(mc_kw.get("config", [])),
                "prompt": sorted(mc_kw.get("prompt", [])),
            },
            "conditions": sorted(cond_kw.get("condition", []) + ["IS_FALSE", "NOT", "OR"]),
            "config_options": sorted(mc_kw.get("config_option", [])),
            "export_formats": {
                "query": sorted(QUERY_EXPORT_FORMATS),
                "table": sorted(TABLE_EXPORT_FORMATS),
                "serve": sorted(SERVE_FORMATS),
                "metadata": sorted(METADATA_FORMATS),
                "json_variants": sorted(JSON_VARIANT_FORMATS),
                "all": sorted(ALL_EXPORT_FORMATS),
            },
            "database_types": sorted(DATABASE_TYPES),
            "variable_patterns": {
                "system": "!!$name!!",
                "environment": "!!&name!!",
                "parameter": "!!#name!!",
                "column": "!!@name!!",
                "local": "!!~name!!",
                "local_alt": "!!+name!!",
                "regular": "!!name!!",
                "deferred": "!{name}!",
            },
        }
        _console.print_json(_json.dumps(data, indent=2))
        raise typer.Exit()

    if online_help:
        import webbrowser

        webbrowser.open("https://execsql2.readthedocs.io/en/latest/", new=2, autoraise=True)
        raise typer.Exit()

    positional = args or []
    if command is not None:
        script_name = None  # inline mode — no script file
    else:
        if not positional:
            _err_console.print(
                "[bold red]Error:[/bold red] No SQL script file specified. Use [cyan]-c[/cyan] to run an inline script.",
            )
            raise typer.Exit(code=1)
        script_name = positional[0]
        if not Path(script_name).exists():
            _err_console.print(
                f'[bold red]Error:[/bold red] SQL script file [cyan]"{script_name}"[/cyan] does not exist.',
            )
            raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Validate positional args and db_type choice
    # ------------------------------------------------------------------

    if db_type and db_type not in ("a", "d", "p", "s", "l", "m", "k", "o", "f"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid database type [cyan]{db_type!r}[/cyan]. "
            "Choose from: a, d, p, s, l, m, k, o, f",
        )
        raise typer.Exit(code=2)

    if use_gui and use_gui not in ("0", "1", "2", "3"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid GUI level [cyan]{use_gui!r}[/cyan]. Choose from: 0, 1, 2, 3",
        )
        raise typer.Exit(code=2)

    if gui_framework and gui_framework.lower() not in ("tkinter", "textual"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid GUI framework [cyan]{gui_framework!r}[/cyan]. Choose from: tkinter, textual",
        )
        raise typer.Exit(code=2)

    if boolean_int and boolean_int.lower() not in ("0", "1", "t", "f", "y", "n"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid --boolean-int value [cyan]{boolean_int!r}[/cyan].",
        )
        raise typer.Exit(code=2)

    # ------------------------------------------------------------------
    # Delegate to the real main implementation
    # ------------------------------------------------------------------
    _run(
        positional=positional,
        sub_vars=sub_vars,
        boolean_int=boolean_int,
        make_dirs=make_dirs,
        database_encoding=database_encoding,
        script_encoding=script_encoding,
        output_encoding=output_encoding,
        import_encoding=import_encoding,
        user_logfile=user_logfile,
        new_db=new_db,
        port=port,
        scanlines=scanlines,
        db_type=db_type,
        user=user,
        use_gui=use_gui,
        gui_framework=gui_framework,
        no_passwd=no_passwd,
        import_buffer=import_buffer,
        script_name=script_name,
        command=command,
        dry_run=dry_run,
        dsn=dsn,
        output_dir=output_dir,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Legacy entry point (kept for backwards compat with pyproject.toml script)
# ---------------------------------------------------------------------------


def _legacy_main() -> None:
    """Entry point that wraps the Typer app for use as a console_scripts target."""
    try:
        app()
    except SystemExit as exc:
        raise exc from exc
    except ErrInfo as exc:
        from execsql.utils.errors import exit_now

        exit_now(1, exc)
    except ConfigError as exc:
        strace = traceback.extract_tb(sys.exc_info()[2])[-1:]
        lno = strace[0][1]
        sys.exit(f"Configuration error on line {lno} of execsql: {exc}")
    except Exception:
        strace = traceback.extract_tb(sys.exc_info()[2])[-1:]
        lno = strace[0][1]
        msg = f"{Path(sys.argv[0]).name}: Uncaught exception {sys.exc_info()[0]} ({sys.exc_info()[1]}) on line {lno}"
        from execsql.utils.errors import exit_now

        exit_now(1, ErrInfo("exception", exception_msg=msg))


if __name__ == "__main__":
    _legacy_main()
