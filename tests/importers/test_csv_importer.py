"""
Integration tests for execsql.importers.csv and execsql.importers.base.

Uses in-memory SQLiteDatabase so no external services are required.
The minimal_conf fixture (autouse) provides the config namespace; the
importer_conf fixture extends it with attributes specific to the importers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo
from execsql.importers.base import import_data_table
from execsql.importers.csv import importfile, importtable


# ---------------------------------------------------------------------------
# Extra conf attributes required by the importers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def importer_conf(minimal_conf):
    minimal_conf.del_empty_cols = False
    minimal_conf.create_col_hdrs = False
    minimal_conf.clean_col_hdrs = False
    minimal_conf.trim_col_hdrs = "none"
    minimal_conf.fold_col_hdrs = "no"
    minimal_conf.dedup_col_hdrs = False
    minimal_conf.import_encoding = "utf-8"
    minimal_conf.import_common_cols_only = False
    minimal_conf.quote_all_text = False
    minimal_conf.scan_lines = 50
    minimal_conf.empty_rows = True
    yield minimal_conf


# ---------------------------------------------------------------------------
# SQLite fixture — persistent file db (tmp_path) so tables survive across calls
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    d = SQLiteDatabase(path)
    yield d
    d.close()


# ===========================================================================
# importtable — CSV → new SQLite table
# ===========================================================================


class TestImportTableNew:
    def test_creates_and_populates_table(self, db, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
        importtable(db, None, "people", str(csv), is_new=1)
        _, rows = db.select_data("SELECT id, name FROM people ORDER BY id;")
        assert len(rows) == 2

    def test_row_values_correct(self, db, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("id,val\n10,hello\n20,world\n", encoding="utf-8")
        importtable(db, None, "tbl", str(csv), is_new=1)
        _, rows = db.select_data("SELECT val FROM tbl ORDER BY id;")
        vals = [r[0] for r in rows]
        assert "hello" in vals
        assert "world" in vals

    def test_replaces_existing_table_when_is_new_2(self, db, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n2\n", encoding="utf-8")
        importtable(db, None, "tbl", str(csv), is_new=1)
        csv.write_text("x\n99\n", encoding="utf-8")
        importtable(db, None, "tbl", str(csv), is_new=2)
        _, rows = db.select_data("SELECT x FROM tbl;")
        assert len(rows) == 1

    def test_nonexistent_file_raises_errinfo(self, db, tmp_path):
        with pytest.raises(ErrInfo):
            importtable(db, None, "t", str(tmp_path / "nope.csv"), is_new=1)

    def test_tsv_import(self, db, tmp_path):
        tsv = tmp_path / "data.tsv"
        tsv.write_text("a\tb\n1\t2\n3\t4\n", encoding="utf-8")
        importtable(db, None, "tbl", str(tsv), is_new=1, delimchar="\t", quotechar="none")
        _, rows = db.select_data("SELECT a, b FROM tbl ORDER BY a;")
        assert len(rows) == 2


class TestImportTableExisting:
    def test_append_to_existing_table(self, db, tmp_path):
        db.execute("CREATE TABLE tbl (id INTEGER, name TEXT);")
        db.execute("INSERT INTO tbl VALUES (1, 'existing');")
        db.commit()
        csv = tmp_path / "data.csv"
        csv.write_text("id,name\n2,new\n", encoding="utf-8")
        importtable(db, None, "tbl", str(csv), is_new=False)
        _, rows = db.select_data("SELECT name FROM tbl ORDER BY id;")
        names = [r[0] for r in rows]
        assert "existing" in names
        assert "new" in names

    def test_nonexistent_table_raises_errinfo(self, db, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n", encoding="utf-8")
        with pytest.raises(ErrInfo):
            importtable(db, None, "no_such_table", str(csv), is_new=False)


# ===========================================================================
# importfile — import entire file content into a single TEXT column
# ===========================================================================


class TestImportFile:
    def test_imports_file_content_into_column(self, db, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello world", encoding="utf-8")
        db.execute("CREATE TABLE docs (content TEXT);")
        db.execute("INSERT INTO docs VALUES ('placeholder');")
        db.commit()
        # importfile requires the table to exist and the column to hold the data
        importfile(db, None, "docs", "content", str(f))

    def test_nonexistent_table_raises_errinfo(self, db, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("data", encoding="utf-8")
        with pytest.raises(ErrInfo):
            importfile(db, None, "no_such_table", "col", str(f))


# ===========================================================================
# import_data_table — the shared back-end
# ===========================================================================


class TestImportDataTable:
    def test_creates_table_and_inserts_rows(self, db):
        hdrs = ["id", "name"]
        data = [["1", "Alice"], ["2", "Bob"]]
        import_data_table(db, None, "people", is_new=1, hdrs=hdrs, data=data)
        _, rows = db.select_data("SELECT id, name FROM people ORDER BY id;")
        assert len(rows) == 2

    def test_raises_when_extra_columns_in_source(self, db):
        db.execute("CREATE TABLE t (x TEXT);")
        db.commit()
        hdrs = ["x", "y_extra"]
        data = [["a", "b"]]
        with pytest.raises(ErrInfo):
            import_data_table(db, None, "t", is_new=False, hdrs=hdrs, data=data)

    def test_raises_on_missing_column_headers(self, db):
        hdrs = ["id", ""]  # blank header
        data = [["1", "v"]]
        with pytest.raises(ErrInfo):
            import_data_table(db, None, "tbl", is_new=1, hdrs=hdrs, data=data)

    def test_del_empty_cols_strips_blank_header_columns(self, db, minimal_conf):
        minimal_conf.del_empty_cols = True
        hdrs = ["id", "", "name"]
        data = [["1", "X", "Alice"]]
        import_data_table(db, None, "tbl", is_new=1, hdrs=hdrs, data=data)
        cols = db.table_columns("tbl")
        assert "" not in cols
        assert "id" in cols
        assert "name" in cols

    def test_create_col_hdrs_fills_blank_headers(self, db, minimal_conf):
        minimal_conf.create_col_hdrs = True
        hdrs = ["id", ""]
        data = [["1", "v"]]
        import_data_table(db, None, "tbl", is_new=1, hdrs=hdrs, data=data)
        cols = db.table_columns("tbl")
        assert "Col2" in cols

    def test_import_common_cols_only(self, db, minimal_conf):
        minimal_conf.import_common_cols_only = True
        db.execute("CREATE TABLE t (id TEXT);")
        db.commit()
        hdrs = ["id", "extra"]
        data = [["1", "x"]]
        # Should not raise even though 'extra' is not in the table
        import_data_table(db, None, "t", is_new=False, hdrs=hdrs, data=data)
        _, rows = db.select_data("SELECT id FROM t;")
        assert len(rows) == 1


# ===========================================================================
# importtable — quotechar="none" branch (lines 48-50)
# ===========================================================================


class TestImportTableQuotecharNone:
    """lineformat is called with quotechar=None when the user passes quotechar='none'."""

    def test_quotechar_none_string_normalised_and_import_succeeds(self, db, tmp_path):
        """quotechar='none' is treated as no quoting — TSV data imports correctly."""
        tsv = tmp_path / "data.tsv"
        tsv.write_text("col1\tcol2\nhello\tworld\n", encoding="utf-8")
        importtable(db, None, "t", str(tsv), is_new=1, delimchar="\t", quotechar="none")
        _, rows = db.select_data("SELECT col1, col2 FROM t;")
        assert len(rows) == 1
        assert rows[0][0] == "hello"
        assert rows[0][1] == "world"

    def test_quotechar_none_uses_lineformat(self, db, tmp_path):
        """Verify CsvFile.lineformat receives None (not the string 'none') for quotechar."""
        tsv = tmp_path / "data.tsv"
        tsv.write_text("a\tb\n1\t2\n", encoding="utf-8")

        from execsql.exporters.delimited import CsvFile

        captured = {}
        original_lineformat = CsvFile.lineformat

        def capturing_lineformat(self_inner, delim, qchar, echar):
            captured["quotechar"] = qchar
            original_lineformat(self_inner, delim, qchar, echar)

        with patch.object(CsvFile, "lineformat", capturing_lineformat):
            importtable(db, None, "t2", str(tsv), is_new=1, delimchar="\t", quotechar="none")

        assert "quotechar" in captured, "lineformat was not called"
        assert captured["quotechar"] is None


# ===========================================================================
# importtable — drop_table failure logging (lines 57-58)
# ===========================================================================


class TestImportTableDropTableFailure:
    """When drop_table raises and is_new==2, the error is logged but not re-raised."""

    def test_drop_table_failure_is_logged_not_raised(self, db, tmp_path):
        """If drop_table raises, importtable logs a warning and continues."""
        import execsql.state as _state

        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n", encoding="utf-8")

        # exec_log is None by default; replace it with a mock for this test.
        mock_log = MagicMock()
        logged = []
        mock_log.log_status_info.side_effect = lambda msg: logged.append(msg)

        with (
            patch.object(db, "drop_table", side_effect=RuntimeError("boom")),
            patch.object(_state, "exec_log", mock_log),
        ):
            # Should not raise despite drop_table failing.
            importtable(db, None, "t", str(csv), is_new=2)

        assert any("Could not drop" in m for m in logged), f"Expected drop warning in logs: {logged}"

    def test_drop_table_failure_data_still_imported(self, db, tmp_path):
        """Even when drop_table fails, the subsequent CREATE + INSERT still runs."""
        import execsql.state as _state

        csv = tmp_path / "data.csv"
        csv.write_text("val\nhello\n", encoding="utf-8")

        mock_log = MagicMock()

        with (
            patch.object(db, "drop_table", side_effect=RuntimeError("boom")),
            patch.object(_state, "exec_log", mock_log),
        ):
            importtable(db, None, "t", str(csv), is_new=2)

        _, rows = db.select_data("SELECT val FROM t;")
        assert len(rows) == 1


# ===========================================================================
# importtable — schema-qualified table existence check (lines 74-79)
# ===========================================================================


class TestImportTableSchemaQualified:
    """When schemaname is set and is_new is falsy, table_exists is called with the schema."""

    def test_schema_nonexistent_table_raises_errinfo(self, db, tmp_path):
        """ErrInfo is raised when the schema-qualified table does not exist."""
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n", encoding="utf-8")

        # SQLite doesn't use schemas, so table_exists(tablename, schemaname) will
        # return False for any schema name — which triggers the ErrInfo path.
        with pytest.raises(ErrInfo) as exc_info:
            importtable(db, "myschema", "no_such_table", str(csv), is_new=False)

        assert "myschema" in str(exc_info.value) or "no_such_table" in str(exc_info.value)

    def test_schema_path_calls_table_exists_with_schema(self, db, tmp_path):
        """table_exists is called with (tablename, schemaname) when schemaname is set."""
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n", encoding="utf-8")

        calls = []
        original_te = db.table_exists

        def recording_table_exists(table, schema=None):
            calls.append((table, schema))
            return original_te(table, schema)

        with patch.object(db, "table_exists", side_effect=recording_table_exists), pytest.raises(ErrInfo):
            importtable(db, "myschema", "no_such_table", str(csv), is_new=False)

        # Verify at least one call included the schema argument.
        assert any(schema == "myschema" for _, schema in calls)


# ===========================================================================
# importtable — exception wrapping in import_tabular_file (lines 89-97)
# ===========================================================================


class TestImportTableExceptionWrapping:
    """Non-ErrInfo exceptions from import_tabular_file are re-wrapped as ErrInfo."""

    def test_generic_exception_from_import_tabular_file_wrapped_as_errinfo(self, db, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n", encoding="utf-8")
        db.execute("CREATE TABLE t (x TEXT);")
        db.commit()

        with (
            patch.object(db, "import_tabular_file", side_effect=RuntimeError("internal failure")),
            pytest.raises(ErrInfo) as exc_info,
        ):
            importtable(db, None, "t", str(csv), is_new=False)

        # The ErrInfo should mention the filename and table name.
        err = str(exc_info.value)
        assert "t" in err or "internal failure" in err

    def test_errinfo_from_import_tabular_file_propagates_unchanged(self, db, tmp_path):
        """An ErrInfo raised by import_tabular_file is re-raised as-is (not double-wrapped)."""
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n", encoding="utf-8")
        db.execute("CREATE TABLE t (x TEXT);")
        db.commit()

        original_err = ErrInfo("error", other_msg="original error")

        with (
            patch.object(db, "import_tabular_file", side_effect=original_err),
            pytest.raises(ErrInfo) as exc_info,
        ):
            importtable(db, None, "t", str(csv), is_new=False)

        assert exc_info.value is original_err


# ===========================================================================
# importfile — schema-qualified path (lines 111-116)
# ===========================================================================


class TestImportFileSchemaQualified:
    """importfile raises ErrInfo when schema-qualified table does not exist."""

    def test_schema_nonexistent_table_raises_errinfo(self, db, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello", encoding="utf-8")

        with pytest.raises(ErrInfo) as exc_info:
            importfile(db, "myschema", "no_such_table", "content", str(f))

        assert "myschema" in str(exc_info.value) or "no_such_table" in str(exc_info.value)

    def test_schema_path_calls_table_exists_with_schema(self, db, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello", encoding="utf-8")

        calls = []
        original_te = db.table_exists

        def recording_table_exists(table, schema=None):
            calls.append((table, schema))
            return original_te(table, schema)

        with patch.object(db, "table_exists", side_effect=recording_table_exists), pytest.raises(ErrInfo):
            importfile(db, "myschema", "no_such_table", "content", str(f))

        assert any(schema == "myschema" for _, schema in calls)


# ===========================================================================
# importfile — exception wrapping (lines 128-134)
# ===========================================================================


class TestImportFileExceptionWrapping:
    """Non-ErrInfo exceptions from import_entire_file are wrapped as ErrInfo."""

    def test_generic_exception_wrapped_as_errinfo(self, db, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello", encoding="utf-8")
        db.execute("CREATE TABLE docs (content TEXT);")
        db.commit()

        with (
            patch.object(db, "import_entire_file", side_effect=RuntimeError("disk error")),
            pytest.raises(ErrInfo) as exc_info,
        ):
            importfile(db, None, "docs", "content", str(f))

        err = str(exc_info.value)
        assert "docs" in err or "disk error" in err

    def test_errinfo_from_import_entire_file_propagates_unchanged(self, db, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello", encoding="utf-8")
        db.execute("CREATE TABLE docs (content TEXT);")
        db.commit()

        original_err = ErrInfo("error", other_msg="original import error")

        with (
            patch.object(db, "import_entire_file", side_effect=original_err),
            pytest.raises(ErrInfo) as exc_info,
        ):
            importfile(db, None, "docs", "content", str(f))

        assert exc_info.value is original_err
