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
   ``SUB`` (or ``SUB_EMPTY``, ``SUB_ADD``, ``SUB_APPEND``, ``SUBDATA``)
   metacommand in the same parsed command list and not in the set of built-in
   variables (warning).  Note: ``SUB_INI`` and ``SELECT_SUB`` define variables
   whose names are not statically knowable — those may produce false-positive
   warnings.
5. **EXECUTE SCRIPT flow analysis** — when an ``EXECUTE SCRIPT <name>``
   metacommand is encountered, the linter descends into the named script
   block (if found in ``_state.savedscripts``) and merges any variables it
   defines back into the caller's scope.
6. **Missing INCLUDE files** — INCLUDE target does not exist on disk relative
   to the script directory (warning).
7. **Empty script** — no commands found (warning).

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

# SUB_EMPTY <varname> — defines a variable with empty string
_RX_SUB_EMPTY = re.compile(r"^\s*SUB_EMPTY\s+(?P<name>[+~]?\w+)\s*$", re.I)

# SUB_ADD <varname> <expr> — increments a variable (implies it exists)
_RX_SUB_ADD = re.compile(r"^\s*SUB_ADD\s+(?P<name>[+~]?\w+)\s+", re.I)

# SUB_APPEND <varname> <text> — appends to a variable (implies it exists)
_RX_SUB_APPEND = re.compile(r"^\s*SUB_APPEND\s+(?P<name>[+~]?\w+)\s", re.I)

# SUBDATA <varname> <datasource> — defines a variable from a query result
_RX_SUBDATA = re.compile(r"^\s*SUBDATA\s+(?P<name>[+~]?\w+)\s+", re.I)

# SUB_INI [FILE] <filename> [SECTION] <section> — bulk-defines variables from INI file
_RX_SUB_INI = re.compile(
    r'^\s*SUB_INI\s+(?:FILE\s+)?(?:"(?P<qfile>[^"]+)"|(?P<file>\S+))'
    r"(?:\s+SECTION)?\s+(?P<section>\w+)\s*$",
    re.I,
)

# EXECUTE SCRIPT / EXEC SCRIPT / RUN SCRIPT
_RX_EXEC_SCRIPT = re.compile(
    r"^\s*(?:EXEC(?:UTE)?|RUN)\s+SCRIPT(?:\s+IF\s+EXISTS)?\s+(?P<script_id>\w+)",
    re.I,
)

# INCLUDE <file>
_RX_INCLUDE = re.compile(
    r"^\s*INCLUDE(?:\s+IF\s+EXISTS?)?\s+(?P<path>\S+.*?)\s*$",
    re.I,
)

# Variable reference — !!name!! where name may start with $, @, &, ~, #, +
_RX_VAR_REF = re.compile(r"!!([$@&~#+]?\w+)!!", re.I)

# Built-in system variables — extracted automatically from the installed
# ``execsql`` source by scanning for ``add_substitution("$NAME", ...)`` and
# ``register_lazy("$NAME", ...)`` calls.  This avoids maintaining a hand-
# curated list that drifts out of sync when new system variables are added.
# Variable names are stored upper-case without the leading ``$``.


def _discover_builtin_vars() -> frozenset[str]:
    """Scan the execsql package source for ``$VARNAME`` system variables."""
    import importlib.util

    _rx_add_sub = re.compile(r'(?:(?<!\w)add_substitution|(?<!\w)sv)\s*\(\s*["\'](\$\w+)["\']')
    _rx_lazy = re.compile(r'register_lazy\s*\(\s*["\'](\$\w+)["\']')

    names: set[str] = set()

    spec = importlib.util.find_spec("execsql")
    if spec is None or spec.submodule_search_locations is None:
        return frozenset(names)

    pkg_dir = Path(spec.submodule_search_locations[0])
    for src_file in pkg_dir.rglob("*.py"):
        try:
            text = src_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _rx_add_sub.finditer(text):
            names.add(m.group(1).lstrip("$").upper())
        for m in _rx_lazy.finditer(text):
            names.add(m.group(1).lstrip("$").upper())

    return frozenset(names)


_BUILTIN_VARS: frozenset[str] = _discover_builtin_vars()


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


def _collect_defined_vars(
    cmdlist: CommandList,
    script_dir: Path | None,
    defined_vars: set[str],
    *,
    _savedscripts: dict | None = None,
    _visited_scripts: set[str] | None = None,
) -> None:
    """Pass 1: walk *cmdlist* and collect all variable definitions into *defined_vars*.

    This populates the set with every variable name that could be defined at
    runtime — ``SUB``, ``SUB_EMPTY``, ``SUB_ADD``, ``SUB_APPEND``,
    ``SUBDATA``, and ``SUB_INI`` (by reading the INI file on disk).  It also
    descends into ``EXECUTE SCRIPT`` targets to collect their definitions.

    No issues are reported; structural checks and variable-reference validation
    happen in pass 2 (:func:`_lint_cmdlist`).
    """
    visited = _visited_scripts if _visited_scripts is not None else set()

    for cmd in cmdlist.cmdlist:
        if cmd.command_type == "sql":
            continue
        stmt = cmd.command.statement

        # SUB <name> <value>
        sub_m = _RX_SUB.match(stmt)
        if sub_m:
            defined_vars.add(sub_m.group("name").lstrip("+~").upper())

        # SUB_EMPTY / SUB_ADD / SUB_APPEND / SUBDATA
        for rx in (_RX_SUB_EMPTY, _RX_SUB_ADD, _RX_SUB_APPEND, _RX_SUBDATA):
            m = rx.match(stmt)
            if m:
                defined_vars.add(m.group("name").lstrip("+~").upper())
                break

        # SUB_INI — read INI file keys
        ini_m = _RX_SUB_INI.match(stmt)
        if ini_m:
            ini_file = ini_m.group("qfile") or ini_m.group("file")
            ini_section = ini_m.group("section")
            if ini_file and not _RX_VAR_REF.search(ini_file):
                _read_ini_vars(ini_file, ini_section, script_dir, defined_vars)

        # EXECUTE SCRIPT — descend into named script block
        exec_m = _RX_EXEC_SCRIPT.match(stmt)
        if exec_m and _savedscripts is not None:
            script_id = exec_m.group("script_id").lower()
            if script_id in _savedscripts and script_id not in visited:
                visited.add(script_id)
                _collect_defined_vars(
                    _savedscripts[script_id],
                    script_dir,
                    defined_vars,
                    _savedscripts=_savedscripts,
                    _visited_scripts=visited,
                )


def _lint_cmdlist(
    cmdlist: CommandList,
    script_dir: Path | None,
    defined_vars: set[str],
    *,
    _savedscripts: dict | None = None,
    _visited_scripts: set[str] | None = None,
) -> list[_Issue]:
    """Pass 2: lint a :class:`CommandList` for structural and variable issues.

    Args:
        cmdlist: The parsed command list to analyse.
        script_dir: Directory of the top-level script file, used for resolving
            relative INCLUDE paths.  ``None`` for inline (``-c``) scripts.
        defined_vars: Set of variable names (without sigil) that have been
            pre-collected by :func:`_collect_defined_vars`.  This includes
            *all* top-level and script-block definitions so that ordering
            does not matter.
        _savedscripts: Dictionary of named script blocks (from
            ``_state.savedscripts``).  Passed explicitly so the function can
            descend into EXECUTE SCRIPT targets.
        _visited_scripts: Set of script IDs already descended into, shared
            across recursive calls to prevent infinite recursion from circular
            EXECUTE SCRIPT references.

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

    # Track which EXECUTE SCRIPT targets we've already descended into to
    # prevent infinite recursion from circular script references.
    visited_scripts: set[str] = _visited_scripts if _visited_scripts is not None else set()

    for cmd in cmdlist.cmdlist:
        src = cmd.source
        lno = cmd.line_no
        stmt = cmd.command.statement

        if cmd.command_type == "sql":
            # SQL statements: check for variable references only
            for m in _RX_VAR_REF.finditer(stmt):
                _check_var_ref(m.group(1), src, lno, defined_vars, issues)
            continue

        # Metacommand checks — variable references
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

        # -- EXECUTE SCRIPT — descend into named script block --
        exec_m = _RX_EXEC_SCRIPT.match(stmt)
        if exec_m and _savedscripts is not None:
            script_id = exec_m.group("script_id").lower()
            if script_id not in _savedscripts:
                # Warn unless it's EXECUTE SCRIPT IF EXISTS
                if not re.search(r"\bIF\s+EXISTS\b", stmt, re.I):
                    issues.append(
                        _warning(src, lno, f"EXECUTE SCRIPT target not found: '{script_id}'"),
                    )
            elif script_id not in visited_scripts:
                visited_scripts.add(script_id)
                sub_issues = _lint_cmdlist(
                    _savedscripts[script_id],
                    script_dir,
                    defined_vars,
                    _savedscripts=_savedscripts,
                    _visited_scripts=visited_scripts,
                )
                for sev, ssrc, slno, msg in sub_issues:
                    issues.append((sev, ssrc, slno, f"[script '{script_id}'] {msg}"))

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

    # $COUNTER_N is managed by CounterVars (@@counter metacommands)
    if re.match(r"^COUNTER_\d+$", name, re.I):
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


def _read_ini_vars(
    ini_file: str,
    section: str,
    script_dir: Path | None,
    defined_vars: set[str],
) -> None:
    """Read an INI file and register its section keys as defined variables.

    Mirrors what ``SUB_INI`` does at runtime: reads a
    :class:`~configparser.ConfigParser` section and defines each key as a
    substitution variable.  If the file does not exist or the section is
    missing, silently does nothing (the runtime handler behaves the same way).
    """
    from configparser import ConfigParser

    p = Path(ini_file)
    if not p.is_absolute() and script_dir is not None:
        p = script_dir / p

    if not p.exists():
        return

    cp = ConfigParser()
    cp.read(p)
    if cp.has_section(section):
        for key, _value in cp.items(section):
            defined_vars.add(key.upper())


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
    savedscripts: dict = getattr(_state, "savedscripts", {})

    # ------------------------------------------------------------------
    # Pass 1: collect all variable definitions from the top-level script
    # and all reachable script blocks.  This ensures definition order does
    # not matter — a script block executed early can reference variables
    # defined later in the top-level script.
    # ------------------------------------------------------------------
    all_defined: set[str] = set()
    collect_visited: set[str] = set()
    _collect_defined_vars(
        cmdlist,
        script_dir,
        all_defined,
        _savedscripts=savedscripts,
        _visited_scripts=collect_visited,
    )
    # Also collect from every saved script block (they may define vars
    # referenced by other blocks).  Share the visited set so each block
    # is only traversed once (O(N) instead of O(N²)).
    for saved_cl in savedscripts.values():
        _collect_defined_vars(
            saved_cl,
            script_dir,
            all_defined,
            _savedscripts=savedscripts,
            _visited_scripts=collect_visited,
        )

    # ------------------------------------------------------------------
    # Pass 2: lint for structural issues and undefined-variable warnings
    # using the complete variable set from pass 1.
    # ------------------------------------------------------------------
    # Shared visited-scripts tracker — prevents duplicate lint warnings
    # when the same script block is reached via multiple paths.
    visited: set[str] = set()

    issues.extend(
        _lint_cmdlist(
            cmdlist,
            script_dir,
            all_defined,
            _savedscripts=savedscripts,
            _visited_scripts=visited,
        ),
    )

    # Analyse each named SCRIPT block that was NOT already visited via
    # EXECUTE SCRIPT (standalone analysis catches structural issues like
    # unmatched IF/ENDIF in script blocks that are never executed).
    for script_name, saved_cl in savedscripts.items():
        if script_name in visited:
            continue
        visited.add(script_name)
        saved_issues = _lint_cmdlist(
            saved_cl,
            script_dir,
            set(all_defined),
            _savedscripts=savedscripts,
            _visited_scripts=visited,
        )
        for sev, src, lno, msg in saved_issues:
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
