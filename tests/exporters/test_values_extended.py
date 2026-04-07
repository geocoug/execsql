"""
Extended tests for execsql.exporters.values — covering the ZIP path (line 45)
and write_query_to_values error path (lines 77-83).
"""

from __future__ import annotations

import zipfile
from unittest.mock import MagicMock

import pytest

from execsql.exceptions import ErrInfo
from execsql.exporters.values import export_values, write_query_to_values


@pytest.fixture(autouse=True)
def zip_conf(minimal_conf):
    """Add zip_buffer_mb so ZipWriter doesn't fail."""
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


# ---------------------------------------------------------------------------
# export_values — ZIP path (line 45)
# ---------------------------------------------------------------------------


class TestExportValuesZip:
    def test_writes_insert_statement_to_zip(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        export_values(zpath, ["id", "name"], [(1, "Alice"), (2, "Bob")], zipfile=zpath)
        assert zipfile.is_zipfile(zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "INSERT INTO" in content
        assert "'Alice'" in content

    def test_null_values_written_as_null_in_zip(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        export_values(zpath, ["id", "val"], [(1, None)], zipfile=zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "NULL" in content

    def test_desc_written_as_comment_in_zip(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        export_values(zpath, ["id"], [(1,)], desc="My table", zipfile=zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "-- My table" in content

    def test_empty_rows_in_zip(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        export_values(zpath, ["id"], [], zipfile=zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "INSERT INTO" in content
        assert "VALUES" in content


# ---------------------------------------------------------------------------
# write_query_to_values — error path (lines 77-83)
# ---------------------------------------------------------------------------


class TestWriteQueryToValues:
    def test_db_error_raises_errinfo(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.sql")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_values("SELECT 1", db, outfile)

    def test_db_errinfo_propagates_unchanged(self, noop_filewriter_close, tmp_path):
        """ErrInfo exceptions from select_rowsource should propagate unmodified."""
        outfile = str(tmp_path / "out.sql")
        db = MagicMock()
        original_err = ErrInfo("db", "SELECT 1")
        db.select_rowsource.side_effect = original_err
        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_values("SELECT 1", db, outfile)
        assert exc_info.value is original_err

    def test_successful_write(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.sql")
        db = MagicMock()
        db.select_rowsource.return_value = (["id"], [[1], [2]])
        write_query_to_values("SELECT 1", db, outfile)
        text = (tmp_path / "out.sql").read_text()
        assert "INSERT INTO" in text
