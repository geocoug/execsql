"""
SQLite and DuckDB database-file export round trips, driven by a real database.

These exporters write a database rather than a document, which makes the round
trip exact: export a table, then query the written file back and compare it to
what the source driver returned. No parsing, no rendering, no formatting in
between to argue about.

This is also the path ``COPY`` uses to move data between backends, so a value
that does not survive here does not survive a cross-database copy either.
"""

from __future__ import annotations

import datetime
import sqlite3
from decimal import Decimal

import pytest

from execsql.exporters.sqlite import export_sqlite

from .conftest import HEADERS, TABLE_NAME

OUT_TABLE = "exported"


def _source_rows(db):
    return db.select_data(f"select * from {TABLE_NAME} order by id;")


def _col(rows, row, name):
    return rows[row][HEADERS.index(name)]


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_export(export_db, tmp_path):
    """Export the round-trip table to a SQLite file and read it back."""
    hdrs, rows = _source_rows(export_db)
    out = tmp_path / "exported.sqlite"
    export_sqlite(str(out), hdrs, list(rows), False, OUT_TABLE)
    conn = sqlite3.connect(str(out))
    try:
        cur = conn.execute(f"select * from {OUT_TABLE} order by id;")
        written = [list(r) for r in cur.fetchall()]
        names = [d[0] for d in cur.description]
    finally:
        conn.close()
    return names, written, rows


class TestSqliteFileExport:
    def test_column_names_survive(self, sqlite_export):
        names, _, _ = sqlite_export
        assert names == HEADERS

    def test_row_count(self, sqlite_export):
        _, written, _ = sqlite_export
        assert len(written) == 2

    def test_unicode_survives(self, sqlite_export):
        _, written, _ = sqlite_export
        assert _col(written, 0, "t_unicode") == "café — naïve ± 30° ⚡"

    def test_awkward_text_survives_verbatim(self, sqlite_export):
        """Quote, comma, tab and newline, through a second database."""
        _, written, source = sqlite_export
        assert _col(written, 0, "t_awkward") == _col(source, 0, "t_awkward")

    def test_single_quote_survives(self, sqlite_export):
        """Parameterised insert, so the quote is data rather than syntax."""
        _, written, _ = sqlite_export
        assert _col(written, 0, "t_quote") == "O'Brien said 'hi'; -- not a comment"

    def test_nulls_stay_null(self, sqlite_export):
        _, written, _ = sqlite_export
        nulls = [v for name, v in zip(HEADERS, written[1]) if name != "id"]
        assert set(nulls) == {None}, f"a NULL did not survive: {written[1]}"

    def test_zero_is_not_null(self, sqlite_export):
        _, written, _ = sqlite_export
        assert _col(written, 0, "n_zero") == 0

    def test_negative_integer_survives(self, sqlite_export):
        _, written, _ = sqlite_export
        assert _col(written, 0, "n_int") == -42

    def test_numeric_keeps_its_value(self, sqlite_export):
        """SQLite has no decimal type; the value must still be recoverable."""
        _, written, _ = sqlite_export
        assert Decimal(str(_col(written, 0, "n_dec"))) == Decimal("1234.567")

    def test_date_is_recoverable(self, sqlite_export):
        _, written, _ = sqlite_export
        value = str(_col(written, 0, "d_date"))
        assert datetime.date.fromisoformat(value[:10]) == datetime.date(2026, 9, 24)

    def test_timestamp_keeps_its_time(self, sqlite_export):
        _, written, _ = sqlite_export
        assert "13:45:56" in str(_col(written, 0, "d_stamp"))


# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------


@pytest.fixture
def duckdb_export(export_db, tmp_path):
    """Export the round-trip table to a DuckDB file and read it back."""
    duckdb = pytest.importorskip("duckdb", reason="duckdb not installed")
    from execsql.exporters.duckdb import export_duckdb

    hdrs, rows = _source_rows(export_db)
    out = tmp_path / "exported.duckdb"
    export_duckdb(str(out), hdrs, list(rows), False, OUT_TABLE)
    conn = duckdb.connect(str(out))
    try:
        cur = conn.execute(f"select * from {OUT_TABLE} order by id;")
        written = [list(r) for r in cur.fetchall()]
        names = [d[0] for d in cur.description]
    finally:
        conn.close()
    return names, written, rows


class TestDuckdbFileExport:
    def test_column_names_survive(self, duckdb_export):
        names, _, _ = duckdb_export
        assert names == HEADERS

    def test_row_count(self, duckdb_export):
        _, written, _ = duckdb_export
        assert len(written) == 2

    def test_unicode_survives(self, duckdb_export):
        _, written, _ = duckdb_export
        assert _col(written, 0, "t_unicode") == "café — naïve ± 30° ⚡"

    def test_awkward_text_survives_verbatim(self, duckdb_export):
        _, written, source = duckdb_export
        assert _col(written, 0, "t_awkward") == _col(source, 0, "t_awkward")

    def test_single_quote_survives(self, duckdb_export):
        _, written, _ = duckdb_export
        assert _col(written, 0, "t_quote") == "O'Brien said 'hi'; -- not a comment"

    def test_nulls_stay_null(self, duckdb_export):
        _, written, _ = duckdb_export
        nulls = [v for name, v in zip(HEADERS, written[1]) if name != "id"]
        assert set(nulls) == {None}, f"a NULL did not survive: {written[1]}"

    def test_zero_is_not_null(self, duckdb_export):
        _, written, _ = duckdb_export
        assert _col(written, 0, "n_zero") == 0

    def test_numeric_keeps_its_value(self, duckdb_export):
        _, written, _ = duckdb_export
        assert Decimal(str(_col(written, 0, "n_dec"))) == Decimal("1234.567")

    def test_date_is_recoverable(self, duckdb_export):
        _, written, _ = duckdb_export
        value = _col(written, 0, "d_date")
        if isinstance(value, datetime.datetime):
            value = value.date()  # DuckDB may widen a date column to TIMESTAMP
        elif not isinstance(value, datetime.date):
            value = datetime.date.fromisoformat(str(value)[:10])
        assert value == datetime.date(2026, 9, 24)


class TestDuckdbFloatPrecision:
    """DT_Float is IEEE double precision, and a Python float always is one.

    DuckDB's REAL is single precision, so exporting 1234.567 produced a column
    holding 1234.5670166015625.  Every other backend maps DT_Float to a double;
    DuckDB was the only one that did not.
    """

    def test_a_double_is_not_narrowed_to_single_precision(self, export_db, tmp_path):
        duckdb = pytest.importorskip("duckdb", reason="duckdb not installed")
        from execsql.exporters.duckdb import export_duckdb

        out = tmp_path / "precision.duckdb"
        export_duckdb(str(out), ["v"], [[1234.567]], False, "t")
        conn = duckdb.connect(str(out))
        try:
            assert conn.execute("select v from t;").fetchone()[0] == 1234.567
        finally:
            conn.close()

    def test_the_column_is_declared_double(self, export_db, tmp_path):
        duckdb = pytest.importorskip("duckdb", reason="duckdb not installed")
        from execsql.exporters.duckdb import export_duckdb

        out = tmp_path / "declared.duckdb"
        export_duckdb(str(out), ["v"], [[1.5]], False, "t")
        conn = duckdb.connect(str(out))
        try:
            coltype = conn.execute("describe t;").fetchall()[0][1]
            assert coltype == "DOUBLE", f"float column declared {coltype}"
        finally:
            conn.close()
