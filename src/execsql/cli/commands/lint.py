"""The ``lint`` command: check scripts for problems without connecting."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

import typer

from execsql.cli.application import ExecsqlCommand, app

__all__ = ["LintFormat", "lint_cmd", "lint_paths", "sql_files"]


def sql_files(targets: list[str]) -> list[Path]:
    """Every ``.sql`` file named by *targets*, directories walked recursively."""
    found: list[Path] = []
    for raw in targets:
        p = Path(raw)
        if p.is_dir():
            found.extend(sorted(q for q in p.rglob("*.sql")))
        else:
            found.append(p)
    return found


def lint_paths(
    targets: list[str],
    *,
    select: tuple[str, ...] = (),
    ignore: tuple[str, ...] = (),
    output_format: str = "text",
    statistics: bool = False,
) -> int:
    """Lint every script named by *targets*; return the process exit code.

    Directories are searched recursively, so one call checks a whole script
    library.

    Args:
        targets: Files and directories; directories are searched for ``*.sql``.
        select: Rule-code prefixes to report (empty means all), already
            validated by :func:`execsql.cli.lint.resolve_selectors`.
        ignore: Rule-code prefixes to drop; wins over *select*.
        output_format: ``"text"`` (grouped by file), ``"concise"`` (one line
            per issue) or ``"json"``. JSON writes one array to stdout and
            nothing else.
        statistics: Report a count per rule instead of each issue.

    Returns:
        ``1`` when any reported issue is an error or no ``.sql`` file was
        found, otherwise ``0``.
    """
    import json

    from execsql.cli.help import _err_console
    from execsql.cli.lint import (
        Issue,
        exit_code,
        filter_issues,
        lint as _lint_script,
        parse_error,
        print_concise,
        print_statistics,
        print_text,
        render_json,
        rule_counts,
    )
    from execsql.exceptions import ErrInfo
    from execsql.script.parser import parse_script

    paths = sql_files(targets)
    if not paths:
        _err_console.print("[bold red]Error:[/bold red] no .sql files found in the given paths.")
        return 1

    per_file: list[tuple[str, list[Issue]]] = []
    for path in paths:
        label = str(path)
        try:
            tree = parse_script(str(path), encoding="utf-8")
        except ErrInfo as exc:
            found = [parse_error(label, exc)]
        else:
            found = _lint_script(tree, script_path=label)
        per_file.append((label, sorted(filter_issues(found, select, ignore), key=lambda i: (i.line, i.code))))

    reported = [issue for _, issues in per_file for issue in issues]

    if output_format == "json":
        if statistics:
            rows = [
                {"code": rule.code, "rule": rule.name, "severity": rule.severity, "count": n}
                for rule, n in rule_counts(reported)
            ]
            sys.stdout.write(json.dumps(rows, indent=2) + "\n")
        else:
            sys.stdout.write(render_json(reported) + "\n")
        return exit_code(reported)

    if statistics:
        print_statistics(per_file, len(paths))
    elif output_format == "concise":
        print_concise(per_file, len(paths))
    else:
        print_text(per_file, len(paths))
    return exit_code(reported)


class LintFormat(str, Enum):
    """Output formats for ``execsql lint``."""

    text = "text"
    concise = "concise"
    json = "json"


@app.command(
    cls=ExecsqlCommand,
    name="lint",
    help=(
        "Statically check scripts for problems. No database connection is made.\n\n"
        "Every issue names its rule code, which --select and --ignore accept, as a full "
        "code (V001) or a prefix (V). Parse errors (P001) are always reported. Exits 1 "
        "when any error is found; warnings alone exit 0.\n\n"
        "Rules: https://execsql2.readthedocs.io/en/latest/reference/lint/"
    ),
)
def lint_cmd(
    targets: list[str] = typer.Argument(
        ...,
        metavar="FILE_OR_DIR...",
        help="Files or directories to check. Directories are searched recursively for *.sql files.",
    ),
    select: list[str] | None = typer.Option(
        None,
        "--select",
        metavar="CODES",
        help="Report only these rules: codes or prefixes, comma-separated (e.g. V001,F). Repeatable.",
    ),
    ignore: list[str] | None = typer.Option(
        None,
        "--ignore",
        metavar="CODES",
        help="Do not report these rules: codes or prefixes, comma-separated. Wins over --select. Repeatable.",
    ),
    output_format: LintFormat = typer.Option(
        LintFormat.text,
        "--output-format",
        help="text groups issues by file; concise is one path:line line per issue; json is for tools.",
    ),
    statistics: bool = typer.Option(
        False,
        "--statistics",
        help="Show how many times each rule fired instead of listing every issue.",
    ),
) -> None:
    """The ``lint`` command; its user-facing help is the decorator's ``help``."""
    from execsql.cli.lint import resolve_selectors

    try:
        selected = resolve_selectors(select)
        ignored = resolve_selectors(ignore)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    raise typer.Exit(
        code=lint_paths(
            targets,
            select=selected,
            ignore=ignored,
            output_format=output_format.value,
            statistics=statistics,
        ),
    )
