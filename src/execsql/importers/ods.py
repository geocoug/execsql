from __future__ import annotations

"""
ODS spreadsheet import for execsql.

Provides :func:`ods_data` (row iterator over an ODS sheet) and
:func:`importods` (imports an ODS sheet into a database table), used by
the ``IMPORT … FORMAT ods`` metacommand.  Requires ``odfpy``
(``execsql2[ods]``).
"""

from typing import Any

from execsql.exceptions import ErrInfo
from execsql.db.base import Database
from execsql.exporters.ods import OdsFile
from execsql.importers.base import import_data_table
import execsql.state as _state


def ods_data(
    filename: str,
    sheetname: str,
    junk_header_rows: int = 0,
) -> tuple:
    """Returns the data from the specified worksheet as a list of headers and a list of lists of rows."""
    from execsql.utils.strings import clean_words, trim_words, fold_words, dedup_words

    conf = _state.conf

    wbk = OdsFile()
    try:
        wbk.open(filename)
    except Exception:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a valid OpenDocument spreadsheet.")
    try:
        alldata = wbk.sheet_data(sheetname, junk_header_rows)
    except Exception:
        raise ErrInfo(type="cmd", other_msg=f"{sheetname} is not a worksheet in {filename}.")
    colhdrs = alldata[0]
    if any(x is None or len(x.strip()) == 0 for x in colhdrs):
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


def importods(
    db: Database,
    schemaname: str | None,
    tablename: str,
    is_new: Any,
    filename: str,
    sheetname: str,
    junk_header_rows: int,
) -> None:
    hdrs, data = ods_data(filename, sheetname, junk_header_rows)
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
