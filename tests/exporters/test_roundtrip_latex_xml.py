"""
LaTeX and XML export round trips, driven by a real database.

LaTeX has the largest escape surface of any format execsql writes — ``\\ & % $
# _ { } ~ ^`` are all special — and ``&`` is the column separator the exporter
itself emits, so an ampersand in a value silently changed the shape of the
table. XML's escaping is narrower but its structural guarantee is stronger: the
output either parses or it does not, and these tests check by parsing it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from execsql.exporters.latex import export_latex
from execsql.exporters.xml import write_query_to_xml

from .conftest import HEADERS, TABLE_NAME

MARKUP = '<b>a & b</b> | "pipe" <script>'


def _latex_rows(db, outfile):
    """Export to LaTeX and return the body rows, split on unescaped ``&``."""
    hdrs, rows = db.select_data(f"select * from {TABLE_NAME} order by id;")
    export_latex(str(outfile), hdrs, iter(rows), querytext="select *")
    body = outfile.read_text(encoding="utf-8")
    out = []
    # A LaTeX row ends at "\\\\", not at a physical newline: a value containing a
    # newline spans several lines and LaTeX treats it as whitespace, so lines
    # are joined until the row terminator before the columns are counted.
    pending = ""
    for line in body.splitlines():
        pending = f"{pending} {line}" if pending else line
        stripped = pending.strip()
        if not stripped.endswith("\\\\"):
            continue
        cells = re.split(r"(?<!\\)&", stripped[:-2])
        out.append([c.strip() for c in cells])
        pending = ""
    return out


class TestLatexTableShape:
    """``&`` is the column separator; a value containing one added a column.

    The resulting .tex does not compile — LaTeX reports "Extra alignment tab
    has been changed to \\cr" — so the export is not merely wrong, it is
    unusable.
    """

    def test_every_row_has_one_cell_per_column(self, export_db, tmp_path):
        rows = _latex_rows(export_db, tmp_path / "out.tex")
        widths = {len(r) for r in rows}
        assert widths == {len(HEADERS)}, f"ragged table: row widths {widths}"

    def test_ampersand_in_a_value_is_escaped(self, export_db, tmp_path):
        rows = _latex_rows(export_db, tmp_path / "out.tex")
        cell = rows[1][HEADERS.index("t_markup")]
        assert r"\&" in cell, "an ampersand was left as a column separator"

    def test_underscore_in_a_header_is_escaped(self, export_db, tmp_path):
        rows = _latex_rows(export_db, tmp_path / "out.tex")
        assert r"t\_markup" in rows[0]


class TestLatexNullHandling:
    """``str(c)`` rendered NULL as the literal text "None"."""

    def test_null_is_an_empty_cell(self, export_db, tmp_path):
        rows = _latex_rows(export_db, tmp_path / "out.tex")
        null_row = rows[2]
        assert null_row[HEADERS.index("n_int")] == ""

    def test_the_word_none_appears_nowhere(self, export_db, tmp_path):
        hdrs, rows = export_db.select_data(f"select * from {TABLE_NAME} order by id;")
        out = tmp_path / "out.tex"
        export_latex(str(out), hdrs, iter(rows), querytext="select *")
        assert "None" not in out.read_text(encoding="utf-8")

    def test_zero_is_not_blank(self, export_db, tmp_path):
        """A zero is a value; only NULL is blank."""
        rows = _latex_rows(export_db, tmp_path / "out.tex")
        assert rows[1][HEADERS.index("n_zero")] == "0"


class TestLatexEscapesEverySpecialCharacter:
    def test_no_unescaped_special_survives(self, export_db, tmp_path):
        r"""Nothing in a data cell may leave ``& % $ # _ { }`` unescaped."""
        rows = _latex_rows(export_db, tmp_path / "out.tex")
        offenders = []
        for row in rows[1:]:
            for name, cell in zip(HEADERS, row):
                for ch in "&%$#_{}":
                    if re.search(r"(?<!\\)" + re.escape(ch), cell):
                        offenders.append((name, ch, cell))
        assert not offenders, f"unescaped LaTeX specials: {offenders}"


class TestXmlIsWellFormed:
    """XML either parses or it does not — so parse it."""

    def _export(self, db, outfile):
        write_query_to_xml(f"select * from {TABLE_NAME} order by id;", "row", db, str(outfile))
        return ET.parse(outfile).getroot()

    def test_output_parses(self, export_db, tmp_path):
        root = self._export(export_db, tmp_path / "out.xml")
        assert root is not None

    def test_one_element_per_row(self, export_db, tmp_path):
        root = self._export(export_db, tmp_path / "out.xml")
        assert len(list(root)) == 2

    def test_markup_in_a_value_does_not_become_markup(self, export_db, tmp_path):
        """``<script>`` in the data must be text, not an element."""
        root = self._export(export_db, tmp_path / "out.xml")
        assert root.find(".//script") is None
        assert list(root)[0].find("t_markup").text == MARKUP

    def test_unicode_survives(self, export_db, tmp_path):
        root = self._export(export_db, tmp_path / "out.xml")
        assert list(root)[0].find("t_unicode").text == "café — naïve ± 30° ⚡"

    def test_null_is_empty_not_the_word_none(self, export_db, tmp_path):
        root = self._export(export_db, tmp_path / "out.xml")
        value = list(root)[1].find("n_int").text
        assert value in (None, ""), f"NULL rendered as {value!r}"

    def test_zero_is_not_blank(self, export_db, tmp_path):
        root = self._export(export_db, tmp_path / "out.xml")
        assert list(root)[0].find("n_zero").text == "0"
