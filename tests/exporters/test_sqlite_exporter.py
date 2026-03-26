"""
Tests for execsql.exporters.sqlite — SQLite database export.

Covers:
  - export_sqlite: writes rows directly to an SQLite file
  - write_query_to_sqlite: fetches from a FakeDB and delegates to export_sqlite

Uses :memory: via the standard library sqlite3 for result verification.
No external services or optional packages required.
"""

from __future__ import annotations

import sqlite3

import pytest

from execsql.exporters.sqlite import export_sqlite, write_query_to_sqlite
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# FakeDB
# ---------------------------------------------------------------------------


class FakeDB:
    """Minimal DB stub returning fixed headers and rows."""

    def __init__(self, hdrs, rows):
        self._hdrs = hdrs
        self._rows = iter(rows)

    def select_rowsource(self, sql):
        return self._hdrs, self._rows


class ErrorDB:
    """DB stub that raises on select."""

    def select_rowsource(self, sql):
        raise RuntimeError("driver error")


# ---------------------------------------------------------------------------
# export_sqlite — direct tests
# ---------------------------------------------------------------------------


class TestExportSqlite:
    def test_creates_file(self, tmp_path):
        out = str(tmp_path / "out.db")
        export_sqlite(out, ["id", "name"], [(1, "Alice"), (2, "Bob")], append=False, tablename="t")
        assert (tmp_path / "out.db").exists()

    def test_table_contains_rows(self, tmp_path):
        out = str(tmp_path / "out.db")
        export_sqlite(out, ["id", "name"], [(1, "Alice"), (2, "Bob")], append=False, tablename="t")
        con = sqlite3.connect(out)
        try:
            rows = con.execute("SELECT id, name FROM t ORDER BY id").fetchall()
        finally:
            con.close()
        assert rows == [(1, "Alice"), (2, "Bob")]

    def test_table_headers(self, tmp_path):
        out = str(tmp_path / "out.db")
        export_sqlite(out, ["alpha", "beta"], [(10, 20)], append=False, tablename="hdr_tbl")
        con = sqlite3.connect(out)
        try:
            cols = [d[0] for d in con.execute("SELECT * FROM hdr_tbl").description]
        finally:
            con.close()
        assert cols == ["alpha", "beta"]

    def test_empty_rows(self, tmp_path):
        out = str(tmp_path / "out.db")
        export_sqlite(out, ["id"], [], append=False, tablename="empty_t")
        con = sqlite3.connect(out)
        try:
            rows = con.execute("SELECT id FROM empty_t").fetchall()
        finally:
            con.close()
        assert rows == []

    def test_overwrite_existing_table(self, tmp_path):
        out = str(tmp_path / "out.db")
        export_sqlite(out, ["val"], [(1,)], append=False, tablename="t")
        # Second call with append=False should drop and recreate the table
        export_sqlite(out, ["val"], [(99,)], append=False, tablename="t")
        con = sqlite3.connect(out)
        try:
            rows = con.execute("SELECT val FROM t").fetchall()
        finally:
            con.close()
        assert rows == [(99,)]

    def test_append_to_existing_table_raises(self, tmp_path):
        out = str(tmp_path / "out.db")
        export_sqlite(out, ["val"], [(1,)], append=False, tablename="t")
        # append=True to an existing table should raise ErrInfo
        with pytest.raises(ErrInfo):
            export_sqlite(out, ["val"], [(2,)], append=True, tablename="t")

    def test_large_batch(self, tmp_path):
        """Write more than the 10,000-row chunk size."""
        out = str(tmp_path / "large.db")
        rows = [(i, f"name_{i}") for i in range(12_000)]
        export_sqlite(out, ["id", "name"], rows, append=False, tablename="big")
        con = sqlite3.connect(out)
        try:
            count = con.execute("SELECT count(*) FROM big").fetchone()[0]
        finally:
            con.close()
        assert count == 12_000

    def test_none_values(self, tmp_path):
        out = str(tmp_path / "out.db")
        export_sqlite(out, ["id", "val"], [(1, None)], append=False, tablename="t")
        con = sqlite3.connect(out)
        try:
            rows = con.execute("SELECT val FROM t").fetchall()
        finally:
            con.close()
        assert rows == [(None,)]


# ---------------------------------------------------------------------------
# write_query_to_sqlite
# ---------------------------------------------------------------------------


class TestWriteQueryToSqlite:
    def test_writes_result_to_file(self, tmp_path):
        out = str(tmp_path / "out.db")
        db = FakeDB(["x", "y"], [(1, "a"), (2, "b")])
        write_query_to_sqlite("SELECT x, y FROM t", db, out, append=False, tablename="res")
        con = sqlite3.connect(out)
        try:
            rows = con.execute("SELECT x, y FROM res ORDER BY x").fetchall()
        finally:
            con.close()
        assert rows == [(1, "a"), (2, "b")]

    def test_driver_error_raises_errinfo(self, tmp_path):
        out = str(tmp_path / "out.db")
        db = ErrorDB()
        with pytest.raises(ErrInfo):
            write_query_to_sqlite("SELECT 1", db, out, append=False, tablename="t")

    def test_errinfo_from_db_is_reraised(self, tmp_path):
        """ErrInfo raised by select_rowsource must propagate unchanged (line 77)."""
        out = str(tmp_path / "out.db")
        original = ErrInfo(type="db", exception_msg="original error")

        class ErrInfoDB:
            def select_rowsource(self, sql):
                raise original

        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_sqlite("SELECT 1", ErrInfoDB(), out, append=False, tablename="t")
        assert exc_info.value is original
