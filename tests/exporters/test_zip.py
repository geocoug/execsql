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
