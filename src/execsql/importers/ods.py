from __future__ import annotations

"""
ODS spreadsheet import for execsql.

Provides :func:`ods_data` (row iterator over an ODS sheet) and
:func:`importods` (imports an ODS sheet into a database table), used by
the ``IMPORT … FORMAT ods`` metacommand.  Requires ``odfpy``
(``execsql2[formats]``).
"""

from typing import Any

from execsql.exceptions import ErrInfo
from execsql.db.base import Database
from execsql.exporters.ods import OdsFile
from execsql.importers.base import import_data_table
from execsql.utils.fileio import check_zip_decompression_ratio
from execsql.utils.spreadsheet import SheetBudget
import execsql.state as _state

__all__ = ["check_ods_archive", "importods", "ods_data"]


def check_ods_archive(filename: str) -> None:
    """Apply ODS archive limits before any reader, including sheet-name discovery."""
    budget = SheetBudget(_state.conf, filename, "<workbook>")
    check_zip_decompression_ratio(
        filename,
        max_uncompressed_mb=budget.limits["ods_max_xml_mb"],
        max_ratio=budget.limits["ods_max_compression_ratio"],
        xml_only=True,
        limit_names=("ods_max_xml_mb", "ods_max_compression_ratio"),
    )


def ods_data(
    filename: str,
    sheetname: str,
    junk_header_rows: int = 0,
) -> tuple:
    """Returns the data from the specified worksheet as a list of headers and a list of lists of rows."""
    from execsql.utils.strings import clean_words, trim_words, fold_words, dedup_words

    conf = _state.conf

    budget = SheetBudget(conf, filename, sheetname)
    check_ods_archive(filename)
    wbk = OdsFile()
    try:
        wbk.open(filename)
    except Exception as e:
        raise ErrInfo(type="cmd", other_msg=f"{filename} is not a valid OpenDocument spreadsheet.") from e
    try:
        alldata = wbk.sheet_data(sheetname, junk_header_rows, budget=budget)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo(type="cmd", other_msg=f"{sheetname} is not a worksheet in {filename}.") from e
    finally:
        wbk.close()
    if not alldata:
        raise ErrInfo(type="error", other_msg=f"The input file {filename}, sheet {sheetname} contains no data.")
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
    """Import an ODS worksheet into a new or existing database table."""
    hdrs, data = ods_data(filename, sheetname, junk_header_rows)
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
