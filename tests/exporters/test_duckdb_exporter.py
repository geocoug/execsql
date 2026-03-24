"""
Tests for execsql.exporters.duckdb — DuckDB database export.

Covers:
  - export_duckdb: writes rows directly to a DuckDB file
  - write_query_to_duckdb: fetches from a FakeDB and delegates to export_duckdb

Requires the ``duckdb`` package.  The entire module is skipped if duckdb is
not installed (e.g., on a minimal test environment).
"""

from __future__ import annotations

import pytest

duckdb = pytest.importorskip("duckdb")

from execsql.exporters.duckdb import export_duckdb, write_query_to_duckdb
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# FakeDB
# ---------------------------------------------------------------------------


class FakeDB:
    def __init__(self, hdrs, rows):
        self._hdrs = hdrs
        self._rows = iter(rows)

    def select_rowsource(self, sql):
        return self._hdrs, self._rows


class ErrorDB:
    def select_rowsource(self, sql):
        raise RuntimeError("driver error")


# ---------------------------------------------------------------------------
# export_duckdb — direct tests
# ---------------------------------------------------------------------------


class TestExportDuckdb:
    def test_creates_file(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        export_duckdb(out, ["id", "name"], [(1, "Alice"), (2, "Bob")], append=False, tablename="t")
        assert (tmp_path / "out.duckdb").exists()

    def test_table_contains_rows(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        export_duckdb(out, ["id", "name"], [(1, "Alice"), (2, "Bob")], append=False, tablename="t")
        con = duckdb.connect(out)
        rows = con.execute("SELECT id, name FROM t ORDER BY id").fetchall()
        con.close()
        assert rows == [(1, "Alice"), (2, "Bob")]

    def test_table_headers(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        export_duckdb(out, ["alpha", "beta"], [(10, 20)], append=False, tablename="hdr_tbl")
        con = duckdb.connect(out)
        desc = con.execute("SELECT * FROM hdr_tbl").description
        cols = [d[0] for d in desc]
        con.close()
        assert cols == ["alpha", "beta"]

    def test_empty_rows(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        export_duckdb(out, ["id"], [], append=False, tablename="empty_t")
        con = duckdb.connect(out)
        rows = con.execute("SELECT id FROM empty_t").fetchall()
        con.close()
        assert rows == []

    def test_overwrite_existing_table(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        export_duckdb(out, ["val"], [(1,)], append=False, tablename="t")
        export_duckdb(out, ["val"], [(99,)], append=False, tablename="t")
        con = duckdb.connect(out)
        rows = con.execute("SELECT val FROM t").fetchall()
        con.close()
        assert rows == [(99,)]

    def test_append_to_existing_table_raises(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        export_duckdb(out, ["val"], [(1,)], append=False, tablename="t")
        with pytest.raises(ErrInfo):
            export_duckdb(out, ["val"], [(2,)], append=True, tablename="t")

    def test_none_values(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        export_duckdb(out, ["id", "val"], [(1, None)], append=False, tablename="t")
        con = duckdb.connect(out)
        rows = con.execute("SELECT val FROM t").fetchall()
        con.close()
        assert rows == [(None,)]

    def test_existing_file_without_table(self, tmp_path):
        """File exists but target table doesn't — should create it fresh (line 47→52 branch)."""
        out = str(tmp_path / "out.duckdb")
        # Create file with a different table name
        export_duckdb(out, ["id"], [(1,)], append=False, tablename="other_table")
        # Now export to a new table in the same file — file exists, table doesn't
        export_duckdb(out, ["val"], [(42,)], append=False, tablename="new_table")
        con = duckdb.connect(out)
        rows = con.execute("SELECT val FROM new_table").fetchall()
        con.close()
        assert rows == [(42,)]


# ---------------------------------------------------------------------------
# write_query_to_duckdb
# ---------------------------------------------------------------------------


class TestWriteQueryToDuckdb:
    def test_writes_result_to_file(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        db = FakeDB(["x", "y"], [(1, "a"), (2, "b")])
        write_query_to_duckdb("SELECT x, y FROM t", db, out, append=False, tablename="res")
        con = duckdb.connect(out)
        rows = con.execute("SELECT x, y FROM res ORDER BY x").fetchall()
        con.close()
        assert rows == [(1, "a"), (2, "b")]

    def test_driver_error_raises_errinfo(self, tmp_path):
        out = str(tmp_path / "out.duckdb")
        db = ErrorDB()
        with pytest.raises(ErrInfo):
            write_query_to_duckdb("SELECT 1", db, out, append=False, tablename="t")

    def test_errinfo_from_db_is_reraised(self, tmp_path):
        """ErrInfo raised by select_rowsource must propagate unchanged (line 87)."""
        out = str(tmp_path / "out.duckdb")
        original = ErrInfo(type="db", exception_msg="original error")

        class ErrInfoDB:
            def select_rowsource(self, sql):
                raise original

        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_duckdb("SELECT 1", ErrInfoDB(), out, append=False, tablename="t")
        assert exc_info.value is original
