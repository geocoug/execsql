"""Export metacommand handlers.

Implements ``x_export``, ``x_export_query``, template-based exports,
ODS multi-sheet export, and export metadata operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.exporters.base import ExportRecord
from execsql.exporters.delimited import write_delimited_file
from execsql.exporters.duckdb import write_query_to_duckdb
from execsql.exporters.feather import write_query_to_feather, write_query_to_hdf5
from execsql.exporters.html import write_query_to_cgi_html, write_query_to_html
from execsql.exporters.json import write_query_to_json, write_query_to_json_ts
from execsql.exporters.latex import write_query_to_latex
from execsql.exporters.ods import write_queries_to_ods, write_query_to_ods
from execsql.exporters.parquet import write_query_to_parquet
from execsql.exporters.pretty import prettyprint_query, prettyprint_rowset
from execsql.exporters.raw import write_query_b64, write_query_raw
from execsql.exporters.sqlite import write_query_to_sqlite
from execsql.exporters.templates import report_query
from execsql.exporters.values import write_query_to_values
from execsql.exporters.xml import write_query_to_xml
from execsql.importers.base import import_data_table
from execsql.script import current_script_line
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import check_dir


def _apply_output_dir(path: str) -> str:
    """Prepend the configured --output-dir to *path* if it is a relative path.

    If ``conf.export_output_dir`` is set and *path* is not absolute (and not
    ``stdout``), the base directory is joined to *path* so that all EXPORT
    output lands in the same directory without requiring scripts to hard-code
    absolute paths.
    """
    output_dir = getattr(_state.conf, "export_output_dir", None)
    if not output_dir:
        return path
    if path.lower() == "stdout":
        return path
    if Path(path).is_absolute():
        return path
    # Windows drive-letter paths are also absolute
    if len(path) > 1 and path[1] == ":":
        return path
    return str(Path(output_dir) / path)


def x_export(**kwargs: Any) -> None:
    schema = kwargs["schema"]
    table = kwargs["table"]
    queryname = _state.dbs.current().schema_qualified_table_name(schema, table)
    select_stmt = f"select * from {queryname};"
    outfile = _apply_output_dir(kwargs["filename"])
    description = kwargs["description"]
    tee = kwargs["tee"]
    tee = bool(tee)
    append = kwargs["append"]
    append = bool(append)
    filefmt = kwargs["format"].lower()
    zipfilename = _apply_output_dir(kwargs["zipfilename"]) if kwargs["zipfilename"] else None
    if zipfilename is not None:
        if outfile.lower() == "stdout":
            raise ErrInfo("error", other_msg="Cannot write stdout to a zipfile.")
        elif len(outfile) > 1 and outfile[1] == ":":
            raise ErrInfo("error", other_msg="Cannot use a drive letter for a file path within a zipfile.")
        if filefmt == "duckdb":
            raise ErrInfo("error", other_msg="Cannot export to the DuckDB format within a zipfile.")
        if filefmt == "sqlite":
            raise ErrInfo("error", other_msg="Cannot export to the SQLite format within a zipfile.")
        if filefmt == "latex":
            raise ErrInfo("error", other_msg="Cannot export to the LaTeX format within a zipfile.")
        if filefmt == "feather":
            raise ErrInfo("error", other_msg="Cannot export to the feather format within a zipfile.")
        if filefmt == "parquet":
            raise ErrInfo("error", other_msg="Cannot export to the parquet format within a zipfile.")
        if filefmt == "hdf5":
            raise ErrInfo("error", other_msg="Cannot export to the HDF5 format within a zipfile.")
        if filefmt == "ods":
            raise ErrInfo("error", other_msg="Cannot export to an ODS workbook within a zipfile.")
    notype = bool(kwargs.get("notype"))
    if zipfilename is not None:
        check_dir(zipfilename)
    else:
        check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False, desc=description)
    if filefmt in ("txt", "text"):
        prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("txt-and", "text-and"):
        prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            and_val="AND",
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "ods":
        write_query_to_ods(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            sheetname=queryname,
            desc=description,
        )
    elif filefmt == "duckdb":
        write_query_to_duckdb(select_stmt, _state.dbs.current(), outfile, append, tablename=queryname)
    elif filefmt == "sqlite":
        write_query_to_sqlite(select_stmt, _state.dbs.current(), outfile, append, tablename=queryname)
    elif filefmt == "xml":
        write_query_to_xml(
            select_stmt,
            table,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "json":
        write_query_to_json(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("json_ts", "json_tableschema"):
        write_query_to_json_ts(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            not notype,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "values":
        write_query_to_values(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "html":
        write_query_to_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "cgi-html":
        write_query_to_cgi_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "latex":
        write_query_to_latex(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "hdf5":
        write_query_to_hdf5(table, select_stmt, _state.dbs.current(), outfile, append, desc=description)
    else:
        try:
            hdrs, rows = _state.dbs.current().select_rowsource(select_stmt)
        except ErrInfo:
            raise
        except Exception:
            raise ErrInfo("db", select_stmt, exception_msg=exception_desc())
        if filefmt == "raw":
            write_query_raw(outfile, rows, _state.dbs.current().encoding, append, zipfile=zipfilename)
        elif filefmt == "b64":
            write_query_b64(outfile, rows, append)
        elif filefmt == "feather":
            write_query_to_feather(outfile, hdrs, rows)
        elif filefmt == "parquet":
            write_query_to_parquet(outfile, hdrs, rows)
        else:
            write_delimited_file(outfile, filefmt, hdrs, rows, _state.conf.output_encoding, append, zipfilename)
    _state.export_metadata.add(ExportRecord(queryname, outfile, zipfilename, description))
    return None


def x_export_query(**kwargs: Any) -> None:
    select_stmt = kwargs["query"]
    outfile = kwargs["filename"]
    description = kwargs["description"]
    tee = kwargs["tee"]
    tee = bool(tee)
    append = kwargs["append"]
    append = bool(append)
    filefmt = kwargs["format"].lower()
    zipfilename = kwargs["zipfilename"]
    if zipfilename is not None:
        if outfile == "stdout":
            raise ErrInfo("error", other_msg="Cannot write stdout to a zipfile.")
        elif len(outfile) > 1 and outfile[1] == ":":
            raise ErrInfo("error", other_msg="Cannot use a drive letter for a file path within a zipfile.")
        if filefmt == "latex":
            raise ErrInfo("error", other_msg="Cannot export to the LaTeX format within a zipfile.")
        if filefmt == "feather":
            raise ErrInfo("error", other_msg="Cannot export to the feather format within a zipfile.")
        if filefmt == "parquet":
            raise ErrInfo("error", other_msg="Cannot export to the parquet format within a zipfile.")
        if filefmt == "hdf5":
            raise ErrInfo("error", other_msg="Cannot export to the HDF5 format within a zipfile.")
        if filefmt == "ods":
            raise ErrInfo("error", other_msg="Cannot export to an ODS workbook within a zipfile.")
    notype = bool(kwargs.get("notype"))
    check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False, desc=description)
    if filefmt in ("txt", "text"):
        prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("txt-and", "text-and"):
        prettyprint_query(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            and_val="AND",
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "ods":
        script_name, lno = current_script_line()
        write_query_to_ods(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            sheetname=f"Query_{lno}",
            desc=description,
        )
    elif filefmt == "json":
        write_query_to_json(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt in ("json_ts", "json_tableschema"):
        write_query_to_json_ts(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            not notype,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "values":
        write_query_to_values(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "html":
        write_query_to_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "cgi-html":
        write_query_to_cgi_html(
            select_stmt,
            _state.dbs.current(),
            outfile,
            append,
            desc=description,
            zipfile=zipfilename,
        )
    elif filefmt == "latex":
        write_query_to_latex(
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
        except ErrInfo:
            raise
        except Exception:
            raise ErrInfo("db", select_stmt, exception_msg=exception_desc())
        if filefmt == "raw":
            write_query_raw(outfile, rows, _state.dbs.current().encoding, append, zipfile=zipfilename)
        elif filefmt == "b64":
            write_query_b64(outfile, rows, append, zipfile=zipfilename)
        elif filefmt == "feather":
            write_query_to_feather(outfile, hdrs, rows)
        elif filefmt == "parquet":
            write_query_to_parquet(outfile, hdrs, rows)
        else:
            write_delimited_file(
                outfile,
                filefmt,
                hdrs,
                rows,
                _state.conf.output_encoding,
                append,
                zipfile=zipfilename,
            )
    _state.export_metadata.add(ExportRecord(select_stmt, outfile, zipfilename, description))
    return None


def x_export_query_with_template(**kwargs: Any) -> None:
    select_stmt = kwargs["query"]
    outfile = kwargs["filename"]
    template_file = kwargs["template"]
    tee = kwargs["tee"]
    tee = bool(tee)
    append = kwargs["append"]
    append = bool(append)
    zipfilename = kwargs["zipfilename"]
    check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False)
    report_query(select_stmt, _state.dbs.current(), outfile, template_file, append, zipfile=zipfilename)
    _state.export_metadata.add(ExportRecord(select_stmt, outfile, zipfilename))
    return None


def x_export_with_template(**kwargs: Any) -> None:
    schema = kwargs["schema"]
    table = kwargs["table"]
    queryname = _state.dbs.current().schema_qualified_table_name(schema, table)
    select_stmt = f"select * from {queryname};"
    outfile = kwargs["filename"]
    template_file = kwargs["template"]
    tee = kwargs["tee"]
    tee = bool(tee)
    append = kwargs["append"]
    append = bool(append)
    zipfilename = kwargs["zipfilename"]
    check_dir(outfile)
    if tee and outfile.lower() != "stdout":
        prettyprint_query(select_stmt, _state.dbs.current(), "stdout", False)
    report_query(select_stmt, _state.dbs.current(), outfile, template_file, append, zipfile=zipfilename)
    _state.export_metadata.add(ExportRecord(queryname, outfile, zipfilename))
    return None


def x_export_ods_multiple(**kwargs: Any) -> None:
    table_list = kwargs["tables"]
    outfile = kwargs["filename"]
    description = kwargs["description"]
    tee = kwargs["tee"]
    tee = bool(tee)
    append = kwargs["append"]
    append = append is not None
    check_dir(outfile)
    write_queries_to_ods(table_list, _state.dbs.current(), outfile, append, tee, desc=description)


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
        check_dir(outfile)
    if filefmt in ("txt", "text"):
        prettyprint_rowset(hdrs, rows, outfile, append, and_val="", zipfile=zipfilename)
    else:
        write_delimited_file(outfile, filefmt, hdrs, rows, _state.conf.output_encoding, append, zipfilename)


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
    import_data_table(_state.dbs.current(), schemaname, tablename, is_new, hdrs, rows)


def x_export_row_buffer(**kwargs: Any) -> None:
    rows = kwargs["rows"]
    _state.conf.export_row_buffer = int(rows)
