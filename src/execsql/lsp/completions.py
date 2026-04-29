"""Completion provider for the execsql language server.

Generates autocomplete candidates for metacommand keywords, substitution
variables, and condition predicates.
"""

from __future__ import annotations

import re

from execsql.lsp.analysis import AnalysisResult
from execsql.lsp.keywords import get_all_conditions_flat, get_all_keywords_flat, get_builtin_vars

__all__ = ["get_completions"]

_EXEC_PREFIX_RX = re.compile(r"^\s*--\s*!x!\s*", re.I)
_COND_CONTEXT_RX = re.compile(r"\b(?:IF|ELSEIF|LOOP\s+(?:WHILE|UNTIL)|ASSERT)\s*\(\s*$", re.I)
_VAR_TRIGGER_RX = re.compile(r"!!\$?$")


def get_completions(
    line_text: str,
    col: int,
    analysis: AnalysisResult | None = None,
) -> list[dict]:
    """Return completion items for the given cursor position.

    Each item is a dict with ``label``, ``kind``, ``detail``, and
    optionally ``insert_text``.

    Args:
        line_text: Full text of the line.
        col: 0-based column position.
        analysis: Current document analysis (for variable definitions).
    """
    items: list[dict] = []

    # Check for variable trigger: cursor after !! or !!$
    text_before = line_text[:col]
    if _VAR_TRIGGER_RX.search(text_before):
        items.extend(_variable_completions(analysis))
        return items

    # Check if we're on a metacommand line
    m = _EXEC_PREFIX_RX.match(text_before)
    if not m:
        return items

    cmd_so_far = text_before[m.end() :]

    # Check if we're inside a condition context
    if _COND_CONTEXT_RX.search(cmd_so_far):
        items.extend(_condition_completions())
        return items

    # Metacommand keyword completions
    items.extend(_keyword_completions(cmd_so_far.strip()))
    return items


def _keyword_completions(prefix: str) -> list[dict]:
    """Return metacommand keyword completions matching the prefix."""
    all_kw = get_all_keywords_flat()
    prefix_upper = prefix.upper()

    items = []
    for kw in all_kw:
        if kw.upper().startswith(prefix_upper):
            items.append(
                {
                    "label": kw,
                    "kind": "keyword",
                    "detail": "execsql metacommand",
                },
            )
    return items


def _condition_completions() -> list[dict]:
    """Return condition predicate completions."""
    conditions = get_all_conditions_flat()
    items = []
    for cond in conditions:
        items.append(
            {
                "label": cond,
                "kind": "function",
                "detail": "condition predicate",
                "insert_text": f"{cond}(",
            },
        )
    return items


def _variable_completions(analysis: AnalysisResult | None) -> list[dict]:
    """Return substitution variable completions."""
    items = []

    # Built-in system variables
    for var_name in sorted(get_builtin_vars()):
        items.append(
            {
                "label": f"${var_name}",
                "kind": "variable",
                "detail": "system variable",
                "insert_text": f"${var_name}!!",
            },
        )

    # User-defined variables from analysis
    if analysis:
        for var_name, line_no in sorted(analysis.defined_vars.items()):
            items.append(
                {
                    "label": var_name,
                    "kind": "variable",
                    "detail": f"defined on line {line_no}",
                    "insert_text": f"{var_name}!!",
                },
            )

    return items
