"""
Tests for execsql.utils.fileio — file I/O utilities.

Covers the pure-Python, dependency-free helpers:
- make_export_dirs
- check_dir
- EncodedFile (repr, open, close, BOM detection)
- TempFileMgr (repr, new_temp_fn, remove_all)
- list_encodings
"""

from __future__ import annotations

import codecs
import os

import pytest

from execsql.exceptions import ErrInfo
from execsql.utils.fileio import (
    EncodedFile,
    FileWriter,
    TempFileMgr,
    check_dir,
    list_encodings,
    make_export_dirs,
)


# ---------------------------------------------------------------------------
# make_export_dirs
# ---------------------------------------------------------------------------


class TestMakeExportDirs:
    def test_creates_nested_dirs(self, tmp_path):
        target = str(tmp_path / "a" / "b" / "c" / "out.csv")
        make_export_dirs(target)
        assert os.path.isdir(str(tmp_path / "a" / "b" / "c"))

    def test_existing_dir_is_noop(self, tmp_path):
        target = str(tmp_path / "out.csv")
        # Directory already exists — should not raise
        make_export_dirs(target)

    def test_stdout_skipped(self, tmp_path):
        # "stdout" should not attempt to create any directory
        make_export_dirs("stdout")
        make_export_dirs("STDOUT")

    def test_file_in_cwd_no_error(self):
        # A bare filename with no directory component → no dir to create
        make_export_dirs("out.csv")


# ---------------------------------------------------------------------------
# check_dir
# ---------------------------------------------------------------------------


class TestCheckDir:
    def test_stdout_always_passes(self, minimal_conf):
        minimal_conf.make_export_dirs = False
        check_dir("stdout")  # must not raise

    def test_existing_dir_passes(self, tmp_path, minimal_conf):
        minimal_conf.make_export_dirs = False
        target = str(tmp_path / "out.csv")
        check_dir(target)  # dir (tmp_path) exists → no error

    def test_missing_dir_raises_when_no_makedirs(self, tmp_path, minimal_conf):
        minimal_conf.make_export_dirs = False
        target = str(tmp_path / "nonexistent" / "out.csv")
        with pytest.raises(ErrInfo):
            check_dir(target)

    def test_missing_dir_created_when_makedirs_true(self, tmp_path, minimal_conf):
        minimal_conf.make_export_dirs = True
        target = str(tmp_path / "newdir" / "out.csv")
        check_dir(target)
        assert os.path.isdir(str(tmp_path / "newdir"))

    def test_bare_filename_no_dir_component(self, minimal_conf):
        minimal_conf.make_export_dirs = False
        check_dir("out.csv")  # no directory component → should not raise


# ---------------------------------------------------------------------------
# EncodedFile
# ---------------------------------------------------------------------------


class TestEncodedFileRepr:
    def test_repr(self, tmp_path):
        path = str(tmp_path / "f.txt")
        ef = EncodedFile(path, "utf-8")
        r = repr(ef)
        assert "EncodedFile(" in r
        assert "utf-8" in r


class TestEncodedFileInit:
    def test_nonexistent_file_stores_encoding(self, tmp_path):
        path = str(tmp_path / "missing.txt")
        ef = EncodedFile(path, "latin-1")
        assert ef.encoding == "latin-1"
        assert ef.bom_length == 0

    def test_existing_plain_file_no_bom(self, tmp_path):
        path = tmp_path / "plain.txt"
        path.write_text("hello", encoding="utf-8")
        ef = EncodedFile(str(path), "utf-8")
        assert ef.encoding == "utf-8"
        assert ef.bom_length == 0

    def test_utf8_bom_detected(self, tmp_path):
        path = tmp_path / "bom.txt"
        path.write_bytes(codecs.BOM_UTF8 + b"hello")
        ef = EncodedFile(str(path), "utf-8")
        assert ef.encoding == "utf-8-sig"
        assert ef.bom_length == 3

    def test_utf16_le_bom_detected(self, tmp_path):
        path = tmp_path / "bom16.txt"
        path.write_bytes(codecs.BOM_UTF16_LE + "hi".encode("utf-16-le"))
        ef = EncodedFile(str(path), "utf-8")
        assert ef.encoding == "utf_16"
        assert ef.bom_length == 2


class TestEncodedFileOpenClose:
    def test_open_returns_file_object(self, tmp_path, minimal_conf):
        minimal_conf.enc_err_disposition = "replace"
        path = tmp_path / "test.txt"
        path.write_text("data", encoding="utf-8")
        ef = EncodedFile(str(path), "utf-8")
        fo = ef.open("r")
        assert fo is not None
        ef.close()

    def test_open_and_read(self, tmp_path, minimal_conf):
        minimal_conf.enc_err_disposition = "replace"
        path = tmp_path / "test.txt"
        path.write_text("hello world", encoding="utf-8")
        ef = EncodedFile(str(path), "utf-8")
        fo = ef.open("r")
        content = fo.read()
        ef.close()
        assert content == "hello world"

    def test_open_write_mode(self, tmp_path, minimal_conf):
        minimal_conf.enc_err_disposition = "replace"
        path = tmp_path / "out.txt"
        ef = EncodedFile(str(path), "utf-8")
        fo = ef.open("w")
        fo.write("written")
        ef.close()
        assert path.read_text(encoding="utf-8") == "written"

    def test_close_none_is_noop(self):
        # EncodedFile with no file opened should not raise on close
        ef = EncodedFile.__new__(EncodedFile)
        ef.fo = None
        ef.close()  # must not raise


# ---------------------------------------------------------------------------
# TempFileMgr
# ---------------------------------------------------------------------------


class TestTempFileMgr:
    def test_repr(self):
        m = TempFileMgr()
        assert repr(m) == "TempFileMgr()"

    def test_new_temp_fn_returns_string(self):
        m = TempFileMgr()
        fn = m.new_temp_fn()
        assert isinstance(fn, str)

    def test_new_temp_fn_registered(self):
        m = TempFileMgr()
        fn = m.new_temp_fn()
        assert fn in m.temp_file_names

    def test_multiple_new_temp_fns_unique(self):
        m = TempFileMgr()
        fns = [m.new_temp_fn() for _ in range(5)]
        assert len(set(fns)) == 5

    def test_remove_all_handles_nonexistent_files(self):
        m = TempFileMgr()
        m.temp_file_names = ["/tmp/this_file_does_not_exist_xyz_123.tmp"]
        m.remove_all()  # should not raise

    def test_remove_all_deletes_existing_file(self, tmp_path):
        path = tmp_path / "tmpfile.tmp"
        path.write_text("temp")
        m = TempFileMgr()
        m.temp_file_names = [str(path)]
        m.remove_all()
        assert not path.exists()

    def test_remove_all_empty_list_noop(self):
        m = TempFileMgr()
        m.remove_all()  # no files registered → should not raise


# ---------------------------------------------------------------------------
# list_encodings
# ---------------------------------------------------------------------------


class TestListEncodings:
    def test_prints_encodings(self, capsys):
        list_encodings()
        captured = capsys.readouterr()
        assert "Encodings:" in captured.out

    def test_output_contains_utf8(self, capsys):
        list_encodings()
        captured = capsys.readouterr()
        # codec_dict key is "utf8" (no underscore)
        assert "utf8" in captured.out


# ---------------------------------------------------------------------------
# FileWriter.FileControl
# ---------------------------------------------------------------------------


class TestFileControlTryOpen:
    def test_status_remains_waiting_on_open_failure(self, tmp_path):
        """When io.open() fails, status must stay STATUS_WAITING, not STATUS_OPEN."""
        # Use a path inside a non-existent directory so io.open() will fail
        bad_path = str(tmp_path / "no_such_dir" / "file.txt")
        fc = FileWriter.FileControl(bad_path, open_timeout=600)
        fc.try_open()
        assert fc.status == fc.STATUS_WAITING
