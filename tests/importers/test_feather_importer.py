"""
Tests for execsql.importers.feather — Feather and Parquet import.

Requires ``polars``.  The entire module is skipped if polars is not installed.
Uses an in-memory SQLiteDatabase so no external services are required.
"""

from __future__ import annotations

import pytest

pl = pytest.importorskip("polars")

from execsql.db.sqlite import SQLiteDatabase
from execsql.importers.feather import import_feather, import_parquet


# ---------------------------------------------------------------------------
# Extra conf attributes required by import_data_table
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


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    d = SQLiteDatabase(path)
    yield d
    d.close()


# ---------------------------------------------------------------------------
# import_feather
# ---------------------------------------------------------------------------


class TestImportFeather:
    def test_creates_table_and_inserts_rows(self, db, tmp_path):
        f = str(tmp_path / "data.feather")
        pl.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]}).write_ipc(f)
        import_feather(db, None, "people", f, is_new=1)
        _, rows = db.select_data("SELECT id, name FROM people ORDER BY id;")
        assert len(rows) == 2

    def test_row_values_correct(self, db, tmp_path):
        f = str(tmp_path / "data.feather")
        pl.DataFrame({"x": [10, 20], "y": ["foo", "bar"]}).write_ipc(f)
        import_feather(db, None, "tbl", f, is_new=1)
        _, rows = db.select_data("SELECT y FROM tbl ORDER BY x;")
        vals = [r[0] for r in rows]
        assert vals == ["foo", "bar"]

    def test_replaces_existing_table_when_is_new_2(self, db, tmp_path):
        f = str(tmp_path / "data.feather")
        pl.DataFrame({"x": [1, 2]}).write_ipc(f)
        import_feather(db, None, "tbl", f, is_new=1)
        f2 = str(tmp_path / "data2.feather")
        pl.DataFrame({"x": [99]}).write_ipc(f2)
        import_feather(db, None, "tbl", f2, is_new=2)
        _, rows = db.select_data("SELECT x FROM tbl;")
        assert len(rows) == 1

    def test_append_to_existing_table(self, db, tmp_path):
        db.execute("CREATE TABLE tbl (id INTEGER, name TEXT);")
        db.execute("INSERT INTO tbl VALUES (1, 'existing');")
        db.commit()
        f = str(tmp_path / "data.feather")
        pl.DataFrame({"id": [2], "name": ["new"]}).write_ipc(f)
        import_feather(db, None, "tbl", f, is_new=False)
        _, rows = db.select_data("SELECT name FROM tbl ORDER BY id;")
        names = [r[0] for r in rows]
        assert "existing" in names
        assert "new" in names

    def test_none_values_imported(self, db, tmp_path):
        f = str(tmp_path / "data.feather")
        pl.DataFrame({"id": [1, 2], "val": [None, "ok"]}).write_ipc(f)
        import_feather(db, None, "tbl", f, is_new=1)
        _, rows = db.select_data("SELECT val FROM tbl ORDER BY id;")
        assert rows[0][0] is None
        assert rows[1][0] == "ok"


# ---------------------------------------------------------------------------
# import_parquet
# ---------------------------------------------------------------------------


class TestImportParquet:
    def test_creates_table_and_inserts_rows(self, db, tmp_path):
        f = str(tmp_path / "data.parquet")
        pl.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]}).write_parquet(f)
        import_parquet(db, None, "people", f, is_new=1)
        _, rows = db.select_data("SELECT id, name FROM people ORDER BY id;")
        assert len(rows) == 2

    def test_row_values_correct(self, db, tmp_path):
        f = str(tmp_path / "data.parquet")
        pl.DataFrame({"x": [10, 20], "y": ["foo", "bar"]}).write_parquet(f)
        import_parquet(db, None, "tbl", f, is_new=1)
        _, rows = db.select_data("SELECT y FROM tbl ORDER BY x;")
        vals = [r[0] for r in rows]
        assert vals == ["foo", "bar"]

    def test_none_values_imported(self, db, tmp_path):
        f = str(tmp_path / "data.parquet")
        pl.DataFrame({"id": [1, 2], "val": [None, "ok"]}).write_parquet(f)
        import_parquet(db, None, "tbl", f, is_new=1)
        _, rows = db.select_data("SELECT val FROM tbl ORDER BY id;")
        assert rows[0][0] is None
        assert rows[1][0] == "ok"

    def test_replaces_existing_table_when_is_new_2(self, db, tmp_path):
        f = str(tmp_path / "data.parquet")
        pl.DataFrame({"x": [1, 2]}).write_parquet(f)
        import_parquet(db, None, "tbl", f, is_new=1)
        f2 = str(tmp_path / "data2.parquet")
        pl.DataFrame({"x": [99]}).write_parquet(f2)
        import_parquet(db, None, "tbl", f2, is_new=2)
        _, rows = db.select_data("SELECT x FROM tbl;")
        assert len(rows) == 1
