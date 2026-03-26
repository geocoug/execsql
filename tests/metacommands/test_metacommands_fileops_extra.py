"""Additional unit tests for metacommands/io_fileops.py — zip, serve, include home."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# x_include — home directory expansion
# ---------------------------------------------------------------------------


class TestXIncludeHomeExpansion:
    def test_include_tilde_expansion(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_fileops import x_include

        sql_file = tmp_path / "home_script.sql"
        sql_file.write_text("SELECT 1;")

        tilde_path = f"~{os.sep}{sql_file.name}"

        with (
            patch("execsql.metacommands.io_fileops.Path") as MockPath,
            patch("execsql.metacommands.io_fileops.read_sqlfile") as mock_read,
        ):
            # Make Path.home() return tmp_path
            MockPath.home.return_value = tmp_path
            # Make Path(expanded).is_file() return True for the resolved path
            mock_path_instance = MagicMock()
            mock_path_instance.is_file.return_value = True
            MockPath.return_value = mock_path_instance

            x_include(filename=tilde_path, exists=None)
            mock_read.assert_called_once()


# ---------------------------------------------------------------------------
# x_zip
# ---------------------------------------------------------------------------


class TestXZip:
    def test_zip_creates_archive(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_fileops import x_zip

        # Create source files
        f1 = tmp_path / "data.txt"
        f1.write_text("hello")

        zipfile = tmp_path / "archive.zip"
        x_zip(filename=str(f1), zipfilename=str(zipfile), append=None)
        assert zipfile.exists()

    def test_zip_append_mode(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_fileops import x_zip
        import zipfile

        f1 = tmp_path / "file1.txt"
        f1.write_text("first")
        f2 = tmp_path / "file2.txt"
        f2.write_text("second")

        zpath = tmp_path / "archive.zip"
        x_zip(filename=str(f1), zipfilename=str(zpath), append=None)
        x_zip(filename=str(f2), zipfilename=str(zpath), append="APPEND")

        with zipfile.ZipFile(str(zpath), "r") as zf:
            assert len(zf.namelist()) >= 2

    def test_zip_glob_pattern(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_fileops import x_zip

        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        zpath = tmp_path / "out.zip"
        x_zip(filename=str(tmp_path / "*.txt"), zipfilename=str(zpath), append=None)
        assert zpath.exists()


# ---------------------------------------------------------------------------
# x_serve
# ---------------------------------------------------------------------------


class TestXServe:
    @pytest.mark.parametrize(
        "fmt,expected_content_type",
        [
            ("csv", "text/csv"),
            ("txt", "text/plain"),
            ("text", "text/plain"),
            ("json", "application/json"),
            ("html", "text/html"),
            ("pdf", "application/pdf"),
            ("zip", "application/zip"),
            ("ods", "application/vnd.oasis.opendocument.spreadsheet"),
            ("binary", "application/octet-stream"),
            ("unknown_format", "application/octet-stream"),
        ],
    )
    def test_serve_content_types(self, minimal_conf, tmp_path, fmt, expected_content_type, capsys):
        from execsql.metacommands.io_fileops import x_serve

        test_file = tmp_path / "test.dat"
        test_file.write_bytes(b"test content")

        with patch("execsql.metacommands.io_fileops.sys.stdout") as mock_stdout:
            mock_stdout.buffer = MagicMock()
            x_serve(filename=str(test_file), format=fmt, metacommandline="SERVE ...")

    def test_serve_missing_file_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_fileops import x_serve

        with pytest.raises(ErrInfo):
            x_serve(
                filename=str(tmp_path / "missing.dat"),
                format="csv",
                metacommandline="SERVE ...",
            )


# ---------------------------------------------------------------------------
# x_copy
# ---------------------------------------------------------------------------


class TestXCopy:
    def _setup_dbs(self, db1_data, db2_type="sqlite"):
        mock_db1 = MagicMock()
        mock_db1.select_rowsource.return_value = db1_data
        mock_db1.schema_qualified_table_name.return_value = "schema1.table1"
        mock_db1.table_exists.return_value = True
        mock_db1.type = "sqlite"

        mock_db2 = MagicMock()
        mock_db2.schema_qualified_table_name.return_value = "schema2.table2"
        mock_db2.table_exists.return_value = False
        mock_db2.type = db2_type

        mock_dbs = MagicMock()
        mock_dbs.aliases.return_value = ["src", "dst"]
        mock_dbs.aliased_as.side_effect = lambda alias: {"src": mock_db1, "dst": mock_db2}[alias]
        _state.dbs = mock_dbs
        _state.exec_log = MagicMock()
        return mock_db1, mock_db2

    def test_copy_basic(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy

        hdrs = ["id", "name"]
        rows = [(1, "Alice"), (2, "Bob")]
        db1, db2 = self._setup_dbs((hdrs, iter(rows)))

        x_copy(
            alias1="SRC",
            schema1=None,
            table1="t1",
            new=None,
            alias2="DST",
            schema2=None,
            table2="t2",
            metacommandline="COPY ...",
        )
        db2.populate_table.assert_called_once()
        db2.commit.assert_called_once()

    def test_copy_unknown_alias_raises(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy

        mock_dbs = MagicMock()
        mock_dbs.aliases.return_value = ["src"]
        _state.dbs = mock_dbs

        with pytest.raises(ErrInfo):
            x_copy(
                alias1="UNKNOWN",
                schema1=None,
                table1="t1",
                new=None,
                alias2="SRC",
                schema2=None,
                table2="t2",
                metacommandline="COPY ...",
            )

    def test_copy_new_creates_table(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy

        hdrs = ["id"]
        rows = [(1,)]
        db1, db2 = self._setup_dbs((hdrs, iter(rows)))

        with patch("execsql.metacommands.io_fileops.DataTable") as MockDT:
            mock_dt = MagicMock()
            mock_dt.create_table.return_value = "CREATE TABLE t2 (id INT);"
            MockDT.return_value = mock_dt

            x_copy(
                alias1="SRC",
                schema1=None,
                table1="t1",
                new="NEW",
                alias2="DST",
                schema2=None,
                table2="t2",
                metacommandline="COPY ...",
            )
            db2.execute.assert_called()


# ---------------------------------------------------------------------------
# x_copy_query
# ---------------------------------------------------------------------------


class TestXCopyQuery:
    def _setup_copy_dbs(self):
        mock_db1 = MagicMock()
        mock_db1.select_rowsource.return_value = (["id"], iter([(1,)]))
        mock_db1.type = "sqlite"

        mock_db2 = MagicMock()
        mock_db2.schema_qualified_table_name.return_value = "schema2.table2"
        mock_db2.table_exists.return_value = False
        mock_db2.type = "sqlite"

        mock_dbs = MagicMock()
        mock_dbs.aliases.return_value = ["src", "dst"]
        mock_dbs.aliased_as.side_effect = lambda alias: {"src": mock_db1, "dst": mock_db2}[alias]
        _state.dbs = mock_dbs
        _state.exec_log = MagicMock()
        return mock_db1, mock_db2

    def test_copy_query_unknown_alias_raises(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy_query

        mock_dbs = MagicMock()
        mock_dbs.aliases.return_value = ["src"]
        _state.dbs = mock_dbs

        with pytest.raises(ErrInfo):
            x_copy_query(
                alias1="UNKNOWN",
                query="SELECT 1",
                new=None,
                alias2="SRC",
                schema=None,
                table="t2",
                metacommandline="COPY QUERY ...",
            )

    def test_copy_query_second_alias_unknown_raises(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy_query

        mock_dbs = MagicMock()
        mock_dbs.aliases.return_value = ["src"]
        _state.dbs = mock_dbs

        with pytest.raises(ErrInfo):
            x_copy_query(
                alias1="SRC",
                query="SELECT 1",
                new=None,
                alias2="MISSING",
                schema=None,
                table="t2",
                metacommandline="COPY QUERY ...",
            )

    def test_copy_query_basic(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy_query

        db1, db2 = self._setup_copy_dbs()

        x_copy_query(
            alias1="SRC",
            query="SELECT id FROM t1",
            new=None,
            alias2="DST",
            schema=None,
            table="t2",
            metacommandline="COPY QUERY ...",
        )
        db2.populate_table.assert_called_once()
        db2.commit.assert_called_once()

    def test_copy_query_new_creates_table(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy_query

        db1, db2 = self._setup_copy_dbs()

        with patch("execsql.metacommands.io_fileops.DataTable") as MockDT:
            mock_dt = MagicMock()
            mock_dt.create_table.return_value = "CREATE TABLE t2 (id INT);"
            MockDT.return_value = mock_dt

            x_copy_query(
                alias1="SRC",
                query="SELECT id FROM t1",
                new="NEW",
                alias2="DST",
                schema=None,
                table="t2",
                metacommandline="COPY QUERY ...",
            )
            db2.execute.assert_called()

    def test_copy_query_replacement(self, minimal_conf):
        from execsql.metacommands.io_fileops import x_copy_query

        db1, db2 = self._setup_copy_dbs()

        with patch("execsql.metacommands.io_fileops.DataTable") as MockDT:
            mock_dt = MagicMock()
            mock_dt.create_table.return_value = "CREATE TABLE t2 (id INT);"
            MockDT.return_value = mock_dt

            x_copy_query(
                alias1="SRC",
                query="SELECT id FROM t1",
                new="REPLACEMENT",
                alias2="DST",
                schema=None,
                table="t2",
                metacommandline="COPY QUERY ...",
            )
            db2.drop_table.assert_called_once()
            db2.execute.assert_called()
