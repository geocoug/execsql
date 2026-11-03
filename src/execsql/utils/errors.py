from __future__ import annotations

"""
Error handling and reporting utilities for execsql.

Provides the functions that form the error-reporting pipeline used
throughout the codebase:

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
from execsql.exceptions import ErrInfo, ScriptExit

__all__ = [
    "error_origin",
    "exception_desc",
    "logged_error",
    "exit_now",
    "fatal_error",
    "stamp_errinfo",
    "write_warning",
    "file_size_date",
    "install_hint",
]

_ADDING_AN_EXTRA = "https://execsql2.readthedocs.io/en/stable/getting-started/installation/#adding-an-extra-later"


def install_hint(extra: str) -> str:
    """How to install the execsql2 *extra*, for a message about a missing optional package.

    ``uv tool install`` and ``pipx install --force`` replace an install's
    extras with the ones named, so the hint says to keep those already there.
    """
    return (
        f'Install the {extra} extra along with the extras you already have: uv tool install "execsql2[...,{extra}]" '
        f'or pipx install --force "execsql2[...,{extra}]" (in a project environment: pip install "execsql2[{extra}]"). '
        f"See {_ADDING_AN_EXTRA}"
    )


def exception_desc() -> str:
    """``Type: message`` for the exception being handled, as shown to the person running the script.

    The message is the exception's ``message`` or ``value`` attribute when it
    has a non-empty string one (as some drivers' exceptions do), else its
    ``str()``.  Where in execsql it was raised is for the log: see
    :func:`error_origin`.
    """
    exc_type, exc = sys.exc_info()[:2]
    if isinstance(exc, str):
        message = exc
    elif exc is None:
        message = ""
    else:
        attr = next(
            (v for v in (getattr(exc, "message", None), getattr(exc, "value", None)) if isinstance(v, str) and v),
            None,
        )
        try:
            message = attr if attr is not None else str(exc)
        except Exception:
            message = repr(exc)
    return f"{getattr(exc_type, '__name__', '')}: {message}"


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
            # The metacommand as written, without "-- !x!", as upstream reported it.
            errinfo.cmd = getattr(lc.command, "statement", None)
            errinfo.cmdtype = lc.command_type
    return errinfo


def _run_deferred_script(spec: Any) -> None:
    """Execute a deferred ScriptExecSpec (ON ERROR_HALT / ON CANCEL_HALT EXECUTE SCRIPT).

    Executes the target script natively through the AST executor.  Its
    arguments are substituted now, when the halt fires, so a deferred
    variable (``!{$ERROR_MESSAGE}!``) holds the error that fired it.
    """
    from execsql.script.ast import IncludeDirective, SourceSpan
    from execsql.script.engine import substitute_vars
    from execsql.script.executor import _execute_script_native, _script_args, _stack_localvars
    from execsql.script.parser import substitute_directive
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
            command=(
                f"EXECUTE SCRIPT {spec.script_id}"
                + (f" WITH ARGUMENTS ({spec.arg_exp})" if spec.arg_exp else "")
                + (f" {spec.looptype} ({spec.loopcond})" if spec.looptype else "")
            ),
        )
        localvars = _stack_localvars(ctx)
        node = substitute_directive(node, lambda text: substitute_vars(text, localvars, ctx=ctx))
        script_block = ctx.ast_scripts[script_id]
        _execute_script_native(ctx, node, script_block, _script_args(node, script_block))
    else:
        raise ErrInfo(
            type="error",
            other_msg=f"ON ERROR_HALT/CANCEL_HALT EXECUTE SCRIPT: no SCRIPT named {spec.script_id}.",
        )


#: How long a halt waits for an output file that another process has
#: locked, before its pending output is counted as lost.
HALT_FLUSH_SECONDS = 10.0


def _flush_output_at_halt() -> ErrInfo | None:
    """Write out what the run's files are still waiting for; the loss, if any, as an error."""
    from execsql.utils.fileio import filewriter_close_all_after_write

    try:
        filewriter_close_all_after_write(max_wait=HALT_FLUSH_SECONDS)
    except ErrInfo as lost:
        # The loss belongs to no particular statement.
        lost.script_file = ""
        return lost
    except Exception:
        pass  # A failed flush must not hide the error that halted the run.
    return None


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
    # A halt inside BEGIN BATCH rolls the batch back: after the error is
    # shown, in case a lost connection makes the rollback wait, and before
    # the ON ERROR_HALT / ON CANCEL_HALT script, whose own SQL then commits.
    if _state.status is not None:
        _state.status.batch.abandon_all()
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
    # After the ON ERROR_HALT / ON CANCEL_HALT actions, which may write files
    # themselves; before the writer is stopped, which discards what waits.
    lost_output = _flush_output_at_halt()
    if lost_output is not None:
        _state.halt_output_error = lost_output
        lost_output.write()
        exit_status = exit_status or 1
    if exit_status > 0 and _state.exec_log:
        if logmsg:
            _state.exec_log.log_exit_error(logmsg)
        elif errinfo is not None:
            _state.exec_log.log_exit_error(logged_error(errinfo))
        if lost_output is not None:
            _state.exec_log.log_status_error(lost_output.errmsg())
    if _state.exec_log is not None:
        _state.exec_log.log_status_info(f"{_state.cmds_run} commands run")
        _state.exec_log.log_exit()
        _state.exec_log.close()
    from execsql.utils.fileio import filewriter_end

    filewriter_end()
    # Last, so the ON ERROR_HALT / ON CANCEL_HALT actions above are in it.
    from execsql import manifest as _manifest

    if (manifest := _manifest.current()) is not None:
        if lost_output is not None:
            manifest.add_error(lost_output)
        manifest.finish(exit_status, errinfo)
    raise ScriptExit(exit_status)


def fatal_error(error_msg: str | None = None) -> None:
    exit_now(1, ErrInfo("error", other_msg=error_msg))


def write_warning(warning_msg: str, *, always: bool = False) -> None:
    """Write a non-fatal warning message to the log and optionally to stderr.

    Args:
        warning_msg: The warning text to emit.
        always: When ``True``, always write to stderr regardless of the
            ``conf.write_warnings`` setting.  Use this for structural warnings
            (e.g. IF-level mismatch) that should always be visible.  When
            ``False`` (default), stderr output is gated by
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
