"""AST-based static analysis (``--lint``) for execsql scripts.

Operates on the :class:`~execsql.script.ast.Script` tree produced by
:func:`execsql.script.parser.parse_script` / ``parse_string``. Runs as
an early CLI exit — no DB connection and no ``_state`` initialisation
required.

Checks performed:

1. **Parse errors** — the AST parser rejects unmatched IF / LOOP /
   BATCH / SCRIPT blocks at parse time with precise source spans;
   ``cli/__init__.py`` reports any parse failure as a lint error before
   :func:`lint` is even called.
2. **Empty scripts** — warns when no nodes were parsed.
3. **Potentially undefined variables** — flags ``!!$VAR!!`` references
   with no preceding ``SUB``-family definition, ignoring built-in
   ``$VAR`` names discovered from the package source and the
   non-``$`` sigils (``~``, ``#``, ``+``, ``@``, ``&``) that resolve at
   runtime.
4. **Missing INCLUDE files** — warns when the resolved target does not
   exist on disk (skipped when ``IF EXISTS`` is present).
5. **EXECUTE SCRIPT target resolution** — warns when a target name does
   not correspond to a :class:`ScriptBlock` in the same file (skipped
   when ``IF EXISTS`` is present).

Every check has a rule code (:data:`RULES`), so a caller can select or
ignore rules and machine-readable output can name them.

Public surface:

- :func:`lint` — entry point; returns a list of :class:`Issue`.
- :data:`RULES` / :class:`Rule` — the rule registry: code, name, severity.
- :func:`parse_error` — the :class:`Issue` for a script that fails to parse.
- :func:`resolve_selectors` / :func:`filter_issues` — ``--select`` and
  ``--ignore`` handling.
- :func:`print_text`, :func:`print_concise`, :func:`print_statistics`,
  :func:`render_json` — output formats; :func:`exit_code` — ``1`` when any
  reported issue is an error, ``0`` otherwise. :func:`_print_lint_results`
  is the single-script form ``--lint`` uses.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from execsql.exceptions import ErrInfo
from execsql.script.ast import (
    BatchBlock,
    Comment,
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

__all__ = [
    "RULES",
    "Issue",
    "Rule",
    "_print_lint_results",
    "exit_code",
    "filter_issues",
    "lint",
    "parse_error",
    "print_concise",
    "print_statistics",
    "print_text",
    "render_json",
    "resolve_selectors",
    "rule_counts",
]


# ---------------------------------------------------------------------------
# Rules and issues
# ---------------------------------------------------------------------------


class Rule(NamedTuple):
    """One lint check.

    Codes are grouped by what the rule is about, not by severity, so a rule
    can change severity without breaking anyone's ``--ignore`` list:
    ``P`` parsing, ``S`` the script as a whole, ``V`` variables, ``I``
    INCLUDE / EXECUTE SCRIPT targets, ``F`` control flow.
    """

    code: str
    name: str
    severity: str  # "error" | "warning"
    summary: str


#: Every rule, by code. Codes are a public contract: never renumber or reuse one.
RULES: dict[str, Rule] = {
    rule.code: rule
    for rule in (
        Rule(
            "P001",
            "parse-error",
            "error",
            "The script cannot be parsed, for example an IF, LOOP, BATCH or SCRIPT block that is never closed.",
        ),
        Rule("S001", "empty-script", "warning", "The script contains no statements."),
        Rule(
            "V001",
            "undefined-variable",
            "warning",
            "A !!variable!! is referenced, but no SUB-family metacommand in the script defines it.",
        ),
        Rule(
            "V002",
            "unused-variable",
            "warning",
            "A SUB-family metacommand defines a variable that nothing in the script references.",
        ),
        Rule("I001", "missing-include", "warning", "An INCLUDE target file does not exist."),
        Rule(
            "I002",
            "missing-script",
            "warning",
            "EXECUTE SCRIPT names a script that no BEGIN SCRIPT block in the file defines.",
        ),
        Rule(
            "F001",
            "constant-condition",
            "warning",
            "An IF condition is always true or always false, so one of its branches can never run.",
        ),
        Rule("F002", "unreachable-code", "warning", "A statement follows an unconditional HALT."),
    )
}

#: Always reported, whatever --select and --ignore say: a script that does not
#: parse has not been checked, and reporting "no issues" for it would be false.
_ALWAYS_REPORTED = frozenset({"P001"})


class Issue(NamedTuple):
    """One finding. ``line`` is 0 when the issue has no single line."""

    severity: str
    source: str
    line: int
    message: str
    code: str


# Kept as the internal name the walker functions were written against.
_Issue = Issue


def _issue(code: str, source: str, line_no: int, message: str) -> Issue:
    return Issue(RULES[code].severity, source, line_no, message, code)


_RX_ON_LINE = re.compile(r"\bon line (\d+)")


def parse_error(source: str, exc: ErrInfo) -> Issue:
    """The issue reported for a script that fails to parse.

    Uses the parser's own message rather than :meth:`ErrInfo.errmsg`, which
    adds a banner and a timestamp, and folds it onto one line. Every parser
    message names the offending line as "on line N", which becomes the
    issue's line so editors and JSON consumers can jump to it.
    """
    text = " ".join((exc.other or exc.exception or str(exc)).split())
    found = _RX_ON_LINE.search(text)
    return _issue("P001", source, int(found.group(1)) if found else 0, text.rstrip("."))


# ---------------------------------------------------------------------------
# Variable-related patterns
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
# Built-in variable discovery
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


_BUILTIN_VARS: frozenset[str] | None = None


def _get_builtin_vars() -> frozenset[str]:
    """Return the cached set of built-in variable names, discovering on first call."""
    global _BUILTIN_VARS
    if _BUILTIN_VARS is None:
        _BUILTIN_VARS = _discover_builtin_vars()
    return _BUILTIN_VARS


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
    if name.upper() in _get_builtin_vars():
        return

    # User-defined via SUB
    if name.upper() in defined_vars:
        return

    issues.append(
        _issue(
            "V001",
            source,
            line_no,
            f"undefined variable !!{raw_name}!!",
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
            _issue("I001", source, line_no, f"INCLUDE file does not exist: {raw_path}"),
        )


# ---------------------------------------------------------------------------
# Structural rules
#
# These are the checks a compiler performs for every other language and that
# an execsql script has only ever got by being run: a branch that cannot be
# reached, a statement after a HALT, a variable defined and never used.
# Today those are found by running the script against a live database and
# watching it do the wrong thing halfway through.
# ---------------------------------------------------------------------------

#: Conditions whose value is fixed at parse time.  ``IF(True)`` is a real and
#: reasonable thing to write while developing; leaving it in is what makes
#: every other branch dead code.
_RX_CONST_TRUE = re.compile(r"^\s*\(?\s*(?:true|1\s*=\s*1|yes)\s*\)?\s*$", re.I)
_RX_CONST_FALSE = re.compile(r"^\s*\(?\s*(?:false|0\s*=\s*1|1\s*=\s*0|no)\s*\)?\s*$", re.I)

#: Metacommands after which nothing in the same block can run.
_RX_TERMINAL = re.compile(r"^\s*HALT\b(?!\s+DISPLAY)", re.I)


def _is_always_true(node: IfBlock) -> bool:
    """True when the IF condition is a literal that cannot be false.

    Compounding modifiers are not analysed — an ANDIF could make the whole
    condition false, so a modified IF is never reported.
    """
    if node.condition_modifiers:
        return False
    return bool(_RX_CONST_TRUE.match(node.condition))


def _is_always_false(node: IfBlock) -> bool:
    if node.condition_modifiers:
        return False
    return bool(_RX_CONST_FALSE.match(node.condition))


def _check_constant_condition(node: IfBlock, issues: list[_Issue]) -> None:
    """Report branches that a constant condition makes unreachable."""
    src, lno = node.span.file, node.span.start_line
    if _is_always_true(node):
        n_elseif = len(node.elseif_clauses)
        dead = []
        if n_elseif:
            dead.append("ELSEIF" if n_elseif == 1 else f"{n_elseif} ELSEIF branches")
        if node.else_body:
            dead.append("ELSE")
        if dead:
            verb = "runs" if len(dead) == 1 and n_elseif <= 1 else "run"
            issues.append(
                _issue(
                    "F001",
                    src,
                    lno,
                    f"IF({node.condition}) is always true; its {' and '.join(dead)} never {verb}",
                ),
            )
    elif _is_always_false(node) and node.body:
        issues.append(
            _issue(
                "F001",
                src,
                lno,
                f"IF({node.condition}) is always false; its body never runs",
            ),
        )


def _check_unreachable_after_halt(nodes: list[Node], issues: list[_Issue]) -> None:
    """Report statements that follow an unconditional HALT in the same block.

    ``HALT DISPLAY`` shows a message and can be cancelled, so it is not
    treated as terminal.
    """
    for i, node in enumerate(nodes):
        if not isinstance(node, MetaCommandStatement):
            continue
        if not _RX_TERMINAL.match(node.command):
            continue
        rest = [n for n in nodes[i + 1 :] if not isinstance(n, Comment)]
        if rest:
            after = rest[0]
            issues.append(
                _issue(
                    "F002",
                    after.span.file,
                    after.span.start_line,
                    f"unreachable: HALT on line {node.span.start_line} ends the script",
                ),
            )
        return


def _collect_var_references(nodes: list[Node], seen: set[str]) -> None:
    """Record every ``!!var!!`` reference anywhere beneath *nodes*."""
    for node in nodes:
        for text in _referencing_text(node):
            for m in _RX_VAR_REF.finditer(text):
                seen.add(m.group(1).lstrip("$@&~#+").upper())
        for child in node.children():
            _collect_var_references([child], seen)


def _referencing_text(node: Node) -> list[str]:
    """Every string on *node* in which a variable reference may appear."""
    texts: list[str] = []
    if isinstance(node, SqlStatement):
        texts.append(node.text)
    elif isinstance(node, MetaCommandStatement):
        texts.append(node.command)
    elif isinstance(node, IncludeDirective):
        texts.append(node.target)
    if isinstance(node, IfBlock):
        texts.append(node.condition)
        texts.extend(m.condition for m in node.condition_modifiers)
        texts.extend(c.condition for c in node.elseif_clauses)
    elif isinstance(node, LoopBlock):
        texts.append(node.condition)
    return texts


def _check_unused_variables(script: Script, defined: set[str], issues: list[_Issue]) -> None:
    """Report variables a SUB defines that nothing ever reads.

    Almost always a typo in either the definition or the reference — the two
    spellings differ and neither the script nor the database complains.
    Variables a script *exports* for a caller are the false positive here, so
    this is a warning.
    """
    referenced: set[str] = set()
    _collect_var_references(script.body, referenced)
    unused = sorted(defined - referenced)
    for name in unused:
        line = _definition_line(script.body, name)
        issues.append(
            _issue(
                "V002",
                script.body[0].span.file if script.body else "<script>",
                line,
                f"variable !!{name.lower()}!! is never used",
            ),
        )


def _definition_line(nodes: list[Node], name: str) -> int:
    """Line of the SUB that defines *name*, or 0 when it cannot be located."""
    for node in nodes:
        if isinstance(node, MetaCommandStatement):
            probe: set[str] = set()
            _extract_var_definition(node.command, None, probe)
            if name in probe:
                return node.span.start_line
        found = _definition_line(list(node.children()), name)
        if found:
            return found
    return 0


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

    _check_unreachable_after_halt(nodes, issues)

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
                            _issue("I002", src, lno, f"no BEGIN SCRIPT block named {target}"),
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
            _check_constant_condition(node, issues)
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
                for sub in sub_issues:
                    issues.append(sub._replace(message=f"[script '{node.name}'] {sub.message}"))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def lint(
    script: Script,
    script_path: str | None = None,
) -> list[_Issue]:
    """Perform static analysis on an AST-parsed script.

    Args:
        script: The parsed :class:`Script` tree.
        script_path: Path to the source file (for resolving relative
            INCLUDE paths).  ``None`` for inline scripts.

    Returns:
        Every :class:`Issue` found, unfiltered.
    """
    issues: list[_Issue] = []

    if not script.body:
        issues.append(_issue("S001", script_path or "<script>", 0, "script is empty"))
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

    # Pass 3: whole-script rules, which need every reference collected first
    _check_unused_variables(script, all_defined, issues)

    return issues


# ---------------------------------------------------------------------------
# Selecting rules
# ---------------------------------------------------------------------------


def resolve_selectors(values: Iterable[str] | None) -> tuple[str, ...]:
    """Normalize ``--select`` / ``--ignore`` values into code prefixes.

    Each value may hold several comma-separated entries. An entry is a full
    code (``V001``) or a prefix of one (``V``, ``V0``), matched without
    regard to case.

    Raises:
        ValueError: An entry matches no rule. A typo in ``--ignore`` would
            otherwise silently ignore nothing.
    """
    prefixes: list[str] = []
    for value in values or ():
        for entry in value.split(","):
            prefix = entry.strip().upper()
            if not prefix:
                continue
            if not any(code.startswith(prefix) for code in RULES):
                raise ValueError(f"unknown rule code or prefix: {entry.strip()!r}")
            prefixes.append(prefix)
    return tuple(prefixes)


def filter_issues(
    issues: Iterable[Issue],
    select: tuple[str, ...] = (),
    ignore: tuple[str, ...] = (),
) -> list[Issue]:
    """Keep the issues *select* asks for, minus those *ignore* removes.

    An empty *select* means every rule. *ignore* wins over *select*. Parse
    errors (``P001``) are kept regardless.
    """
    kept = []
    for issue in issues:
        if issue.code in _ALWAYS_REPORTED:
            kept.append(issue)
            continue
        if select and not issue.code.startswith(select):
            continue
        if ignore and issue.code.startswith(ignore):
            continue
        kept.append(issue)
    return kept


# ---------------------------------------------------------------------------
# Result printing
# ---------------------------------------------------------------------------


def exit_code(issues: Iterable[Issue]) -> int:
    """``1`` when any issue is an error, otherwise ``0``."""
    return 1 if any(issue.severity == "error" for issue in issues) else 0


def _sorted(issues: Iterable[Issue]) -> list[Issue]:
    """By line, then code: the order a reader works through a file."""
    return sorted(issues, key=lambda i: (i.line, i.code))


#: One script's path and the issues reported for it.
FileResult = tuple[str, list[Issue]]

_SEVERITY_STYLE = {"error": "bold red", "warning": "yellow"}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _summary(results: list[FileResult], checked: int) -> str:
    """The closing line, as Rich markup."""
    issues = [i for _, found in results for i in found]
    checked_note = f"({_plural(checked, 'file')} checked)"
    if not issues:
        return f"[green]No issues found[/green] {checked_note}"
    n_errors = sum(1 for i in issues if i.severity == "error")
    n_files = sum(1 for _, found in results if found)
    counts = []
    if n_errors:
        counts.append(f"[bold red]{_plural(n_errors, 'error')}[/bold red]")
    if len(issues) - n_errors:
        counts.append(f"[yellow]{_plural(len(issues) - n_errors, 'warning')}[/yellow]")
    return f"Found {_plural(len(issues), 'issue')} in {_plural(n_files, 'file')}: {', '.join(counts)} {checked_note}"


def print_text(results: list[FileResult], checked: int) -> None:
    """Issues grouped under each file, one aligned row per issue.

    ::

        scripts/validate_orders.sql
           2  warning  V002  variable !!report_dir!! is never used
          10  warning  V001  undefined variable !!output_path!!

        Found 2 issues in 1 file: 2 warnings (4 files checked)

    On a terminal, a message too long for the window wraps under the message
    column rather than back to the left margin. Piped output is never
    wrapped, so each issue stays on one line for grep.
    """
    import textwrap

    from rich.markup import escape

    from execsql.cli.help import _console

    for path, found in results:
        if not found:
            continue
        ordered = _sorted(found)
        line_width = max(len(str(i.line)) for i in ordered)
        indent = 2 + line_width + 2 + 7 + 2 + 4 + 2
        wrap_at = _console.width - indent if _console.is_terminal else 0

        _console.print(f"[bold]{escape(path)}[/bold]", highlight=False)
        for issue in ordered:
            line = str(issue.line) if issue.line else "-"
            style = _SEVERITY_STYLE[issue.severity]
            lines = (
                # A variable or path is never split: a broken name is harder to
                # read, and to search for, than one that runs past the edge.
                textwrap.wrap(issue.message, wrap_at, break_long_words=False, break_on_hyphens=False)
                if wrap_at >= 30
                else [issue.message]
            )
            message = ("\n" + " " * indent).join(escape(part) for part in lines)
            _console.print(
                f"  [dim]{line:>{line_width}}[/dim]  [{style}]{issue.severity:<7}[/{style}]"
                f"  [dim]{issue.code}[/dim]  {message}",
                highlight=False,
                soft_wrap=True,
            )
        _console.print()
    _console.print(_summary(results, checked), highlight=False)


def print_concise(results: list[FileResult], checked: int) -> None:
    """One ``path:line: CODE message`` line per issue, for grep and editors."""
    from rich.markup import escape

    from execsql.cli.help import _console

    for path, found in results:
        for issue in _sorted(found):
            where = f"{path}:{issue.line}" if issue.line else path
            style = _SEVERITY_STYLE[issue.severity]
            _console.print(
                f"{escape(where)}: [{style}]{issue.code}[/{style}] {escape(issue.message)}",
                highlight=False,
                soft_wrap=True,
            )
    if any(found for _, found in results):
        _console.print()
    _console.print(_summary(results, checked), highlight=False)


def print_statistics(results: list[FileResult], checked: int) -> None:
    """How often each rule fired, most frequent first."""
    from execsql.cli.help import _console

    counts = rule_counts(i for _, found in results for i in found)
    if counts:
        width = max(len(str(n)) for _, n in counts)
        for rule, n in counts:
            style = _SEVERITY_STYLE[rule.severity]
            _console.print(f"  {n:>{width}}  [{style}]{rule.code}[/{style}]  {rule.name}", highlight=False)
        _console.print()
    _console.print(_summary(results, checked), highlight=False)


def _print_lint_results(issues: list[Issue], script_label: str) -> int:
    """Print one script's issues in the text layout; return the exit code.

    The ``--lint`` option of ``run`` checks a single script and uses this.
    """
    print_text([(script_label, issues)], checked=1)
    return exit_code(issues)


def render_json(issues: Iterable[Issue]) -> str:
    """Every issue as one JSON array, in the order given.

    Each object has ``file``, ``line`` (``null`` when the issue has no single
    line), ``code``, ``rule``, ``severity`` and ``message``.
    """
    rows = [
        {
            "file": i.source,
            "line": i.line or None,
            "code": i.code,
            "rule": RULES[i.code].name,
            "severity": i.severity,
            "message": i.message,
        }
        for i in issues
    ]
    return json.dumps(rows, indent=2, ensure_ascii=False)


def rule_counts(issues: Iterable[Issue]) -> list[tuple[Rule, int]]:
    """How often each rule fired, most frequent first, then by code."""
    counts = Counter(i.code for i in issues)
    return sorted(((RULES[code], n) for code, n in counts.items()), key=lambda rc: (-rc[1], rc[0].code))
