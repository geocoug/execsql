"""Subcommand dispatch for the ``execsql`` console script.

execsql grew three tools with three argument shapes: a runner that takes one
script plus connection arguments, a formatter that takes files and
directories, and a linter that wants directories too.  Subcommands give each
its own shape without the runner's parser having to accommodate the others.

The legacy positional form is why this is argv dispatch rather than a plain
``typer.Typer`` carrying several commands.  ``execsql script.sql server db``
has been the invocation since upstream v1.130.1; it is in shell scripts, cron
entries, and every page of the documentation, and it must keep working
unchanged.  So ``argv[1]`` decides: a known verb selects a subcommand, and
anything else is handed to the existing runner parser untouched.

The one ambiguity this could introduce is a script named exactly ``run``,
``format``, ``fmt``, ``lint``, or ``check`` *with no extension*.
:func:`_is_verb` refuses to read ``argv[1]`` as a verb when a file of that
name exists, so the file always wins and no existing invocation can change
meaning.  There is deliberately no deprecation warning on the legacy form: it
is the documented upstream spelling, and warning on it would punish people for
having followed the documentation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["VERBS", "dispatch", "route"]

#: ``argv[1]`` values that select a subcommand.  ``fmt`` is an alias for
#: ``format``: ruff spells it ``format`` and most people type ``fmt``.
VERBS = ("run", "format", "fmt", "lint")

_ALIASES = {"fmt": "format"}


def _is_verb(token: str) -> bool:
    """True when *token* should be read as a subcommand rather than a path.

    A real file of that name wins: a script called ``lint`` must still run,
    not be read as a request to lint nothing.
    """
    if token not in VERBS:
        return False
    return not os.path.exists(token)


def route(argv: list[str]) -> tuple[str, list[str]]:
    """Map a full ``argv`` to ``(target, remaining_args)``.

    *target* is one of ``run``, ``format``, ``lint``, or
    ``legacy`` — the last meaning "hand these arguments to the runner parser
    exactly as they arrived".
    """
    if len(argv) < 2:
        return "legacy", argv[1:]
    head = argv[1]
    if _is_verb(head):
        return _ALIASES.get(head, head), argv[2:]
    return "legacy", argv[1:]


def _sql_files(targets: list[str]) -> list[Path]:
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
    one script you were about to run, while the ``lint`` subcommand is aimed
    at a whole library.
    """
    from execsql.cli.help import _console, _err_console
    from execsql.cli.lint import _print_lint_results, lint as _lint_script
    from execsql.exceptions import ErrInfo
    from execsql.script.parser import parse_script

    paths = _sql_files(targets)
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
    """Route ``sys.argv`` to a subcommand, or fall through to the runner."""
    target, rest = route(sys.argv)

    if target == "format":
        # execsql-format owns the formatter's own argument parser; handing it
        # a rewritten argv keeps exactly one definition of those options.
        from execsql.format import main as _format_main

        sys.argv = ["execsql format", *rest]
        _format_main()
        return

    if target == "lint":
        raise SystemExit(lint_paths(rest))

    # "run" is the explicit spelling of the legacy form; both reach the same
    # parser with the same arguments.
    sys.argv = [sys.argv[0], *rest]
    from execsql.cli import _legacy_main

    _legacy_main()
