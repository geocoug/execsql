"""
Integration tests for execsql.importers.csv and execsql.importers.base.

Uses in-memory SQLiteDatabase so no external services are required.
The minimal_conf fixture (autouse) provides the config namespace; the
importer_conf fixture extends it with attributes specific to the importers.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import execsql.state as _state
from execsql.db.sqlite import SQLiteDatabase
from execsql.importers.csv import importtable, importfile
from execsql.importers.base import import_data_table
from execsql.exceptions import ErrInfo


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
