"""
ODS export round trips, driven by a real database.

ODS is a zip of XML, like XLSX, and it repeated both of the mistakes that
format made: a ``numeric`` column written without a type, and text quietly
altered on the way out.  Both are checked here against what each driver
actually returns.

Cells are read back through odfpy rather than by matching strings in the XML,
so the assertions are about the document the file actually describes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from .conftest import HEADERS, TABLE_NAME

odf_load = pytest.importorskip("odf.opendocument", reason="requires odfpy (execsql2[formats])").load
from odf.namespaces import OFFICENS  # noqa: E402
from odf.table import Table, TableCell, TableRow  # noqa: E402
from odf.text import P  # noqa: E402

from execsql.exporters.ods import write_query_to_ods  # noqa: E402


def _export(db, outfile):
    """Export the round-trip table and return the data sheet's rows.

    The workbook opens with an inventory sheet; the query result is the last.
    """
    write_query_to_ods(f"select * from {TABLE_NAME} order by id;", db, str(outfile))
    doc = odf_load(str(outfile))
    tables = doc.spreadsheet.getElementsByType(Table)
    assert len(tables) >= 2, "expected an inventory sheet and a data sheet"
    return tables[-1].getElementsByType(TableRow)


def _cell(rows, row, column_name):
    return rows[row].getElementsByType(TableCell)[HEADERS.index(column_name)]


def _value_type(cell):
    return cell.attributes.get((OFFICENS, "value-type"))


def _lines(cell):
    """The cell's text, one entry per <text:p> — ODF's multi-line representation."""
    return [str(p) for p in cell.getElementsByType(P)]


class TestOdsRoundTrip:
    def test_header_row_is_the_column_names(self, export_db, tmp_path):
        rows = _export(export_db, tmp_path / "out.ods")
        assert [str(c) for c in rows[0].getElementsByType(TableCell)] == HEADERS

    def test_unicode_survives(self, export_db, tmp_path):
        rows = _export(export_db, tmp_path / "out.ods")
        assert _lines(_cell(rows, 1, "t_unicode")) == ["café — naïve ± 30° ⚡"]

    def test_integer_is_a_typed_number(self, export_db, tmp_path):
        rows = _export(export_db, tmp_path / "out.ods")
        cell = _cell(rows, 1, "n_int")
        assert _value_type(cell) == "float"
        assert Decimal(cell.attributes[(OFFICENS, "value")]) == -42


class TestNumericIsTyped:
    """A value-bearing cell must declare its type.

    ``isinstance(item, float | int)`` excluded ``Decimal``, which is what
    PostgreSQL, MySQL and DuckDB return for ``numeric``/``decimal``.  Those
    values fell through to a branch that set ``office:value`` and no
    ``office:value-type`` — not valid ODF, and a reader is free to treat the
    number as text or ignore it.
    """

    def test_numeric_column_declares_a_type(self, export_db, tmp_path):
        rows = _export(export_db, tmp_path / "out.ods")
        cell = _cell(rows, 1, "n_dec")
        assert _value_type(cell) == "float", f"numeric written with value-type {_value_type(cell)!r}"

    def test_numeric_keeps_its_value(self, export_db, tmp_path):
        rows = _export(export_db, tmp_path / "out.ods")
        cell = _cell(rows, 1, "n_dec")
        assert Decimal(cell.attributes[(OFFICENS, "value")]) == Decimal("1234.567")

    def test_every_populated_cell_declares_a_type(self, export_db, tmp_path):
        """No cell in the data row may carry a value without saying what it is."""
        rows = _export(export_db, tmp_path / "out.ods")
        untyped = [
            HEADERS[i]
            for i, cell in enumerate(rows[1].getElementsByType(TableCell))
            if cell.attributes.get((OFFICENS, "value")) is not None and _value_type(cell) is None
        ]
        assert not untyped, f"cells carry a value with no value-type: {untyped}"


class TestEmbeddedNewlineSurvives:
    """Newlines inside a value were replaced with spaces on the way out.

    An XML parser normalises a newline inside an attribute to a space, so
    ``office:string-value`` genuinely cannot carry one — but ODF's answer is
    one ``<text:p>`` per line, not silently altering the data.
    """

    def test_newline_is_not_flattened_to_a_space(self, export_db, tmp_path):
        rows = _export(export_db, tmp_path / "out.ods")
        lines = _lines(_cell(rows, 1, "t_awkward"))
        assert len(lines) == 2, f"expected two lines, got {lines!r}"

    def test_both_lines_keep_their_text(self, export_db, tmp_path):
        rows = _export(export_db, tmp_path / "out.ods")
        lines = _lines(_cell(rows, 1, "t_awkward"))
        assert lines[0] == 'has "quotes", a comma, a\ttab and a'
        assert lines[1] == "newline"

    def test_rejoining_the_lines_reproduces_the_value(self, export_db, tmp_path):
        """The exported cell must still describe the string the database holds."""
        _, db_rows = export_db.select_data(f"select * from {TABLE_NAME} order by id;")
        original = db_rows[0][HEADERS.index("t_awkward")]
        rows = _export(export_db, tmp_path / "out.ods")
        assert "\n".join(_lines(_cell(rows, 1, "t_awkward"))) == original

    def test_single_line_text_still_uses_the_attribute(self, export_db, tmp_path):
        """Only multi-line values skip office:string-value."""
        rows = _export(export_db, tmp_path / "out.ods")
        cell = _cell(rows, 1, "t_short")
        assert cell.attributes.get((OFFICENS, "string-value")) == "plain"
