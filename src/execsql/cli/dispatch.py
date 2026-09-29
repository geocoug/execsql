"""Command dispatch for the ``execsql`` console script.

execsql is six commands behind one program — ``run``, ``format``, ``lint``,
``ping``, ``config`` and ``list`` — each a real :class:`typer.Typer` command,
so ``execsql --help`` lists them the way any multi-command CLI does.

What this module adds on top is one rule, applied before the parser sees
anything: **an argument list with no command in it means** ``run``.
``execsql script.sql server db`` has been the invocation since upstream
v1.130.1 — it is in shell scripts, cron entries, and every page of the
documentation — so :func:`normalize` inserts the verb rather than asking
users to. There is no deprecation of the bare form and none is planned.

Two things must not have ``run`` inserted: a command name, and an option the
app declares itself — ``--help``, ``--version``, ``--online-help``.
Everything else, including ``-m`` and the other hidden aliases declared on
``run``, is a run.

A command name is always a command, whatever files the working directory
holds: a linter must never be able to execute a script because a file named
``lint`` happens to be present. A script named exactly like a command, with
no extension, runs with ``execsql run NAME`` (or ``./NAME``). That is a
recorded, maintainer-approved break from upstream (docs/about/divergence.md).
"""

from __future__ import annotations


__all__ = ["COMMANDS", "GLOBAL_FLAGS", "dispatch", "normalize"]

#: Tokens that name a command.  ``fmt`` is an alias for ``format``: ruff
#: spells it ``format`` and most people type ``fmt``.
COMMANDS = ("run", "format", "fmt", "lint", "ping", "config", "list", "init", "inspect", "shell")

#: Options declared on the app rather than on a command, which must reach
#: the parser without ``run`` in front of them. ``-m``, ``--encodings`` and
#: the other early-exit options are declared on ``run``, so they are not
#: here — they get the verb inserted like any other run invocation.
GLOBAL_FLAGS = ("--help", "-h", "--version", "-o", "--online-help")


def normalize(argv: list[str]) -> list[str]:
    """Insert ``run`` when *argv* carries no command.

    Takes and returns the arguments after the program name.
    """
    if not argv:
        return argv
    head = argv[0]
    if head in COMMANDS or head in GLOBAL_FLAGS:
        return argv
    return ["run", *argv]


def dispatch() -> None:
    """Console-script entry point.

    :func:`normalize` is applied by the app's command group, so every caller —
    this entry point, ``python -m execsql``, and a test driving ``app``
    directly — gets the same treatment. This is a thin alias kept because
    pyproject names it.
    """
    from execsql.cli import _legacy_main

    _legacy_main()
