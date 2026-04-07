"""
Extended tests for execsql.exporters.raw — covering additional branches
not exercised by test_exporters.py.

NOTE: The ZipWriter class (used in the zipfile= branches of raw.py) calls
.encode("utf-8") internally and does not support writing raw bytes objects.
Those branches therefore cannot be exercised via the public API without
triggering an AttributeError.  The ZIP-path tests here verify that the
zip branch is reached and raises the expected error for bytes data.
"""

from __future__ import annotations

import base64

import pytest

from execsql.exporters.raw import write_query_b64, write_query_raw


@pytest.fixture(autouse=True)
def zip_conf(minimal_conf):
    """Add zip_buffer_mb so ZipWriter doesn't fail on init."""
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


# ---------------------------------------------------------------------------
# write_query_raw — ZIP branch reached (lines 43-55)
# ZipWriter.write() expects str, not bytes — writing bytes raises AttributeError.
# This confirms the branch is entered and that the limitation exists.
# ---------------------------------------------------------------------------


class TestWriteQueryRawZipBranch:
    def test_zip_branch_entered_for_empty_rowsource(self, noop_filewriter_close, tmp_path):
        """ZIP branch is entered even with empty rows — no data written, no error."""
        zpath = str(tmp_path / "out.zip")
        write_query_raw(zpath, [], db_encoding="utf-8", zipfile=zpath)

    def test_zip_branch_string_data_raises_attribute_error(self, noop_filewriter_close, tmp_path):
        """raw.py zip branch converts str to bytes then passes to ZipWriter.write()
        which calls .encode("utf-8") on the result — AttributeError for bytes."""
        zpath = str(tmp_path / "out.zip")
        with pytest.raises(AttributeError):
            write_query_raw(zpath, [["hello"]], db_encoding="utf-8", zipfile=zpath)

    def test_zip_branch_bytearray_raises_attribute_error(self, noop_filewriter_close, tmp_path):
        """Bytearray data in zip branch hits ZipWriter limitation — AttributeError."""
        zpath = str(tmp_path / "out.zip")
        with pytest.raises(AttributeError):
            write_query_raw(zpath, [[bytearray(b"\x01\x02")]], db_encoding="utf-8", zipfile=zpath)


# ---------------------------------------------------------------------------
# write_query_b64 — ZIP branch reached (lines 68-74)
# ---------------------------------------------------------------------------


class TestWriteQueryB64ZipBranch:
    def test_zip_branch_entered_for_empty_rowsource(self, noop_filewriter_close, tmp_path):
        """ZIP branch is entered with empty rows."""
        zpath = str(tmp_path / "out.zip")
        write_query_b64(zpath, [], zipfile=zpath)

    def test_zip_branch_bytes_decode_raises_attribute_error(self, noop_filewriter_close, tmp_path):
        """b64decode returns bytes; ZipWriter.write() can't encode bytes."""
        zpath = str(tmp_path / "out.zip")
        payload = base64.standard_b64encode(b"hello")
        with pytest.raises(AttributeError):
            write_query_b64(zpath, [[payload]], zipfile=zpath)
