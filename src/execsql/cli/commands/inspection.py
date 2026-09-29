"""The ``inspect`` command: what a script needs and what it touches, without running it.

The module is not named ``inspect`` so it never shadows the standard library.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.markup import escape

from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _console, _err_console
from execsql.cli.options import ConfigFileOpt, OutputFormat, OutputFormatOpt, ScriptEncodingOpt

__all__ = ["inspect_cmd"]

_NEED_NOTES = {
    "arguments": "-a on the command line",
    "environment": "environment variable",
    "variables": "--var, [variables] in a config file, or SUB_INI",
}


def _print_text(data: dict) -> None:
    _console.print(f"[bold]{escape(data['script'])}[/bold]", highlight=False, soft_wrap=True)
    needs = [(name, _NEED_NOTES[kind]) for kind in _NEED_NOTES for name in data["needs"][kind]]
    touches = [
        ("Includes", data["includes"]),
        ("Reads", data["reads"]),
        ("Writes", data["writes"]),
        ("Deletes", data["deletes"]),
        ("Connections", data["connections"]),
    ]
    rows = [t for _, section in touches for t in section]
    if not needs and not rows and not data["defines"]["variables"] and not data["defines"]["scripts"]:
        _console.print("\nNothing found: the script needs no outside values and touches no files or databases.")
        return
    if needs:
        _console.print("\n[bold green]Needs from outside[/bold green]")
        width = max(len(name) for name, _ in needs)
        for name, note in needs:
            _console.print(f"  [cyan]{escape(name):<{width}}[/cyan]  [dim]{escape(note)}[/dim]", highlight=False)
    line_w = max((len(str(t["line"])) for t in rows), default=1)
    by_w = max((len(t["by"]) for t in rows), default=1)
    target_w = min(48, max((len(t["target"]) for t in rows), default=1))
    for title, section in touches:
        if not section:
            continue
        _console.print(f"\n[bold green]{title}[/bold green]")
        for t in section:
            target = escape(t["target"])
            detail = f"{target:<{target_w}}  [dim]{escape(t['detail'])}[/dim]" if t["detail"] else target
            _console.print(
                f"  {t['line']:>{line_w}}  {t['by']:<{by_w}}  {detail}",
                highlight=False,
                soft_wrap=True,
            )
    defines = data["defines"]
    if defines["variables"] or defines["scripts"]:
        _console.print("\n[bold green]Defines[/bold green]")
        if defines["variables"]:
            _console.print(f"  variables  {escape(', '.join(defines['variables']))}", highlight=False, soft_wrap=True)
        if defines["scripts"]:
            _console.print(f"  scripts    {escape(', '.join(defines['scripts']))}", highlight=False, soft_wrap=True)


@app.command(cls=ExecsqlCommand, name="inspect")
def inspect_cmd(
    script: Path = typer.Argument(..., metavar="SQL_SCRIPT", help="The script to inspect. - reads it from stdin."),
    script_encoding: ScriptEncodingOpt = None,
    config_file: ConfigFileOpt = None,
    output_format: OutputFormatOpt = OutputFormat.text,
) -> None:
    """Show what a script needs and touches, without running it.

    Lists the values it expects from outside (command-line arguments,
    environment variables, variables it never defines), the scripts it
    includes, the files it reads, writes and deletes, and the databases it
    connects to. Paths are shown as written, variables and all.
    """
    from execsql.cli.inspection import inspect_script
    from execsql.cli.run import _configured_script_encoding, _tool_config
    from execsql.exceptions import ErrInfo
    from execsql.script.parser import parse_string

    if config_file and not Path(config_file).is_file():
        _err_console.print(f"[bold red]Error:[/bold red] Config file {config_file!r} does not exist.")
        raise typer.Exit(code=2)
    stdin = str(script) == "-"
    if not stdin and not script.is_file():
        _err_console.print(f'[bold red]Error:[/bold red] SQL script file "{script}" does not exist.')
        raise typer.Exit(code=2)

    encoding = script_encoding or _configured_script_encoding(_tool_config(config_file)) or "utf-8"
    label = "<stdin>" if stdin else str(script)
    try:
        source = sys.stdin.buffer.read().decode(encoding) if stdin else script.read_text(encoding=encoding)
    except UnicodeDecodeError as exc:
        _err_console.print(
            f"[bold red]Error:[/bold red] cannot decode {escape(label)} as {encoding} ({exc.reason}); "
            "set -f/--script-encoding",
        )
        raise typer.Exit(code=1) from exc
    try:
        tree = parse_string(source, label)
    except ErrInfo as exc:
        from execsql.cli.lint import parse_error

        problem = parse_error(label, exc)
        where = f"{label}:{problem.line}" if problem.line else label
        _err_console.print(f"[bold red]Error:[/bold red] cannot parse {escape(where)}: {escape(problem.message)}")
        raise typer.Exit(code=1) from exc

    data = inspect_script(tree, None if stdin else label).to_dict()
    if output_format is OutputFormat.json:
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
    else:
        _print_text(data)
