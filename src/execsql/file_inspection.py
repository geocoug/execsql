"""Read-only file metadata using the same readers and inference as IMPORT."""

from __future__ import annotations

import codecs
import importlib
from contextlib import closing
from enum import Enum
from itertools import islice
from pathlib import Path
from typing import Any, cast
from collections.abc import Iterable

from execsql.exceptions import ErrInfo, ScriptExit
from execsql.models import DataTable
from execsql.state import RuntimeContext, active_context

__all__ = ["FileFormat", "inspect_file"]


class FileFormat(str, Enum):
    """Input formats understood by the built-in IMPORT readers."""

    csv = "csv"
    tsv = "tsv"
    text = "text"
    json = "json"
    jsonl = "jsonl"
    xls = "xls"
    xlsx = "xlsx"
    ods = "ods"
    parquet = "parquet"
    feather = "feather"


_EXTENSIONS = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".tab": "tsv",
    ".txt": "text",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".ods": "ods",
    ".parquet": "parquet",
    ".feather": "feather",
    ".arrow": "feather",
    ".ipc": "feather",
}
_TEXT = {"csv", "tsv", "text", "json", "jsonl"}
_DELIMITED = {"csv", "tsv", "text"}
_WORKBOOK = {"xls", "xlsx", "ods"}
_SETTINGS = (
    "import_encoding",
    "enc_err_disposition",
    "scan_lines",
    "max_int",
    "boolean_int",
    "boolean_words",
    "exact_decimals",
    "only_strings",
    "empty_strings",
    "empty_rows",
    "trim_strings",
    "replace_newlines",
    "del_empty_cols",
    "create_col_hdrs",
    "clean_col_hdrs",
    "trim_col_hdrs",
    "fold_col_hdrs",
    "dedup_col_hdrs",
)


def _columns(table: DataTable, stored: list[str] | None = None) -> list[dict[str, Any]]:
    columns = []
    for index, column in enumerate(table.cols):
        name, kind, length, _nullable, precision, scale = column.column_type()
        inferred = kind.data_type_name
        if length is not None:
            inferred += f"({length})"
        elif precision is not None and scale is not None:
            inferred += f"({precision},{scale})"
        columns.append(
            {
                "name": name,
                "inferred_type": inferred,
                "source_type": stored[index] if stored is not None else None,
                "null_count": column.nullrows,
            },
        )
    return columns


def _scan(
    result: dict[str, Any],
    headers: list[str],
    rows: Iterable[Any],
    sample_rows: int | None,
    *,
    materialized: bool,
    stored: list[str] | None = None,
) -> None:
    total = len(rows) if isinstance(rows, list) else None
    if sample_rows is None:
        table = DataTable(headers, rows)
        complete = True
    else:
        prefix = list(islice(rows, sample_rows + 1))
        complete = len(prefix) <= sample_rows
        table = DataTable(headers, prefix[:sample_rows])
    result["columns"] = _columns(table, stored)
    result["scan"] = {
        "mode": "full" if sample_rows is None else "sample",
        "row_limit": sample_rows,
        "rows_examined": table.inputrows,
        "complete": complete,
        "total_rows": table.inputrows if complete else total,
        "source_materialized": materialized,
    }


def _workbook_names(filename: str, kind: str, encoding: str | None) -> list[str]:
    if kind == "ods":
        from execsql.importers.ods import OdsFile, check_ods_archive

        check_ods_archive(filename)
        workbook: Any = OdsFile()
    else:
        from execsql.exporters.xls import XlsFile, XlsxFile
        from execsql.utils.fileio import check_zip_decompression_ratio

        if kind == "xlsx":
            check_zip_decompression_ratio(filename)
        workbook = XlsFile() if kind == "xls" else XlsxFile()
    try:
        if kind == "ods":
            workbook.open(filename)
        else:
            workbook.open(filename, encoding, read_only=True)
        if kind == "xls":
            return [sheet.name for sheet in workbook.sheetnames()]
        return list(workbook.sheetnames())
    finally:
        if kind == "xls":
            if workbook.wbk is not None:
                workbook.wbk.release_resources()
        else:
            workbook.close()


def _read(
    result: dict[str, Any],
    filename: str,
    kind: str,
    conf: Any,
    sheet: str | None,
    sample_rows: int | None,
    encoding: str | None,
    delimiter: str | None,
    quote: str | None,
    skip_rows: int,
) -> None:
    from execsql.importers.base import prepare_import_data

    enc = encoding or conf.import_encoding
    enc_source = "explicit" if encoding else "config" if conf.sources.get("import_encoding") else "default"
    if kind in _DELIMITED:
        from execsql.exporters.delimited import CsvFile

        source = CsvFile(filename, enc, junk_header_lines=skip_rows)
        try:
            if delimiter is not None:
                source.lineformat(delimiter, None if quote == "none" else quote or '"', None)
            else:
                source.evaluate_line_format()
            result.update(
                encoding={
                    "name": codecs.lookup(source.encoding).name,
                    "source": "bom" if source.bom_length else enc_source,
                },
                delimiter=source.delimiter,
                quote=source.quotechar,
                dialect_source="explicit" if delimiter is not None else "detected",
            )
            with closing(source.reader()) as rows:
                headers = source._colhdrs(rows)
                _scan(result, headers, rows, sample_rows, materialized=False)
        finally:
            source.close()
        return
    stored = None
    if kind in _WORKBOOK:
        names = _workbook_names(filename, kind, encoding)
        result["worksheets"] = names
        if sheet is None:
            return
        if sheet.isdecimal() and 1 <= int(sheet) <= len(names):
            result["sheet"] = names[int(sheet) - 1]
        if kind == "ods":
            from execsql.importers.ods import ods_data

            headers, data = ods_data(filename, sheet, skip_rows)
        else:
            from execsql.importers.xls import xls_data

            headers, data = xls_data(filename, sheet, skip_rows, encoding, file_format=kind)
            if kind == "xls" and encoding is not None:
                result["encoding"] = {"name": codecs.lookup(encoding).name, "source": "explicit"}
    elif kind in ("json", "jsonl"):
        from execsql.importers.json import json_data, json_format

        headers, data = json_data(filename, enc)
        result.update(format=json_format(filename, enc), format_source="detected")
        result["encoding"] = {"name": codecs.lookup(enc).name, "source": enc_source}
    else:
        from execsql.importers.feather import columnar_data

        frame = columnar_data(filename, kind)
        headers, data = frame.columns, [list(row) for row in frame.rows()]
        stored = [str(dtype) for dtype in frame.schema.values()]
        if conf.del_empty_cols:
            stored = [dtype for name, dtype in zip(headers, stored) if name and name.strip()]
    # Spreadsheet readers already perform their first header pass; IMPORT's
    # shared loader performs another. Keep both passes, including empty sheets.
    headers, data = prepare_import_data(headers, data)
    _scan(result, headers, data, sample_rows, materialized=True, stored=stored)


def inspect_file(
    file: str | Path,
    *,
    file_format: str | None = None,
    sheet: str | None = None,
    sample_rows: int | None = None,
    encoding: str | None = None,
    delimiter: str | None = None,
    quote: str | None = None,
    skip_rows: int = 0,
    config_file: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect an importable local file without connecting, loading or writing.

    Full scans use IMPORT's inference and configuration. Samples are provisional;
    eager readers can still materialize the full source. Workbooks without a sheet
    selector list worksheets without inferring columns. See the file reference.
    """
    from execsql.api import _LibraryConfig
    from execsql.cli.run import _tool_config
    from execsql.utils.spreadsheet import INPUT_LIMIT_DEFAULTS

    if not isinstance(file, (str, Path)):
        raise ValueError("file must be a local path.")
    for name, value in (
        ("file_format", file_format),
        ("sheet", sheet),
        ("encoding", encoding),
        ("delimiter", delimiter),
        ("quote", quote),
    ):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} must be text.")
    filename = str(file)
    if not filename or "\x00" in filename:
        raise ValueError("file must be a nonempty path without NUL characters.")
    if sample_rows is not None and (type(sample_rows) is not int or sample_rows < 1):
        raise ValueError("sample_rows must be a positive integer.")
    if type(skip_rows) is not int or skip_rows < 0:
        raise ValueError("skip_rows must be a non-negative integer.")
    if file_format is not None and file_format not in {item.value for item in FileFormat}:
        raise ValueError("Unsupported file_format.")
    kind = file_format or _EXTENSIONS.get(Path(filename).suffix.lower())
    if encoding is not None:
        try:
            codecs.lookup(encoding)
        except LookupError as exc:
            raise ValueError("Unknown encoding.") from exc
    if sheet is not None and (not sheet or "\x00" in sheet or kind not in _WORKBOOK):
        raise ValueError("sheet requires a nonempty worksheet selector and a workbook format.")
    if encoding is not None and kind not in _TEXT | {"xls"}:
        raise ValueError("encoding applies only to text and legacy XLS files.")
    if delimiter is not None:
        delimiter = {"tab": "\t", "us": "\x1f", "unitsep": "\x1f", "space": " "}.get(delimiter.lower(), delimiter)
        if kind not in _DELIMITED or len(delimiter) != 1 or delimiter in "\r\n\x00":
            raise ValueError("delimiter requires delimited text and one non-newline character (or TAB/US/SPACE).")
    if quote is not None and (delimiter is None or (quote != "none" and (len(quote) != 1 or quote in "\r\n\x00"))):
        raise ValueError("quote requires delimiter and one character, or 'none'.")
    if quote is not None and quote == delimiter:
        raise ValueError("quote and delimiter must differ.")
    if skip_rows and kind not in _WORKBOOK | _DELIMITED:
        raise ValueError("skip_rows applies only to delimited text and worksheets.")
    result: dict[str, Any] = {
        "schema_version": 1,
        "success": False,
        "file": filename,
        "format": "delimited" if kind in _DELIMITED else kind,
        "format_source": "explicit" if file_format else "extension",
        "encoding": None,
        "delimiter": None,
        "quote": None,
        "dialect_source": None,
        "sheet": sheet,
        "skip_rows": skip_rows,
        "worksheets": None,
        "scan": None,
        "columns": [],
        "settings": {},
        "config_files": [],
        "error": None,
    }
    ctx = RuntimeContext()
    ctx.conf = cast(Any, _LibraryConfig())
    phase = "file"
    with active_context(ctx):
        try:
            if not Path(filename).is_file():
                raise FileNotFoundError("Input is not an existing regular file.")
            if kind is None:
                result["error"] = {"code": "unsupported_format", "message": "Unknown file extension; supply --format."}
                return result
            phase = "configuration"
            if config_file is not None and not Path(config_file).is_file():
                raise FileNotFoundError("Configuration file does not exist.")
            conf = _tool_config(str(config_file) if config_file is not None else None)
            ctx.conf = conf
            result["settings"] = {name: getattr(conf, name) for name in (*_SETTINGS, *INPUT_LIMIT_DEFAULTS)}
            result["config_files"] = list(conf.files_read)
            phase = "dependency"
            dependencies = {
                "xls": ["xlrd"],
                "xlsx": ["openpyxl"],
                "ods": ["defusedxml", "odf"],
                "parquet": ["polars"],
                "feather": ["polars"],
            }.get(kind, [])
            for dependency in dependencies:
                importlib.import_module(dependency)
            phase = "read"
            _read(result, filename, kind, conf, sheet, sample_rows, encoding, delimiter, quote, skip_rows)
            result["success"] = True
        except (Exception, ScriptExit) as exc:
            if phase == "dependency":
                message = "Install execsql2[formats] with its working optional readers to inspect this format."
            elif isinstance(exc, ErrInfo):
                message = exc.errmsg()
            elif isinstance(exc, ScriptExit):
                message = "File reader halted."
            else:
                message = (
                    str(exc)
                    if phase in ("file", "configuration")
                    else "Cannot read file; check its format and parser settings."
                )
            result["columns"], result["scan"] = [], None
            result["error"] = {"code": f"{phase}_error", "message": message}
    return result
