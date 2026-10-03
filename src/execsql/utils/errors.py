from __future__ import annotations

"""
Error handling and reporting utilities for execsql.

Provides the functions that form the error-reporting pipeline used
throughout the codebase:

- :func:`exception_info` — extracts type, value, and source location
  from the current exception.
- :func:`exception_desc` — ``Type: message`` for the exception being
  handled, as shown on screen.
- :func:`error_origin` / :func:`logged_error` — where in execsql an error
  was raised, added to the message written to the log.
- :func:`write_warning` — writes a non-fatal warning message.
- :func:`exit_now` — terminates execution after optional halt hooks.
- :func:`fatal_error` — logs a fatal error and calls :func:`exit_now`.
"""

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo

__all__ = [
    "exception_info",
    "error_origin",
    "exception_desc",
    "logged_error",
    "exit_now",
    "fatal_error",
    "stamp_errinfo",
    "write_warning",
    "file_size_date",
]


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
    elif exc_param is not None:
        message = getattr(exc_param, "message", None)
        value = getattr(exc_param, "value", None)
        if isinstance(message, str) and len(message) > 0:
            exc_message = message
        elif isinstance(value, str) and len(value) > 0:
            exc_message = value
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
    """``Type: message`` for the exception being handled, as shown to the person running the script.

    Where in execsql it was raised is for the log: see :func:`error_origin`.
    """
    exc_type, exc_strval, _filename, _lineno, _linetext = exception_info()
    return f"{exc_type}: {exc_strval}"


def error_origin(exc: BaseException) -> str | None:
    """Where in the execsql package the error behind *exc* was raised, as ``execsql/db/base.py:254``.

    Follows *exc* to the exception it was raised from, and returns the last
    frame of that traceback inside the package, or ``None`` when there is none.
    """
    package = Path(__file__).resolve().parents[1]
    cause = exc.__cause__ or exc.__context__ or exc
    origin = None
    for frame in traceback.extract_tb(cause.__traceback__):
        path = Path(frame.filename).resolve()
        if path.is_relative_to(package):
            origin = f"{path.relative_to(package.parent).as_posix()}:{frame.lineno}"
    return origin


def logged_error(errinfo: ErrInfo) -> str:
    """The error message for the log: what the screen shows, plus :func:`error_origin` when known."""
    origin = error_origin(errinfo)
    message = errinfo.errmsg()
    return f"{message}\n     Raised at: {origin}" if origin else message


def stamp_errinfo(errinfo: ErrInfo) -> ErrInfo:
    """Attach script location from ``_state.last_command`` to an :class:`~execsql.exceptions.ErrInfo`.

    Reads the source file name, line number, command text, and command type from
    the most-recently-executed statement and
    populates any ``None`` fields on *errinfo*.  This ensures that error messages
    include "Line N of script foo.sql" context even when the ErrInfo was originally
    created deep inside a handler that had no access to execution state.

    Args:
        errinfo: The :class:`~execsql.exceptions.ErrInfo` to stamp.

    Returns:
        The same *errinfo* object, with location fields populated.
    """
    lc = _state.last_command
    if lc is not None and errinfo.script_file is None:
        errinfo.script_file = lc.source
        errinfo.script_line_no = lc.line_no
        if errinfo.cmd is None:
            errinfo.cmd = lc.command.commandline() if hasattr(lc.command, "commandline") else None
            errinfo.cmdtype = lc.command_type
    return errinfo


def _run_deferred_script(spec: Any) -> None:
    """Execute a deferred ScriptExecSpec (ON ERROR_HALT / ON CANCEL_HALT EXECUTE SCRIPT).

    Executes the target script natively through the AST executor.
    """
    from execsql.script.ast import IncludeDirective, SourceSpan
    from execsql.script.executor import _execute_script_native
    from execsql.state import get_context

    script_id = spec.script_id.lower() if hasattr(spec, "script_id") else None
    ctx = get_context()
    if script_id and script_id in ctx.ast_scripts:
        node = IncludeDirective(
            span=SourceSpan("<error-halt>", 0),
            target=spec.script_id,
            is_execute_script=True,
            arguments=spec.arg_exp,
            loop_type=spec.looptype,
            loop_condition=spec.loopcond,
        )
        _execute_script_native(ctx, node, ctx.ast_scripts[script_id])
    else:
        raise ErrInfo(
            type="error",
            other_msg=f"ON ERROR_HALT/CANCEL_HALT EXECUTE SCRIPT: no SCRIPT named {spec.script_id}.",
        )


def exit_now(exit_status: int, errinfo: ErrInfo | None, logmsg: str | None = None) -> None:
    # An error in input typed at a BREAKPOINT prompt ends
    # that input, not the run: the prompt reports it and reads the next one.
    # HALT and a canceled prompt carry no error and still end the run.
    if errinfo is not None and _state.prompt_input is not None:
        raise errinfo
    _state.halt_error = errinfo
    if errinfo is not None:
        stamp_errinfo(errinfo)
        if _state.subvars is not None:
            _state.subvars.add_substitution("$ERROR_MESSAGE", errinfo.errmsg())
        errinfo.write()
        if _state.err_halt_writespec is not None:
            try:
                _state.err_halt_writespec.write()
            except Exception:
                if _state.exec_log is not None:
                    _state.exec_log.log_status_error("Failed to write the ON ERROR_HALT WRITE message.")
    # User canceled
    if exit_status == 2 and _state.cancel_halt_writespec is not None:
        try:
            _state.cancel_halt_writespec.write()
        except Exception:
            if _state.exec_log is not None:
                _state.exec_log.log_status_error("Failed to write the ON CANCEL_HALT WRITE message.")
    # Defer import to avoid circular dependencies
    from execsql.utils.gui import gui_console_isrunning, gui_console_wait_user, gui_console_off

    if gui_console_isrunning() and _state.conf is not None:
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
            if _state.exec_log is not None:
                _state.exec_log.log_status_error("Failed to send the ON ERROR_HALT EMAIL message.")
    if errinfo is not None and _state.err_halt_exec is not None:
        errexec = _state.err_halt_exec
        _state.err_halt_exec = None
        _run_deferred_script(errexec)
    if exit_status == 2 and _state.cancel_halt_mailspec is not None:
        try:
            _state.cancel_halt_mailspec.send()
        except Exception:
            if _state.exec_log is not None:
                _state.exec_log.log_status_error("Failed to send the ON CANCEL_HALT EMAIL message.")
    if exit_status == 2 and _state.cancel_halt_exec is not None:
        cancelexec = _state.cancel_halt_exec
        _state.cancel_halt_exec = None
        _run_deferred_script(cancelexec)
    if exit_status > 0 and _state.exec_log:
        if logmsg:
            _state.exec_log.log_exit_error(logmsg)
        elif errinfo is not None:
            _state.exec_log.log_exit_error(logged_error(errinfo))
    if _state.exec_log is not None:
        _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
        _state.exec_log.close()
    from execsql.utils.fileio import filewriter_end

    filewriter_end()
    # Last, so the ON ERROR_HALT / ON CANCEL_HALT actions above are in it.
    from execsql import manifest as _manifest

    if (manifest := _manifest.current()) is not None:
        manifest.finish(exit_status, errinfo)
    sys.exit(exit_status)


def fatal_error(error_msg: str | None = None) -> None:
    exit_now(1, ErrInfo("error", other_msg=error_msg))


def write_warning(warning_msg: str, *, always: bool = False) -> None:
    """Write a non-fatal warning message to the log and optionally to stderr.

    Args:
        warning_msg: The warning text to emit.
        always: When ``True``, always write to stderr regardless of the
            ``conf.write_warnings`` setting.  Use this for structural warnings
            (e.g. IF-level mismatch, unsubstituted variables) that should always
            be visible.  When ``False`` (default), stderr output is gated by
            ``conf.write_warnings``.
    """
    if _state.exec_log is not None:
        _state.exec_log.log_status_warning(warning_msg)
    if _state.output is not None and (always or (_state.conf is not None and _state.conf.write_warnings)):
        _state.output.write_err(f"**** Warning {warning_msg}")


def file_size_date(filename: str) -> tuple:
    # Returns the file size and date (as string) of the given file.
    s_file = str(Path(filename).resolve())
    f_stat = os.stat(s_file)
    return f_stat.st_size, time.strftime("%Y-%m-%d %H:%M", time.gmtime(f_stat.st_mtime))
