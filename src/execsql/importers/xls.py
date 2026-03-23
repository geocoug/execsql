from __future__ import annotations

"""
XLS and XLSX spreadsheet import for execsql.

Provides :func:`xls_data` / :func:`importxls` (``xlrd``-based ``.xls``
reader) and the XLSX equivalent using ``openpyxl``.  Used by
``IMPORT … FORMAT xls`` and ``FORMAT xlsx``.  Requires
``execsql2[excel]``.
"""

import os
from typing import Any, List, Optional

from execsql.exceptions import ErrInfo
from execsql.db.base import Database
from execsql.importers.base import import_data_table
import execsql.state as _state


def xls_data(
    filename: str,
    sheetname: str,
    junk_header_rows: int,
    encoding: Optional[str] = None,
) -> tuple:
    """Returns the data from the specified worksheet as a list of headers and a list of lists of rows."""
    from execsql.utils.strings import clean_words, trim_words, fold_words, dedup_words

    conf = _state.conf

    if len(filename) < 4:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a recognizable Excel spreadsheet name.")
    ext3 = filename[-3:].lower()
    if ext3 == "xls":
        # xlrd imported lazily
        from execsql.exporters.xls import XlsFile

        wbk = XlsFile()
    elif ext3 == "lsx":
        # openpyxl imported lazily
        from execsql.exporters.xls import XlsxFile

        wbk = XlsxFile()
    else:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a recognizable Excel spreadsheet name.")
    try:
        wbk.open(filename, encoding, read_only=True)
    except Exception:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a valid Excel spreadsheet.")
    try:
        alldata = wbk.sheet_data(sheetname, junk_header_rows)
    except Exception:
        raise ErrInfo(type="cmd", other_msg=f"Error reading worksheet {sheetname} from {filename}.")
    if len(alldata) == 0:
        raise ErrInfo(type="cmd", other_msg=f"There are no data on worksheet {sheetname} of file {filename}.")
    if ext3 == "lsx":
        wbk.close()
    if len(alldata) == 1:
        return alldata[0], []
    colhdrs = alldata[0]
    if any([x is None or (isinstance(x, str) and len(x.strip()) == 0) for x in colhdrs]):
        if conf.del_empty_cols:
            blanks = [i for i in range(len(colhdrs)) if colhdrs[i] is None or len(colhdrs[i].strip()) == 0]
            while len(blanks) > 0:
                b = blanks.pop()
                for r in range(len(alldata)):
                    del alldata[r][b]
            colhdrs = alldata[0]
        else:
            if conf.create_col_hdrs:
                for i in range(len(colhdrs)):
                    if colhdrs[i] is None or len(colhdrs[i]) == 0:
                        colhdrs[i] = f"Col{i + 1}"
            else:
                raise ErrInfo(
                    type="error",
                    other_msg=f"The input file {filename}, sheet {sheetname} has missing column headers.",
                )
    if conf.clean_col_hdrs:
        colhdrs = clean_words(colhdrs)
    if conf.trim_col_hdrs != "none":
        colhdrs = trim_words(colhdrs, conf.trim_col_hdrs)
    if conf.fold_col_hdrs != "no":
        colhdrs = fold_words(colhdrs, conf.fold_col_hdrs)
    if conf.dedup_col_hdrs:
        colhdrs = dedup_words(colhdrs)
    return colhdrs, alldata[1:]


def importxls(
    db: Database,
    schemaname: Optional[str],
    tablename: str,
    is_new: Any,
    filename: str,
    sheetname: str,
    junk_header_rows: int,
    encoding: Optional[str],
) -> None:
    hdrs, data = xls_data(filename, sheetname, junk_header_rows, encoding)
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
