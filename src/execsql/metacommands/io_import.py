"""Import metacommand handlers.

Implements ``x_import``, ``x_import_file``, ODS/XLS/Parquet/Feather
import handlers, and the import row buffer setting.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.importers.csv import importfile, importtable
from execsql.importers.feather import import_feather, import_parquet
from execsql.importers.ods import OdsFile, importods
from execsql.exporters.xls import XlsFile, XlsxFile
from execsql.importers.xls import importxls
from execsql.utils.errors import exception_desc
from execsql.utils.strings import clean_words, fold_words


def x_import(**kwargs: Any) -> None:
    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    filename = kwargs["filename"]
    if len(filename) > 1 and filename[0] == "~" and filename[1] == os.sep:
        filename = str(Path.home() / filename[2:])
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {filename} does not exist",
        )
    quotechar = kwargs["quotechar"]
    if quotechar:
        quotechar = quotechar.lower()
    delimchar = kwargs["delimchar"]
    if delimchar:
        if delimchar.lower() == "tab":
            delimchar = chr(9)
        elif delimchar.lower() in ("unitsep", "us"):
            delimchar = chr(31)
    enc = kwargs["encoding"]
    junk_hdrs = kwargs["skip"]
    if not junk_hdrs:
        junk_hdrs = 0
    else:
        junk_hdrs = int(junk_hdrs)
    from execsql.metacommands.conditions import file_size_date

    sz, dt = file_size_date(filename)
    _state.exec_log.log_status_info(f"IMPORTing {filename} ({sz}, {dt})")
    try:
        importtable(
            _state.dbs.current(),
            schemaname,
            tablename,
            filename,
            is_new,
            skip_header_line=True,
            quotechar=quotechar,
            delimchar=delimchar,
            encoding=enc,
            junk_header_lines=junk_hdrs,
        )
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't import data from tabular text file {filename}",
        )
    return None


def x_import_file(**kwargs: Any) -> None:
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    columnname = kwargs["columnname"]
    filename = kwargs["filename"]
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {filename} does not exist",
        )
    from execsql.metacommands.conditions import file_size_date

    sz, dt = file_size_date(filename)
    _state.exec_log.log_status_info(f"IMPORTing_FILE {filename} ({sz}, {dt})")
    try:
        importfile(_state.dbs.current(), schemaname, tablename, columnname, filename)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't import file {filename}",
        )
    return None


def x_import_ods(**kwargs: Any) -> None:
    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    filename = kwargs["filename"]
    sheetname = kwargs["sheetname"]
    hdr_rows = kwargs["skip"]
    if not hdr_rows:
        hdr_rows = 0
    else:
        hdr_rows = int(hdr_rows)
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    try:
        importods(_state.dbs.current(), schemaname, tablename, is_new, filename, sheetname, hdr_rows)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't import data from ODS file {filename}",
        )
    return None


def x_import_ods_pattern(**kwargs: Any) -> None:
    import re

    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    schemaname = kwargs["schema"]
    filename = kwargs["filename"]
    rx = re.compile(kwargs["patn"], re.I)
    hdr_rows = kwargs["skip"]
    if not hdr_rows:
        hdr_rows = 0
    else:
        hdr_rows = int(hdr_rows)
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    wbk = OdsFile()
    try:
        wbk.open(filename)
    except Exception:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a valid OpenDocument spreadsheet.")
    sheets = wbk.sheetnames()
    impsheets = [s for s in sheets if rx.search(s)]
    tables = list(impsheets)
    if _state.conf.clean_col_hdrs:
        tables = clean_words(tables)
    if _state.conf.fold_col_hdrs != "no":
        tables = fold_words(tables, _state.conf.fold_col_hdrs)
    for ix in range(len(impsheets)):
        sheetname = impsheets[ix]
        tablename = tables[ix]
        try:
            importods(_state.dbs.current(), schemaname, tablename, is_new, filename, sheetname, hdr_rows)
        except ErrInfo:
            raise
        except Exception:
            raise ErrInfo(
                "exception",
                exception_msg=exception_desc(),
                other_msg=f"Can't import data from ODS file {filename}",
            )
    _state.subvars.add_substitution("$SHEETS_IMPORTED", ",".join(impsheets))
    _state.subvars.add_substitution("$SHEETS_TABLES", ",".join(tables))
    if schemaname is None:
        _state.subvars.add_substitution("$SHEETS_TABLES_VALUES", ",".join([f"('{t}')" for t in tables]))
    else:
        _state.subvars.add_substitution("$SHEETS_TABLES_VALUES", ",".join([f"('{schemaname}.{t}')" for t in tables]))
    return None


def x_import_xls(**kwargs: Any) -> None:
    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    filename = kwargs["filename"]
    sheetname = kwargs["sheetname"]
    junk_hdrs = kwargs["skip"]
    encoding = kwargs["encoding"]
    if not junk_hdrs:
        junk_hdrs = 0
    else:
        junk_hdrs = int(junk_hdrs)
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    try:
        importxls(_state.dbs.current(), schemaname, tablename, is_new, filename, sheetname, junk_hdrs, encoding)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't import data from Excel file {filename}",
        )
    return None


def x_import_xls_pattern(**kwargs: Any) -> None:
    import re

    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    schemaname = kwargs["schema"]
    filename = kwargs["filename"]
    rx = re.compile(kwargs["patn"], re.I)
    hdr_rows = kwargs["skip"]
    encoding = kwargs["encoding"]
    if not hdr_rows:
        hdr_rows = 0
    else:
        hdr_rows = int(hdr_rows)
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    if len(filename) < 4:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a recognizable Excel spreadsheet name.")
    ext3 = filename[-3:].lower()
    if ext3 == "xls":
        wbk = XlsFile()
    elif ext3 == "lsx":
        wbk = XlsxFile()
    else:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a recognizable Excel spreadsheet name.")
    try:
        wbk.open(filename, encoding, read_only=True)
    except Exception:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a valid Excel spreadsheet.")
    sheets = wbk.sheetnames()
    impsheets = [s for s in sheets if rx.search(s)]
    tables = list(impsheets)
    if _state.conf.clean_col_hdrs:
        tables = clean_words(tables)
    if _state.conf.fold_col_hdrs != "no":
        tables = fold_words(tables, _state.conf.fold_col_hdrs)
    for ix in range(len(impsheets)):
        sheetname = impsheets[ix]
        tablename = tables[ix]
        try:
            importxls(
                _state.dbs.current(),
                schemaname,
                tablename,
                is_new,
                filename,
                sheetname,
                hdr_rows,
                encoding,
            )
        except ErrInfo:
            raise
        except Exception:
            raise ErrInfo(
                "exception",
                exception_msg=exception_desc(),
                other_msg=f"Can't import data from ODS file {filename}",
            )
    _state.subvars.add_substitution("$SHEETS_IMPORTED", ",".join(impsheets))
    _state.subvars.add_substitution("$SHEETS_TABLES", ",".join(tables))
    if schemaname is None:
        _state.subvars.add_substitution("$SHEETS_TABLES_VALUES", ",".join([f"('{t}')" for t in tables]))
    else:
        _state.subvars.add_substitution("$SHEETS_TABLES_VALUES", ",".join([f"('{schemaname}.{t}')" for t in tables]))
    return None


def x_import_parquet(**kwargs: Any) -> None:
    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    filename = kwargs["filename"]
    if len(filename) > 1 and filename[0] == "~" and filename[1] == os.sep:
        filename = str(Path.home() / filename[2:])
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {filename} does not exist",
        )
    from execsql.metacommands.conditions import file_size_date

    sz, dt = file_size_date(filename)
    _state.exec_log.log_status_info(f"IMPORTing from Parquet file {filename} ({sz}, {dt})")
    try:
        import_parquet(_state.dbs.current(), schemaname, tablename, filename, is_new)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't import data from Parquet data file {filename}",
        )
    return None


def x_import_feather(**kwargs: Any) -> None:
    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    filename = kwargs["filename"]
    if len(filename) > 1 and filename[0] == "~" and filename[1] == os.sep:
        filename = str(Path.home() / filename[2:])
    if not Path(filename).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {filename} does not exist",
        )
    from execsql.metacommands.conditions import file_size_date

    sz, dt = file_size_date(filename)
    _state.exec_log.log_status_info(f"IMPORTing from Feather file {filename} ({sz}, {dt})")
    try:
        import_feather(_state.dbs.current(), schemaname, tablename, filename, is_new)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't import data from Feather data file {filename}",
        )
    return None


def x_import_row_buffer(**kwargs: Any) -> None:
    rows = kwargs["rows"]
    _state.conf.import_row_buffer = int(rows)


def x_show_progress(**kwargs: Any) -> None:
    setting = kwargs["setting"].lower()
    _state.conf.show_progress = setting in ("yes", "on", "true", "1")
