"""
Tests for execsql.exporters.xml — XML export.

write_query_to_xml — serializes a query result to a well-formed XML file.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from execsql.exporters.xml import write_query_to_xml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(headers, rows):
    db = MagicMock()
    db.select_rowsource.return_value = (headers, rows)
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteQueryToXml:
    def test_produces_xml_declaration(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["id"], [[1]])
        write_query_to_xml("SELECT 1", "items", db, outfile)
        text = (tmp_path / "out.xml").read_text()
        assert "<?xml" in text

    def test_root_element_uses_tablename(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["id"], [[1]])
        write_query_to_xml("SELECT 1", "mytable", db, outfile)
        text = (tmp_path / "out.xml").read_text()
        assert "<mytable>" in text
        assert "</mytable>" in text

    def test_row_elements_present(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["id", "name"], [[1, "Alice"], [2, "Bob"]])
        write_query_to_xml("SELECT 1", "rows", db, outfile)
        text = (tmp_path / "out.xml").read_text()
        assert text.count("<row>") == 2
        assert text.count("</row>") == 2

    def test_column_values_in_elements(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["name"], [["Alice"]])
        write_query_to_xml("SELECT 1", "data", db, outfile)
        text = (tmp_path / "out.xml").read_text()
        assert "<name>Alice</name>" in text

    def test_empty_result_produces_root_only(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["id"], [])
        write_query_to_xml("SELECT 1", "empty", db, outfile)
        text = (tmp_path / "out.xml").read_text()
        assert "<empty>" in text
        assert "</empty>" in text
        assert "<row>" not in text

    def test_desc_written_as_comment(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["id"], [[1]])
        write_query_to_xml("SELECT 1", "d", db, outfile, desc="My comment")
        text = (tmp_path / "out.xml").read_text()
        assert "<!--My comment-->" in text

    def test_no_desc_no_comment(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["id"], [[1]])
        write_query_to_xml("SELECT 1", "d", db, outfile)
        text = (tmp_path / "out.xml").read_text()
        assert "<!--" not in text

    def test_append_mode(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["id"], [[1]])
        write_query_to_xml("SELECT 1", "d", db, outfile)
        size1 = (tmp_path / "out.xml").stat().st_size
        db2 = _make_db(["id"], [[2]])
        write_query_to_xml("SELECT 1", "d", db2, outfile, append=True)
        assert (tmp_path / "out.xml").stat().st_size > size1

    def test_multiple_columns(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.xml")
        db = _make_db(["a", "b"], [[10, 20]])
        write_query_to_xml("SELECT 1", "tbl", db, outfile)
        text = (tmp_path / "out.xml").read_text()
        assert "<a>10</a>" in text
        assert "<b>20</b>" in text

    def test_db_error_raises(self, noop_filewriter_close, tmp_path):
        from execsql.exceptions import ErrInfo

        outfile = str(tmp_path / "out.xml")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_xml("SELECT 1", "t", db, outfile)

    def test_errinfo_from_db_is_reraised(self, tmp_path):
        """ErrInfo raised by select_rowsource must propagate unchanged (line 33)."""
        from execsql.exceptions import ErrInfo

        outfile = str(tmp_path / "out.xml")
        original = ErrInfo(type="db", exception_msg="original error")
        db = MagicMock()
        db.select_rowsource.side_effect = original
        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_xml("SELECT 1", "t", db, outfile)
        assert exc_info.value is original

    def test_write_to_zipfile(self, tmp_path):
        """zipfile branch: output is written into a zip archive (lines 48-49)."""
        import zipfile as _zipfile

        import execsql.state as _state

        _state.conf.zip_buffer_mb = 1
        zpath = str(tmp_path / "out.zip")
        member = "data.xml"
        db = _make_db(["id"], [[1]])
        write_query_to_xml("SELECT 1", "rows", db, member, zipfile=zpath)
        with _zipfile.ZipFile(zpath, "r") as zf:
            content = zf.read(member).decode("utf-8")
        assert "<?xml" in content
        assert "<rows>" in content
