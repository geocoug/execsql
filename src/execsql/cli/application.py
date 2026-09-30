"""The execsql Typer app: command group, help rendering, global options.

Every command registers itself on :data:`app` from a module in
:mod:`execsql.cli.commands`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import typer
from typer.core import TyperCommand, TyperGroup

from execsql import __version__
from execsql.cli.help import _console, _err_console
from execsql.utils.color import color_disabled_by_env

__all__ = ["ExecsqlCommand", "ExecsqlGroup", "ExecsqlSubGroup", "app"]


#: Options the app answers about itself rather than about a run, shown under
#: their own heading. ``--config`` is deliberately not here: only ``run``
#: reads an execsql config file, so listing it as global would be a lie.
_GLOBAL_OPTIONS = ("--online-help", "--version")

#: What to type instead of a flag that, used without a command, implies ``run``.
_REPLACEMENTS = {
    "-m": "execsql list metacommands",
    "--metacommands": "execsql list metacommands",
    "-y": "execsql list encodings",
    "--encodings": "execsql list encodings",
    "--list-plugins": "execsql list plugins",
    "--dump-keywords": "execsql list keywords --output-format json",
    "--init-config": "execsql config --init",
    "--ping": "execsql run --ping",
}


def deprecated_bare_form(head: str) -> str:
    """The warning printed when ``run`` is implied rather than typed; *head* is the first argument."""
    if head in _REPLACEMENTS:
        return (
            f"Deprecated: `execsql {head}` is now `{_REPLACEMENTS[head]}`; the old form stops working in execsql2 3.0."
        )
    return (
        "Deprecated: running a script without the run command. Use `execsql run SCRIPT ...`; "
        "`execsql SCRIPT ...` stops working in execsql2 3.0."
    )


def _unescape(record: tuple[str, str]) -> tuple[str, str]:
    """Undo Typer's Rich bracket escaping for plain help output.

    Typer escapes ``[`` as ``\\[`` so Rich does not read ``[required]`` as
    markup. With Rich rendering off those backslashes are literal text, so
    every default and required marker would print as ``\\[default: 4]``.
    """
    name, help_text = record
    return name.replace("\\[", "["), help_text.replace("\\[", "[")


# Help fills the terminal, as ruff's and uv's do. Click caps it at 80 columns
# unless told otherwise; piped help still wraps at 80, since there is no
# terminal to measure. The option column is wide enough for the longest
# names here ("--gui-framework {tkinter,textual}"), so their descriptions
# start on the same line instead of the next.
_HELP_MAX_WIDTH = 10_000
_OPTION_COLUMN = 36

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
        # Every argument here carries an explicit metavar, and it is printed as
        # written. Typer 0.27 decorates it instead, wrapping required arguments
        # in braces and optional ones in brackets, so the same command would
        # print a different usage line depending on the installed Typer.
        pieces = [self.options_metavar] if self.options_metavar else []  # type: ignore[attr-defined]
        for param in self.get_params(ctx):  # type: ignore[attr-defined]
            if param.param_type_name == "argument" and param.metavar:
                pieces.append(param.metavar)
            else:
                pieces.extend(param.get_usage_pieces(ctx))
        formatter.write_usage(ctx.command_path, " ".join(pieces), prefix=_usage_prefix())

    def format_arguments(self, ctx: Any, formatter: Any) -> None:
        # Click 8.5 added this step, with its own "Positional arguments"
        # heading. format_options below already renders the arguments, and a
        # Typer built on the standalone Click would otherwise list them twice.
        pass

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
                formatter.write_dl(args, col_max=_OPTION_COLUMN)
        if opts:
            with _section(formatter, "Options"):
                formatter.write_dl(opts, col_max=_OPTION_COLUMN)


class ExecsqlCommand(_PlainHelpMixin, TyperCommand):
    """A command whose help is plain text, brackets and all."""


class ExecsqlGroup(TyperGroup):
    """The top-level command group: default command, dual usage, grouped options.

    Three departures from Click's defaults, each for a reason:

    *Default command, deprecated.* ``execsql script.sql server db`` has been
    the invocation since upstream v1.130.1 — it is in shell scripts and cron
    entries — so an argument list carrying no command name still gets ``run``
    inserted before the parser sees it, with a deprecation warning on stderr;
    the form stops working in execsql2 3.0. Doing that here rather than in the
    console-script wrapper means the app behaves the same however it is
    reached: the entry point, ``python -m execsql``, or a test driving ``app``
    directly.

    *One usage line.* Help documents one form, ``execsql COMMAND``.

    *Grouped options.* Click lists every option in one block. The four that
    apply to the whole tool rather than to a run are worth separating from
    ``--help``.
    """

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        from execsql.cli.dispatch import normalize

        if not args:
            # Running execsql with no arguments is a usage error: the help goes
            # to stdout, and the status is 2, as for any other usage error.
            # Upstream exited 0 here; this is a recorded divergence
            # (docs/about/divergence.md, "CLI Interface"). Click's own
            # no_args_is_help exits 0 on Click 8.1 and 2 on 8.2+, so the status
            # is set here rather than left to whichever Click is installed.
            typer.echo(ctx.get_help(), color=ctx.color)
            ctx.exit(2)
        normalized = normalize(args)
        if normalized is not args:
            _err_console.print(f"[yellow]{deprecated_bare_form(args[0])}[/yellow]", highlight=False, soft_wrap=True)
        return super().parse_args(ctx, normalized)

    def list_commands(self, ctx: Any) -> list[str]:
        # Typer registers command groups (``list``) after plain commands; help
        # follows the order COMMANDS gives instead.
        from execsql.cli.dispatch import COMMANDS

        names = super().list_commands(ctx)
        return sorted(names, key=lambda n: COMMANDS.index(n) if n in COMMANDS else len(COMMANDS))

    def format_usage(self, ctx: Any, formatter: Any) -> None:
        formatter.write_usage(ctx.command_path, "[OPTIONS] COMMAND [ARGS]...", prefix=_usage_prefix())

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
                formatter.write_dl(globals_, col_max=_OPTION_COLUMN)
        if rest:
            with _section(formatter, "Options"):
                formatter.write_dl(rest, col_max=_OPTION_COLUMN)
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


class ExecsqlSubGroup(ExecsqlGroup):
    """A command with commands of its own (``execsql list``).

    The app's help layout, without the app's ``run`` insertion; with no
    arguments it prints its help and exits 2, as the app does.
    """

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if not args:
            typer.echo(ctx.get_help(), color=ctx.color)
            ctx.exit(2)
        return TyperGroup.parse_args(self, ctx, args)

    def list_commands(self, ctx: Any) -> list[str]:
        return TyperGroup.list_commands(self, ctx)


app = typer.Typer(
    cls=ExecsqlGroup,
    name="execsql",
    # Plain click rendering: no panels, and format_options below can group.
    rich_markup_mode=None,
    help="Run, format and lint SQL scripts with metacommands.",
    add_completion=False,
    no_args_is_help=True,
    # Upstream's optparse answered -h as well as --help. Commands inherit this.
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": _HELP_MAX_WIDTH},
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
