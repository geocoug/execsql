"""
Tests for execsql.exporters.xls — XlsFile and XlsxFile readers.

XlsFile wraps xlrd (reads legacy .xls).
XlsxFile wraps openpyxl (reads modern .xlsx).

Both packages are in the ``excel`` optional extra, and both are included in
the ``all`` extra used by the tox test matrix.  The tests are skipped if the
relevant package is not installed.
"""

from __future__ import annotations


import pytest


# ---------------------------------------------------------------------------
# XlsxFile (openpyxl)
# ---------------------------------------------------------------------------


openpyxl = pytest.importorskip("openpyxl")


def _make_xlsx(tmp_path, sheet_name, rows):
    """Create a minimal .xlsx file using openpyxl and return its path."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    path = tmp_path / "test.xlsx"
    wb.save(str(path))
    wb.close()
    return str(path)


class TestXlsxFileInit:
    def test_repr(self):
        from execsql.exporters.xls import XlsxFile

        assert repr(XlsxFile()) == "XlsxFile()"

    def test_init_creates_instance(self):
        from execsql.exporters.xls import XlsxFile

        f = XlsxFile()
        assert f.wbk is None
        assert f.filename is None


class TestXlsxFileOpen:
    def test_open_existing_file(self, tmp_path):
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "Sheet1", [["id", "name"], [1, "Alice"]])
        f = XlsxFile()
        f.open(path)
        assert f.wbk is not None
        f.close()

    def test_open_nonexistent_raises(self, tmp_path):
        from execsql.exporters.xls import XlsxFile
        from execsql.exceptions import XlsxFileError

        f = XlsxFile()
        with pytest.raises(XlsxFileError):
            f.open(str(tmp_path / "missing.xlsx"))

    def test_close_clears_state(self, tmp_path):
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "Sheet1", [["x"], [1]])
        f = XlsxFile()
        f.open(path)
        f.close()
        assert f.wbk is None
        assert f.filename is None


class TestXlsxFileSheetnames:
    def test_returns_sheet_name(self, tmp_path):
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "MySheet", [["a"], [1]])
        f = XlsxFile()
        f.open(path)
        names = f.sheetnames()
        f.close()
        assert "MySheet" in names


class TestXlsxFileSheetData:
    def test_reads_header_and_data(self, tmp_path):
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "Sheet1", [["id", "name"], [1, "Alice"], [2, "Bob"]])
        f = XlsxFile()
        f.open(path)
        data = f.sheet_data("Sheet1")
        f.close()
        assert data[0] == ["id", "name"]
        assert data[1] == [1, "Alice"]
        assert data[2] == [2, "Bob"]

    def test_sheet_by_integer_index(self, tmp_path):
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "First", [["col"], [42]])
        f = XlsxFile()
        f.open(path)
        data = f.sheet_data(1)  # 1-based
        f.close()
        assert data[0] == ["col"]

    def test_nonexistent_sheet_raises(self, tmp_path):
        from execsql.exporters.xls import XlsxFile
        from execsql.exceptions import XlsxFileError

        path = _make_xlsx(tmp_path, "Sheet1", [["x"], [1]])
        f = XlsxFile()
        f.open(path)
        with pytest.raises(XlsxFileError):
            f.sheet_data("NoSuchSheet")
        f.close()

    def test_empty_row_stops_read(self, tmp_path):
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "Sheet1", [["id"], [1], [None], [3]])
        f = XlsxFile()
        f.open(path)
        data = f.sheet_data("Sheet1")
        f.close()
        # Reads stop at the first all-None row
        assert [1] in data
        assert [3] not in data


# ---------------------------------------------------------------------------
# XlsFile (xlrd) — skipped if xlrd not installed
# ---------------------------------------------------------------------------


class TestXlsxFileSheetNamed:
    def test_sheet_by_string_integer(self, tmp_path):
        """Passing '1' as string selects the first sheet (1-based)."""
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "First", [["col"], [42]])
        f = XlsxFile()
        f.open(path)
        data = f.sheet_data("1")
        f.close()
        assert data[0] == ["col"]

    def test_sheet_by_zero_uses_name_lookup(self, tmp_path):
        """Passing '0' (< 1) treats it as a name, which will fail."""
        from execsql.exporters.xls import XlsxFile
        from execsql.exceptions import XlsxFileError

        path = _make_xlsx(tmp_path, "Sheet1", [["x"], [1]])
        f = XlsxFile()
        f.open(path)
        with pytest.raises(XlsxFileError):
            f.sheet_data("0")
        f.close()

    def test_sheet_by_non_numeric_string(self, tmp_path):
        """Passing a non-numeric string looks up by name."""
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "MyData", [["a"], [1]])
        f = XlsxFile()
        f.open(path)
        data = f.sheet_data("MyData")
        f.close()
        assert data[0] == ["a"]


class TestXlsxFileBoolFormulas:
    def test_false_formula_converted(self, tmp_path):
        """Cells with '=FALSE()' are converted to False."""
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "Sheet1", [["flag"], ["=FALSE()"]])
        f = XlsxFile()
        f.open(path)
        data = f.sheet_data("Sheet1")
        f.close()
        assert data[1] == [False]

    def test_true_formula_converted(self, tmp_path):
        """Cells with '=TRUE()' are converted to True."""
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "Sheet1", [["flag"], ["=TRUE()"]])
        f = XlsxFile()
        f.open(path)
        data = f.sheet_data("Sheet1")
        f.close()
        assert data[1] == [True]


class TestXlsxFileReadOnly:
    def test_open_read_only(self, tmp_path):
        from execsql.exporters.xls import XlsxFile

        path = _make_xlsx(tmp_path, "Sheet1", [["x"], [1]])
        f = XlsxFile()
        f.open(path, read_only=True)
        assert f.read_only is True
        f.close()


class TestXlsxLog:
    def test_log_write(self):
        from execsql.exporters.xls import XlsxFile

        f = XlsxFile()
        f.errlog.write("test message")
        assert "test message" in f.errlog.log_msgs


class TestXlsFileInit:
    xlrd = pytest.importorskip("xlrd")

    def test_repr(self):
        from execsql.exporters.xls import XlsFile

        assert repr(XlsFile()) == "XlsFile()"

    def test_open_nonexistent_raises(self, tmp_path):
        from execsql.exporters.xls import XlsFile
        from execsql.exceptions import XlsFileError

        f = XlsFile()
        with pytest.raises(XlsFileError):
            f.open(str(tmp_path / "missing.xls"))
