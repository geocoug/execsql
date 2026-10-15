"""IMPORT from ODS reads each cell's stored value, one value per column.

The reader used to take each cell's displayed text, one entry per paragraph:
a ``#`` cell was dropped and the rest of the row shifted left, a two-line
cell became two columns, a cell comment became a value, ``0`` came back
NULL, and a number formatted to two places lost its other digits.

``tests/data/ods/libreoffice.ods`` was saved by LibreOffice from
``libreoffice.fods`` beside it (``soffice --headless --convert-to ods
libreoffice.fods``), so the reader is checked against a real spreadsheet
application's output, not only against execsql's own writer.
"""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("odf.opendocument", reason="requires odfpy (execsql2[formats])")

from odf.table import CoveredTableCell, TableCell, TableRow  # noqa: E402
from odf.text import LineBreak, P, S, Tab  # noqa: E402

from execsql import run  # noqa: E402
from execsql.exceptions import ErrInfo  # noqa: E402
from execsql.exporters.ods import OdsFile  # noqa: E402
from execsql.importers.ods import ods_data  # noqa: E402

LIBREOFFICE_ODS = Path(__file__).parent.parent / "data" / "ods" / "libreoffice.ods"


def _write(path, rows):
    wbk = OdsFile()
    wbk.open(str(path))
    tbl = wbk.new_sheet("s")
    for row in rows:
        wbk.add_row_to_sheet(row, tbl)
    wbk.add_sheet(tbl)
    wbk.save_close()


def _read(path, sheet="s"):
    wbk = OdsFile()
    wbk.open(str(path))
    return wbk.sheet_data(sheet)


def _write_raw(path, *rows):
    """Write a sheet from hand-built ``<table:table-row>`` elements."""
    wbk = OdsFile()
    wbk.open(str(path))
    tbl = wbk.new_sheet("s")
    for row in rows:
        tbl.addElement(row)
    wbk.add_sheet(tbl)
    wbk.save_close()


def _row(*cells):
    tr = TableRow()
    for cell in cells:
        tr.addElement(cell)
    return tr


def _text_cell(*paragraphs, **attrs):
    tc = TableCell(**attrs)
    for p in paragraphs:
        tc.addElement(P(text=p) if isinstance(p, str) else p)
    return tc


class TestLibreOfficeFile:
    def test_every_cell_is_read_as_its_value(self):
        assert _read(LIBREOFFICE_ODS, "data") == [
            ["id", "rate", "amount", "sampled", "note", "flag", "site", "area"],
            # 12.50% → 0.125, "1,234.57" → its stored value, 06/02/2024 → ISO,
            # a "#" cell kept, a horizontal merge repeated across its columns.
            ["1", "0.125", "1234.5678", "2024-02-06", "#", "true", "merged", "merged"],
            # 0 is 0, the cell comment is not a value, two paragraphs are one
            # value, and the vertical merge's start sits in "site" ...
            ["2", "0", "0", None, "two   spaces\nsecond line", "false", "tall", "x"],
            # ... so the covered cell below it keeps "y" in "area".
            ["3", None, None, None, None, None, None, "y"],
            # Two empty rows LibreOffice wrote as one repeated row: rows of
            # NULLs, which EMPTY_ROWS keeps or drops.
            [None] * 8,
            [None] * 8,
            ["4", "same", None, None, None, None, None, None],
            ["4", "same", None, None, None, None, None, None],
        ]

    def test_imports_into_a_table(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        db = tmp_path / "t.db"
        sqlite3.connect(db).close()
        script = f"-- !x! IMPORT TO NEW lo FROM {LIBREOFFICE_ODS} SHEET data\n"
        result = run(sql=script, dsn=f"sqlite:///{db}")
        assert result.success, result.errors
        con = sqlite3.connect(db)
        rows = con.execute("select id, rate, amount, note, site, area from lo where id <= 3 order by id").fetchall()
        assert rows == [
            # "rate" is text: the last rows hold the word "same" in it.
            (1, "0.125", 1234.5678, "#", "merged", "merged"),
            (2, "0", 0, "two   spaces\nsecond line", "tall", "x"),
            (3, None, None, None, None, "y"),
        ]


class TestWriterRoundTrip:
    def test_values_execsql_writes_read_back_unchanged(self, tmp_path):
        path = tmp_path / "w.ods"
        _write(
            path,
            [
                ["#", "two\nlines", 0, 0.0, False, True, None, "after"],
                [datetime.date(2024, 2, 6), datetime.time(13, 5, 9, 500000), 1.5, "", None, None, None, "z"],
            ],
        )
        assert _read(path) == [
            ["#", "two\nlines", "0", "0.0", "false", "true", None, "after"],
            ["2024-02-06", "13:05:09.5", "1.5", None, None, None, None, "z"],
        ]

    def test_script_round_trip_returns_the_source_rows(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        db = tmp_path / "t.db"
        rows = [
            (1, 1.5, "a", "x", "A"),
            (2, 1234567.891, "#", None, "B"),
            (3, 0.0, "two\nlines", "y", "C"),
            (0, 0.125, None, None, "D"),
        ]
        con = sqlite3.connect(db)
        con.execute("create table src (id integer, amt real, txt text, z text, after text)")
        con.executemany("insert into src values (?, ?, ?, ?, ?)", rows)
        con.commit()
        con.close()
        script = "-- !x! EXPORT src TO rt.ods AS ODS\n-- !x! IMPORT TO NEW back FROM rt.ods SHEET src\n"
        result = run(sql=script, dsn=f"sqlite:///{db}")
        assert result.success, result.errors
        con = sqlite3.connect(db)
        assert con.execute("select * from back").fetchall() == rows

    def test_files_from_earlier_versions_still_read(self, tmp_path):
        # execsql2 2.30 and earlier wrote a boolean as office:value="1", a
        # NULL as office:value="None", and 0 with an empty paragraph.
        path = tmp_path / "old.ods"
        _write_raw(
            path,
            _row(
                _text_cell("True", valuetype="boolean", value="1"),
                _text_cell("", valuetype="boolean", value="0"),
                TableCell(value="None"),
                _text_cell("", valuetype="float", value="0.0"),
                _text_cell("z", valuetype="string", stringvalue="z"),
            ),
        )
        assert _read(path) == [["true", "false", None, "0.0", "z"]]


class TestCellText:
    def test_space_tab_and_line_break_elements(self, tmp_path):
        p = P(text="a")
        p.addElement(S(c=3))
        p.addText("b")
        p.addElement(Tab())
        p.addText("c")
        p.addElement(LineBreak())
        p.addText("d")
        path = tmp_path / "t.ods"
        _write_raw(path, _row(_text_cell(p, valuetype="string")))
        assert _read(path) == [["a   b\tc\nd"]]

    def test_covered_cell_from_a_row_above_keeps_its_column(self, tmp_path):
        path = tmp_path / "t.ods"
        _write_raw(
            path,
            _row(_text_cell("top", valuetype="string", numberrowsspanned=2), _text_cell("a", valuetype="string")),
            _row(CoveredTableCell(), _text_cell("b", valuetype="string")),
        )
        assert _read(path) == [["top", "a"], [None, "b"]]

    def test_repeated_cells_and_rows_are_expanded(self, tmp_path):
        path = tmp_path / "t.ods"
        repeated = _row(_text_cell("v", valuetype="string", numbercolumnsrepeated=2), TableCell(), _text_cell("w"))
        repeated.setAttribute("numberrowsrepeated", 2)
        _write_raw(path, repeated)
        assert _read(path) == [["v", "v", None, "w"], ["v", "v", None, "w"]]

    def test_trailing_filler_is_dropped(self, tmp_path):
        # Spreadsheets pad rows to the sheet width and pad the sheet with
        # empty rows; neither is data, and expanding them would cost
        # millions of cells.
        path = tmp_path / "t.ods"
        filler_row = _row(TableCell(numbercolumnsrepeated=16384))
        filler_row.setAttribute("numberrowsrepeated", 1048575)
        _write_raw(path, _row(_text_cell("v"), TableCell(numbercolumnsrepeated=16383)), filler_row)
        assert _read(path) == [["v"]]


def test_empty_sheet_is_an_error(tmp_path, minimal_conf):
    minimal_conf.del_empty_cols = False
    path = tmp_path / "t.ods"
    _write_raw(path, _row(TableCell(numbercolumnsrepeated=8)))
    with pytest.raises(ErrInfo, match="contains no data"):
        ods_data(str(path), "s")
