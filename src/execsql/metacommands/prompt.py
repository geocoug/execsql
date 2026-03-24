from __future__ import annotations
from execsql.exceptions import ErrInfo

"""
Interactive user prompt metacommand handlers for execsql.

Implements all ``x_*`` handler functions that display GUI dialogs or
console prompts to the user:

- ``x_prompt_action`` — ACTION prompt (choose from a list of actions)
- ``x_prompt_message`` — MESSAGE dialog
- ``x_prompt_display`` — DISPLAY (show a query result)
- ``x_prompt_entry`` — ENTRY FORM (fill in substitution variables)
- ``x_prompt_compare`` — COMPARE dialog
- ``x_prompt_selectrows`` — SELECT ROWS dialog
- ``x_prompt_map`` — MAP display
- ``x_open_file`` — OPEN FILE browser
- ``x_save_file`` — SAVE FILE browser
- ``x_get_directory`` — GET DIRECTORY browser
- ``x_credentials`` — CREDENTIALS dialog
- ``x_gui_console`` — GUI console on/off control
"""

import os
import queue as _queue
from typing import Any

import execsql.state as _state
from execsql.script import current_script_line
from execsql.utils.errors import exception_desc, exit_now
from execsql.utils.fileio import EncodedFile, check_dir
from execsql.utils.gui import (
    ActionSpec,
    EntrySpec,
    GUI_ACTION,
    GUI_COMPARE,
    GUI_DIRECTORY,
    GUI_DISPLAY,
    GUI_ENTRY,
    GUI_HALT,
    GUI_MAP,
    GUI_MSG,
    GUI_OPENFILE,
    GUI_PAUSE,
    GUI_SAVEFILE,
    GUI_SELECTROWS,
    GuiSpec,
    QUERY_CONSOLE,
    enable_gui,
    get_yn,
    get_yn_win,
    gui_connect,
    gui_credentials,
    pause,
    pause_win,
)
from execsql.utils.strings import unquoted


def x_prompt(**kwargs: Any) -> None:
    db = _state.dbs.current()
    schema = kwargs["schema"]
    table = kwargs["table"]
    message = kwargs["message"]
    help_url = unquoted(kwargs["help"])
    free = kwargs["free"] is not None
    sq_name = db.schema_qualified_table_name(schema, table)
    script, line_no = current_script_line()
    cmd = f"select * from {sq_name};"
    colnames, rows = db.select_data(cmd)
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": table,
        "message": message,
        "button_list": [("Continue", 1, "<Return>")],
        "column_headers": colnames,
        "rowset": rows,
        "help_url": help_url,
        "free": free,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_DISPLAY, gui_args, return_queue))
    if not free:
        user_response = return_queue.get(block=True)
        btn = user_response["button"]
        if not btn and _state.status.cancel_halt:
            msg = f"Halted from display of {sq_name}"
            _state.exec_log.log_exit_halt(script, line_no, msg)
            exit_now(2, None)
    return None


def x_prompt_enter(**kwargs: Any) -> None:
    sub_var = kwargs["match_str"]
    message = kwargs["message"]
    texttype = kwargs["type"]
    textcase = kwargs["case"]
    as_pw = kwargs["password"] is not None
    schema = kwargs["schema"]
    table = kwargs["table"]
    initial = kwargs["initial"]
    help_url = unquoted(kwargs["help"])
    if table is not None:
        db = _state.dbs.current()
        cmd = f"select * from {db.schema_qualified_table_name(schema, table)};"
        hdrs, rows = db.select_data(cmd)
    else:
        hdrs, rows = None, None
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": "Enter a value",
        "message": message,
        "button_list": [("OK", 1, "<Return>")],
        "column_headers": hdrs,
        "rowset": rows,
        "textentry": True,
        "hidetext": as_pw,
        "textentrytype": texttype,
        "textentrycase": textcase,
        "initialtext": initial,
        "help_url": help_url,
        "free": False,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_DISPLAY, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btnval = user_response["button"]
    txtval = user_response["return_value"]
    if btnval is None:
        if _state.status.cancel_halt:
            _state.exec_log.log_exit_halt(*current_script_line(), msg="Quit from prompt to enter a SUB value.")
            exit_now(2, None)
    else:
        subvarset = _state.subvars if sub_var[0] != "~" else _state.commandliststack[-1].localvars
        subvarset.add_substitution(sub_var, txtval)
        script_name, lno = current_script_line()
        if as_pw:
            _state.exec_log.log_status_info(f"Password assigned to variable {{{sub_var}}} on line {lno}.")
        else:
            _state.exec_log.log_status_info(f"Variable {{{sub_var}}} set to {{{txtval}}} on line {lno}.")
    return None


def x_prompt_entryform(**kwargs: Any) -> None:
    import re as _re

    spec_schema = kwargs["schema"]
    spec_table = kwargs["table"]
    display_schema = kwargs["schemadisp"]
    display_table = kwargs["tabledisp"]
    message = kwargs["message"]
    help_url = unquoted(kwargs["help"])
    tbl1 = _state.dbs.current().schema_qualified_table_name(spec_schema, spec_table)
    try:
        if not _state.dbs.current().table_exists(spec_table, spec_schema):
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg=f"Table {spec_table} does not exist",
            )
    except Exception:
        pass
    curs = _state.dbs.current().cursor()
    cmd = f"select * from {tbl1};"
    curs.execute(cmd)
    colhdrs = [d[0].lower() for d in curs.description]
    if "sequence" in colhdrs:
        cmd = f"select * from {tbl1} order by sequence;"
        curs.execute(cmd)
    if not ("sub_var" in colhdrs and "prompt" in colhdrs):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="The variable name and prompt are required, but missing.",
        )
    spec_rows = curs.fetchall()
    entry_list = []
    subvar_rx = _re.compile(r"^~?\w+$", _re.I)
    for r in spec_rows:
        lookups = None
        entry_width = None
        entry_height = None
        entry_col = None
        v = dict(zip(colhdrs, r))
        subvar = v.get("sub_var")
        if not subvar:
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg="A substitution variable name must be provided for all of the entry specifications.",
            )
        if not subvar_rx.match(subvar):
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg=f"Invalid substitution variable name: {subvar}",
            )
        prompt_msg = v.get("prompt")
        if not prompt_msg:
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg="A prompt must be provided for all of the entry specifications.",
            )
        initial_value = None
        if "initial_value" in colhdrs and v["initial_value"] is not None:
            try:
                if "entry_type" in colhdrs and v["entry_type"] is not None and v["entry_type"].lower() == "checkbox":
                    initial_value = str(str(v["initial_value"]).lower() in ("yes", "true", "on", "1"))
                else:
                    initial_value = str(v["initial_value"])
            except Exception:
                raise ErrInfo(
                    type="cmd",
                    command_text=kwargs["metacommandline"],
                    other_msg=f"The initial value of {v['initial_value']} can't be used.",
                )
        if "lookup_table" in colhdrs:
            lt = v["lookup_table"]
            if lt:
                curs.execute(f"select * from {lt};")
                lookups = [lookup_row[0] for lookup_row in curs.fetchall()]
        if "width" in colhdrs:
            entry_width = v.get("width")
            if entry_width:
                try:
                    entry_width = int(entry_width)
                except Exception:
                    raise ErrInfo(
                        type="cmd",
                        command_text=kwargs["metacommandline"],
                        other_msg=f"Entry width {entry_width} is not an integer",
                    )
        if "height" in colhdrs:
            entry_height = v.get("height")
            if entry_height:
                try:
                    entry_height = int(entry_height)
                except Exception:
                    raise ErrInfo(
                        type="cmd",
                        command_text=kwargs["metacommandline"],
                        other_msg=f"Entry height {entry_height} is not an integer",
                    )
                if entry_height < 1:
                    entry_height = 1
        if "form_column" in colhdrs:
            entry_col = v.get("form_column")
            if entry_col:
                try:
                    entry_col = int(entry_col)
                except Exception:
                    raise ErrInfo(
                        type="cmd",
                        command_text=kwargs["metacommandline"],
                        other_msg=f"Entry column {entry_col} is not an integer",
                    )
                if entry_col < 1:
                    entry_col = 1
        subvarset = _state.subvars if subvar[0] != "~" else _state.commandliststack[-1].localvars
        subvarset.remove_substitution(subvar)
        entry_list.append(
            EntrySpec(
                subvar,
                prompt_msg,
                required=bool(v.get("required")),
                initial_value=initial_value,
                default_width=entry_width,
                default_height=entry_height,
                lookup_list=lookups,
                form_column=entry_col,
                validation_regex=v.get("validation_regex"),
                validation_key_regex=v.get("validation_key_regex"),
                entry_type=v.get("entry_type"),
            ),
        )
    colnames, rows = None, None
    if display_table:
        db = _state.dbs.current()
        sq_name = db.schema_qualified_table_name(display_schema, display_table)
        colnames, rows = db.select_data(f"select * from {sq_name};")
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": "Entry",
        "message": message,
        "entry_specs": entry_list,
        "column_headers": colnames,
        "rowset": rows,
        "help_url": help_url,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_ENTRY, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btn = user_response["button"]
    entries = user_response["return_value"]
    script, line_no = current_script_line()
    if btn:
        for e in entries:
            if e.value:
                value = str(e.value)
                subvarset = _state.subvars if subvar[0] != "~" else _state.commandliststack[-1].localvars
                subvarset.add_substitution(e.name, value)
                _state.exec_log.log_status_info(
                    f"Substitution variable {e.name} set to {{{value}}} on line {line_no} of {script}",
                )
            else:
                if _state.subvars.sub_exists(e.name):
                    _state.exec_log.log_status_info(
                        f"Substitution variable {e.name} removed on line {line_no} of {script}",
                    )
    else:
        if _state.status.cancel_halt:
            msg = f"Halted from entry form {tbl1}"
            _state.exec_log.log_exit_halt(script, line_no, msg)
            exit_now(2, None)


def x_prompt_pause(**kwargs: Any) -> None:
    quitmsg = "Quit from PROMPT PAUSE metacommand"
    text = kwargs["text"]
    action = kwargs["action"]
    if action:
        action = action.lower()
    countdown = kwargs["countdown"]
    timeunit = kwargs["timeunit"]
    msg = text
    if countdown:
        countdown = float(countdown)
        msg = f"{msg}\nProcess will {action} after {countdown} {timeunit} without a response."
    maxtime_secs = countdown
    if timeunit and timeunit.lower() == "minutes":
        maxtime_secs = maxtime_secs * 60
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": f"Script {current_script_line()[0]}",
        "message": msg,
        "countdown": maxtime_secs,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_PAUSE, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    quit = user_response["quit"]
    return_queue.task_done()
    if quit and _state.status.cancel_halt:
        _state.exec_log.log_exit_halt(*current_script_line(), msg=quitmsg)
        exit_now(2, None)
    return None


def prompt_compare(button_list: list, **kwargs: Any) -> Any:
    schema1 = kwargs["schema1"]
    table1 = kwargs["table1"]
    alias1 = kwargs["alias1"]
    orient = kwargs["orient"]
    schema2 = kwargs["schema2"]
    table2 = kwargs["table2"]
    alias2 = kwargs["alias2"]
    pks = kwargs["pks"]
    msg = kwargs["msg"]
    help_url = unquoted(kwargs["help"])
    badaliasmsg = "Alias %s is not recognized."
    if alias1 is not None:
        try:
            db1 = _state.dbs.aliased_as(alias1)
        except Exception:
            raise ErrInfo(type="error", other_msg=badaliasmsg % alias1)
    else:
        db1 = _state.dbs.current()
    if alias2 is not None:
        try:
            db2 = _state.dbs.aliased_as(alias2)
        except Exception:
            raise ErrInfo(type="error", other_msg=badaliasmsg % alias2)
    else:
        db2 = _state.dbs.current()
    sq_name1 = db1.schema_qualified_table_name(schema1, table1)
    sq_name2 = db2.schema_qualified_table_name(schema2, table2)
    sql1 = f"select * from {sq_name1};"
    sql2 = f"select * from {sq_name2};"
    hdrs1, rows1 = db1.select_data(sql1)
    if len(rows1) == 0:
        raise ErrInfo("error", other_msg=f"There are no data in {sq_name1}.")
    hdrs2, rows2 = db2.select_data(sql2)
    if len(rows2) == 0:
        raise ErrInfo("error", other_msg=f"There are no data in {sq_name2}.")
    pklist = [pk.replace('"', "").replace(" ", "") for pk in pks.split(",")]
    sidebyside = orient.lower() == "beside"
    if not all(col in hdrs1 for col in pklist) or not all(col in hdrs2 for col in pklist):
        script, line_no = current_script_line()
        raise ErrInfo(
            type="error",
            other_msg=f"Specified primary key columns do not exist in PROMPT COMPARE metacommand on line {line_no} of {script}.",
        )
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": "Compare data",
        "message": msg,
        "button_list": button_list,
        "headers1": hdrs1,
        "rows1": rows1,
        "headers2": hdrs2,
        "rows2": rows2,
        "keylist": pklist,
        "sidebyside": sidebyside,
        "help_url": help_url,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_COMPARE, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btn = user_response["button"]
    if btn is None and _state.status.cancel_halt:
        script, line_no = current_script_line()
        msg = f"Halted from comparison of {sq_name1} and {sq_name2}"
        _state.exec_log.log_exit_halt(script, line_no, msg)
        exit_now(2, None)
    return btn


def x_prompt_compare(**kwargs: Any) -> None:
    prompt_compare([("Continue", 1, "<Return>")], **kwargs)


def x_prompt_ask_compare(**kwargs: Any) -> None:
    subvar = kwargs["match"]
    script, lno = current_script_line()
    btn = prompt_compare([("Yes", 1, "y"), ("No", 0, "n")], **kwargs)
    if btn is None:
        if _state.status.cancel_halt:
            _state.exec_log.log_exit_halt(script, lno, msg="Quit from PROMPT ASK COMPARE metacommand")
            exit_now(2, None)
    else:
        respstr = "Yes" if btn == 1 else "No"
        subvarset = _state.subvars if subvar[0] != "~" else _state.commandliststack[-1].localvars
        subvarset.add_substitution(subvar, respstr)
        _state.exec_log.log_status_info(f"Question {{{kwargs['msg']}}} on line {lno} answered {respstr}")


def x_prompt_ask(**kwargs: Any) -> None:
    quitmsg = "Quit from PROMPT ASK metacommand"
    subvar = kwargs["match"]
    schema = kwargs["schema"]
    table = kwargs["table"]
    help_url = unquoted(kwargs["help"])
    script, lno = current_script_line()
    if table is not None:
        queryname = _state.dbs.current().schema_qualified_table_name(schema, table)
        cmd = f"select * from {queryname};"
        colnames, rows = _state.dbs.current().select_data(cmd)
    else:
        colnames, rows = None, None
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": script,
        "message": kwargs["question"],
        "button_list": [("Yes", 1, "y"), ("No", 0, "n")],
        "column_headers": colnames,
        "rowset": rows,
        "help_url": help_url,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_DISPLAY, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btn = user_response["button"]
    if btn is None:
        if _state.status.cancel_halt:
            _state.exec_log.log_exit_halt(script, lno, msg=quitmsg)
            exit_now(2, None)
    else:
        respstr = "Yes" if btn == 1 else "No"
        subvarset = _state.subvars if subvar[0] != "~" else _state.commandliststack[-1].localvars
        subvarset.add_substitution(subvar, respstr)
        _state.exec_log.log_status_info(
            f"Question {{{kwargs['question']}}} answered {respstr} on line {lno} of script {script}",
        )
    return None


def x_prompt_map(**kwargs: Any) -> None:
    db = _state.dbs.current()
    schema = kwargs["schema"]
    table = kwargs["table"]
    message = kwargs["message"]
    lat_col = kwargs["lat_col"]
    lon_col = kwargs["lon_col"]
    label_col = kwargs["label_col"]
    symbol_col = kwargs["symbol_col"]
    color_col = kwargs["color_col"]
    sq_name = db.schema_qualified_table_name(schema, table)
    script, line_no = current_script_line()
    cmd = f"select * from {sq_name};"
    colnames, rows = db.select_data(cmd)
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": table,
        "message": message,
        "button_list": [("Continue", 1, "<Return>")],
        "headers": colnames,
        "rows": rows,
        "lat_col": lat_col,
        "lon_col": lon_col,
        "label_col": label_col,
        "symbol_col": symbol_col,
        "color_col": color_col,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_MAP, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btn = user_response["button"]
    if not btn and _state.status.cancel_halt:
        msg = f"Halted from map of {sq_name}"
        _state.exec_log.log_exit_halt(script, line_no, msg)
        exit_now(2, None)
    return None


def x_prompt_action(**kwargs: Any) -> None:
    spec_schema = kwargs["schema"]
    spec_table = kwargs["table"]
    display_schema = kwargs["schemadisp"]
    display_table = kwargs["tabledisp"]
    message = kwargs["message"]
    compact = kwargs["compact"]
    help_url = unquoted(kwargs["help"])
    if compact is not None:
        compact = int(compact)
    do_continue = kwargs["continue"]
    if do_continue is not None:
        do_continue = bool(do_continue)
    tbl1 = _state.dbs.current().schema_qualified_table_name(spec_schema, spec_table)
    try:
        if not _state.dbs.current().table_exists(spec_table, spec_schema):
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg=f"Table {spec_table} does not exist",
            )
    except Exception:
        pass
    curs = _state.dbs.current().cursor()
    cmd = f"select * from {tbl1};"
    curs.execute(cmd)
    colhdrs = [d[0].lower() for d in curs.description]
    if "sequence" in colhdrs:
        cmd = f"select * from {tbl1} order by sequence;"
        curs.execute(cmd)
    if not ("label" in colhdrs and "prompt" in colhdrs and "script" in colhdrs):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="The columns 'label', 'prompt', and 'script' are required, but one or more is missing.",
        )
    spec_rows = curs.fetchall()
    action_list = []
    for r in spec_rows:
        v = dict(zip(colhdrs, r))
        button_label = v.get("label")
        if not button_label:
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg="A button label must be provided for all of the action specifications.",
            )
        prompt_msg = v.get("prompt")
        if not prompt_msg:
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg="A prompt must be provided for all of the action specifications.",
            )
        action_list.append(
            ActionSpec(
                button_label,
                prompt_msg,
                v["script"],
                data_required=bool(v.get("data_required")),
            ),
        )
    colnames, rows = None, None
    if display_table:
        db = _state.dbs.current()
        sq_name = db.schema_qualified_table_name(display_schema, display_table)
        colnames, rows = db.select_data(f"select * from {sq_name};")
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": "Actions",
        "message": message,
        "button_specs": action_list,
        "include_continue_button": do_continue,
        "compact": compact,
        "help_url": help_url,
        "column_headers": colnames,
        "rowset": rows,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_ACTION, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btn = user_response["button"]
    script, line_no = current_script_line()
    if not btn and _state.status.cancel_halt:
        msg = f"Halted from entry form {tbl1}"
        _state.exec_log.log_exit_halt(script, line_no, msg)
        exit_now(2, None)


def x_prompt_savefile(**kwargs: Any) -> None:
    sub_name = kwargs["match"]
    sub_name2 = kwargs["fn_match"]
    sub_name3 = kwargs["path_match"]
    sub_name4 = kwargs["ext_match"]
    sub_name5 = kwargs["fnbase_match"]
    startdir = kwargs["startdir"]
    try:
        subvarset = _state.subvars if sub_name[0] != "~" else _state.commandliststack[-1].localvars
        subvarset.remove_substitution(sub_name)
        script, lno = current_script_line()
        working_dir = startdir if startdir is not None else os.path.dirname(os.path.abspath(script))
        enable_gui()
        return_queue = _queue.Queue()
        gui_args = {"working_dir": working_dir, "script": script}
        _state.gui_manager_queue.put(GuiSpec(GUI_SAVEFILE, gui_args, return_queue))
        user_response = return_queue.get(block=True)
        fn = user_response["filename"]
        if not fn:
            if _state.status.cancel_halt:
                msg = "Halted from prompt for name of file to save"
                _state.exec_log.log_exit_halt(script, lno, msg)
                exit_now(2, None)
        else:
            if os.name != "posix":
                fn = fn.replace("/", "\\")
            subvarset.add_substitution(sub_name, fn)
            _state.exec_log.log_status_info(
                f"Substitution variable {sub_name} set to path and filename {fn} at line {lno} of {script}",
            )
            if sub_name2 is not None:
                subvarset2 = _state.subvars if sub_name2[0] != "~" else _state.commandliststack[-1].localvars
                subvarset2.remove_substitution(sub_name2)
                basefn = os.path.basename(fn)
                subvarset2.add_substitution(sub_name2, basefn)
                _state.exec_log.log_status_info(
                    f"Substitution variable {sub_name2} set to filename {basefn} at line {lno} of {script}",
                )
            if sub_name3 is not None:
                subvarset3 = _state.subvars if sub_name3[0] != "~" else _state.commandliststack[-1].localvars
                subvarset3.remove_substitution(sub_name3)
                dirname = os.path.dirname(fn)
                if os.name != "posix":
                    dirname = dirname.replace("/", "\\")
                subvarset3.add_substitution(sub_name3, dirname)
                _state.exec_log.log_status_info(
                    f"Substitution variable {sub_name3} set to path {dirname} at line {lno} of {script}",
                )
            if sub_name4 is not None:
                subvarset4 = _state.subvars if sub_name4[0] != "~" else _state.commandliststack[-1].localvars
                subvarset4.remove_substitution(sub_name4)
                root, ext = os.path.splitext(fn)
                if ext is None:
                    subvarset4.add_substitution(sub_name4, "")
                else:
                    ext = ext[1:]
                    subvarset4.add_substitution(sub_name4, ext)
            if sub_name5 is not None:
                subvarset5 = _state.subvars if sub_name5[0] != "~" else _state.commandliststack[-1].localvars
                subvarset5.remove_substitution(sub_name5)
                basefn = os.path.basename(fn)
                root, ext = os.path.splitext(basefn)
                subvarset5.add_substitution(sub_name5, root)
    except (ErrInfo, SystemExit):
        raise
    except Exception:
        raise ErrInfo(type="exception", exception_msg=exception_desc())
    return None


def x_prompt_openfile(**kwargs: Any) -> None:
    sub_name = kwargs["match"]
    sub_name2 = kwargs["fn_match"]
    sub_name3 = kwargs["path_match"]
    sub_name4 = kwargs["ext_match"]
    sub_name5 = kwargs["fnbase_match"]
    startdir = kwargs["startdir"]
    if sub_name2 is not None and sub_name2 == sub_name:
        raise ErrInfo(
            type="error",
            other_msg="Different values can't be assigned to the same substitution variable.",
        )
    try:
        subvarset = _state.subvars if sub_name[0] != "~" else _state.commandliststack[-1].localvars
        subvarset.remove_substitution(sub_name)
        script, lno = current_script_line()
        working_dir = startdir if startdir is not None else os.path.dirname(os.path.abspath(script))
        enable_gui()
        return_queue = _queue.Queue()
        gui_args = {"working_dir": working_dir, "script": script}
        _state.gui_manager_queue.put(GuiSpec(GUI_OPENFILE, gui_args, return_queue))
        user_response = return_queue.get(block=True)
        fn = user_response["filename"]
        if not fn:
            if _state.status.cancel_halt:
                msg = "Halted from prompt for name of file to open"
                _state.exec_log.log_exit_halt(script, lno, msg)
                exit_now(2, None)
        else:
            if os.name != "posix":
                fn = fn.replace("/", "\\")
            subvarset.add_substitution(sub_name, fn)
            _state.exec_log.log_status_info(
                f"Substitution variable {sub_name} set to path and filename {fn} at line {lno} of {script}",
            )
            if sub_name2 is not None:
                subvarset2 = _state.subvars if sub_name2[0] != "~" else _state.commandliststack[-1].localvars
                subvarset2.remove_substitution(sub_name2)
                basefn = os.path.basename(fn)
                subvarset2.add_substitution(sub_name2, basefn)
            if sub_name3 is not None:
                subvarset3 = _state.subvars if sub_name3[0] != "~" else _state.commandliststack[-1].localvars
                subvarset3.remove_substitution(sub_name3)
                dirname = os.path.dirname(fn)
                if os.name != "posix":
                    dirname = dirname.replace("/", "\\")
                subvarset3.add_substitution(sub_name3, dirname)
            if sub_name4 is not None:
                subvarset4 = _state.subvars if sub_name4[0] != "~" else _state.commandliststack[-1].localvars
                subvarset4.remove_substitution(sub_name4)
                root, ext = os.path.splitext(fn)
                if ext is None:
                    subvarset4.add_substitution(sub_name4, "")
                else:
                    ext = ext[1:]
                    subvarset4.add_substitution(sub_name4, ext)
            if sub_name5 is not None:
                subvarset5 = _state.subvars if sub_name5[0] != "~" else _state.commandliststack[-1].localvars
                subvarset5.remove_substitution(sub_name5)
                basefn = os.path.basename(fn)
                root, ext = os.path.splitext(basefn)
                subvarset5.add_substitution(sub_name5, root)
    except (ErrInfo, SystemExit):
        raise
    except Exception:
        raise ErrInfo(type="exception", exception_msg=exception_desc())
    return None


def x_prompt_directory(**kwargs: Any) -> None:
    sub_name = kwargs["match"]
    fullpath = kwargs["fullpath"]
    startdir = kwargs["startdir"]
    try:
        subvarset = _state.subvars if sub_name[0] != "~" else _state.commandliststack[-1].localvars
        subvarset.remove_substitution(sub_name)
        script, lno = current_script_line()
        working_dir = startdir if startdir is not None else os.path.dirname(os.path.abspath(script))
        enable_gui()
        return_queue = _queue.Queue()
        gui_args = {"working_dir": working_dir, "script": script}
        _state.gui_manager_queue.put(GuiSpec(GUI_DIRECTORY, gui_args, return_queue))
        user_response = return_queue.get(block=True)
        dirname = user_response["directory"]
        if not dirname:
            if _state.status.cancel_halt:
                msg = "Halted from prompt for name of directory"
                _state.exec_log.log_exit_halt(script, lno, msg)
                exit_now(2, None)
        else:
            if fullpath is not None:
                dirname = os.path.abspath(dirname)
            if os.name != "posix":
                dirname = dirname.replace("/", "\\")
            subvarset.add_substitution(sub_name, dirname)
            _state.exec_log.log_status_info(
                f"Substitution string {sub_name} set to directory {dirname} at line {lno} of {script}",
            )
    except (ErrInfo, SystemExit):
        raise
    except Exception:
        raise ErrInfo(type="exception", exception_msg=exception_desc())
    return None


def prompt_select_rows(button_list: list, **kwargs: Any) -> Any:
    schema1 = kwargs["schema1"]
    table1 = kwargs["table1"]
    alias1 = kwargs["alias1"]
    schema2 = kwargs["schema2"]
    table2 = kwargs["table2"]
    alias2 = kwargs["alias2"]
    msg = kwargs["msg"]
    help_url = unquoted(kwargs["help"])
    badaliasmsg = "Alias %s is not recognized."
    if alias1 is not None:
        try:
            db1 = _state.dbs.aliased_as(alias1)
        except Exception:
            raise ErrInfo(type="error", other_msg=badaliasmsg % alias1)
    else:
        db1 = _state.dbs.current()
    if alias2 is not None:
        try:
            db2 = _state.dbs.aliased_as(alias2)
        except Exception:
            raise ErrInfo(type="error", other_msg=badaliasmsg % alias2)
    else:
        db2 = _state.dbs.current()
    sq_name1 = db1.schema_qualified_table_name(schema1, table1)
    sq_name2 = db2.schema_qualified_table_name(schema2, table2)
    sql1 = f"select * from {sq_name1};"
    sql2 = f"select * from {sq_name2};"
    hdrs1, rows1 = db1.select_data(sql1)
    if len(rows1) == 0:
        raise ErrInfo("error", other_msg=f"There are no data in {sq_name1}.")
    hdrs2, rows2 = db2.select_data(sql2)
    missing_hdrs = [hdr for hdr in hdrs1 if hdr not in hdrs2]
    if len(missing_hdrs) > 0:
        raise ErrInfo("error", other_msg=f"Columns [{', '.join(missing_hdrs)}] are missing from {sq_name2}.")
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": "Select rows",
        "message": msg,
        "button_list": button_list,
        "headers1": hdrs1,
        "rows1": rows1,
        "headers2": hdrs2,
        "rows2": rows2,
        "alias2": alias2,
        "table2": sq_name2,
        "help_url": help_url,
    }
    _state.gui_manager_queue.put(GuiSpec(GUI_SELECTROWS, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btn = user_response["button"]
    if btn is None and _state.status.cancel_halt:
        script, line_no = current_script_line()
        msg = f"Halted from selection of rows from {sq_name1} into {sq_name2}"
        _state.exec_log.log_exit_halt(script, line_no, msg)
        exit_now(2, None)
    return btn


def x_prompt_select_rows(**kwargs: Any) -> None:
    prompt_select_rows([("Continue", 1, "<Return>")], **kwargs)


def x_prompt_credentials(**kwargs: Any) -> None:
    message = kwargs["message"]
    user = kwargs["user"]
    pw = kwargs["pw"]
    gui_credentials(message, username=user, pwtext=pw, cmd=kwargs["metacommandline"])
    return None


def x_prompt_connect(**kwargs: Any) -> None:
    alias = kwargs["alias"]
    message = kwargs["message"]
    help_url = unquoted(kwargs["help"])
    gui_connect(alias, message, help_url=help_url, cmd=kwargs["metacommandline"])
    return None


def x_ask(**kwargs: Any) -> None:
    message = kwargs["question"]
    subvar = kwargs["match"]
    script, lno = current_script_line()
    if _state.gui_console:
        return_queue = _queue.Queue()
        gui_args = {
            "title": script,
            "message": kwargs["question"],
            "button_list": [("Yes", 1, "y"), ("No", 0, "n")],
            "free": False,
        }
        _state.gui_manager_queue.put(GuiSpec(GUI_DISPLAY, gui_args, return_queue))
        user_response = return_queue.get(block=True)
        btn = user_response["button"]
        if btn is None:
            if _state.status.cancel_halt:
                _state.exec_log.log_exit_halt(script, lno, msg="Quit from ASK metacommand")
                exit_now(2, None)
        else:
            respstr = "Yes" if btn == 1 else "No"
    else:
        if os.name == "posix":
            resp = get_yn(message)
        else:
            resp = get_yn_win(message)
        if resp == chr(27):
            _state.exec_log.log_exit_halt(script, lno, msg="Quit from ASK metacommand")
            exit_now(2, None)
        else:
            respstr = "Yes" if resp == "y" else "No"
    subvarset = _state.subvars if subvar[0] != "~" else _state.commandliststack[-1].localvars
    subvarset.add_substitution(subvar, respstr)
    _state.exec_log.log_status_info(
        f"Question {{{message}}} answered {respstr} on line {lno} of script {script}",
    )
    return None


def x_pause(**kwargs: Any) -> None:
    quitmsg = "Quit from PAUSE metacommand"
    text = kwargs["text"]
    action = kwargs["action"]
    if action:
        action = action.lower()
    countdown = kwargs["countdown"]
    timeunit = kwargs["timeunit"]
    quit = False
    timed_out = False
    msg = text
    if countdown:
        countdown = float(countdown)
        msg = f"{msg}\nProcess will {action} after {countdown} {timeunit} without a response."
    maxtime_secs = countdown
    if timeunit and timeunit.lower() == "minutes":
        maxtime_secs = maxtime_secs * 60
    use_gui = False
    if _state.gui_manager_thread:
        return_queue = _queue.Queue()
        _state.gui_manager_queue.put(GuiSpec(QUERY_CONSOLE, {}, return_queue))
        user_response = return_queue.get(block=True)
        use_gui = user_response["console_running"]
    if use_gui or _state.conf.gui_level > 0:
        enable_gui()
        return_queue = _queue.Queue()
        gui_args = {
            "title": f"Script {current_script_line()[0]}",
            "message": msg,
            "countdown": maxtime_secs,
        }
        _state.gui_manager_queue.put(GuiSpec(GUI_PAUSE, gui_args, return_queue))
        user_response = return_queue.get(block=True)
        quit = user_response["quit"]
        return_queue.task_done()
    else:
        timed_out = False
        if os.name == "posix":
            rv = pause(msg, action=action, countdown=maxtime_secs, timeunit=timeunit)
        else:
            rv = pause_win(msg, action=action, countdown=maxtime_secs, timeunit=timeunit)
        quit = rv == 1
        timed_out = rv == 2
    if (quit or (timed_out and action == "halt")) and _state.status.cancel_halt:
        _state.exec_log.log_exit_halt(*current_script_line(), msg=quitmsg)
        exit_now(2, None)
    return None


def x_halt_msg(**kwargs: Any) -> None:
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
        of.write(f"{errmsg}\n")
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


def x_msg(**kwargs: Any) -> None:
    message = kwargs["message"]
    current_script_line()
    enable_gui()
    return_queue = _queue.Queue()
    gui_args = {"title": "Message", "message": message}
    _state.gui_manager_queue.put(GuiSpec(GUI_MSG, gui_args, return_queue))
    return_queue.get(block=True)
    return None


def x_reset_dialog_canceled(**kwargs: Any) -> None:
    _state.status.dialog_canceled = False
