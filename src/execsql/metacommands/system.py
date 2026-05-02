from __future__ import annotations

"""
System and shell metacommand handlers for execsql.

Implements ``x_shell`` (SHELL — execute an OS command via ``subprocess``)
and related system-interaction metacommands that allow SQL scripts to
invoke external programs, set environment variables, or query the OS.
"""

import os
import shlex
import subprocess
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.exporters.base import WriteSpec
from execsql.script import ScriptExecSpec, current_script_line
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close_all_after_write
from execsql.utils.gui import (
    gui_console_height,
    gui_console_hide,
    gui_console_off,
    gui_console_on,
    gui_console_progress,
    gui_console_save,
    gui_console_show,
    gui_console_status,
    gui_console_wait_user,
    gui_console_width,
)
from execsql.utils.mail import MailSpec, Mailer


def x_system_cmd(**kwargs: Any) -> None:
    if not _state.conf.allow_system_cmd:
        raise ErrInfo(
            type="cmd",
            command_text=kwargs.get("metacommandline", "SYSTEM_CMD"),
            other_msg="SYSTEM_CMD is disabled (--no-system-cmd flag is active).",
        )
    syscmd = kwargs["command"]
    cont = kwargs["continue"]
    script, lno = current_script_line()
    _state.exec_log.log_user_msg(f"System command on line {lno} of script {script}: {syscmd}")
    filewriter_close_all_after_write()
    cmdlist = shlex.split(syscmd, posix=(os.name == "posix"))
    if cont is None:
        result = subprocess.run(cmdlist)
        _state.subvars.add_substitution("$SYSTEM_CMD_EXIT_STATUS", str(result.returncode))
    else:
        proc = subprocess.Popen(cmdlist)
        _state.subvars.add_substitution("$SYSTEM_CMD_PID", str(proc.pid))
    return None


def x_email(**kwargs: Any) -> None:
    from_addr = kwargs["from"]
    to_addr = kwargs["to"]
    subject = kwargs["subject"]
    msg = kwargs["msg"]
    msg_file = kwargs["msg_file"]
    att_file = kwargs["att_file"]
    with Mailer() as m:
        m.sendmail(from_addr, to_addr, subject, msg, msg_file, att_file)


def x_timer(**kwargs: Any) -> None:
    onoff = kwargs["onoff"].lower()
    if onoff == "on":
        _state.timer.start()
    else:
        _state.timer.stop()


def x_log(**kwargs: Any) -> None:
    message = kwargs["message"]
    _state.exec_log.log_user_msg(message)


def x_logwritemessages(**kwargs: Any) -> None:
    setting = kwargs["setting"].lower()
    _state.conf.tee_write_log = setting in ("yes", "on", "true", "1")


def x_log_datavars(**kwargs: Any) -> None:
    setting = kwargs["setting"].lower()
    _state.conf.log_datavars = setting in ("yes", "on", "true", "1")


def x_log_sql(**kwargs: Any) -> None:
    setting = kwargs["setting"].lower()
    _state.conf.log_sql = setting in ("yes", "on", "true", "1")


def x_console(**kwargs: Any) -> None:
    onoff = kwargs["onoff"].lower()
    if onoff == "on":
        gui_console_on()
    else:
        gui_console_off()


def x_consoleprogress(**kwargs: Any) -> None:
    num = float(kwargs["num"])
    total = kwargs["total"]
    if total:
        num = 100 * num / float(total)
    gui_console_progress(num)


def x_consolewait(**kwargs: Any) -> None:
    message = kwargs["message"]
    gui_console_wait_user(message)


def x_consolewait_onerror(**kwargs: Any) -> None:
    flag = kwargs["onoff"].lower()
    _state.conf.gui_wait_on_error_halt = flag in ("on", "yes", "true", "1")


def x_consolewait_whendone(**kwargs: Any) -> None:
    flag = kwargs["onoff"].lower()
    _state.conf.gui_wait_on_exit = flag in ("on", "yes", "true", "1")


def x_console_hideshow(**kwargs: Any) -> None:
    hideshow = kwargs["hideshow"].lower()
    if hideshow == "hide":
        gui_console_hide()
    else:
        gui_console_show()


def x_consolewidth(**kwargs: Any) -> None:
    width = kwargs["width"]
    _state.conf.gui_console_width = int(width)
    gui_console_width(width)


def x_consoleheight(**kwargs: Any) -> None:
    height = kwargs["height"]
    _state.conf.gui_console_height = int(height)
    gui_console_height(height)


def x_consolestatus(**kwargs: Any) -> None:
    message = kwargs["message"]
    gui_console_status(message)


def x_consolesave(**kwargs: Any) -> None:
    fn = kwargs["filename"]
    ap = kwargs["append"]
    append = ap is not None
    gui_console_save(fn, append)


def x_cancel_halt(**kwargs: Any) -> None:
    flag = kwargs["onoff"].lower()
    if flag not in ("on", "off", "yes", "no", "true", "false"):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized flag for handling GUI cancellations: {flag}",
        )
    _state.status.cancel_halt = flag in ("on", "yes", "true")
    return None


def x_cancel_halt_write_clear(**kwargs: Any) -> None:
    _state.cancel_halt_writespec = None


def x_cancel_halt_write(**kwargs: Any) -> None:
    msg = f"{kwargs['text']}\n"
    tee = kwargs["tee"]
    tee = bool(tee)
    outf = kwargs["filename"]
    _state.cancel_halt_writespec = WriteSpec(message=msg, dest=outf, tee=tee)


def x_cancel_halt_email_clear(**kwargs: Any) -> None:
    _state.cancel_halt_mailspec = None


def x_cancel_halt_email(**kwargs: Any) -> None:
    from_addr = kwargs["from"]
    to_addr = kwargs["to"]
    subject = kwargs["subject"]
    msg = kwargs["msg"]
    msg_file = kwargs["msg_file"]
    att_file = kwargs["att_file"]
    _state.cancel_halt_mailspec = MailSpec(from_addr, to_addr, subject, msg, msg_file, att_file)


def x_cancel_halt_exec(**kwargs: Any) -> None:
    _state.cancel_halt_exec = ScriptExecSpec(**kwargs)


def x_cancel_halt_exec_clear(**kwargs: Any) -> None:
    _state.cancel_halt_exec = None


def x_error_halt_write_clear(**kwargs: Any) -> None:
    _state.err_halt_writespec = None


def x_error_halt_write(**kwargs: Any) -> None:
    msg = f"{kwargs['text']}\n"
    tee = kwargs["tee"]
    tee = bool(tee)
    outf = kwargs["filename"]
    _state.err_halt_writespec = WriteSpec(message=msg, dest=outf, tee=tee)


def x_error_halt_email_clear(**kwargs: Any) -> None:
    _state.err_halt_email = None


def x_error_halt_email(**kwargs: Any) -> None:
    from_addr = kwargs["from"]
    to_addr = kwargs["to"]
    subject = kwargs["subject"]
    msg = kwargs["msg"]
    msg_file = kwargs["msg_file"]
    att_file = kwargs["att_file"]
    _state.err_halt_email = MailSpec(from_addr, to_addr, subject, msg, msg_file, att_file)


def x_error_halt_exec(**kwargs: Any) -> None:
    _state.err_halt_exec = ScriptExecSpec(**kwargs)


def x_error_halt_exec_clear(**kwargs: Any) -> None:
    _state.err_halt_exec = None


def x_write_warnings(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.write_warnings = flag in ("yes", "on", "true", "1")
    return None


def x_gui_level(**kwargs: Any) -> None:
    _state.conf.gui_level = int(kwargs["level"])


def x_execute(**kwargs: Any) -> None:
    """Run a database function, view, or action query. Returns None."""
    sql = kwargs["queryname"]
    db = _state.dbs.current()
    try:
        db.exec_cmd(sql)
        db.commit()
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", command_text=sql, exception_msg=exception_desc()) from e
    return None
