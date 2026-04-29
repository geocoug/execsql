"""Cached keyword metadata for completions and hover.

Loads the metacommand dispatch table and condition table once, then
provides fast lookup for autocomplete candidates and hover docs.
"""

from __future__ import annotations

from functools import lru_cache

__all__ = ["get_metacommand_keywords", "get_condition_keywords", "get_builtin_vars", "get_syntax_help"]


@lru_cache(maxsize=1)
def get_metacommand_keywords() -> dict[str, list[str]]:
    """Return ``{category: [keyword, ...]}`` for all metacommands."""
    from execsql.metacommands import DISPATCH_TABLE

    return DISPATCH_TABLE.keywords_by_category()


@lru_cache(maxsize=1)
def get_condition_keywords() -> dict[str, list[str]]:
    """Return ``{category: [keyword, ...]}`` for all condition predicates."""
    from execsql.metacommands.conditions import CONDITIONAL_TABLE

    return CONDITIONAL_TABLE.keywords_by_category()


@lru_cache(maxsize=1)
def get_builtin_vars() -> frozenset[str]:
    """Return the set of built-in system variable names (upper-case, no ``$``)."""
    from execsql.cli.lint_ast import _discover_builtin_vars

    return _discover_builtin_vars()


@lru_cache(maxsize=1)
def get_syntax_help() -> dict[str, tuple[str, str]]:
    """Return ``{KEYWORD: (display_name, syntax_hint)}`` from the help module."""
    from execsql.cli.help import _SYNTAX

    return dict(_SYNTAX)


def get_all_keywords_flat() -> list[str]:
    """Return a flat sorted list of all metacommand keywords."""
    keywords = set()
    for kw_list in get_metacommand_keywords().values():
        keywords.update(kw_list)
    return sorted(keywords)


def get_all_conditions_flat() -> list[str]:
    """Return a flat sorted list of all condition predicate keywords."""
    conditions = set()
    for kw_list in get_condition_keywords().values():
        conditions.update(kw_list)
    return sorted(conditions)
