from __future__ import annotations

"""
Input/output metacommand handlers for execsql.

Implements the ``x_*`` handler functions for all output and I/O-related
metacommands:

- ``x_write`` / ``x_writeln`` — WRITE messages to log or console
- ``x_copy_file`` — COPY FILE
- ``x_delete_file`` / ``x_rename_file`` — file management
- ``x_pause`` — PAUSE execution until user input
- ``x_tee_log`` — TEE LOG on/off
- ``x_log`` — LOG to file
- ``x_set_write_output`` — redirect WRITE output
"""

import os
import sys
from shutil import copyfileobj
from typing import Any

import execsql.state as _state


def x_export(**kwargs: Any) -> None:
    schema = kwargs["schema"]
    table = kwargs["table"]
    queryname = _state.dbs.current().schema_qualified_table_name(schema, table)
    select_stmt = f"select * from {queryname};"
    outfile = kwargs["filename"]
    description = kwargs["description"]
    tee = kwargs["tee"]
    tee = False if not tee else True
    append = kwargs["append"]
    append = True if append else False
    filefmt = kwargs["format"].lower()
    zipfilename = kwargs["zipfilename"]
    if zipfilename is not None:
        if outfile.lower() == "stdout":
            raise _state.ErrInfo("error", other_msg="Cannot write stdout to a zipfile.")
        elif len(outfile) > 1 and outfile[1] == ":":
            raise _state.ErrInfo("error", other_msg="Cannot use a drive letter for a file path within a zipfile.")
        if filefmt == "duckdb":
            raise _state.ErrInfo("error", other_msg="Cannot export to the DuckDB format within a zipfile.")
        if filefmt == "sqlite":
            raise _state.ErrInfo("error", other_msg="Cannot export to the SQLite format within a zipfile.")
        if filefmt == "latex":
            raise _state.ErrInfo("error", other_msg="Cannot export to the LaTeX format within a zipfile.")
        if filefmt == "feather":
            raise _state.ErrInfo("error", other_msg="Cannot export to the feather format within a zipfile.")
        if filefmt == "hdf5":
            raise _state.ErrInfo("error", other_msg="Cannot export to the HDF5 format within a zipfile.")
        if filefmt == "ods":
            raise _state.ErrInfo("error", other_msg="Cannot export to an ODS workbook within a zipfile.")
    notype = True if kwargs.get("notype") else False
    if zipfilename is not None:
        _state.check_dir(zipfilename)
    else:
        _state.check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        _state.prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False, desc=description)
    if filefmt in ("txt", "text"):
        _state.prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("txt-and", "text-and"):
        _state.prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            and_val="AND",
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "ods":
        _state.write_query_to_ods(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            sheetname=queryname,
            desc=description,
        )
    elif filefmt == "duckdb":
        _state.write_query_to_duckdb(select_stmt, _state.dbs.current(), outfile, append, tablename=queryname)
    elif filefmt == "sqlite":
        _state.write_query_to_sqlite(select_stmt, _state.dbs.current(), outfile, append, tablename=queryname)
    elif filefmt == "xml":
        _state.write_query_to_xml(
            select_stmt,
            table,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "json":
        _state.write_query_to_json(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("json_ts", "json_tableschema"):
        _state.write_query_to_json_ts(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            not notype,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "values":
        _state.write_query_to_values(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "html":
        _state.write_query_to_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "cgi-html":
        _state.write_query_to_cgi_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "latex":
        _state.write_query_to_latex(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "hdf5":
        _state.write_query_to_hdf5(table, select_stmt, _state.dbs.current(), outfile, append, desc=description)
    else:
        try:
            hdrs, rows = _state.dbs.current().select_rowsource(select_stmt)
        except _state.ErrInfo:
            raise
        except Exception:
            raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())
        if filefmt == "raw":
            _state.write_query_raw(outfile, rows, _state.dbs.current().encoding, append, zipfile=zipfilename)
        elif filefmt == "b64":
            _state.write_query_b64(outfile, rows, append)
        elif filefmt == "feather":
            _state.write_query_to_feather(outfile, hdrs, rows)
        else:
            _state.write_delimited_file(outfile, filefmt, hdrs, rows, _state.conf.output_encoding, append, zipfilename)
    _state.export_metadata.add(_state.ExportRecord(queryname, outfile, zipfilename, description))
    return None


def x_export_query(**kwargs: Any) -> None:
    select_stmt = kwargs["query"]
    outfile = kwargs["filename"]
    description = kwargs["description"]
    tee = kwargs["tee"]
    tee = False if not tee else True
    append = kwargs["append"]
    append = True if append else False
    filefmt = kwargs["format"].lower()
    zipfilename = kwargs["zipfilename"]
    if zipfilename is not None:
        if outfile == "stdout":
            raise _state.ErrInfo("error", other_msg="Cannot write stdout to a zipfile.")
        elif len(outfile) > 1 and outfile[1] == ":":
            raise _state.ErrInfo("error", other_msg="Cannot use a drive letter for a file path within a zipfile.")
        if filefmt == "latex":
            raise _state.ErrInfo("error", other_msg="Cannot export to the LaTeX format within a zipfile.")
        if filefmt == "feather":
            raise _state.ErrInfo("error", other_msg="Cannot export to the feather format within a zipfile.")
        if filefmt == "hdf5":
            raise _state.ErrInfo("error", other_msg="Cannot export to the HDF5 format within a zipfile.")
        if filefmt == "ods":
            raise _state.ErrInfo("error", other_msg="Cannot export to an ODS workbook within a zipfile.")
    notype = True if kwargs.get("notype") else False
    _state.check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        _state.prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False, desc=description)
    if filefmt in ("txt", "text"):
        _state.prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("txt-and", "text-and"):
        _state.prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            and_val="AND",
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "ods":
        script_name, lno = _state.current_script_line()
        _state.write_query_to_ods(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            sheetname=f"Query_{lno}",
            desc=description,
        )
    elif filefmt == "json":
        _state.write_query_to_json(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("json_ts", "json_tableschema"):
        _state.write_query_to_json_ts(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            not notype,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "values":
        _state.write_query_to_values(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "html":
        _state.write_query_to_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "cgi-html":
        _state.write_query_to_cgi_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "latex":
        _state.write_query_to_latex(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    else:
        try:
            hdrs, rows = _state.dbs.current().select_rowsource(select_stmt)
        except _state.ErrInfo:
            raise
        except Exception:
            raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())
        if filefmt == "raw":
            _state.write_query_raw(outfile, rows, _state.dbs.current().encoding, append, zipfile=zipfilename)
        elif filefmt == "b64":
            _state.write_query_b64(outfile, rows, append, zipfile=zipfilename)
        elif filefmt == "feather":
            _state.write_query_to_feather(outfile, hdrs, rows)
        else:
            _state.write_delimited_file(
                outfile,
                filefmt,
                hdrs,
                rows,
                _state.conf.output_encoding,
                append,
                zipfile=zipfilename,
            )
    _state.export_metadata.add(_state.ExportRecord(select_stmt, outfile, zipfilename, description))
    return None


def x_export_query_with_template(**kwargs: Any) -> None:
    select_stmt = kwargs["query"]
    outfile = kwargs["filename"]
    template_file = kwargs["template"]
    tee = kwargs["tee"]
    tee = False if not tee else True
    append = kwargs["append"]
    append = True if append else False
    zipfilename = kwargs["zipfilename"]
    _state.check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        _state.prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False)
    _state.report_query(select_stmt, _state.dbs.current(), outfile, template_file, append, zipfile=zipfilename)
    _state.export_metadata.add(_state.ExportRecord(select_stmt, outfile, zipfilename))
    return None


def x_export_with_template(**kwargs: Any) -> None:
    schema = kwargs["schema"]
    table = kwargs["table"]
    queryname = _state.dbs.current().schema_qualified_table_name(schema, table)
    select_stmt = f"select * from {queryname};"
    outfile = kwargs["filename"]
    template_file = kwargs["template"]
    tee = kwargs["tee"]
    tee = False if not tee else True
    append = kwargs["append"]
    append = True if append else False
    zipfilename = kwargs["zipfilename"]
    _state.check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        _state.prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False)
    _state.report_query(select_stmt, _state.dbs.current(), outfile, template_file, append, zipfile=zipfilename)
    _state.export_metadata.add(_state.ExportRecord(queryname, outfile, zipfilename))
    return None


def x_export_ods_multiple(**kwargs: Any) -> None:
    table_list = kwargs["tables"]
    outfile = kwargs["filename"]
    description = kwargs["description"]
    tee = kwargs["tee"]
    tee = False if not tee else True
    append = kwargs["append"]
    append = False if append is None else True
    _state.check_dir(outfile)
    _state.write_queries_to_ods(table_list, _state.dbs.current(), outfile, append, tee, desc=description)


def x_export_metadata(**kwargs: Any) -> None:
    outfile = kwargs["filename"]
    append = kwargs["append"] is not None
    xall = kwargs["all"] is not None
    zipfilename = kwargs["zipfilename"]
    filefmt = kwargs["format"].lower()
    if xall:
        hdrs, rows = _state.export_metadata.get_all()
    else:
        hdrs, rows = _state.export_metadata.get()
    if outfile.lower() != "stdout":
        _state.check_dir(outfile)
    if filefmt in ("txt", "text"):
        _state.prettyprint_rowset(hdrs, rows, outfile, append, and_val="", zipfile=zipfilename)
    else:
        _state.write_delimited_file(outfile, filefmt, hdrs, rows, _state.conf.output_encoding, append, zipfilename)


def x_export_metadata_table(**kwargs: Any) -> None:
    xall = kwargs["all"] is not None
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    newstr = kwargs["new"]
    if newstr:
        is_new = 1 + ["new", "replacement"].index(newstr.lower())
    else:
        is_new = 0
    if xall:
        hdrs, rows = _state.export_metadata.get_all()
    else:
        hdrs, rows = _state.export_metadata.get()
    _state.import_data_table(_state.dbs.current(), schemaname, tablename, is_new, hdrs, rows)


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
        filename = os.path.join(os.path.expanduser(r"~"), filename[2:])
    if not os.path.exists(filename):
        raise _state.ErrInfo(
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
        _state.importtable(
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
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            "exception",
            exception_msg=_state.exception_desc(),
            other_msg=f"Can't import data from tabular text file {filename}",
        )
    return None


def x_import_file(**kwargs: Any) -> None:
    schemaname = kwargs["schema"]
    tablename = kwargs["table"]
    columnname = kwargs["columnname"]
    filename = kwargs["filename"]
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {filename} does not exist",
        )
    from execsql.metacommands.conditions import file_size_date

    sz, dt = file_size_date(filename)
    _state.exec_log.log_status_info(f"IMPORTing_FILE {filename} ({sz}, {dt})")
    try:
        _state.importfile(_state.dbs.current(), schemaname, tablename, columnname, filename)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            "exception",
            exception_msg=_state.exception_desc(),
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
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    try:
        _state.importods(_state.dbs.current(), schemaname, tablename, is_new, filename, sheetname, hdr_rows)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            "exception",
            exception_msg=_state.exception_desc(),
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
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    wbk = _state.OdsFile()
    try:
        wbk.open(filename)
    except Exception:
        raise _state.ErrInfo(type="cmd", other_msg=f"{filename} is not a valid OpenDocument spreadsheet.")
    sheets = wbk.sheetnames()
    impsheets = [s for s in sheets if rx.search(s)]
    tables = list(impsheets)
    if _state.conf.clean_col_hdrs:
        tables = _state.clean_words(tables)
    if _state.conf.fold_col_hdrs != "no":
        tables = _state.fold_words(tables, _state.conf.fold_col_hdrs)
    for ix in range(len(impsheets)):
        sheetname = impsheets[ix]
        tablename = tables[ix]
        try:
            _state.importods(_state.dbs.current(), schemaname, tablename, is_new, filename, sheetname, hdr_rows)
        except _state.ErrInfo:
            raise
        except Exception:
            raise _state.ErrInfo(
                "exception",
                exception_msg=_state.exception_desc(),
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
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    try:
        _state.importxls(_state.dbs.current(), schemaname, tablename, is_new, filename, sheetname, junk_hdrs, encoding)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            "exception",
            exception_msg=_state.exception_desc(),
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
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    if len(filename) < 4:
        raise _state.ErrInfo(type="cmd", other_msg=f"{filename} is not a recognizable Excel spreadsheet name.")
    ext3 = filename[-3:].lower()
    if ext3 == "xls":
        wbk = _state.XlsFile()
    elif ext3 == "lsx":
        wbk = _state.XlsxFile()
    else:
        raise _state.ErrInfo(type="cmd", other_msg=f"{filename} is not a recognizable Excel spreadsheet name.")
    try:
        wbk.open(filename, encoding, read_only=True)
    except Exception:
        raise _state.ErrInfo(type="cmd", other_msg=f"{filename} is not a valid Excel spreadsheet.")
    sheets = wbk.sheetnames()
    impsheets = [s for s in sheets if rx.search(s)]
    tables = list(impsheets)
    if _state.conf.clean_col_hdrs:
        tables = _state.clean_words(tables)
    if _state.conf.fold_col_hdrs != "no":
        tables = _state.fold_words(tables, _state.conf.fold_col_hdrs)
    for ix in range(len(impsheets)):
        sheetname = impsheets[ix]
        tablename = tables[ix]
        try:
            _state.importxls(
                _state.dbs.current(),
                schemaname,
                tablename,
                is_new,
                filename,
                sheetname,
                hdr_rows,
                encoding,
            )
        except _state.ErrInfo:
            raise
        except Exception:
            raise _state.ErrInfo(
                "exception",
                exception_msg=_state.exception_desc(),
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
        filename = os.path.join(os.path.expanduser(r"~"), filename[2:])
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {filename} does not exist",
        )
    from execsql.metacommands.conditions import file_size_date

    sz, dt = file_size_date(filename)
    _state.exec_log.log_status_info(f"IMPORTing from Parquet file {filename} ({sz}, {dt})")
    try:
        _state.import_parquet(_state.dbs.current(), schemaname, tablename, filename, is_new)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            "exception",
            exception_msg=_state.exception_desc(),
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
        filename = os.path.join(os.path.expanduser(r"~"), filename[2:])
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {filename} does not exist",
        )
    from execsql.metacommands.conditions import file_size_date

    sz, dt = file_size_date(filename)
    _state.exec_log.log_status_info(f"IMPORTing from Feather file {filename} ({sz}, {dt})")
    try:
        _state.import_feather(_state.dbs.current(), schemaname, tablename, filename, is_new)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo(
            "exception",
            exception_msg=_state.exception_desc(),
            other_msg=f"Can't import data from Feather data file {filename}",
        )
    return None


def x_import_row_buffer(**kwargs: Any) -> None:
    rows = kwargs["rows"]
    _state.conf.import_row_buffer = int(rows)


def x_export_row_buffer(**kwargs: Any) -> None:
    rows = kwargs["rows"]
    _state.conf.export_row_buffer = int(rows)


def x_write(**kwargs: Any) -> None:
    msg = f"{kwargs['text']}\n"
    tee = kwargs["tee"]
    tee = False if not tee else True
    outf = kwargs["filename"]
    if _state.conf.write_prefix is not None:
        msg = _state.substitute_vars(_state.conf.write_prefix) + " " + msg
    if _state.conf.write_suffix is not None:
        msg = msg[:-1] + " " + _state.substitute_vars(_state.conf.write_suffix) + "\n"
    if outf:
        _state.check_dir(outf)
        _state.filewriter_write(outf, msg)
    if (not outf) or tee:
        try:
            _state.output.write(msg)
        except TypeError:
            raise _state.ErrInfo(
                type="other",
                command_text=kwargs["metacommandline"],
                other_msg="TypeError in 'write' metacommand.",
            )
        except _state.ConsoleUIError as e:
            _state.output.reset()
            _state.exec_log.log_status_info(f"Console UI write failed (message {{{e.value}}}); output reset to stdout.")
            _state.output.write(msg.encode(_state.conf.output_encoding))
    if _state.conf.tee_write_log:
        _state.exec_log.log_user_msg(msg)
    return None


def x_write_create_table(**kwargs: Any) -> None:
    filename = kwargs["filename"]
    if not os.path.exists(filename):
        raise _state.ErrInfo(
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
    enc = _state.conf.import_encoding if not encoding else encoding
    inf = _state.CsvFile(filename, enc, junk_header_lines=junk_hdrs)
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
            _state.filewriter_write(outfile, txt)

    if outfile:
        _state.check_dir(outfile)
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
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    hdrs, data = _state.ods_data(filename, sheetname, hdr_rows)
    tablespec = _state.DataTable(hdrs, data)
    sql = tablespec.create_table(_state.dbs.current().type, schemaname, tablename, pretty=True)
    if outfile:
        if comment:
            _state.filewriter_write(outfile, f"-- {comment}\n")
        _state.filewriter_write(outfile, sql)
        _state.filewriter_close(outfile)
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
    enc = _state.conf.import_encoding if not encoding else encoding
    if not junk_hdrs:
        junk_hdrs = 0
    else:
        junk_hdrs = int(junk_hdrs)
    comment = kwargs["comment"]
    outfile = kwargs["outfile"]
    if not os.path.exists(filename):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Input file does not exist",
        )
    hdrs, data = _state.xls_data(filename, sheetname, junk_hdrs, enc)
    tablespec = _state.DataTable(hdrs, data)
    sql = tablespec.create_table(_state.dbs.current().type, schemaname, tablename, pretty=True)
    if outfile:
        if comment:
            _state.filewriter_write(outfile, f"-- {comment}\n")
        _state.filewriter_write(outfile, sql)
        _state.filewriter_close(outfile)
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
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias}.",
        )
    db = _state.dbs.aliased_as(alias)
    tbl = db.schema_qualified_table_name(schema, table)
    try:
        if not db.table_exists(table, schema):
            raise _state.ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg=f"Table {tbl} does not exist",
            )
    except Exception:
        pass
    select_stmt = f"select * from {tbl};"
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())
    tablespec = _state.DataTable(hdrs, rows)
    sql = tablespec.create_table(_state.dbs.current().type, kwargs["schema1"], kwargs["table1"], pretty=True)
    if outfile:
        if comment:
            _state.filewriter_write(outfile, f"-- {comment}\n")
        _state.filewriter_write(outfile, sql)
        _state.filewriter_close(outfile)
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


def x_writescript(**kwargs: Any) -> None:
    script_id = kwargs["script_id"]
    output_dest = kwargs["filename"]
    append = kwargs["append"]

    def write(txt: str) -> None:
        if output_dest is None or output_dest == "stdout":
            _state.output.write(txt)
        else:
            _state.filewriter_write(output_dest, txt)

    if output_dest is not None and output_dest != "stdout":
        _state.check_dir(output_dest)
        if not append:
            _state.filewriter_open_as_new(output_dest)
    script = _state.savedscripts[script_id]
    if script.paramnames is not None and len(script.paramnames) > 0:
        write(f"BEGIN SCRIPT {script_id} ({', '.join(script.paramnames)})\n")
    else:
        write(f"BEGIN SCRIPT {script_id}\n")
    lines = [c.commandline() for c in script.cmdlist]
    for line in lines:
        write(f"{line}\n")
    write(f"END SCRIPT {script_id}\n")


def x_include(**kwargs: Any) -> None:
    filename = kwargs["filename"]
    if len(filename) > 1 and filename[0] == "~" and filename[1] == os.sep:
        filename = os.path.join(os.path.expanduser(r"~"), filename[2:])
    exists = kwargs["exists"]
    if exists is not None:
        if os.path.isfile(filename):
            _state.read_sqlfile(filename)
    else:
        if not os.path.isfile(filename):
            raise _state.ErrInfo(type="error", other_msg=f"File {filename} does not exist.")
        _state.read_sqlfile(filename)
    return None


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
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias1}.",
        )
    if alias2 not in _state.dbs.aliases():
        raise _state.ErrInfo(
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
            raise _state.ErrInfo(
                type="cmd",
                command_text=kwargs["metacommandline"],
                other_msg=f"Table {tbl1} does not exist",
            )
    except Exception:
        pass
    if new_tbl2 and new_tbl2 == "new":
        try:
            if db2.table_exists(table2, schema2):
                raise _state.ErrInfo(
                    type="cmd",
                    command_text=kwargs["metacommandline"],
                    other_msg=f"Table {tbl2} already exists",
                )
        except Exception:
            pass
    select_stmt = f"select * from {tbl1};"

    def get_ts() -> _state.DataTable:
        if get_ts.tablespec is None:
            hdrs, rows = db1.select_rowsource(select_stmt)
            get_ts.tablespec = _state.DataTable(hdrs, rows)
        return get_ts.tablespec

    get_ts.tablespec = None

    if new_tbl2:
        tbl_desc = get_ts()
        create_tbl = tbl_desc.create_table(db2.type, schema2, table2)
        if new_tbl2 == "replacement":
            try:
                db2.drop_table(tbl2)
            except Exception:
                _state.exec_log.log_status_info(f"Could not drop existing table ({tbl2}) for COPY metacommand")
        db2.execute(create_tbl)
        if db2.type == _state.dbt_firebird:
            db2.execute("COMMIT;")
    try:
        hdrs, rows = db1.select_rowsource(select_stmt)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())
    try:
        db2.populate_table(schema2, table2, rows, hdrs, get_ts)
        db2.commit()
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())


def x_copy_query(**kwargs: Any) -> None:
    alias1 = kwargs["alias1"].lower()
    select_stmt = kwargs["query"]
    new = kwargs["new"]
    new_tbl2 = new.lower() if new else None
    alias2 = kwargs["alias2"].lower()
    schema2 = kwargs["schema"]
    table2 = kwargs["table"]
    if alias1 not in _state.dbs.aliases():
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {alias1}.",
        )
    if alias2 not in _state.dbs.aliases():
        raise _state.ErrInfo(
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
                raise _state.ErrInfo(
                    type="cmd",
                    command_text=kwargs["metacommandline"],
                    other_msg=f"Table {tbl2} already exists",
                )
        except Exception:
            pass

    def get_ts() -> _state.DataTable:
        if not get_ts.tablespec:
            hdrs, rows = db1.select_rowsource(select_stmt)
            get_ts.tablespec = _state.DataTable(hdrs, rows)
        return get_ts.tablespec

    get_ts.tablespec = None

    if new_tbl2:
        try:
            hdrs, rows = db1.select_rowsource(select_stmt)
        except _state.ErrInfo:
            raise
        except Exception:
            raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())
        get_ts.tablespec = _state.DataTable(hdrs, rows)
        tbl_desc = get_ts.tablespec
        create_tbl = tbl_desc.create_table(db2.type, schema2, table2)
        if new_tbl2 == "replacement":
            try:
                db2.drop_table(tbl2)
            except Exception:
                _state.exec_log.log_status_info(f"Could not drop existing table ({tbl2}) for COPY metacommand")
        db2.execute(create_tbl)
        if db2.type == _state.dbt_firebird:
            db2.execute("COMMIT;")
    try:
        hdrs, rows = db1.select_rowsource(select_stmt)
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())
    try:
        db2.populate_table(schema2, table2, rows, hdrs, get_ts)
        db2.commit()
    except _state.ErrInfo:
        raise
    except Exception:
        raise _state.ErrInfo("db", select_stmt, exception_msg=_state.exception_desc())


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
        if os.path.isfile(f):
            zf.write(f)
    zf.close()


def x_zip_buffer_mb(**kwargs: Any) -> None:
    size_mb = kwargs["size"]
    _state.conf.zip_buffer_mb = int(size_mb)


def x_rm_file(**kwargs: Any) -> None:
    import glob as _glob

    fn = kwargs["filename"].strip(' "')
    fnlist = _glob.glob(fn)
    for f in fnlist:
        if os.path.isfile(f):
            _state.filewriter_close(f)
            os.unlink(f)


def x_make_export_dirs(**kwargs: Any) -> None:
    setting = kwargs["setting"].lower()
    _state.conf.make_export_dirs = setting in ("yes", "on", "true", "1")


def x_cd(**kwargs: Any) -> None:
    new_dir = _state.unquoted(kwargs["dir"])
    if not os.path.isdir(new_dir):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="Directory does not exist",
        )
    os.chdir(new_dir)
    script, lno = _state.current_script_line()
    _state.exec_log.log_status_info(f"Current directory changed to {new_dir} at line {lno} of {script}")
    return None


def x_scan_lines(**kwargs: Any) -> None:
    _state.conf.scan_lines = int(kwargs["scanlines"])


def x_hdf5_text_len(**kwargs: Any) -> None:
    _state.conf.hdf5_text_len = int(kwargs["textlen"])


def x_serve(**kwargs: Any) -> None:
    infname = kwargs["filename"]
    fmt = kwargs["format"].lower()
    if not os.path.isfile(infname):
        raise _state.ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Input file {infname} does not exist",
        )
    fname = os.path.basename(infname)
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
    print(f"Content-Disposition: attachment; filename={fname}\n")
    with open(infname, "rb") as f:
        copyfileobj(f, sys.stdout.buffer)
