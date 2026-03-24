from __future__ import annotations

"""
Data import and export metacommand handlers for execsql.

Implements ``x_export`` (the EXPORT metacommand) and ``x_import`` (the
IMPORT metacommand).  These are among the most complex handlers: they
parse the full metacommand argument syntax (format, file name, options)
and delegate to the appropriate exporter or importer function in
:mod:`execsql.exporters` and :mod:`execsql.importers`.
"""

import math
from typing import Any

import execsql.state as _state


def x_sub(**kwargs: Any) -> None:
    varname = kwargs["match"]
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.add_substitution(varname, kwargs["repl"])
    return None


def x_sub_add(**kwargs: Any) -> None:
    varname = kwargs["match"]
    increment_expr = kwargs["increment"]
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.increment_by(varname, _state.NumericParser(increment_expr).parse().eval())
    return None


def x_sub_append(**kwargs: Any) -> None:
    varname = kwargs["match"]
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.append_substitution(varname, kwargs["repl"])
    return None


def x_sub_empty(**kwargs: Any) -> None:
    varname = kwargs["match"]
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.add_substitution(varname, "")
    return None


def x_rm_sub(**kwargs: Any) -> None:
    varname = kwargs["match"]
    subvarset = _state.subvars if varname[0] != "~" else _state.commandliststack[-1].localvars
    subvarset.remove_substitution(varname)
    return None


def x_sub_local(**kwargs: Any) -> None:
    varname = kwargs["match"]
    if varname[0] != "~":
        varname = "~" + varname
    _state.commandliststack[-1].localvars.add_substitution(varname, kwargs["repl"])
    return None


def x_sub_tempfile(**kwargs: Any) -> None:
    varname = kwargs["match"]
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.add_substitution(varname, _state.tempfiles.new_temp_fn())
    return None


def x_sub_ini(**kwargs: Any) -> None:
    from configparser import ConfigParser

    ini_fn = kwargs["filename"]
    ini_sect = kwargs["section"]
    cp = ConfigParser()
    cp.read(ini_fn)
    if cp.has_section(ini_sect):
        varsect = cp.items(ini_sect)
        for sub, repl in varsect:
            if not _state.subvars.var_name_ok(sub):
                raise _state.ErrInfo(type="error", other_msg=f"Invalid variable name in SUB_INI file: {sub}")
            _state.subvars.add_substitution(sub, repl)


def x_sub_querystring(**kwargs: Any) -> None:
    from urllib.parse import parse_qsl

    qstr = kwargs["qstr"]
    sublist = parse_qsl(qstr)
    for sub, value in sublist:
        _state.subvars.add_substitution(sub, value)
    return None


def x_sub_encrypt(**kwargs: Any) -> None:
    varname = kwargs["match"]
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.add_substitution(varname, _state.Encrypt().encrypt(kwargs["plaintext"]))
    return None


def x_sub_decrypt(**kwargs: Any) -> None:
    varname = kwargs["match"]
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.add_substitution(varname, _state.Encrypt().decrypt(kwargs["crypttext"]))
    return None


def x_subdata(**kwargs: Any) -> None:
    varname = kwargs["match"]
    sql = f"select * from {kwargs['datasource']};"
    db = _state.dbs.current()
    subvarset, varname = _state.get_subvarset(varname, kwargs["metacommandline"])
    subvarset.remove_substitution(varname)
    try:
        _, rec = db.select_rowsource(sql)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            type="exception",
            exception_msg=_state.exception_desc(),
            other_msg=f"Can't get headers and rows from {sql}.",
        )
    try:
        row1 = next(rec)
    except Exception:
        row1 = None
    if row1:
        dataval = row1[0]
        if dataval is None:
            dataval = ""
        if not isinstance(dataval, str):
            dataval = str(dataval)
        subvarset.add_substitution(varname, dataval)
    return None


def x_selectsub(**kwargs: Any) -> None:
    sql = f"select * from {kwargs['datasource']};"
    db = _state.dbs.current()
    script, line_no = _state.current_script_line()
    nodatamsg = (
        f"There are no data in {kwargs['datasource']} to use with the SELECT_SUB metacommand "
        f"(script {script}, line {line_no})."
    )
    try:
        hdrs, rec = db.select_rowsource(sql)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            type="exception",
            exception_msg=_state.exception_desc(),
            other_msg=f"Can't get headers and rows from {sql}.",
        )
    for subvar in hdrs:
        subvar = "@" + subvar
        if _state.subvars.sub_exists(subvar):
            _state.subvars.remove_substitution(subvar)
            if _state.conf.log_datavars:
                _state.exec_log.log_status_info(f"Substitution variable {subvar} removed on line {line_no} of {script}")
    try:
        row1 = next(rec)
    except StopIteration:
        row1 = None
    except Exception:
        raise _state.ErrInfo(type="exception", exception_msg=_state.exception_desc(), other_msg=nodatamsg)
    if row1:
        for i, item in enumerate(row1):
            if item is None:
                item = ""
            item = str(item)
            match_str = "@" + hdrs[i]
            _state.subvars.add_substitution(match_str, item)
            if _state.conf.log_datavars:
                _state.exec_log.log_status_info(
                    f"Substitution variable {match_str} set to {{{item}}} on line {line_no} of {script}",
                )
    else:
        _state.exec_log.log_status_info(nodatamsg)
    return None


def x_prompt_selectsub(**kwargs: Any) -> None:
    import queue as _queue

    schema = kwargs["schema"]
    table = kwargs["table"]
    msg = kwargs["msg"]
    cont = kwargs["cont"]
    help_url = _state.unquoted(kwargs["help"])
    db = _state.dbs.current()
    sq_name = db.schema_qualified_table_name(schema, table)
    sql = f"select * from {sq_name};"
    hdrs, rows = db.select_data(sql)
    if len(rows) == 0:
        raise _state.ErrInfo(type="error", other_msg=f"The table {sq_name} has no rows to display.")
    for subvar in hdrs:
        subvar = "@" + subvar
        _state.subvars.remove_substitution(subvar)
    btns = [("OK", 1, "O")]
    if cont:
        btns.append(("Continue", 2, "<Return>"))
    _state.enable_gui()
    return_queue = _queue.Queue()
    gui_args = {
        "title": "Select data",
        "message": msg,
        "button_list": btns,
        "column_headers": hdrs,
        "rowset": rows,
        "help_url": help_url,
    }
    _state.gui_manager_queue.put(_state.GuiSpec(_state.GUI_SELECTSUB, gui_args, return_queue))
    user_response = return_queue.get(block=True)
    btn_val = user_response["button"]
    return_val = user_response["return_value"]
    selected_row = None
    if btn_val and btn_val == 1:
        selected_row = rows[int(return_val[0])]
    script, line_no = _state.current_script_line()
    if btn_val is None or (btn_val == 1 and selected_row is None):
        if _state.status.cancel_halt:
            _state.exec_log.log_exit_halt(
                script,
                line_no,
                msg=f"Halted from prompt for row of {sq_name} on line {line_no} of {script}",
            )
            _state.exit_now(2, None)
    else:
        if btn_val == 1:
            for i, item in enumerate(selected_row):
                if item is None:
                    item = ""
                item = str(item)
                match_str = "@" + hdrs[i]
                _state.subvars.add_substitution(match_str, item)
                if _state.conf.log_datavars:
                    _state.exec_log.log_status_info(
                        f"Substitution string {match_str} set to {{{item}}} on line {line_no} of {script}",
                    )
    return None


def x_empty_strings(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.empty_strings = flag in ("yes", "on", "true", "1")
    return None


def x_trim_strings(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.trim_strings = flag in ("yes", "on", "true", "1")
    return None


def x_replace_newlines(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.replace_newlines = flag in ("yes", "on", "true", "1")
    return None


def x_empty_rows(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.empty_rows = flag in ("yes", "on", "true", "1")
    return None


def x_only_strings(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.only_strings = flag in ("yes", "on", "true", "1")
    return None


def x_boolean_int(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.boolean_int = flag in ("yes", "on", "true", "1")
    return None


def x_boolean_words(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.boolean_words = flag in ("yes", "on", "true", "1")
    return None


def x_fold_col_hdrs(**kwargs: Any) -> None:
    _state.conf.fold_col_hdrs = kwargs["foldspec"]
    return None


def x_trim_col_hdrs(**kwargs: Any) -> None:
    _state.conf.trim_col_hdrs = kwargs["which"].lower()
    return None


def x_clean_col_hdrs(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.clean_col_hdrs = flag in ("yes", "on", "true", "1")
    return None


def x_del_empty_cols(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.del_empty_cols = flag in ("yes", "on", "true", "1")
    return None


def x_create_col_hdrs(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.create_col_hdrs = flag in ("yes", "on", "true", "1")
    return None


def x_dedup_col_hdrs(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.dedup_col_hdrs = flag in ("yes", "on", "true", "1")
    return None


def x_import_common_cols_only(**kwargs: Any) -> None:
    flag = kwargs["yesno"].lower()
    _state.conf.import_common_cols_only = flag in ("yes", "on", "true", "1")
    return None


def x_quote_all_text(**kwargs: Any) -> None:
    setting = kwargs["setting"].lower()
    _state.conf.quote_all_text = setting in ("yes", "on", "true", "1")


def x_reset_counter(**kwargs: Any) -> None:
    ctr_no = int(kwargs["counter_no"])
    _state.counters.remove_counter(ctr_no)


def x_reset_counters(**kwargs: Any) -> None:
    _state.counters.remove_all_counters()


def x_set_counter(**kwargs: Any) -> None:
    ctr_no = int(kwargs["counter_no"])
    ctr_expr = kwargs["value"]
    _state.counters.set_counter(ctr_no, int(math.floor(_state.NumericParser(ctr_expr).parse().eval())))


def x_max_int(**kwargs: Any) -> None:
    maxint = kwargs["maxint"]
    _state.conf.max_int = int(maxint)
    return None
