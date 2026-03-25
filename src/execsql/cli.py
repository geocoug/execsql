"""Command-line interface for execsql.

Parses arguments, initialises global state, establishes a database
connection, loads the SQL script, and drives the main execution loop.
"""

from __future__ import annotations

import atexit
import datetime
import getpass
import os
import sys
import traceback
from pathlib import Path
from encodings.aliases import aliases as codec_dict

import typer
from rich.console import Console
from rich.table import Table

from execsql import __version__
from execsql.config import ConfigData, StatObj
from execsql.exceptions import ConfigError, ErrInfo
from execsql.script import SubVarSet, current_script_line, read_sqlfile, read_sqlstring, runscripts
from execsql.utils.fileio import FileWriter, Logger, filewriter_end
from execsql.utils.gui import gui_connect, gui_console_isrunning, gui_console_off, gui_console_on, gui_console_wait_user

_console = Console()
_err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Metacommand help text
# ---------------------------------------------------------------------------

_METACOMMANDS = [
    ("ASK", '"<question>" SUB <match_string>'),
    ("AUTOCOMMIT", "ON|OFF"),
    ("BEGIN BATCH / END BATCH / ROLLBACK BATCH", ""),
    ("BEGIN SCRIPT / END SCRIPT", ""),
    ("BEGIN SQL / END SQL", ""),
    ("CANCEL_HALT", "ON|OFF"),
    ("CD", "<directory>"),
    ("CONNECT", "<alias> [AS <alias_name>]"),
    ("COPY", "<source_file> TO <dest_file>"),
    ("DEBUG", "ON|OFF"),
    ("DEFINE SUB", "<variable> [AS] <value>"),
    ("EXPORT QUERY", "<queryname> [AS <alias>] ..."),
    ("EXPORT", "<queryname> TO <format> <filename> ..."),
    ("HALT [ON]", "ERROR|CANCEL"),
    ("IF <condition>", "/ ELSE / ENDIF"),
    ("IMPORT FILE", "<filename> [OPTIONS ...]"),
    ("IMPORT TABLE", "<tablename> FROM FILE <filename> [OPTIONS ...]"),
    ("LOOP <n> TIMES", "/ END LOOP"),
    ("LOOP WHILE <condition>", "/ END LOOP"),
    ("LOOP UNTIL <condition>", "/ END LOOP"),
    ("ON CANCEL_HALT", "..."),
    ("ON ERROR_HALT", "..."),
    ("PAUSE", "[<text>]"),
    ("PROMPT ACTION", "..."),
    ("PROMPT ENTRY_FORM", "..."),
    ("PROMPT MENU", "..."),
    ("PROMPT OPENFILE", "..."),
    ("PROMPT SAVEFILE", "..."),
    ("PROMPT DIRECTORY", "..."),
    ("PROMPT MAP", "..."),
    ("RECONNECT", ""),
    ("ROLLBACK", ""),
    ("SERVE", "<queryname> ..."),
    ("SET AUTOCOMMIT", "ON|OFF"),
    ("SHELL", "(<command>)"),
    ("SHOW WARNINGS", "ON|OFF"),
    ("SUB", "<variable> [AS] <value>"),
    ("SUB_TEMPFILE", "<variable>"),
    ("SYSTEM_CMD", "(<operating system command line>)"),
    ("TIMER", "ON|OFF"),
    ("USE", "<alias_name>"),
    ("WAIT_UNTIL", "<Boolean_expression> <HALT|CONTINUE> AFTER <n> SECONDS"),
    ("WRITE", '"<text>" [[TEE] TO <output>]'),
    ("WRITE CREATE_TABLE FROM", "<filename> [TO <output>]"),
    ("WRITE SCRIPT", "<script_name> [[APPEND] TO <output_file>]"),
    ("ZIP", "<filename> [APPEND] TO ZIPFILE <zipfilename>"),
]

_METACOMMANDS_PLAIN = """\
Metacommands are embedded in SQL comment lines following the !x! token.
See the documentation for more complete descriptions of the metacommands.
   ASK "<question>" SUB <match_string>
   AUTOCOMMIT ON|OFF
   BEGIN BATCH / END BATCH / ROLLBACK BATCH
   BEGIN SCRIPT / END SCRIPT
   BEGIN SQL / END SQL
   CANCEL_HALT ON|OFF
   CD <directory>
   CONNECT <alias> [AS <alias_name>]
   COPY <source_file> TO <dest_file>
   DEBUG ON|OFF
   DEFINE SUB <variable> [AS] <value>
   EXPORT QUERY <queryname> [AS <alias>] ...
   EXPORT <queryname> TO <format> <filename> ...
   HALT [ON] ERROR|CANCEL
   IF <condition> / ELSE / ENDIF
   IMPORT FILE <filename> [OPTIONS ...]
   IMPORT TABLE <tablename> FROM FILE <filename> [OPTIONS ...]
   LOOP <n> TIMES / END LOOP
   LOOP WHILE <condition> / END LOOP
   LOOP UNTIL <condition> / END LOOP
   ON CANCEL_HALT ...
   ON ERROR_HALT ...
   PAUSE [<text>]
   PROMPT ACTION ...
   PROMPT ENTRY_FORM ...
   PROMPT MENU ...
   PROMPT OPENFILE ...
   PROMPT SAVEFILE ...
   PROMPT DIRECTORY ...
   PROMPT MAP ...
   RECONNECT
   ROLLBACK
   SERVE <queryname> ...
   SET AUTOCOMMIT ON|OFF
   SHELL (<command>)
   SHOW WARNINGS ON|OFF
   SUB <variable> [AS] <value>
   SUB_TEMPFILE <variable>
   SYSTEM_CMD (<operating system command line>)
   TIMER ON|OFF
   USE <alias_name>
   WAIT_UNTIL <Boolean_expression> <HALT|CONTINUE> AFTER <n> SECONDS
   WRITE "<text>" [[TEE] TO <output>]
   WRITE CREATE_TABLE FROM <filename> [TO <output>]
   WRITE SCRIPT <script_name> [[APPEND] TO <output_file>]
   ZIP <filename> [APPEND] TO ZIPFILE <zipfilename>"""


def _print_metacommands() -> None:
    """Print the metacommands table using Rich."""
    table = Table(
        title="execsql Metacommands",
        caption="Embed in SQL comment lines following the [bold]!x![/bold] token.",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=False,
    )
    table.add_column("Metacommand", style="bold green", no_wrap=True)
    table.add_column("Syntax", style="white")
    for name, syntax in _METACOMMANDS:
        table.add_row(name, syntax)
    _console.print(table)


def _print_encodings() -> None:
    """Print available encodings using Rich."""
    enc = sorted(codec_dict.keys())
    table = Table(
        title="Available Encodings",
        show_header=False,
        border_style="dim",
        expand=True,
    )
    table.add_column("Encoding", style="cyan")
    # 4 columns
    cols = 4
    for i in range(0, len(enc), cols):
        row = enc[i : i + cols]
        while len(row) < cols:
            row.append("")
        table.add_row(*row)
    _console.print(table)


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
    )


# ---------------------------------------------------------------------------
# Connection-string parser
# ---------------------------------------------------------------------------

#: Mapping from URL scheme → execsql db_type code
_SCHEME_TO_DBTYPE: dict[str, str] = {
    "postgresql": "p",
    "postgres": "p",
    "mysql": "m",
    "mariadb": "m",
    "mssql": "s",
    "sqlserver": "s",
    "oracle": "o",
    "oracle+cx_oracle": "o",
    "firebird": "f",
    "sqlite": "l",
    "duckdb": "k",
}


def _parse_connection_string(dsn: str) -> dict:
    """Parse a database URL into a dict of connection parameters.

    Supports the common form::

        scheme://[user[:password]@][host[:port]]/database

    For file-based databases (SQLite, DuckDB) the path after ``//`` is
    treated as the database file path::

        sqlite:///path/to/file.db   → db_file = /path/to/file.db
        duckdb:///path/to/file.db   → db_file = /path/to/file.db

    Returns a dict with keys: ``db_type``, ``server``, ``db``, ``db_file``,
    ``user``, ``password``, ``port``.  Absent components are ``None``.

    Raises :class:`~execsql.exceptions.ConfigError` for an unrecognised
    URL scheme or a completely un-parseable string.
    """
    from urllib.parse import urlparse

    parsed = urlparse(dsn)
    scheme = parsed.scheme.lower()
    if not scheme:
        raise ConfigError(f"Cannot parse connection string (no scheme): {dsn!r}")
    if scheme not in _SCHEME_TO_DBTYPE:
        raise ConfigError(
            f"Unrecognised connection-string scheme {scheme!r}. "
            f"Supported schemes: {', '.join(sorted(_SCHEME_TO_DBTYPE))}",
        )

    db_type = _SCHEME_TO_DBTYPE[scheme]
    port: int | None = parsed.port
    server: str | None = parsed.hostname or None
    user: str | None = parsed.username or None
    password: str | None = parsed.password or None

    # Database / file path
    # urlparse puts the path in parsed.path.  For three-slash URIs like
    # sqlite:///foo.db the path starts with "/"; strip exactly one leading
    # slash for relative paths (sqlite:///foo.db → foo.db) and leave
    # absolute paths intact (sqlite:////abs/path → /abs/path).
    raw_path = parsed.path
    if db_type in ("l", "k", "a"):
        # File-based: no server component
        if raw_path.startswith("/") and not raw_path.startswith("//"):
            db_file: str | None = raw_path[1:] or None
        else:
            db_file = raw_path or None
        db: str | None = None
    else:
        db_file = None
        # Remove leading "/"
        db = raw_path.lstrip("/") or None

    return {
        "db_type": db_type,
        "server": server,
        "db": db,
        "db_file": db_file,
        "user": user,
        "password": password,
        "port": port,
    }


# ---------------------------------------------------------------------------
# Dry-run helper
# ---------------------------------------------------------------------------


def _print_dry_run(cmdlist: object) -> None:
    """Print the parsed command list for --dry-run mode."""
    if cmdlist is None or not cmdlist.cmdlist:
        _console.print("[yellow]No commands found in script.[/yellow]")
        return
    n = len(cmdlist.cmdlist)
    _console.print(f"[bold cyan]Dry Run[/bold cyan] — [dim]{n} command(s) parsed[/dim]")
    _console.print()
    for i, cmd in enumerate(cmdlist.cmdlist, 1):
        ctype = "SQL    " if cmd.command_type == "sql" else "METACMD"
        source_info = f"[dim]{cmd.source}:{cmd.line_no}[/dim]"
        _console.print(f"  [dim]{i:>4}[/dim]  [bold green]{ctype}[/bold green]  {source_info}  {cmd.commandline()}")


# ---------------------------------------------------------------------------
# Core execution (split from argument parsing for testability)
# ---------------------------------------------------------------------------


def _run(
    positional: list,
    sub_vars: list[str] | None,
    boolean_int: str | None,
    make_dirs: str | None,
    database_encoding: str | None,
    script_encoding: str | None,
    output_encoding: str | None,
    import_encoding: str | None,
    user_logfile: bool,
    new_db: bool,
    port: int | None,
    scanlines: int | None,
    db_type: str | None,
    user: str | None,
    use_gui: str | None,
    gui_framework: str | None = None,
    no_passwd: bool = False,
    import_buffer: int | None = None,
    script_name: str | None = None,
    command: str | None = None,
    dry_run: bool = False,
    dsn: str | None = None,
    output_dir: str | None = None,
) -> None:
    """Initialise state, connect to the database, load the script, and run it.

    Separated from argument parsing so it can be called directly in tests
    without going through the Typer CLI layer. All parameters mirror the
    corresponding CLI options; see [Syntax & Options](../syntax.md) for
    descriptions.
    """
    import execsql.state as _state

    # ------------------------------------------------------------------
    # Early setup: substitution variables seeded before arg parsing
    # ------------------------------------------------------------------
    _state.subvars = SubVarSet()

    for k in os.environ:
        try:
            _state.subvars.add_substitution("&" + k, os.environ[k])
        except Exception:
            pass  # Skip env vars with names that can't be substitution keys.
    _state.subvars.add_substitution("$LAST_ROWCOUNT", None)

    dt_now = datetime.datetime.now()
    dt_now_utc = datetime.datetime.now(tz=datetime.UTC)

    _state.subvars.add_substitution("$SCRIPT_START_TIME", dt_now.strftime("%Y-%m-%d %H:%M"))
    _state.subvars.add_substitution("$SCRIPT_START_TIME_UTC", dt_now_utc.strftime("%Y-%m-%d %H:%M"))
    _state.subvars.add_substitution("$DATE_TAG", dt_now.strftime("%Y%m%d"))
    _state.subvars.add_substitution("$DATETIME_TAG", dt_now.strftime("%Y%m%d_%H%M"))
    _state.subvars.add_substitution("$DATETIME_UTC_TAG", dt_now_utc.strftime("%Y%m%d_%H%M"))
    _state.subvars.add_substitution("$LAST_SQL", "")
    _state.subvars.add_substitution("$LAST_ERROR", "")
    _state.subvars.add_substitution("$ERROR_MESSAGE", "")
    _state.subvars.add_substitution("$USER", getpass.getuser())
    _state.subvars.add_substitution("$STARTING_PATH", os.getcwd() + os.sep)
    _state.subvars.add_substitution("$PATHSEP", os.sep)
    osys = sys.platform
    if osys.startswith("linux"):
        osys = "linux"
    elif osys.startswith("win"):
        osys = "windows"
    _state.subvars.add_substitution("$OS", osys)
    _state.subvars.add_substitution("$PYTHON_EXECUTABLE", sys.executable)

    # ------------------------------------------------------------------
    # Read configuration file
    # ------------------------------------------------------------------
    script_path = str(Path(script_name).resolve().parent) if script_name else os.getcwd()
    _state.conf = ConfigData(script_path, _state.subvars)
    conf = _state.conf

    # ------------------------------------------------------------------
    # Connection string (--dsn / --connection-string): overrides -t/-u/-p
    # and positional server/db args when provided.
    # ------------------------------------------------------------------
    if dsn:
        try:
            parsed_dsn = _parse_connection_string(dsn)
        except ConfigError as exc:
            _err_console.print(f"[bold red]Error:[/bold red] {exc}")
            raise SystemExit(1)
        db_type = db_type or parsed_dsn["db_type"]
        conf.db_type = db_type
        if parsed_dsn["server"] and not conf.server:
            conf.server = parsed_dsn["server"]
        if parsed_dsn["db"] and not conf.db:
            conf.db = parsed_dsn["db"]
        if parsed_dsn["db_file"] and not conf.db_file:
            conf.db_file = parsed_dsn["db_file"]
        if parsed_dsn["user"] and not user:
            user = parsed_dsn["user"]
        if parsed_dsn["password"]:
            conf.db_password = parsed_dsn["password"]
            conf.passwd_prompt = False
        if parsed_dsn["port"] and not port:
            port = parsed_dsn["port"]

    # Apply CLI options over config-file values
    if user:
        conf.username = user
    if no_passwd:
        conf.passwd_prompt = False
    if database_encoding:
        conf.db_encoding = database_encoding
    if script_encoding:
        conf.script_encoding = script_encoding
    if not conf.script_encoding:
        conf.script_encoding = "utf8"
    if output_encoding:
        conf.output_encoding = output_encoding
    if not conf.output_encoding:
        conf.output_encoding = "utf8"
    if import_encoding:
        conf.import_encoding = import_encoding
    if not conf.import_encoding:
        conf.import_encoding = "utf8"
    if import_buffer:
        conf.import_buffer = import_buffer * 1024
    if make_dirs:
        conf.make_export_dirs = make_dirs in ("1", "t", "T", "y", "Y")
    if boolean_int:
        conf.boolean_int = boolean_int in ("1", "t", "T", "y", "Y")
    if scanlines is not None:
        conf.scan_lines = scanlines
    if conf.scan_lines is None:
        conf.scan_lines = 100
    if use_gui:
        conf.gui_level = int(use_gui)
    if conf.gui_level is None:
        conf.gui_level = 0
    elif conf.gui_level not in range(4):
        raise ConfigError(f"Invalid GUI level specification: {conf.gui_level}")
    if gui_framework:
        conf.gui_framework = gui_framework.lower()
    if db_type:
        conf.db_type = db_type
    if conf.db_type is None:
        conf.db_type = "a"
    if user_logfile:
        conf.user_logfile = True
    if port:
        conf.port = port
    if conf.db_type == "a" and user:
        conf.access_username = user
    if new_db:
        conf.new_db = True
    if output_dir:
        conf.export_output_dir = str(Path(output_dir).resolve())

    # Positional arguments after the script name (or all positionals in inline mode)
    # off=1: script file occupies positional[0]; connection args start at [1]
    # off=0: no script file; all positionals are connection args
    off = 0 if command is not None else 1
    if len(positional) == off + 1:
        if conf.db_type in ("a", "l", "k"):
            conf.db_file = positional[off]
        elif conf.db_type == "d":
            conf.db = positional[off]
        else:
            if conf.server and not conf.db:
                conf.db = positional[off]
            else:
                conf.server = positional[off]
    elif len(positional) == off + 2:
        conf.server = positional[off]
        conf.db = positional[off + 1]
    elif len(positional) > off + 2:
        from execsql.utils.errors import fatal_error

        fatal_error("Incorrect number of command-line arguments.")

    # ------------------------------------------------------------------
    # Script substitution variables that depend on the script path
    # ------------------------------------------------------------------
    from execsql.utils.errors import file_size_date

    if script_name is not None:
        _state.subvars.add_substitution("$STARTING_SCRIPT", script_name)
        _state.subvars.add_substitution("$STARTING_SCRIPT_NAME", Path(script_name).name)
        _state.subvars.add_substitution("$STARTING_SCRIPT_REVTIME", file_size_date(script_name)[1])
    else:
        _state.subvars.add_substitution("$STARTING_SCRIPT", "<inline>")
        _state.subvars.add_substitution("$STARTING_SCRIPT_NAME", "<inline>")
        _state.subvars.add_substitution("$STARTING_SCRIPT_REVTIME", "")

    # ------------------------------------------------------------------
    # Initialise state objects
    # ------------------------------------------------------------------
    from execsql.metacommands import DISPATCH_TABLE
    from execsql.metacommands.conditions import CONDITIONAL_TABLE

    _state.initialize(conf, DISPATCH_TABLE, CONDITIONAL_TABLE)

    # Local-only objects that require CLI-specific args or class definitions
    _state.status = StatObj()

    from execsql.config import WriteHooks

    _state.output = WriteHooks()

    import execsql.utils.fileio as _fileio

    if _state.filewriter is None or not _state.filewriter.is_alive():
        _fileio.filewriter = _state.filewriter = FileWriter(
            _fileio.fw_input,
            _fileio.fw_output,
            file_encoding=conf.output_encoding,
            open_timeout=getattr(conf, "outfile_open_timeout", 10),
        )
        _state.filewriter.start()
        atexit.register(filewriter_end)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    opts_dict = {
        k: v
        for k, v in {
            "sub_vars": sub_vars,
            "boolean_int": boolean_int,
            "make_dirs": make_dirs,
            "database_encoding": database_encoding,
            "script_encoding": script_encoding,
            "output_encoding": output_encoding,
            "import_encoding": import_encoding,
            "user_logfile": user_logfile,
            "new_db": new_db,
            "port": port,
            "scanlines": scanlines,
            "db_type": db_type,
            "user": user,
            "use_gui": use_gui,
            "no_passwd": no_passwd,
            "import_buffer": import_buffer,
        }.items()
        if v
    }
    _state.exec_log = Logger(
        script_name or "<inline>",
        conf.db,
        conf.server,
        opts_dict,
        conf.user_logfile,
    )
    _state.exec_log.log_status_info(
        f"Python version {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} {sys.version_info[3]}",
    )
    _state.exec_log.log_status_info(f"execsql version {__version__}")
    _state.exec_log.log_status_info(f"System user: {getpass.getuser()}")
    for configfile in conf.files_read:
        sz, dt = file_size_date(configfile)
        _state.exec_log.log_status_info(
            f"Read configuration file {configfile} (size: {sz}, date: {dt}).",
        )

    _state.subvars.add_substitution("$RUN_ID", _state.exec_log.run_id)

    if sub_vars:
        for n, repl in enumerate(sub_vars):
            var = f"$ARG_{n + 1}"
            _state.subvars.add_substitution(var, repl)
            _state.exec_log.log_status_info(
                f"Command-line substitution variable assignment: {var} set to {{{repl}}}",
            )

    # ------------------------------------------------------------------
    # Load the SQL script
    # ------------------------------------------------------------------
    if command is not None:
        read_sqlstring(command.replace("\\n", "\n").replace("\\t", "\t"), "<inline>")
    else:
        read_sqlfile(script_name)

    # ------------------------------------------------------------------
    # Dry-run: print command list and exit without connecting to DB
    # ------------------------------------------------------------------
    if dry_run:
        _print_dry_run(_state.commandliststack[-1] if _state.commandliststack else None)
        raise SystemExit(0)

    # ------------------------------------------------------------------
    # Start GUI console if requested
    # ------------------------------------------------------------------
    if conf.gui_level > 2:
        gui_console_on()

    # ------------------------------------------------------------------
    # Establish database connection
    # ------------------------------------------------------------------
    if conf.server is None and conf.db is None and conf.db_file is None:
        if conf.gui_level > 1:
            gui_connect("initial", f"Select the database to use with {script_name or '<inline>'}.")
            db = _state.dbs.current()
        else:
            from execsql.utils.errors import fatal_error

            fatal_error(
                "Database not specified in configuration files or command-line arguments, and prompt not requested.",
            )
    else:
        db = _connect_initial_db(conf)
        _state.dbs.add("initial", db)

    _state.exec_log.log_db_connect(db)
    _state.subvars.add_substitution("$CURRENT_DBMS", db.type.dbms_id)
    _state.subvars.add_substitution("$CURRENT_DATABASE", db.name())
    _state.subvars.add_substitution("$DB_SERVER", db.server_name)
    _state.subvars.add_substitution("$SYSTEM_CMD_EXIT_STATUS", "0")

    # ------------------------------------------------------------------
    # Execute the script
    # ------------------------------------------------------------------
    atexit.register(_state.dbs.closeall)
    _state.dbs.do_rollback = True

    _execute_script_direct(conf)


# ---------------------------------------------------------------------------
# Script execution helpers
# ---------------------------------------------------------------------------


def _execute_script_textual_console(conf: ConfigData) -> None:
    """Run the script in a background thread while ConsoleApp runs in the main thread."""
    import execsql.state as _state
    import execsql.utils.gui as _gui
    from execsql.gui.tui import ConsoleApp, _ConsoleDialogQueue

    dialog_queue = _ConsoleDialogQueue()
    _state.gui_manager_queue = dialog_queue

    app = ConsoleApp(
        script_runner=runscripts,
        dialog_queue=dialog_queue,
        wait_on_exit=conf.gui_wait_on_exit,
    )
    _state.output.redir_stdout(app.write_console)
    _state.output.redir_stderr(app.write_console)
    _gui._active_backend._console_app = app

    try:
        app.run()
    finally:
        _state.output.reset()
        _gui._active_backend._console_app = None

    if app._script_exception is not None:
        exc = app._script_exception
        if isinstance(exc, SystemExit):
            _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
            sys.exit(exc.code)
        elif isinstance(exc, ConfigError):
            raise exc
        elif isinstance(exc, ErrInfo):
            from execsql.utils.errors import exit_now

            exit_now(1, exc)
        else:
            strace = traceback.extract_tb(exc.__traceback__)[-1:]
            lno = strace[0][1] if strace else "?"
            msg = f"{Path(sys.argv[0]).name}: Uncaught exception {type(exc)} ({exc}) on line {lno}"
            script, slno = current_script_line()
            if script is not None:
                msg += f" in script {script}, line {slno}"
            from execsql.utils.errors import exit_now

            exit_now(1, ErrInfo("exception", exception_msg=msg))

    _state.dbs.do_rollback = False
    _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
    _state.exec_log.log_exit_end()


def _execute_script_direct(conf: ConfigData) -> None:
    """Run runscripts() in the current (main) thread — used when Textual is not active."""
    import execsql.state as _state
    import execsql.utils.gui as _gui

    # For Textual + gui_level 3, use the persistent ConsoleApp architecture.
    if conf.gui_level > 2:
        try:
            from execsql.gui.tui import TextualBackend

            if isinstance(_gui._active_backend, TextualBackend):
                _execute_script_textual_console(conf)
                return
        except ImportError:
            pass

    try:
        runscripts()
    except SystemExit as exc:
        if gui_console_isrunning() and conf.gui_wait_on_exit:
            gui_console_wait_user(
                "Script complete; close the console window to exit execsql.",
            )
            if gui_console_isrunning():
                gui_console_off()
        _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
        sys.exit(exc.code)
    except ConfigError:
        raise
    except ErrInfo as exc:
        from execsql.utils.errors import exit_now

        exit_now(1, exc)
    except Exception:
        strace = traceback.extract_tb(sys.exc_info()[2])[-1:]
        lno = strace[0][1]
        msg = f"{Path(sys.argv[0]).name}: Uncaught exception {sys.exc_info()[0]} ({sys.exc_info()[1]}) on line {lno}"
        script, slno = current_script_line()
        if script is not None:
            msg += f" in script {script}, line {slno}"
        from execsql.utils.errors import exit_now

        exit_now(1, ErrInfo("exception", exception_msg=msg))

    _state.dbs.do_rollback = False
    if gui_console_isrunning() and conf.gui_wait_on_exit:
        gui_console_wait_user(
            "Script complete; close the console window to exit execsql.",
        )
        if gui_console_isrunning():
            gui_console_off()
    _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
    _state.exec_log.log_exit_end()


# ---------------------------------------------------------------------------
# Utility: build the database connection for the initial/default database
# ---------------------------------------------------------------------------


def _connect_initial_db(conf: ConfigData):
    """Create and return the initial database object based on conf.db_type."""
    from execsql.db.factory import (
        db_Access,
        db_Postgres,
        db_SQLite,
        db_SqlServer,
        db_MySQL,
        db_DuckDB,
        db_Oracle,
        db_Firebird,
        db_Dsn,
    )

    if conf.db_type == "a":
        if conf.db_file is None:
            from execsql.utils.errors import fatal_error

            fatal_error("Configured to run with MS-Access, but no Access file name is provided.")
        return db_Access(
            conf.db_file,
            pw_needed=conf.passwd_prompt and conf.access_username is not None,
            user=conf.access_username,
            encoding=conf.db_encoding,
        )
    elif conf.db_type == "p":
        return db_Postgres(
            conf.server,
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            port=conf.port,
            encoding=conf.db_encoding,
            new_db=conf.new_db,
            password=getattr(conf, "db_password", None),
        )
    elif conf.db_type == "s":
        return db_SqlServer(
            conf.server,
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            port=conf.port,
            encoding=conf.db_encoding,
        )
    elif conf.db_type == "l":
        if conf.db_file is None:
            from execsql.utils.errors import fatal_error

            fatal_error("Configured to run with SQLite, but no SQLite file name is provided.")
        return db_SQLite(conf.db_file, new_db=conf.new_db, encoding=conf.db_encoding)
    elif conf.db_type == "m":
        return db_MySQL(
            conf.server,
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            port=conf.port,
            encoding=conf.db_encoding,
        )
    elif conf.db_type == "k":
        if conf.db_file is None:
            from execsql.utils.errors import fatal_error

            fatal_error("Configured to run with DuckDB, but no DuckDB file name is provided.")
        return db_DuckDB(conf.db_file, new_db=conf.new_db, encoding=conf.db_encoding)
    elif conf.db_type == "o":
        return db_Oracle(
            conf.server,
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            port=conf.port,
            encoding=conf.db_encoding,
        )
    elif conf.db_type == "f":
        return db_Firebird(
            conf.server,
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            port=conf.port,
            encoding=conf.db_encoding,
        )
    elif conf.db_type == "d":
        return db_Dsn(
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            encoding=conf.db_encoding,
        )
    else:
        from execsql.utils.errors import fatal_error

        fatal_error(f"Unknown database type: '{conf.db_type}'")


# ---------------------------------------------------------------------------
# Legacy entry point (kept for backwards compat with pyproject.toml script)
# ---------------------------------------------------------------------------


def _legacy_main() -> None:
    """Entry point that wraps the Typer app for use as a console_scripts target."""
    try:
        app()
    except SystemExit as exc:
        raise exc
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
