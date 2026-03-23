from __future__ import annotations

"""
Error handling and reporting utilities for execsql.

Provides the functions that form the error-reporting pipeline used
throughout the codebase:

- :func:`exception_info` — extracts type, value, and source location
  from the current exception.
- :func:`exception_desc` — formats exception information as a
  human-readable string.
- :func:`write_warning` — writes a non-fatal warning message.
- :func:`exit_now` — terminates execution after optional halt hooks.
- :func:`fatal_error` — logs a fatal error and calls :func:`exit_now`.
"""

import datetime
import os
import sys
import time
import traceback
from typing import Any, Optional

import execsql.state as _state
from execsql.exceptions import ErrInfo


def exception_info() -> tuple:
    # Returns the exception type, value, source file name, source line number, and source line text.
    strace = traceback.extract_tb(sys.exc_info()[2])[-1:]
    traces = traceback.extract_tb(sys.exc_info()[2])
    xline = 0
    for trace in traces:
        if "execsql" in trace[0]:
            xline = trace[1]
    exc_message = ""
    exc_param = sys.exc_info()[1]
    if isinstance(exc_param, str):
        exc_message = exc_param
    else:
        if hasattr(exc_param, "message") and isinstance(exc_param.message, str) and len(exc_param.message) > 0:
            exc_message = exc_param.message
        elif hasattr(exc_param, "value") and isinstance(exc_param.value, str) and len(exc_param.value) > 0:
            exc_message = exc_param.value
        else:
            exc_message = str(exc_param)
    try:
        exc_message = str(exc_message)
    except Exception:
        exc_message = repr(exc_message)
    xinfo = sys.exc_info()[0]
    xname = getattr(xinfo, "__name__", "")
    return xname, exc_message, strace[0][0], xline, strace[0][3]


def exception_desc() -> str:
    exc_type, exc_strval, exc_filename, exc_lineno, exc_linetext = exception_info()
    return f"{exc_type}: {exc_strval} in {exc_filename} on line {exc_lineno} of execsql."


def exit_now(exit_status: int, errinfo: Optional[ErrInfo], logmsg: Optional[str] = None) -> None:
    em = None
    if errinfo is not None:
        em = errinfo.write()
        if _state.err_halt_writespec is not None:
            try:
                _state.err_halt_writespec.write()
            except Exception:
                _state.exec_log.log_status_error("Failed to write the ON ERROR_HALT WRITE message.")
    if exit_status == 2:
        # User canceled
        if _state.cancel_halt_writespec is not None:
            try:
                _state.cancel_halt_writespec.write()
            except Exception:
                _state.exec_log.log_status_error("Failed to write the ON CANCEL_HALT WRITE message.")
    # Defer import to avoid circular dependencies
    from execsql.utils.gui import gui_console_isrunning, gui_console_wait_user, gui_console_off

    if gui_console_isrunning():
        if errinfo is not None:
            if _state.conf.gui_wait_on_error_halt:
                gui_console_wait_user("Script error; close the console window to exit execsql.")
                if gui_console_isrunning():
                    gui_console_off()
        elif _state.conf.gui_wait_on_exit:
            gui_console_wait_user("Script complete; close the console window to exit execsql.")
            if gui_console_isrunning():
                gui_console_off()
    if errinfo is not None and _state.err_halt_email is not None:
        try:
            _state.err_halt_email.send()
        except Exception:
            _state.exec_log.log_status_error("Failed to send the ON ERROR_HALT EMAIL message.")
    if errinfo is not None and _state.err_halt_exec is not None:
        errexec = _state.err_halt_exec
        _state.err_halt_exec = None
        _state.commandliststack = []
        errexec.execute()
        _state.runscripts()
    if exit_status == 2 and _state.cancel_halt_mailspec is not None:
        try:
            _state.cancel_halt_mailspec.send()
        except Exception:
            _state.exec_log.log_status_error("Failed to send the ON CANCEL_HALT EMAIL message.")
    if exit_status == 2 and _state.cancel_halt_exec is not None:
        cancelexec = _state.cancel_halt_exec
        _state.cancel_halt_exec = None
        _state.commandliststack = []
        cancelexec.execute()
        _state.runscripts()
    if exit_status > 0:
        if _state.exec_log:
            if logmsg:
                _state.exec_log.log_exit_error(logmsg)
            else:
                if em:
                    _state.exec_log.log_exit_error(em)
    if _state.exec_log is not None:
        _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
        _state.exec_log.close()
    from execsql.utils.fileio import filewriter_end

    filewriter_end()
    sys.exit(exit_status)


def fatal_error(error_msg: Optional[str] = None) -> None:
    exit_now(1, ErrInfo("error", other_msg=error_msg))


def write_warning(warning_msg: str) -> None:
    _state.exec_log.log_status_warning(warning_msg)
    if _state.conf.write_warnings:
        _state.output.write_err(f"**** Warning {warning_msg}")


def file_size_date(filename: str) -> tuple:
    # Returns the file size and date (as string) of the given file.
    s_file = os.path.abspath(filename)
    f_stat = os.stat(s_file)
    return f_stat.st_size, time.strftime("%Y-%m-%d %H:%M", time.gmtime(f_stat.st_mtime))


def chainfuncs(*funcs: Any) -> Any:
    funclist = funcs

    def execchain(*args: Any) -> None:
        for f in funclist:
            f()

    return execchain


def as_none(item: Any) -> Any:
    if isinstance(item, str) and len(item) == 0:
        return None
    elif isinstance(item, int) and item == 0:
        return None
    return item
