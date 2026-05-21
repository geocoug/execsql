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

from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import MetacommandStmt, ScriptCmd, SqlStmt, current_script_line


def x_extendscript(**kwargs: Any) -> None:
    script1 = kwargs["script1"].lower()
    if script1 not in _state.savedscripts:
        raise ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script1}.")
    script2 = kwargs["script2"].lower()
    if script2 not in _state.savedscripts:
        raise ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script2}.")
    s1 = _state.savedscripts[script1]
    s2 = _state.savedscripts[script2]
    for cmd in s1.cmdlist:
        s2.add(cmd)
    if s1.paramnames is not None:
        if s2.paramnames is None:
            s2.paramnames = []
        for param in s1.paramnames:
            if param not in s2.paramnames:
                s2.paramnames.append(param)


def x_extendscript_metacommand(**kwargs: Any) -> None:
    script = kwargs["script"].lower()
    if script not in _state.savedscripts:
        raise ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script}.")
    script_file, script_line_no = current_script_line()
    _state.savedscripts[script].add(
        ScriptCmd(script_file, script_line_no, "cmd", MetacommandStmt(kwargs["cmd"])),
    )


def x_extendscript_sql(**kwargs: Any) -> None:
    script = kwargs["script"].lower()
    if script not in _state.savedscripts:
        raise ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script}.")
    script_file, script_line_no = current_script_line()
    _state.savedscripts[script].add(
        ScriptCmd(script_file, script_line_no, "sql", SqlStmt(kwargs["sql"])),
    )


def x_executescript(**kwargs: Any) -> None:
    # EXECUTE SCRIPT is now handled natively by the AST executor
    # (_execute_include / _execute_script_native). This handler exists only
    # for dispatch table registration compatibility.
    raise ErrInfo(
        "cmd",
        other_msg="EXECUTE SCRIPT should be handled by the AST executor, not the dispatch table.",
    )
