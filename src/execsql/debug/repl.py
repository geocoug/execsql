from __future__ import annotations

"""Interactive debug REPL metacommand handler for execsql.

Implements ``x_breakpoint`` — the ``BREAKPOINT`` metacommand — which pauses
script execution and drops into an interactive read-eval-print loop.

The REPL allows the user to:

- Inspect and print substitution variables.
- Run ad-hoc SQL queries against the current database.
- Step through the script one statement at a time.
- Resume or abort execution.

Dispatch is two-way (psql-style): input starting with ``.`` is a REPL
command (``.continue``, ``.vars [VAR]``, ``.next``, etc.), everything
else is SQL.  Multi-line SQL is supported: any non-``.`` input opens a
buffer whose continuation prompt is ``  ...        > ``, accumulating
until a line ends with ``;``.  ``.cancel`` (or Ctrl-C / EOF) discards
the partial buffer.

Variable lookup is explicit — ``.vars LOGFILE`` prints one variable;
``.vars`` lists them all.  There is no bare-identifier lookup, so any
SQL keyword you type starts a buffer the moment you press Enter.

The trailing ``;`` is the SQL terminator both within one line and across
multiple lines — the REPL has no read-only mode and DDL on most adapters
is irreversible, so requiring ``;`` is a small intent gate against
accidental DML/DDL on mistyped input.  Use SQL ``BEGIN; … ROLLBACK;`` to
bracket exploratory DML if you need recoverability.

Errors raised by any REPL helper — bad SQL, malformed dot-commands, etc. —
are caught at the loop level so the session re-prompts instead of escaping
through ``x_breakpoint`` and being stamped as a "Metacommand error".

In non-interactive environments (CI, piped input, ``sys.stdin.isatty()`` is
``False``) the metacommand is silently skipped so automated pipelines are not
blocked.
"""

import os
import sys
from pathlib import Path
from typing import Any

import execsql.state as _state

__all__ = ["x_breakpoint"]

# ---------------------------------------------------------------------------
# ANSI color support — auto-detected, respects NO_COLOR / EXECSQL_NO_COLOR
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_ITALIC = "\033[3m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"


_color_cache: bool | None = None


def _use_color() -> bool:
    """Return True if the output stream supports ANSI color.

    Checks ``NO_COLOR`` and ``EXECSQL_NO_COLOR`` environment variables first
    (either set → color off).  Then tests whether the active output stream
    reports itself as a TTY.

    The result is cached after the first call; call ``_reset_color_cache()``
    to force re-evaluation (e.g. when entering the REPL).
    """
    global _color_cache  # noqa: PLW0603
    if _color_cache is not None:
        return _color_cache
    if os.environ.get("NO_COLOR") is not None or os.environ.get("EXECSQL_NO_COLOR") is not None:
        _color_cache = False
    else:
        output = _state.output
        if output is not None and hasattr(output, "isatty"):
            _color_cache = output.isatty()
        else:
            # WriteHooks (the default _state.output) has no isatty — fall through
            # to check the underlying stream it would write to.
            _color_cache = sys.stdout.isatty()
    return _color_cache


def _reset_color_cache() -> None:
    """Clear the cached color decision so it is re-evaluated on next use."""
    global _color_cache  # noqa: PLW0603
    _color_cache = None


def _c(code: str, text: str) -> str:
    """Wrap *text* in an ANSI escape sequence when color is enabled.

    Returns plain *text* unchanged when ``_use_color()`` is False so that
    tests and non-TTY environments receive undecorated strings.

    Args:
        code: One or more ANSI escape codes (e.g. ``_BOLD + _CYAN``).
        text: The text to colorize.

    Returns:
        ``f"{code}{text}{_RESET}"`` when color is on, else *text* unchanged.
    """
    if not _use_color():
        return text
    return f"{code}{text}{_RESET}"


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------

_HELP_COMMANDS = [
    (".continue", ".c", "Resume script execution"),
    (".quit", ".q", "Halt the script (exit 1)"),
    (".vars", ".v", "List all execsql substitution variables"),
    (".vars VAR", ".v VAR", "Print the value of a single variable (e.g. .vars logfile)"),
    (".next", ".n", "Execute the next statement then pause again (step mode)"),
    (".where", ".w", "Show the current script location and upcoming statement"),
    (".stack", "", "Show the command-list stack (script name, line, depth)"),
    (".set VAR VAL", ".s", "Set or update a substitution variable"),
    (".scripts", "", "List all registered SCRIPT definitions"),
    (".scripts NAME", "", "Show detail for a specific SCRIPT"),
    (".cancel", "", "Discard a partial multi-line SQL buffer"),
    (".help", ".h", "Show this help text"),
]

_HELP_OTHER = [
    ("SELECT ...;", "Run SQL — multi-line accepted, terminate with ';' to execute"),
]

_HELP_CMD_WIDTH = 13  # width of the command column
_HELP_SHORT_WIDTH = 7  # width of the shortcut column


def _format_help() -> str:
    """Build the help text with optional ANSI color."""
    lines: list[str] = []
    lines.append(f"{_c(_BOLD, 'execsql debug REPL')} {_c(_DIM, '— all commands start with')} {_c(_CYAN, '.')}")
    lines.append("")
    for cmd, short, desc in _HELP_COMMANDS:
        cmd_col = _c(_CYAN, cmd.ljust(_HELP_CMD_WIDTH))
        short_col = _c(_CYAN, short.ljust(_HELP_SHORT_WIDTH)) if short else " " * _HELP_SHORT_WIDTH
        lines.append(f"  {cmd_col}  {short_col}  {desc}")
    lines.append("")
    lines.append(f"{_c(_BOLD, 'Everything else:')}")
    for cmd, desc in _HELP_OTHER:
        cmd_col = _c(_DIM, cmd.ljust(_HELP_CMD_WIDTH + _HELP_SHORT_WIDTH + 2))
        lines.append(f"  {cmd_col}  {desc}")
    lines.append("")
    return "\n".join(lines) + "\n"


_WHERE_TRUNCATE = 120


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


def _write_rule(label: str) -> None:
    """Print a horizontal rule with an embedded label.

    The rule is ``──<label>`` followed by a fixed-width suffix of dashes,
    giving a consistent visual separator regardless of terminal width.

    Args:
        label: Text (may include ANSI codes) to embed in the rule.
    """
    _write(f"{_c(_DIM, '──')}{label}{_c(_DIM, '─' * 40)}\n")


def _debug_repl(*, step: bool = False) -> None:
    """Interactive read-eval-print loop for script debugging.

    Reads commands from stdin until the user types ``.continue`` or ``.abort``,
    or until EOF / KeyboardInterrupt.

    Args:
        step: When ``True``, the entry banner says "Step" instead of
            "Breakpoint" to indicate the REPL was re-entered via step mode.
    """
    _reset_color_cache()
    try:
        import readline as _readline  # noqa: F401 — side-effect: enables history/arrow keys
    except ImportError:
        pass  # readline not available on Windows; continue without it

    label_word = "Step" if step else "Breakpoint"
    lc = _state.last_command
    if lc is not None:
        location = f"{Path(lc.source).name}:{lc.line_no}"
        type_tag = lc.command_type
        text = lc.command.commandline()
        if len(text) > _WHERE_TRUNCATE:
            text = text[:_WHERE_TRUNCATE] + "..."
        rule_label = f" {_c(_BOLD + _YELLOW, label_word)} {_c(_DIM, '──')} {_c(_CYAN, location)} "
    else:
        type_tag = None
        text = None
        location = "(position unknown)"
        rule_label = f" {_c(_BOLD + _YELLOW, label_word)} "

    _write("\n")
    _write_rule(rule_label)
    if type_tag and text:
        _write(f"  {_c(_DIM + _GREEN, '(' + type_tag + ')')} {text}\n")
    _hint_help = _c(_DIM, "'.help'")
    _hint_c = _c(_DIM, "'.c'")
    _write(f"  Type {_hint_help} for commands, {_hint_c} to resume.\n\n")

    sql_buffer: list[str] = []

    while True:
        prompt = "  ...        > " if sql_buffer else "execsql debug> "
        try:
            line = input(prompt).strip()
        except EOFError:
            if sql_buffer:
                sql_buffer.clear()
                _write("\n  (input discarded)\n")
                continue
            _write("\n")
            return
        except KeyboardInterrupt:
            if sql_buffer:
                sql_buffer.clear()
                _write("\n  (input discarded)\n")
                continue
            _write("\n")
            return

        if not line:
            continue

        try:
            if line.startswith("."):
                cmd = line[1:].strip().lower()
                if cmd == "cancel":
                    if sql_buffer:
                        sql_buffer.clear()
                        _write("  (input discarded)\n")
                    continue
                _handle_dot_command(line)
                if cmd in ("continue", "c"):
                    return
                if cmd in ("abort", "q", "quit"):
                    return
                if cmd in ("next", "n"):
                    return
                continue

            if sql_buffer:
                sql_buffer.append(line)
                joined = " ".join(sql_buffer)
                if joined.rstrip().endswith(";"):
                    _run_sql(joined)
                    sql_buffer.clear()
                continue

            if line.rstrip().endswith(";"):
                _run_sql(line)
                continue

            sql_buffer.append(line)
        except SystemExit:
            raise
        except KeyboardInterrupt:
            sql_buffer.clear()
            _write("\n  (interrupted)\n")
            continue
        except Exception as exc:
            sql_buffer.clear()
            _write(f"  {_c(_RED, 'Error:')} {exc}\n")
            continue


def _handle_dot_command(line: str) -> None:
    """Dispatch a dot-prefixed REPL command."""
    # Strip the leading dot and normalize
    cmd = line[1:].strip().lower()

    if cmd in ("continue", "c"):
        return  # caller checks and returns from _debug_repl
    elif cmd in ("abort", "q", "quit"):
        raise SystemExit(1)
    elif cmd in ("help", "h"):
        _write(_format_help())
    elif cmd in ("vars", "v"):
        _print_all_vars()
    elif cmd.startswith("vars ") or cmd.startswith("v "):
        rest = cmd.split(None, 1)[1].strip() if " " in cmd else ""
        if rest:
            _print_var(rest)
        else:
            _print_all_vars()
    elif cmd in ("where", "w"):
        _print_where()
    elif cmd == "stack":
        _print_stack()
    elif cmd in ("next", "n"):
        _enable_step_mode()
    elif cmd.startswith("set ") or cmd == "set":
        # .set VAR VAL — set or update a substitution variable
        rest = cmd[4:].strip() if cmd.startswith("set ") else ""
        if not rest:
            _write("  Usage: .set VAR VALUE\n")
        else:
            parts = rest.split(None, 1)
            varname = parts[0]
            value = parts[1] if len(parts) > 1 else ""
            _set_var(varname, value)
    elif cmd.startswith("s ") or cmd == "s":
        # .s VAR VAL — shorthand for .set
        rest = cmd[2:].strip() if cmd.startswith("s ") else ""
        if not rest:
            _write("  Usage: .s VAR VALUE\n")
        else:
            parts = rest.split(None, 1)
            varname = parts[0]
            value = parts[1] if len(parts) > 1 else ""
            _set_var(varname, value)
    elif cmd.startswith("scripts"):
        rest = cmd[7:].strip()
        if rest:
            _print_script_detail(rest)
        else:
            _print_scripts()
    else:
        _write(f"  {_c(_RED, 'Unknown command:')} {line!r}. Type '.help' for available commands.\n")


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


def _print_where() -> None:
    """Print the current script location and the upcoming statement.

    Reads ``_state.last_command`` (a :class:`ScriptCmd`) and displays the
    filename, line number, command type, and (truncated) statement text.
    If ``last_command`` is ``None``, reports that the position is unknown.
    """
    lc = _state.last_command
    if lc is None:
        _write("  (position unknown)\n")
        return
    filename = Path(lc.source).name
    location = f"{filename}:{lc.line_no}"
    rule_label = f" {_c(_BOLD + _YELLOW, 'Location')} {_c(_DIM, '──')} {_c(_CYAN, location)} "
    _write_rule(rule_label)
    text = lc.command.commandline()
    if len(text) > _WHERE_TRUNCATE:
        text = text[:_WHERE_TRUNCATE] + "..."
    _write(f"  {_c(_DIM + _GREEN, '(' + lc.command_type + ')')} {text}\n\n")


def _print_all_vars(*, include_env: bool = False) -> None:
    """Print substitution variables grouped by type."""
    subvars = _state.subvars
    if subvars is None:
        _write("  (no substitution variables defined)\n\n")
        return
    items = list(subvars.substitutions)  # list of (name, value) tuples
    # Include ~local and #param variables from the current scope frame.
    localvars = _state.current_localvars()
    if localvars is not None:
        items.extend(localvars.substitutions)
    paramvals = _state.current_paramvals()
    if paramvals is not None:
        items.extend(paramvals.substitutions)
    if not items:
        _write("  (no substitution variables defined)\n\n")
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

    _write_rule(f" {_c(_BOLD + _YELLOW, 'Variables')} ")

    def _print_group(label: str, group: list[tuple[str, str]]) -> None:
        if not group:
            return
        _write(f"  {_c(_BOLD, label)}:\n")
        max_name = max(len(n) for n, _ in group)
        for name, value in group:
            # Pre-compute padding from RAW name length — the format-spec ``:<{max_name}``
            # form measures the colored string, which (when ANSI is on) is ~9 chars
            # longer per wrap and breaks the column alignment.
            pad = " " * (max_name - len(name))
            _write(f"    {_c(_CYAN, name)}{pad}  {_c(_DIM, '=')}  {value}\n")

    _print_group("User", user_vars)
    _print_group("System ($)", system_vars)
    _print_group("Local (~)", local_vars)
    _print_group("Counter (@)", counter_vars)
    if include_env:
        _print_group("Environment (&)", env_vars)

    if not any([user_vars, system_vars, local_vars, counter_vars]):
        if env_vars:
            _write("  (no script variables defined — use '.vars all' to see environment variables)\n")
        else:
            _write("  (no variables defined)\n")
    _write("\n")


def _print_var(varname: str) -> None:
    """Print the value of a single substitution variable.

    Tries the name as typed, then with the sigil prefix stripped.
    Checks both global subvars and the current stack frame's local/param vars.
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
    # Check current scope frame for ~local and #param variables.
    if value is None:
        localvars = _state.current_localvars()
        if localvars is not None:
            value = localvars.varvalue(varname)
        if value is None:
            paramvals = _state.current_paramvals()
            if paramvals is not None:
                value = paramvals.varvalue(varname)
    if value is None:
        _write(f"  {_c(_CYAN, varname)}: {_c(_DIM, '(undefined)')}\n")
    else:
        _write(f"  {_c(_CYAN, varname)} {_c(_DIM, '=')} {value}\n")


def _print_stack() -> None:
    """Print the unified AST execution stack.

    Shows every nesting construct the executor is currently inside:
    ``<main>`` script, ``EXECUTE SCRIPT`` calls, ``INCLUDE``'d files,
    ``IF``/``ELSEIF``/``ELSE`` branches, ``LOOP`` iterations (with iteration
    count), and ``BATCH`` blocks. Each frame shows source file and line.
    """
    stack = _state.ast_exec_stack
    if not stack:
        _write("  (execution stack is empty)\n\n")
        return
    _write_rule(f" {_c(_BOLD + _YELLOW, 'Stack')} ")
    _write(f"  {_c(_DIM, 'depth:')} {len(stack)}\n")
    for depth, frame in enumerate(stack):
        kind_label = frame.kind.upper().replace("LOOP_", "LOOP ")
        # Build the right-hand description per kind
        if frame.kind in ("if", "elseif"):
            desc = f"{kind_label}  {frame.label}"
        elif frame.kind == "else":
            desc = kind_label
        elif frame.kind in ("loop_while", "loop_until"):
            desc = f"{kind_label}  {frame.label}  {_c(_DIM, f'iter={frame.iteration}')}"
        elif frame.kind == "script":
            params = ""
            if frame.params:
                params = "(" + ", ".join(f"{k}={v!r}" for k, v in frame.params.items()) + ")"
            iter_suffix = f"  {_c(_DIM, f'iter={frame.iteration}')}" if frame.iteration else ""
            desc = f"SCRIPT {frame.label}{params}{iter_suffix}"
        elif frame.kind == "include":
            desc = f"INCLUDE {frame.label}"
        elif frame.kind == "batch":
            desc = "BATCH"
        elif frame.kind == "main":
            desc = frame.label or "<main>"
        else:
            desc = f"{kind_label}  {frame.label}"
        src = ""
        if frame.source:
            src_name = frame.source.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            src = _c(_DIM, f"  {src_name}:{frame.line}" if frame.line else f"  {src_name}")
        _write(f"  [{depth}] {desc}{src}\n")
    _write("\n")


def _run_sql(sql: str) -> None:
    """Execute ad-hoc SQL and pretty-print results or affected rowcount."""
    dbs = _state.dbs
    if dbs is None:
        _write("  (no database connection is active)\n")
        return
    db = dbs.current()
    if db is None:
        _write("  (no database connection is active)\n")
        return

    try:
        with db._cursor() as curs:
            try:
                curs.execute(sql)
            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                _write(f"  {_c(_RED, 'SQL error:')} {exc}\n")
                return

            try:
                _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
            except Exception:
                pass

            if curs.description is None:
                rowcount = curs.rowcount if curs.rowcount is not None else -1
                if rowcount >= 0:
                    row_word = "row" if rowcount == 1 else "rows"
                    _write(f"  {_c(_DIM, f'({rowcount} {row_word} affected)')}\n")
                else:
                    _write(f"  {_c(_DIM, '(statement executed)')}\n")
                return

            colnames = [d[0] for d in curs.description]
            rows = curs.fetchall()
    except Exception as exc:
        _write(f"  {_c(_RED, 'SQL error:')} {exc}\n")
        return

    if not colnames:
        _write("  (query returned no columns)\n")
        return

    # Build a simple text table.
    col_widths = [len(c) for c in colnames]
    str_rows: list[list[str]] = []
    for row in rows:
        str_row = ["NULL" if v is None else str(v) for v in row]
        str_rows.append(str_row)
        for i, cell in enumerate(str_row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = _c(_DIM, "+-" + "-+-".join("-" * w for w in col_widths) + "-+")
    # Header: column names in bold
    header_cells = " | ".join(_c(_BOLD, c.ljust(col_widths[i])) for i, c in enumerate(colnames))
    header = _c(_DIM, "| ") + header_cells + _c(_DIM, " |")
    _write("  " + sep + "\n")
    _write("  " + header + "\n")
    _write("  " + sep + "\n")
    for str_row in str_rows:
        cells = " | ".join(
            _c(_DIM + _ITALIC, "NULL".ljust(col_widths[i])) if cell == "NULL" else cell.ljust(col_widths[i])
            for i, cell in enumerate(str_row)
        )
        data_line = _c(_DIM, "| ") + cells + _c(_DIM, " |")
        _write("  " + data_line + "\n")
    _write("  " + sep + "\n")
    row_word = "row" if len(str_rows) == 1 else "rows"
    _write(f"  {_c(_DIM, f'({len(str_rows)} {row_word})')}\n")


def _enable_step_mode() -> None:
    """Activate step mode so the engine re-enters the REPL after the next statement."""
    _state.step_mode = True


def _set_var(varname: str, value: str) -> None:
    """Set or update a substitution variable in the current session.

    Routes ~local variables to the current stack frame's localvars (matching
    the behavior of ``x_sub`` / ``get_subvarset``).  All other variables go
    to the global subvars pool.

    Args:
        varname: The variable name (with optional sigil prefix).
        value: The value to assign to the variable.
    """
    subvars = _state.subvars
    if subvars is None:
        _write("  Error: substitution variables are not initialised.\n")
        return
    if varname.startswith("~"):
        localvars = _state.current_localvars()
        if localvars is not None:
            localvars.add_substitution(varname, value)
        else:
            subvars.add_substitution(varname, value)
    else:
        subvars.add_substitution(varname, value)
    _write(f"  {_c(_CYAN, varname)} {_c(_DIM, '=')} {value}\n")


def _print_scripts() -> None:
    """Print all registered SCRIPT definitions."""
    from execsql.metacommands.debug import _format_script_signature, _format_script_source

    scripts = _state.ast_scripts
    if not scripts:
        _write("  (no scripts registered)\n\n")
        return
    _write_rule(f" {_c(_BOLD + _YELLOW, 'Scripts')} {_c(_DIM, f'({len(scripts)})')} ")
    sigs = {name: _format_script_signature(name, block.param_defs) for name, block in scripts.items()}
    max_sig = max(len(s) for s in sigs.values())
    for name, block in scripts.items():
        sig = sigs[name]
        src = _format_script_source(block.span)
        _write(f"  {_c(_CYAN, sig):<{max_sig + len(_CYAN) + len(_RESET)}}  {_c(_DIM, src)}\n")
    _write("\n")


def _print_script_detail(name: str) -> None:
    """Print detail for a single SCRIPT definition."""
    from execsql.metacommands.debug import _format_script_signature, _format_script_source

    script_name = name.lower()
    scripts = _state.ast_scripts
    if script_name not in scripts:
        _write(f"  {_c(_RED, 'No script named')} {_c(_CYAN, repr(script_name))} {_c(_RED, 'is registered.')}\n")
        return
    block = scripts[script_name]
    sig = _format_script_signature(block.name, block.param_defs)
    src = _format_script_source(block.span, full_path=True)
    _write_rule(f" {_c(_BOLD + _YELLOW, 'Script')} {_c(_DIM, '──')} {_c(_CYAN, sig)} ")
    _write(f"  {_c(_BOLD, 'Source:')}     {src}\n")
    if block.param_defs:
        _write(f"  {_c(_BOLD, 'Parameters:')}\n")
        max_name = max(len(p.name) for p in block.param_defs)
        for p in block.param_defs:
            if p.default is not None:
                _write(
                    f"    {_c(_CYAN, p.name):<{max_name + len(_CYAN) + len(_RESET)}}  {_c(_DIM, f'(optional, default: {p.default})')}\n",
                )
            else:
                _write(f"    {_c(_CYAN, p.name):<{max_name + len(_CYAN) + len(_RESET)}}  {_c(_DIM, '(required)')}\n")
    else:
        _write(f"  {_c(_BOLD, 'Parameters:')} (none)\n")
    if block.doc:
        _write("\n")
        for doc_line in block.doc.split("\n"):
            _write(f"  {_c(_DIM, doc_line)}\n")
    _write("\n")
