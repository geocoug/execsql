"""Core execution logic for the execsql CLI.

Initialises global state, connects to the database, loads the SQL script,
and drives the main execution loop.  Separated from argument parsing
(``cli/__init__.py``) for testability and maintainability.
"""

from __future__ import annotations

import atexit
from typing import Any
import datetime
import getpass
import os
import platform
import sys
import traceback
from pathlib import Path

from execsql import __version__
from execsql.cli.dsn import _parse_connection_string
from execsql.cli.help import _console, _err_console
from execsql.config import ConfigData, StatObj
from execsql.exceptions import ConfigError, ErrInfo
from execsql.script import SubVarSet, current_script_line, substitute_vars
from execsql.utils.fileio import FileWriter, Logger, filewriter_end
from execsql.utils.gui import gui_connect, gui_console_isrunning, gui_console_off, gui_console_on, gui_console_wait_user

__all__ = ["_connect_initial_db", "_ping_db", "_print_dry_run", "_print_profile", "_run"]

# Lint helper — imported lazily inside _run() to keep start-up cost low, but
# re-exported here so that tests and callers can reach it via cli.run.
from execsql.cli.lint import _print_lint_results  # noqa: F401 — re-export (used by cli/__init__.py)


# ---------------------------------------------------------------------------
# Dry-run helper
# ---------------------------------------------------------------------------


def _print_dry_run(tree: object) -> None:
    """Print the parsed AST for --dry-run mode.

    Walks the AST tree and prints each SQL statement and metacommand with
    source location. Variables already populated at parse time are expanded;
    execution-time variables remain unexpanded.
    """
    from execsql.script.ast import MetaCommandStatement, SqlStatement

    if tree is None:
        _console.print("[yellow]No commands found in script.[/yellow]")
        return
    nodes = list(tree.walk())
    # Count only executable nodes (SQL and metacommands)
    executable = [n for n in nodes if isinstance(n, (SqlStatement, MetaCommandStatement))]
    if not executable:
        _console.print("[yellow]No commands found in script.[/yellow]")
        return
    _console.print(f"[bold cyan]Dry Run[/bold cyan] — [dim]{len(executable)} command(s) parsed[/dim]")
    _console.print()
    for i, node in enumerate(executable, 1):
        if isinstance(node, SqlStatement):
            ctype = "SQL    "
            raw = node.text
        else:
            ctype = "METACMD"
            raw = "-- !x! " + node.command
        source_info = f"[dim]{node.span.file}:{node.span.start_line}[/dim]"
        try:
            expanded = substitute_vars(raw)
        except Exception:
            expanded = raw
        _console.print(f"  [dim]{i:>4}[/dim]  [bold green]{ctype}[/bold green]  {source_info}  {expanded}")


# ---------------------------------------------------------------------------
# Profile report helper
# ---------------------------------------------------------------------------


def _print_profile(profile_data: list[tuple], limit: int = 20) -> None:
    """Print a per-statement timing summary to stdout.

    Args:
        profile_data: List of ``(source, line_no, command_type, elapsed_secs,
            command_text_preview)`` tuples collected during execution.
        limit: Maximum number of top statements to display (default: 20).
            All statements are included in totals regardless of this value.
    """
    if not profile_data:
        _console.print("[dim]Profile: no statements recorded.[/dim]")
        return

    total_secs = sum(row[3] for row in profile_data)
    n = len(profile_data)

    # Sort descending by elapsed time; show top `limit` (or all if <= limit).
    sorted_data = sorted(profile_data, key=lambda r: r[3], reverse=True)
    display = sorted_data[:limit]

    _console.print()
    _console.print(f"[bold cyan]Profile:[/bold cyan] {n} statement{'s' if n != 1 else ''} in {total_secs:.3f}s")
    _console.print()

    header = f"  {'Time (s)':<10}  {'Pct':<7}  {'Source:Line':<20}  {'Type':<7}  Command"
    sep = f"  {'-' * 10}  {'-' * 7}  {'-' * 20}  {'-' * 7}  {'-' * 40}"
    _console.print(f"[dim]{header}[/dim]")
    _console.print(f"[dim]{sep}[/dim]")

    for source, line_no, command_type, elapsed, preview in display:
        pct = (elapsed / total_secs * 100) if total_secs > 0 else 0.0
        source_col = f"{source}:{line_no}"
        if len(source_col) > 20:
            source_col = "..." + source_col[-17:]
        ctype_label = "SQL    " if command_type == "sql" else "METACMD"
        preview_short = preview[:50].replace("\n", " ").strip()
        if len(preview) > 50:
            preview_short += "..."
        _console.print(
            f"  [yellow]{elapsed:<10.3f}[/yellow]  "
            f"[dim]{pct:<6.1f}%[/dim]  "
            f"[cyan]{source_col:<20}[/cyan]  "
            f"[green]{ctype_label:<7}[/green]  "
            f"{preview_short}",
        )

    if len(sorted_data) > limit:
        omitted = len(sorted_data) - limit
        _console.print(
            f"[dim]  ... {omitted} more statement{'s' if omitted != 1 else ''} not shown (top {limit} by time)[/dim]",
        )

    _console.print()


# ---------------------------------------------------------------------------
# --ping helper
# ---------------------------------------------------------------------------


def _ping_db(db: Any) -> None:
    """Test connectivity for *db*, print connection details, and exit.

    Attempts to execute ``SELECT version()`` (or ``SELECT sqlite_version()``
    for SQLite) to retrieve the server version string.  If the query fails the
    connection is still reported as successful — only the version line is
    omitted.  On success the function raises :class:`SystemExit` with code 0.

    Args:
        db: An open :class:`~execsql.db.base.Database` instance.
    """
    dbms_id: str = db.type.dbms_id if db.type else "unknown"

    # Try to fetch a human-readable server version string.
    version_str: str | None = None
    _version_queries = [
        "SELECT version()",
        "SELECT sqlite_version()",
        "SELECT @@VERSION",
    ]
    for sql in _version_queries:
        try:
            curs = db.cursor()
            curs.execute(sql)
            row = curs.fetchone()
            curs.close()
            if row and row[0]:
                version_str = str(row[0]).split("\n")[0].strip()
                break
        except Exception:
            continue

    # Build the connection descriptor.
    if db.server_name:
        port_part = f":{db.port}" if db.port else ""
        location = f"{db.server_name}{port_part}/{db.db_name or ''}"
    else:
        location = db.db_name or "<in-memory>"

    if version_str:
        _console.print(
            f"[bold green]Connected[/bold green] to [bold]{dbms_id}[/bold] "
            f"[dim]{version_str}[/dim] at [cyan]{location}[/cyan]",
        )
    else:
        _console.print(
            f"[bold green]Connected[/bold green] to [bold]{dbms_id}[/bold] at [cyan]{location}[/cyan]",
        )

    db.close()
    raise SystemExit(0)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Extracted phases — pure computation, no global state coupling
# ---------------------------------------------------------------------------


def _seed_early_subvars() -> SubVarSet:
    """Create and populate the initial substitution variable pool.

    Seeds environment variables (filtering secrets), timestamps, system info,
    and placeholder variables.  Called once at the start of :func:`_run`.
    """
    subvars = SubVarSet()

    _SENSITIVE_SUBSTRINGS = ("SECRET", "TOKEN", "PASSWORD", "PASSWD", "PRIVATE_KEY", "CREDENTIAL")
    for k in os.environ:
        if any(s in k.upper() for s in _SENSITIVE_SUBSTRINGS):
            continue
        try:
            subvars.add_substitution("&" + k, os.environ[k])
        except Exception:
            pass  # Skip env vars with names that can't be substitution keys.
    subvars.add_substitution("$LAST_ROWCOUNT", None)

    dt_now = datetime.datetime.now()
    dt_now_utc = datetime.datetime.now(tz=datetime.timezone.utc)

    subvars.add_substitution("$SCRIPT_START_TIME", dt_now.strftime("%Y-%m-%d %H:%M"))
    subvars.add_substitution("$SCRIPT_START_TIME_UTC", dt_now_utc.strftime("%Y-%m-%d %H:%M"))
    subvars.add_substitution("$DATE_TAG", dt_now.strftime("%Y%m%d"))
    subvars.add_substitution("$DATETIME_TAG", dt_now.strftime("%Y%m%d_%H%M"))
    subvars.add_substitution("$DATETIME_UTC_TAG", dt_now_utc.strftime("%Y%m%d_%H%M"))
    subvars.add_substitution("$LAST_SQL", "")
    subvars.add_substitution("$LAST_ERROR", "")
    subvars.add_substitution("$ERROR_MESSAGE", "")
    subvars.add_substitution("$USER", getpass.getuser())
    subvars.add_substitution("$STARTING_PATH", os.getcwd() + os.sep)
    subvars.add_substitution("$PATHSEP", os.sep)
    osys = sys.platform
    if osys.startswith("linux"):
        osys = "linux"
    elif osys.startswith("win"):
        osys = "windows"
    subvars.add_substitution("$OS", osys)
    subvars.add_substitution("$HOSTNAME", platform.node())
    subvars.add_substitution("$PYTHON_EXECUTABLE", sys.executable)
    return subvars


def _load_config(
    script_name: str | None,
    subvars: SubVarSet,
    config_file: str | None,
) -> ConfigData:
    """Load and merge configuration files for the given script.

    Returns a fully populated :class:`ConfigData` instance.
    """
    script_path = str(Path(script_name).resolve().parent) if script_name else os.getcwd()
    return ConfigData(script_path, subvars, config_file=config_file)


def _seed_script_subvars(subvars: SubVarSet, script_name: str | None) -> None:
    """Add substitution variables that depend on the script path."""
    from execsql.utils.errors import file_size_date

    if script_name is not None:
        subvars.add_substitution("$STARTING_SCRIPT", script_name)
        subvars.add_substitution("$STARTING_SCRIPT_NAME", Path(script_name).name)
        subvars.add_substitution("$STARTING_SCRIPT_REVTIME", file_size_date(script_name)[1])
    else:
        subvars.add_substitution("$STARTING_SCRIPT", "<inline>")
        subvars.add_substitution("$STARTING_SCRIPT_NAME", "<inline>")
        subvars.add_substitution("$STARTING_SCRIPT_REVTIME", "")


def _load_script(
    command: str | None,
    script_name: str | None,
    encoding: str,
) -> Any:
    """Parse the SQL script (or inline command) into an AST.

    Returns the AST tree, or ``None`` if no script is provided.
    """
    from execsql.script.parser import parse_script, parse_string

    if command is not None:
        return parse_string(
            command.replace("\\n", "\n").replace("\\t", "\t"),
            "<inline>",
        )
    return parse_script(script_name, encoding=encoding)


def _apply_dsn(dsn: str, conf: ConfigData, db_type: str | None) -> tuple[str | None, str | None, int | None]:
    """Parse a DSN connection string and apply overrides to *conf*.

    Returns ``(db_type, user_override, port_override)`` — values extracted
    from the DSN that must also be applied to CLI-level variables in the
    caller.
    """
    try:
        parsed = _parse_connection_string(dsn)
    except ConfigError as exc:
        _err_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None
    db_type = db_type or parsed["db_type"]
    conf.db_type = db_type
    if parsed["server"]:
        conf.server = parsed["server"]
    if parsed["db"]:
        conf.db = parsed["db"]
    if parsed["db_file"]:
        conf.db_file = parsed["db_file"]
    user = parsed["user"]  # may be None
    if parsed["password"]:
        conf.db_password = parsed["password"]
        conf.passwd_prompt = False
    port = parsed["port"]  # may be None
    return db_type, user, port


def _apply_cli_options(
    conf: ConfigData,
    *,
    user: str | None,
    no_passwd: bool,
    database_encoding: str | None,
    script_encoding: str | None,
    output_encoding: str | None,
    import_encoding: str | None,
    import_buffer: int | None,
    make_dirs: str | None,
    boolean_int: str | None,
    scanlines: int | None,
    use_gui: str | None,
    gui_framework: str | None,
    db_type: str | None,
    user_logfile: bool,
    port: int | None,
    new_db: bool,
    output_dir: str | None,
    progress: bool,
) -> None:
    """Merge CLI flags into *conf*, overriding config-file values."""
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
        conf.db_type = "l"
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
    if progress:
        conf.show_progress = True


def _route_positionals(
    positional: list,
    conf: ConfigData,
    *,
    command: str | None,
    ping: bool,
) -> None:
    """Apply remaining positional CLI arguments to *conf* as server/db/db_file."""
    off = 0 if (command is not None or ping) else 1
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


def _setup_logging(
    conf: ConfigData,
    subvars: SubVarSet,
    script_name: str | None,
    sub_vars: list[str] | None,
    *,
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
    no_passwd: bool,
    import_buffer: int | None,
) -> Logger:
    """Create the execution logger, log initial info, and seed ``$RUN_ID``."""
    from execsql.utils.errors import file_size_date

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
    logger = Logger(
        script_name or "<inline>",
        conf.db,
        conf.server,
        opts_dict,
        conf.user_logfile,
    )
    logger.log_status_info(
        f"Python version {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} {sys.version_info[3]}",
    )
    logger.log_status_info(f"execsql version {__version__}")
    logger.log_status_info(f"System user: {getpass.getuser()}")
    for configfile in conf.files_read:
        sz, dt = file_size_date(configfile)
        logger.log_status_info(
            f"Read configuration file {configfile} (size: {sz}, date: {dt}).",
        )

    subvars.add_substitution("$RUN_ID", logger.run_id)

    if sub_vars:
        for n, repl in enumerate(sub_vars):
            var = f"$ARG_{n + 1}"
            subvars.add_substitution(var, repl)
            logger.log_status_info(
                f"Command-line substitution variable assignment: {var} set to {{{repl}}}",
            )

    return logger


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
    progress: bool = False,
    profile: bool = False,
    profile_limit: int = 20,
    ping: bool = False,
    lint: bool = False,
    debug: bool = False,
    config_file: str | None = None,
) -> None:
    """Initialise state, connect to the database, load the script, and run it.

    Separated from argument parsing so it can be called directly in tests
    without going through the Typer CLI layer. All parameters mirror the
    corresponding CLI options; see [Syntax & Options](../syntax.md) for
    descriptions.

    When *ping* is ``True``, the function connects to the database, prints
    connection details (DBMS name, server version, and location), and calls
    :func:`_ping_db` which raises ``SystemExit(0)``.  No script is loaded or
    executed.  *script_name* and *command* may both be ``None`` in ping mode.

    When *lint* is ``True``, the script is parsed and statically analysed for
    structural issues (unmatched IF/ENDIF/LOOP/BATCH blocks, potentially
    undefined variables, missing INCLUDE files, empty scripts) without
    connecting to a database or executing anything.  Exits with code 0 if no
    errors were found, or code 1 if errors were found.
    """
    import execsql.state as _state

    # ------------------------------------------------------------------
    # Early setup: substitution variables seeded before config loading
    # ------------------------------------------------------------------
    _state.subvars = _seed_early_subvars()

    # ------------------------------------------------------------------
    # Read configuration file
    # ------------------------------------------------------------------
    _state.conf = _load_config(script_name, _state.subvars, config_file)
    conf = _state.conf

    # ------------------------------------------------------------------
    # Connection string (--dsn / --connection-string): overrides -t/-u/-p
    # and positional server/db args when provided.
    # ------------------------------------------------------------------
    if dsn:
        db_type, dsn_user, dsn_port = _apply_dsn(dsn, conf, db_type)
        if dsn_user:
            user = dsn_user
        if dsn_port:
            port = dsn_port

    # ------------------------------------------------------------------
    # Merge CLI options over config-file values
    # ------------------------------------------------------------------
    _apply_cli_options(
        conf,
        user=user,
        no_passwd=no_passwd,
        database_encoding=database_encoding,
        script_encoding=script_encoding,
        output_encoding=output_encoding,
        import_encoding=import_encoding,
        import_buffer=import_buffer,
        make_dirs=make_dirs,
        boolean_int=boolean_int,
        scanlines=scanlines,
        use_gui=use_gui,
        gui_framework=gui_framework,
        db_type=db_type,
        user_logfile=user_logfile,
        port=port,
        new_db=new_db,
        output_dir=output_dir,
        progress=progress,
    )

    # ------------------------------------------------------------------
    # Positional arguments → server/db/db_file
    # ------------------------------------------------------------------
    _route_positionals(positional, conf, command=command, ping=ping)

    # ------------------------------------------------------------------
    # Script substitution variables that depend on the script path
    # ------------------------------------------------------------------
    _seed_script_subvars(_state.subvars, script_name)

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
    _state.exec_log = _setup_logging(
        conf,
        _state.subvars,
        script_name,
        sub_vars,
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
        no_passwd=no_passwd,
        import_buffer=import_buffer,
    )

    # ------------------------------------------------------------------
    # Load the SQL script (skipped in --ping mode)
    # ------------------------------------------------------------------
    _ast_tree = None if ping else _load_script(command, script_name, conf.script_encoding)

    # ------------------------------------------------------------------
    # Dry-run: print command list and exit without connecting to DB
    # ------------------------------------------------------------------
    if dry_run:
        _print_dry_run(_ast_tree)
        raise SystemExit(0)

    # ------------------------------------------------------------------
    # NOTE: --lint is handled as an early exit in cli/__init__.py (AST
    # linter) before _run() is called.  No lint code path here.
    # ------------------------------------------------------------------

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
    # --ping: report connection details and exit (no script executed)
    # ------------------------------------------------------------------
    if ping:
        _ping_db(db)  # raises SystemExit(0) on success

    # ------------------------------------------------------------------
    # Execute the script
    # ------------------------------------------------------------------
    atexit.register(_state.dbs.closeall)
    _state.dbs.do_rollback = True

    if profile:
        _state.profile_data = []

    if debug:
        _state.step_mode = True

    if _ast_tree is not None:
        _execute_script_ast(_ast_tree, conf, profile=profile, profile_limit=profile_limit)


# ---------------------------------------------------------------------------
# Script execution helpers
# ---------------------------------------------------------------------------


def _execute_script_ast(
    tree: Any,
    conf: ConfigData,
    *,
    profile: bool = False,
    profile_limit: int = 20,
) -> None:
    """Execute a script using the AST executor."""
    import execsql.state as _state
    import execsql.utils.gui as _gui

    from execsql.script.executor import execute

    # For Textual + gui_level 3, run in background thread with ConsoleApp.
    if conf.gui_level > 2:
        try:
            from execsql.gui.tui import TextualBackend

            if isinstance(_gui._active_backend, TextualBackend):
                _execute_script_textual_console(tree, conf)
                return
        except ImportError:
            pass

    try:
        execute(tree)
    except SystemExit as exc:
        if gui_console_isrunning() and conf.gui_wait_on_exit:
            gui_console_wait_user(
                "Script complete; close the console window to exit execsql.",
            )
            if gui_console_isrunning():
                gui_console_off()
        _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
        if profile and _state.profile_data is not None:
            _print_profile(_state.profile_data, limit=profile_limit)
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
    if profile and _state.profile_data is not None:
        _print_profile(_state.profile_data, limit=profile_limit)
    _state.exec_log.log_exit_end()


def _execute_script_textual_console(tree: Any, conf: ConfigData) -> None:
    """Run the script in a background thread while ConsoleApp runs in the main thread."""
    import execsql.state as _state
    import execsql.utils.gui as _gui
    from execsql.gui.tui import ConsoleApp, _ConsoleDialogQueue

    from execsql.script.executor import execute

    dialog_queue = _ConsoleDialogQueue()
    _state.gui_manager_queue = dialog_queue

    app = ConsoleApp(
        script_runner=lambda: execute(tree),
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


# ---------------------------------------------------------------------------
# Utility: build the database connection for the initial/default database
# ---------------------------------------------------------------------------


def _connect_initial_db(conf: ConfigData):
    """Create and return the initial database object based on conf.db_type."""
    from execsql.db.factory import (
        db_Access,
        db_Dsn,
        db_DuckDB,
        db_Firebird,
        db_MySQL,
        db_Oracle,
        db_Postgres,
        db_SQLite,
        db_SqlServer,
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
            password=getattr(conf, "db_password", None),
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
            password=getattr(conf, "db_password", None),
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
            password=getattr(conf, "db_password", None),
        )
    elif conf.db_type == "f":
        return db_Firebird(
            conf.server,
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            port=conf.port,
            encoding=conf.db_encoding,
            password=getattr(conf, "db_password", None),
        )
    elif conf.db_type == "d":
        return db_Dsn(
            conf.db,
            user=conf.username,
            pw_needed=conf.passwd_prompt,
            encoding=conf.db_encoding,
            password=getattr(conf, "db_password", None),
        )
    else:
        from execsql.utils.errors import fatal_error

        fatal_error(f"Unknown database type: '{conf.db_type}'")
