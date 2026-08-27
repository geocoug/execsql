from __future__ import annotations

"""
Control-flow metacommand handlers for execsql.

Implements the ``x_*`` functions for script flow control:

- Conditional execution: ``x_if`` and its companions ``x_if_andif``,
  ``x_if_orif``, ``x_if_elseif``, ``x_if_else``, ``x_if_end``,
  ``x_if_block`` (compound IF / ELSEIF / ELSE / ENDIF handling).
- Assertion: ``x_assert`` (ASSERT condition with optional message).
- Loop management: ``x_loop`` (LOOP … END LOOP, including WHILE/UNTIL
  variants matched by the same regex).
- Batch control: ``x_begin_batch``, ``x_end_batch``, ``x_rollback``.
- Error/halt control: ``x_halt``, ``x_halt_msg``, ``x_error_halt``,
  ``x_metacommand_error_halt``.
- Flow modifiers: ``x_break`` (exit a LOOP), ``x_wait_until``.

Handlers for related areas live in sibling modules:

- INCLUDE / EXECUTE SCRIPT / RUN / named-script registration —
  :mod:`execsql.metacommands.script_ext` (and the AST executor).
- Counter operations (RESET COUNTER, SET COUNTER) and substitution
  variable assignment (SUB, SUB_LOCAL, etc.) —
  :mod:`execsql.metacommands.data`.
- ON ERROR_HALT / ON CANCEL_HALT directives —
  :mod:`execsql.metacommands.system`.
"""

import time

from execsql.exceptions import ErrInfo
from typing import Any

import execsql.state as _state
from execsql.gui.base import format_table, row_count_text
from execsql.script import current_script_line
from execsql.utils.errors import exit_now
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


def _ast_only_stub(name: str):
    """Return an ErrInfo for a metacommand the AST executor handles structurally.

    These handlers stay registered in the dispatch table so ``--dump-keywords``,
    the VS Code grammar generator, and ``--list-keywords`` still see the
    keyword.  The AST parser converts the source form (``IF`` / ``ENDIF`` /
    ``LOOP`` / ``BEGIN BATCH`` / ``BREAK`` / ``ELSE`` / ``ELSEIF`` / ``ANDIF``
    / ``ORIF``) into structural AST nodes that the executor walks directly —
    none of these dispatch handlers fire for parsed scripts.  Reaching one
    means the AST parser failed to recognise the keyword, which is a bug.
    """
    from execsql.exceptions import ErrInfo

    return ErrInfo(
        type="cmd",
        other_msg=f"{name} should be handled by the AST executor, not the dispatch table.",
    )


def x_if(**kwargs: Any) -> None:
    raise _ast_only_stub("IF")


def x_if_orif(**kwargs: Any) -> None:
    raise _ast_only_stub("ORIF")


def x_if_andif(**kwargs: Any) -> None:
    raise _ast_only_stub("ANDIF")


def x_if_elseif(**kwargs: Any) -> None:
    raise _ast_only_stub("ELSEIF")


def x_if_else(**kwargs: Any) -> None:
    raise _ast_only_stub("ELSE")


def x_if_block(**kwargs: Any) -> None:
    raise _ast_only_stub("IF")


def x_if_end(**kwargs: Any) -> None:
    raise _ast_only_stub("ENDIF")


def x_loop(**kwargs: Any) -> None:
    raise _ast_only_stub("LOOP")


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
    raise _ast_only_stub("BEGIN BATCH")


def x_end_batch(**kwargs: Any) -> None:
    raise _ast_only_stub("END BATCH")


def x_rollback(**kwargs: Any) -> None:
    """Roll back all DBs registered in the innermost batch level."""
    _state.status.batch.rollback_batch()


def x_break(**kwargs: Any) -> None:
    raise _ast_only_stub("BREAK")


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
    """Halt the script, reporting *errmsg* in a dialog or on the console.

    The dialog is used only when the run is interactive — either a GUI console
    is already running, or ``gui_level`` is greater than 1.  Otherwise the
    message (and any ``DISPLAY`` rowset) is written to the error output and the
    script exits, so that unattended runs fail instead of blocking forever on a
    modal nobody can dismiss.
    """
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

    # Non-interactive runs (no GUI console, gui_level 0 or 1) must not block on
    # a modal dialog: report on the console and exit instead.  This mirrors the
    # guard in x_halt, which the message-bearing HALT forms never reach because
    # their metacommand patterns are registered later and so take priority.
    if not (gui_console_isrunning() or conf.gui_level > 1):
        if errmsg:
            _state.output.write_err(errmsg)
        if headers:
            # Unlike the dialog, render an empty rowset too — a HALT diagnostic
            # showing zero rows is more useful than showing nothing at all.
            _state.output.write_err(format_table(headers, rows or []))
            _state.output.write_err(row_count_text(len(rows or [])))
        _state.exec_log.log_exit_halt(*current_script_line(), msg=errmsg)
        exit_now(errlevel, None)
        return

    enable_gui()
    return_queue: _queue.Queue[Any] = _queue.Queue()
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
