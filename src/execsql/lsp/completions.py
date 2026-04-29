"""Completion provider for the execsql language server.

Generates autocomplete candidates for metacommand keywords with full
syntax patterns, substitution variables, and condition predicates.
"""

from __future__ import annotations

import re
from functools import lru_cache

from execsql.lsp.analysis import AnalysisResult
from execsql.lsp.keywords import get_all_conditions_flat, get_all_keywords_flat, get_builtin_vars

__all__ = ["get_completions"]

_EXEC_PREFIX_RX = re.compile(r"^\s*--\s*!x!\s*", re.I)
_COND_CONTEXT_RX = re.compile(r"\b(?:IF|ELSEIF|LOOP\s+(?:WHILE|UNTIL)|ASSERT)\s*\(\s*$", re.I)
_VAR_TRIGGER_RX = re.compile(r"!!\$?$")
_CODE_BLOCK_RX = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


def get_completions(
    line_text: str,
    col: int,
    analysis: AnalysisResult | None = None,
) -> list[dict]:
    """Return completion items for the given cursor position.

    Each item is a dict with ``label``, ``kind``, ``detail``, and
    optionally ``insert_text`` and ``documentation``.
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

    # Metacommand keyword completions with syntax patterns
    items.extend(_keyword_completions(cmd_so_far.strip()))
    return items


@lru_cache(maxsize=1)
def _build_syntax_completions() -> list[dict]:
    """Build completion items from docs and dispatch table.

    Extracts code blocks from documentation to show real syntax patterns
    as completion detail text.
    """
    from execsql.lsp.docs import _load_docs

    docs = _load_docs()
    all_kw = get_all_keywords_flat()
    items = []
    seen_labels = set()

    # Build from docs — these have rich syntax
    for heading, content in docs.items():
        # Extract first code block as the primary syntax
        code_blocks = _CODE_BLOCK_RX.findall(content)
        if code_blocks:
            syntax = code_blocks[0].strip()
            # Use first line of syntax as the detail
            first_line = syntax.split("\n")[0].strip()
        else:
            first_line = heading

        label = heading.split(" and ")[0].strip()  # "BEGIN BATCH and END BATCH" → "BEGIN BATCH"
        if label not in seen_labels:
            seen_labels.add(label)
            items.append(
                {
                    "label": label,
                    "kind": "keyword",
                    "detail": first_line,
                    "documentation": content,
                },
            )

        # Add additional syntax variants as separate completions
        for _i, block in enumerate(code_blocks[1:], 1):
            variant_syntax = block.strip().split("\n")[0].strip()
            variant_label = variant_syntax.split("(")[0].split("<")[0].strip()
            # Only add if it starts differently from the main label
            if variant_label and variant_label.upper() != label.upper() and variant_label not in seen_labels:
                seen_labels.add(variant_label)
                items.append(
                    {
                        "label": variant_label,
                        "kind": "keyword",
                        "detail": variant_syntax,
                        "documentation": content,
                    },
                )

    # Add dispatch table keywords not in docs
    for kw in all_kw:
        if kw not in seen_labels:
            seen_labels.add(kw)
            items.append(
                {
                    "label": kw,
                    "kind": "keyword",
                    "detail": "execsql metacommand",
                },
            )

    return sorted(items, key=lambda x: x["label"])


def _keyword_completions(prefix: str) -> list[dict]:
    """Return metacommand keyword completions matching the prefix."""
    all_items = _build_syntax_completions()
    prefix_upper = prefix.upper()

    if not prefix_upper:
        return all_items

    return [item for item in all_items if item["label"].upper().startswith(prefix_upper)]


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
