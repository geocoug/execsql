"""The ``config`` command: list config options, or print the template."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _console, _err_console, _init_config
from execsql.cli.options import ConfigFileOpt, OutputFormat, OutputFormatOpt

__all__ = ["config_cmd", "config_rows"]


def config_rows(script: str | None, config_file: str | None) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve config the way ``execsql run SCRIPT`` would; describe every option.

    Args:
        script: A script path whose directory is searched for ``execsql.conf``,
            as a run of that script would; ``None`` searches only the working
            directory, user and system locations.
        config_file: An extra file loaded last, as ``--config`` does for a run.

    Returns:
        The files read, in load order, and one dict per option with ``section``,
        ``key``, ``type``, ``value``, ``default`` and ``source`` (the file that
        set it, or ``None`` when the default applies). Password values are
        replaced by ``"***"``.
    """
    from execsql.cli.run import _load_config, _seed_early_subvars
    from execsql.config import ConfigData
    from execsql.metacommands.debug import _SENSITIVE_ATTRS  # what DEBUG WRITE CONFIG masks

    conf = _load_config(script, _seed_early_subvars(), config_file)
    rows: list[dict[str, Any]] = []
    # Options read inline in ConfigData register after the rest, so group by
    # section (in first-seen order) to keep each section in one block.
    sections: dict[str, int] = {}
    for section, _key, _type in ConfigData._schema.values():
        sections.setdefault(section, len(sections))
    ordered = sorted(ConfigData._schema.items(), key=lambda item: sections[item[1][0]])
    for attr, (section, key, type_label) in ordered:
        value = getattr(conf, attr, None)
        default = conf.defaults.get(attr)
        if attr in _SENSITIVE_ATTRS:
            value = "***" if value else value
            default = "***" if default else default
        rows.append(
            {
                "section": section,
                "key": key,
                "type": type_label,
                "value": value,
                "default": default,
                "source": conf.sources.get(attr),
            },
        )
    return list(conf.files_read), rows


def _shown(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _print_text(files: list[str], rows: list[dict[str, Any]]) -> None:
    home = str(Path.home())

    def short(path: str) -> str:
        return "~" + path[len(home) :] if path.startswith(home + os.sep) else path

    if files:
        _console.print("[bold]Config files read, in order:[/bold]")
        for f in files:
            _console.print(f"  {short(f)}", highlight=False, soft_wrap=True)
    else:
        _console.print("[bold]No config files found;[/bold] every option has its default.")
    width_key = max(len(r["key"]) for r in rows)
    width_val = min(40, max(len(_shown(r["value"])) for r in rows))
    section = None
    for r in rows:
        if r["section"] != section:
            section = r["section"]
            _console.print(f"\n[bold green]\\[{section}][/bold green]")
        source = short(r["source"]) if r["source"] else "[dim]default[/dim]"
        _console.print(
            f"  [cyan]{r['key']:<{width_key}}[/cyan]  {_shown(r['value']):<{width_val}}  {source}",
            highlight=False,
            soft_wrap=True,
        )


@app.command(cls=ExecsqlCommand, name="config")
def config_cmd(
    script: str | None = typer.Argument(
        None,
        metavar="[SQL_SCRIPT]",
        help=(
            "Resolve config as a run of this script would, including the execsql.conf "
            "in its directory. Without it, only the working directory, user and system "
            "files are read."
        ),
    ),
    init: bool = typer.Option(False, "--init", help="Print a default execsql.conf template to stdout and exit."),
    config_file: ConfigFileOpt = None,
    output_format: OutputFormatOpt = OutputFormat.text,
) -> None:
    """List config options with their values, defaults and sources.

    Config files are read from the same places a run reads them. Passwords
    are never shown.
    """
    if init:
        _init_config()
        raise typer.Exit()
    if config_file and not Path(config_file).is_file():
        _err_console.print(f"[bold red]Error:[/bold red] Config file {config_file!r} does not exist.")
        raise typer.Exit(code=2)
    if script and not Path(script).is_file():
        _err_console.print(f'[bold red]Error:[/bold red] SQL script file "{script}" does not exist.')
        raise typer.Exit(code=2)

    files, rows = config_rows(script, config_file)
    if output_format is OutputFormat.json:
        sys.stdout.write(json.dumps({"files_read": files, "options": rows}, indent=2, default=str) + "\n")
    else:
        _print_text(files, rows)
