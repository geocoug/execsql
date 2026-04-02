"""Unit tests for execsql metacommand handlers in metacommands/io_export.py.

Tests every handler function:
  - _apply_output_dir
  - x_export  (all format branches + zip restrictions)
  - x_export_query  (all format branches + zip restrictions)
  - x_export_query_with_template
  - x_export_with_template
  - x_export_ods_multiple
  - x_export_xlsx_multiple
  - x_export_metadata
  - x_export_metadata_table
  - x_export_row_buffer

State is managed through the minimal_conf autouse fixture.  A fake
DatabasePool current-db object and ExportMetadata are installed on
_state at the start of each test that needs them.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.exporters.base import ExportMetadata


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_fake_db(encoding: str = "utf-8") -> MagicMock:
    """Return a minimal mock that satisfies io_export usage."""
    db = MagicMock()
    db.encoding = encoding
    db.server_name = "localhost"
    db.db_name = "testdb"
    db.user = "testuser"
    db.schema_qualified_table_name.side_effect = lambda schema, table: f"{schema}.{table}" if schema else table
    db.select_rowsource.return_value = (["col1", "col2"], [["a", 1], ["b", 2]])
    db.select_data.return_value = (["col1", "col2"], [["a", 1], ["b", 2]])
    return db


def _setup_db(db: MagicMock | None = None) -> MagicMock:
    """Install a fake DB pool on _state.dbs and return the fake db."""
    if db is None:
        db = _make_fake_db()
    pool = MagicMock()
    pool.current.return_value = db
    _state.dbs = pool
    return db


def _setup_export_metadata() -> ExportMetadata:
    """Install a real ExportMetadata on _state.export_metadata."""
    em = ExportMetadata()
    _state.export_metadata = em
    return em


def _base_export_kwargs(
    *,
    schema: str = "",
    table: str = "mytable",
    filename: str = "out.csv",
    description: str = "",
    tee: str | None = None,
    append: bool = False,
    filefmt: str = "csv",
    zipfilename: str | None = None,
    notype: bool = False,
) -> dict:
    return {
        "schema": schema,
        "table": table,
        "filename": filename,
        "description": description,
        "tee": tee,
        "append": append,
        "format": filefmt,
        "zipfilename": zipfilename,
        "notype": notype,
    }


def _base_query_kwargs(
    *,
    query: str = "select 1;",
    filename: str = "out.csv",
    description: str = "",
    tee: str | None = None,
    append: bool = False,
    filefmt: str = "csv",
    zipfilename: str | None = None,
    notype: bool = False,
) -> dict:
    return {
        "query": query,
        "filename": filename,
        "description": description,
        "tee": tee,
        "append": append,
        "format": filefmt,
        "zipfilename": zipfilename,
        "notype": notype,
    }


# ---------------------------------------------------------------------------
# _apply_output_dir
# ---------------------------------------------------------------------------


class TestApplyOutputDir:
    """Tests for the _apply_output_dir() path-prefix helper."""

    def _fn(self):
        from execsql.metacommands.io_export import _apply_output_dir

        return _apply_output_dir

    def test_no_output_dir_returns_path_unchanged(self, minimal_conf):
        fn = self._fn()
        assert fn("output.csv") == "output.csv"

    def test_relative_path_gets_prefix(self, minimal_conf, tmp_path):
        minimal_conf.export_output_dir = str(tmp_path / "exports")
        fn = self._fn()
        result = fn("output.csv")
        assert result == str(Path(str(tmp_path / "exports")) / "output.csv")

    def test_stdout_is_unchanged(self, minimal_conf, tmp_path):
        minimal_conf.export_output_dir = str(tmp_path / "exports")
        fn = self._fn()
        assert fn("stdout") == "stdout"
        assert fn("STDOUT") == "STDOUT"

    def test_absolute_path_unchanged(self, minimal_conf, tmp_path):
        minimal_conf.export_output_dir = str(tmp_path / "exports")
        fn = self._fn()
        abs_path = str(tmp_path / "abs" / "output.csv")
        assert fn(abs_path) == abs_path

    def test_windows_drive_letter_path_unchanged(self, minimal_conf, tmp_path):
        """A path starting with X: should not get a prefix applied."""
        minimal_conf.export_output_dir = str(tmp_path / "exports")
        fn = self._fn()
        # Simulate a Windows-style path — just test the logic; no actual I/O
        result = fn("C:\\data\\output.csv")
        assert result == "C:\\data\\output.csv"

    def test_empty_output_dir_is_passthrough(self, minimal_conf):
        minimal_conf.export_output_dir = ""
        fn = self._fn()
        assert fn("relative.csv") == "relative.csv"

    def test_attr_absent_is_passthrough(self, minimal_conf):
        if hasattr(minimal_conf, "export_output_dir"):
            del minimal_conf.export_output_dir
        fn = self._fn()
        assert fn("file.csv") == "file.csv"


# ---------------------------------------------------------------------------
# x_export — zip restriction paths
# ---------------------------------------------------------------------------


class TestXExportZipRestrictions:
    """x_export raises ErrInfo for format+zip combinations that are not supported."""

    def _call(self, filefmt: str, outfile: str = "out.txt") -> None:
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(
            filename=outfile,
            filefmt=filefmt,
            zipfilename="archive.zip",
        )
        with patch("execsql.metacommands.io_export.check_dir"):
            x_export(**kwargs)

    def test_stdout_with_zip_raises(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(
            filename="stdout",
            filefmt="csv",
            zipfilename="archive.zip",
        )
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo, match="stdout"):
            x_export(**kwargs)

    def test_drive_letter_with_zip_raises(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(
            filename="C:\\data\\out.csv",
            filefmt="csv",
            zipfilename="archive.zip",
        )
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo, match="drive letter"):
            x_export(**kwargs)

    @pytest.mark.parametrize("fmt", ["duckdb", "sqlite", "latex", "feather", "parquet", "hdf5", "ods", "xlsx"])
    def test_restricted_format_with_zip_raises(self, fmt):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(
            filename="out.bin",
            filefmt=fmt,
            zipfilename="archive.zip",
        )
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo):
            x_export(**kwargs)


# ---------------------------------------------------------------------------
# x_export — format dispatch (happy paths)
# ---------------------------------------------------------------------------


class TestXExportFormats:
    """x_export routes each format to the correct exporter function."""

    def _call_with_mock(self, target: str, filefmt: str, extra_kwargs: dict | None = None) -> MagicMock:
        """Patch *target*, call x_export with *filefmt*, return the mock."""
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt=filefmt, **(extra_kwargs or {}))
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch(target) as mock_fn,
        ):
            x_export(**kwargs)
        return mock_fn

    def test_txt_format_calls_prettyprint_query(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.prettyprint_query", "txt")
        mock_fn.assert_called_once()

    def test_text_format_calls_prettyprint_query(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.prettyprint_query", "text")
        mock_fn.assert_called_once()

    def test_txt_and_format_calls_prettyprint_with_and(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="txt-and")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.prettyprint_query") as mock_fn,
        ):
            x_export(**kwargs)
        # verify that and_val='AND' was passed
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs.get("and_val") == "AND"

    def test_ods_format_calls_write_query_to_ods(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_ods", "ods")
        mock_fn.assert_called_once()

    def test_xlsx_format_calls_write_query_to_xlsx(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_xlsx", "xlsx")
        mock_fn.assert_called_once()

    def test_duckdb_format_calls_write_query_to_duckdb(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_duckdb", "duckdb")
        mock_fn.assert_called_once()

    def test_sqlite_format_calls_write_query_to_sqlite(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_sqlite", "sqlite")
        mock_fn.assert_called_once()

    def test_xml_format_calls_write_query_to_xml(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_xml", "xml")
        mock_fn.assert_called_once()

    def test_json_format_calls_write_query_to_json(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_json", "json")
        mock_fn.assert_called_once()

    def test_json_ts_format_calls_write_query_to_json_ts(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_json_ts", "json_ts")
        mock_fn.assert_called_once()

    def test_json_tableschema_format_calls_write_query_to_json_ts(self):
        mock_fn = self._call_with_mock(
            "execsql.metacommands.io_export.write_query_to_json_ts",
            "json_tableschema",
        )
        mock_fn.assert_called_once()

    def test_values_format_calls_write_query_to_values(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_values", "values")
        mock_fn.assert_called_once()

    def test_html_format_calls_write_query_to_html(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_html", "html")
        mock_fn.assert_called_once()

    def test_cgi_html_format_calls_write_query_to_cgi_html(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_cgi_html", "cgi-html")
        mock_fn.assert_called_once()

    def test_latex_format_calls_write_query_to_latex(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_latex", "latex")
        mock_fn.assert_called_once()

    def test_hdf5_format_calls_write_query_to_hdf5(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_hdf5", "hdf5")
        mock_fn.assert_called_once()

    def test_yaml_format_calls_write_query_to_yaml(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_yaml", "yaml")
        mock_fn.assert_called_once()

    def test_markdown_format_calls_write_query_to_markdown(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_markdown", "markdown")
        mock_fn.assert_called_once()

    def test_md_alias_calls_write_query_to_markdown(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_markdown", "md")
        mock_fn.assert_called_once()

    def test_raw_format_calls_write_query_raw(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="raw")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_raw") as mock_fn,
        ):
            x_export(**kwargs)
        mock_fn.assert_called_once()

    def test_b64_format_calls_write_query_b64(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="b64")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_b64") as mock_fn,
        ):
            x_export(**kwargs)
        mock_fn.assert_called_once()

    def test_feather_format_calls_write_query_to_feather(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="feather")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_feather") as mock_fn,
        ):
            x_export(**kwargs)
        mock_fn.assert_called_once()

    def test_parquet_format_calls_write_query_to_parquet(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="parquet")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_parquet") as mock_fn,
        ):
            x_export(**kwargs)
        mock_fn.assert_called_once()

    def test_csv_fallback_calls_write_delimited_file(self):
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="csv")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_delimited_file") as mock_fn,
        ):
            x_export(**kwargs)
        mock_fn.assert_called_once()

    def test_tee_calls_prettyprint_to_stdout(self):
        """When tee is set and outfile != stdout, prettyprint_query is called for stdout."""
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="csv", tee="TEE", filename="out.csv")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_delimited_file"),
            patch("execsql.metacommands.io_export.prettyprint_query") as mock_pp,
        ):
            x_export(**kwargs)
        # Should be called once for the tee (stdout) output
        mock_pp.assert_called_once()
        assert mock_pp.call_args.args[2] == "stdout"

    def test_schema_qualified_table_used_in_select(self):
        """schema_qualified_table_name is called with schema/table."""
        from execsql.metacommands.io_export import x_export

        db = _make_fake_db()
        _setup_db(db)
        _setup_export_metadata()
        kwargs = _base_export_kwargs(schema="myschema", table="mytable", filefmt="csv")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_delimited_file"),
        ):
            x_export(**kwargs)
        db.schema_qualified_table_name.assert_called_once_with("myschema", "mytable")

    def test_export_metadata_record_added(self):
        """After a successful export, export_metadata has one record."""
        from execsql.metacommands.io_export import x_export

        _setup_db()
        em = ExportMetadata()
        _state.export_metadata = em
        kwargs = _base_export_kwargs(filefmt="csv")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
            patch("execsql.metacommands.io_export.write_delimited_file"),
        ):
            mock_rec.return_value = MagicMock()
            x_export(**kwargs)
        assert len(em.recordlist) == 1

    def test_select_rowsource_exception_wrapped_as_errinfo(self):
        """A non-ErrInfo DB exception from select_rowsource is wrapped in ErrInfo."""
        from execsql.metacommands.io_export import x_export

        db = _make_fake_db()
        db.select_rowsource.side_effect = RuntimeError("boom")
        _setup_db(db)
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="csv")
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo):
            x_export(**kwargs)

    def test_select_rowsource_errinfo_propagates(self):
        """An ErrInfo raised by select_rowsource propagates unchanged."""
        from execsql.metacommands.io_export import x_export

        db = _make_fake_db()
        original = ErrInfo("db", "select 1;", other_msg="fail")
        db.select_rowsource.side_effect = original
        _setup_db(db)
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="csv")
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo) as exc_info:
            x_export(**kwargs)
        assert exc_info.value is original

    def test_zip_non_restricted_format_calls_check_dir_with_zipfilename(self):
        """When a non-restricted format is used with a zip, check_dir is called
        with the zip filename (covering the zipfilename is not None branch, line 95)."""
        from execsql.metacommands.io_export import x_export

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_export_kwargs(filefmt="json", filename="data.json", zipfilename="out.zip")
        with (
            patch("execsql.metacommands.io_export.check_dir") as mock_cd,
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_json"),
        ):
            x_export(**kwargs)
        mock_cd.assert_called_once_with("out.zip")


# ---------------------------------------------------------------------------
# x_export_query — zip restriction paths
# ---------------------------------------------------------------------------


class TestXExportQueryZipRestrictions:
    """x_export_query raises ErrInfo for format+zip combinations that are blocked."""

    @pytest.mark.parametrize("fmt", ["latex", "feather", "parquet", "hdf5", "ods", "xlsx"])
    def test_restricted_format_with_zip_raises(self, fmt):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt=fmt, zipfilename="archive.zip")
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo):
            x_export_query(**kwargs)

    def test_stdout_with_zip_raises(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filename="stdout", filefmt="csv", zipfilename="archive.zip")
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo, match="stdout"):
            x_export_query(**kwargs)

    def test_drive_letter_with_zip_raises(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(
            filename="C:\\data\\out.csv",
            filefmt="csv",
            zipfilename="archive.zip",
        )
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo, match="drive letter"):
            x_export_query(**kwargs)


# ---------------------------------------------------------------------------
# x_export_query — format dispatch (happy paths)
# ---------------------------------------------------------------------------


class TestXExportQueryFormats:
    """x_export_query routes each format to the correct exporter function."""

    def _call_with_mock(self, target: str, filefmt: str) -> MagicMock:
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt=filefmt)
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch(target) as mock_fn,
        ):
            x_export_query(**kwargs)
        return mock_fn

    def test_txt_calls_prettyprint_query(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.prettyprint_query", "txt")
        mock_fn.assert_called_once()

    def test_text_and_calls_prettyprint_with_and_val(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="text-and")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.prettyprint_query") as mock_fn,
        ):
            x_export_query(**kwargs)
        assert mock_fn.call_args.kwargs.get("and_val") == "AND"

    def test_ods_calls_write_query_to_ods(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="ods")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_ods") as mock_fn,
            patch("execsql.metacommands.io_export.current_script_line", return_value=("script.sql", 42)),
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()
        # sheetname should be derived from the line number
        call_kwargs = mock_fn.call_args.kwargs
        assert "Query_42" in call_kwargs.get("sheetname", "")

    def test_xlsx_calls_write_query_to_xlsx_with_sheetname(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="xlsx")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_xlsx") as mock_fn,
            patch("execsql.metacommands.io_export.current_script_line", return_value=("script.sql", 7)),
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args.kwargs
        assert "Query_7" in call_kwargs.get("sheetname", "")

    def test_json_calls_write_query_to_json(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_json", "json")
        mock_fn.assert_called_once()

    def test_json_ts_calls_write_query_to_json_ts(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_json_ts", "json_ts")
        mock_fn.assert_called_once()

    def test_json_tableschema_calls_write_query_to_json_ts(self):
        mock_fn = self._call_with_mock(
            "execsql.metacommands.io_export.write_query_to_json_ts",
            "json_tableschema",
        )
        mock_fn.assert_called_once()

    def test_values_calls_write_query_to_values(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_values", "values")
        mock_fn.assert_called_once()

    def test_html_calls_write_query_to_html(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_html", "html")
        mock_fn.assert_called_once()

    def test_cgi_html_calls_write_query_to_cgi_html(self):
        mock_fn = self._call_with_mock(
            "execsql.metacommands.io_export.write_query_to_cgi_html",
            "cgi-html",
        )
        mock_fn.assert_called_once()

    def test_latex_calls_write_query_to_latex(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        # No zip so this is allowed
        kwargs = _base_query_kwargs(filefmt="latex", zipfilename=None)
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_latex") as mock_fn,
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()

    def test_yaml_calls_write_query_to_yaml(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_yaml", "yaml")
        mock_fn.assert_called_once()

    def test_markdown_calls_write_query_to_markdown(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_markdown", "markdown")
        mock_fn.assert_called_once()

    def test_md_alias_calls_write_query_to_markdown(self):
        mock_fn = self._call_with_mock("execsql.metacommands.io_export.write_query_to_markdown", "md")
        mock_fn.assert_called_once()

    def test_raw_calls_write_query_raw(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="raw")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_raw") as mock_fn,
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()

    def test_b64_calls_write_query_b64(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="b64")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_b64") as mock_fn,
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()

    def test_feather_calls_write_query_to_feather(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="feather", zipfilename=None)
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_feather") as mock_fn,
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()

    def test_parquet_calls_write_query_to_parquet(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="parquet", zipfilename=None)
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_parquet") as mock_fn,
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()

    def test_csv_calls_write_delimited_file(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="csv")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_delimited_file") as mock_fn,
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()

    def test_tee_calls_prettyprint_to_stdout(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="csv", tee="TEE", filename="out.csv")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_delimited_file"),
            patch("execsql.metacommands.io_export.prettyprint_query") as mock_pp,
        ):
            x_export_query(**kwargs)
        mock_pp.assert_called_once()
        assert mock_pp.call_args.args[2] == "stdout"

    def test_export_query_metadata_record_added(self):
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        em = ExportMetadata()
        _state.export_metadata = em
        kwargs = _base_query_kwargs(filefmt="csv")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
            patch("execsql.metacommands.io_export.write_delimited_file"),
        ):
            mock_rec.return_value = MagicMock()
            x_export_query(**kwargs)
        assert len(em.recordlist) == 1

    def test_select_rowsource_exception_wrapped_as_errinfo(self):
        from execsql.metacommands.io_export import x_export_query

        db = _make_fake_db()
        db.select_rowsource.side_effect = RuntimeError("db error")
        _setup_db(db)
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="csv")
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo):
            x_export_query(**kwargs)

    def test_select_rowsource_errinfo_propagates(self):
        from execsql.metacommands.io_export import x_export_query

        db = _make_fake_db()
        original = ErrInfo("db", "select 1;", other_msg="fail")
        db.select_rowsource.side_effect = original
        _setup_db(db)
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="csv")
        with patch("execsql.metacommands.io_export.check_dir"), pytest.raises(ErrInfo) as exc_info:
            x_export_query(**kwargs)
        assert exc_info.value is original

    def test_zip_non_restricted_format_reaches_notype(self):
        """When a non-restricted format is used with a zip, execution continues
        past the zip checks (covering the notype assignment at line 274)."""
        from execsql.metacommands.io_export import x_export_query

        _setup_db()
        _setup_export_metadata()
        kwargs = _base_query_kwargs(filefmt="json", filename="data.json", zipfilename="out.zip")
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.ExportRecord"),
            patch("execsql.metacommands.io_export.write_query_to_json") as mock_fn,
        ):
            x_export_query(**kwargs)
        mock_fn.assert_called_once()


# ---------------------------------------------------------------------------
# x_export_query_with_template
# ---------------------------------------------------------------------------


class TestXExportQueryWithTemplate:
    """Tests for template-based query export."""

    def test_calls_report_query(self):
        from execsql.metacommands.io_export import x_export_query_with_template

        _setup_db()
        em = ExportMetadata()
        _state.export_metadata = em
        kwargs = {
            "query": "select 1;",
            "filename": "out.html",
            "template": "report.tmpl",
            "tee": None,
            "append": False,
            "zipfilename": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.report_query") as mock_rq,
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
        ):
            mock_rec.return_value = MagicMock()
            x_export_query_with_template(**kwargs)
        mock_rq.assert_called_once_with(
            "select 1;",
            _state.dbs.current(),
            "out.html",
            "report.tmpl",
            False,
            zipfile=None,
        )

    def test_tee_triggers_prettyprint(self):
        from execsql.metacommands.io_export import x_export_query_with_template

        _setup_db()
        _setup_export_metadata()
        kwargs = {
            "query": "select 1;",
            "filename": "out.html",
            "template": "report.tmpl",
            "tee": "TEE",
            "append": False,
            "zipfilename": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.report_query"),
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
            patch("execsql.metacommands.io_export.prettyprint_query") as mock_pp,
        ):
            mock_rec.return_value = MagicMock()
            x_export_query_with_template(**kwargs)
        mock_pp.assert_called_once()

    def test_metadata_record_added(self):
        from execsql.metacommands.io_export import x_export_query_with_template

        _setup_db()
        em = ExportMetadata()
        _state.export_metadata = em
        kwargs = {
            "query": "select 1;",
            "filename": "out.html",
            "template": "report.tmpl",
            "tee": None,
            "append": False,
            "zipfilename": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.report_query"),
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
        ):
            mock_rec.return_value = MagicMock()
            x_export_query_with_template(**kwargs)
        assert len(em.recordlist) == 1


# ---------------------------------------------------------------------------
# x_export_with_template
# ---------------------------------------------------------------------------


class TestXExportWithTemplate:
    """Tests for table-based template export."""

    def test_calls_report_query_with_select_star(self):
        from execsql.metacommands.io_export import x_export_with_template

        db = _make_fake_db()
        _setup_db(db)
        em = ExportMetadata()
        _state.export_metadata = em
        kwargs = {
            "schema": "",
            "table": "employees",
            "filename": "out.html",
            "template": "tmpl.html",
            "tee": None,
            "append": False,
            "zipfilename": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.report_query") as mock_rq,
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
        ):
            mock_rec.return_value = MagicMock()
            x_export_with_template(**kwargs)
        # The select statement should use the table name
        call_args = mock_rq.call_args.args
        assert "employees" in call_args[0]

    def test_tee_triggers_prettyprint(self):
        from execsql.metacommands.io_export import x_export_with_template

        _setup_db()
        _setup_export_metadata()
        kwargs = {
            "schema": "",
            "table": "employees",
            "filename": "out.html",
            "template": "tmpl.html",
            "tee": "TEE",
            "append": False,
            "zipfilename": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.report_query"),
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
            patch("execsql.metacommands.io_export.prettyprint_query") as mock_pp,
        ):
            mock_rec.return_value = MagicMock()
            x_export_with_template(**kwargs)
        mock_pp.assert_called_once()

    def test_metadata_record_added(self):
        from execsql.metacommands.io_export import x_export_with_template

        _setup_db()
        em = ExportMetadata()
        _state.export_metadata = em
        kwargs = {
            "schema": "",
            "table": "employees",
            "filename": "out.html",
            "template": "tmpl.html",
            "tee": None,
            "append": False,
            "zipfilename": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.report_query"),
            patch("execsql.metacommands.io_export.ExportRecord") as mock_rec,
        ):
            mock_rec.return_value = MagicMock()
            x_export_with_template(**kwargs)
        assert len(em.recordlist) == 1


# ---------------------------------------------------------------------------
# x_export_ods_multiple
# ---------------------------------------------------------------------------


class TestXExportOdsMultiple:
    """Tests for multi-table ODS export."""

    def test_calls_write_queries_to_ods(self):
        from execsql.metacommands.io_export import x_export_ods_multiple

        _setup_db()
        kwargs = {
            "tables": [("", "table1"), ("", "table2")],
            "filename": "out.ods",
            "description": "test",
            "tee": None,
            "append": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.write_queries_to_ods") as mock_fn,
        ):
            x_export_ods_multiple(**kwargs)
        mock_fn.assert_called_once()

    def test_append_none_is_false(self):
        from execsql.metacommands.io_export import x_export_ods_multiple

        _setup_db()
        kwargs = {
            "tables": [],
            "filename": "out.ods",
            "description": "",
            "tee": None,
            "append": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.write_queries_to_ods") as mock_fn,
        ):
            x_export_ods_multiple(**kwargs)
        # append is passed as False when None
        call_args = mock_fn.call_args.args
        assert call_args[3] is False  # append positional arg

    def test_append_value_is_true(self):
        from execsql.metacommands.io_export import x_export_ods_multiple

        _setup_db()
        kwargs = {
            "tables": [],
            "filename": "out.ods",
            "description": "",
            "tee": None,
            "append": "APPEND",  # Any truthy non-None
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.write_queries_to_ods") as mock_fn,
        ):
            x_export_ods_multiple(**kwargs)
        call_args = mock_fn.call_args.args
        assert call_args[3] is True


# ---------------------------------------------------------------------------
# x_export_xlsx_multiple
# ---------------------------------------------------------------------------


class TestXExportXlsxMultiple:
    """Tests for multi-table XLSX export."""

    def test_calls_write_queries_to_xlsx(self):
        from execsql.metacommands.io_export import x_export_xlsx_multiple

        _setup_db()
        kwargs = {
            "tables": [("", "table1")],
            "filename": "out.xlsx",
            "description": "desc",
            "tee": None,
            "append": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.write_queries_to_xlsx") as mock_fn,
        ):
            x_export_xlsx_multiple(**kwargs)
        mock_fn.assert_called_once()

    def test_append_none_is_false(self):
        from execsql.metacommands.io_export import x_export_xlsx_multiple

        _setup_db()
        kwargs = {
            "tables": [],
            "filename": "out.xlsx",
            "description": "",
            "tee": None,
            "append": None,
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.write_queries_to_xlsx") as mock_fn,
        ):
            x_export_xlsx_multiple(**kwargs)
        call_args = mock_fn.call_args.args
        assert call_args[3] is False

    def test_append_value_is_true(self):
        from execsql.metacommands.io_export import x_export_xlsx_multiple

        _setup_db()
        kwargs = {
            "tables": [],
            "filename": "out.xlsx",
            "description": "",
            "tee": None,
            "append": "APPEND",
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.write_queries_to_xlsx") as mock_fn,
        ):
            x_export_xlsx_multiple(**kwargs)
        call_args = mock_fn.call_args.args
        assert call_args[3] is True


# ---------------------------------------------------------------------------
# x_export_metadata
# ---------------------------------------------------------------------------


class TestXExportMetadata:
    """Tests for the EXPORT METADATA metacommand handler."""

    def _make_meta_state(self) -> ExportMetadata:
        em = ExportMetadata()
        _state.export_metadata = em
        return em

    def test_txt_format_calls_prettyprint_rowset(self):
        from execsql.metacommands.io_export import x_export_metadata

        self._make_meta_state()
        kwargs = {
            "filename": "meta.txt",
            "append": None,
            "all": None,
            "zipfilename": None,
            "format": "txt",
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.prettyprint_rowset") as mock_pp,
        ):
            x_export_metadata(**kwargs)
        mock_pp.assert_called_once()

    def test_text_format_calls_prettyprint_rowset(self):
        from execsql.metacommands.io_export import x_export_metadata

        self._make_meta_state()
        kwargs = {
            "filename": "meta.txt",
            "append": None,
            "all": None,
            "zipfilename": None,
            "format": "text",
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.prettyprint_rowset") as mock_pp,
        ):
            x_export_metadata(**kwargs)
        mock_pp.assert_called_once()

    def test_csv_format_calls_write_delimited_file(self):
        from execsql.metacommands.io_export import x_export_metadata

        self._make_meta_state()
        kwargs = {
            "filename": "meta.csv",
            "append": None,
            "all": None,
            "zipfilename": None,
            "format": "csv",
        }
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.write_delimited_file") as mock_fn,
        ):
            x_export_metadata(**kwargs)
        mock_fn.assert_called_once()

    def test_stdout_skips_check_dir(self):
        from execsql.metacommands.io_export import x_export_metadata

        self._make_meta_state()
        kwargs = {
            "filename": "stdout",
            "append": None,
            "all": None,
            "zipfilename": None,
            "format": "csv",
        }
        with (
            patch("execsql.metacommands.io_export.check_dir") as mock_cd,
            patch("execsql.metacommands.io_export.write_delimited_file"),
        ):
            x_export_metadata(**kwargs)
        mock_cd.assert_not_called()

    def test_all_flag_calls_get_all(self):
        from execsql.metacommands.io_export import x_export_metadata

        em = self._make_meta_state()
        kwargs = {
            "filename": "stdout",
            "append": None,
            "all": "ALL",  # truthy — triggers get_all()
            "zipfilename": None,
            "format": "csv",
        }
        with (
            patch.object(em, "get_all", wraps=em.get_all) as mock_ga,
            patch("execsql.metacommands.io_export.write_delimited_file"),
        ):
            x_export_metadata(**kwargs)
        mock_ga.assert_called_once()

    def test_no_all_flag_calls_get(self):
        from execsql.metacommands.io_export import x_export_metadata

        em = self._make_meta_state()
        kwargs = {
            "filename": "stdout",
            "append": None,
            "all": None,
            "zipfilename": None,
            "format": "csv",
        }
        with (
            patch.object(em, "get", wraps=em.get) as mock_g,
            patch("execsql.metacommands.io_export.write_delimited_file"),
        ):
            x_export_metadata(**kwargs)
        mock_g.assert_called_once()

    def test_append_none_means_false(self):
        from execsql.metacommands.io_export import x_export_metadata

        self._make_meta_state()
        kwargs = {
            "filename": "stdout",
            "append": None,
            "all": None,
            "zipfilename": None,
            "format": "csv",
        }
        with patch("execsql.metacommands.io_export.write_delimited_file") as mock_fn:
            x_export_metadata(**kwargs)
        # append arg is positional index 5
        call_args = mock_fn.call_args.args
        assert call_args[5] is False

    def test_append_value_means_true(self):
        from execsql.metacommands.io_export import x_export_metadata

        self._make_meta_state()
        kwargs = {
            "filename": "stdout",
            "append": "APPEND",
            "all": None,
            "zipfilename": None,
            "format": "csv",
        }
        with patch("execsql.metacommands.io_export.write_delimited_file") as mock_fn:
            x_export_metadata(**kwargs)
        call_args = mock_fn.call_args.args
        assert call_args[5] is True


# ---------------------------------------------------------------------------
# x_export_metadata_table
# ---------------------------------------------------------------------------


class TestXExportMetadataTable:
    """Tests for x_export_metadata_table."""

    def _make_meta_state(self) -> ExportMetadata:
        em = ExportMetadata()
        _state.export_metadata = em
        return em

    def test_calls_import_data_table_with_new_zero(self):
        from execsql.metacommands.io_export import x_export_metadata_table

        _setup_db()
        self._make_meta_state()
        kwargs = {"all": None, "schema": "pub", "table": "meta_out", "new": None}
        with patch("execsql.metacommands.io_export.import_data_table") as mock_idt:
            x_export_metadata_table(**kwargs)
        mock_idt.assert_called_once()
        call_args = mock_idt.call_args.args
        # is_new is the 4th positional arg (index 3): (db, schemaname, tablename, is_new, ...)
        assert call_args[3] == 0

    def test_new_new_sets_is_new_to_1(self):
        from execsql.metacommands.io_export import x_export_metadata_table

        _setup_db()
        self._make_meta_state()
        kwargs = {"all": None, "schema": "", "table": "meta_out", "new": "new"}
        with patch("execsql.metacommands.io_export.import_data_table") as mock_idt:
            x_export_metadata_table(**kwargs)
        call_args = mock_idt.call_args.args
        # is_new is the 4th positional arg (index 3)
        assert call_args[3] == 1

    def test_new_replacement_sets_is_new_to_2(self):
        from execsql.metacommands.io_export import x_export_metadata_table

        _setup_db()
        self._make_meta_state()
        kwargs = {"all": None, "schema": "", "table": "meta_out", "new": "replacement"}
        with patch("execsql.metacommands.io_export.import_data_table") as mock_idt:
            x_export_metadata_table(**kwargs)
        call_args = mock_idt.call_args.args
        # is_new is the 4th positional arg (index 3)
        assert call_args[3] == 2

    def test_all_flag_calls_get_all(self):
        from execsql.metacommands.io_export import x_export_metadata_table

        _setup_db()
        em = self._make_meta_state()
        kwargs = {"all": "ALL", "schema": "", "table": "meta_out", "new": None}
        with (
            patch.object(em, "get_all", wraps=em.get_all) as mock_ga,
            patch("execsql.metacommands.io_export.import_data_table"),
        ):
            x_export_metadata_table(**kwargs)
        mock_ga.assert_called_once()

    def test_no_all_flag_calls_get(self):
        from execsql.metacommands.io_export import x_export_metadata_table

        _setup_db()
        em = self._make_meta_state()
        kwargs = {"all": None, "schema": "", "table": "meta_out", "new": None}
        with (
            patch.object(em, "get", wraps=em.get) as mock_g,
            patch("execsql.metacommands.io_export.import_data_table"),
        ):
            x_export_metadata_table(**kwargs)
        mock_g.assert_called_once()


# ---------------------------------------------------------------------------
# x_export_row_buffer
# ---------------------------------------------------------------------------


class TestXExportRowBuffer:
    """Tests for the EXPORT ROW BUFFER metacommand handler."""

    def test_sets_export_row_buffer(self, minimal_conf):
        from execsql.metacommands.io_export import x_export_row_buffer

        x_export_row_buffer(rows="5000")
        assert minimal_conf.export_row_buffer == 5000

    def test_integer_coercion(self, minimal_conf):
        from execsql.metacommands.io_export import x_export_row_buffer

        x_export_row_buffer(rows="1")
        assert isinstance(minimal_conf.export_row_buffer, int)
        assert minimal_conf.export_row_buffer == 1
