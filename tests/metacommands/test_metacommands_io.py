"""Unit tests for execsql metacommand handlers in metacommands/io.py.

Tests the handler functions directly with appropriate state mocking,
focusing on testable behaviour without side effects. Uses tmp_path
for file outputs.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_exec_log():
    """Install a mock exec_log on _state."""
    mock_log = MagicMock()
    _state.exec_log = mock_log
    return mock_log


def _setup_output():
    """Install a mock output on _state."""
    mock_output = MagicMock()
    _state.output = mock_output
    return mock_output


# ---------------------------------------------------------------------------
# Tests for x_write
# ---------------------------------------------------------------------------


class TestXWrite:
    """Tests for the WRITE metacommand handler."""

    def test_write_to_stdout(self, minimal_conf):
        from execsql.metacommands.io import x_write

        mock_output = _setup_output()
        minimal_conf.write_prefix = None
        minimal_conf.write_suffix = None
        minimal_conf.tee_write_log = False

        x_write(text="hello world", tee=None, filename=None, metacommandline="WRITE hello world")
        mock_output.write.assert_called_once_with("hello world\n")

    def test_write_to_file(self, minimal_conf, tmp_path):
        from execsql.metacommands.io import x_write

        _setup_output()
        minimal_conf.write_prefix = None
        minimal_conf.write_suffix = None
        minimal_conf.tee_write_log = False

        outfile = str(tmp_path / "out.txt")

        with (
            patch("execsql.metacommands.io_write.filewriter_write") as mock_fw,
            patch("execsql.metacommands.io_write.check_dir"),
        ):
            x_write(text="file output", tee=None, filename=outfile, metacommandline="WRITE ...")
            mock_fw.assert_called_once_with(outfile, "file output\n")

    def test_write_with_tee(self, minimal_conf, tmp_path):
        from execsql.metacommands.io import x_write

        mock_output = _setup_output()
        minimal_conf.write_prefix = None
        minimal_conf.write_suffix = None
        minimal_conf.tee_write_log = False

        outfile = str(tmp_path / "out.txt")

        with patch("execsql.metacommands.io_write.filewriter_write"), patch("execsql.metacommands.io_write.check_dir"):
            x_write(text="tee output", tee="TEE", filename=outfile, metacommandline="WRITE ...")
            # With tee, output.write should also be called
            mock_output.write.assert_called_once_with("tee output\n")

    def test_write_with_prefix(self, minimal_conf):
        from execsql.metacommands.io import x_write

        mock_output = _setup_output()
        minimal_conf.write_prefix = "PREFIX:"
        minimal_conf.write_suffix = None
        minimal_conf.tee_write_log = False

        with patch("execsql.metacommands.io_write.substitute_vars", side_effect=lambda x: x):
            x_write(text="msg", tee=None, filename=None, metacommandline="WRITE msg")
            mock_output.write.assert_called_once_with("PREFIX: msg\n")

    def test_write_with_suffix(self, minimal_conf):
        from execsql.metacommands.io import x_write

        mock_output = _setup_output()
        minimal_conf.write_prefix = None
        minimal_conf.write_suffix = ":SUFFIX"
        minimal_conf.tee_write_log = False

        with patch("execsql.metacommands.io_write.substitute_vars", side_effect=lambda x: x):
            x_write(text="msg", tee=None, filename=None, metacommandline="WRITE msg")
            mock_output.write.assert_called_once_with("msg :SUFFIX\n")

    def test_write_with_tee_write_log(self, minimal_conf):
        from execsql.metacommands.io import x_write

        _setup_output()
        mock_log = _setup_exec_log()
        minimal_conf.write_prefix = None
        minimal_conf.write_suffix = None
        minimal_conf.tee_write_log = True

        x_write(text="logged", tee=None, filename=None, metacommandline="WRITE logged")
        mock_log.log_user_msg.assert_called_once_with("logged\n")


# ---------------------------------------------------------------------------
# Tests for x_write_prefix / x_write_suffix
# ---------------------------------------------------------------------------


class TestXWritePrefixSuffix:
    """Tests for WRITE PREFIX and WRITE SUFFIX metacommand handlers."""

    def test_write_prefix_set(self, minimal_conf):
        from execsql.metacommands.io import x_write_prefix

        minimal_conf.write_prefix = None
        x_write_prefix(prefix="[INFO]")
        assert minimal_conf.write_prefix == "[INFO]"

    def test_write_prefix_clear(self, minimal_conf):
        from execsql.metacommands.io import x_write_prefix

        minimal_conf.write_prefix = "[INFO]"
        x_write_prefix(prefix="CLEAR")
        assert minimal_conf.write_prefix is None

    def test_write_prefix_clear_case_insensitive(self, minimal_conf):
        from execsql.metacommands.io import x_write_prefix

        minimal_conf.write_prefix = "[INFO]"
        x_write_prefix(prefix="clear")
        assert minimal_conf.write_prefix is None

    def test_write_suffix_set(self, minimal_conf):
        from execsql.metacommands.io import x_write_suffix

        minimal_conf.write_suffix = None
        x_write_suffix(suffix="[END]")
        assert minimal_conf.write_suffix == "[END]"

    def test_write_suffix_clear(self, minimal_conf):
        from execsql.metacommands.io import x_write_suffix

        minimal_conf.write_suffix = "[END]"
        x_write_suffix(suffix="CLEAR")
        assert minimal_conf.write_suffix is None


# ---------------------------------------------------------------------------
# Tests for x_rm_file
# ---------------------------------------------------------------------------


class TestXRmFile:
    """Tests for the DELETE FILE metacommand handler."""

    def test_rm_file_deletes_existing(self, minimal_conf, tmp_path):
        from execsql.metacommands.io import x_rm_file

        target = tmp_path / "deleteme.txt"
        target.write_text("content")
        assert target.exists()

        with patch("execsql.metacommands.io_fileops.filewriter_close"):
            x_rm_file(filename=str(target))

        assert not target.exists()

    def test_rm_file_nonexistent_is_noop(self, minimal_conf, tmp_path):
        from execsql.metacommands.io import x_rm_file

        target = str(tmp_path / "nosuchfile.txt")
        # Should not raise
        x_rm_file(filename=target)

    def test_rm_file_glob_pattern(self, minimal_conf, tmp_path):
        from execsql.metacommands.io import x_rm_file

        f1 = tmp_path / "data1.csv"
        f2 = tmp_path / "data2.csv"
        f3 = tmp_path / "keep.txt"
        f1.write_text("a")
        f2.write_text("b")
        f3.write_text("c")

        with patch("execsql.metacommands.io_fileops.filewriter_close"):
            x_rm_file(filename=str(tmp_path / "data*.csv"))

        assert not f1.exists()
        assert not f2.exists()
        assert f3.exists()


# ---------------------------------------------------------------------------
# Tests for x_make_export_dirs
# ---------------------------------------------------------------------------


class TestXMakeExportDirs:
    """Tests for MAKE EXPORT DIRS metacommand handler."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("on", True),
            ("true", True),
            ("1", True),
            ("no", False),
            ("off", False),
        ],
    )
    def test_make_export_dirs_flag(self, minimal_conf, value, expected):
        from execsql.metacommands.io import x_make_export_dirs

        x_make_export_dirs(setting=value)
        assert minimal_conf.make_export_dirs is expected


# ---------------------------------------------------------------------------
# Tests for x_cd
# ---------------------------------------------------------------------------


class TestXCd:
    """Tests for the CD metacommand handler."""

    def test_cd_changes_directory(self, minimal_conf, tmp_path):
        from execsql.metacommands.io import x_cd

        _setup_exec_log()
        mock_cl = MagicMock()
        mock_cl.current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 1),
        )
        _state.commandliststack = [mock_cl]

        original_dir = os.getcwd()
        try:
            x_cd(dir=str(tmp_path), metacommandline=f"CD {tmp_path}")
            assert os.getcwd() == str(tmp_path)
        finally:
            os.chdir(original_dir)

    def test_cd_nonexistent_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.io import x_cd

        with pytest.raises(ErrInfo):
            x_cd(dir=str(tmp_path / "nosuchdir"), metacommandline="CD nosuchdir")


# ---------------------------------------------------------------------------
# Tests for x_scan_lines
# ---------------------------------------------------------------------------


class TestXScanLines:
    """Tests for SCAN LINES metacommand handler."""

    def test_scan_lines_sets_conf(self, minimal_conf):
        from execsql.metacommands.io import x_scan_lines

        x_scan_lines(scanlines="500")
        assert minimal_conf.scan_lines == 500


# ---------------------------------------------------------------------------
# Tests for x_hdf5_text_len
# ---------------------------------------------------------------------------


class TestXHdf5TextLen:
    """Tests for HDF5 TEXT LEN metacommand handler."""

    def test_hdf5_text_len_sets_conf(self, minimal_conf):
        from execsql.metacommands.io import x_hdf5_text_len

        x_hdf5_text_len(textlen="1024")
        assert minimal_conf.hdf5_text_len == 1024


# ---------------------------------------------------------------------------
# Tests for x_include
# ---------------------------------------------------------------------------


class TestXInclude:
    """Tests for the INCLUDE metacommand handler (now handled by AST executor)."""

    def test_x_include_raises_in_ast_mode(self, minimal_conf):
        """x_include raises because INCLUDE is handled by the AST executor."""
        from execsql.metacommands.io import x_include

        with pytest.raises(ErrInfo, match="AST executor"):
            x_include(filename="anything.sql", exists=None)


# ---------------------------------------------------------------------------
# Tests for x_zip_buffer_mb
# ---------------------------------------------------------------------------


class TestXZipBufferMb:
    """Tests for ZIP BUFFER MB metacommand handler."""

    def test_zip_buffer_mb_sets_conf(self, minimal_conf):
        from execsql.metacommands.io import x_zip_buffer_mb

        minimal_conf.zip_buffer_mb = 0
        x_zip_buffer_mb(size="64")
        assert minimal_conf.zip_buffer_mb == 64


# ---------------------------------------------------------------------------
# Tests for x_import_row_buffer
# ---------------------------------------------------------------------------


class TestXImportRowBuffer:
    """Tests for IMPORT ROW BUFFER metacommand handler."""

    def test_import_row_buffer_sets_conf(self, minimal_conf):
        from execsql.metacommands.io import x_import_row_buffer

        x_import_row_buffer(rows="5000")
        assert minimal_conf.import_row_buffer == 5000


# ---------------------------------------------------------------------------
# Tests for x_export_row_buffer
# ---------------------------------------------------------------------------


class TestXExportRowBuffer:
    """Tests for EXPORT ROW BUFFER metacommand handler."""

    def test_export_row_buffer_sets_conf(self, minimal_conf):
        from execsql.metacommands.io import x_export_row_buffer

        x_export_row_buffer(rows="10000")
        assert minimal_conf.export_row_buffer == 10000


# ---------------------------------------------------------------------------
# Tests for _apply_output_dir
# ---------------------------------------------------------------------------


class TestApplyOutputDir:
    """Tests for the _apply_output_dir() helper."""

    def _fn(self):
        from execsql.metacommands.io import _apply_output_dir

        return _apply_output_dir

    def test_no_output_dir_returns_path_unchanged(self, minimal_conf):
        # No export_output_dir attribute on conf → passthrough
        assert not hasattr(minimal_conf, "export_output_dir") or not minimal_conf.export_output_dir
        fn = self._fn()
        assert fn("output.csv") == "output.csv"

    def test_relative_path_gets_prefix(self, minimal_conf, tmp_path):
        export_dir = str(tmp_path / "exports")
        minimal_conf.export_output_dir = export_dir
        fn = self._fn()
        result = fn("output.csv")
        assert result == str(Path(export_dir) / "output.csv")

    def test_stdout_unchanged(self, minimal_conf, tmp_path):
        minimal_conf.export_output_dir = str(tmp_path / "exports")
        fn = self._fn()
        assert fn("stdout") == "stdout"
        assert fn("STDOUT") == "STDOUT"

    def test_absolute_path_unchanged(self, minimal_conf, tmp_path):
        minimal_conf.export_output_dir = str(tmp_path / "exports")
        fn = self._fn()
        abs_path = str(tmp_path / "abs" / "path" / "output.csv")
        assert fn(abs_path) == abs_path

    def test_no_attr_returns_path(self, minimal_conf):
        """If conf has no export_output_dir attribute at all, passthrough."""
        if hasattr(minimal_conf, "export_output_dir"):
            del minimal_conf.export_output_dir
        fn = self._fn()
        assert fn("file.csv") == "file.csv"
