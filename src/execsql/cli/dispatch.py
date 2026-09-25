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

Two things must not have ``run`` inserted: a real command, and ``--help``,
which the app answers itself.  Everything else — including ``--version``,
``-m`` and the other early-exit options, which are declared on ``run`` — is a
run.

The one ambiguity this could introduce is a script named exactly ``run``,
``format``, ``fmt`` or ``lint`` *with no extension*.  :func:`_is_command`
refuses to read a token as a command when a file of that name exists, so the
file wins and no existing invocation can change meaning.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["COMMANDS", "GLOBAL_FLAGS", "dispatch", "normalize"]

#: Tokens that name a command.  ``fmt`` is an alias for ``format``: ruff
#: spells it ``format`` and most people type ``fmt``.
COMMANDS = ("run", "format", "fmt", "lint")

#: Options the app answers itself rather than passing to a command.  Only
#: help qualifies: ``--version``, ``-m``, ``--encodings`` and the rest are
#: declared on ``run``, so they reach it the same way every other run option
#: does.
GLOBAL_FLAGS = ("--help", "-h")


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


def lint_paths(targets: list[str]) -> int:
    """Lint every script named by *targets*; return the process exit code.

    This is the multi-file half that ``--lint`` never had: the flag lints the
    one script you were about to run, while the ``lint`` command is aimed at a
    whole library.
    """
    from execsql.cli.help import _console, _err_console
    from execsql.cli.lint import _print_lint_results, lint as _lint_script
    from execsql.exceptions import ErrInfo
    from execsql.script.parser import parse_script

    paths = sql_files(targets)
    if not paths:
        _err_console.print("[bold red]Error:[/bold red] no .sql files found in the given paths.")
        return 1

    worst = 0
    total_issues = 0
    for path in paths:
        label = str(path)
        try:
            tree = parse_script(str(path), encoding="utf-8")
        except ErrInfo as exc:
            issues = [("error", label, 0, f"Parse error: {exc.errmsg()}")]
            worst = max(worst, _print_lint_results(issues, label))
            total_issues += 1
            continue
        issues = _lint_script(tree, script_path=str(path))
        if issues:
            total_issues += len(issues)
            worst = max(worst, _print_lint_results(issues, label))

    if total_issues == 0:
        _console.print(f"[green]Lint: {len(paths)} file(s) checked, no issues.[/green]")
    return worst


def dispatch() -> None:
    """Console-script entry point.

    :func:`normalize` is applied by the app's command group, so every caller —
    this entry point, ``python -m execsql``, and a test driving ``app``
    directly — gets the same treatment. This is a thin alias kept because
    pyproject names it.
    """
    from execsql.cli import _legacy_main

    _legacy_main()
