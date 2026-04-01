"""Static analysis (lint) for execsql scripts.

:func:`_lint_script` inspects a parsed :class:`~execsql.script.CommandList`
for common structural problems without connecting to a database or executing
any commands.

Checks performed
----------------
1. **Unmatched IF / ENDIF** — mismatched nesting depth (error).
2. **Unmatched LOOP / END LOOP** — mismatched nesting depth (error).
3. **Unmatched BEGIN BATCH / END BATCH** — mismatched nesting depth (error).
4. **Potentially undefined variables** — ``!!$VAR!!`` tokens not preceded by a
   ``SUB`` metacommand in the same parsed command list and not in the set of
   built-in variables (warning).
5. **Missing INCLUDE files** — INCLUDE target does not exist on disk relative
   to the script directory (warning).
6. **Empty script** — no commands found (warning).

The function walks ``CommandList.cmdlist`` and also descends into any
``CommandList`` objects stored in ``_state.savedscripts`` (i.e. named scripts
defined with ``BEGIN SCRIPT … END SCRIPT`` in the same file).  SCRIPT blocks
are analysed in isolation; nesting counters reset for each block.

Exit-code contract
------------------
- Returns ``1`` when at least one **error**-severity issue is found.
- Returns ``0`` when only warnings (or nothing) are found.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execsql.script.engine import CommandList

__all__ = ["_lint_script"]


# ---------------------------------------------------------------------------
# Compiled patterns for metacommand recognition
# ---------------------------------------------------------------------------

# IF block — "IF(...)" block form (single-command, no ENDIF needed)
_RX_IF_INLINE = re.compile(
    r"^\s*IF\s*\(\s*.+\s*\)\s*\{.+\}\s*$",
    re.I,
)
# IF block form that opens a block requiring ENDIF
_RX_IF_BLOCK = re.compile(r"^\s*IF\s*\(\s*.+\s*\)\s*$", re.I)
_RX_ENDIF = re.compile(r"^\s*ENDIF\s*$", re.I)
_RX_ELSE = re.compile(r"^\s*ELSE\s*$", re.I)
_RX_ELSEIF = re.compile(r"^\s*ELSEIF\s*\(\s*.+\s*\)\s*$", re.I)
_RX_ANDIF = re.compile(r"^\s*ANDIF\s*\(\s*.+\s*\)\s*$", re.I)
_RX_ORIF = re.compile(r"^\s*ORIF\s*\(\s*.+\s*\)\s*$", re.I)

# LOOP … END LOOP
_RX_LOOP = re.compile(r"^\s*LOOP\s+(?:WHILE|UNTIL)\s*\(", re.I)
_RX_END_LOOP = re.compile(r"^\s*END\s+LOOP\s*$", re.I)

# BEGIN BATCH … END BATCH
_RX_BEGIN_BATCH = re.compile(r"^\s*BEGIN\s+BATCH\s*$", re.I)
_RX_END_BATCH = re.compile(r"^\s*END\s+BATCH\s*$", re.I)

# SUB <varname> <value> — defines a substitution variable
_RX_SUB = re.compile(r"^\s*SUB\s+(?P<name>[+~]?\w+)\s+", re.I)

# INCLUDE <file>
_RX_INCLUDE = re.compile(
    r"^\s*INCLUDE(?:\s+IF\s+EXISTS?)?\s+(?P<path>\S+.*?)\s*$",
    re.I,
)

# Variable reference — !!name!! where name may start with $, @, &, ~, #, +
_RX_VAR_REF = re.compile(r"!!([$@&~#+]?\w+)!!", re.I)

# Built-in system variables that are always defined (populated by _run before
# any script commands execute).  Variable names are stored without the leading
# ``$`` for case-insensitive set membership tests.
_BUILTIN_VARS: frozenset[str] = frozenset(
    {
        # Start-time / environment
        "SCRIPT_START_TIME",
        "SCRIPT_START_TIME_UTC",
        "DATE_TAG",
        "DATETIME_TAG",
        "DATETIME_UTC_TAG",
        "LAST_ROWCOUNT",
        "LAST_SQL",
        "LAST_ERROR",
        "ERROR_MESSAGE",
        "USER",
        "STARTING_PATH",
        "PATHSEP",
        "OS",
        "PYTHON_EXECUTABLE",
        "STARTING_SCRIPT",
        "STARTING_SCRIPT_NAME",
        "STARTING_SCRIPT_REVTIME",
        "RUN_ID",
        # Execution-time (set during runscripts — not available in --dry-run
        # but always defined before any script command can reference them)
        "CURRENT_TIME",
        "CURRENT_TIME_UTC",
        "CURRENT_SCRIPT",
        "CURRENT_SCRIPT_PATH",
        "CURRENT_SCRIPT_NAME",
        "CURRENT_SCRIPT_LINE",
        "SCRIPT_LINE",
        "CURRENT_DIR",
        "CURRENT_PATH",
        "CURRENT_ALIAS",
        "AUTOCOMMIT_STATE",
        "TIMER",
        "DB_USER",
        "DB_SERVER",
        "DB_NAME",
        "DB_NEED_PWD",
        "RANDOM",
        "UUID",
        "VERSION1",
        "VERSION2",
        "VERSION3",
        "CANCEL_HALT_STATE",
        "ERROR_HALT_STATE",
        "METACOMMAND_ERROR_HALT_STATE",
        "CONSOLE_WAIT_WHEN_ERROR_HALT_STATE",
        "CONSOLE_WAIT_WHEN_DONE_STATE",
        "CURRENT_DBMS",
        "CURRENT_DATABASE",
        "SYSTEM_CMD_EXIT_STATUS",
        # Connection-populated
        "DB_FILE",
        "DB_PORT",
        # Counter variables (@@name) are always valid — skip validation
    },
)


# ---------------------------------------------------------------------------
# Issue tuple helpers
# ---------------------------------------------------------------------------

_Issue = tuple[str, str, int, str]  # (severity, source, line_no, message)


def _error(source: str, line_no: int, message: str) -> _Issue:
    return ("error", source, line_no, message)


def _warning(source: str, line_no: int, message: str) -> _Issue:
    return ("warning", source, line_no, message)


# ---------------------------------------------------------------------------
# Core lint implementation
# ---------------------------------------------------------------------------


def _lint_cmdlist(
    cmdlist: CommandList,
    script_dir: Path | None,
    defined_vars: set[str],
) -> list[_Issue]:
    """Lint a single :class:`CommandList` and return any issues found.

    Args:
        cmdlist: The parsed command list to analyse.
        script_dir: Directory of the top-level script file, used for resolving
            relative INCLUDE paths.  ``None`` for inline (``-c``) scripts.
        defined_vars: Mutable set of variable names (without sigil) that have
            been defined by preceding ``SUB`` metacommands.  The caller passes
            in the set from the outer scope so that variables defined before an
            EXECUTE SCRIPT call are visible inside the script block when
            analysing top-level scripts.  For named-script analysis the caller
            passes a *copy* so that local definitions don't leak.

    Returns:
        List of ``(severity, source, line_no, message)`` issue tuples.
    """
    issues: list[_Issue] = []

    if_depth = 0
    if_open_locs: list[tuple[str, int]] = []  # (source, line_no) of unmatched IF

    loop_depth = 0
    loop_open_locs: list[tuple[str, int]] = []

    batch_depth = 0
    batch_open_locs: list[tuple[str, int]] = []

    for cmd in cmdlist.cmdlist:
        src = cmd.source
        lno = cmd.line_no
        stmt = cmd.command.statement

        if cmd.command_type == "sql":
            # SQL statements: check for variable references only
            for m in _RX_VAR_REF.finditer(stmt):
                _check_var_ref(m.group(1), src, lno, defined_vars, issues)
            continue

        # Metacommand checks
        for m in _RX_VAR_REF.finditer(stmt):
            _check_var_ref(m.group(1), src, lno, defined_vars, issues)

        # -- IF block (opens a block requiring ENDIF) --
        if _RX_IF_BLOCK.match(stmt) and not _RX_IF_INLINE.match(stmt):
            if_depth += 1
            if_open_locs.append((src, lno))

        elif _RX_ENDIF.match(stmt):
            if if_depth == 0:
                issues.append(_error(src, lno, "ENDIF without a matching preceding IF"))
            else:
                if_depth -= 1
                if_open_locs.pop()

        elif _RX_ELSEIF.match(stmt) or _RX_ELSE.match(stmt) or _RX_ANDIF.match(stmt) or _RX_ORIF.match(stmt):
            if if_depth == 0:
                kw = stmt.strip().split(None, 1)[0].upper()
                issues.append(_error(src, lno, f"{kw} without a matching preceding IF"))

        # -- LOOP --
        elif _RX_LOOP.match(stmt):
            loop_depth += 1
            loop_open_locs.append((src, lno))

        elif _RX_END_LOOP.match(stmt):
            if loop_depth == 0:
                issues.append(_error(src, lno, "END LOOP without a matching preceding LOOP"))
            else:
                loop_depth -= 1
                loop_open_locs.pop()

        # -- BATCH --
        elif _RX_BEGIN_BATCH.match(stmt):
            batch_depth += 1
            batch_open_locs.append((src, lno))

        elif _RX_END_BATCH.match(stmt):
            if batch_depth == 0:
                issues.append(_error(src, lno, "END BATCH without a matching preceding BEGIN BATCH"))
            else:
                batch_depth -= 1
                batch_open_locs.pop()

        # -- SUB variable definition --
        sub_m = _RX_SUB.match(stmt)
        if sub_m:
            varname = sub_m.group("name").lstrip("+~")
            defined_vars.add(varname.upper())

        # -- INCLUDE file existence --
        inc_m = _RX_INCLUDE.match(stmt)
        if inc_m:
            raw_path = inc_m.group("path").strip().strip("\"'")
            # Only check if no substitution variables are in the path
            if not _RX_VAR_REF.search(raw_path):
                _check_include_path(raw_path, script_dir, src, lno, stmt, issues)

    # Report unclosed blocks at end of command list
    for osrc, olno in if_open_locs:
        issues.append(_error(osrc, olno, "IF without a matching ENDIF"))
    for osrc, olno in loop_open_locs:
        issues.append(_error(osrc, olno, "LOOP without a matching END LOOP"))
    for osrc, olno in batch_open_locs:
        issues.append(_error(osrc, olno, "BEGIN BATCH without a matching END BATCH"))

    return issues


def _check_var_ref(
    raw_name: str,
    source: str,
    line_no: int,
    defined_vars: set[str],
    issues: list[_Issue],
) -> None:
    """Emit a warning if *raw_name* looks like an undefined user variable.

    Built-in system variables, environment-variable references (``&``-prefix),
    column variables (``@``-prefix), counter variables (``@@``), parameter
    variables (``#``-prefix), and ``$ARG_N`` are excluded from the check.

    Args:
        raw_name: Variable name token as captured from ``!!name!!`` (with sigil).
        source: Source file name for the issue location.
        line_no: Line number of the command containing the reference.
        defined_vars: Set of variable names (upper-case, no sigil) that have
            been defined by preceding SUB metacommands.
        issues: Issue list to append to.
    """
    if not raw_name:
        return

    sigil = raw_name[0] if raw_name[0] in ("$", "@", "&", "~", "#", "+") else ""
    name = raw_name[len(sigil) :]

    # Skip non-$ sigil prefixes — these are always resolved at runtime
    if sigil in ("@", "&", "~", "#", "+"):
        return

    # $ARG_N is set via -a/--assign-arg at invocation time
    if re.match(r"^ARG_\d+$", name, re.I):
        return

    # Built-in system variables
    if name.upper() in _BUILTIN_VARS:
        return

    # User-defined via SUB
    if name.upper() in defined_vars:
        return

    issues.append(
        _warning(
            source,
            line_no,
            f"Potentially undefined variable: !!{raw_name}!! "
            "(not defined by a preceding SUB; may be set by a config file or -a arg)",
        ),
    )


def _check_include_path(
    raw_path: str,
    script_dir: Path | None,
    source: str,
    line_no: int,
    stmt: str,
    issues: list[_Issue],
) -> None:
    """Warn if the INCLUDE target does not exist on disk.

    Args:
        raw_path: Unquoted file path string from the INCLUDE metacommand.
        script_dir: Directory of the top-level script file; used for relative
            path resolution.  ``None`` for inline scripts.
        source: Source file name for issue location.
        line_no: Line number of the INCLUDE command.
        stmt: Full metacommand statement text (for the IF EXISTS variant).
        issues: Issue list to append to.
    """
    # IF EXISTS variant — missing file is intentional; skip
    if re.match(r"^\s*INCLUDE\s+IF\s+EXISTS?", stmt, re.I):
        return

    p = Path(raw_path)
    if not p.is_absolute() and script_dir is not None:
        p = script_dir / p

    if not p.exists():
        issues.append(
            _warning(
                source,
                line_no,
                f"INCLUDE target does not exist: {raw_path!r}",
            ),
        )


def _lint_script(
    cmdlist: CommandList | None,
    script_path: str | None = None,
) -> list[_Issue]:
    """Perform static analysis on a parsed command list.

    Walks every :class:`~execsql.script.ScriptCmd` in *cmdlist* and any named
    scripts accumulated in ``_state.savedscripts`` (those defined with
    ``BEGIN SCRIPT … END SCRIPT`` in the same source file).

    Args:
        cmdlist: The top-level :class:`~execsql.script.CommandList` returned by
            ``read_sqlfile()`` / ``read_sqlstring()``.  If ``None`` or empty,
            a single "empty script" warning is returned.
        script_path: Absolute or relative path to the SQL script file.  Used
            to resolve relative INCLUDE paths.  Pass ``None`` for inline
            (``-c``) scripts.

    Returns:
        List of ``(severity, source, line_no, message)`` tuples, one per issue
        found.  An empty list means the script is clean.
    """
    import execsql.state as _state

    issues: list[_Issue] = []

    if cmdlist is None or not cmdlist.cmdlist:
        issues.append(_warning("<script>", 0, "Script is empty — no commands found"))
        return issues

    script_dir = Path(script_path).resolve().parent if script_path else None

    # Shared set of variables defined in the top-level script via SUB.
    # Named scripts get a fresh copy so their internal definitions don't bleed
    # back into the top-level analysis.
    top_defined: set[str] = set()

    issues.extend(_lint_cmdlist(cmdlist, script_dir, top_defined))

    # Analyse each named SCRIPT block collected during parsing
    for script_name, saved_cl in getattr(_state, "savedscripts", {}).items():
        saved_issues = _lint_cmdlist(saved_cl, script_dir, set(top_defined))
        for sev, src, lno, msg in saved_issues:
            # Annotate with the script name if the source is the same file
            issues.append((sev, src, lno, f"[script '{script_name}'] {msg}"))

    return issues


# ---------------------------------------------------------------------------
# Rich output helper
# ---------------------------------------------------------------------------


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

    for severity, source, line_no, message in issues:
        loc = f"{source}:{line_no}" if line_no else source
        if severity == "error":
            _console.print(f"  [bold red]ERROR  [/bold red]  [dim]{loc}[/dim]  {message}")
        else:
            _console.print(f"  [bold yellow]WARNING[/bold yellow]  [dim]{loc}[/dim]  {message}")

    _console.print()
    parts = []
    if n_errors:
        parts.append(f"[bold red]{n_errors} error{'s' if n_errors != 1 else ''}[/bold red]")
    if n_warnings:
        parts.append(f"[bold yellow]{n_warnings} warning{'s' if n_warnings != 1 else ''}[/bold yellow]")
    _console.print("  " + ", ".join(parts))
    _console.print()

    return 1 if n_errors > 0 else 0
