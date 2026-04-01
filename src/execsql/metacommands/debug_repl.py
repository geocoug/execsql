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

All REPL commands are dot-prefixed (``.continue``, ``.vars``, ``.next``)
to avoid ambiguity with variable names and SQL.  Anything not starting
with ``.`` is treated as either a variable lookup (if it matches a known
variable) or SQL (if it ends with ``;``).

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
execsql debug REPL — all commands start with '.'

  .continue  .c       Resume script execution
  .abort     .q       Halt the script (exit 1)
  .vars               List user, system, local, and counter variables
  .vars all           Include environment variables (&) in the listing
  .next      .n       Execute the next statement then pause again (step mode)
  .stack              Show the command-list stack (script name, line, depth)
  .help               Show this help text

Everything else:
  varname             Print a variable's value (e.g. logfile, $ARG_1, &HOME)
  SELECT ...;         Run ad-hoc SQL against the current database
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

    Reads commands from stdin until the user types ``.continue`` or ``.abort``,
    or until EOF / KeyboardInterrupt.
    """
    try:
        import readline as _readline  # noqa: F401 — side-effect: enables history/arrow keys
    except ImportError:
        pass  # readline not available on Windows; continue without it

    _write("\n[Breakpoint] Script paused. Type '.help' for commands, '.c' to resume.\n")

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

        # Dot-prefixed → REPL command
        if line.startswith("."):
            _handle_dot_command(line)
            if line.lower().lstrip(".") in ("continue", "c"):
                return
            if line.lower().lstrip(".") in ("abort", "q", "quit"):
                # _handle_dot_command already raised SystemExit, but guard anyway
                return
            if line.lower().lstrip(".") in ("next", "n"):
                return
            continue

        # SQL (ends with semicolon)
        if line.rstrip().endswith(";"):
            _run_sql(line)
            continue

        # Everything else → variable lookup
        _print_var(line)


def _handle_dot_command(line: str) -> None:
    """Dispatch a dot-prefixed REPL command."""
    # Strip the leading dot and normalize
    cmd = line[1:].strip().lower()

    if cmd in ("continue", "c"):
        return  # caller checks and returns from _debug_repl
    elif cmd in ("abort", "q", "quit"):
        raise SystemExit(1)
    elif cmd == "help":
        _write(_HELP_TEXT)
    elif cmd == "vars all":
        _print_all_vars(include_env=True)
    elif cmd == "vars":
        _print_all_vars()
    elif cmd == "stack":
        _print_stack()
    elif cmd in ("next", "n"):
        _enable_step_mode()
    else:
        _write(f"  Unknown command: {line!r}. Type '.help' for available commands.\n")


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


def _print_all_vars(*, include_env: bool = False) -> None:
    """Print substitution variables grouped by type."""
    subvars = _state.subvars
    if subvars is None:
        _write("  (no substitution variables defined)\n")
        return
    items = subvars.substitutions  # list of (name, value) tuples
    if not items:
        _write("  (no substitution variables defined)\n")
        return

    # Group by prefix.
    user_vars: list[tuple[str, str]] = []
    system_vars: list[tuple[str, str]] = []
    counter_vars: list[tuple[str, str]] = []
    local_vars: list[tuple[str, str]] = []
    env_vars: list[tuple[str, str]] = []

    for name, value in sorted(items):
        if name.startswith("&"):
            env_vars.append((name, value))
        elif name.startswith("~"):
            local_vars.append((name, value))
        elif name.startswith("@"):
            counter_vars.append((name, value))
        elif name.startswith("$"):
            system_vars.append((name, value))
        else:
            user_vars.append((name, value))

    def _print_group(label: str, group: list[tuple[str, str]]) -> None:
        if not group:
            return
        _write(f"  {label}:\n")
        max_name = max(len(n) for n, _ in group)
        for name, value in group:
            _write(f"    {name:<{max_name}}  =  {value}\n")

    _print_group("User variables", user_vars)
    _print_group("System variables ($)", system_vars)
    _print_group("Local variables (~)", local_vars)
    _print_group("Counter variables (@)", counter_vars)
    if include_env:
        _print_group("Environment variables (&)", env_vars)

    if not any([user_vars, system_vars, local_vars, counter_vars]):
        if env_vars:
            _write("  (no script variables defined — use '.vars all' to see environment variables)\n")
        else:
            _write("  (no variables defined)\n")


def _print_var(varname: str) -> None:
    """Print the value of a single substitution variable.

    Tries the name as typed, then with the sigil prefix stripped.
    """
    subvars = _state.subvars
    if subvars is None:
        _write(f"  {varname}: (substitution variables not initialised)\n")
        return
    # Try the name as typed first, then without the sigil prefix ($, &, @, #, ~).
    # SUB creates variables without a prefix (e.g., "logfile"), but users
    # may type "$logfile" at the prompt.
    value = subvars.varvalue(varname)
    if value is None and len(varname) > 1 and varname[0] in "$&@#~":
        value = subvars.varvalue(varname[1:])
    if value is None:
        _write(f"  {varname}: (undefined)\n")
    else:
        _write(f"  {varname} = {value}\n")


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
    """Execute ad-hoc SQL against the current database and pretty-print the results."""
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
