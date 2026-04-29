"""Document analysis for the execsql language server.

Parses a document, runs lint checks, extracts symbols, and builds
variable scope information for other LSP features.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from execsql.exceptions import ErrInfo
from execsql.script.ast import (
    BatchBlock,
    IfBlock,
    LoopBlock,
    MetaCommandStatement,
    Node,
    Script,
    ScriptBlock,
    SourceSpan,
    SqlBlock,
)

__all__ = ["AnalysisResult", "analyze_document"]

_RX_SUB = re.compile(r"^\s*SUB\s+(?P<name>[+~]?\w+)\s+", re.I)
_RX_SUB_EMPTY = re.compile(r"^\s*SUB_EMPTY\s+(?P<name>[+~]?\w+)\s*$", re.I)
_RX_SUB_ADD = re.compile(r"^\s*SUB_ADD\s+(?P<name>[+~]?\w+)\s+", re.I)
_RX_SUB_APPEND = re.compile(r"^\s*SUB_APPEND\s+(?P<name>[+~]?\w+)\s", re.I)
_RX_SUBDATA = re.compile(r"^\s*SUBDATA\s+(?P<name>[+~]?\w+)\s+", re.I)
_RX_SUB_LOCAL = re.compile(r"^\s*SUB_LOCAL\s+(?P<name>\w+)\s+", re.I)
_RX_SUB_TEMPFILE = re.compile(r"^\s*SUB_TEMPFILE\s+(?P<name>\w+)\s", re.I)

_SUB_PATTERNS = [_RX_SUB, _RX_SUB_EMPTY, _RX_SUB_ADD, _RX_SUB_APPEND, _RX_SUBDATA, _RX_SUB_LOCAL, _RX_SUB_TEMPFILE]


# ---------------------------------------------------------------------------
# Analysis result
# ---------------------------------------------------------------------------


@dataclass
class DocumentSymbol:
    """A symbol in the document (for outline view)."""

    name: str
    kind: str  # "script", "if", "loop", "batch", "sql_block"
    span: SourceSpan
    children: list[DocumentSymbol] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis of a single document."""

    uri: str
    script: Script | None = None
    parse_error: str | None = None
    diagnostics: list[tuple[str, int, int, str]] = field(default_factory=list)
    # (severity, start_line, end_line, message)
    script_blocks: dict[str, SourceSpan] = field(default_factory=dict)
    defined_vars: dict[str, int] = field(default_factory=dict)
    # var_name -> line where defined
    symbols: list[DocumentSymbol] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def analyze_document(uri: str, source: str) -> AnalysisResult:
    """Parse and analyze a document, returning all LSP-relevant information."""
    from execsql.script.parser import parse_string

    result = AnalysisResult(uri=uri)

    # Parse
    try:
        script = parse_string(source, source_name=uri)
        result.script = script
    except ErrInfo as exc:
        result.parse_error = exc.errmsg()
        result.diagnostics.append(("error", 1, 1, exc.errmsg()))
        return result

    # Lint
    try:
        from execsql.cli.lint_ast import lint_ast

        issues = lint_ast(script, script_path=_uri_to_path(uri))
        for severity, _source, line_no, message in issues:
            result.diagnostics.append((severity, line_no, line_no, message))
    except Exception:
        pass  # lint failure shouldn't break the LSP

    # Extract script blocks
    _extract_script_blocks(script.body, result.script_blocks)

    # Extract variable definitions
    _extract_vars(script.body, result.defined_vars)

    # Build document symbols
    result.symbols = _build_symbols(script.body)

    return result


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _extract_script_blocks(nodes: list[Node], blocks: dict[str, SourceSpan]) -> None:
    """Recursively find ScriptBlock nodes and record their name → span."""
    for node in nodes:
        if isinstance(node, ScriptBlock):
            blocks[node.name] = node.span
        # Recurse into block children
        if isinstance(node, (IfBlock, LoopBlock, BatchBlock, ScriptBlock, SqlBlock)):
            _extract_script_blocks(list(node.children()), blocks)


def _extract_vars(nodes: list[Node], defined: dict[str, int]) -> None:
    """Walk nodes and record variable definitions with their line numbers."""
    for node in nodes:
        if isinstance(node, MetaCommandStatement):
            for rx in _SUB_PATTERNS:
                m = rx.match(node.command)
                if m:
                    name = m.group("name").lstrip("+~")
                    defined[name] = node.span.start_line
                    break

        # Recurse into block children
        if isinstance(node, (IfBlock, LoopBlock, BatchBlock, ScriptBlock, SqlBlock)):
            _extract_vars(list(node.children()), defined)


def _build_symbols(nodes: list[Node]) -> list[DocumentSymbol]:
    """Build document symbols for the outline view."""
    symbols = []
    for node in nodes:
        if isinstance(node, ScriptBlock):
            params = f"({', '.join(node.param_names)})" if node.param_names else ""
            sym = DocumentSymbol(
                name=f"SCRIPT {node.name}{params}",
                kind="script",
                span=node.span,
                children=_build_symbols(node.body),
            )
            symbols.append(sym)
        elif isinstance(node, IfBlock):
            sym = DocumentSymbol(
                name=f"IF ({node.condition})",
                kind="if",
                span=node.span,
                children=_build_symbols(node.body),
            )
            symbols.append(sym)
        elif isinstance(node, LoopBlock):
            sym = DocumentSymbol(
                name=f"LOOP {node.loop_type} ({node.condition})",
                kind="loop",
                span=node.span,
                children=_build_symbols(node.body),
            )
            symbols.append(sym)
        elif isinstance(node, BatchBlock):
            sym = DocumentSymbol(
                name="BATCH",
                kind="batch",
                span=node.span,
                children=_build_symbols(node.body),
            )
            symbols.append(sym)
    return symbols


def _uri_to_path(uri: str) -> str | None:
    """Convert a file:// URI to a filesystem path, or return None."""
    if uri.startswith("file://"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(uri)
        return unquote(parsed.path)
    return None
