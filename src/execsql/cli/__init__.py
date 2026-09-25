"""Command-line interface for execsql.

Parses arguments via Typer, then delegates to :func:`_run` for state
initialisation, database connection, and script execution.

Submodules:

- :mod:`execsql.cli.help`      — Rich-formatted help output & console objects
- :mod:`execsql.cli.dsn`       — Connection-string (DSN URL) parser
- :mod:`execsql.cli.run`       — Core execution logic (``_run``, ``_connect_initial_db``, ``_ping_db``, ``_print_dry_run``, ``_print_profile``)
- :mod:`execsql.cli.lint`      — AST-based ``--lint`` static analyser and Rich result printer
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import typer
from typer.core import TyperCommand, TyperGroup

from execsql import __version__
from execsql.cli.dsn import _parse_connection_string, _SCHEME_TO_DBTYPE  # noqa: F401 — re-export
from execsql.cli.help import _console, _err_console, _init_config, _print_encodings, _print_metacommands  # noqa: F401 — re-export
from execsql.cli.run import _connect_initial_db, _run  # noqa: F401 — re-export
from execsql.exceptions import ConfigError, ErrInfo
from execsql.utils.color import color_disabled_by_env

__all__ = [
    "_SCHEME_TO_DBTYPE",
    "_connect_initial_db",
    "_console",
    "_err_console",
    "_init_config",
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


#: Options the app answers about itself rather than about a run, shown under
#: their own heading. ``--config`` is deliberately not here: only ``run``
#: reads an execsql config file, so listing it as global would be a lie.
_GLOBAL_OPTIONS = ("--online-help", "--version")


def _unescape(record: tuple[str, str]) -> tuple[str, str]:
    """Undo Typer's Rich bracket escaping for plain help output.

    Typer escapes ``[`` as ``\\[`` so Rich does not read ``[required]`` as
    markup. With Rich rendering off those backslashes are literal text, so
    every default and required marker would print as ``\\[default: 4]``.
    """
    name, help_text = record
    return name.replace("\\[", "["), help_text.replace("\\[", "[")


# Help color follows uv and cargo: headings bold green, names cyan with the
# option flags bold. Click's echo drops ANSI when stdout is not a terminal,
# and its column widths ignore escape codes, so styling costs no alignment
# and never reaches a pipe; NO_COLOR is the one case left to handle here.


def _style(text: str, **styles: Any) -> str:
    if not text or color_disabled_by_env():
        return text
    return typer.style(text, **styles)


@contextmanager
def _section(formatter: Any, name: str) -> Iterator[None]:
    """``formatter.section`` with a colored heading, colon included."""
    formatter.write_paragraph()
    formatter.write(f"{'':>{formatter.current_indent}}{_style(name + ':', fg='green', bold=True)}\n")
    formatter.indent()
    try:
        yield
    finally:
        formatter.dedent()


def _usage_prefix() -> str:
    return _style("Usage:", fg="green", bold=True) + " "


def _styled_record(param: Any, record: tuple[str, str]) -> tuple[str, str]:
    """Color one help row: the flags bold, any metavar after them plain."""
    name, help_text = _unescape(record)
    if param.param_type_name == "argument":
        return _style(name, fg="cyan"), help_text
    flags = [*param.opts, *param.secondary_opts]
    end = max((name.find(flag) + len(flag) for flag in flags if flag in name), default=len(name))
    return _style(name[:end], fg="cyan", bold=True) + _style(name[end:], fg="cyan"), help_text


# Typer 0.26 stopped depending on Click and vendors it as ``typer._click``, so
# ``click.Context`` is the wrong class on newer Typer and ``click`` may not be
# installed at all. The overrides below take ``ctx`` and ``formatter`` as
# ``Any`` because no public import names the right type across the supported
# Typer range; they rely only on methods both Click lineages provide.


class _PlainHelpMixin:
    """Render option help without Typer's Rich escaping."""

    def format_usage(self, ctx: Any, formatter: Any) -> None:
        pieces = self.collect_usage_pieces(ctx)  # type: ignore[attr-defined]
        formatter.write_usage(ctx.command_path, " ".join(pieces), prefix=_usage_prefix())

    def format_options(self, ctx: Any, formatter: Any) -> None:
        args: list[tuple[str, str]] = []
        opts: list[tuple[str, str]] = []
        for param in self.get_params(ctx):  # type: ignore[attr-defined]
            record = param.get_help_record(ctx)
            if not record:
                continue
            bucket = args if param.param_type_name == "argument" else opts
            bucket.append(_styled_record(param, record))
        if args:
            with _section(formatter, "Arguments"):
                formatter.write_dl(args)
        if opts:
            with _section(formatter, "Options"):
                formatter.write_dl(opts)


class ExecsqlCommand(_PlainHelpMixin, TyperCommand):
    """A command whose help is plain text, brackets and all."""


class ExecsqlGroup(TyperGroup):
    """The top-level command group: default command, dual usage, grouped options.

    Three departures from Click's defaults, each for a reason:

    *Default command.* ``execsql script.sql server db`` has been the
    invocation since upstream v1.130.1 — it is in shell scripts, cron entries
    and every page of the documentation — so an argument list carrying no
    command name gets ``run`` inserted before the parser sees it. Doing that
    here rather than in the console-script wrapper means the app behaves the
    same however it is reached: the entry point, ``python -m execsql``, or a
    test driving ``app`` directly.

    *Two usage lines.* The bare form is not a shorthand to be discovered in
    prose; it is how most people invoke execsql, so it is stated as an
    invocation in its own right.

    *Grouped options.* Click lists every option in one block. The four that
    apply to the whole tool rather than to a run are worth separating from
    ``--help``.
    """

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        from execsql.cli.dispatch import normalize

        if not args:
            # Click's no_args_is_help exits 0 for a group. Running execsql with
            # no arguments is a usage error and has always exited non-zero, so
            # the help goes out but the status does not change.
            typer.echo(ctx.get_help(), color=ctx.color)
            ctx.exit(2)
        return super().parse_args(ctx, normalize(args))

    def format_usage(self, ctx: Any, formatter: Any) -> None:
        formatter.write_usage(ctx.command_path, "[OPTIONS] COMMAND [ARGS]...", prefix=_usage_prefix())
        formatter.write_usage(
            ctx.command_path,
            "[OPTIONS] SQL_SCRIPT [SERVER DATABASE | DATABASE_FILE]",
            prefix=" " * len("Usage: "),
        )

    def format_options(self, ctx: Any, formatter: Any) -> None:
        globals_: list[tuple[str, str]] = []
        rest: list[tuple[str, str]] = []
        for param in self.get_params(ctx):
            record = param.get_help_record(ctx)
            if not record:
                continue
            bucket = globals_ if any(o in param.opts for o in _GLOBAL_OPTIONS) else rest
            bucket.append(_styled_record(param, record))

        if globals_:
            with _section(formatter, "Global options"):
                formatter.write_dl(globals_)
        if rest:
            with _section(formatter, "Options"):
                formatter.write_dl(rest)
        self.format_commands(ctx, formatter)

    def format_commands(self, ctx: Any, formatter: Any) -> None:
        # Click's own version, with the command names colored.
        commands = [
            (name, cmd)
            for name in self.list_commands(ctx)
            if (cmd := self.get_command(ctx, name)) is not None and not cmd.hidden
        ]
        if not commands:
            return
        limit = formatter.width - 6 - max(len(name) for name, _ in commands)
        with _section(formatter, "Commands"):
            formatter.write_dl(
                [(_style(name, fg="cyan", bold=True), cmd.get_short_help_str(limit)) for name, cmd in commands],
            )


app = typer.Typer(
    cls=ExecsqlGroup,
    name="execsql",
    # Plain click rendering: no panels, and format_options below can group.
    rich_markup_mode=None,
    help=(
        "Write, format, lint and run SQL scripts with metacommands.\n\n"
        "format and lint need no database. Giving no command is the same "
        "as run."
    ),
    add_completion=False,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        _console.print(f"execsql [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


def _online_help_callback(value: bool) -> None:
    if value:
        import webbrowser

        webbrowser.open("https://execsql2.readthedocs.io/en/latest/", new=2, autoraise=True)
        raise typer.Exit()


@app.callback()
def _global_options(
    online_help: bool = typer.Option(
        False,
        "-o",
        "--online-help",
        callback=_online_help_callback,
        is_eager=True,
        help="Open the online documentation in the default browser.",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Options about execsql itself rather than about one run.

    Both are eager and exit on their own, so neither needs to reach a
    command; the callback body has nothing to do.
    """


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
    db_type: str | None = typer.Option(
        None,
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
    dsn: str | None = typer.Option(
        None,
        "--dsn",
        "--connection-string",
        metavar="URL",
        help=(
            "Database connection URL, e.g. postgresql://user:pass@host:5432/db. "
            "Supported schemes: postgresql, mysql, mssql, oracle, firebird, sqlite, duckdb. "
            "Overrides -t/-u/-p and positional server/db args."
        ),
    ),
    user: str | None = typer.Option(
        None,
        "-u",
        "--user",
        help="Database user name.",
    ),
    port: int | None = typer.Option(
        None,
        "-p",
        "--port",
        help="Database server port.",
    ),
    no_passwd: bool = typer.Option(
        False,
        "-w",
        "--no-passwd",
        help="Skip password prompt when user is specified.",
    ),
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
    script_encoding: str | None = typer.Option(
        None,
        "-f",
        "--script-encoding",
        help="Character encoding of the script file. Default: UTF-8",
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
    lint: bool = typer.Option(
        False,
        "--lint",
        help=(
            "Parse the script and perform static analysis without connecting to a database or executing anything. "
            "Reports unmatched IF/ENDIF/LOOP/BATCH blocks (errors), potentially undefined variables, "
            "and missing INCLUDE files (warnings). Exits 0 if no errors, 1 if errors found."
        ),
    ),
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
    config_file: str | None = typer.Option(
        None,
        "--config",
        metavar="FILE",
        help=(
            "Path to an execsql configuration file. "
            "Loaded after the implicit search paths so its values take precedence. "
            "The file may chain additional configs via its [config] section."
        ),
    ),
    init_config: bool = typer.Option(
        False,
        "--init-config",
        help="Print a default execsql.conf template to stdout and exit.",
    ),
    sub_vars: list[str] | None = typer.Option(
        None,
        "-a",
        "--assign-arg",
        metavar="VALUE",
        help="Define the replacement string for a substitution variable $ARG_x.",
    ),
    user_logfile: bool = typer.Option(
        False,
        "-l",
        "--user-logfile",
        help="Write a log file to ~/execsql.log.",
    ),
    # -- Information -------------------------------------------------------
    metacommands: bool = typer.Option(
        False,
        "-m",
        "--metacommands",
        help="List metacommands and exit.",
    ),
    encodings: bool = typer.Option(
        False,
        "-y",
        "--encodings",
        help="List available encoding names and exit.",
    ),
    dump_keywords: bool = typer.Option(
        False,
        "--dump-keywords",
        help="Dump all metacommand keywords as JSON and exit.",
    ),
    list_plugins: bool = typer.Option(
        False,
        "--list-plugins",
        help="List all discovered plugins (metacommands, exporters, importers) and exit.",
    ),
    ping: bool = typer.Option(
        False,
        "--ping",
        help=(
            "Test database connectivity and exit. "
            "Prints connection details and the server version on success (exit 0), "
            "or the error message on failure (exit 1). "
            "No script file is required."
        ),
    ),
) -> None:
    """Run SQL_SCRIPT against the specified database.

    Positional arguments after the script file:

    Client-server databases:
      execsql script.sql [SERVER] [DATABASE]

    File-based databases (SQLite, DuckDB, Access):
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

    if init_config:
        _init_config()
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

    if list_plugins:
        from execsql.plugins import (
            EXPORTER_GROUP,
            IMPORTER_GROUP,
            METACOMMAND_GROUP,
            _load_entry_points,
        )

        _console.print("\n[bold cyan]Installed plugins:[/bold cyan]\n")

        mc_plugins = _load_entry_points(METACOMMAND_GROUP)
        ex_plugins = _load_entry_points(EXPORTER_GROUP)
        im_plugins = _load_entry_points(IMPORTER_GROUP)

        if not mc_plugins and not ex_plugins and not im_plugins:
            _console.print("  [dim]No plugins found.[/dim]")
            _console.print()
            _console.print(
                "  Plugins are discovered via Python entry points.\n"
                "  See the execsql documentation for how to create plugins.",
            )
        else:
            if mc_plugins:
                _console.print(f"  [bold]Metacommands[/bold] ({len(mc_plugins)}):")
                for name, _ in mc_plugins:
                    _console.print(f"    - {name}")
            if ex_plugins:
                _console.print(f"  [bold]Exporters[/bold] ({len(ex_plugins)}):")
                for name, _ in ex_plugins:
                    _console.print(f"    - {name}")
            if im_plugins:
                _console.print(f"  [bold]Importers[/bold] ({len(im_plugins)}):")
                for name, _ in im_plugins:
                    _console.print(f"    - {name}")

        _console.print()
        raise typer.Exit()

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
    # Lint: AST-based static analysis (no DB connection needed)
    # ------------------------------------------------------------------
    if lint:
        from execsql.cli.lint import _print_lint_results, lint as _lint_script
        from execsql.script.parser import parse_script, parse_string

        label = script_name or "<inline>"
        try:
            if command is not None:
                tree = parse_string(command.replace("\\n", "\n").replace("\\t", "\t"), "<inline>")
            elif script_name is not None:
                encoding = script_encoding or "utf-8"
                tree = parse_script(script_name, encoding=encoding)
            else:
                _err_console.print(
                    "[bold red]Error:[/bold red] --lint requires a script file or -c command.",
                )
                raise typer.Exit(code=1)
        except ErrInfo as exc:
            # Parse failure IS a lint error — report it
            issues = [("error", label, 0, f"Parse error: {exc.errmsg()}")]
            exit_code = _print_lint_results(issues, label)
            raise typer.Exit(code=exit_code) from exc

        issues = _lint_script(tree, script_path=script_name)
        exit_code = _print_lint_results(issues, label)
        raise typer.Exit(code=exit_code)

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
        lint=lint,
        debug=debug,
        no_system_cmd=no_system_cmd,
        no_rm_file=no_rm_file,
        no_serve=no_serve,
        config_file=config_file,
    )


# ---------------------------------------------------------------------------
# format / lint commands
#
# Registered here rather than dispatched by hand so that ``execsql --help``
# lists them: a Typer app with one command has no command list to show.
# ---------------------------------------------------------------------------


@app.command(cls=ExecsqlCommand, name="format")
def format_cmd(
    targets: list[Path] = typer.Argument(
        ...,
        metavar="FILE_OR_DIR",
        help="Files or directories to format. Directories are searched recursively for *.sql files.",
    ),
    check: bool = typer.Option(False, "--check", help="Exit 1 if any file needs changes; write nothing."),
    in_place: bool = typer.Option(False, "-i", "--in-place", help="Modify files in place."),
    no_sql: bool = typer.Option(False, "--no-sql", help="Skip SQL reformatting via sqlglot."),
    indent: int = typer.Option(4, "--indent", metavar="N", help="Spaces per indent level."),
    leading_comma: bool = typer.Option(
        False,
        "--leading-comma",
        help="Place commas at the start of lines instead of the end.",
    ),
    encoding: str = typer.Option(
        "utf-8",
        "--encoding",
        metavar="NAME",
        help="Text encoding used to read and write SQL files.",
    ),
) -> None:
    """Normalize metacommand keywords, block indentation, and SQL layout.

    SQL reformatting needs the [formatter] extra; --no-sql works without it.
    """
    from execsql.format import run_formatter

    raise typer.Exit(
        code=run_formatter(
            targets,
            check=check,
            in_place=in_place,
            no_sql=no_sql,
            indent=indent,
            leading_comma=leading_comma,
            encoding=encoding,
        ),
    )


@app.command(cls=ExecsqlCommand, name="fmt", hidden=True)
def fmt_cmd(
    targets: list[Path] = typer.Argument(..., metavar="FILE_OR_DIR"),
    check: bool = typer.Option(False, "--check"),
    in_place: bool = typer.Option(False, "-i", "--in-place"),
    no_sql: bool = typer.Option(False, "--no-sql"),
    indent: int = typer.Option(4, "--indent", metavar="N"),
    leading_comma: bool = typer.Option(False, "--leading-comma"),
    encoding: str = typer.Option("utf-8", "--encoding", metavar="NAME"),
) -> None:
    """Alias for format, hidden so the command list shows one spelling."""
    format_cmd(
        targets,
        check=check,
        in_place=in_place,
        no_sql=no_sql,
        indent=indent,
        leading_comma=leading_comma,
        encoding=encoding,
    )


@app.command(
    cls=ExecsqlCommand,
    name="lint",
    help="Statically check scripts for problems. No database connection is made.",
)
def lint_cmd(
    targets: list[str] = typer.Argument(
        ...,
        metavar="FILE_OR_DIR",
        help="Files or directories to check. Directories are searched recursively for *.sql files.",
    ),
) -> None:
    """Report unmatched blocks, undefined variables, unreachable branches, and
    missing INCLUDE / EXECUTE SCRIPT targets. Exits 1 when any error is found;
    warnings do not affect the exit code.
    """
    from execsql.cli.dispatch import lint_paths

    raise typer.Exit(code=lint_paths(targets))


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
