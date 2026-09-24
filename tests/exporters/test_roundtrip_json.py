"""
JSON export round trips, driven by a real database.

``write_query_to_json`` takes the connection itself and runs the query, so the
fixture hands it a live database rather than a stub.  Output is read back with
:func:`json.loads` — if the writer emits anything that is not valid JSON, the
parser says so, which eyeballing substrings cannot.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from execsql.exporters.json import write_query_to_json

from .conftest import HEADERS, TABLE_NAME


def _export(db, outfile):
    write_query_to_json(f"select * from {TABLE_NAME} order by id;", db, str(outfile))
    with open(outfile, encoding="utf-8") as f:
        return json.load(f)


class TestJsonRoundTrip:
    def test_output_is_valid_json(self, export_db, tmp_path):
        assert isinstance(_export(export_db, tmp_path / "out.json"), list)

    def test_one_object_per_row(self, export_db, tmp_path):
        assert len(_export(export_db, tmp_path / "out.json")) == 2

    def test_keys_are_the_database_column_names(self, export_db, tmp_path):
        assert list(_export(export_db, tmp_path / "out.json")[0]) == HEADERS

    def test_null_becomes_json_null(self, export_db, tmp_path):
        """Row 2 is NULL in every nullable column — none may become "None"."""
        null_row = _export(export_db, tmp_path / "out.json")[1]
        assert null_row["id"] == 2
        leaked = {k: v for k, v in null_row.items() if k != "id" and v is not None}
        assert not leaked, f"NULL did not round-trip as null: {leaked}"

    def test_unicode_survives(self, export_db, tmp_path):
        row = _export(export_db, tmp_path / "out.json")[0]
        assert row["t_unicode"] == "café — naïve ± 30° ⚡"

    def test_awkward_text_survives_verbatim(self, export_db, tmp_path):
        """Quote, comma, tab and newline inside one value must come back intact."""
        row = _export(export_db, tmp_path / "out.json")[0]
        assert row["t_awkward"] == 'has "quotes", a comma, a\ttab and a\nnewline'

    def test_integer_stays_a_json_number(self, export_db, tmp_path):
        row = _export(export_db, tmp_path / "out.json")[0]
        assert row["n_int"] == -42
        assert isinstance(row["n_int"], int)

    def test_float_stays_a_json_number(self, export_db, tmp_path):
        row = _export(export_db, tmp_path / "out.json")[0]
        assert row["n_float"] == 2.5

    def test_numeric_keeps_its_value_whatever_json_type_it_takes(self, export_db, tmp_path):
        """A driver returning Decimal writes a JSON string; one returning float writes a number.

        The exporter passes ``default=str`` to :func:`json.dumps`, which has no
        representation for Decimal and falls back to its string form.  So the
        *type* in the file depends on the driver — SQLite hands back float and
        gets a number, PostgreSQL and DuckDB hand back Decimal and get a string.
        The value must be the same either way.
        """
        row = _export(export_db, tmp_path / "out.json")[0]
        assert Decimal(str(row["n_dec"])) == Decimal("1234.567")

    def test_date_is_recoverable(self, export_db, tmp_path):
        row = _export(export_db, tmp_path / "out.json")[0]
        assert datetime.date.fromisoformat(str(row["d_date"])[:10]) == datetime.date(2026, 9, 24)

    def test_timestamp_is_recoverable(self, export_db, tmp_path):
        row = _export(export_db, tmp_path / "out.json")[0]
        parsed = datetime.datetime.fromisoformat(str(row["d_stamp"]))
        assert parsed.replace(microsecond=0) == datetime.datetime(2026, 9, 24, 13, 45, 56)
