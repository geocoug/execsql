from __future__ import annotations

"""
Script-block extension and dispatch handlers for execsql.

Handlers for the named-script invocation and dynamic-extension
metacommands. Used by both the AST executor and legacy command paths:

- ``x_executescript`` — ``EXECUTE SCRIPT <name>`` / ``RUN SCRIPT <name>``
  (look up a previously-registered ``BEGIN SCRIPT`` block and run it,
  optionally with parameter bindings and a WHILE / UNTIL loop).
- ``x_extendscript`` — ``EXTEND SCRIPT <name> WITH SCRIPT|FILE …``
  (append additional commands to an existing named script block from
  an inline source).
- ``x_extendscript_metacommand`` — ``EXTEND SCRIPT … WITH METACOMMAND …``.
- ``x_extendscript_sql`` — ``EXTEND SCRIPT … WITH SQL …``.

Registration of ``BEGIN SCRIPT … END SCRIPT`` blocks themselves is
handled by the AST parser (block boundaries) and executor (registering
the block on ``ctx.ast_scripts``); this module is only the call-site /
extension handlers.
"""

import copy
from dataclasses import replace
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import current_script_line


def _get_ast_script(name: str):
    """Return the AST :class:`ScriptBlock` for ``name`` or raise ErrInfo."""
    block = _state.ast_scripts.get(name.lower())
    if block is None:
        raise ErrInfo("cmd", other_msg=f"There is no SCRIPT named {name}.")
    return block


def _new_span(source: str, line_no: int):
    """Construct a SourceSpan for a synthetic AST node created at runtime."""
    from execsql.script.ast import SourceSpan

    return SourceSpan(file=source, start_line=line_no, end_line=line_no)


def x_extendscript(**kwargs: Any) -> None:
    """Append the body of one SCRIPT to another, merging parameter names."""
    target = _get_ast_script(kwargs["script2"])
    source = _get_ast_script(kwargs["script1"])

    # Append a deep copy of the source body so future mutations don't bleed.
    target.body.extend(copy.deepcopy(source.body))

    # Merge parameter definitions, preserving the target's existing order and
    # adding any new params from the source.
    if source.param_defs:
        existing = list(target.param_defs or [])
        existing_names = {p.name for p in existing}
        for pdef in source.param_defs:
            if pdef.name not in existing_names:
                existing.append(replace(pdef))
                existing_names.add(pdef.name)
        target.param_defs = existing


def x_extendscript_metacommand(**kwargs: Any) -> None:
    """Append a single metacommand line to an existing SCRIPT body."""
    from execsql.script.ast import MetaCommandStatement

    block = _get_ast_script(kwargs["script"])
    script_file, script_line_no = current_script_line()
    span = _new_span(script_file, script_line_no or 0)
    block.body.append(MetaCommandStatement(span=span, command=kwargs["cmd"]))


def x_extendscript_sql(**kwargs: Any) -> None:
    """Append a single SQL statement to an existing SCRIPT body."""
    from execsql.script.ast import SqlStatement

    block = _get_ast_script(kwargs["script"])
    script_file, script_line_no = current_script_line()
    span = _new_span(script_file, script_line_no or 0)
    block.body.append(SqlStatement(span=span, text=kwargs["sql"]))


def x_executescript(**kwargs: Any) -> None:
    # EXECUTE SCRIPT is now handled natively by the AST executor
    # (_execute_include / _execute_script_native). This handler exists only
    # for dispatch table registration compatibility.
    raise ErrInfo(
        "cmd",
        other_msg="EXECUTE SCRIPT should be handled by the AST executor, not the dispatch table.",
    )
