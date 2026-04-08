"""
Extended tests for execsql.exporters.pretty — covering uncovered lines:

  Line 44   — as_ucode: bytes (non-bytearray) that fall through to isinstance check
  Lines 48-55 — rows is not a list (iterator/generator); ErrInfo on failure
  Line 82   — ZIP path for ofile
"""

from __future__ import annotations

import zipfile

import pytest

from execsql.exporters.pretty import prettyprint_rowset


@pytest.fixture(autouse=True)
def zip_conf(minimal_conf):
    """Add zip_buffer_mb so ZipWriter doesn't fail."""
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


# ---------------------------------------------------------------------------
# Rows provided as a generator (lines 48-55)
# ---------------------------------------------------------------------------


class TestPrettyprintRowsetGeneratorInput:
    def test_accepts_generator_rows(self, noop_filewriter_close, tmp_path):
        """prettyprint_rowset should materialise a generator into a list."""
        out = str(tmp_path / "out.txt")

        def row_gen():
            yield ("alpha",)
            yield ("beta",)

        prettyprint_rowset(["col"], row_gen(), out)
        text = (tmp_path / "out.txt").read_text()
        assert "alpha" in text
        assert "beta" in text

    def test_accepts_iter_of_tuples(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        rows = iter([(1, "x"), (2, "y")])
        prettyprint_rowset(["id", "val"], rows, out)
        text = (tmp_path / "out.txt").read_text()
        assert "id" in text
        assert "val" in text


# ---------------------------------------------------------------------------
# as_ucode: bytes path (line 44 — isinstance(s, bytes) inside the else branch)
# ---------------------------------------------------------------------------


class TestPrettyprintRowsetBytesData:
    def test_bytes_value_shown_as_binary_data(self, noop_filewriter_close, tmp_path):
        """Regular bytes objects trigger the memoryview/bytes/bytearray branch."""
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["data"], [(b"\x01\x02",)], out)
        text = (tmp_path / "out.txt").read_text()
        assert "Binary data" in text

    def test_memoryview_shown_as_binary_data(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["data"], [(memoryview(b"\xab\xcd"),)], out)
        text = (tmp_path / "out.txt").read_text()
        assert "Binary data" in text


# ---------------------------------------------------------------------------
# ZIP path (line 82)
# ---------------------------------------------------------------------------


class TestPrettyprintRowsetZip:
    def test_writes_to_zip_archive(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        prettyprint_rowset(["id", "name"], [(1, "Alice")], zpath, zipfile=zpath)
        assert zipfile.is_zipfile(zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert "id" in content
        assert "Alice" in content

    def test_zip_append_mode(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        prettyprint_rowset(["col"], [("first",)], zpath, zipfile=zpath)
        size1 = (tmp_path / "out.zip").stat().st_size
        prettyprint_rowset(["col"], [("second",)], zpath, append=True, zipfile=zpath)
        assert (tmp_path / "out.zip").stat().st_size > size1

    def test_zip_with_desc(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        prettyprint_rowset(["col"], [("v",)], zpath, desc="My Title", zipfile=zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert "My Title" in content
