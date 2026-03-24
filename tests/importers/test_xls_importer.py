"""
Tests for execsql.importers.xls — XLS/XLSX spreadsheet import.

Uses openpyxl to create .xlsx test fixtures, then reads them back via
xls_data / importxls.  Skipped if openpyxl is not installed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

openpyxl = pytest.importorskip("openpyxl")

import execsql.state as _state
from execsql.db.sqlite import SQLiteDatabase
from execsql.importers.xls import xls_data, importxls
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Extra conf attributes required by the importers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def importer_conf(minimal_conf):
    minimal_conf.del_empty_cols = False
    minimal_conf.create_col_hdrs = False
    minimal_conf.clean_col_hdrs = False
    minimal_conf.trim_col_hdrs = "none"
    minimal_conf.fold_col_hdrs = "no"
    minimal_conf.dedup_col_hdrs = False
    minimal_conf.import_common_cols_only = False
    minimal_conf.quote_all_text = False
    minimal_conf.scan_lines = 50
    minimal_conf.empty_rows = True
    minimal_conf.import_encoding = "utf-8"
    yield minimal_conf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_xlsx(tmp_path, sheet_name, rows, filename="test.xlsx"):
    """Write a minimal .xlsx file and return its path."""
    path = tmp_path / filename
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    wb.save(str(path))
    return str(path)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    d = SQLiteDatabase(path)
    yield d
    d.close()


# ---------------------------------------------------------------------------
# xls_data — error cases (no live file needed)
# ---------------------------------------------------------------------------


class TestXlsDataErrors:
    def test_short_filename_raises(self):
        with pytest.raises(ErrInfo):
            xls_data("ab", "Sheet1", 0)

    def test_unrecognized_extension_raises(self):
        with pytest.raises(ErrInfo):
            xls_data("myfile.ods", "Sheet1", 0)

    def test_nonexistent_xlsx_raises(self, tmp_path):
        with pytest.raises(ErrInfo):
            xls_data(str(tmp_path / "missing.xlsx"), "Sheet1", 0)


# ---------------------------------------------------------------------------
# xls_data — xlsx round-trip
# ---------------------------------------------------------------------------


class TestXlsDataXlsx:
    def test_returns_headers_and_rows(self, tmp_path):
        path = _make_xlsx(tmp_path, "Sheet1", [["id", "name"], ["1", "Alice"], ["2", "Bob"]])
        hdrs, rows = xls_data(path, "Sheet1", 0)
        assert hdrs == ["id", "name"]
        assert len(rows) == 2

    def test_single_row_is_header_only(self, tmp_path):
        path = _make_xlsx(tmp_path, "Sheet1", [["id", "name"]])
        hdrs, rows = xls_data(path, "Sheet1", 0)
        assert hdrs == ["id", "name"]
        assert rows == []

    def test_empty_sheet_raises(self, tmp_path):
        path = _make_xlsx(tmp_path, "Sheet1", [])
        with pytest.raises(ErrInfo):
            xls_data(path, "Sheet1", 0)

    def test_invalid_sheet_raises(self, tmp_path):
        path = _make_xlsx(tmp_path, "Sheet1", [["id"], ["1"]])
        with pytest.raises(ErrInfo):
            xls_data(path, "NoSuchSheet", 0)

    def test_junk_header_rows_skipped(self, tmp_path):
        path = _make_xlsx(
            tmp_path,
            "Sheet1",
            [["junk"], ["id", "name"], ["1", "Alice"]],
        )
        hdrs, rows = xls_data(path, "Sheet1", junk_header_rows=1)
        assert hdrs == ["id", "name"]
        assert len(rows) == 1

    def test_del_empty_cols(self, tmp_path, minimal_conf):
        minimal_conf.del_empty_cols = True
        path = _make_xlsx(tmp_path, "Sheet1", [["id", None, "name"], ["1", "x", "Alice"]])
        hdrs, rows = xls_data(path, "Sheet1", 0)
        assert None not in hdrs
        assert "id" in hdrs
        assert "name" in hdrs

    def test_create_col_hdrs_fills_blanks(self, tmp_path, minimal_conf):
        minimal_conf.create_col_hdrs = True
        path = _make_xlsx(tmp_path, "Sheet1", [["id", None], ["1", "v"]])
        hdrs, rows = xls_data(path, "Sheet1", 0)
        assert "Col2" in hdrs

    def test_missing_header_no_create_raises(self, tmp_path, minimal_conf):
        minimal_conf.create_col_hdrs = False
        minimal_conf.del_empty_cols = False
        path = _make_xlsx(tmp_path, "Sheet1", [["id", None], ["1", "v"]])
        with pytest.raises(ErrInfo):
            xls_data(path, "Sheet1", 0)


# ---------------------------------------------------------------------------
# importxls — xlsx integration
# ---------------------------------------------------------------------------


class TestImportXls:
    def test_creates_and_populates_table(self, tmp_path, db):
        path = _make_xlsx(tmp_path, "Sheet1", [["id", "name"], ["1", "Alice"], ["2", "Bob"]])
        importxls(
            db,
            None,
            "people",
            is_new=1,
            filename=path,
            sheetname="Sheet1",
            junk_header_rows=0,
            encoding=None,
        )
        _, rows = db.select_data("SELECT id, name FROM people ORDER BY id;")
        assert len(rows) == 2

    def test_appends_to_existing_table(self, tmp_path, db):
        db.execute("CREATE TABLE tbl (id TEXT, name TEXT);")
        db.execute("INSERT INTO tbl VALUES ('0', 'existing');")
        db.commit()
        path = _make_xlsx(tmp_path, "Sheet1", [["id", "name"], ["1", "new"]])
        importxls(
            db,
            None,
            "tbl",
            is_new=False,
            filename=path,
            sheetname="Sheet1",
            junk_header_rows=0,
            encoding=None,
        )
        _, rows = db.select_data("SELECT name FROM tbl ORDER BY id;")
        names = [r[0] for r in rows]
        assert "existing" in names
        assert "new" in names
