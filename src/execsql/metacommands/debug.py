from __future__ import annotations

"""
Debug metacommand handlers for execsql.

Provides ``x_debug_write_metacommands``, which implements the
``WRITE METACOMMANDS`` debug metacommand that prints the full registered
metacommand list to the log/console for troubleshooting.

Also provides ``x_show_scripts`` for runtime introspection of registered
SCRIPT blocks.
"""

from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.utils.errors import fatal_error
from execsql.utils.fileio import EncodedFile, filewriter_open_as_new, filewriter_write


def x_debug_write_metacommands(**kwargs: Any) -> None:
    output_dest = kwargs["filename"]
    if output_dest is None or output_dest == "stdout":
        ofile = _state.output
    else:
        ofile = EncodedFile(output_dest, _state.conf.output_encoding).open("w")
    try:
        for m in _state.metacommandlist:
            ofile.write(f"({m.hitcount})  {m.rx.pattern}\n")
    finally:
        if output_dest is not None and output_dest != "stdout":
            ofile.close()


def x_debug_commandliststack(**kwargs: Any) -> None:
    _state.output.write("Command List Stack:\n")
    pfx = "  "
    for cl in _state.commandliststack:
        _state.output.write(pfx + f"Name:             {cl.listname}\n")
        _state.output.write(pfx + f"Parameters:       {cl.paramnames}\n")
        _state.output.write(pfx + f"Command pointer:  {cl.cmdptr}\n")
        pfx = pfx + "  "
    return None


def x_debug_iflevels(**kwargs: Any) -> None:
    if len(_state.if_stack.if_levels) == 0:
        _state.output.write("If levels: None\n")
    else:
        _state.output.write(
            "If levels: [{}]\n".format(",".join([str(tf.tf_value) for tf in _state.if_stack.if_levels])),
        )
    return None


def x_debug_write_odbc_drivers(**kwargs: Any) -> None:
    try:
        import pyodbc
    except Exception:
        fatal_error("The pyodbc module is required.")
    output_dest = kwargs["filename"]
    append = kwargs["append"]

    def write(txt: str) -> None:
        if output_dest is None or output_dest == "stdout":
            _state.output.write(txt)
        else:
            if not append:
                filewriter_open_as_new(output_dest)
            filewriter_write(output_dest, txt)

    for d in pyodbc.drivers():
        write(f"{d}\n")


def x_debug_log_subvars(**kwargs: Any) -> None:
    local = kwargs["local"]
    user = kwargs["user"]
    if _state.commandliststack:
        for s in _state.commandliststack[-1].localvars.substitutions:
            _state.exec_log.log_status_info(f"Substitution [{s[0]}] = [{s[1]}]")
    if local is None:
        for s in _state.subvars.substitutions:
            if user is None or s[0][0].isalnum() or s[0][0] == "_":
                _state.exec_log.log_status_info(f"Substitution [{s[0]}] = [{s[1]}]")


def x_debug_log_config(**kwargs: Any) -> None:
    conf = _state.conf
    _state.exec_log.log_status_info(f"Config; Script encoding = {conf.script_encoding}")
    _state.exec_log.log_status_info(f"Config; Output encoding = {conf.output_encoding}")
    _state.exec_log.log_status_info(f"Config; Import encoding = {conf.import_encoding}")
    _state.exec_log.log_status_info(f"Config; Import common columns only = {conf.import_common_cols_only}")
    _state.exec_log.log_status_info(f"Config; Use numeric type for Access = {conf.access_use_numeric}")
    _state.exec_log.log_status_info(f"Config; Max int = {conf.max_int}")
    _state.exec_log.log_status_info(f"Config; Boolean int = {conf.boolean_int}")
    _state.exec_log.log_status_info(f"Config; Boolean words = {conf.boolean_words}")
    _state.exec_log.log_status_info(f"Config; Clean column headers {conf.clean_col_hdrs}")
    _state.exec_log.log_status_info(f"Config; Create column headers {conf.create_col_hdrs}")
    _state.exec_log.log_status_info(f"Config; Dedup column headers {conf.dedup_col_hdrs}")
    _state.exec_log.log_status_info(f"Config; Console wait when done {conf.gui_wait_on_exit}")
    _state.exec_log.log_status_info(f"Config; Console wait when error {conf.gui_wait_on_error_halt}")
    _state.exec_log.log_status_info(f"Config; Empty rows = {conf.empty_rows}")
    _state.exec_log.log_status_info(f"Config; Empty_strings = {conf.empty_strings}")
    _state.exec_log.log_status_info(f"Config: Trim_strings = {conf.trim_strings}")
    _state.exec_log.log_status_info(f"Config: Replace_newlines = {conf.replace_newlines}")
    _state.exec_log.log_status_info(f"Config; Only_strings = {conf.only_strings}")
    _state.exec_log.log_status_info(f"Config; Scan lines = {conf.scan_lines}")
    _state.exec_log.log_status_info(f"Config; Import row buffer size = {conf.import_row_buffer}")
    _state.exec_log.log_status_info(f"Config; Write warnings to console = {conf.write_warnings}")
    _state.exec_log.log_status_info(f"Config; Write prefix = {conf.write_prefix}")
    _state.exec_log.log_status_info(f"Config; Write suffix = {conf.write_suffix}")
    _state.exec_log.log_status_info(f"Config; Log write messages = {conf.tee_write_log}")
    _state.exec_log.log_status_info(f"Config; Log data variable assignments = {conf.log_datavars}")
    _state.exec_log.log_status_info(f"Config; GUI level = {conf.gui_level}")
    _state.exec_log.log_status_info(f"Config; CSS file for HTML export = {conf.css_file}")
    _state.exec_log.log_status_info(f"Config; CSS styles for HTML export = {conf.css_styles}")
    _state.exec_log.log_status_info(f"Config; Make export directories = {conf.make_export_dirs}")
    _state.exec_log.log_status_info(f"Config; Quote all text on export = {conf.quote_all_text}")
    _state.exec_log.log_status_info(f"Config; Export row buffer size = {conf.export_row_buffer}")
    _state.exec_log.log_status_info(f"Config; Text length for HDF5 export = {conf.hdf5_text_len}")
    _state.exec_log.log_status_info(f"Config; Template processor = {conf.template_processor}")
    _state.exec_log.log_status_info(f"Config; SMTP host = {conf.smtp_host}")
    _state.exec_log.log_status_info(f"Config; SMTP port = {conf.smtp_port}")
    _state.exec_log.log_status_info(f"Config; SMTP username = {conf.smtp_username}")
    _state.exec_log.log_status_info(f"Config; SMTP use SSL = {conf.smtp_ssl}")
    _state.exec_log.log_status_info(f"Config; SMTP use TLS = {conf.smtp_tls}")
    _state.exec_log.log_status_info(f"Config; Email format = {conf.email_format}")
    _state.exec_log.log_status_info(f"Config; Email CSS = {conf.email_css}")
    _state.exec_log.log_status_info(f"Config; Zip buffer size (Mb) = {conf.zip_buffer_mb}")
    _state.exec_log.log_status_info(f"Config; DAO flush delay (seconds) = {conf.dao_flush_delay_secs}")
    _state.exec_log.log_status_info(f"Config; Configuration files read = {', '.join(conf.files_read)}")


def x_debug_write_subvars(**kwargs: Any) -> None:
    output_dest = kwargs["filename"]
    append = kwargs["append"]
    user = kwargs["user"]
    local = kwargs["local"]
    if output_dest is not None and output_dest != "stdout" and append is None:
        filewriter_open_as_new(output_dest)

    def write(txt: str) -> None:
        if output_dest is None or output_dest == "stdout":
            _state.output.write(txt)
        else:
            filewriter_write(output_dest, txt)

    if _state.commandliststack:
        for s in _state.commandliststack[-1].localvars.substitutions:
            write(f"Substitution [{s[0]}] = [{s[1]}]\n")
    if local is None:
        for s in _state.subvars.substitutions:
            if user is None or s[0][0].isalnum() or s[0][0] == "_":
                write(f"Substitution [{s[0]}] = [{s[1]}]\n")


def x_debug_write_config(**kwargs: Any) -> None:
    output_dest = kwargs["filename"]
    append = kwargs["append"]
    conf = _state.conf
    lines = [
        f"Config; Script encoding = {conf.script_encoding}",
        f"Config; Output encoding = {conf.output_encoding}",
        f"Config; Import encoding = {conf.import_encoding}",
        f"Config; GUI level = {conf.gui_level}",
    ]
    if output_dest is not None and output_dest != "stdout" and append is None:
        filewriter_open_as_new(output_dest)

    def write(txt: str) -> None:
        if output_dest is None or output_dest == "stdout":
            _state.output.write(txt)
        else:
            filewriter_write(output_dest, txt)

    for line in lines:
        write(f"{line}\n")


# ---------------------------------------------------------------------------
# Helpers for SCRIPT introspection (shared by metacommands and REPL)
# ---------------------------------------------------------------------------


def _format_script_signature(name: str, param_defs: Any) -> str:
    """Return ``name(param1, param2, opt=default)`` or ``name()``.

    *param_defs* may be a list of :class:`ParamDef` objects (preferred) or
    a plain list of strings (backward compat).
    """
    if not param_defs:
        return f"{name}()"
    parts: list[str] = []
    for p in param_defs:
        if hasattr(p, "default") and p.default is not None:
            parts.append(f"{p.name}={p.default}")
        elif hasattr(p, "name"):
            parts.append(p.name)
        else:
            parts.append(str(p))
    return f"{name}({', '.join(parts)})"


def _format_script_source(span: Any) -> str:
    """Return ``file:start-end`` from a SourceSpan."""
    filename = Path(span.file).name if span and span.file else "<unknown>"
    if span and span.start_line is not None:
        if span.end_line is not None and span.end_line != span.start_line:
            return f"{filename}:{span.start_line}-{span.end_line}"
        return f"{filename}:{span.start_line}"
    return filename


# ---------------------------------------------------------------------------
# SHOW SCRIPTS metacommand handler
# ---------------------------------------------------------------------------


def x_show_scripts(**kwargs: Any) -> None:
    """List all registered scripts, or show detail for one script.

    Without a name argument, lists all registered SCRIPT definitions with
    their parameter signatures and source locations.  With a name, shows
    detail for that script including parameters, source, and docstring.
    """
    script_name = (kwargs.get("script_id") or "").strip().lower()
    scripts = _state.ast_scripts

    if script_name:
        # ---------- detail for one script ----------
        if script_name not in scripts:
            _state.output.write(f"No script named '{script_name}' is registered.\n")
            return
        block = scripts[script_name]
        sig = _format_script_signature(block.name, block.param_defs)
        src = _format_script_source(block.span)
        _state.output.write(f"Script: {sig}\n")
        _state.output.write(f"Source: {src}\n")
        if block.param_defs:
            _state.output.write("Parameters:\n")
            max_name = max(len(p.name) for p in block.param_defs)
            for p in block.param_defs:
                if p.default is not None:
                    _state.output.write(f"  {p.name:<{max_name}}  (optional, default: {p.default})\n")
                else:
                    _state.output.write(f"  {p.name:<{max_name}}  (required)\n")
        else:
            _state.output.write("Parameters: (none)\n")
        if block.doc:
            _state.output.write("\n")
            for doc_line in block.doc.split("\n"):
                _state.output.write(f"  {doc_line}\n")
    else:
        # ---------- list all scripts ----------
        if not scripts:
            _state.output.write("No scripts registered.\n")
            return
        _state.output.write(f"Registered scripts ({len(scripts)}):\n\n")
        sigs = {name: _format_script_signature(name, block.param_defs) for name, block in scripts.items()}
        max_sig = max(len(s) for s in sigs.values())
        for name, block in scripts.items():
            sig = sigs[name]
            src = _format_script_source(block.span)
            _state.output.write(f"  {sig:<{max_sig}}  {src}\n")
        _state.output.write("\n")
