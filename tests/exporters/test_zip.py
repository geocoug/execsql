"""
Integration tests for execsql.exporters.zip.

Covers WriteableZipfile and ZipWriter using the filesystem (tmp_path).
No database or special state is required; the only _state dependency is
conf.zip_buffer_mb which is added by the zip_conf fixture below.
"""

from __future__ import annotations

import zipfile as _zipfile

import pytest

from execsql.exporters.zip import WriteableZipfile, ZipWriter


@pytest.fixture(autouse=True)
def zip_conf(minimal_conf):
    """Add zip_buffer_mb to the minimal conf namespace."""
    minimal_conf.zip_buffer_mb = 1  # 1 MB buffer
    yield minimal_conf


# ===========================================================================
# WriteableZipfile
# ===========================================================================


class TestWriteableZipfile:
    def test_creates_zip_archive(self, tmp_path):
        zpath = str(tmp_path / "out.zip")
        wz = WriteableZipfile(zpath)
        wz.member_file("hello.txt")
        wz.write("hello world")
        wz.close()
        assert _zipfile.is_zipfile(zpath)

    def test_member_file_content_readable(self, tmp_path):
        zpath = str(tmp_path / "out.zip")
        wz = WriteableZipfile(zpath)
        wz.member_file("data.txt")
        wz.write("content here")
        wz.close()
        with _zipfile.ZipFile(zpath, "r") as zf:
            assert "data.txt" in zf.namelist()
            text = zf.read("data.txt").decode("utf-8")
        assert "content here" in text

    def test_multiple_member_files(self, tmp_path):
        zpath = str(tmp_path / "multi.zip")
        wz = WriteableZipfile(zpath)
        for name in ("a.txt", "b.txt", "c.txt"):
            wz.member_file(name)
            wz.write(f"content of {name}")
            wz.close_member()
        wz.close()
        with _zipfile.ZipFile(zpath, "r") as zf:
            names = zf.namelist()
        assert set(names) == {"a.txt", "b.txt", "c.txt"}

    def test_write_large_content_flushed_correctly(self, tmp_path):
        zpath = str(tmp_path / "large.zip")
        wz = WriteableZipfile(zpath)
        wz.member_file("big.txt")
        # Write enough to potentially overflow buffer
        chunk = "x" * 1024
        for _ in range(1024):
            wz.write(chunk)
        wz.close()
        with _zipfile.ZipFile(zpath, "r") as zf:
            data = zf.read("big.txt")
        assert len(data) == 1024 * 1024

    def test_append_mode_adds_to_existing_zip(self, tmp_path):
        zpath = str(tmp_path / "append.zip")
        # Create initial zip
        wz1 = WriteableZipfile(zpath)
        wz1.member_file("first.txt")
        wz1.write("first")
        wz1.close()
        # Append a second member
        wz2 = WriteableZipfile(zpath, append=True)
        wz2.member_file("second.txt")
        wz2.write("second")
        wz2.close()
        with _zipfile.ZipFile(zpath, "r") as zf:
            names = zf.namelist()
        assert "first.txt" in names
        assert "second.txt" in names

    def test_close_is_idempotent(self, tmp_path):
        zpath = str(tmp_path / "out.zip")
        wz = WriteableZipfile(zpath)
        wz.member_file("f.txt")
        wz.write("data")
        wz.close()
        # Second close should not raise
        wz.close()


# ===========================================================================
# ZipWriter
# ===========================================================================


class TestZipWriter:
    def test_creates_zip_with_member(self, tmp_path):
        zpath = str(tmp_path / "out.zip")
        zw = ZipWriter(zpath, "member.txt")
        zw.write("hello from ZipWriter")
        zw.close()
        assert _zipfile.is_zipfile(zpath)
        with _zipfile.ZipFile(zpath, "r") as zf:
            assert "member.txt" in zf.namelist()

    def test_member_content_correct(self, tmp_path):
        zpath = str(tmp_path / "out.zip")
        zw = ZipWriter(zpath, "content.txt")
        zw.write("test content")
        zw.close()
        with _zipfile.ZipFile(zpath, "r") as zf:
            data = zf.read("content.txt").decode("utf-8")
        assert data == "test content"

    def test_multiple_writes_concatenated(self, tmp_path):
        zpath = str(tmp_path / "out.zip")
        zw = ZipWriter(zpath, "joined.txt")
        zw.write("part1")
        zw.write("part2")
        zw.close()
        with _zipfile.ZipFile(zpath, "r") as zf:
            data = zf.read("joined.txt").decode("utf-8")
        assert data == "part1part2"

    def test_context_manager_returns_zipwriter_instance(self, tmp_path):
        """__enter__ returns the ZipWriter itself."""
        zpath = str(tmp_path / "cm.zip")
        with ZipWriter(zpath, "cm.txt") as zw:
            assert isinstance(zw, ZipWriter)
            zw.write("cm content")

    def test_context_manager_produces_valid_zip(self, tmp_path):
        """Data written inside a `with` block is flushed and the archive is valid."""
        zpath = str(tmp_path / "cm_valid.zip")
        with ZipWriter(zpath, "entry.txt") as zw:
            zw.write("context manager data")
        assert _zipfile.is_zipfile(zpath)
        with _zipfile.ZipFile(zpath, "r") as zf:
            data = zf.read("entry.txt").decode("utf-8")
        assert data == "context manager data"

    def test_context_manager_closes_on_exception(self, tmp_path):
        """Even when an exception is raised inside the block, the archive is finalised."""
        zpath = str(tmp_path / "cm_exc.zip")
        try:
            with ZipWriter(zpath, "partial.txt") as zw:
                zw.write("before error")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        # Archive must still be a valid zip (close was called via __exit__)
        assert _zipfile.is_zipfile(zpath)

    def test_close_is_idempotent(self, tmp_path):
        """Calling close() twice on ZipWriter must not raise."""
        zpath = str(tmp_path / "idem.zip")
        zw = ZipWriter(zpath, "f.txt")
        zw.write("data")
        zw.close()
        zw.close()  # second close — must not raise

    def test_close_sets_zwriter_to_none(self, tmp_path):
        """After close(), zwriter is set to None to mark the writer as done."""
        zpath = str(tmp_path / "closed.zip")
        zw = ZipWriter(zpath, "f.txt")
        zw.close()
        assert zw.zwriter is None


# ===========================================================================
# WriteableZipfile — context manager and __del__ safety
# ===========================================================================


class TestWriteableZipfileContextManager:
    def test_context_manager_returns_self(self, tmp_path):
        """__enter__ returns the WriteableZipfile instance."""
        zpath = str(tmp_path / "wz_cm.zip")
        with WriteableZipfile(zpath) as wz:
            assert isinstance(wz, WriteableZipfile)

    def test_context_manager_produces_valid_zip(self, tmp_path):
        """Data written via `with WriteableZipfile(...)` produces a valid archive."""
        zpath = str(tmp_path / "wz_valid.zip")
        with WriteableZipfile(zpath) as wz:
            wz.member_file("content.txt")
            wz.write("hello from context manager")
        assert _zipfile.is_zipfile(zpath)
        with _zipfile.ZipFile(zpath, "r") as zf:
            data = zf.read("content.txt").decode("utf-8")
        assert data == "hello from context manager"

    def test_context_manager_closes_on_exception(self, tmp_path):
        """__exit__ is called even when an exception escapes the block."""
        zpath = str(tmp_path / "wz_exc.zip")
        try:
            with WriteableZipfile(zpath) as wz:
                wz.member_file("partial.txt")
                wz.write("before error")
                raise RuntimeError("deliberate")
        except RuntimeError:
            pass
        # Archive must still be a valid (possibly partial) zip file
        assert _zipfile.is_zipfile(zpath)

    def test_del_does_not_raise_on_already_closed_instance(self, tmp_path):
        """__del__ must be silent even if the underlying ZipFile is already closed."""
        zpath = str(tmp_path / "wz_del.zip")
        wz = WriteableZipfile(zpath)
        wz.member_file("del_test.txt")
        wz.write("data")
        wz.close()
        # Manually call __del__ after close — must not raise
        wz.__del__()
