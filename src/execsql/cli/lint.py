"""Shared Rich-formatted output for ``--lint`` results.

The active linter is :mod:`execsql.cli.lint_ast`, which produces
``(severity, source, line_no, message)`` tuples. This module owns the
small surface that converts those tuples into the user-facing console
output:

- :class:`_Issue` — the issue tuple type alias.
- :func:`_error` / :func:`_warning` — issue constructors.
- :func:`_print_lint_results` — Rich console formatter; returns the
  ``--lint`` exit code (``1`` if any error, else ``0``).

This module previously hosted a flat-CommandList walker
(``_lint_script`` / ``_lint_cmdlist`` and friends) that pre-dated the
AST. The walker was removed once the CLI fully migrated to the AST
linter; the rename of ``_state.savedscripts`` → ``_state.ast_scripts``
had silently turned its EXECUTE-SCRIPT flow analysis into a no-op.

Exit-code contract (honoured by the AST linter):

- ``1`` when at least one error-severity issue is found.
- ``0`` when only warnings (or nothing) are found.
"""

from __future__ import annotations

__all__ = ["_Issue", "_error", "_print_lint_results", "_warning"]


_Issue = tuple[str, str, int, str]  # (severity, source, line_no, message)


def _error(source: str, line_no: int, message: str) -> _Issue:
    return ("error", source, line_no, message)


def _warning(source: str, line_no: int, message: str) -> _Issue:
    return ("warning", source, line_no, message)


def _print_lint_results(issues: list[_Issue], script_label: str) -> int:
    """Print lint issues to the console using Rich formatting.

    Args:
        issues: List of ``(severity, source, line_no, message)`` tuples.
        script_label: Human-readable label for the script (file path or
            ``<inline>``), shown in the summary line.

    Returns:
        ``1`` if any errors were found, ``0`` if only warnings or nothing.
    """
    from execsql.cli.help import _console

    n_errors = sum(1 for sev, *_ in issues if sev == "error")
    n_warnings = sum(1 for sev, *_ in issues if sev == "warning")

    _console.print(f"\n[bold cyan]Lint:[/bold cyan] {script_label}")
    _console.print()

    if not issues:
        _console.print("[bold green]No issues found.[/bold green]")
        _console.print()
        return 0

    # Sort: errors first, then warnings; within each group sort by line number.
    _sev_order = {"error": 0, "warning": 1}
    sorted_issues = sorted(issues, key=lambda i: (_sev_order.get(i[0], 9), i[2]))

    # Compute the widest location string so columns align.
    locs: list[str] = []
    for _, source, line_no, _ in sorted_issues:
        locs.append(f"{source}:{line_no}" if line_no else source)
    loc_width = max(len(loc) for loc in locs) if locs else 0

    for (severity, _source, _line_no, message), loc in zip(sorted_issues, locs):
        pad = " " * (loc_width - len(loc))
        if severity == "error":
            _console.print(f"  [bold red]ERROR  [/bold red]  [dim]{loc}[/dim]{pad}  {message}")
        else:
            _console.print(f"  [bold yellow]WARNING[/bold yellow]  [dim]{loc}[/dim]{pad}  {message}")

    _console.print()
    parts = []
    if n_errors:
        parts.append(f"[bold red]{n_errors} error{'s' if n_errors != 1 else ''}[/bold red]")
    if n_warnings:
        parts.append(f"[bold yellow]{n_warnings} warning{'s' if n_warnings != 1 else ''}[/bold yellow]")
    _console.print("  " + ", ".join(parts))
    _console.print()

    return 1 if n_errors > 0 else 0
