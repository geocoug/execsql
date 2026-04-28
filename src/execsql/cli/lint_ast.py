"""AST-based static analysis (lint) for execsql scripts.

Performs the same checks as :mod:`execsql.cli.lint` but operates on the
:class:`~execsql.script.ast.Script` tree instead of a flat
:class:`~execsql.script.engine.CommandList`.

Advantages over the flat linter:

- **No runtime state required** — works with the AST parser alone, so it
  can run as an early exit in the CLI without initialising ``_state``.
- **Structural validation is free** — the AST parser already rejects
  unmatched IF/LOOP/BATCH/SCRIPT blocks at parse time with precise source
  spans.  This linter only needs to report variable and INCLUDE issues.
- **Script blocks are in the tree** — ``EXECUTE SCRIPT`` targets are
  resolved by finding :class:`ScriptBlock` nodes, not by looking up
  ``_state.savedscripts``.

Checks performed
----------------
1. **Parse errors** — the AST parser rejects unmatched blocks, so any
   parse failure is reported as an error with the parser's message.
2. **Potentially undefined variables** — same heuristic as the flat linter.
3. **EXECUTE SCRIPT target resolution** — warns when a target name does
   not correspond to a :class:`ScriptBlock` in the same file.
4. **Missing INCLUDE files** — warns when the file does not exist on disk.
5. **Empty script** — warns when no nodes were parsed.
"""

from __future__ import annotations

import re
from pathlib import Path

from execsql.script.ast import (
    BatchBlock,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    MetaCommandStatement,
    Node,
    Script,
    ScriptBlock,
    SqlBlock,
    SqlStatement,
)

__all__ = ["lint_ast"]


# ---------------------------------------------------------------------------
# Variable-related patterns (shared with the flat linter)
# ---------------------------------------------------------------------------

_RX_SUB = re.compile(r"^\s*SUB\s+(?P<name>[+~]?\w+)\s+", re.I)
_RX_SUB_EMPTY = re.compile(r"^\s*SUB_EMPTY\s+(?P<name>[+~]?\w+)\s*$", re.I)
_RX_SUB_ADD = re.compile(r"^\s*SUB_ADD\s+(?P<name>[+~]?\w+)\s+", re.I)
_RX_SUB_APPEND = re.compile(r"^\s*SUB_APPEND\s+(?P<name>[+~]?\w+)\s", re.I)
_RX_SUBDATA = re.compile(r"^\s*SUBDATA\s+(?P<name>[+~]?\w+)\s+", re.I)
_RX_SUB_INI = re.compile(
    r'^\s*SUB_INI\s+(?:FILE\s+)?(?:"(?P<qfile>[^"]+)"|(?P<file>\S+))'
    r"(?:\s+SECTION)?\s+(?P<section>\w+)\s*$",
    re.I,
)
_RX_SELECTSUB = re.compile(r"^\s*(?:SELECT_?SUB|PROMPT\s+SELECT_?SUB)\s+", re.I)
_RX_SUB_LOCAL = re.compile(r"^\s*SUB_LOCAL\s+(?P<name>\w+)\s+", re.I)
_RX_SUB_TEMPFILE = re.compile(r"^\s*SUB_TEMPFILE\s+(?P<name>\w+)\s", re.I)
_RX_SUB_DECRYPT = re.compile(r"^\s*SUB_DECRYPT\s+(?P<name>\w+)\s+", re.I)
_RX_SUB_ENCRYPT = re.compile(r"^\s*SUB_ENCRYPT\s+(?P<name>\w+)\s+", re.I)
_RX_SUB_QUERYSTRING = re.compile(r"^\s*SUB_QUERYSTRING\s+(?P<name>\w+)\s+", re.I)

_RX_VAR_REF = re.compile(r"!!([$@&~#+]?\w+)!!", re.I)


# ---------------------------------------------------------------------------
# Issue tuple helpers
# ---------------------------------------------------------------------------

_Issue = tuple[str, str, int, str]  # (severity, source, line_no, message)


def _error(source: str, line_no: int, message: str) -> _Issue:
    return ("error", source, line_no, message)


def _warning(source: str, line_no: int, message: str) -> _Issue:
    return ("warning", source, line_no, message)


# ---------------------------------------------------------------------------
# Built-in variable discovery (reuse from flat linter)
# ---------------------------------------------------------------------------


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
# AST walker helpers
# ---------------------------------------------------------------------------


def _collect_script_blocks(script: Script) -> dict[str, ScriptBlock]:
    """Build a name → ScriptBlock lookup from all ScriptBlock nodes in the tree."""
    blocks: dict[str, ScriptBlock] = {}
    for node in script.walk():
        if isinstance(node, ScriptBlock):
            blocks[node.name] = node
    return blocks


def _collect_defined_vars_from_nodes(
    nodes: list[Node],
    script_blocks: dict[str, ScriptBlock],
    script_dir: Path | None,
    defined: set[str],
    visited: set[str] | None = None,
) -> None:
    """Walk nodes and collect variable definitions into *defined*."""
    if visited is None:
        visited = set()

    for node in nodes:
        if isinstance(node, MetaCommandStatement):
            _extract_var_definition(node.command, script_dir, defined)

        elif isinstance(node, IncludeDirective) and node.is_execute_script:
            target = node.target.lower()
            if target in script_blocks and target not in visited:
                visited.add(target)
                _collect_defined_vars_from_nodes(
                    script_blocks[target].body,
                    script_blocks,
                    script_dir,
                    defined,
                    visited,
                )

        # Recurse into block children
        if isinstance(node, (IfBlock, LoopBlock, BatchBlock, ScriptBlock, SqlBlock)):
            _collect_defined_vars_from_nodes(
                list(node.children()),
                script_blocks,
                script_dir,
                defined,
                visited,
            )


def _extract_var_definition(
    command: str,
    script_dir: Path | None,
    defined: set[str],
) -> None:
    """Extract variable name from a SUB-family metacommand into *defined*."""
    for rx in (
        _RX_SUB,
        _RX_SUB_EMPTY,
        _RX_SUB_ADD,
        _RX_SUB_APPEND,
        _RX_SUBDATA,
        _RX_SUB_LOCAL,
        _RX_SUB_TEMPFILE,
        _RX_SUB_DECRYPT,
        _RX_SUB_ENCRYPT,
        _RX_SUB_QUERYSTRING,
    ):
        m = rx.match(command)
        if m:
            defined.add(m.group("name").lstrip("+~").upper())
            return

    # SUB_INI bulk-defines from INI file — read keys at lint time
    ini_m = _RX_SUB_INI.match(command)
    if ini_m:
        ini_file = ini_m.group("qfile") or ini_m.group("file")
        ini_section = ini_m.group("section")
        if ini_file and not _RX_VAR_REF.search(ini_file):
            _read_ini_vars(ini_file, ini_section, script_dir, defined)


def _read_ini_vars(
    ini_file: str,
    section: str,
    script_dir: Path | None,
    defined_vars: set[str],
) -> None:
    """Read an INI file and register its section keys as defined variables."""
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


def _check_var_ref(
    raw_name: str,
    source: str,
    line_no: int,
    defined_vars: set[str],
    issues: list[_Issue],
) -> None:
    """Emit a warning if *raw_name* looks like an undefined user variable."""
    if not raw_name:
        return

    sigil = raw_name[0] if raw_name[0] in ("$", "@", "&", "~", "#", "+") else ""
    name = raw_name[len(sigil) :]

    # Skip non-$ sigil prefixes — resolved at runtime
    if sigil in ("@", "&", "~", "#", "+"):
        return

    # $ARG_N is set via -a/--assign-arg at invocation time
    if re.match(r"^ARG_\d+$", name, re.I):
        return

    # $COUNTER_N is managed by CounterVars
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


def _check_include_path(
    raw_path: str,
    script_dir: Path | None,
    source: str,
    line_no: int,
    issues: list[_Issue],
) -> None:
    """Warn if the INCLUDE target does not exist on disk."""
    p = Path(raw_path)
    if not p.is_absolute() and script_dir is not None:
        p = script_dir / p

    if not p.exists():
        issues.append(
            _warning(source, line_no, f"INCLUDE target does not exist: {raw_path!r}"),
        )


# ---------------------------------------------------------------------------
# Core lint walk
# ---------------------------------------------------------------------------


def _lint_nodes(
    nodes: list[Node],
    script_dir: Path | None,
    defined_vars: set[str],
    script_blocks: dict[str, ScriptBlock],
    issues: list[_Issue],
    *,
    visited_scripts: set[str] | None = None,
) -> None:
    """Walk a list of AST nodes and collect lint issues."""
    if visited_scripts is None:
        visited_scripts = set()

    for node in nodes:
        src = node.span.file
        lno = node.span.start_line

        # -- Variable references in SQL --
        if isinstance(node, SqlStatement):
            for m in _RX_VAR_REF.finditer(node.text):
                _check_var_ref(m.group(1), src, lno, defined_vars, issues)

        # -- Metacommand checks --
        elif isinstance(node, MetaCommandStatement):
            for m in _RX_VAR_REF.finditer(node.command):
                _check_var_ref(m.group(1), src, lno, defined_vars, issues)

        # -- IncludeDirective checks --
        elif isinstance(node, IncludeDirective):
            if node.is_execute_script:
                target = node.target.lower()
                if target not in script_blocks:
                    if not node.if_exists:
                        issues.append(
                            _warning(src, lno, f"EXECUTE SCRIPT target not found: '{target}'"),
                        )
                elif target not in visited_scripts:
                    visited_scripts.add(target)
                    _lint_nodes(
                        script_blocks[target].body,
                        script_dir,
                        defined_vars,
                        script_blocks,
                        issues,
                        visited_scripts=visited_scripts,
                    )
            else:
                # INCLUDE file existence check
                if not node.if_exists:
                    raw_path = node.target.strip().strip("\"'")
                    if not _RX_VAR_REF.search(raw_path):
                        _check_include_path(raw_path, script_dir, src, lno, issues)

        # -- Recurse into block children --
        if isinstance(node, IfBlock):
            _lint_nodes(node.body, script_dir, defined_vars, script_blocks, issues, visited_scripts=visited_scripts)
            for clause in node.elseif_clauses:
                _lint_nodes(
                    clause.body,
                    script_dir,
                    defined_vars,
                    script_blocks,
                    issues,
                    visited_scripts=visited_scripts,
                )
            _lint_nodes(
                node.else_body,
                script_dir,
                defined_vars,
                script_blocks,
                issues,
                visited_scripts=visited_scripts,
            )
        elif isinstance(node, (LoopBlock, BatchBlock, SqlBlock)):
            _lint_nodes(node.body, script_dir, defined_vars, script_blocks, issues, visited_scripts=visited_scripts)
        elif isinstance(node, ScriptBlock):
            # Lint script block body (structural errors already caught by parser)
            if node.name not in visited_scripts:
                visited_scripts.add(node.name)
                sub_issues: list[_Issue] = []
                _lint_nodes(
                    node.body,
                    script_dir,
                    defined_vars,
                    script_blocks,
                    sub_issues,
                    visited_scripts=visited_scripts,
                )
                for sev, ssrc, slno, msg in sub_issues:
                    issues.append((sev, ssrc, slno, f"[script '{node.name}'] {msg}"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lint_ast(
    script: Script,
    script_path: str | None = None,
) -> list[_Issue]:
    """Perform static analysis on an AST-parsed script.

    Args:
        script: The parsed :class:`Script` tree.
        script_path: Path to the source file (for resolving relative
            INCLUDE paths).  ``None`` for inline scripts.

    Returns:
        List of ``(severity, source, line_no, message)`` issue tuples.
    """
    issues: list[_Issue] = []

    if not script.body:
        issues.append(_warning("<script>", 0, "Script is empty — no commands found"))
        return issues

    script_dir = Path(script_path).resolve().parent if script_path else None
    script_blocks = _collect_script_blocks(script)

    # Pass 1: collect all variable definitions
    all_defined: set[str] = set()
    _collect_defined_vars_from_nodes(script.body, script_blocks, script_dir, all_defined)

    # Pass 2: lint for variable and include issues
    _lint_nodes(
        script.body,
        script_dir,
        all_defined,
        script_blocks,
        issues,
    )

    return issues
