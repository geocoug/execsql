"""Additional unit tests for metacommands/io_write.py — writescript, ConsoleUIError path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.utils.gui import ConsoleUIError


# ---------------------------------------------------------------------------
# x_writescript
# ---------------------------------------------------------------------------


class TestXWritescript:
    def test_writescript_to_stdout(self, minimal_conf):
        from execsql.metacommands.io_write import x_writescript

        mock_output = MagicMock()
        _state.output = mock_output

        mock_script = MagicMock()
        mock_script.paramnames = ["p1", "p2"]
        mock_cmd1 = MagicMock()
        mock_cmd1.commandline.return_value = "SELECT 1;"
        mock_cmd2 = MagicMock()
        mock_cmd2.commandline.return_value = "SELECT 2;"
        mock_script.cmdlist = [mock_cmd1, mock_cmd2]
        _state.savedscripts = {"test_script": mock_script}

        x_writescript(script_id="test_script", filename=None, append=None)
        calls = [c[0][0] for c in mock_output.write.call_args_list]
        assert any("BEGIN SCRIPT" in c for c in calls)
        assert any("END SCRIPT" in c for c in calls)
        assert any("p1, p2" in c for c in calls)

    def test_writescript_no_params(self, minimal_conf):
        from execsql.metacommands.io_write import x_writescript

        mock_output = MagicMock()
        _state.output = mock_output

        mock_script = MagicMock()
        mock_script.paramnames = None
        mock_script.cmdlist = []
        _state.savedscripts = {"s1": mock_script}

        x_writescript(script_id="s1", filename=None, append=None)
        calls = [c[0][0] for c in mock_output.write.call_args_list]
        assert any("BEGIN SCRIPT s1\n" in c for c in calls)

    def test_writescript_to_file(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_writescript

        mock_script = MagicMock()
        mock_script.paramnames = []
        mock_cmd = MagicMock()
        mock_cmd.commandline.return_value = "SELECT 1;"
        mock_script.cmdlist = [mock_cmd]
        _state.savedscripts = {"s1": mock_script}

        outfile = str(tmp_path / "script.sql")
        with (
            patch("execsql.metacommands.io_write.filewriter_write") as mock_fw,
            patch("execsql.metacommands.io_write.filewriter_open_as_new"),
            patch("execsql.metacommands.io_write.check_dir"),
        ):
            x_writescript(script_id="s1", filename=outfile, append=None)
            assert mock_fw.call_count >= 3  # BEGIN, command line, END

    def test_writescript_to_file_append(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_writescript

        mock_script = MagicMock()
        mock_script.paramnames = []
        mock_script.cmdlist = []
        _state.savedscripts = {"s1": mock_script}

        outfile = str(tmp_path / "script.sql")
        with (
            patch("execsql.metacommands.io_write.filewriter_write"),
            patch("execsql.metacommands.io_write.filewriter_open_as_new") as mock_new,
            patch("execsql.metacommands.io_write.check_dir"),
        ):
            x_writescript(script_id="s1", filename=outfile, append="APPEND")
            mock_new.assert_not_called()  # append mode should not open as new


# ---------------------------------------------------------------------------
# x_write — ConsoleUIError path
# ---------------------------------------------------------------------------


class TestXWriteConsoleUIError:
    def test_write_console_error_resets_output(self, minimal_conf):
        from execsql.metacommands.io_write import x_write

        err = ConsoleUIError("console failed")
        err.value = "console failed"  # io_write.py:47 accesses e.value
        mock_output = MagicMock()
        # First call raises ConsoleUIError; second call (after reset) succeeds
        mock_output.write.side_effect = [err, None]
        mock_output.reset = MagicMock()
        _state.output = mock_output
        _state.exec_log = MagicMock()
        minimal_conf.write_prefix = None
        minimal_conf.write_suffix = None
        minimal_conf.tee_write_log = False
        minimal_conf.output_encoding = "utf-8"

        x_write(text="test", tee=None, filename=None, metacommandline="WRITE test")
        mock_output.reset.assert_called_once()


# ---------------------------------------------------------------------------
# x_write_create_table — CSV
# ---------------------------------------------------------------------------


class TestXWriteCreateTable:
    def test_missing_file_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_write_create_table

        with pytest.raises(ErrInfo):
            x_write_create_table(
                filename=str(tmp_path / "missing.csv"),
                quotechar=None,
                delimchar=None,
                encoding=None,
                skip=None,
                schema=None,
                table="t1",
                comment=None,
                outfile=None,
                metacommandline="WRITE CREATE TABLE ...",
            )

    def test_create_table_unitsep_delimiter(self, minimal_conf, tmp_path):
        """Verify that the 'unitsep' delimiter alias is recognized (line 68-69)."""
        from execsql.metacommands.io_write import x_write_create_table

        # We just need to get past the delimiter parsing; the CsvFile will
        # need many conf attrs, so we mock it instead.
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id|name\n1|Alice\n")
        minimal_conf.import_encoding = "utf-8"

        mock_csvfile = MagicMock()
        mock_csvfile.create_table.return_value = "CREATE TABLE t1 (id INT);"

        mock_db = MagicMock()
        mock_db.type = "sqlite"
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs
        mock_output = MagicMock()
        _state.output = mock_output

        with patch("execsql.metacommands.io_write.CsvFile", return_value=mock_csvfile):
            x_write_create_table(
                filename=str(csv_file),
                quotechar='"',
                delimchar="US",
                encoding=None,
                skip="2",
                schema=None,
                table="t1",
                comment="comment",
                outfile=None,
                metacommandline="WRITE CREATE TABLE ...",
            )
        mock_csvfile.lineformat.assert_called_once()
        calls = [c[0][0] for c in mock_output.write.call_args_list]
        assert any("CREATE TABLE" in c for c in calls)

    def test_create_table_to_file(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_write_create_table

        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,name\n1,Alice\n")
        minimal_conf.import_encoding = "utf-8"

        mock_csvfile = MagicMock()
        mock_csvfile.create_table.return_value = "CREATE TABLE t1 (id INT);"

        mock_db = MagicMock()
        mock_db.type = "sqlite"
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        outfile = str(tmp_path / "out.sql")
        with (
            patch("execsql.metacommands.io_write.CsvFile", return_value=mock_csvfile),
            patch("execsql.metacommands.io_write.filewriter_write") as mock_fw,
            patch("execsql.metacommands.io_write.check_dir"),
        ):
            x_write_create_table(
                filename=str(csv_file),
                quotechar=None,
                delimchar=None,
                encoding=None,
                skip=None,
                schema=None,
                table="t1",
                comment=None,
                outfile=outfile,
                metacommandline="WRITE CREATE TABLE ...",
            )
            mock_fw.assert_called()


# ---------------------------------------------------------------------------
# x_write_prefix / x_write_suffix — already tested but verify edge cases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# x_write_create_table_ods
# ---------------------------------------------------------------------------


class TestXWriteCreateTableOds:
    def test_missing_file_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_write_create_table_ods

        with pytest.raises(ErrInfo):
            x_write_create_table_ods(
                schema=None,
                table="t1",
                filename=str(tmp_path / "missing.ods"),
                sheet=None,
                skip=None,
                comment=None,
                outfile=None,
                metacommandline="WRITE CREATE TABLE ODS ...",
            )

    def test_create_table_ods_stdout(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_write_create_table_ods

        ods_file = tmp_path / "data.ods"
        ods_file.write_text("dummy")  # Won't be read since we mock ods_data

        mock_output = MagicMock()
        _state.output = mock_output

        mock_db = MagicMock()
        mock_db.type = "sqlite"
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        with (
            patch("execsql.metacommands.io_write.ods_data", return_value=(["id", "name"], [(1, "Alice")])),
            patch("execsql.metacommands.io_write.DataTable") as MockDT,
        ):
            mock_dt = MagicMock()
            mock_dt.create_table.return_value = "CREATE TABLE t1 (id INT, name TEXT);"
            MockDT.return_value = mock_dt

            x_write_create_table_ods(
                schema=None,
                table="t1",
                filename=str(ods_file),
                sheet=None,
                skip="2",
                comment="ODS comment",
                outfile=None,
                metacommandline="WRITE CREATE TABLE ODS ...",
            )
        calls = [c[0][0] for c in mock_output.write.call_args_list]
        assert any("CREATE TABLE" in c for c in calls)
        assert any("ODS comment" in c for c in calls)

    def test_create_table_ods_to_file(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_write_create_table_ods

        ods_file = tmp_path / "data.ods"
        ods_file.write_text("dummy")

        mock_db = MagicMock()
        mock_db.type = "sqlite"
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        with (
            patch("execsql.metacommands.io_write.ods_data", return_value=(["id"], [(1,)])),
            patch("execsql.metacommands.io_write.DataTable") as MockDT,
            patch("execsql.metacommands.io_write.filewriter_write") as mock_fw,
            patch("execsql.metacommands.io_write.filewriter_close"),
        ):
            mock_dt = MagicMock()
            mock_dt.create_table.return_value = "CREATE TABLE t1 (id INT);"
            MockDT.return_value = mock_dt

            x_write_create_table_ods(
                schema=None,
                table="t1",
                filename=str(ods_file),
                sheet=None,
                skip=None,
                comment=None,
                outfile=str(tmp_path / "out.sql"),
                metacommandline="WRITE CREATE TABLE ODS ...",
            )
            mock_fw.assert_called()


# ---------------------------------------------------------------------------
# x_write_create_table_xls
# ---------------------------------------------------------------------------


class TestXWriteCreateTableXls:
    def test_missing_file_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_write_create_table_xls

        minimal_conf.import_encoding = "utf-8"
        with pytest.raises(ErrInfo):
            x_write_create_table_xls(
                schema=None,
                table="t1",
                filename=str(tmp_path / "missing.xls"),
                sheet=None,
                skip=None,
                encoding=None,
                comment=None,
                outfile=None,
                metacommandline="WRITE CREATE TABLE XLS ...",
            )

    def test_create_table_xls_stdout(self, minimal_conf, tmp_path):
        from execsql.metacommands.io_write import x_write_create_table_xls

        xls_file = tmp_path / "data.xls"
        xls_file.write_text("dummy")

        mock_output = MagicMock()
        _state.output = mock_output
        minimal_conf.import_encoding = "utf-8"

        mock_db = MagicMock()
        mock_db.type = "sqlite"
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        with (
            patch("execsql.metacommands.io_write.xls_data", return_value=(["id"], [(1,)])),
            patch("execsql.metacommands.io_write.DataTable") as MockDT,
        ):
            mock_dt = MagicMock()
            mock_dt.create_table.return_value = "CREATE TABLE t1 (id INT);"
            MockDT.return_value = mock_dt

            x_write_create_table_xls(
                schema=None,
                table="t1",
                filename=str(xls_file),
                sheet=None,
                skip="1",
                encoding="latin-1",
                comment="XLS comment",
                outfile=None,
                metacommandline="WRITE CREATE TABLE XLS ...",
            )
        calls = [c[0][0] for c in mock_output.write.call_args_list]
        assert any("CREATE TABLE" in c for c in calls)


# ---------------------------------------------------------------------------
# x_write_create_table_alias
# ---------------------------------------------------------------------------


class TestXWriteCreateTableAlias:
    def test_unknown_alias_raises(self, minimal_conf):
        from execsql.metacommands.io_write import x_write_create_table_alias

        mock_dbs = MagicMock()
        mock_dbs.aliases.return_value = ["db1"]
        _state.dbs = mock_dbs

        with pytest.raises(ErrInfo):
            x_write_create_table_alias(
                alias="UNKNOWN",
                schema=None,
                table="t1",
                comment=None,
                filename=None,
                schema1=None,
                table1="t2",
                metacommandline="WRITE CREATE TABLE ALIAS ...",
            )

    def test_create_table_alias_stdout(self, minimal_conf):
        from execsql.metacommands.io_write import x_write_create_table_alias

        mock_db = MagicMock()
        mock_db.schema_qualified_table_name.return_value = "schema1.t1"
        mock_db.table_exists.return_value = True
        mock_db.select_rowsource.return_value = (["id", "name"], iter([(1, "Alice")]))
        mock_db.type = "sqlite"

        mock_dbs = MagicMock()
        mock_dbs.aliases.return_value = ["mydb"]
        mock_dbs.aliased_as.return_value = mock_db
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        mock_output = MagicMock()
        _state.output = mock_output

        with patch("execsql.metacommands.io_write.DataTable") as MockDT:
            mock_dt = MagicMock()
            mock_dt.create_table.return_value = "CREATE TABLE t2 (id INT, name TEXT);"
            MockDT.return_value = mock_dt

            x_write_create_table_alias(
                alias="MYDB",
                schema=None,
                table="t1",
                comment="alias comment",
                filename=None,
                schema1=None,
                table1="t2",
                metacommandline="WRITE CREATE TABLE ALIAS ...",
            )
        calls = [c[0][0] for c in mock_output.write.call_args_list]
        assert any("CREATE TABLE" in c for c in calls)
        assert any("alias comment" in c for c in calls)


class TestXWritePrefixSuffixEdge:
    def test_prefix_case_insensitive_clear(self, minimal_conf):
        from execsql.metacommands.io_write import x_write_prefix

        minimal_conf.write_prefix = "PREFIX"
        x_write_prefix(prefix="Clear")
        assert minimal_conf.write_prefix is None

    def test_suffix_case_insensitive_clear(self, minimal_conf):
        from execsql.metacommands.io_write import x_write_suffix

        minimal_conf.write_suffix = "SUFFIX"
        x_write_suffix(suffix="Clear")
        assert minimal_conf.write_suffix is None
