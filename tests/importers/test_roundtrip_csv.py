"""
CSV import round trips, driven by real files and real databases.

The exporter work checked one direction. This checks the other: write a real
file with the stdlib csv writer, import it through a real driver, and query the
table back.

The case that matters most is a quoted field containing a newline. RFC 4180
allows it, the stdlib writes and reads it, and execsql's own CSV *exporter*
produces it — so failing to import one means execsql cannot read back what it
just wrote.
"""

from __future__ import annotations

import csv
import pathlib

import pytest

from execsql.importers.csv import importtable

from .conftest import HEADERS, ROWS, TABLE_NAME, requires_local_infile, write_csv


def _import_and_read(db, path, table=TABLE_NAME, order="id"):
    requires_local_infile(db)
    importtable(db, None, table, str(path), is_new=True)
    order_by = f" order by {order}" if order else ""
    return db.select_data(f"select * from {table}{order_by};")


def _write(path, rows, headers=("a", "b")):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
    return path


class TestQuotedNewlineIsOneRecord:
    """A quoted field containing a newline is one field, not two rows.

    Diagnosis scanned physical lines, so ``"one`` and ``two",x`` had
    inconsistent delimiter counts and the real delimiter was rejected. The
    header came back as a single column named ``a,b`` and the row split in two
    with the quote characters still in it.
    """

    def test_the_row_is_not_split(self, import_db, tmp_path):
        path = _write(tmp_path / "nl.csv", [["one\ntwo", "x"]])
        _, rows = _import_and_read(import_db, path, "nl_table", order=None)
        assert len(rows) == 1, f"one record became {len(rows)} rows: {rows}"

    def test_the_header_is_split_into_columns(self, import_db, tmp_path):
        path = _write(tmp_path / "nl.csv", [["one\ntwo", "x"]])
        hdrs, _ = _import_and_read(import_db, path, "nl_table", order=None)
        assert hdrs == ["a", "b"], f"delimiter was not detected: {hdrs}"

    def test_the_newline_is_preserved_in_the_value(self, import_db, tmp_path):
        path = _write(tmp_path / "nl.csv", [["one\ntwo", "x"]])
        _, rows = _import_and_read(import_db, path, "nl_table", order=None)
        assert rows[0][0] == "one\ntwo"

    def test_no_quote_characters_leak_into_the_data(self, import_db, tmp_path):
        path = _write(tmp_path / "nl.csv", [["one\ntwo", "x"]])
        _, rows = _import_and_read(import_db, path, "nl_table", order=None)
        assert '"' not in str(rows[0][0])

    def test_a_newline_in_a_later_row_also_works(self, import_db, tmp_path):
        """Diagnosis reads several lines; the break must be handled anywhere."""
        path = _write(tmp_path / "nl.csv", [["p", "q"], ["r", "s"], ["multi\nline", "t"]])
        _, rows = _import_and_read(import_db, path, "nl_table", order=None)
        assert len(rows) == 3
        assert any(r[0] == "multi\nline" for r in rows)


class TestFullTableRoundTrip:
    """Every awkward value, written to a file and imported back."""

    def _round_trip(self, db, tmp_path):
        path = write_csv(tmp_path / "full.csv")
        return _import_and_read(db, path)

    def test_column_names_survive(self, import_db, tmp_path):
        hdrs, _ = self._round_trip(import_db, tmp_path)
        assert hdrs == HEADERS

    def test_row_count(self, import_db, tmp_path):
        _, rows = self._round_trip(import_db, tmp_path)
        assert len(rows) == 2

    def test_unicode_survives(self, import_db, tmp_path):
        _, rows = self._round_trip(import_db, tmp_path)
        assert rows[0][HEADERS.index("t_unicode")] == "café — naïve ± 30° ⚡"

    def test_awkward_text_survives_verbatim(self, import_db, tmp_path):
        """Quote, comma and newline in one value, through a real file."""
        _, rows = self._round_trip(import_db, tmp_path)
        assert rows[0][HEADERS.index("t_awkward")] == ROWS[0][HEADERS.index("t_awkward")]

    def test_empty_fields_become_null(self, import_db, tmp_path):
        """Row 2 is empty in every column but id; those must be NULL, not ""."""
        _, rows = self._round_trip(import_db, tmp_path)
        values = [v for name, v in zip(HEADERS, rows[1]) if name != "id"]
        assert set(values) == {None}, f"an empty field did not become NULL: {rows[1]}"

    def test_negative_integer_survives(self, import_db, tmp_path):
        _, rows = self._round_trip(import_db, tmp_path)
        assert int(rows[0][HEADERS.index("n_int")]) == -42

    def test_numeric_value_survives(self, import_db, tmp_path):
        from decimal import Decimal

        _, rows = self._round_trip(import_db, tmp_path)
        assert Decimal(str(rows[0][HEADERS.index("n_dec")])) == Decimal("1234.567")


class TestDelimiterDetection:
    @pytest.mark.parametrize("delimiter,name", [(",", "comma"), ("\t", "tab"), (";", "semicolon"), ("|", "pipe")])
    def test_delimiter_is_detected(self, import_db, tmp_path, delimiter, name):
        path = write_csv(tmp_path / f"{name}.csv", delimiter=delimiter)
        hdrs, rows = _import_and_read(import_db, path)
        assert hdrs == HEADERS, f"{name} delimiter not detected"
        assert len(rows) == 2


class TestCrlfFileIsReadCorrectly:
    r"""A CRLF file must not leave a carriage return on the last field.

    MySQL's LOAD DATA defaults to "\n" as the line terminator, so every row's
    final field kept a trailing "\r". The value was not empty, so the NULLIF
    that maps empty fields to NULL could not see it, and a date column became
    0000-00-00. csv.writer emits CRLF by default, so this is the ordinary case.
    """

    def test_the_last_column_of_an_empty_row_is_null(self, import_db, tmp_path):
        path = write_csv(tmp_path / "crlf.csv")
        _, rows = _import_and_read(import_db, path)
        assert rows[1][HEADERS.index("d_date")] is None

    def test_no_value_carries_a_trailing_carriage_return(self, import_db, tmp_path):
        path = write_csv(tmp_path / "crlf.csv")
        _, rows = _import_and_read(import_db, path)
        offenders = [(n, v) for n, v in zip(HEADERS, rows[0]) if isinstance(v, str) and v.endswith("\r")]
        assert not offenders, f"carriage return left in data: {offenders}"

    def test_the_file_really_is_crlf(self, tmp_path):
        """Guards the premise: if csv.writer stops emitting CRLF, say so here."""
        path = write_csv(tmp_path / "crlf.csv")
        assert b"\r\n" in pathlib.Path(path).read_bytes()
