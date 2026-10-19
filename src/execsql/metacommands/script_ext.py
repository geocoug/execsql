from __future__ import annotations

"""
Script-block extension and dispatch handlers for execsql.

Handlers for the named-script extension metacommands invoked by the
AST executor:

- ``x_extendscript`` — ``EXTEND SCRIPT <name> WITH SCRIPT|FILE …``
  (append additional commands to an existing named script block from
  an inline source).
- ``x_extendscript_metacommand`` — ``EXTEND SCRIPT … WITH METACOMMAND …``.
- ``x_extendscript_sql`` — ``EXTEND SCRIPT … WITH SQL …``.
- ``x_executescript`` — dispatch-table entry. The executor runs
  ``EXECUTE SCRIPT`` / ``RUN SCRIPT`` itself wherever the script writes them
  (a line of their own, an inline ``IF``, ``EXTEND SCRIPT … WITH
  METACOMMAND``); this stub is reached only by one that a substitution
  variable supplies, and reports that it cannot run.

Registration of ``BEGIN SCRIPT … END SCRIPT`` blocks themselves is
handled by the AST parser (block boundaries) and executor (registering
the block on ``ctx.ast_scripts``); this module is only the
extension-site handlers.
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
    from execsql.script.parser import metacommand_node

    block = _get_ast_script(kwargs["script"])
    script_file, script_line_no = current_script_line()
    span = _new_span(script_file, script_line_no or 0)
    block.body.append(metacommand_node(kwargs["cmd"].strip(), span))


def x_extendscript_sql(**kwargs: Any) -> None:
    """Append a single SQL statement to an existing SCRIPT body."""
    from execsql.script.ast import SqlStatement

    block = _get_ast_script(kwargs["script"])
    script_file, script_line_no = current_script_line()
    span = _new_span(script_file, script_line_no or 0)
    block.body.append(SqlStatement(span=span, text=kwargs["sql"]))


def x_executescript(**kwargs: Any) -> None:
    # The executor runs EXECUTE SCRIPT itself (an IncludeDirective) wherever
    # the script writes it. Only a metacommand whose text a substitution
    # variable supplies (-- !x! !!cmd!!) reaches the dispatch table. The entry
    # also gives EXECUTE / RUN SCRIPT their place in the keyword list, the
    # language server and the run manifest.
    raise ErrInfo(
        "cmd",
        other_msg="An EXECUTE SCRIPT that a substitution variable supplies cannot run; write it in the script.",
    )
