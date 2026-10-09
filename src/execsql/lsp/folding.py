"""Folding ranges: metacommand blocks and their branches, multi-line SQL statements and comments.

An editor that gets folding ranges from a server stops folding by
indentation, so the ranges cover everything worth folding, not only the
blocks execsql adds.
"""

from __future__ import annotations

import re

from lsprotocol import types

from execsql.script.ast import BatchBlock, Comment, IfBlock, LoopBlock, ScriptBlock, SqlBlock, SqlStatement
from execsql.script.parser import parse_string

__all__ = ["folding_ranges"]

_BLOCKS = (IfBlock, LoopBlock, BatchBlock, ScriptBlock, SqlBlock)
# The line that closes a block, as the parser reads it: ENDIF, END LOOP, END SCRIPT, END BATCH, END SQL.
_RX_BLOCK_END = re.compile(r"^\s*--\s*!x!\s*(?:ENDIF|END\s*LOOP|END\s+(?:SCRIPT|BATCH|SQL)\b)", re.I)


def _range(start_line: int, end_line: int, kind: str | None = None) -> types.FoldingRange | None:
    """A range over 1-based *start_line*..*end_line*, or ``None`` if that is a single line."""
    if end_line <= start_line:
        return None
    return types.FoldingRange(start_line=start_line - 1, end_line=end_line - 1, kind=kind)


def folding_ranges(source: str, path: str | None) -> list[types.FoldingRange]:
    """The script's folding ranges, in document order.

    A block folds up to the line before its closing metacommand, so
    ``ENDIF`` / ``END LOOP`` / ``END SCRIPT`` stays visible (a block left
    unclosed folds to its last line); an IF folds each branch separately, up
    to the line before the next ``ELSEIF`` or ``ELSE``.
    """
    lines = source.splitlines()
    tree = parse_string(source, path or "<untitled>", errors=[])
    found: list[types.FoldingRange | None] = []
    for node in tree.walk():
        span = node.span
        end = span.effective_end_line
        if isinstance(node, _BLOCKS) and not (0 < end <= len(lines) and _RX_BLOCK_END.match(lines[end - 1])):
            end += 1  # no closing line to keep visible
        if isinstance(node, IfBlock):
            starts = [span.start_line, *(c.span.start_line for c in node.elseif_clauses)]
            if node.else_span is not None:
                starts.append(node.else_span.start_line)
            for start, following in zip(starts, [*starts[1:], end], strict=True):
                found.append(_range(start, following - 1))
        elif isinstance(node, _BLOCKS):
            found.append(_range(span.start_line, end - 1))
        elif isinstance(node, SqlStatement):
            found.append(_range(span.start_line, end))
        elif isinstance(node, Comment):
            found.append(_range(span.start_line, end, types.FoldingRangeKind.Comment))
    return sorted((r for r in found if r is not None), key=lambda r: (r.start_line, -r.end_line))
