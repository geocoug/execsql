from __future__ import annotations

"""
Debug metacommand handlers for execsql.

Handlers for the ``DEBUG …`` family of introspection metacommands and
``SHOW SCRIPTS`` script-block listing:

- ``x_debug_log_subvars`` / ``x_debug_write_subvars`` — dump substitution
  variables to the log file or to terminal/file (``DEBUG LOG SUBVARS`` /
  ``DEBUG WRITE SUBVARS``). Both accept optional ``LOCAL`` / ``USER``
  qualifiers.
- ``x_debug_log_config`` / ``x_debug_write_config`` — dump the merged
  configuration.
- ``x_debug_write_odbc_drivers`` — list installed ODBC drivers.
- ``x_debug_write_metacommands`` — dump the registered metacommand list
  (``DEBUG WRITE METACOMMANDLIST TO <file>``).
- ``x_debug_commandliststack`` — dump the current execution stack
  (``DEBUG WRITE COMMANDLISTSTACK``).
- ``x_debug_iflevels`` — dump the nested IF condition state
  (``DEBUG WRITE IFLEVELS``).
- ``x_show_scripts`` — list registered ``BEGIN SCRIPT`` blocks
  (``SHOW SCRIPTS [<name>]``), with optional name argument for detail.
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
    """Dump the unified AST execution stack.

    Shows every nesting construct the executor is currently inside:
    ``<main>`` script, ``EXECUTE SCRIPT`` calls, ``INCLUDE``'d files,
    ``IF``/``ELSEIF``/``ELSE`` branches, ``LOOP`` iterations (with iteration
    count), and ``BATCH`` blocks. Each frame shows source file and line.

    The legacy ``commandliststack`` is reported separately as a secondary view
    because it only records SCRIPT call frames; the unified ``ast_exec_stack``
    is the authoritative debugger view.
    """
    stack = getattr(_state, "ast_exec_stack", None) or []
    _state.output.write(f"Execution Stack (depth: {len(stack)}):\n")
    if not stack:
        _state.output.write("  (empty)\n")
        return None

    for depth, frame in enumerate(stack):
        kind_label = frame.kind.upper().replace("LOOP_", "LOOP ")
        # Right-hand description per kind
        if frame.kind in ("if", "elseif"):
            desc = f"{kind_label}  {frame.label}"
        elif frame.kind == "else":
            desc = kind_label
        elif frame.kind in ("loop_while", "loop_until"):
            desc = f"{kind_label}  {frame.label}  iter={frame.iteration}"
        elif frame.kind == "script":
            params = ""
            if frame.params:
                params = "(" + ", ".join(f"{k}={v!r}" for k, v in frame.params.items()) + ")"
            iter_suffix = f"  iter={frame.iteration}" if frame.iteration else ""
            desc = f"SCRIPT {frame.label}{params}{iter_suffix}"
        elif frame.kind == "include":
            desc = f"INCLUDE {frame.label}"
        elif frame.kind == "batch":
            desc = "BATCH"
        elif frame.kind == "main":
            desc = frame.label or "<main>"
        else:
            desc = f"{kind_label}  {frame.label}"
        src = f"  {frame.source}:{frame.line}" if frame.source and frame.line else ""
        _state.output.write(f"  [{depth}] {desc}{src}\n")
    return None


def x_debug_iflevels(**kwargs: Any) -> None:
    # Filter the unified AST exec stack to just IF/ELSEIF/ELSE frames.
    stack = getattr(_state, "ast_exec_stack", None) or []
    if_frames = [f for f in stack if f.kind in ("if", "elseif", "else")]
    if not if_frames:
        _state.output.write("If levels: (no active IF block)\n")
        return None

    _state.output.write(f"If levels (depth {len(if_frames)}):\n")
    for depth, frame in enumerate(if_frames):
        kind_label = frame.kind.upper()
        label = f"{kind_label} {frame.label}".strip() if frame.label else kind_label
        src = f"  {frame.source}:{frame.line}" if frame.source and frame.line else ""
        _state.output.write(f"  [{depth}] {label}{src}\n")
    return None


def x_debug_write_odbc_drivers(**kwargs: Any) -> None:
    try:
        import pyodbc
    except Exception:
        fatal_error("The pyodbc module is required.")
    output_dest = kwargs["filename"]
    append = kwargs["append"]
    if output_dest is not None and output_dest != "stdout" and append is None:
        filewriter_open_as_new(output_dest)

    def write(txt: str) -> None:
        if output_dest is None or output_dest == "stdout":
            _state.output.write(txt)
        else:
            filewriter_write(output_dest, txt)

    for d in pyodbc.drivers():
        write(f"{d}\n")


def x_debug_log_subvars(**kwargs: Any) -> None:
    local = kwargs["local"]
    user = kwargs["user"]
    localvars = _state.current_localvars()
    if localvars is not None:
        for s in localvars.substitutions:
            _state.exec_log.log_status_info(f"Substitution [{s[0]}] = [{s[1]}]")
    if local is None:
        for s in _state.subvars.substitutions:
            if user is None or s[0][0].isalnum() or s[0][0] == "_":
                _state.exec_log.log_status_info(f"Substitution [{s[0]}] = [{s[1]}]")


_SENSITIVE_ATTRS = frozenset({"smtp_password", "passwd", "password"})


def _config_lines() -> list[str]:
    """Return the merged config as a list of ``"[<section>] <key> = <value>"`` lines.

    Pulled directly from ``ConfigData._schema``, the registry that ``ConfigData``
    populates each time it reads an option from the INI files. Adding a new
    option to ``ConfigData.__init__`` automatically makes it appear here —
    nothing in this file needs updating.

    Lines are grouped by section in the order each section was first registered
    so the dump matches the natural reading order of ``execsql.conf``.

    Sensitive values (passwords) are redacted.
    """
    from execsql.config import ConfigData

    conf = _state.conf
    if conf is None:
        return ["(no config loaded)"]

    # Group attrs by section, preserving registration order within each section.
    by_section: dict[str, list[tuple[str, str, str]]] = {}
    section_order: list[str] = []
    for attr, (section, ini_key, type_label) in ConfigData._schema.items():
        if section not in by_section:
            by_section[section] = []
            section_order.append(section)
        by_section[section].append((attr, ini_key, type_label))

    lines: list[str] = []
    for section in section_order:
        lines.append(f"[{section}]")
        for attr, ini_key, _type_label in by_section[section]:
            value = getattr(conf, attr, "(unset)")
            if attr in _SENSITIVE_ATTRS and value:
                value = "***"
            lines.append(f"  {ini_key} = {value}  (attr: {attr})")
        lines.append("")

    # Runtime-computed values that aren't read from the INI file.
    lines.append("[runtime]")
    files = getattr(conf, "files_read", None) or []
    lines.append(f"  files_read = {', '.join(files) if files else '(none)'}")
    return lines


def x_debug_log_config(**kwargs: Any) -> None:
    for line in _config_lines():
        _state.exec_log.log_status_info(line)


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

    localvars = _state.current_localvars()
    if localvars is not None:
        for s in localvars.substitutions:
            write(f"Substitution [{s[0]}] = [{s[1]}]\n")
    if local is None:
        for s in _state.subvars.substitutions:
            if user is None or s[0][0].isalnum() or s[0][0] == "_":
                write(f"Substitution [{s[0]}] = [{s[1]}]\n")


def x_debug_write_config(**kwargs: Any) -> None:
    output_dest = kwargs["filename"]
    append = kwargs["append"]
    if output_dest is not None and output_dest != "stdout" and append is None:
        filewriter_open_as_new(output_dest)

    def write(txt: str) -> None:
        if output_dest is None or output_dest == "stdout":
            _state.output.write(txt)
        else:
            filewriter_write(output_dest, txt)

    for line in _config_lines():
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


def _format_script_source(span: Any, *, full_path: bool = False) -> str:
    """Return ``file:start-end`` from a SourceSpan.

    By default the filename is the basename, suitable for compact list-view
    output.  Pass ``full_path=True`` to retain the full source path (used by
    detail views like ``SHOW SCRIPTS <name>`` and ``.scripts <name>``).
    """
    if not span or not span.file:
        filename = "<unknown>"
    elif full_path:
        filename = span.file
    else:
        filename = Path(span.file).name
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
        src = _format_script_source(block.span, full_path=True)
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
