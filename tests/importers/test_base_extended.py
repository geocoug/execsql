"""
Tests for execsql.importers.base.import_data_table — covering uncovered lines:

  Lines 51-65 — del_empty_cols=True: blank column headers are deleted
  Lines 82-83 — create_col_hdrs=True: blank headers get generated names
  Lines 90-92 — ErrInfo raised when headers are missing and create_col_hdrs=False
  Lines 112-115 — populate_table raises ErrInfo; non-ErrInfo exception wrapped
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from execsql.exceptions import ErrInfo
from execsql.importers.base import import_data_table


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def importer_conf(minimal_conf):
    """Extend minimal_conf with all attributes needed by importers.base."""
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


_db_counter = 0


@pytest.fixture
def sqlite_db(tmp_path):
    """Yield a fresh SQLiteDatabase; close it after the test to avoid ResourceWarnings."""
    global _db_counter
    _db_counter += 1
    from execsql.db.sqlite import SQLiteDatabase

    db_path = str(tmp_path / f"test_{_db_counter}.db")
    db = SQLiteDatabase(db_path)
    yield db
    try:
        db.close()
    except Exception:
        pass


def _make_sqlite_db(tmp_path, create_table_sql=None):
    """Return a SQLiteDatabase with an optional pre-created table."""
    global _db_counter
    _db_counter += 1
    from execsql.db.sqlite import SQLiteDatabase

    db_path = str(tmp_path / f"test_{_db_counter}.db")
    db = SQLiteDatabase(db_path)
    if create_table_sql:
        db.execute(create_table_sql)
        db.commit()
    return db


# ---------------------------------------------------------------------------
# del_empty_cols=True: blank/None column headers removed (lines 51-65)
# ---------------------------------------------------------------------------


class TestImportDataTableDelEmptyCols:
    def test_blank_header_column_deleted_when_del_empty_cols_true(self, tmp_path, importer_conf):
        importer_conf.del_empty_cols = True

        db = _make_sqlite_db(tmp_path, "CREATE TABLE t1 (a TEXT, b TEXT)")
        # hdrs has a blank entry; corresponding data column should be removed
        hdrs = ["a", "", "b"]
        data = [["val_a", "ignored", "val_b"]]

        import_data_table(db, None, "t1", False, hdrs, data)
        # After deletion, hdrs should be ["a", "b"] and row data ["val_a", "val_b"]
        # The table was not newly created so we just verify no error and insertion
        _, rows = db.select_data("SELECT * FROM t1")
        assert len(rows) == 1
        assert rows[0][0] == "val_a"
        assert rows[0][1] == "val_b"

    def test_none_header_column_deleted_when_del_empty_cols_true(self, tmp_path, importer_conf):
        importer_conf.del_empty_cols = True

        db = _make_sqlite_db(tmp_path, "CREATE TABLE t2 (x TEXT)")
        hdrs = [None, "x"]
        data = [["drop_me", "keep_me"]]

        import_data_table(db, None, "t2", False, hdrs, data)
        _, rows = db.select_data("SELECT * FROM t2")
        assert rows[0][0] == "keep_me"

    def test_multiple_blank_headers_all_deleted(self, tmp_path, importer_conf):
        importer_conf.del_empty_cols = True

        db = _make_sqlite_db(tmp_path, "CREATE TABLE t3 (z TEXT)")
        hdrs = ["", "z", "   "]
        data = [["drop1", "keep", "drop2"]]

        import_data_table(db, None, "t3", False, hdrs, data)
        _, rows = db.select_data("SELECT * FROM t3")
        assert rows[0][0] == "keep"


# ---------------------------------------------------------------------------
# create_col_hdrs=True: blank headers get generated names "ColN" (lines 82-83)
# ---------------------------------------------------------------------------


class TestImportDataTableCreateColHdrs:
    def test_blank_header_replaced_with_generated_name(self, tmp_path, importer_conf):
        importer_conf.create_col_hdrs = True
        # We need is_new=True to create the table from the generated headers
        db = _make_sqlite_db(tmp_path)

        hdrs = ["a", ""]
        data = [["val_a", "val_b"]]
        import_data_table(db, None, "generated_tbl", True, hdrs, data)

        # Table should have been created; column Col2 should exist
        tbl_cols = db.table_columns("generated_tbl", None)
        assert "Col2" in tbl_cols or any(c.lower() == "col2" for c in tbl_cols)

    def test_none_header_replaced_with_generated_name(self, tmp_path, importer_conf):
        importer_conf.create_col_hdrs = True
        db = _make_sqlite_db(tmp_path)

        hdrs = [None, "b"]
        data = [["val1", "val2"]]
        import_data_table(db, None, "gen_tbl2", True, hdrs, data)

        tbl_cols = db.table_columns("gen_tbl2", None)
        assert any(c.lower() == "col1" for c in tbl_cols)


# ---------------------------------------------------------------------------
# Missing headers + create_col_hdrs=False raises ErrInfo (lines 90-92)
# ---------------------------------------------------------------------------


class TestImportDataTableMissingHeadersError:
    def test_missing_header_raises_when_create_col_hdrs_false(self, tmp_path, importer_conf):
        importer_conf.create_col_hdrs = False
        importer_conf.del_empty_cols = False

        db = _make_sqlite_db(tmp_path, "CREATE TABLE err_tbl (col1 TEXT)")
        hdrs = ["col1", ""]
        data = [["v1", "v2"]]

        with pytest.raises(ErrInfo):
            import_data_table(db, None, "err_tbl", False, hdrs, data)


# ---------------------------------------------------------------------------
# populate_table error paths (lines 112-115)
# ---------------------------------------------------------------------------


class TestImportDataTablePopulateErrors:
    def test_errinfo_from_populate_table_propagates(self, tmp_path, importer_conf):
        """ErrInfo raised by populate_table must propagate unmodified."""
        db = _make_sqlite_db(tmp_path, "CREATE TABLE pop_tbl (id INTEGER)")
        db_mock = MagicMock(wraps=db)
        original_err = ErrInfo("db", "INSERT INTO pop_tbl VALUES (?)")
        db_mock.populate_table.side_effect = original_err
        db_mock.table_columns.return_value = ["id"]
        db_mock.type = db.type

        hdrs = ["id"]
        data = [[1], [2]]
        with pytest.raises(ErrInfo) as exc_info:
            import_data_table(db_mock, None, "pop_tbl", False, hdrs, data)
        assert exc_info.value is original_err

    def test_non_errinfo_from_populate_table_wrapped_in_errinfo(self, tmp_path, importer_conf):
        """Non-ErrInfo exceptions from populate_table are wrapped in ErrInfo."""
        db = _make_sqlite_db(tmp_path, "CREATE TABLE wrap_tbl (id INTEGER)")
        db_mock = MagicMock(wraps=db)
        db_mock.populate_table.side_effect = RuntimeError("disk full")
        db_mock.table_columns.return_value = ["id"]
        db_mock.type = db.type

        hdrs = ["id"]
        data = [[1]]
        with pytest.raises(ErrInfo):
            import_data_table(db_mock, None, "wrap_tbl", False, hdrs, data)


# ---------------------------------------------------------------------------
# import_common_cols_only path (line 100)
# ---------------------------------------------------------------------------


class TestImportDataTableCommonColsOnly:
    def test_import_common_cols_only_skips_extra_source_cols(self, tmp_path, importer_conf):
        """With import_common_cols_only=True, extra columns in source are ignored."""
        importer_conf.import_common_cols_only = True

        db = _make_sqlite_db(tmp_path, "CREATE TABLE common_tbl (a TEXT)")
        # Source has two columns; only 'a' is in the target table
        hdrs = ["a", "extra"]
        data = [["val_a", "ignored"]]
        # Should not raise (the extra column is silently dropped)
        import_data_table(db, None, "common_tbl", False, hdrs, data)
        _, rows = db.select_data("SELECT * FROM common_tbl")
        assert len(rows) == 1

    def test_extra_source_cols_raise_when_not_common_only(self, tmp_path, importer_conf):
        """Without import_common_cols_only, extra source columns raise ErrInfo."""
        importer_conf.import_common_cols_only = False

        db = _make_sqlite_db(tmp_path, "CREATE TABLE extra_tbl (a TEXT)")
        hdrs = ["a", "extra"]
        data = [["val_a", "causes_error"]]
        with pytest.raises(ErrInfo):
            import_data_table(db, None, "extra_tbl", False, hdrs, data)
