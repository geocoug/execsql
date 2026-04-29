"""Hover provider for the execsql language server.

Returns Markdown-formatted documentation when hovering over metacommand
keywords, condition predicates, or substitution variable references.
"""

from __future__ import annotations

import re

from execsql.lsp.analysis import AnalysisResult
from execsql.lsp.keywords import (
    get_all_conditions_flat,
    get_all_keywords_flat,
    get_builtin_vars,
    get_syntax_help,
)

__all__ = ["get_hover"]

_EXEC_LINE_RX = re.compile(r"^\s*--\s*!x!\s*(?P<cmd>.+)$", re.I)
_VAR_REF_RX = re.compile(r"!!([$@&~#+]?\w+)!!")


def get_hover(line_text: str, col: int, analysis: AnalysisResult | None = None) -> str | None:
    """Return hover Markdown for the token at the given column, or None.

    Args:
        line_text: Full text of the line.
        col: 0-based column position.
        analysis: Current document analysis (for variable definitions).
    """
    # Check if cursor is over a variable reference
    var_hover = _hover_variable(line_text, col, analysis)
    if var_hover:
        return var_hover

    # Check if this is a metacommand line
    m = _EXEC_LINE_RX.match(line_text)
    if not m:
        return None

    cmd_text = m.group("cmd").strip()
    first_word = cmd_text.split("(")[0].split(None, 1)[0].upper() if cmd_text else ""

    # Check for condition predicates inside IF/ELSEIF/LOOP
    if first_word in ("IF", "ELSEIF", "LOOP", "ASSERT"):
        cond_hover = _hover_condition(cmd_text, col - m.start("cmd"))
        if cond_hover:
            return cond_hover

    # Look up metacommand keyword
    return _hover_metacommand(cmd_text)


def _hover_metacommand(cmd_text: str) -> str | None:
    """Look up hover docs for a metacommand keyword."""
    syntax = get_syntax_help()
    all_kw = get_all_keywords_flat()

    # Try matching against known keywords (longest match first)
    upper = cmd_text.upper()
    for kw in sorted(syntax.keys(), key=len, reverse=True):
        if upper.startswith(kw):
            display_name, syntax_hint = syntax[kw]
            hint = f" `{syntax_hint}`" if syntax_hint else ""
            return f"**{display_name}**{hint}\n\nexecsql metacommand"

    # Fall back to dispatch table keywords
    first_word = upper.split(None, 1)[0] if upper else ""
    if first_word in all_kw:
        return f"**{first_word}**\n\nexecsql metacommand"

    return None


def _hover_condition(cmd_text: str, offset: int) -> str | None:
    """Look up hover docs for a condition predicate inside a conditional."""
    conditions = get_all_conditions_flat()

    # Find the condition predicate at the cursor position
    # Look for WORD( pattern
    for cond in conditions:
        pattern = re.compile(rf"\b{re.escape(cond)}\b", re.I)
        for m in pattern.finditer(cmd_text):
            if m.start() <= offset <= m.end():
                return f"**{cond}**\n\nexecsql condition predicate"

    return None


def _hover_variable(line_text: str, col: int, analysis: AnalysisResult | None) -> str | None:
    """Show variable info when hovering over a !!var!! reference."""
    for m in _VAR_REF_RX.finditer(line_text):
        # Check if cursor is within this variable reference
        # The full match includes !! delimiters
        if m.start() <= col <= m.end():
            raw_name = m.group(1)
            sigil = raw_name[0] if raw_name and raw_name[0] in ("$", "@", "&", "~", "#", "+") else ""
            name = raw_name[len(sigil) :]

            # Classify the variable
            if sigil == "&":
                return f"**!!{raw_name}!!**\n\nEnvironment variable `{name}`"
            if sigil == "@":
                return f"**!!{raw_name}!!**\n\nColumn variable"
            if sigil == "~":
                return f"**!!{raw_name}!!**\n\nLocal (script-scope) variable"
            if sigil == "#":
                return f"**!!{raw_name}!!**\n\nScript parameter"
            if sigil == "+":
                return f"**!!{raw_name}!!**\n\nLocal variable (+ prefix)"

            # $ or no prefix — check if builtin
            builtin_vars = get_builtin_vars()
            if name.upper() in builtin_vars:
                return f"**!!{raw_name}!!**\n\nBuilt-in system variable"

            # Check if user-defined
            if analysis and name in analysis.defined_vars:
                def_line = analysis.defined_vars[name]
                return f"**!!{raw_name}!!**\n\nUser variable (defined on line {def_line})"

            return f"**!!{raw_name}!!**\n\nSubstitution variable"

    return None
