from __future__ import annotations

"""
ODS (OpenDocument Spreadsheet) export for execsql.

Provides :func:`write_query_to_ods` (single-sheet export),
:func:`write_queries_to_ods` (multi-sheet export), and :class:`OdsFile`
(wrapper around ``odfpy`` for writing ``.ods`` files).  Requires the
``odfpy`` package (``execsql2[ods]``).
"""

import datetime
import getpass
import os
from typing import Any

import execsql.state as _state
from execsql.exceptions import OdsFileError
from execsql.exceptions import ErrInfo
from execsql.script import current_script_line
from execsql.utils.errors import exception_desc, fatal_error
from execsql.utils.fileio import filewriter_close
from execsql.utils.strings import unquoted


class OdsFile:
    def __repr__(self) -> str:
        return "OdsFile()"

    def __init__(self) -> None:
        global of
        try:
            import of as of
            import of.opendocument
            import of.table
            import of.text
            import of.number
            import of.style
        except ImportError:
            fatal_error("The odfpy library is needed to create OpenDocument spreadsheets.")
        self.filename = None
        self.wbk = None
        self.cell_style_names = []

    def open(self, filename: str) -> None:
        self.filename = filename
        if os.path.isfile(filename):
            self.wbk = of.opendocument.load(filename)
            # Get a list of all cell style names used, so as not to re-define them.
            for sty in self.wbk.automaticstyles.childNodes:
                try:
                    fam = sty.getAttribute("family")
                    if fam == "table-cell":
                        name = sty.getAttribute("name")
                        if name not in self.cell_style_names:
                            self.cell_style_names.append(name)
                except Exception:
                    pass
        else:
            self.wbk = of.opendocument.OpenDocumentSpreadsheet()

    def define_body_style(self) -> None:
        st_name = "body"
        if st_name not in self.cell_style_names:
            body_style = of.style.Style(name=st_name, family="table-cell")
            body_style.addElement(of.style.TableCellProperties(attributes={"verticalalign": "top"}))
            self.wbk.styles.addElement(body_style)
            self.cell_style_names.append(st_name)

    def define_header_style(self) -> None:
        st_name = "header"
        if st_name not in self.cell_style_names:
            header_style = of.style.Style(name=st_name, family="table-cell")
            header_style.addElement(
                of.style.TableCellProperties(
                    attributes={
                        "borderbottom": "1pt solid #000000",
                        "verticalalign": "bottom",
                    },
                ),
            )
            self.wbk.styles.addElement(header_style)
            self.cell_style_names.append(st_name)

    def define_iso_datetime_style(self) -> None:
        st_name = "iso_datetime"
        if st_name not in self.cell_style_names:
            dt_style = of.number.DateStyle(name="iso-datetime")
            dt_style.addElement(of.number.Year(style="long"))
            dt_style.addElement(of.number.Text(text="-"))
            dt_style.addElement(of.number.Month(style="long"))
            dt_style.addElement(of.number.Text(text="-"))
            dt_style.addElement(of.number.Day(style="long"))
            dt_style.addElement(of.number.Text(text="T"))
            dt_style.addElement(of.number.Hours(style="long"))
            dt_style.addElement(of.number.Text(text=":"))
            dt_style.addElement(of.number.Minutes(style="long"))
            dt_style.addElement(of.number.Text(text=":"))
            dt_style.addElement(of.number.Seconds(style="long", decimalplaces="3"))
            self.wbk.styles.addElement(dt_style)
            self.define_body_style()
            dts = of.style.Style(
                name=st_name,
                datastylename="iso-datetime",
                parentstylename="body",
                family="table-cell",
            )
            self.wbk.automaticstyles.addElement(dts)
            self.cell_style_names.append(st_name)

    def define_iso_date_style(self) -> None:
        st_name = "iso_date"
        if st_name not in self.cell_style_names:
            dt_style = of.number.DateStyle(name="iso-date")
            dt_style.addElement(of.number.Year(style="long"))
            dt_style.addElement(of.number.Text(text="-"))
            dt_style.addElement(of.number.Month(style="long"))
            dt_style.addElement(of.number.Text(text="-"))
            dt_style.addElement(of.number.Day(style="long"))
            self.wbk.styles.addElement(dt_style)
            self.define_body_style()
            dts = of.style.Style(name=st_name, datastylename="iso-date", parentstylename="body", family="table-cell")
            self.wbk.automaticstyles.addElement(dts)
            self.cell_style_names.append(st_name)

    def sheetnames(self) -> list[str]:
        # Returns a list of the worksheet names in the specified ODS spreadsheet.
        return [sheet.getAttribute("name") for sheet in self.wbk.spreadsheet.getElementsByType(of.table.Table)]

    def sheet_named(self, sheetname: Any) -> Any:
        # Return the sheet with the matching name.  If the name is actually an integer,
        # return that sheet number.
        if isinstance(sheetname, int):
            sheet_no = sheetname
        else:
            try:
                sheet_no = int(sheetname)
                if sheet_no < 1:
                    sheet_no = None
            except (ValueError, TypeError):
                sheet_no = None
        if sheet_no is not None:
            for i, sheet in enumerate(self.wbk.spreadsheet.getElementsByType(of.table.Table)):
                if i + 1 == sheet_no:
                    return sheet
            else:
                sheet_no = None
        if sheet_no is None:
            for sheet in self.wbk.spreadsheet.getElementsByType(of.table.Table):
                if sheet.getAttribute("name").lower() == sheetname.lower():
                    return sheet
        return None

    def sheet_data(self, sheetname: Any, junk_header_rows: int = 0) -> list:
        sheet = self.sheet_named(sheetname)
        if not sheet:
            raise OdsFileError(f"There is no sheet named {sheetname}")

        def row_data(sheetrow):
            # Adapted from http://www.marco83.com/work/wp-content/uploads/2011/11/odf-to-array.py
            cells = sheetrow.getElementsByType(of.table.TableCell)
            rowdata = []
            for cell in cells:
                p_content = []
                repeat = cell.getAttribute("numbercolumnsrepeated")
                if not repeat:
                    repeat = 1
                    spanned = int(cell.getAttribute("numbercolumnsspanned") or 0)
                    if spanned > 1:
                        repeat = spanned
                ps = cell.getElementsByType(of.text.P)
                if len(ps) == 0:
                    for _rr in range(int(repeat)):
                        p_content.append(None)
                else:
                    for p in ps:
                        pval = str(p)
                        if len(pval) == 0:
                            for _rr in range(int(repeat)):
                                p_content.append(None)
                        else:
                            for _rr in range(int(repeat)):
                                p_content.append(pval)
                if len(p_content) == 0:
                    for _rr in range(int(repeat)):
                        rowdata.append(None)
                elif p_content[0] != "#":
                    rowdata.extend(p_content)
            return rowdata

        rows = sheet.getElementsByType(of.table.TableRow)
        if junk_header_rows > 0:
            rows = rows[junk_header_rows:]
        return [row_data(r) for r in rows]

    def new_sheet(self, sheetname: str) -> Any:
        # Returns a sheet (a named Table) that has not yet been added to the workbook
        return of.table.Table(name=sheetname)

    def add_row_to_sheet(self, datarow: Any, of_table: Any, header: bool = False) -> None:
        if header:
            self.define_header_style()
            style_name = "header"
        else:
            self.define_body_style()
            style_name = "body"
        tr = of.table.TableRow()
        of_table.addElement(tr)
        for item in datarow:
            if isinstance(item, bool):
                # Booleans must be evaluated before numbers.
                tc = of.table.TableCell(valuetype="boolean", value=1 if item else 0, stylename=style_name)
            elif isinstance(item, (float, int)):
                tc = of.table.TableCell(valuetype="float", value=item, stylename=style_name)
            elif isinstance(item, datetime.datetime):
                self.define_iso_datetime_style()
                tc = of.table.TableCell(
                    valuetype="date",
                    datevalue=item.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                    stylename="iso_datetime",
                )
            elif isinstance(item, datetime.date):
                self.define_iso_date_style()
                tc = of.table.TableCell(valuetype="date", datevalue=item.strftime("%Y-%m-%d"), stylename="iso_date")
            elif isinstance(item, datetime.time):
                self.define_iso_datetime_style()
                timeval = datetime.datetime(
                    1899,
                    12,
                    30,
                    item.hour,
                    item.minute,
                    item.second,
                    item.microsecond,
                    item.tzinfo,
                )
                tc = of.table.TableCell(timevalue=timeval.strftime("PT%HH%MM%S.%fS"), stylename="iso_datetime")
                tc.addElement(of.text.P(text=timeval.strftime("%H:%M:%S.%f")))
            elif isinstance(item, str):
                item = item.replace("\n", " ").replace("\r", " ")
                tc = of.table.TableCell(valuetype="string", stringvalue=item, stylename=style_name)
            else:
                tc = of.table.TableCell(value=item, stylename=style_name)
            if item is not None:
                tc.addElement(of.text.P(text=item))
            tr.addElement(tc)

    def add_sheet(self, of_table: Any) -> None:
        self.wbk.spreadsheet.addElement(of_table)

    def save_close(self) -> None:
        with open(self.filename, "wb") as ofile:
            self.wbk.write(ofile)
        self.filename = None
        self.wbk = None

    def close(self) -> None:
        self.filename = None
        self.wbk = None


def export_ods(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool = False,
    querytext: str | None = None,
    sheetname: str | None = None,
    desc: str | None = None,
) -> None:
    # If not given, determine the worksheet name to use.  The pattern is "Sheetx", where x is
    # the first integer for which there is not already a sheet name.
    if append and os.path.isfile(outfile):
        wbk = OdsFile()
        wbk.open(outfile)
        sheet_names = wbk.sheetnames()
        name = sheetname or "Sheet"
        sheet_name = name
        sheet_no = 1
        while True:
            if sheet_name not in sheet_names:
                break
            sheet_no += 1
            sheet_name = f"{name}{sheet_no}"
        wbk.close()
    else:
        sheet_name = sheetname or "Sheet1"
        if os.path.isfile(outfile):
            filewriter_close(outfile)
            os.unlink(outfile)
    wbk = OdsFile()
    wbk.open(outfile)
    # Add a "Datasheets" inventory sheet if it doesn't exist.
    datasheet_name = "Datasheets"
    if datasheet_name not in wbk.sheetnames():
        inventory_sheet = wbk.new_sheet(datasheet_name)
        wbk.add_row_to_sheet(
            ("datasheet_name", "created_on", "created_by", "description", "source"),
            inventory_sheet,
            header=True,
        )
        wbk.add_sheet(inventory_sheet)
    # Add the data to a new sheet.
    tbl = wbk.new_sheet(sheet_name)
    wbk.add_row_to_sheet(hdrs, tbl, header=True)
    for row in rows:
        wbk.add_row_to_sheet(row, tbl)
    # Add sheet to workbook
    wbk.add_sheet(tbl)
    # Add information to the "Datasheets" sheet.
    datasheetlist = wbk.sheet_named(datasheet_name)
    if datasheetlist:
        script, lno = current_script_line()
        if querytext:
            src = f"{querytext} with database {_state.dbs.current().name()}, with script {os.path.abspath(script)}, line {lno}"
        else:
            src = f"From database {_state.dbs.current().name()}, with script {os.path.abspath(script)}, line {lno}"
        wbk.add_row_to_sheet(
            (
                sheet_name,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                getpass.getuser(),
                desc,
                src,
            ),
            datasheetlist,
        )
    # Save and close the workbook.
    wbk.save_close()


def write_query_to_ods(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    sheetname: str | None = None,
    desc: str | None = None,
) -> None:
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc())
    export_ods(outfile, hdrs, rows, append, select_stmt, sheetname, desc)


def write_queries_to_ods(
    table_list: str,
    db: Any,
    outfile: str,
    append: bool = False,
    tee: bool = False,
    desc: str | None = None,
) -> None:
    from execsql.exporters.pretty import prettyprint_query
    from execsql.exporters.base import ExportRecord

    tables = [t.strip() for t in table_list.split(",")]
    if desc is not None:
        descriptions = [d.strip() for d in desc.split(",")]
        one_desc = len(descriptions) != len(tables)
    if os.path.isfile(outfile) and not append:
        filewriter_close(outfile)
        os.unlink(outfile)
    wbk = OdsFile()
    wbk.open(outfile)
    # Add a "Datasheets" inventory sheet if it doesn't exist.
    inventory_name = "Datasheets"
    if inventory_name not in wbk.sheetnames():
        inventory_sheet = wbk.new_sheet(inventory_name)
        wbk.add_row_to_sheet(
            ("datasheet_name", "created_on", "created_by", "description", "source"),
            inventory_sheet,
            header=True,
        )
        wbk.add_sheet(inventory_sheet)
    for i, t in enumerate(tables):
        if "." in t:
            st = t.split(".")
            if len(st) != 2:
                raise ErrInfo("cmd", other_msg=f"Unrecognized table specification in <{t}>")
            if len(st) == 1:
                tblname = unquoted(st[0])
            else:
                tblname = unquoted(st[1])
        else:
            tblname = unquoted(t)
        # Get next sheet number for sheet name
        sheet_names = wbk.sheetnames()
        sheet_name = tblname
        sheet_no = 1
        while True:
            if sheet_name not in sheet_names:
                break
            sheet_name = f"{tblname}_{sheet_no}"
            sheet_no += 1
        # Get the data
        select_stmt = f"select * from {t};"
        try:
            hdrs, rows = db.select_rowsource(select_stmt)
        except ErrInfo:
            raise
        except Exception:
            raise ErrInfo("db", select_stmt, exception_msg=exception_desc())
        # Add the data to a new sheet.
        tbl = wbk.new_sheet(sheet_name)
        wbk.add_row_to_sheet(hdrs, tbl, header=True)
        for row in rows:
            wbk.add_row_to_sheet(row, tbl)
        # Add sheet to workbook
        wbk.add_sheet(tbl)
        # Add information to the "Datasheets" sheet.
        if desc is None:
            d = None
        else:
            if one_desc:
                d = desc
            else:
                d = descriptions[i]
        datasheetlist = wbk.sheet_named(inventory_name)
        if datasheetlist:
            script, lno = current_script_line()
            src = f"From database {_state.dbs.current().name()}, with script {os.path.abspath(script)}, line {lno}"
            wbk.add_row_to_sheet(
                (
                    sheet_name,
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    getpass.getuser(),
                    d,
                    src,
                ),
                datasheetlist,
            )
        if tee and outfile.lower() != "stdout":
            prettyprint_query(select_stmt, db, "stdout", False, desc=d)
        _state.export_metadata.add(ExportRecord(queryname=select_stmt, outfile=outfile, zipfile=None, description=d))
        sheet_no += 1
    # Save and close the workbook.
    wbk.save_close()
