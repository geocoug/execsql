"""File and system operation metacommand handlers.

Implements ``x_include``, ``x_copy``, ``x_copy_query``, ``x_zip``,
``x_zip_buffer_mb``, ``x_rm_file``, ``x_make_export_dirs``, ``x_cd``,
``x_scan_lines``, ``x_hdf5_text_len``, and ``x_serve``.
"""

from __future__ import annotations

import os
import sys
from itertools import tee
from pathlib import Path
from shutil import copyfileobj
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.models import DataTable
from execsql.script import current_script_line
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close
from execsql.utils.strings import unquoted


def _close_rowsource(rows: Any) -> None:
    close = getattr(rows, "close", None)
    if close:
        close()


def x_include(**kwargs: Any) -> None:
    # INCLUDE is now handled natively by the AST executor (_execute_include_native).
    # This handler exists only for dispatch table registration compatibility.
    raise ErrInfo(
        type="cmd",
        other_msg="INCLUDE should be handled by the AST executor, not the dispatch table.",
    )


def x_copy(**kwargs: Any) -> None:
    alias1 = kwargs["alias1"].lower()
    schema1 = kwargs["schema1"]
    table1 = kwargs["table1"]
    new = kwargs["new"]
    new_tbl2 = new.lower() if new else None
    alias2 = kwargs["alias2"].lower()
    schema2 = kwargs["schema2"]
    table2 = kwargs["table2"]
    if alias1 not in _state.dbs.aliases():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias1}.",
        )
    if alias2 not in _state.dbs.aliases():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias2}.",
        )
    db1 = _state.dbs.aliased_as(alias1)
    db2 = _state.dbs.aliased_as(alias2)
    tbl1 = db1.schema_qualified_table_name(schema1, table1)
    tbl2 = db2.schema_qualified_table_name(schema2, table2)
    try:
        if not db1.table_exists(table1, schema1):
            raise ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg=f"Table {tbl1} does not exist",
            )
    except Exception:
        pass  # Best-effort check; some adapters lack information_schema.
    if new_tbl2 and new_tbl2 == "new":
        try:
            if db2.table_exists(table2, schema2):
                raise ErrInfo(
                    type="cmd",
                    command_text=kwargs["metacommandline"],
                    other_msg=f"Table {tbl2} already exists",
                )
        except Exception:
            pass  # Best-effort check; some adapters lack information_schema.
    select_stmt = f"select * from {tbl1};"

    get_ts_tablespec = None
    rows_to_close = None

    if new_tbl2:
        try:
            hdrs, rows = db1.select_rowsource(select_stmt)
        except ErrInfo:
            raise
        except Exception as e:
            raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
        rows_to_close = rows
        rows_for_schema, rows = tee(rows)
        get_ts_tablespec = DataTable(hdrs, rows_for_schema)
        tbl_desc = get_ts_tablespec
        create_tbl = tbl_desc.create_table(db2.type, schema2, table2)
        if new_tbl2 == "replacement":
            try:
                db2.drop_table(tbl2)
            except ErrInfo:
                raise
            except Exception as e:
                raise ErrInfo(
                    type="db",
                    other_msg=f"Could not drop existing table ({tbl2}) for COPY metacommand",
                    exception_msg=exception_desc(),
                ) from e
        db2.execute(create_tbl)
        if db2.needs_explicit_commit_after_ddl():
            db2.execute("COMMIT;")
    else:
        try:
            hdrs, rows = db1.select_rowsource(select_stmt)
        except ErrInfo:
            raise
        except Exception as e:
            raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
        rows_to_close = rows

    def get_ts() -> DataTable:
        nonlocal get_ts_tablespec
        if get_ts_tablespec is None:
            ts_hdrs, ts_rows = db1.select_rowsource(select_stmt)
            get_ts_tablespec = DataTable(ts_hdrs, ts_rows)
        return get_ts_tablespec

    try:
        db2.populate_table(schema2, table2, rows, hdrs, get_ts)
        db2.commit()
    except BaseException:
        _close_rowsource(rows_to_close)
        raise


def x_copy_query(**kwargs: Any) -> None:
    alias1 = kwargs["alias1"].lower()
    select_stmt = kwargs["query"]
    new = kwargs["new"]
    new_tbl2 = new.lower() if new else None
    alias2 = kwargs["alias2"].lower()
    schema2 = kwargs["schema"]
    table2 = kwargs["table"]
    if alias1 not in _state.dbs.aliases():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias1}.",
        )
    if alias2 not in _state.dbs.aliases():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias2}.",
        )
    db1 = _state.dbs.aliased_as(alias1)
    db2 = _state.dbs.aliased_as(alias2)
    tbl2 = db2.schema_qualified_table_name(schema2, table2)
    if new_tbl2 and new_tbl2 == "new":
        try:
            if db2.table_exists(table2, schema2):
                raise ErrInfo(
                    type="cmd",
                    command_text=kwargs["metacommandline"],
                    other_msg=f"Table {tbl2} already exists",
                )
        except Exception:
            pass  # Best-effort check; some adapters lack information_schema.

    get_ts_tablespec = None
    rows_to_close = None

    if new_tbl2:
        try:
            hdrs, rows = db1.select_rowsource(select_stmt)
        except ErrInfo:
            raise
        except Exception as e:
            raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
        rows_to_close = rows
        rows_for_schema, rows = tee(rows)
        get_ts_tablespec = DataTable(hdrs, rows_for_schema)
        tbl_desc = get_ts_tablespec
        create_tbl = tbl_desc.create_table(db2.type, schema2, table2)
        if new_tbl2 == "replacement":
            try:
                db2.drop_table(tbl2)
            except ErrInfo:
                raise
            except Exception as e:
                raise ErrInfo(
                    type="db",
                    other_msg=f"Could not drop existing table ({tbl2}) for COPY metacommand",
                    exception_msg=exception_desc(),
                ) from e
        db2.execute(create_tbl)
        if db2.needs_explicit_commit_after_ddl():
            db2.execute("COMMIT;")
    else:
        try:
            hdrs, rows = db1.select_rowsource(select_stmt)
        except ErrInfo:
            raise
        except Exception as e:
            raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
        rows_to_close = rows

    def get_ts() -> DataTable:
        nonlocal get_ts_tablespec
        if get_ts_tablespec is None:
            ts_hdrs, ts_rows = db1.select_rowsource(select_stmt)
            get_ts_tablespec = DataTable(ts_hdrs, ts_rows)
        return get_ts_tablespec

    try:
        db2.populate_table(schema2, table2, rows, hdrs, get_ts)
        db2.commit()
    except BaseException:
        _close_rowsource(rows_to_close)
        raise


def x_zip(**kwargs: Any) -> None:
    import zipfile as _zipfile
    import glob as _glob

    files = kwargs["filename"].strip(' "')
    zipfile_name = kwargs["zipfilename"].strip(' "')
    append = kwargs["append"]
    zmode = "a" if append is not None else "w"
    zf = _zipfile.ZipFile(zipfile_name, mode=zmode, compression=_zipfile.ZIP_BZIP2, compresslevel=9)
    fnlist = _glob.glob(files)
    for f in fnlist:
        if Path(f).is_file():
            zf.write(f)
    zf.close()


def x_zip_buffer_mb(**kwargs: Any) -> None:
    size_mb = kwargs["size"]
    _state.conf.zip_buffer_mb = int(size_mb)


def x_rm_file(**kwargs: Any) -> None:
    import glob as _glob

    if not getattr(_state.conf, "allow_rm_file", True):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs.get("metacommandline", "RM_FILE"),
            other_msg="The RM_FILE metacommand is disabled (--no-rm-file).",
        )

    fn = kwargs["filename"].strip(' "')
    fnlist = _glob.glob(fn)
    for f in fnlist:
        if Path(f).is_file():
            filewriter_close(f)
            os.unlink(f)


def x_make_export_dirs(**kwargs: Any) -> None:
    setting = kwargs["setting"].lower()
    _state.conf.make_export_dirs = setting in ("yes", "on", "true", "1")


def x_cd(**kwargs: Any) -> None:
    new_dir = unquoted(kwargs["dir"])
    if not Path(new_dir).is_dir():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Directory does not exist",
        )
    os.chdir(new_dir)
    script, lno = current_script_line()
    _state.exec_log.log_status_info(f"Current directory changed to {new_dir} at line {lno} of {script}")
    if _state.subvars is not None:
        from execsql.script.engine import set_static_system_vars

        set_static_system_vars()
    return None


def x_scan_lines(**kwargs: Any) -> None:
    _state.conf.scan_lines = int(kwargs["scanlines"])


def x_hdf5_text_len(**kwargs: Any) -> None:
    _state.conf.hdf5_text_len = int(kwargs["textlen"])


def x_serve(**kwargs: Any) -> None:
    from execsql.utils.fileio import safe_output_path

    if not getattr(_state.conf, "allow_serve", True):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs.get("metacommandline", "SERVE"),
            other_msg="The SERVE metacommand is disabled (--no-serve).",
        )

    infname = kwargs["filename"]
    serve_root = getattr(_state.conf, "serve_root", None)
    if serve_root:
        infname = safe_output_path(infname, serve_root)
    fmt = kwargs["format"].lower()
    if not Path(infname).is_file():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {infname} does not exist",
        )
    fname = Path(infname).name
    if fmt == "binary":
        contenttype = "application/octet-stream"
    elif fmt == "csv":
        contenttype = "text/csv"
    elif fmt in ("txt", "text"):
        contenttype = "text/plain"
    elif fmt == "ods":
        contenttype = "application/vnd.oasis.opendocument.spreadsheet"
    elif fmt == "json":
        contenttype = "application/json"
    elif fmt == "html":
        contenttype = "text/html"
    elif fmt == "pdf":
        contenttype = "application/pdf"
    elif fmt == "zip":
        contenttype = "application/zip"
    else:
        contenttype = "application/octet-stream"
    print(f"Content-Type: {contenttype}")
    safe_fname = fname.replace("\r", "").replace("\n", "").replace('"', '\\"')
    print(f'Content-Disposition: attachment; filename="{safe_fname}"\n')
    with open(infname, "rb") as f:
        copyfileobj(f, sys.stdout.buffer)
