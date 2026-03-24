"""
Tests for execsql.importers.ods — ODS spreadsheet import.

Uses OdsFile (from exporters.ods) to write test fixtures, then reads them
back via ods_data / importods.  Skipped if odfpy is not installed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("of")

import execsql.state as _state
from execsql.db.sqlite import SQLiteDatabase
from execsql.exporters.ods import OdsFile
from execsql.importers.ods import ods_data, importods
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


def _make_ods(tmp_path, sheet_name, rows):
    """Write a minimal ODS file and return its path."""
    path = str(tmp_path / "test.ods")
    wbk = OdsFile()
    wbk.open(path)
    tbl = wbk.new_sheet(sheet_name)
    for i, row in enumerate(rows):
        wbk.add_row_to_sheet(row, tbl, header=(i == 0))
    wbk.add_sheet(tbl)
    wbk.save_close()
    return path


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    d = SQLiteDatabase(path)
    yield d
    d.close()


# ---------------------------------------------------------------------------
# ods_data
# ---------------------------------------------------------------------------


class TestOdsData:
    def test_returns_headers_and_rows(self, tmp_path):
        path = _make_ods(tmp_path, "Sheet1", [["id", "name"], ["1", "Alice"], ["2", "Bob"]])
        hdrs, rows = ods_data(path, "Sheet1")
        assert hdrs == ["id", "name"]
        assert len(rows) == 2

    def test_row_values_correct(self, tmp_path):
        path = _make_ods(tmp_path, "Sheet1", [["x"], ["42"], ["99"]])
        hdrs, rows = ods_data(path, "Sheet1")
        assert hdrs == ["x"]
        assert len(rows) == 2

    def test_invalid_file_raises_errinfo(self, tmp_path):
        bad = str(tmp_path / "not_an_ods.txt")
        with open(bad, "w") as f:
            f.write("not a spreadsheet")
        with pytest.raises(ErrInfo):
            ods_data(bad, "Sheet1")

    def test_invalid_sheet_raises_errinfo(self, tmp_path):
        path = _make_ods(tmp_path, "Sheet1", [["id"], ["1"]])
        with pytest.raises(ErrInfo):
            ods_data(path, "NoSuchSheet")

    def test_junk_header_rows_skipped(self, tmp_path):
        # 1 junk row before the header
        path = _make_ods(
            tmp_path,
            "Sheet1",
            [["junk row"], ["id", "name"], ["1", "Alice"]],
        )
        hdrs, rows = ods_data(path, "Sheet1", junk_header_rows=1)
        assert hdrs == ["id", "name"]
        assert len(rows) == 1

    def test_del_empty_cols(self, tmp_path, minimal_conf):
        minimal_conf.del_empty_cols = True
        path = _make_ods(tmp_path, "Sheet1", [["id", "", "name"], ["1", "x", "Alice"]])
        hdrs, rows = ods_data(path, "Sheet1")
        assert "" not in hdrs
        assert "id" in hdrs
        assert "name" in hdrs

    def test_create_col_hdrs_fills_blanks(self, tmp_path, minimal_conf):
        minimal_conf.create_col_hdrs = True
        path = _make_ods(tmp_path, "Sheet1", [["id", ""], ["1", "v"]])
        hdrs, rows = ods_data(path, "Sheet1")
        assert "Col2" in hdrs

    def test_missing_headers_no_create_raises(self, tmp_path, minimal_conf):
        minimal_conf.create_col_hdrs = False
        minimal_conf.del_empty_cols = False
        path = _make_ods(tmp_path, "Sheet1", [["id", ""], ["1", "v"]])
        with pytest.raises(ErrInfo):
            ods_data(path, "Sheet1")


# ---------------------------------------------------------------------------
# importods
# ---------------------------------------------------------------------------


class TestImportOds:
    def test_creates_and_populates_table(self, tmp_path, db):
        path = _make_ods(tmp_path, "Sheet1", [["id", "name"], ["1", "Alice"], ["2", "Bob"]])
        importods(db, None, "people", is_new=1, filename=path, sheetname="Sheet1", junk_header_rows=0)
        _, rows = db.select_data("SELECT id, name FROM people ORDER BY id;")
        assert len(rows) == 2

    def test_appends_to_existing_table(self, tmp_path, db):
        db.execute("CREATE TABLE tbl (id TEXT, name TEXT);")
        db.execute("INSERT INTO tbl VALUES ('0', 'existing');")
        db.commit()
        path = _make_ods(tmp_path, "Sheet1", [["id", "name"], ["1", "new"]])
        importods(db, None, "tbl", is_new=False, filename=path, sheetname="Sheet1", junk_header_rows=0)
        _, rows = db.select_data("SELECT name FROM tbl ORDER BY id;")
        names = [r[0] for r in rows]
        assert "existing" in names
        assert "new" in names
