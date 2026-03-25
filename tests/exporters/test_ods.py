"""
Tests for execsql.exporters.ods — ODS (OpenDocument Spreadsheet) export.

Tests focus on the OdsFile class (create, read, round-trip data).
The higher-level export_ods and write_query_to_ods functions require
runtime state (_state.dbs, _state.current_script_line) that is not
available outside the CLI pipeline; those paths are covered by the
CLI metacommand integration tests.

Requires the ``odfpy`` package (``execsql2[ods]``).  The entire module
is skipped if odfpy is not installed.
"""

from __future__ import annotations

import pytest

try:
    import of.opendocument  # noqa: F401

    _ods_available = True
except ImportError:
    _ods_available = False

pytestmark = pytest.mark.skipif(not _ods_available, reason="requires odfpy (install with execsql2[ods])")

from execsql.exporters.ods import OdsFile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ods(tmp_path, sheet_name, rows):
    """Build a minimal ODS file using OdsFile and return its path."""
    path = str(tmp_path / "test.ods")
    wbk = OdsFile()
    wbk.open(path)
    tbl = wbk.new_sheet(sheet_name)
    for i, row in enumerate(rows):
        wbk.add_row_to_sheet(row, tbl, header=(i == 0))
    wbk.add_sheet(tbl)
    wbk.save_close()
    return path


# ---------------------------------------------------------------------------
# OdsFile — init and repr
# ---------------------------------------------------------------------------


class TestOdsFileInit:
    def test_repr(self):
        assert repr(OdsFile()) == "OdsFile()"

    def test_wbk_none_initially(self):
        f = OdsFile()
        assert f.wbk is None

    def test_filename_none_initially(self):
        f = OdsFile()
        assert f.filename is None


# ---------------------------------------------------------------------------
# OdsFile.open — new file
# ---------------------------------------------------------------------------


class TestOdsFileOpen:
    def test_open_new_file_creates_workbook(self, tmp_path):
        path = str(tmp_path / "new.ods")
        f = OdsFile()
        f.open(path)
        assert f.wbk is not None
        f.close()

    def test_open_sets_filename(self, tmp_path):
        path = str(tmp_path / "new.ods")
        f = OdsFile()
        f.open(path)
        assert f.filename == path
        f.close()


# ---------------------------------------------------------------------------
# OdsFile.sheetnames / new_sheet / add_sheet / save_close
# ---------------------------------------------------------------------------


class TestOdsFileSheets:
    def test_new_sheet_returns_table(self, tmp_path):
        path = str(tmp_path / "test.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("MySheet")
        assert tbl is not None
        f.close()

    def test_add_sheet_and_sheetnames(self, tmp_path):
        path = str(tmp_path / "test.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("DataSheet")
        f.add_sheet(tbl)
        names = f.sheetnames()
        f.close()
        assert "DataSheet" in names

    def test_save_close_creates_file(self, tmp_path):
        path = str(tmp_path / "out.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("Sheet1")
        f.add_row_to_sheet(["id", "name"], tbl, header=True)
        f.add_row_to_sheet([1, "Alice"], tbl)
        f.add_sheet(tbl)
        f.save_close()
        assert (tmp_path / "out.ods").exists()


# ---------------------------------------------------------------------------
# OdsFile round-trip: write then read back
# ---------------------------------------------------------------------------


class TestOdsFileRoundTrip:
    def test_header_row_written(self, tmp_path):
        path = _make_ods(tmp_path, "Sheet1", [["id", "name"], [1, "Alice"]])
        f = OdsFile()
        f.open(path)
        data = f.sheet_data("Sheet1")
        f.close()
        assert data[0] == ["id", "name"]

    def test_data_row_written(self, tmp_path):
        path = _make_ods(tmp_path, "Sheet1", [["val"], ["hello"]])
        f = OdsFile()
        f.open(path)
        data = f.sheet_data("Sheet1")
        f.close()
        # Data row contains the string value
        assert any("hello" in row for row in data)

    def test_sheet_named_by_string(self, tmp_path):
        path = _make_ods(tmp_path, "MyData", [["x"], [42]])
        f = OdsFile()
        f.open(path)
        sheet = f.sheet_named("MyData")
        f.close()
        assert sheet is not None

    def test_nonexistent_sheet_returns_none(self, tmp_path):
        path = _make_ods(tmp_path, "Sheet1", [["x"], [1]])
        f = OdsFile()
        f.open(path)
        sheet = f.sheet_named("NoSuchSheet")
        f.close()
        assert sheet is None

    def test_sheet_data_missing_sheet_raises(self, tmp_path):
        from execsql.exceptions import OdsFileError

        path = _make_ods(tmp_path, "Sheet1", [["x"], [1]])
        f = OdsFile()
        f.open(path)
        with pytest.raises(OdsFileError):
            f.sheet_data("MissingSheet")
        f.close()


# ---------------------------------------------------------------------------
# OdsFile.add_row_to_sheet — various data types
# ---------------------------------------------------------------------------


class TestOdsFileRowTypes:
    def test_integer_value(self, tmp_path):
        path = str(tmp_path / "types.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("S")
        f.add_row_to_sheet([1], tbl)
        f.add_sheet(tbl)
        f.save_close()
        assert (tmp_path / "types.ods").exists()

    def test_float_value(self, tmp_path):
        path = str(tmp_path / "types.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("S")
        f.add_row_to_sheet([3.14], tbl)
        f.add_sheet(tbl)
        f.save_close()
        assert (tmp_path / "types.ods").exists()

    def test_bool_value(self, tmp_path):
        path = str(tmp_path / "types.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("S")
        f.add_row_to_sheet([True, False], tbl)
        f.add_sheet(tbl)
        f.save_close()
        assert (tmp_path / "types.ods").exists()

    def test_date_value(self, tmp_path):
        import datetime

        path = str(tmp_path / "types.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("S")
        f.add_row_to_sheet([datetime.date(2024, 1, 15)], tbl)
        f.add_sheet(tbl)
        f.save_close()
        assert (tmp_path / "types.ods").exists()

    def test_datetime_value(self, tmp_path):
        import datetime

        path = str(tmp_path / "types.ods")
        f = OdsFile()
        f.open(path)
        tbl = f.new_sheet("S")
        f.add_row_to_sheet([datetime.datetime(2024, 1, 15, 12, 30, 0)], tbl)
        f.add_sheet(tbl)
        f.save_close()
        assert (tmp_path / "types.ods").exists()
