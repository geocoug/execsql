"""
Parquet and Feather export round trips, driven by a real database.

Both formats store a schema alongside the data, so unlike CSV they can be
checked on *type* and not only on value — and type is precisely what the XLSX
exporter got wrong, turning every ``numeric`` column into text. These tests pin
the property down here so the same mistake cannot arrive quietly in a columnar
format, where a silently-stringified measurement column would survive into
whatever reads the file next.

Read back with polars, the same library the exporters write with.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from .conftest import HEADERS, TABLE_NAME

pl = pytest.importorskip("polars", reason="requires polars (execsql2[formats])")

from execsql.exporters.feather import write_query_to_feather  # noqa: E402
from execsql.exporters.parquet import write_query_to_parquet  # noqa: E402

#: (name, writer, polars reader) for the two columnar formats.
FORMATS = [
    ("parquet", write_query_to_parquet, lambda p: pl.read_parquet(p)),
    ("feather", write_query_to_feather, lambda p: pl.read_ipc(p)),
]
FORMAT_IDS = [f[0] for f in FORMATS]


@pytest.fixture(params=FORMATS, ids=FORMAT_IDS)
def columnar(request, export_db, tmp_path):
    """Export the round-trip table and read it back as a polars DataFrame."""
    name, writer, reader = request.param
    headers, rows = export_db.select_data(f"select * from {TABLE_NAME} order by id;")
    out = tmp_path / f"out.{name}"
    writer(str(out), headers, iter(rows))
    return reader(out), rows


class TestColumnarRoundTrip:
    def test_columns_are_the_database_column_names(self, columnar):
        df, _ = columnar
        assert df.columns == HEADERS

    def test_row_count(self, columnar):
        df, _ = columnar
        assert df.height == 2

    def test_null_row_is_null_not_a_string(self, columnar):
        """Row 2 is NULL in every nullable column; none may arrive as "None"."""
        df, _ = columnar
        leaked = {name: df[name][1] for name in HEADERS if name != "id" and df[name][1] is not None}
        assert not leaked, f"NULL did not survive as null: {leaked}"

    def test_unicode_survives(self, columnar):
        df, _ = columnar
        assert df["t_unicode"][0] == "café — naïve ± 30° ⚡"

    def test_awkward_text_survives_verbatim(self, columnar):
        df, _ = columnar
        assert df["t_awkward"][0] == 'has "quotes", a comma, a\ttab and a\nnewline'

    def test_integer_stays_an_integer(self, columnar):
        df, _ = columnar
        assert df["n_int"][0] == -42
        assert df["n_int"].dtype.is_integer(), f"got {df['n_int'].dtype}"

    def test_float_stays_a_float(self, columnar):
        df, _ = columnar
        assert df["n_float"][0] == 2.5
        assert df["n_float"].dtype.is_float()

    def test_numeric_keeps_its_value(self, columnar):
        df, _ = columnar
        assert Decimal(str(df["n_dec"][0])) == Decimal("1234.567")


class TestDriverTypesAreNotFlattenedToText:
    """What the driver hands over must not be stringified on the way out.

    A columnar file carries its schema, so a measurement column written as text
    stays text for every reader downstream — the XLSX failure, in a format
    where it is harder to notice.
    """

    def test_numeric_is_not_written_as_text(self, columnar):
        df, rows = columnar
        driver_value = rows[0][HEADERS.index("n_dec")]
        if isinstance(driver_value, Decimal):
            assert df["n_dec"].dtype == pl.Decimal, f"Decimal was flattened to {df['n_dec'].dtype}"
        else:
            # SQLite has no decimal type and returns float; that is the driver's
            # answer, not the exporter's, and must arrive as a number either way.
            assert df["n_dec"].dtype.is_numeric(), f"got {df['n_dec'].dtype}"

    def test_date_is_not_written_as_text(self, columnar):
        df, rows = columnar
        driver_value = rows[0][HEADERS.index("d_date")]
        if isinstance(driver_value, datetime.date):
            assert df["d_date"].dtype == pl.Date, f"date was flattened to {df['d_date'].dtype}"
        else:
            assert str(df["d_date"][0]).startswith("2026-09-24")

    def test_timestamp_is_not_written_as_text(self, columnar):
        df, rows = columnar
        driver_value = rows[0][HEADERS.index("d_stamp")]
        if isinstance(driver_value, datetime.datetime):
            assert df["d_stamp"].dtype == pl.Datetime, f"timestamp was flattened to {df['d_stamp'].dtype}"
            assert df["d_stamp"][0].hour == 13
        else:
            assert "13:45:56" in str(df["d_stamp"][0])


class TestEmptyResultSet:
    """An empty result must still produce a readable file with the right columns."""

    @pytest.mark.parametrize("name,writer,reader", FORMATS, ids=FORMAT_IDS)
    def test_empty_query_writes_headers_only(self, export_db, tmp_path, name, writer, reader):
        headers, rows = export_db.select_data(f"select * from {TABLE_NAME} where id < 0;")
        out = tmp_path / f"empty.{name}"
        writer(str(out), headers, iter(rows))
        df = reader(out)
        assert df.columns == HEADERS
        assert df.height == 0
