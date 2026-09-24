"""
CSV/TSV export round trips, driven by a real database.

``tests/exporters/test_delimited.py`` checks the writer against rows the test
author typed.  This module checks it against rows a driver actually returned,
across every Tier 1 backend that can be reached, and reads the file back with
the stdlib :mod:`csv` parser rather than eyeballing substrings.

The two questions it answers that a stub cannot:

- does what each driver returns for ``numeric``, ``date``, and ``timestamp``
  survive being written and re-parsed?
- does text containing the delimiter, the quote character, a tab, and a
  newline come back byte-identical?
"""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal

from execsql.exporters.delimited import write_delimited_file

from .conftest import HEADERS, TABLE_NAME


def _export(db, outfile, filefmt="csv"):
    """Export the whole round-trip table through the exporter under test."""
    headers, rows = db.select_data(f"select * from {TABLE_NAME} order by id;")
    write_delimited_file(str(outfile), filefmt, headers, iter(rows))
    return headers, rows


def _read_csv(path, **kw):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f, **kw))


class TestCsvRoundTrip:
    def test_headers_are_the_database_column_names(self, export_db, tmp_path):
        out = tmp_path / "out.csv"
        _export(export_db, out)
        assert _read_csv(out)[0] == HEADERS

    def test_row_count_survives(self, export_db, tmp_path):
        out = tmp_path / "out.csv"
        _export(export_db, out)
        assert len(_read_csv(out)) == 3, "header + two data rows"

    def test_awkward_text_survives_verbatim(self, export_db, tmp_path):
        """Delimiter, quote, tab and newline inside one value must round-trip."""
        out = tmp_path / "out.csv"
        _, rows = _export(export_db, out)
        written = _read_csv(out)
        col = HEADERS.index("t_awkward")
        assert written[1][col] == rows[0][col]

    def test_unicode_survives(self, export_db, tmp_path):
        out = tmp_path / "out.csv"
        _, rows = _export(export_db, out)
        col = HEADERS.index("t_unicode")
        assert _read_csv(out)[1][col] == rows[0][col]

    def test_null_is_not_the_string_none(self, export_db, tmp_path):
        """Every column of row 2 is NULL; none may export as Python's "None"."""
        out = tmp_path / "out.csv"
        _export(export_db, out)
        null_row = _read_csv(out)[2]
        assert null_row[0] == "2", "the id column is not null"
        assert set(null_row[1:]) <= {""}, f"NULL leaked as a literal: {null_row!r}"

    def test_numeric_keeps_its_value(self, export_db, tmp_path):
        """A driver may hand back Decimal or float; the written value is the same number."""
        out = tmp_path / "out.csv"
        _, rows = _export(export_db, out)
        col = HEADERS.index("n_dec")
        assert Decimal(_read_csv(out)[1][col]) == Decimal(str(rows[0][col]))

    def test_date_is_iso_formatted(self, export_db, tmp_path):
        """Whether the driver returns a date object or a string, the file gets ISO."""
        out = tmp_path / "out.csv"
        _export(export_db, out)
        written = _read_csv(out)[1][HEADERS.index("d_date")]
        assert datetime.date.fromisoformat(written[:10]) == datetime.date(2026, 9, 24)

    def test_timestamp_keeps_date_and_time(self, export_db, tmp_path):
        out = tmp_path / "out.csv"
        _export(export_db, out)
        written = _read_csv(out)[1][HEADERS.index("d_stamp")]
        parsed = datetime.datetime.fromisoformat(written)
        assert (parsed.year, parsed.month, parsed.day) == (2026, 9, 24)
        assert (parsed.hour, parsed.minute, parsed.second) == (13, 45, 56)

    def test_negative_integer_survives(self, export_db, tmp_path):
        out = tmp_path / "out.csv"
        _export(export_db, out)
        assert int(_read_csv(out)[1][HEADERS.index("n_int")]) == -42


class TestTabRoundTrip:
    def test_tab_quoted_format_round_trips_awkward_text(self, export_db, tmp_path):
        """``tabq`` quotes fields, so an embedded tab must survive the trip."""
        out = tmp_path / "out.tsv"
        _, rows = _export(export_db, out, filefmt="tabq")
        written = _read_csv(out, delimiter="\t")
        col = HEADERS.index("t_awkward")
        assert written[1][col] == rows[0][col]

    def test_tab_format_headers(self, export_db, tmp_path):
        out = tmp_path / "out.tsv"
        _export(export_db, out, filefmt="tab")
        assert _read_csv(out, delimiter="\t")[0] == HEADERS
