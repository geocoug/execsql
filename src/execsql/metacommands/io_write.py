"""WRITE metacommand handlers.

- ``x_write`` — WRITE "<text>" [TEE TO <file>] (text output).
- ``x_writescript`` — WRITE SCRIPT <name> [TO <file>] (dump a named
  script block).
- ``x_write_create_table`` — WRITE CREATE_TABLE … (emit a CREATE TABLE
  statement inferred from a data source); plus the format-specific
  variants ``x_write_create_table_ods``, ``x_write_create_table_xls``,
  ``x_write_create_table_alias``.
- ``x_write_prefix`` / ``x_write_suffix`` — CONFIG WRITE_PREFIX /
  CONFIG WRITE_SUFFIX (set text prepended / appended to every WRITE).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.exporters.delimited import CsvFile
from execsql.importers.ods import ods_data
from execsql.importers.xls import xls_data
from execsql.models import DataTable
from execsql.script import substitute_vars
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import check_dir, filewriter_close, filewriter_open_as_new, filewriter_write
from execsql.utils.gui import ConsoleUIError


def x_write(**kwargs: Any) -> None:
    msg = f"{kwargs['text']}\n"
    tee = kwargs["tee"]
    tee = bool(tee)
    outf = kwargs["filename"]
    if _state.conf.write_prefix is not None:
        msg = substitute_vars(_state.conf.write_prefix) + " " + msg
    if _state.conf.write_suffix is not None:
        msg = msg[:-1] + " " + substitute_vars(_state.conf.write_suffix) + "\n"
    if outf:
        check_dir(outf)
        filewriter_write(outf, msg)
    if (not outf) or tee:
        try:
            _state.output.write(msg)
        except TypeError as e:
            raise ErrInfo(
                type="other",
                command_text=kwargs["metacommandline"],
                other_msg="TypeError in 'write' metacommand.",
            ) from e
        except ConsoleUIError as e:
            _state.output.reset()
            _state.exec_log.log_status_info(f"Console UI write failed (message {{{e}}}); output reset to stdout.")
            _state.output.write(msg)
    if _state.conf.tee_write_log:
        _state.exec_log.log_user_msg(msg)
    return None


def x_write_create_table(**kwargs: Any) -> None:
    filename = kwargs["filename"]
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    quotechar = kwargs["quotechar"]
    delimchar = kwargs["delimchar"]
    encoding = kwargs["encoding"]
    if delimchar:
        if delimchar.lower() == "tab":
            delimchar = chr(9)
        elif delimchar.lower() in ("unitsep", "us"):
            delimchar = chr(31)
    junk_hdrs = kwargs["skip"]
    if not junk_hdrs:
        junk_hdrs = 0
    else:
        junk_hdrs = int(junk_hdrs)
    enc = encoding if encoding else _state.conf.import_encoding
    inf = CsvFile(filename, enc, junk_header_lines=junk_hdrs)
    if quotechar and delimchar:
        inf.lineformat(delimchar, quotechar, None)
    inf.evaluate_column_types()
    sql = inf.create_table(_state.dbs.current().type, kwargs["schema"], kwargs["table"], pretty=True)
    inf.close()
    comment = kwargs["comment"]
    outfile = kwargs["outfile"]

    def write(txt: str) -> None:
        if outfile is None or outfile == "stdout":
            _state.output.write(txt)
        else:
            filewriter_write(outfile, txt)

    if outfile:
        check_dir(outfile)
    if comment:
        write(f"-- {comment}\n")
    write(f"{sql}\n")


def x_write_create_table_ods(**kwargs: Any) -> None:
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    filename = kwargs["filename"]
    sheetname = kwargs["sheet"]
    hdr_rows = kwargs["skip"]
    if not hdr_rows:
        hdr_rows = 0
    else:
        hdr_rows = int(hdr_rows)
    comment = kwargs["comment"]
    outfile = kwargs["outfile"]
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    hdrs, data = ods_data(filename, sheetname, hdr_rows)
    tablespec = DataTable(hdrs, data)
    sql = tablespec.create_table(_state.dbs.current().type, schemaname, tablename, pretty=True)
    if outfile:
        if comment:
            filewriter_write(outfile, f"-- {comment}\n")
        filewriter_write(outfile, sql)
        filewriter_close(outfile)
    else:
        if comment:
            _state.output.write(f"-- {comment}\n")
        _state.output.write(f"{sql}\n")


def x_write_create_table_xls(**kwargs: Any) -> None:
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    filename = kwargs["filename"]
    sheetname = kwargs["sheet"]
    junk_hdrs = kwargs["skip"]
    encoding = kwargs["encoding"]
    enc = encoding if encoding else _state.conf.import_encoding
    if not junk_hdrs:
        junk_hdrs = 0
    else:
        junk_hdrs = int(junk_hdrs)
    comment = kwargs["comment"]
    outfile = kwargs["outfile"]
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    hdrs, data = xls_data(filename, sheetname, junk_hdrs, enc)
    tablespec = DataTable(hdrs, data)
    sql = tablespec.create_table(_state.dbs.current().type, schemaname, tablename, pretty=True)
    if outfile:
        if comment:
            filewriter_write(outfile, f"-- {comment}\n")
        filewriter_write(outfile, sql)
        filewriter_close(outfile)
    else:
        if comment:
            _state.output.write(f"-- {comment}\n")
        _state.output.write(f"{sql}\n")


def x_write_create_table_alias(**kwargs: Any) -> None:
    alias = kwargs["alias"].lower()
    schema = kwargs["schema"]
    table = kwargs["table"]
    comment = kwargs["comment"]
    outfile = kwargs["filename"]
    if alias not in _state.dbs.aliases():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias}.",
        )
    db = _state.dbs.aliased_as(alias)
    tbl = db.schema_qualified_table_name(schema, table)
    try:
        if not db.table_exists(table, schema):
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg=f"Table {tbl} does not exist",
            )
    except Exception:
        pass  # Best-effort check; some adapters lack information_schema.
    select_stmt = f"select * from {tbl};"
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    tablespec = DataTable(hdrs, rows)
    sql = tablespec.create_table(_state.dbs.current().type, kwargs["schema1"], kwargs["table1"], pretty=True)
    if outfile:
        if comment:
            filewriter_write(outfile, f"-- {comment}\n")
        filewriter_write(outfile, sql)
        filewriter_close(outfile)
    else:
        if comment:
            _state.output.write(f"-- {comment}\n")
        _state.output.write(f"{sql}\n")


def x_write_prefix(**kwargs: Any) -> None:
    pf = kwargs["prefix"]
    if pf.lower() == "clear":
        _state.conf.write_prefix = None
    else:
        _state.conf.write_prefix = pf
    return None


def x_write_suffix(**kwargs: Any) -> None:
    sf = kwargs["suffix"]
    if sf.lower() == "clear":
        _state.conf.write_suffix = None
    else:
        _state.conf.write_suffix = sf
    return None


def _render_script_nodes(nodes: Any, emit: Any) -> None:
    """Walk a list of AST nodes and emit reconstructed source lines.

    Every node type that can legally appear in a ``ScriptBlock.body`` is
    handled — nested ``IfBlock`` / ``LoopBlock`` / ``BatchBlock`` /
    ``SqlBlock`` structures render with their delimiters; ``Comment`` and
    ``IncludeDirective`` (``INCLUDE`` / ``EXECUTE SCRIPT``) are preserved.
    Unknown node types raise ``ErrInfo`` rather than silently disappear so
    future AST additions can't quietly cause data loss.
    """
    from execsql.exceptions import ErrInfo
    from execsql.script.ast import (
        BatchBlock,
        Comment,
        IfBlock,
        IncludeDirective,
        LoopBlock,
        MetaCommandStatement,
        ScriptBlock,
        SqlBlock,
        SqlStatement,
    )

    for node in nodes:
        if isinstance(node, SqlStatement):
            emit(f"{node.text}\n")
        elif isinstance(node, MetaCommandStatement):
            emit(f"-- !x! {node.command}\n")
        elif isinstance(node, Comment):
            # Preserve comment text verbatim; the parser stores it including
            # the leading "--" / "/* ... */" delimiters.
            emit(f"{node.text}\n")
        elif isinstance(node, IncludeDirective):
            kw = "EXECUTE SCRIPT" if node.is_execute_script else "INCLUDE"
            if_exists = " IF EXISTS" if node.if_exists else ""
            args = f" ({node.arguments})" if node.arguments else ""
            loop = f" LOOP {node.loop_type} ({node.loop_condition})" if node.loop_type else ""
            emit(f"-- !x! {kw}{if_exists} {node.target}{args}{loop}\n")
        elif isinstance(node, IfBlock):
            emit(f"-- !x! IF ({node.condition})\n")
            for mod in node.condition_modifiers:
                kw = "ANDIF" if mod.kind == "AND" else "ORIF"
                emit(f"-- !x! {kw} ({mod.condition})\n")
            _render_script_nodes(node.body, emit)
            for clause in node.elseif_clauses:
                emit(f"-- !x! ELSEIF ({clause.condition})\n")
                for mod in clause.condition_modifiers:
                    kw = "ANDIF" if mod.kind == "AND" else "ORIF"
                    emit(f"-- !x! {kw} ({mod.condition})\n")
                _render_script_nodes(clause.body, emit)
            if node.else_body:
                emit("-- !x! ELSE\n")
                _render_script_nodes(node.else_body, emit)
            emit("-- !x! ENDIF\n")
        elif isinstance(node, LoopBlock):
            emit(f"-- !x! LOOP {node.loop_type} ({node.condition})\n")
            _render_script_nodes(node.body, emit)
            emit("-- !x! END LOOP\n")
        elif isinstance(node, BatchBlock):
            emit("-- !x! BEGIN BATCH\n")
            _render_script_nodes(node.body, emit)
            emit("-- !x! END BATCH\n")
        elif isinstance(node, SqlBlock):
            emit("-- !x! BEGIN SQL\n")
            _render_script_nodes(node.body, emit)
            emit("-- !x! END SQL\n")
        elif isinstance(node, ScriptBlock):
            # Nested SCRIPT definition — emit recursively with its own
            # BEGIN/END SCRIPT framing.
            param_names = node.param_names
            if param_names:
                emit(f"-- !x! BEGIN SCRIPT {node.name} ({', '.join(param_names)})\n")
            else:
                emit(f"-- !x! BEGIN SCRIPT {node.name}\n")
            _render_script_nodes(node.body, emit)
            emit(f"-- !x! END SCRIPT {node.name}\n")
        else:
            raise ErrInfo(
                type="cmd",
                other_msg=f"WRITE SCRIPT cannot render AST node of type {type(node).__name__}.",
            )


def x_writescript(**kwargs: Any) -> None:
    """Dump a registered SCRIPT block's source to stdout or a file.

    Reads from the AST script registry (``ctx.ast_scripts``) and walks the
    full block tree — including nested IF / LOOP / BATCH structures —
    reconstructing source between ``BEGIN SCRIPT`` and ``END SCRIPT``
    delimiters so the output is re-includable.
    """
    from execsql.exceptions import ErrInfo

    script_id = kwargs["script_id"].lower()
    output_dest = kwargs["filename"]
    append = kwargs["append"]

    block = _state.ast_scripts.get(script_id)
    if block is None:
        raise ErrInfo("cmd", other_msg=f"There is no SCRIPT named {script_id}.")

    def write(txt: str) -> None:
        if output_dest is None or output_dest == "stdout":
            _state.output.write(txt)
        else:
            filewriter_write(output_dest, txt)

    if output_dest is not None and output_dest != "stdout":
        check_dir(output_dest)
        if not append:
            filewriter_open_as_new(output_dest)

    param_names = block.param_names
    if param_names:
        write(f"-- !x! BEGIN SCRIPT {script_id} ({', '.join(param_names)})\n")
    else:
        write(f"-- !x! BEGIN SCRIPT {script_id}\n")
    _render_script_nodes(block.body, write)
    write(f"-- !x! END SCRIPT {script_id}\n")
