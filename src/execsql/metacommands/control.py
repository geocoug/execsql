from __future__ import annotations

"""
Control-flow metacommand handlers for execsql.

Implements the imperative ``x_*`` functions for script flow control:

- Loop management: ``x_loop`` (LOOP … END LOOP), ``x_while_loop``
  (WHILE … END LOOP), ``x_until_loop`` (UNTIL … END LOOP)
- Batch control: ``x_begin_batch``, ``x_end_batch``, ``x_commit``,
  ``x_rollback``
- Script include/execute: ``x_include``, ``x_execute_script``
- Named scripts: ``x_begin_script``, ``x_end_script``, ``x_run_script``
- Error/halt control: ``x_halt``, ``x_on_error``, ``x_on_cancel``
- Counter operations: ``x_set_counter``, ``x_increment_counter``
- Substitution variable assignment: ``x_set``
"""

import time

from execsql.exceptions import ErrInfo
from typing import Any

import execsql.state as _state
from execsql.script import (
    CommandList,
    CommandListUntilLoop,
    CommandListWhileLoop,
    MetacommandStmt,
    ScriptCmd,
    current_script_line,
)
from execsql.utils.errors import exit_now, write_warning
from execsql.utils.fileio import EncodedFile, check_dir
from execsql.utils.gui import GUI_HALT, GuiSpec, enable_gui, gui_console_isrunning


def x_assert(**kwargs: Any) -> None:
    """Evaluate a condition and raise ErrInfo if it is false.

    Syntax::

        -- !x! ASSERT <condition> ["message"]
        -- !x! ASSERT <condition> ['message']
        -- !x! ASSERT <condition>

    Args:
        **kwargs: Keyword arguments injected by the dispatch table.
            ``condtest`` — the condition expression string.
            ``message``  — optional user-supplied failure message; may be None.

    Raises:
        ErrInfo: When the condition evaluates to False (or raises internally
            for an unrecognized condition).
    """
    condition: str = kwargs["condtest"].strip()
    raw_message: str | None = kwargs.get("message")
    if raw_message:
        # Strip surrounding quotes that the regex captured
        message: str = raw_message.strip("'\"")
    else:
        message = f"Assertion failed: {condition}"

    result = _state.xcmd_test(condition)
    if result:
        if _state.exec_log is not None:
            _state.exec_log.log_user_msg(f"ASSERT passed: {condition}")
    else:
        raise ErrInfo(type="assert", other_msg=message)


def x_if(**kwargs: Any) -> None:
    tf_value = _state.xcmd_test(kwargs["condtest"])
    if tf_value:
        src, line_no = current_script_line()
        metacmd = MetacommandStmt(kwargs["condcmd"])
        script_cmd = ScriptCmd(src, line_no, "cmd", metacmd)
        cmdlist = CommandList([script_cmd], f"{src}_{line_no}")
        _state.commandliststack.append(cmdlist)
    return None


def x_if_orif(**kwargs: Any) -> None:
    if _state.if_stack.all_true():
        return None  # Short-circuit evaluation
    if _state.if_stack.only_current_false():
        _state.if_stack.replace(_state.xcmd_test(kwargs["condtest"]))
    return None


def x_if_andif(**kwargs: Any) -> None:
    if _state.if_stack.all_true():
        _state.if_stack.replace(_state.if_stack.current() and _state.xcmd_test(kwargs["condtest"]))
    return None


def x_if_elseif(**kwargs: Any) -> None:
    if _state.if_stack.only_current_false():
        _state.if_stack.replace(_state.xcmd_test(kwargs["condtest"]))
    else:
        _state.if_stack.replace(False)
    return None


def x_if_else(**kwargs: Any) -> None:
    if _state.if_stack.all_true() or _state.if_stack.only_current_false():
        _state.if_stack.invert()
    return None


def x_if_block(**kwargs: Any) -> None:
    if _state.if_stack.all_true():
        _state.if_stack.nest(_state.xcmd_test(kwargs["condtest"]))
    else:
        _state.if_stack.nest(False)
    return None


def x_if_end(**kwargs: Any) -> None:
    _state.if_stack.unnest()
    return None


def x_loop(**kwargs: Any) -> None:
    _state.compiling_loop = True
    looptype = kwargs["looptype"].upper()
    loopcond = kwargs["loopcond"]
    listname = "loop" + str(len(_state.loopcommandstack) + 1)
    if looptype == "WHILE":
        _state.loopcommandstack.append(
            CommandListWhileLoop([], listname, paramnames=None, loopcondition=loopcond),
        )
    else:
        _state.loopcommandstack.append(
            CommandListUntilLoop([], listname, paramnames=None, loopcondition=loopcond),
        )


def x_halt(**kwargs: Any) -> None:
    errmsg = kwargs["errmsg"]
    tee = kwargs["tee"]
    tee = bool(tee)
    outf = kwargs["filename"]
    errlevel = kwargs["errorlevel"]
    conf = _state.conf
    if outf:
        check_dir(outf)
        of = EncodedFile(outf, conf.output_encoding).open("a")
        try:
            of.write(f"{errmsg}\n")
        finally:
            of.close()
    if conf.tee_write_log:
        _state.exec_log.log_user_msg(errmsg)
    use_gui = gui_console_isrunning()
    if errmsg and (use_gui or conf.gui_level > 1):
        x_halt_msg(table=None, schema=None, **kwargs)
        return
    if errlevel:
        errlevel = int(errlevel)
    else:
        errlevel = 3
    if errmsg:
        _state.output.write_err(errmsg)
    script, lno = current_script_line()
    _state.exec_log.log_exit_halt(script, lno, msg=errmsg)
    exit_now(errlevel, None)


def x_error_halt(**kwargs: Any) -> None:
    flag = kwargs["onoff"].lower()
    if flag not in ("on", "off", "yes", "no", "true", "false"):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized flag for error handling: {flag}",
        )
    _state.status.halt_on_err = flag in ("on", "yes", "true")
    return None


def x_metacommand_error_halt(**kwargs: Any) -> None:
    flag = kwargs["onoff"].lower()
    if flag not in ("on", "off", "yes", "no", "true", "false"):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized flag for metacommand error handling: {flag}",
        )
    _state.status.halt_on_metacommand_err = flag in ("on", "yes", "true")
    return None


def x_begin_batch(**kwargs: Any) -> None:
    _state.status.batch.new_batch()
    return None


def x_end_batch(**kwargs: Any) -> None:
    _state.status.batch.end_batch()
    return None


def x_rollback(**kwargs: Any) -> None:
    _state.status.batch.rollback_batch()


def x_break(**kwargs: Any) -> None:
    if len(_state.commandliststack) == 1:
        src, line_no = current_script_line()
        write_warning(f"BREAK metacommand with no command nesting on line {line_no} of {src}")
    else:
        _state.if_stack.if_levels = _state.if_stack.if_levels[: _state.commandliststack[-1].init_if_level]
        _state.commandliststack.pop()
    return None


def x_wait_until(**kwargs: Any) -> None:
    countdown = int(kwargs["seconds"])
    while countdown > 0:
        if _state.xcmd_test(kwargs["condition"]):
            return
        time.sleep(1)
        countdown -= 1
    if kwargs["end"].lower() == "halt":
        _state.exec_log.log_exit_halt(
            *current_script_line(),
            msg="Halted at expiration of WAIT_UNTIL metacommand.",
        )
        exit_now(2, None)
    return None


# x_halt_msg is also needed by x_halt - define it here
def x_halt_msg(**kwargs: Any) -> None:
    import queue as _queue

    errmsg = kwargs["errmsg"]
    tee = kwargs["tee"]
    tee = bool(tee)
    outf = kwargs["filename"]
    errlevel = kwargs["errorlevel"]
    if errlevel:
        errlevel = int(errlevel)
    else:
        errlevel = 3
    conf = _state.conf
    if outf:
        check_dir(outf)
        of = EncodedFile(outf, conf.output_encoding).open("a")
        try:
            of.write(f"{errmsg}\n")
        finally:
            of.close()
    schema = kwargs.get("schema")
    table = kwargs.get("table")
    if table:
        db = _state.dbs.current()
        db_obj = db.schema_qualified_table_name(schema, table)
        sql = f"select * from {db_obj};"
        headers, rows = db.select_data(sql)
    else:
        headers, rows = None, None
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": "HALT",
        "message": errmsg,
        "button_list": [("OK", 1, "<Return>")],
        "no_cancel": True,
        "column_headers": headers,
        "rowset": rows,
        "help_url": None,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_HALT, gui_args, return_queue))
    return_queue.get(block=True)
    _state.exec_log.log_exit_halt(*current_script_line(), msg=errmsg)
    exit_now(errlevel, None)
