"""The ``init`` command: set up execsql in a project directory."""

from __future__ import annotations

import datetime
import importlib.resources
import re
from pathlib import Path

import typer
from rich.markup import escape

from execsql import __version__
from execsql.cli.application import ExecsqlCommand, app
from execsql.cli.help import _console

__all__ = ["init_cmd", "pre_commit_snippet", "script_header"]

_HOOKS_REPO = "https://github.com/geocoug/execsql"


def script_header(name: str, today: datetime.date | None = None) -> str:
    """The header a new script starts with: purpose, notes, project, authors and history."""
    today = today or datetime.date.today()
    text = importlib.resources.files("execsql.data").joinpath("script_header.sql").read_text(encoding="utf-8")
    return text.replace("{name}", name).replace("{date}", today.isoformat()).replace("{year}", str(today.year))


def pre_commit_snippet(indent: str = "  ") -> str:
    """The ``repos:`` entry for the execsql-format and execsql-lint hooks, at *indent*."""
    return (
        f"{indent}- repo: {_HOOKS_REPO}\n"
        f"{indent}  rev: v{__version__}\n"
        f"{indent}  hooks:\n"
        f"{indent}    - id: execsql-format\n"
        f"{indent}    - id: execsql-lint\n"
    )


def _add_hooks(path: Path) -> tuple[str, str]:
    """Add the execsql hooks to a pre-commit config; return (action, detail).

    A new file is written whole. An existing one is only appended to, and only
    when ``repos:`` is its last top-level key, so its comments and layout are
    untouched; anything else is reported with the snippet to add by hand.
    """
    if not path.exists():
        path.write_text("repos:\n" + pre_commit_snippet(), encoding="utf-8")
        return "created", ""
    text = path.read_text(encoding="utf-8")
    if _HOOKS_REPO in text or "geocoug/execsql" in text:
        return "skipped", "already has the execsql hooks"
    top_level = re.findall(r"^([A-Za-z_][\w-]*)\s*:", text, flags=re.M)
    if not top_level or top_level[-1] != "repos":
        return "manual", "repos: is not the last key"
    item = re.search(r"^(\s*)- repo:", text, flags=re.M)
    indent = item.group(1) if item else "  "
    path.write_text(text.rstrip("\n") + "\n" + pre_commit_snippet(indent), encoding="utf-8")
    return "added", "the execsql-format and execsql-lint hooks"


def _write(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return "skipped"
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "overwrote" if existed else "created"


@app.command(cls=ExecsqlCommand, name="init")
def init_cmd(
    directory: Path = typer.Argument(
        Path("."),
        metavar="[DIR]",
        help="Project directory; created if missing. Default: the current directory.",
        show_default=False,
    ),
    script: str = typer.Option(
        "main.sql",
        "--script",
        metavar="NAME",
        help="Name of the script to create, relative to DIR. .sql is added if missing.",
    ),
    no_script: bool = typer.Option(False, "--no-script", help="Do not create a script."),
    no_config: bool = typer.Option(False, "--no-config", help="Do not create execsql.conf."),
    no_pre_commit: bool = typer.Option(
        False,
        "--no-pre-commit",
        help="Do not create or change .pre-commit-config.yaml.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite an existing execsql.conf or script. .pre-commit-config.yaml is never overwritten.",
    ),
) -> None:
    """Set up execsql in a project: a config file, a script with a header, and pre-commit hooks.

    Existing files are left alone unless --force is given. Run it again in an
    existing project with --no-config --no-pre-commit --script NAME to add a
    script.
    """
    from execsql.cli.help import _init_config_text

    directory.mkdir(parents=True, exist_ok=True)
    report: list[tuple[str, str, str]] = []

    if not no_config:
        path = directory / "execsql.conf"
        report.append((_write(path, _init_config_text(), force), str(path), ""))

    if not no_script:
        name = script if Path(script).suffix else f"{script}.sql"
        path = directory / name
        report.append((_write(path, script_header(Path(name).name), force), str(path), ""))

    if not no_pre_commit:
        path = directory / ".pre-commit-config.yaml"
        action, detail = _add_hooks(path)
        report.append((action, str(path), detail))

    styles = {"created": "green", "added": "green", "overwrote": "yellow", "skipped": "dim", "manual": "yellow"}
    for action, path_text, detail in report:
        style = styles[action]
        label = "add by hand" if action == "manual" else action
        note = f" ({escape(detail)})" if detail else ""
        if action == "skipped" and not detail:
            note = " (exists; --force to overwrite)"
        _console.print(f"  [{style}]{label:<11}[/{style}] {escape(path_text)}{note}", highlight=False, soft_wrap=True)
        if action == "manual":
            _console.print("\n  Add this under repos: in that file:\n", highlight=False)
            _console.print(escape(pre_commit_snippet("    ")), highlight=False, soft_wrap=True)
    if not report:
        _console.print("Nothing to do: --no-config, --no-script and --no-pre-commit were all given.")
