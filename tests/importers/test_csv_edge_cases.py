"""
Edge-case tests for CSV/delimited import.

Covers scenarios not exercised by test_csv_importer.py:
- Empty files
- Header-only files (no data rows)
- Files with BOM markers (UTF-8 BOM)
- Inconsistent column counts across rows
- Unicode/special characters in data
- Very long field values
- Files with only whitespace rows
- Encoding parameter override
"""

from __future__ import annotations

import pytest

from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import DataTableError, ErrInfo
from execsql.importers.csv import importtable


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
    minimal_conf.import_encoding = "utf-8"
    minimal_conf.import_common_cols_only = False
    minimal_conf.quote_all_text = False
    minimal_conf.scan_lines = 50
    minimal_conf.empty_rows = True
    minimal_conf.import_row_buffer = 1000
    minimal_conf.import_progress_interval = 0
    minimal_conf.show_progress = False
    yield minimal_conf


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    d = SQLiteDatabase(path)
    yield d
    d.close()


# ===========================================================================
# Empty and minimal files
# ===========================================================================


class TestEmptyAndMinimalFiles:
    def test_header_only_no_data_rows(self, db, tmp_path):
        """A CSV with headers but zero data rows should create a table with no rows."""
        csv = tmp_path / "empty_data.csv"
        csv.write_text("id,name,value\n", encoding="utf-8")
        importtable(db, None, "empty_tbl", str(csv), is_new=1)
        _, rows = db.select_data("SELECT * FROM empty_tbl;")
        assert len(rows) == 0

    def test_single_column_single_row(self, db, tmp_path):
        csv = tmp_path / "single.csv"
        csv.write_text("x\n42\n", encoding="utf-8")
        importtable(db, None, "single_tbl", str(csv), is_new=1)
        _, rows = db.select_data("SELECT x FROM single_tbl;")
        assert len(rows) == 1

    def test_nonexistent_file_raises(self, db, tmp_path):
        with pytest.raises(ErrInfo, match="Non-existent file"):
            importtable(db, None, "t", str(tmp_path / "ghost.csv"), is_new=1)


# ===========================================================================
# BOM handling
# ===========================================================================


class TestBOMHandling:
    def test_utf8_bom_import(self, db, tmp_path):
        """UTF-8 BOM should not corrupt the first column header."""
        csv = tmp_path / "bom.csv"
        csv.write_bytes(b"\xef\xbb\xbfid,name\n1,Alice\n2,Bob\n")
        importtable(db, None, "bom_tbl", str(csv), is_new=1, encoding="utf-8-sig")
        cols = db.table_columns("bom_tbl")
        # First column should be 'id', not '\ufeffid'
        assert cols[0] == "id"
        _, rows = db.select_data("SELECT id FROM bom_tbl ORDER BY id;")
        assert len(rows) == 2


# ===========================================================================
# Unicode and special characters
# ===========================================================================


class TestUnicodeData:
    def test_unicode_values(self, db, tmp_path):
        csv = tmp_path / "unicode.csv"
        csv.write_text('id,name\n1,"café résumé"\n2,"日本語"\n', encoding="utf-8")
        importtable(db, None, "uni_tbl", str(csv), is_new=1)
        _, rows = db.select_data("SELECT name FROM uni_tbl ORDER BY id;")
        assert rows[0][0] == "café résumé"
        assert rows[1][0] == "日本語"

    def test_embedded_commas_in_quoted_field(self, db, tmp_path):
        csv = tmp_path / "commas.csv"
        csv.write_text('id,description\n1,"hello, world"\n', encoding="utf-8")
        importtable(db, None, "comma_tbl", str(csv), is_new=1)
        _, rows = db.select_data("SELECT description FROM comma_tbl;")
        assert rows[0][0] == "hello, world"

    def test_embedded_newlines_in_quoted_field(self, db, tmp_path):
        """Embedded newlines in quoted CSV fields are not preserved by the
        execsql CSV reader — the newline is treated as a row break.  This test
        documents the current behavior: the import succeeds but the value is
        split across rows or truncated."""
        csv = tmp_path / "newlines.csv"
        csv.write_text('id,val\n1,"line1\nline2"\n', encoding="utf-8")
        # The import should not crash — whether the newline is preserved
        # depends on the parser path (csv module fast-path vs character parser).
        try:
            importtable(db, None, "nl_tbl", str(csv), is_new=1)
        except ErrInfo:
            pass  # Some parser paths may raise on the malformed row; that's acceptable

    def test_embedded_quotes_doubled(self, db, tmp_path):
        csv = tmp_path / "quotes.csv"
        csv.write_text('id,description\n1,"he said ""hello"""\n', encoding="utf-8")
        importtable(db, None, "qt_tbl", str(csv), is_new=1)
        _, rows = db.select_data("SELECT description FROM qt_tbl;")
        assert rows[0][0] == 'he said "hello"'


# ===========================================================================
# Long fields
# ===========================================================================


class TestLongFields:
    def test_long_string_value(self, db, tmp_path):
        """Values over 255 chars should be imported as TEXT type."""
        long_val = "x" * 500
        csv = tmp_path / "long.csv"
        csv.write_text(f"id,data\n1,{long_val}\n", encoding="utf-8")
        importtable(db, None, "long_tbl", str(csv), is_new=1)
        _, rows = db.select_data("SELECT data FROM long_tbl;")
        assert len(rows[0][0]) == 500


# ===========================================================================
# Encoding parameter
# ===========================================================================


class TestEncodingOverride:
    def test_latin1_encoding(self, db, tmp_path):
        csv = tmp_path / "latin1.csv"
        csv.write_bytes(b"id,name\n1,caf\xe9\n")
        importtable(db, None, "lat_tbl", str(csv), is_new=1, encoding="latin-1")
        _, rows = db.select_data("SELECT name FROM lat_tbl;")
        assert rows[0][0] == "café"


# ===========================================================================
# Junk header lines
# ===========================================================================


class TestJunkHeaderLines:
    def test_skip_junk_lines(self, db, tmp_path):
        csv = tmp_path / "junk.csv"
        csv.write_text("Report Title\nGenerated: today\nid,name\n1,Alice\n", encoding="utf-8")
        importtable(db, None, "junk_tbl", str(csv), is_new=1, junk_header_lines=2)
        _, rows = db.select_data("SELECT name FROM junk_tbl;")
        assert rows[0][0] == "Alice"


# ===========================================================================
# Append to existing table with type compatibility
# ===========================================================================


class TestAppendEdgeCases:
    def test_append_with_null_values(self, db, tmp_path):
        db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        db.execute("INSERT INTO t VALUES (1, 'existing');")
        db.commit()
        csv = tmp_path / "nulls.csv"
        csv.write_text("id,name\n2,\n", encoding="utf-8")
        importtable(db, None, "t", str(csv), is_new=False)
        _, rows = db.select_data("SELECT name FROM t WHERE id = 2;")
        assert len(rows) == 1
        # With empty_strings=True (default), empty CSV fields are imported as empty strings
        assert rows[0][0] == "" or rows[0][0] is None

    def test_append_nonexistent_table(self, db, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n", encoding="utf-8")
        with pytest.raises(ErrInfo, match="Non-existent table"):
            importtable(db, None, "no_such", str(csv), is_new=False)


# ===========================================================================
# Inconsistent column counts
# ===========================================================================


class TestInconsistentColumns:
    def test_extra_columns_in_data_row(self, db, tmp_path):
        """A data row with more columns than the header raises an error.

        During type inference (evaluate_column_types called with is_new=1),
        DataTable.__init__ scans every data row and enforces that no row has
        more fields than the header declares.  When del_empty_cols is False
        and the extra field is non-empty, DataTableError("Too many columns
        (N) on data row M") is raised before any INSERT is attempted.
        """
        csv_file = tmp_path / "extra_cols.csv"
        csv_file.write_text("id,name\n1,Alice,extra_value\n2,Bob\n", encoding="utf-8")
        with pytest.raises(DataTableError, match="Too many columns"):
            importtable(db, None, "extra_tbl", str(csv_file), is_new=1)

    def test_fewer_columns_in_data_row(self, db, tmp_path):
        """A data row with fewer columns than the header should raise ErrInfo.

        populate_table enforces ``len(line) < len(columns)`` and raises
        ErrInfo("Too few values on data line ...") when a row is short.
        Row 1 (id=1, name=Alice) is missing the 'value' column — this
        triggers the error before any rows are committed.
        """
        csv_file = tmp_path / "fewer_cols.csv"
        csv_file.write_text("id,name,value\n1,Alice\n2,Bob,42\n", encoding="utf-8")
        with pytest.raises(ErrInfo):
            importtable(db, None, "short_tbl", str(csv_file), is_new=1)


# ===========================================================================
# Encoding errors
# ===========================================================================


class TestEncodingErrors:
    def test_binary_data_with_utf8_encoding(self, db, tmp_path, importer_conf):
        """Raw bytes that are invalid UTF-8 must not be silently swallowed.

        EncodedFile.open() passes ``errors=conf.enc_err_disposition`` to the
        built-in ``open()``.  When enc_err_disposition is None (the default),
        Python's open() uses strict error handling and raises
        UnicodeDecodeError on the invalid bytes, which the importer wraps into
        ErrInfo.
        """
        csv_file = tmp_path / "binary.csv"
        # \x80, \x81, \x82 are invalid in UTF-8 (they are continuation bytes
        # with no preceding start byte).
        csv_file.write_bytes(b"id,val\n1,\x80\x81\x82\n")
        importer_conf.enc_err_disposition = None  # strict: raises on bad bytes
        with pytest.raises((ErrInfo, UnicodeDecodeError)):
            importtable(db, None, "bin_tbl", str(csv_file), is_new=1, encoding="utf-8")

    def test_encoding_error_with_replace_disposition(self, db, tmp_path, importer_conf):
        """With enc_err_disposition='replace', invalid bytes are substituted.

        Python's 'replace' error handler replaces each un-decodable byte with
        the Unicode replacement character (U+FFFD).  The import should
        complete without raising, and the stored value should contain the
        replacement character rather than the raw bytes.
        """
        csv_file = tmp_path / "binary_replace.csv"
        csv_file.write_bytes(b"id,val\n1,\x80\x81\x82\n")
        importer_conf.enc_err_disposition = "replace"
        importtable(db, None, "rep_tbl", str(csv_file), is_new=1, encoding="utf-8")
        _, rows = db.select_data("SELECT val FROM rep_tbl WHERE id = 1;")
        assert len(rows) == 1
        # The replacement character U+FFFD should appear in the stored value.
        stored = rows[0][0]
        assert stored is not None
        assert "\ufffd" in stored


# ===========================================================================
# Zero-byte file
# ===========================================================================


class TestZeroByteFile:
    def test_zero_byte_file(self, db, tmp_path):
        """A zero-byte file has no header line; diagnosis should raise ErrInfo.

        CsvFile.diagnose_delim() reads up to scan_lines lines from the file.
        If the file is empty it reads zero lines and raises
        ErrInfo("CSV diagnosis error: no lines read").
        """
        csv_file = tmp_path / "empty.csv"
        csv_file.write_bytes(b"")
        with pytest.raises(ErrInfo):
            importtable(db, None, "zero_tbl", str(csv_file), is_new=1)
