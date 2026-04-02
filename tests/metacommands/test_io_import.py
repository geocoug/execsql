"""Unit tests for execsql metacommand handlers in metacommands/io_import.py.

Covers x_import, x_import_file, x_import_ods, x_import_ods_pattern,
x_import_xls, x_import_xls_pattern, x_import_parquet, x_import_feather,
x_import_row_buffer, and x_show_progress handlers.

All downstream importer functions are mocked since they have their own tests.
State objects (_state.dbs, _state.exec_log, _state.subvars, _state.conf)
are set up via helpers that mirror the pattern in test_metacommands_data.py.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import SubVarSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_exec_log():
    """Install a mock exec_log on _state and return it."""
    mock_log = MagicMock()
    _state.exec_log = mock_log
    return mock_log


def _setup_dbs():
    """Install a mock DatabasePool on _state and return the mock db."""
    mock_db = MagicMock()
    mock_dbs = MagicMock()
    mock_dbs.current.return_value = mock_db
    _state.dbs = mock_dbs
    return mock_db


def _setup_subvars():
    """Install a real SubVarSet on _state and return it."""
    sv = SubVarSet()
    _state.subvars = sv
    return sv


# ---------------------------------------------------------------------------
# x_import
# ---------------------------------------------------------------------------


class TestXImport:
    """Tests for the IMPORT (CSV/delimited) metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "new": None,
            "schema": None,
            "table": "mytable",
            "filename": filename,
            "quotechar": None,
            "delimchar": None,
            "encoding": None,
            "skip": None,
            "metacommandline": "IMPORT mytable FROM file.csv",
        }
        kwargs.update(overrides)
        return kwargs

    def test_happy_path_calls_importtable(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("a,b\n1,2\n")

        with (
            patch("execsql.metacommands.io_import.importtable") as mock_imp,
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024-01-01")),
        ):
            x_import(**self._base_kwargs(str(csv)))
            mock_imp.assert_called_once()

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        missing = str(tmp_path / "nosuchfile.csv")
        with pytest.raises(ErrInfo):
            x_import(**self._base_kwargs(missing))

    def test_tilde_path_expanded(self, minimal_conf, tmp_path):
        """Tilde prefix is expanded to the home directory."""
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()

        # Simulate a tilde path: "~/tilde_test.csv" but point it to our tmp file
        # by patching Path.exists
        tilde_filename = f"~{os.sep}tilde_test.csv"

        with (
            patch("execsql.metacommands.io_import.Path") as mock_path_cls,
            patch("execsql.metacommands.io_import.importtable"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024-01-01")),
        ):
            # Make Path(filename).exists() return True
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_cls.return_value = mock_path_instance
            mock_path_cls.home.return_value = MagicMock()

            x_import(**self._base_kwargs(tilde_filename))
            # The tilde expansion ran (filename[0] == "~" and filename[1] == os.sep)
            mock_path_cls.home.assert_called()

    def test_new_flag_replacement(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("a\n1\n")

        captured = {}

        def capture_importtable(db, schema, table, filename, is_new, **kw):
            captured["is_new"] = is_new

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=capture_importtable),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            x_import(**self._base_kwargs(str(csv), new="replacement"))
            assert captured["is_new"] == 2

    def test_new_flag_new(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("a\n1\n")

        captured = {}

        def capture_importtable(db, schema, table, filename, is_new, **kw):
            captured["is_new"] = is_new

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=capture_importtable),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            x_import(**self._base_kwargs(str(csv), new="new"))
            assert captured["is_new"] == 1

    def test_delimchar_tab_converted(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        tsv = tmp_path / "data.tsv"
        tsv.write_text("a\tb\n1\t2\n")

        captured = {}

        def capture(db, schema, table, filename, is_new, delimchar=None, **kw):
            captured["delimchar"] = delimchar

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=capture),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            x_import(**self._base_kwargs(str(tsv), delimchar="tab"))
            assert captured["delimchar"] == chr(9)

    def test_delimchar_unitsep_converted(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.txt"
        f.write_text("a" + chr(31) + "b\n")

        captured = {}

        def capture(db, schema, table, filename, is_new, delimchar=None, **kw):
            captured["delimchar"] = delimchar

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=capture),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            x_import(**self._base_kwargs(str(f), delimchar="us"))
            assert captured["delimchar"] == chr(31)

    def test_delimchar_unitsep_alias(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.txt"
        f.write_text("a" + chr(31) + "b\n")

        captured = {}

        def capture(db, schema, table, filename, is_new, delimchar=None, **kw):
            captured["delimchar"] = delimchar

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=capture),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            x_import(**self._base_kwargs(str(f), delimchar="unitsep"))
            assert captured["delimchar"] == chr(31)

    def test_skip_header_lines_int_conversion(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("comment\nheader\na\n1\n")

        captured = {}

        def capture(db, schema, table, filename, is_new, junk_header_lines=0, **kw):
            captured["junk"] = junk_header_lines

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=capture),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            x_import(**self._base_kwargs(str(csv), skip="2"))
            assert captured["junk"] == 2

    def test_importtable_generic_exception_wrapped_as_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("a\n1\n")

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=RuntimeError("boom")),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
            pytest.raises(ErrInfo),
        ):
            x_import(**self._base_kwargs(str(csv)))

    def test_importtable_errinfo_propagated(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("a\n1\n")

        inner = ErrInfo(type="cmd", other_msg="inner error")

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=inner),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            with pytest.raises(ErrInfo) as exc_info:
                x_import(**self._base_kwargs(str(csv)))
            # Should be the exact same ErrInfo, not wrapped
            assert exc_info.value is inner

    def test_quotechar_lowercased(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("a\n1\n")

        captured = {}

        def capture(db, schema, table, filename, is_new, quotechar=None, **kw):
            captured["quotechar"] = quotechar

        with (
            patch("execsql.metacommands.io_import.importtable", side_effect=capture),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            x_import(**self._base_kwargs(str(csv), quotechar="DOUBLE"))
            assert captured["quotechar"] == "double"

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import

        _setup_exec_log()
        _setup_dbs()
        csv = tmp_path / "data.csv"
        csv.write_text("a\n1\n")

        with (
            patch("execsql.metacommands.io_import.importtable"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1KB", "2024")),
        ):
            result = x_import(**self._base_kwargs(str(csv)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_file
# ---------------------------------------------------------------------------


class TestXImportFile:
    """Tests for the IMPORT FILE metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "schema": None,
            "table": "mytable",
            "columnname": "mycolumn",
            "filename": filename,
            "metacommandline": "IMPORT FILE ...",
        }
        kwargs.update(overrides)
        return kwargs

    def test_happy_path_calls_importfile(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_file

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "blob.bin"
        f.write_bytes(b"\x00\x01\x02")

        with (
            patch("execsql.metacommands.io_import.importfile") as mock_imp,
            patch("execsql.metacommands.conditions.file_size_date", return_value=("3B", "2024-01-01")),
        ):
            x_import_file(**self._base_kwargs(str(f)))
            mock_imp.assert_called_once()

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_file

        _setup_exec_log()
        missing = str(tmp_path / "nosuch.bin")
        with pytest.raises(ErrInfo):
            x_import_file(**self._base_kwargs(missing))

    def test_importfile_generic_exception_wrapped(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_file

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.bin"
        f.write_bytes(b"data")

        with (
            patch("execsql.metacommands.io_import.importfile", side_effect=RuntimeError("boom")),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
            pytest.raises(ErrInfo),
        ):
            x_import_file(**self._base_kwargs(str(f)))

    def test_importfile_errinfo_propagated(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_file

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.bin"
        f.write_bytes(b"data")

        inner = ErrInfo(type="cmd", other_msg="inner")

        with (
            patch("execsql.metacommands.io_import.importfile", side_effect=inner),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
        ):
            with pytest.raises(ErrInfo) as exc_info:
                x_import_file(**self._base_kwargs(str(f)))
            assert exc_info.value is inner

    def test_log_status_info_called(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_file

        mock_log = _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"pdf content")

        with (
            patch("execsql.metacommands.io_import.importfile"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("10B", "2024")),
        ):
            x_import_file(**self._base_kwargs(str(f)))
            mock_log.log_status_info.assert_called_once()

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_file

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.bin"
        f.write_bytes(b"x")

        with (
            patch("execsql.metacommands.io_import.importfile"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("1B", "2024")),
        ):
            result = x_import_file(**self._base_kwargs(str(f)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_ods
# ---------------------------------------------------------------------------


class TestXImportOds:
    """Tests for the IMPORT ODS metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "new": None,
            "schema": None,
            "table": "mytable",
            "filename": filename,
            "sheetname": "Sheet1",
            "skip": None,
            "metacommandline": "IMPORT ODS ...",
        }
        kwargs.update(overrides)
        return kwargs

    def test_happy_path_calls_importods(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods

        _setup_dbs()
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")  # dummy ODS (zip) content

        with patch("execsql.metacommands.io_import.importods") as mock_imp:
            x_import_ods(**self._base_kwargs(str(f)))
            mock_imp.assert_called_once()

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods

        _setup_dbs()
        missing = str(tmp_path / "nosuch.ods")
        with pytest.raises(ErrInfo):
            x_import_ods(**self._base_kwargs(missing))

    def test_new_flag_sets_is_new(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods

        _setup_dbs()
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        captured = {}

        def capture(db, schema, table, is_new, *args, **kw):
            captured["is_new"] = is_new

        with patch("execsql.metacommands.io_import.importods", side_effect=capture):
            x_import_ods(**self._base_kwargs(str(f), new="new"))
            assert captured["is_new"] == 1

    def test_skip_int_conversion(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods

        _setup_dbs()
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        captured = {}

        def capture(db, schema, table, is_new, filename, sheetname, hdr_rows):
            captured["hdr_rows"] = hdr_rows

        with patch("execsql.metacommands.io_import.importods", side_effect=capture):
            x_import_ods(**self._base_kwargs(str(f), skip="3"))
            assert captured["hdr_rows"] == 3

    def test_importods_generic_exception_wrapped(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods

        _setup_dbs()
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        with (
            patch("execsql.metacommands.io_import.importods", side_effect=RuntimeError("crash")),
            pytest.raises(ErrInfo),
        ):
            x_import_ods(**self._base_kwargs(str(f)))

    def test_importods_errinfo_propagated(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods

        _setup_dbs()
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")
        inner = ErrInfo(type="cmd", other_msg="inner")

        with patch("execsql.metacommands.io_import.importods", side_effect=inner):
            with pytest.raises(ErrInfo) as exc_info:
                x_import_ods(**self._base_kwargs(str(f)))
            assert exc_info.value is inner

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods

        _setup_dbs()
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        with patch("execsql.metacommands.io_import.importods"):
            result = x_import_ods(**self._base_kwargs(str(f)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_ods_pattern
# ---------------------------------------------------------------------------


class TestXImportOdsPattern:
    """Tests for the IMPORT ODS (pattern) metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "new": None,
            "schema": None,
            "filename": filename,
            "patn": ".*",
            "skip": None,
            "metacommandline": "IMPORT ODS PATTERN ...",
        }
        kwargs.update(overrides)
        return kwargs

    def _mock_odsfile(self, sheets):
        """Return a mock OdsFile that reports the given sheet names."""
        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = sheets
        return mock_wbk

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        missing = str(tmp_path / "nosuch.ods")
        with pytest.raises(ErrInfo):
            x_import_ods_pattern(**self._base_kwargs(missing))

    def test_invalid_ods_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "bad.ods"
        f.write_bytes(b"not an ods file")

        with patch("execsql.metacommands.io_import.OdsFile") as MockOdsFile:
            mock_wbk = MagicMock()
            mock_wbk.open.side_effect = Exception("not a valid ODS")
            MockOdsFile.return_value = mock_wbk
            with pytest.raises(ErrInfo):
                x_import_ods_pattern(**self._base_kwargs(str(f)))

    def test_sheets_imported_subvar_set(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["Sales", "Inventory", "Notes"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods"),
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f), patn="Sales|Inventory"))
            assert sv.sub_exists("$SHEETS_IMPORTED")
            assert sv.sub_exists("$SHEETS_TABLES")
            assert sv.sub_exists("$SHEETS_TABLES_VALUES")

    def test_sheets_tables_values_with_schema(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["Sheet1"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods"),
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f), schema="myschema"))
            val = sv._subs_dict["$sheets_tables_values"]
            assert "myschema" in val

    def test_sheets_tables_values_no_schema(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["Sheet1"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods"),
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f), schema=None))
            val = sv._subs_dict["$sheets_tables_values"]
            # No schema prefix — value wraps table name in parentheses
            assert "myschema" not in val

    def test_pattern_filters_sheets(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["Sales", "Template", "Notes"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods") as mock_imp,
        ):
            # Only import sheets matching "sales"
            x_import_ods_pattern(**self._base_kwargs(str(f), patn="sales"))
            assert mock_imp.call_count == 1
            imported = sv._subs_dict["$sheets_imported"]
            assert "Sales" in imported
            assert "Template" not in imported

    def test_clean_col_hdrs_applied(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = True
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["My Sheet"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods"),
            patch("execsql.metacommands.io_import.clean_words", return_value=["my_sheet"]) as mock_clean,
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f)))
            mock_clean.assert_called_once()

    def test_fold_col_hdrs_applied(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "lower"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["MySheet"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods"),
            patch("execsql.metacommands.io_import.fold_words", return_value=["mysheet"]) as mock_fold,
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f)))
            mock_fold.assert_called_once()

    def test_importods_generic_exception_wrapped(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["Sheet1"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods", side_effect=RuntimeError("crash")),
            pytest.raises(ErrInfo),
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f)))

    def test_skip_int_conversion(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["Sheet1"])
        captured = {}

        def capture(db, schema, table, is_new, filename, sheetname, hdr_rows):
            captured["hdr_rows"] = hdr_rows

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods", side_effect=capture),
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f), skip="4"))
            assert captured["hdr_rows"] == 4

    def test_no_matching_sheets_imports_nothing(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile(["Alpha", "Beta"])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods") as mock_imp,
        ):
            x_import_ods_pattern(**self._base_kwargs(str(f), patn="zzznomatch"))
            assert mock_imp.call_count == 0
            assert sv._subs_dict["$sheets_imported"] == ""

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_ods_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        mock_wbk = self._mock_odsfile([])

        with (
            patch("execsql.metacommands.io_import.OdsFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importods"),
        ):
            result = x_import_ods_pattern(**self._base_kwargs(str(f)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_xls
# ---------------------------------------------------------------------------


class TestXImportXls:
    """Tests for the IMPORT XLS metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "new": None,
            "schema": None,
            "table": "mytable",
            "filename": filename,
            "sheetname": "Sheet1",
            "skip": None,
            "encoding": None,
            "metacommandline": "IMPORT XLS ...",
        }
        kwargs.update(overrides)
        return kwargs

    def test_happy_path_calls_importxls(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls

        _setup_dbs()
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        with patch("execsql.metacommands.io_import.importxls") as mock_imp:
            x_import_xls(**self._base_kwargs(str(f)))
            mock_imp.assert_called_once()

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls

        _setup_dbs()
        missing = str(tmp_path / "nosuch.xlsx")
        with pytest.raises(ErrInfo):
            x_import_xls(**self._base_kwargs(missing))

    def test_new_flag_replacement(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls

        _setup_dbs()
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        captured = {}

        def capture(db, schema, table, is_new, *args):
            captured["is_new"] = is_new

        with patch("execsql.metacommands.io_import.importxls", side_effect=capture):
            x_import_xls(**self._base_kwargs(str(f), new="replacement"))
            assert captured["is_new"] == 2

    def test_skip_int_conversion(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls

        _setup_dbs()
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        captured = {}

        def capture(db, schema, table, is_new, filename, sheetname, junk_hdrs, encoding):
            captured["junk_hdrs"] = junk_hdrs

        with patch("execsql.metacommands.io_import.importxls", side_effect=capture):
            x_import_xls(**self._base_kwargs(str(f), skip="5"))
            assert captured["junk_hdrs"] == 5

    def test_importxls_generic_exception_wrapped(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls

        _setup_dbs()
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        with (
            patch("execsql.metacommands.io_import.importxls", side_effect=RuntimeError("crash")),
            pytest.raises(ErrInfo),
        ):
            x_import_xls(**self._base_kwargs(str(f)))

    def test_importxls_errinfo_propagated(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls

        _setup_dbs()
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")
        inner = ErrInfo(type="cmd", other_msg="inner")

        with patch("execsql.metacommands.io_import.importxls", side_effect=inner):
            with pytest.raises(ErrInfo) as exc_info:
                x_import_xls(**self._base_kwargs(str(f)))
            assert exc_info.value is inner

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls

        _setup_dbs()
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        with patch("execsql.metacommands.io_import.importxls"):
            result = x_import_xls(**self._base_kwargs(str(f)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_xls_pattern
# ---------------------------------------------------------------------------


class TestXImportXlsPattern:
    """Tests for the IMPORT XLS (pattern) metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "new": None,
            "schema": None,
            "filename": filename,
            "patn": ".*",
            "skip": None,
            "encoding": None,
            "metacommandline": "IMPORT XLS PATTERN ...",
        }
        kwargs.update(overrides)
        return kwargs

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        missing = str(tmp_path / "nosuch.xlsx")
        with pytest.raises(ErrInfo):
            x_import_xls_pattern(**self._base_kwargs(missing))

    def test_short_filename_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        # File must exist but have a name too short to determine extension
        f = tmp_path / "ab"
        f.write_bytes(b"PK")

        with pytest.raises(ErrInfo):
            x_import_xls_pattern(**self._base_kwargs(str(f)))

    def test_unrecognized_extension_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.ods"
        f.write_bytes(b"PK")

        with pytest.raises(ErrInfo):
            x_import_xls_pattern(**self._base_kwargs(str(f)))

    def test_invalid_xls_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "bad.xls"
        f.write_bytes(b"notexcel")

        with patch("execsql.metacommands.io_import.XlsFile") as MockXls:
            mock_wbk = MagicMock()
            mock_wbk.open.side_effect = Exception("bad xls")
            MockXls.return_value = mock_wbk
            with pytest.raises(ErrInfo):
                x_import_xls_pattern(**self._base_kwargs(str(f)))

    def test_xlsx_extension_uses_xlsxfile(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        with (
            patch("execsql.metacommands.io_import.XlsxFile") as MockXlsx,
            patch("execsql.metacommands.io_import.importxls"),
        ):
            mock_wbk = MagicMock()
            mock_wbk.sheetnames.return_value = ["Sheet1"]
            MockXlsx.return_value = mock_wbk
            x_import_xls_pattern(**self._base_kwargs(str(f)))
            MockXlsx.assert_called_once()

    def test_xls_extension_uses_xlsfile(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xls"
        f.write_bytes(b"PK")

        with (
            patch("execsql.metacommands.io_import.XlsFile") as MockXls,
            patch("execsql.metacommands.io_import.importxls"),
        ):
            mock_wbk = MagicMock()
            mock_wbk.sheetnames.return_value = ["Sheet1"]
            MockXls.return_value = mock_wbk
            x_import_xls_pattern(**self._base_kwargs(str(f)))
            MockXls.assert_called_once()

    def test_sheets_imported_subvar_set(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = ["Sales", "Data"]

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls"),
        ):
            x_import_xls_pattern(**self._base_kwargs(str(f)))
            assert sv.sub_exists("$SHEETS_IMPORTED")
            assert sv.sub_exists("$SHEETS_TABLES")
            assert sv.sub_exists("$SHEETS_TABLES_VALUES")

    def test_sheets_tables_values_with_schema(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = ["Sheet1"]

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls"),
        ):
            x_import_xls_pattern(**self._base_kwargs(str(f), schema="myschema"))
            val = sv._subs_dict["$sheets_tables_values"]
            assert "myschema" in val

    def test_sheets_tables_values_no_schema(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = ["Sheet1"]

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls"),
        ):
            x_import_xls_pattern(**self._base_kwargs(str(f), schema=None))
            val = sv._subs_dict["$sheets_tables_values"]
            assert "myschema" not in val

    def test_pattern_filters_sheets(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        sv = _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = ["Sales", "Template", "Notes"]

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls") as mock_imp,
        ):
            x_import_xls_pattern(**self._base_kwargs(str(f), patn="sales"))
            assert mock_imp.call_count == 1
            imported = sv._subs_dict["$sheets_imported"]
            assert "Sales" in imported
            assert "Template" not in imported

    def test_clean_col_hdrs_applied(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = True
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = ["My Sheet"]

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls"),
            patch("execsql.metacommands.io_import.clean_words", return_value=["my_sheet"]) as mock_clean,
        ):
            x_import_xls_pattern(**self._base_kwargs(str(f)))
            mock_clean.assert_called_once()

    def test_fold_col_hdrs_applied(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "upper"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = ["MySheet"]

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls"),
            patch("execsql.metacommands.io_import.fold_words", return_value=["MYSHEET"]) as mock_fold,
        ):
            x_import_xls_pattern(**self._base_kwargs(str(f)))
            mock_fold.assert_called_once()

    def test_importxls_generic_exception_wrapped(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = ["Sheet1"]

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls", side_effect=RuntimeError("crash")),
            pytest.raises(ErrInfo),
        ):
            x_import_xls_pattern(**self._base_kwargs(str(f)))

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_xls_pattern

        _setup_dbs()
        _setup_subvars()
        minimal_conf.clean_col_hdrs = False
        minimal_conf.fold_col_hdrs = "no"
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")

        mock_wbk = MagicMock()
        mock_wbk.sheetnames.return_value = []

        with (
            patch("execsql.metacommands.io_import.XlsxFile", return_value=mock_wbk),
            patch("execsql.metacommands.io_import.importxls"),
        ):
            result = x_import_xls_pattern(**self._base_kwargs(str(f)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_parquet
# ---------------------------------------------------------------------------


class TestXImportParquet:
    """Tests for the IMPORT PARQUET metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "new": None,
            "schema": None,
            "table": "mytable",
            "filename": filename,
            "metacommandline": "IMPORT PARQUET ...",
        }
        kwargs.update(overrides)
        return kwargs

    def test_happy_path_calls_import_parquet(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.parquet"
        f.write_bytes(b"PAR1")

        with (
            patch("execsql.metacommands.io_import.import_parquet") as mock_imp,
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
        ):
            x_import_parquet(**self._base_kwargs(str(f)))
            mock_imp.assert_called_once()

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        _setup_exec_log()
        missing = str(tmp_path / "nosuch.parquet")
        with pytest.raises(ErrInfo):
            x_import_parquet(**self._base_kwargs(missing))

    def test_tilde_path_expanded(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        _setup_exec_log()
        _setup_dbs()
        tilde_filename = f"~{os.sep}data.parquet"

        with (
            patch("execsql.metacommands.io_import.Path") as mock_path_cls,
            patch("execsql.metacommands.io_import.import_parquet"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
        ):
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_cls.return_value = mock_path_instance
            mock_path_cls.home.return_value = MagicMock()

            x_import_parquet(**self._base_kwargs(tilde_filename))
            mock_path_cls.home.assert_called()

    def test_new_flag_replacement(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.parquet"
        f.write_bytes(b"PAR1")

        captured = {}

        def capture(db, schema, table, filename, is_new):
            captured["is_new"] = is_new

        with (
            patch("execsql.metacommands.io_import.import_parquet", side_effect=capture),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
        ):
            x_import_parquet(**self._base_kwargs(str(f), new="replacement"))
            assert captured["is_new"] == 2

    def test_generic_exception_wrapped(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.parquet"
        f.write_bytes(b"PAR1")

        with (
            patch("execsql.metacommands.io_import.import_parquet", side_effect=RuntimeError("crash")),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
            pytest.raises(ErrInfo),
        ):
            x_import_parquet(**self._base_kwargs(str(f)))

    def test_errinfo_propagated(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.parquet"
        f.write_bytes(b"PAR1")
        inner = ErrInfo(type="cmd", other_msg="inner")

        with (
            patch("execsql.metacommands.io_import.import_parquet", side_effect=inner),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
        ):
            with pytest.raises(ErrInfo) as exc_info:
                x_import_parquet(**self._base_kwargs(str(f)))
            assert exc_info.value is inner

    def test_log_status_info_called(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        mock_log = _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.parquet"
        f.write_bytes(b"PAR1")

        with (
            patch("execsql.metacommands.io_import.import_parquet"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
        ):
            x_import_parquet(**self._base_kwargs(str(f)))
            mock_log.log_status_info.assert_called_once()

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_parquet

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.parquet"
        f.write_bytes(b"PAR1")

        with (
            patch("execsql.metacommands.io_import.import_parquet"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("4B", "2024")),
        ):
            result = x_import_parquet(**self._base_kwargs(str(f)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_feather
# ---------------------------------------------------------------------------


class TestXImportFeather:
    """Tests for the IMPORT FEATHER metacommand handler."""

    def _base_kwargs(self, filename: str, **overrides) -> dict:
        kwargs = {
            "new": None,
            "schema": None,
            "table": "mytable",
            "filename": filename,
            "metacommandline": "IMPORT FEATHER ...",
        }
        kwargs.update(overrides)
        return kwargs

    def test_happy_path_calls_import_feather(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.feather"
        f.write_bytes(b"FEATHER")

        with (
            patch("execsql.metacommands.io_import.import_feather") as mock_imp,
            patch("execsql.metacommands.conditions.file_size_date", return_value=("7B", "2024")),
        ):
            x_import_feather(**self._base_kwargs(str(f)))
            mock_imp.assert_called_once()

    def test_nonexistent_file_raises_errinfo(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        _setup_exec_log()
        missing = str(tmp_path / "nosuch.feather")
        with pytest.raises(ErrInfo):
            x_import_feather(**self._base_kwargs(missing))

    def test_tilde_path_expanded(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        _setup_exec_log()
        _setup_dbs()
        tilde_filename = f"~{os.sep}data.feather"

        with (
            patch("execsql.metacommands.io_import.Path") as mock_path_cls,
            patch("execsql.metacommands.io_import.import_feather"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("7B", "2024")),
        ):
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_cls.return_value = mock_path_instance
            mock_path_cls.home.return_value = MagicMock()

            x_import_feather(**self._base_kwargs(tilde_filename))
            mock_path_cls.home.assert_called()

    def test_new_flag_new(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.feather"
        f.write_bytes(b"FEATHER")

        captured = {}

        def capture(db, schema, table, filename, is_new):
            captured["is_new"] = is_new

        with (
            patch("execsql.metacommands.io_import.import_feather", side_effect=capture),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("7B", "2024")),
        ):
            x_import_feather(**self._base_kwargs(str(f), new="new"))
            assert captured["is_new"] == 1

    def test_generic_exception_wrapped(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.feather"
        f.write_bytes(b"FEATHER")

        with (
            patch("execsql.metacommands.io_import.import_feather", side_effect=RuntimeError("crash")),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("7B", "2024")),
            pytest.raises(ErrInfo),
        ):
            x_import_feather(**self._base_kwargs(str(f)))

    def test_errinfo_propagated(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.feather"
        f.write_bytes(b"FEATHER")
        inner = ErrInfo(type="cmd", other_msg="inner")

        with (
            patch("execsql.metacommands.io_import.import_feather", side_effect=inner),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("7B", "2024")),
        ):
            with pytest.raises(ErrInfo) as exc_info:
                x_import_feather(**self._base_kwargs(str(f)))
            assert exc_info.value is inner

    def test_log_status_info_called(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        mock_log = _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.feather"
        f.write_bytes(b"FEATHER")

        with (
            patch("execsql.metacommands.io_import.import_feather"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("7B", "2024")),
        ):
            x_import_feather(**self._base_kwargs(str(f)))
            mock_log.log_status_info.assert_called_once()

    def test_returns_none(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_import import x_import_feather

        _setup_exec_log()
        _setup_dbs()
        f = tmp_path / "data.feather"
        f.write_bytes(b"FEATHER")

        with (
            patch("execsql.metacommands.io_import.import_feather"),
            patch("execsql.metacommands.conditions.file_size_date", return_value=("7B", "2024")),
        ):
            result = x_import_feather(**self._base_kwargs(str(f)))
            assert result is None


# ---------------------------------------------------------------------------
# x_import_row_buffer
# ---------------------------------------------------------------------------


class TestXImportRowBuffer:
    """Tests for the IMPORT ROW BUFFER metacommand handler."""

    def test_sets_conf_import_row_buffer(self, minimal_conf):
        from execsql.metacommands.io_import import x_import_row_buffer

        x_import_row_buffer(rows="2500")
        assert minimal_conf.import_row_buffer == 2500

    def test_integer_conversion(self, minimal_conf):
        from execsql.metacommands.io_import import x_import_row_buffer

        x_import_row_buffer(rows="100")
        assert isinstance(minimal_conf.import_row_buffer, int)
        assert minimal_conf.import_row_buffer == 100


# ---------------------------------------------------------------------------
# x_show_progress
# ---------------------------------------------------------------------------


class TestXShowProgress:
    """Tests for the SHOW PROGRESS metacommand handler."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("on", True),
            ("true", True),
            ("1", True),
            ("no", False),
            ("off", False),
            ("false", False),
            ("0", False),
        ],
    )
    def test_show_progress_flag(self, minimal_conf, value, expected):
        from execsql.metacommands.io_import import x_show_progress

        x_show_progress(setting=value)
        assert minimal_conf.show_progress is expected

    def test_case_insensitive(self, minimal_conf):
        from execsql.metacommands.io_import import x_show_progress

        x_show_progress(setting="YES")
        assert minimal_conf.show_progress is True

        x_show_progress(setting="NO")
        assert minimal_conf.show_progress is False


# ---------------------------------------------------------------------------
# Parametrize: new= kwarg mapping across handlers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "handler_name,extra_kwargs",
    [
        ("x_import_ods", {"sheetname": "Sheet1"}),
        ("x_import_xls", {"sheetname": "Sheet1", "encoding": None}),
    ],
)
@pytest.mark.parametrize(
    "new_value,expected_is_new",
    [
        (None, 0),
        ("new", 1),
        ("replacement", 2),
    ],
)
def test_is_new_mapping(minimal_conf, tmp_path, handler_name, extra_kwargs, new_value, expected_is_new):
    """All import handlers map new=None/new/replacement to is_new 0/1/2."""
    import execsql.metacommands.io_import as io_import_mod

    handler = getattr(io_import_mod, handler_name)
    _setup_dbs()

    f = tmp_path / "data.bin"
    f.write_bytes(b"PK")

    captured = {}

    def capture(db, schema, table, is_new, *args, **kw):
        captured["is_new"] = is_new

    importer_name = "importods" if handler_name == "x_import_ods" else "importxls"

    with patch(f"execsql.metacommands.io_import.{importer_name}", side_effect=capture):
        kwargs = {
            "new": new_value,
            "schema": None,
            "table": "t",
            "filename": str(f),
            "skip": None,
            "metacommandline": f"{handler_name} ...",
            **extra_kwargs,
        }
        handler(**kwargs)
        assert captured["is_new"] == expected_is_new
