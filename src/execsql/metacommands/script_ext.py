from __future__ import annotations

"""
Script extension metacommand handlers for execsql.

Implements metacommands that extend or augment a running script:

- ``x_extendscript`` — EXTEND SCRIPT (append additional commands from
  a file into the current script stream)
- Other substitution-variable and script-modification helpers.
"""

from typing import Any

import execsql.state as _state


def x_extendscript(**kwargs: Any) -> None:
    script1 = kwargs["script1"].lower()
    if script1 not in _state.savedscripts:
        raise _state.ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script1}.")
    script2 = kwargs["script2"].lower()
    if script2 not in _state.savedscripts:
        raise _state.ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script2}.")
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
        raise _state.ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script}.")
    script_file, script_line_no = _state.current_script_line()
    _state.savedscripts[script].add(
        _state.ScriptCmd(script_file, script_line_no, "cmd", _state.MetacommandStmt(kwargs["cmd"])),
    )


def x_extendscript_sql(**kwargs: Any) -> None:
    script = kwargs["script"].lower()
    if script not in _state.savedscripts:
        raise _state.ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script}.")
    script_file, script_line_no = _state.current_script_line()
    _state.savedscripts[script].add(
        _state.ScriptCmd(script_file, script_line_no, "sql", _state.SqlStmt(kwargs["sql"])),
    )


def x_executescript(**kwargs: Any) -> None:
    exists = kwargs["exists"]
    script_id = kwargs["script_id"].lower()
    if exists is None or (exists is not None and script_id in _state.savedscripts):
        _state.ScriptExecSpec(**kwargs).execute()
