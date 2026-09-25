"""Command dispatch for the ``execsql`` console script.

execsql is three tools with three argument shapes: a runner taking one script
plus connection arguments, a formatter taking files and directories, and a
linter that wants directories too.  Each is a real
:class:`typer.Typer` command, so ``execsql --help`` lists them the way any
multi-command CLI does.

What this module adds on top is one rule, applied before the parser sees
anything: **an argument list with no command in it means** ``run``.
``execsql script.sql server db`` has been the invocation since upstream
v1.130.1 — it is in shell scripts, cron entries, and every page of the
documentation — so :func:`normalize` inserts the verb rather than asking
users to. There is no deprecation of the bare form and none is planned.

Two things must not have ``run`` inserted: a real command, and an option the
app declares itself — ``--help``, ``--version``, ``--online-help``.
Everything else, including ``-m`` and the other early-exit options that are
declared on ``run``, is a run.

The one ambiguity this could introduce is a script named exactly ``run``,
``format``, ``fmt`` or ``lint`` *with no extension*.  :func:`_is_command`
refuses to read a token as a command when a file of that name exists, so the
file wins and no existing invocation can change meaning.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["COMMANDS", "GLOBAL_FLAGS", "dispatch", "normalize"]

#: Tokens that name a command.  ``fmt`` is an alias for ``format``: ruff
#: spells it ``format`` and most people type ``fmt``.
COMMANDS = ("run", "format", "fmt", "lint")

#: Options declared on the app rather than on a command, which must reach
#: the parser without ``run`` in front of them. ``-m``, ``--encodings`` and
#: the other early-exit options are declared on ``run``, so they are not
#: here — they get the verb inserted like any other run invocation.
GLOBAL_FLAGS = ("--help", "-h", "--version", "-o", "--online-help")


def _is_command(token: str) -> bool:
    """True when *token* names a command rather than a path.

    A real file of that name wins: a script called ``lint`` must still run,
    not be read as a request to lint nothing.
    """
    if token not in COMMANDS:
        return False
    return not os.path.exists(token)


def normalize(argv: list[str]) -> list[str]:
    """Insert ``run`` when *argv* carries no command.

    Takes and returns the arguments after the program name.
    """
    if not argv:
        return argv
    head = argv[0]
    if _is_command(head) or head in GLOBAL_FLAGS:
        return argv
    return ["run", *argv]


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

    This is the multi-file half that ``--lint`` never had: the flag lints the
    one script you were about to run, while the ``lint`` command is aimed at a
    whole library.

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


def dispatch() -> None:
    """Console-script entry point.

    :func:`normalize` is applied by the app's command group, so every caller —
    this entry point, ``python -m execsql``, and a test driving ``app``
    directly — gets the same treatment. This is a thin alias kept because
    pyproject names it.
    """
    from execsql.cli import _legacy_main

    _legacy_main()
