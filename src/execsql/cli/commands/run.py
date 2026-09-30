"""The ``run`` command: execute one script against a database."""

from __future__ import annotations

from pathlib import Path

import typer

from execsql.cli.application import ExecsqlCommand, _online_help_callback, _version_callback, app
from execsql.cli.help import (
    _console,
    _err_console,
    _init_config,
    _print_encodings,
    _print_keywords_json,
    _print_metacommands,
    _print_plugins,
)
from execsql.cli.options import (
    ConfigFileOpt,
    DbTypeOpt,
    DsnOpt,
    NoPasswdOpt,
    PortOpt,
    ScriptEncodingOpt,
    UserOpt,
)
from execsql.cli.run import _run
from execsql.exceptions import ErrInfo

__all__ = ["main"]


@app.command(
    cls=ExecsqlCommand,
    name="run",
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
    # -- Connection --------------------------------------------------------
    db_type: DbTypeOpt = None,
    dsn: DsnOpt = None,
    user: UserOpt = None,
    port: PortOpt = None,
    no_passwd: NoPasswdOpt = False,
    new_db: bool = typer.Option(
        False,
        "-n",
        "--new-db",
        help="Create a new SQLite or Postgres database if it does not exist.",
    ),
    # -- Encoding ----------------------------------------------------------
    database_encoding: str | None = typer.Option(
        None,
        "-e",
        "--database-encoding",
        help="Character encoding used in the database.",
    ),
    script_encoding: ScriptEncodingOpt = None,
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
    # -- Import/Export -----------------------------------------------------
    import_buffer: int | None = typer.Option(
        None,
        "-z",
        "--import-buffer",
        metavar="KB",
        help="Import buffer size in KB. Default: 32",
    ),
    scanlines: int | None = typer.Option(
        None,
        "-s",
        "--scan-lines",
        metavar="N",
        help="Lines to scan for IMPORT format detection. 0 = scan entire file.",
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
        help="Auto-create directories for EXPORT metacommand. n=no (default), y=yes",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        metavar="DIR",
        help=(
            "Default base directory for EXPORT output files. "
            "Relative paths in EXPORT metacommands are joined to this directory. "
            "Absolute paths and stdout are unaffected."
        ),
    ),
    progress: bool = typer.Option(
        False,
        "--progress",
        help="Show a progress bar for long-running IMPORT operations.",
    ),
    # -- Execution ---------------------------------------------------------
    command: str | None = typer.Option(
        None,
        "-c",
        "--command",
        metavar="SCRIPT",
        help=(
            "Execute an inline SQL/metacommand script string instead of a script file. "
            "Use shell $'line1\\nline2' syntax for multi-line scripts."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Parse the script and print the command list without connecting to a database or executing anything.",
    ),
    # Removed: `execsql lint` replaces it. Still declared so the flag is
    # refused with a pointer instead of Click's generic "no such option".
    lint: bool = typer.Option(False, "--lint", hidden=True),
    parse_tree: bool = typer.Option(
        False,
        "--parse-tree",
        help=(
            "Parse the script into an abstract syntax tree and print the tree structure. "
            "Does not connect to a database or execute anything."
        ),
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Start in step-through debug mode. The debug REPL pauses before each statement.",
    ),
    no_system_cmd: bool = typer.Option(
        False,
        "--no-system-cmd",
        help="Disable the SYSTEM_CMD (SHELL) metacommand. Scripts that use SHELL will fail with an error.",
    ),
    no_rm_file: bool = typer.Option(
        False,
        "--no-rm-file",
        help="Disable the RM_FILE metacommand. Scripts that try to delete files will fail with an error.",
    ),
    no_serve: bool = typer.Option(
        False,
        "--no-serve",
        help="Disable the SERVE metacommand. Scripts that try to stream a file to stdout will fail with an error.",
    ),
    profile: bool = typer.Option(
        False,
        "--profile",
        help="Record per-statement execution times and print a timing summary after the script completes.",
    ),
    profile_limit: int = typer.Option(
        20,
        "--profile-limit",
        help="Number of top statements to show in the --profile timing summary (default: 20).",
    ),
    # -- GUI ---------------------------------------------------------------
    use_gui: str | None = typer.Option(
        None,
        "-v",
        "--visible-prompts",
        metavar="{0,1,2,3}",
        help=(
            "GUI level: 0=none (default), 1=GUI for password/pause, "
            "2=GUI for password/pause + DB selection, 3=full GUI console."
        ),
    ),
    gui_framework: str | None = typer.Option(
        None,
        "--gui-framework",
        metavar="{tkinter,textual}",
        help="GUI framework to use with --visible-prompts. Default: tkinter",
    ),
    # -- Configuration -----------------------------------------------------
    config_file: ConfigFileOpt = None,
    init_config: bool = typer.Option(False, "--init-config", hidden=True),  # alias: execsql config --init
    sub_vars: list[str] | None = typer.Option(
        None,
        "-a",
        "--assign-arg",
        metavar="VALUE",
        help="Define the replacement string for a substitution variable $ARG_x.",
    ),
    named_vars: list[str] | None = typer.Option(
        None,
        "--var",
        metavar="NAME=VALUE",
        help=(
            "Set the substitution variable !!NAME!!, as a [variables] entry in a config file would; "
            "it wins over config files, and a SUB in the script can reassign it. Repeatable."
        ),
    ),
    manifest_path: str | None = typer.Option(
        None,
        "--manifest",
        metavar="FILE",
        help=(
            "Write a JSON record of the run to FILE when it ends, even if it fails: script, database, "
            "statement counts, files read, written and deleted, connections, errors. No values or passwords."
        ),
    ),
    user_logfile: bool = typer.Option(
        False,
        "-l",
        "--user-logfile",
        help="Write a log file to ~/execsql.log.",
    ),
    # -- Hidden aliases of `execsql list ...`; -m and -y are upstream flags.
    metacommands: bool = typer.Option(False, "-m", "--metacommands", hidden=True),  # list metacommands
    encodings: bool = typer.Option(False, "-y", "--encodings", hidden=True),  # list encodings
    dump_keywords: bool = typer.Option(False, "--dump-keywords", hidden=True),  # list keywords --output-format json
    list_plugins: bool = typer.Option(False, "--list-plugins", hidden=True),  # list plugins
    ping: bool = typer.Option(
        False,
        "--ping",
        help=(
            "Test database connectivity and exit. Prints connection details and the server version on success "
            "(exit 0), or the error message on failure (exit 1). No script file is required."
        ),
    ),
    # The global options again, hidden. Upstream's optparse accepted them
    # anywhere, so `execsql script.sql db --version` still has to print the
    # version rather than read "--version" as a database name.
    _online_help: bool = typer.Option(
        False,
        "-o",
        "--online-help",
        callback=_online_help_callback,
        is_eager=True,
        hidden=True,
    ),
    _version: bool | None = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        hidden=True,
    ),
) -> None:
    """Run a script against a database.

    Positional arguments after the script file:

    Client-server databases:
      execsql run script.sql [SERVER] [DATABASE]

    File-based databases (SQLite, DuckDB, Access):
      execsql run script.sql [DATABASE_FILE]

    execsql script.sql ... (without run) is the same command.
    """
    if lint:
        _err_console.print("[bold red]Error:[/bold red] run --lint was removed; use execsql lint")
        raise typer.Exit(code=2)

    # ------------------------------------------------------------------
    # Information flags and the --init-config alias (no script file needed)
    # ------------------------------------------------------------------
    if metacommands:
        _print_metacommands()
        raise typer.Exit()

    if encodings:
        _print_encodings()
        raise typer.Exit()

    if init_config:
        _init_config()
        raise typer.Exit()

    if dump_keywords:
        _print_keywords_json()
        raise typer.Exit()

    if list_plugins:
        _print_plugins()
        raise typer.Exit()

    parsed_vars = _parse_named_vars(named_vars)

    if config_file and not Path(config_file).is_file():
        _err_console.print(
            f"[bold red]Error:[/bold red] Config file {config_file!r} does not exist.",
        )
        raise typer.Exit(code=2)

    positional = args or []
    if command is not None:
        script_name = None  # inline mode — no script file
    elif ping:
        # --ping does not require a script file; positional args are still
        # available for server/db arguments if --dsn is not used.
        script_name = None
    else:
        if not positional:
            _err_console.print(
                "[bold red]Error:[/bold red] No SQL script file specified. Use -c to run an inline script.",
            )
            raise typer.Exit(code=1)
        script_name = positional[0]
        if not Path(script_name).exists():
            _err_console.print(
                f'[bold red]Error:[/bold red] SQL script file "{script_name}" does not exist.',
            )
            raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Validate positional args and db_type choice
    # ------------------------------------------------------------------

    if db_type and db_type not in ("a", "d", "p", "s", "l", "m", "k", "o", "f"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid database type {db_type!r}. Choose from: a, d, p, s, l, m, k, o, f",
        )
        raise typer.Exit(code=2)

    if use_gui and use_gui not in ("0", "1", "2", "3"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid GUI level {use_gui!r}. Choose from: 0, 1, 2, 3",
        )
        raise typer.Exit(code=2)

    if gui_framework and gui_framework.lower() not in ("tkinter", "textual"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid GUI framework {gui_framework!r}. Choose from: tkinter, textual",
        )
        raise typer.Exit(code=2)

    if boolean_int and boolean_int.lower() not in ("0", "1", "t", "f", "y", "n"):
        _err_console.print(
            f"[bold red]Error:[/bold red] Invalid --boolean-int value {boolean_int!r}.",
        )
        raise typer.Exit(code=2)

    # ------------------------------------------------------------------
    # Parse tree: parse script into AST and print tree structure
    # ------------------------------------------------------------------
    if parse_tree:
        from execsql.script.ast import format_tree
        from execsql.script.parser import parse_script, parse_string

        try:
            if command is not None:
                tree = parse_string(command.replace("\\n", "\n").replace("\\t", "\t"), "<inline>")
            elif script_name is not None:
                encoding = script_encoding or "utf-8"
                tree = parse_script(script_name, encoding=encoding)
            else:
                _err_console.print(
                    "[bold red]Error:[/bold red] --parse-tree requires a script file or -c command.",
                )
                raise typer.Exit(code=1)
        except ErrInfo as exc:
            _err_console.print(f"[bold red]Parse error:[/bold red] {exc.errmsg()}")
            raise typer.Exit(code=1) from exc

        _console.print(format_tree(tree))
        raise typer.Exit()

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
        profile=profile,
        profile_limit=profile_limit,
        ping=ping,
        debug=debug,
        no_system_cmd=no_system_cmd,
        no_rm_file=no_rm_file,
        no_serve=no_serve,
        config_file=config_file,
        named_vars=parsed_vars,
        manifest_path=manifest_path,
    )


def _parse_named_vars(values: list[str] | None) -> list[tuple[str, str]]:
    """``--var NAME=VALUE`` pairs, in order. Rejects a missing ``=`` or a name execsql reserves."""
    import re

    pairs: list[tuple[str, str]] = []
    for raw in values or ():
        name, sep, value = raw.partition("=")
        name = name.strip()
        if not sep:
            raise typer.BadParameter(f"{raw!r} has no '='; write NAME=VALUE.", param_hint="'--var'")
        if not re.fullmatch(r"\w+", name):
            raise typer.BadParameter(
                f"{name!r} is not a variable name: use letters, digits and _ only. "
                "Names starting with $, & or @ are execsql's own (system, environment and column variables).",
                param_hint="'--var'",
            )
        pairs.append((name, value))
    return pairs
