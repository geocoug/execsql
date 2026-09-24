"""
XLSX export round trips, driven by a real database.

Read back with openpyxl, checking cell *types* and not only cell text.  A
number written as a string looks identical in a screenshot and is useless in a
formula, a sort, or a chart — which is most of why anyone exports to Excel.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from .conftest import HEADERS, TABLE_NAME

openpyxl = pytest.importorskip("openpyxl", reason="requires openpyxl (execsql2[excel])")

from execsql.exporters.xlsx import write_query_to_xlsx  # noqa: E402


#: The workbook opens with an inventory sheet; the query result is the next one.
INVENTORY_SHEET = "Datasheets"


def _export(db, outfile, sheetname="Sheet1"):
    write_query_to_xlsx(f"select * from {TABLE_NAME} order by id;", db, str(outfile))
    wb = openpyxl.load_workbook(str(outfile))
    assert wb.sheetnames[0] == INVENTORY_SHEET, wb.sheetnames
    return wb[sheetname]


def _cell(ws, row, column_name):
    """1-based cell for a data row (1 = first data row, under the header)."""
    return ws.cell(row=row + 1, column=HEADERS.index(column_name) + 1)


class TestXlsxRoundTrip:
    def test_header_row_is_the_column_names(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        assert [c.value for c in ws[1]] == HEADERS

    def test_row_count(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        assert ws.max_row == 3, "header + two data rows"

    def test_null_cells_are_empty_not_the_string_none(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        values = [_cell(ws, 2, name).value for name in HEADERS if name != "id"]
        assert set(values) == {None}, f"NULL leaked into a cell: {values}"

    def test_unicode_survives(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        assert _cell(ws, 1, "t_unicode").value == "café — naïve ± 30° ⚡"

    def test_awkward_text_survives_verbatim(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        assert _cell(ws, 1, "t_awkward").value == 'has "quotes", a comma, a\ttab and a\nnewline'

    def test_integer_is_a_number_cell(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        cell = _cell(ws, 1, "n_int")
        assert cell.value == -42
        assert cell.data_type == "n", "integers must be numeric cells, not text"

    def test_float_is_a_number_cell(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        cell = _cell(ws, 1, "n_float")
        assert cell.value == 2.5
        assert cell.data_type == "n"

    def test_numeric_is_a_number_cell(self, export_db, tmp_path):
        """A ``numeric`` column must arrive in Excel as a number.

        PostgreSQL, MySQL and DuckDB return ``Decimal`` for ``numeric(12,3)``.
        openpyxl stores Decimal natively as a numeric cell, so there is nothing
        forcing it to text — and a measurement column that lands as text cannot
        be summed, sorted, or charted.
        """
        ws = _export(export_db, tmp_path / "out.xlsx")
        cell = _cell(ws, 1, "n_dec")
        assert cell.data_type == "n", f"numeric exported as {cell.data_type!r}: {cell.value!r}"
        assert Decimal(str(cell.value)) == Decimal("1234.567")

    def test_date_is_a_date_cell_when_the_driver_returns_one(self, export_db, tmp_path):
        """SQLite hands back a string; every other Tier 1 driver hands back a date."""
        _, rows = export_db.select_data(f"select * from {TABLE_NAME} order by id;")
        driver_value = rows[0][HEADERS.index("d_date")]
        ws = _export(export_db, tmp_path / "out.xlsx")
        cell = _cell(ws, 1, "d_date")
        if isinstance(driver_value, datetime.date):
            assert isinstance(cell.value, (datetime.date, datetime.datetime))
        else:
            assert str(cell.value).startswith("2026-09-24")

    def test_timestamp_keeps_its_time(self, export_db, tmp_path):
        ws = _export(export_db, tmp_path / "out.xlsx")
        value = _cell(ws, 1, "d_stamp").value
        if isinstance(value, datetime.datetime):
            assert (value.hour, value.minute, value.second) == (13, 45, 56)
        else:
            assert "13:45:56" in str(value)
