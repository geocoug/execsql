"""Abstract Syntax Tree node definitions for execsql scripts.

This module defines the node types that make up the execsql AST.  A parser
(to be added in a later phase) will convert raw ``.sql`` script text into a
tree of these nodes; an executor will walk the tree to run the script.

Design principles:
    - Every node carries a :class:`SourceSpan` so that error messages, the
      LSP, and ``--lint`` can report precise source locations.
    - Block structures (IF, LOOP, BATCH, SCRIPT) are represented as nodes
      whose ``body`` (and optional ``else_body``, ``elseif_clauses``) contain
      child nodes, forming the tree structure.
    - Leaf nodes (:class:`SqlStatement`, :class:`MetaCommandStatement`,
      :class:`Comment`) have no children.
    - All nodes inherit from :class:`Node`, which provides a uniform
      ``children()`` iterator for tree traversal.
    - The tree is meant to be *walked* for execution — nodes are data, not
      behavior.  Execution logic will live in a separate executor module.

Node hierarchy::

    Node (abstract base)
    ├── SqlStatement          — a single SQL statement
    ├── MetaCommandStatement  — a single metacommand (flat, no block structure)
    ├── Comment               — a comment line or block (preserved for formatting)
    ├── IfBlock               — IF / ELSEIF / ELSE / ENDIF structure
    ├── LoopBlock             — LOOP WHILE|UNTIL ... ENDLOOP structure
    ├── BatchBlock            — BEGIN BATCH ... END BATCH structure
    ├── ScriptBlock           — BEGIN SCRIPT name ... END SCRIPT structure
    ├── SqlBlock              — BEGIN SQL ... END SQL structure
    └── IncludeDirective      — INCLUDE or EXECUTE SCRIPT reference

Container::

    Script                    — top-level container holding a sequence of nodes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterator


__all__ = [
    "SourceSpan",
    "Node",
    "SqlStatement",
    "MetaCommandStatement",
    "Comment",
    "ConditionModifier",
    "ElseIfClause",
    "IfBlock",
    "LoopBlock",
    "BatchBlock",
    "ScriptBlock",
    "SqlBlock",
    "IncludeDirective",
    "Script",
    "format_tree",
]


# ---------------------------------------------------------------------------
# Source location
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Location of a node within its source file.

    Attributes:
        file: Path or name of the source file (e.g. ``"pipeline.sql"`` or
            ``"<inline>"``).
        start_line: 1-based line number where the node begins.
        end_line: 1-based line number where the node ends (inclusive).
            Defaults to *start_line* for single-line nodes.
    """

    file: str
    start_line: int
    end_line: int | None = None

    @property
    def effective_end_line(self) -> int:
        """Return *end_line*, falling back to *start_line* if not set."""
        return self.end_line if self.end_line is not None else self.start_line

    def __str__(self) -> str:
        end = self.effective_end_line
        if end == self.start_line:
            return f"{self.file}:{self.start_line}"
        return f"{self.file}:{self.start_line}-{end}"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


@dataclass
class Node:
    """Base class for all AST nodes.

    Every node carries a :attr:`span` indicating where it appeared in the
    source file.  Subclasses that contain child nodes must override
    :meth:`children` to yield them.
    """

    span: SourceSpan

    def children(self) -> Iterator[Node]:
        """Yield immediate child nodes (empty for leaf nodes)."""
        return iter(())

    def walk(self) -> Iterator[Node]:
        """Depth-first traversal of this node and all descendants."""
        yield self
        for child in self.children():
            yield from child.walk()


# ---------------------------------------------------------------------------
# Leaf nodes
# ---------------------------------------------------------------------------


@dataclass
class SqlStatement(Node):
    """A single SQL statement to be executed against the active database.

    Attributes:
        text: The raw SQL text, including any trailing semicolon.
    """

    text: str

    def __repr__(self) -> str:
        preview = self.text[:60] + ("..." if len(self.text) > 60 else "")
        return f"SqlStatement({self.span}, {preview!r})"


@dataclass
class MetaCommandStatement(Node):
    """A single metacommand line (not a block-opening or block-closing command).

    This covers all metacommands that do not introduce block structure:
    SUB, EXPORT, CONNECT, CONFIG, ASSERT, CD, LOG, etc.

    Attributes:
        command: The metacommand text *after* the ``-- !x!`` prefix has been
            stripped (e.g. ``"SUB myvar = hello"``).
    """

    command: str

    def __repr__(self) -> str:
        preview = self.command[:60] + ("..." if len(self.command) > 60 else "")
        return f"MetaCommandStatement({self.span}, {preview!r})"


@dataclass
class Comment(Node):
    """A comment line or block comment preserved for round-trip formatting.

    Attributes:
        text: The full comment text including delimiters (``--`` or
            ``/* ... */``).
    """

    text: str

    def __repr__(self) -> str:
        preview = self.text[:60] + ("..." if len(self.text) > 60 else "")
        return f"Comment({self.span}, {preview!r})"


# ---------------------------------------------------------------------------
# Block nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConditionModifier:
    """An ANDIF or ORIF modifier that compounds an IF condition.

    These are not separate branches — they modify the IF's boolean result
    at runtime.  ``IF (A) / ANDIF (B)`` means ``A AND B``.

    Attributes:
        kind: ``"AND"`` for ANDIF, ``"OR"`` for ORIF.
        condition: The condition expression text.
        span: Source location of the ANDIF/ORIF line.
    """

    kind: str  # "AND" or "OR"
    condition: str
    span: SourceSpan


@dataclass
class ElseIfClause:
    """A single ELSEIF branch within an :class:`IfBlock`.

    Not a full :class:`Node` subclass because it is always contained within
    an :class:`IfBlock` — its source span is derived from the parent.

    Attributes:
        condition: The condition expression text (e.g. ``"HAS_ROWS"``).
        span: Source location of the ELSEIF line itself.
        body: Nodes executed when this condition is true.
    """

    condition: str
    span: SourceSpan
    body: list[Node] = field(default_factory=list)


@dataclass
class IfBlock(Node):
    """An IF / ANDIF / ORIF / ELSEIF / ELSE / ENDIF structure.

    Attributes:
        condition: The condition expression text for the initial IF.
        condition_modifiers: ANDIF/ORIF modifiers that compound the IF
            condition.  Evaluated left-to-right at runtime.
        body: Nodes executed when the (possibly compounded) condition is true.
        elseif_clauses: Zero or more ELSEIF branches, evaluated in order.
        else_body: Nodes executed when the IF condition (and all ELSEIFs)
            are false.  Empty list means no ELSE branch.
    """

    condition: str
    condition_modifiers: list[ConditionModifier] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    elseif_clauses: list[ElseIfClause] = field(default_factory=list)
    else_body: list[Node] = field(default_factory=list)
    else_span: SourceSpan | None = None

    def children(self) -> Iterator[Node]:
        yield from self.body
        for clause in self.elseif_clauses:
            yield from clause.body
        yield from self.else_body

    def __repr__(self) -> str:
        branches = 1 + len(self.elseif_clauses) + (1 if self.else_body else 0)
        total = sum(1 for _ in self.walk()) - 1  # exclude self
        return f"IfBlock({self.span}, condition={self.condition!r}, branches={branches}, descendants={total})"


@dataclass
class LoopBlock(Node):
    """A LOOP WHILE|UNTIL ... ENDLOOP structure.

    Attributes:
        loop_type: Either ``"WHILE"`` or ``"UNTIL"``.
        condition: The condition expression text.
        body: Nodes executed on each iteration.
    """

    loop_type: str  # "WHILE" or "UNTIL"
    condition: str
    body: list[Node] = field(default_factory=list)

    def children(self) -> Iterator[Node]:
        yield from self.body

    def __repr__(self) -> str:
        return f"LoopBlock({self.span}, {self.loop_type} {self.condition!r}, body={len(self.body)})"


@dataclass
class BatchBlock(Node):
    """A BEGIN BATCH ... END BATCH structure.

    All SQL statements within the batch are executed as an atomic unit
    (committed or rolled back together).

    Attributes:
        body: Nodes within the batch.
    """

    body: list[Node] = field(default_factory=list)

    def children(self) -> Iterator[Node]:
        yield from self.body

    def __repr__(self) -> str:
        return f"BatchBlock({self.span}, body={len(self.body)})"


@dataclass
class ScriptBlock(Node):
    """A BEGIN SCRIPT name ... END SCRIPT structure.

    Defines a named, reusable block of commands that can be invoked later
    via EXECUTE SCRIPT.

    Attributes:
        name: The script block name (lowercased).
        param_names: Optional list of formal parameter names.
        body: Nodes within the script block.
    """

    name: str
    param_names: list[str] | None = None
    body: list[Node] = field(default_factory=list)

    def children(self) -> Iterator[Node]:
        yield from self.body

    def __repr__(self) -> str:
        params = f", params={self.param_names}" if self.param_names else ""
        return f"ScriptBlock({self.span}, name={self.name!r}{params}, body={len(self.body)})"


@dataclass
class SqlBlock(Node):
    """A BEGIN SQL ... END SQL structure.

    Multi-line SQL that should be treated as a single statement, even if
    it contains semicolons on intermediate lines.

    Attributes:
        body: Nodes within the SQL block (typically a single
            :class:`SqlStatement`).
    """

    body: list[Node] = field(default_factory=list)

    def children(self) -> Iterator[Node]:
        yield from self.body

    def __repr__(self) -> str:
        return f"SqlBlock({self.span}, body={len(self.body)})"


@dataclass
class IncludeDirective(Node):
    """An INCLUDE or EXECUTE SCRIPT reference to an external file or named script.

    Resolution happens at execution time, not parse time.

    Attributes:
        target: The file path or script name to include.
        is_execute_script: True if this is ``EXECUTE SCRIPT`` (named block
            invocation) rather than ``INCLUDE`` (file inclusion).
        if_exists: True if the ``IF EXISTS`` modifier was present (skip
            silently if the target does not exist).
        arguments: Optional argument expression for EXECUTE SCRIPT.
        loop_type: Optional ``"WHILE"`` or ``"UNTIL"`` for looped execution.
        loop_condition: The loop condition expression, if *loop_type* is set.
    """

    target: str
    is_execute_script: bool = False
    if_exists: bool = False
    arguments: str | None = None
    loop_type: str | None = None
    loop_condition: str | None = None

    def __repr__(self) -> str:
        kind = "EXECUTE SCRIPT" if self.is_execute_script else "INCLUDE"
        loop = f" {self.loop_type} {self.loop_condition}" if self.loop_type else ""
        return f"IncludeDirective({self.span}, {kind} {self.target!r}{loop})"


# ---------------------------------------------------------------------------
# Top-level container
# ---------------------------------------------------------------------------


@dataclass
class Script:
    """Top-level container for a parsed script file.

    Not a :class:`Node` subclass because it represents an entire file, not a
    syntactic element within one.

    Attributes:
        source: Path or name of the source file.
        body: The ordered sequence of top-level nodes.
    """

    source: str
    body: list[Node] = field(default_factory=list)

    def walk(self) -> Iterator[Node]:
        """Depth-first traversal of all nodes in the script."""
        for node in self.body:
            yield from node.walk()

    @property
    def span(self) -> SourceSpan | None:
        """Return a span covering the entire script, or None if empty."""
        if not self.body:
            return None
        first = self.body[0].span
        last = self.body[-1].span
        return SourceSpan(
            file=self.source,
            start_line=first.start_line,
            end_line=last.effective_end_line,
        )

    def __repr__(self) -> str:
        return f"Script({self.source!r}, nodes={len(self.body)})"


# ---------------------------------------------------------------------------
# Tree formatting
# ---------------------------------------------------------------------------


def format_tree(script: Script) -> str:
    """Return a human-readable tree representation of a :class:`Script`.

    Example output::

        Script: pipeline.sql (12 nodes)
        ├── [1] SUB table = users
        ├── [3-5] IF (HAS_ROWS)
        │   ├── [4] SELECT * FROM users;
        │   └── ELSE
        │       └── [6] LOG "no rows"
        ├── [7] SELECT 1;
        └── [8-10] LOOP WHILE (ROW_COUNT_GT(0))
            └── [9] DELETE FROM t LIMIT 100;
    """
    lines: list[str] = []
    lines.append(f"Script: {script.source} ({len(script.body)} nodes)")
    _format_nodes(script.body, lines, prefix="")
    return "\n".join(lines)


def _format_nodes(nodes: list[Node], lines: list[str], prefix: str) -> None:
    """Recursively format a list of nodes into tree lines."""
    for i, node in enumerate(nodes):
        is_last = i == len(nodes) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")

        loc = _format_location(node.span)
        label = _node_label(node)
        lines.append(f"{prefix}{connector}{loc}{label}")

        # Render children based on node type
        if isinstance(node, IfBlock):
            _format_if_block(node, lines, child_prefix)
        elif isinstance(node, (LoopBlock, BatchBlock, ScriptBlock, SqlBlock)):
            _format_nodes(node.body, lines, child_prefix)


def _format_if_block(node: IfBlock, lines: list[str], prefix: str) -> None:
    """Format the branches of an IF block.

    ELSEIF and ELSE are rendered as section headers at the same indent
    level as the IF body — they are sibling branches, not nested children.
    """
    # IF body (the "then" branch)
    if node.body:
        _format_nodes(node.body, lines, prefix)

    # ELSEIF clauses — section headers at the same level
    for clause in node.elseif_clauses:
        loc = _format_location(clause.span)
        lines.append(f"{prefix}{loc}ELSEIF ({clause.condition})")
        if clause.body:
            _format_nodes(clause.body, lines, prefix)

    # ELSE body — section header at the same level
    if node.else_body:
        if node.else_span:
            loc = _format_location(node.else_span)
        else:
            loc = ""
        lines.append(f"{prefix}{loc}ELSE")
        _format_nodes(node.else_body, lines, prefix)


def _format_location(span: SourceSpan) -> str:
    """Format a source span as a dim, bracket-enclosed location prefix."""
    end = span.effective_end_line
    if end == span.start_line:
        return f"[dim]\\[{span.start_line}][/dim] "
    return f"[dim]\\[{span.start_line}-{end}][/dim] "


def _tag(name: str) -> str:
    """Return a Rich-colored type tag for parse-tree output."""
    # Color scheme: SQL=cyan, CMD=green, CMT=dim, blocks=yellow, includes=magenta
    _COLORS = {
        "SQL": "bold cyan",
        "CMD": "bold green",
        "CMT": "dim",
        "IF": "bold yellow",
        "LOOP": "bold yellow",
        "BATCH": "bold yellow",
        "SCRIPT": "bold yellow",
        "SQL_BLK": "bold yellow",
        "INC": "bold magenta",
    }
    color = _COLORS.get(name, "")
    if color:
        return f"[{color}]<{name}>[/{color}]"
    return f"<{name}>"


_PREVIEW_LEN = 60


def _truncate(text: str, maxlen: int = _PREVIEW_LEN) -> str:
    """Truncate *text* to *maxlen* characters, appending ``...`` if clipped."""
    if len(text) <= maxlen:
        return text
    return text[:maxlen] + "..."


def _node_label(node: Node) -> str:
    """Return a concise label for a node.

    Each label is prefixed with a Rich-colored ``<TAG>`` indicating the
    node type: ``<SQL>``, ``<CMD>``, ``<CMT>``, ``<IF>``, ``<LOOP>``,
    ``<BATCH>``, ``<SCRIPT>``, ``<SQL_BLK>``, ``<INC>``.
    """
    if isinstance(node, SqlStatement):
        preview = _truncate(node.text.replace("\n", " "))
        return f"{_tag('SQL')} {preview}"
    if isinstance(node, MetaCommandStatement):
        preview = _truncate(node.command)
        return f"{_tag('CMD')} {preview}"
    if isinstance(node, Comment):
        lines = node.text.split("\n")
        first = _truncate(lines[0].strip())
        if len(lines) > 1:
            return f"{_tag('CMT')} {first} (+{len(lines) - 1} lines)"
        return f"{_tag('CMT')} {first}"
    if isinstance(node, IfBlock):
        parts = [f"IF ({node.condition})"]
        for mod in node.condition_modifiers:
            keyword = "ANDIF" if mod.kind == "AND" else "ORIF"
            parts.append(f"{keyword} ({mod.condition})")
        return f"{_tag('IF')} {' '.join(parts)}"
    if isinstance(node, LoopBlock):
        return f"{_tag('LOOP')} {node.loop_type} ({node.condition})"
    if isinstance(node, BatchBlock):
        return f"{_tag('BATCH')} BEGIN BATCH"
    if isinstance(node, ScriptBlock):
        params = f" ({', '.join(node.param_names)})" if node.param_names else ""
        return f"{_tag('SCRIPT')} {node.name}{params}"
    if isinstance(node, SqlBlock):
        return f"{_tag('SQL_BLK')} BEGIN SQL"
    if isinstance(node, IncludeDirective):
        exists = " IF EXISTS" if node.if_exists else ""
        if node.is_execute_script:
            extra = ""
            if node.loop_type:
                extra = f" {node.loop_type} ({node.loop_condition})"
            return f"{_tag('INC')} EXECUTE SCRIPT{exists} {node.target}{extra}"
        return f"{_tag('INC')} INCLUDE{exists} {node.target}"
    return repr(node)  # pragma: no cover
