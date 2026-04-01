from __future__ import annotations

"""
Interactive debug REPL metacommand handler for execsql.

Implements ``x_breakpoint`` — the ``BREAKPOINT`` metacommand — which pauses
script execution and drops into an interactive read-eval-print loop.

The REPL allows the user to:

- Inspect and print substitution variables.
- Run ad-hoc SQL queries against the current database.
- Step through the script one statement at a time.
- Resume or abort execution.

In non-interactive environments (CI, piped input, ``sys.stdin.isatty()`` is
``False``) the metacommand is silently skipped so automated pipelines are not
blocked.
"""

import sys
from typing import Any

import execsql.state as _state

__all__ = ["x_breakpoint"]

# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
execsql debug REPL commands:
  continue  c        Resume script execution
  abort     q quit   Halt the script (exit 1)
  vars               List all substitution variables and their values
  $VARNAME           Print a single variable's value  (also &VAR, @VAR)
  SELECT ...;        Run ad-hoc SQL against the current database
  next      n        Execute the next statement then pause again (step mode)
  stack              Show the command-list stack (script name, line, depth)
  help               Show this help text
"""


def x_breakpoint(**kwargs: Any) -> None:
    """Pause execution and enter the interactive debug REPL.

    If ``sys.stdin`` is not a TTY (CI, piped input), the metacommand is
    silently skipped — scripts will not hang in automation.

    Args:
        **kwargs: Keyword arguments injected by the dispatch table (unused).
    """
    if not sys.stdin.isatty():
        return
    _debug_repl()


# ---------------------------------------------------------------------------
# REPL core
# ---------------------------------------------------------------------------


def _debug_repl() -> None:
    """Interactive read-eval-print loop for script debugging.

    Reads commands from stdin until the user types ``continue`` or ``abort``,
    or until EOF / KeyboardInterrupt.
    """
    try:
        import readline as _readline  # noqa: F401 — side-effect: enables history/arrow keys
    except ImportError:
        pass  # readline not available on Windows; continue without it

    _write("\n[Breakpoint] Script paused. Type 'help' for commands, 'continue' to resume.\n")

    while True:
        try:
            line = input("execsql debug> ").strip()
        except EOFError:
            _write("\n")
            return  # Ctrl-D → continue
        except KeyboardInterrupt:
            _write("\n")
            return  # Ctrl-C → continue

        if not line:
            continue

        lower = line.lower()

        if lower in ("continue", "c"):
            return
        elif lower in ("abort", "q", "quit"):
            raise SystemExit(1)
        elif lower == "help":
            _write(_HELP_TEXT)
        elif lower == "vars":
            _print_all_vars()
        elif lower == "stack":
            _print_stack()
        elif lower in ("next", "n"):
            _enable_step_mode()
            return
        elif line[0] in ("$", "&", "@"):
            _print_var(line)
        elif line.rstrip().endswith(";"):
            _run_sql(line)
        else:
            _write(f"Unknown command: {line!r}. Type 'help' for available commands.\n")


# ---------------------------------------------------------------------------
# REPL command implementations
# ---------------------------------------------------------------------------


def _write(text: str) -> None:
    """Write *text* to the execsql output stream (falls back to stdout)."""
    output = _state.output
    if output is not None:
        output.write(text)
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


def _print_all_vars() -> None:
    """Print all substitution variables and their current values."""
    subvars = _state.subvars
    if subvars is None:
        _write("  (no substitution variables defined)\n")
        return
    items = subvars.substitutions  # list of (name, value) tuples
    if not items:
        _write("  (no substitution variables defined)\n")
        return
    # Compute column width for aligned output.
    max_name = max((len(name) for name, _ in items), default=0)
    for name, value in sorted(items):
        _write(f"  {name:<{max_name}}  =  {value!r}\n")


def _print_var(varname: str) -> None:
    """Print the value of a single substitution variable.

    Args:
        varname: The variable reference as typed by the user, e.g. ``$FOO``.
    """
    subvars = _state.subvars
    if subvars is None:
        _write(f"  {varname}: (substitution variables not initialised)\n")
        return
    # Try the name as typed first, then without the sigil prefix ($, &, @, #, ~).
    # SUB creates variables without a prefix (e.g., "logfile"), but users
    # naturally type "$logfile" at the prompt.
    value = subvars.varvalue(varname)
    if value is None and len(varname) > 1 and varname[0] in "$&@#~":
        value = subvars.varvalue(varname[1:])
    if value is None:
        _write(f"  {varname}: (undefined)\n")
    else:
        _write(f"  {varname} = {value!r}\n")


def _print_stack() -> None:
    """Print the current command-list stack (script name, line number, depth)."""
    stack = _state.commandliststack
    if not stack:
        _write("  (command list stack is empty)\n")
        return
    _write(f"  Stack depth: {len(stack)}\n")
    for depth, cmdlist in enumerate(stack):
        listname = getattr(cmdlist, "listname", "<unknown>")
        cmdptr = getattr(cmdlist, "cmdptr", 0)
        _write(f"  [{depth}] {listname}  (cursor at index {cmdptr})\n")


def _run_sql(sql: str) -> None:
    """Execute ad-hoc SQL against the current database and pretty-print the results.

    Args:
        sql: A complete SQL statement ending with a semicolon.
    """
    dbs = _state.dbs
    if dbs is None:
        _write("  (no database connection is active)\n")
        return
    db = dbs.current()
    if db is None:
        _write("  (no database connection is active)\n")
        return
    try:
        colnames, rows = db.select_data(sql)
    except Exception as exc:
        _write(f"  SQL error: {exc}\n")
        return

    if not colnames:
        _write("  (query returned no columns)\n")
        return

    # Build a simple text table.
    col_widths = [len(c) for c in colnames]
    str_rows: list[list[str]] = []
    for row in rows:
        str_row = [str(v) if v is not None else "NULL" for v in row]
        str_rows.append(str_row)
        for i, cell in enumerate(str_row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header = "| " + " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(colnames)) + " |"
    _write(sep + "\n")
    _write(header + "\n")
    _write(sep + "\n")
    for str_row in str_rows:
        data_line = "| " + " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(str_row)) + " |"
        _write(data_line + "\n")
    _write(sep + "\n")
    row_word = "row" if len(str_rows) == 1 else "rows"
    _write(f"  ({len(str_rows)} {row_word})\n")


def _enable_step_mode() -> None:
    """Activate step mode so the engine re-enters the REPL after the next statement."""
    _state.step_mode = True
