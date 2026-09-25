"""
HTML and Markdown export round trips, driven by a real database.

Both formats embed values in a structure that certain characters can break —
``<``, ``>``, ``&`` in HTML; ``|`` in a GitHub-flavoured Markdown table — so
these check that a value carrying them arrives intact rather than as markup.

They also check the values that are *falsy but real*.  A zero measurement is a
result, not an absence, and the HTML exporter rendered cells with
``str(v) if v else ''`` — which is empty for ``0``, ``False``, and ``""``.
"""

from __future__ import annotations

import html as html_mod
import re

from execsql.exporters.html import export_html
from execsql.exporters.markdown import write_query_to_markdown

from .conftest import HEADERS, TABLE_NAME

#: The value in t_markup — every character that breaks one of these formats.
MARKUP = '<b>a & b</b> | "pipe" <script>'


def _html_cells(db, outfile, row=0):
    """Export to HTML and return the <td> contents of a data row."""
    hdrs, rows = db.select_data(f"select * from {TABLE_NAME} order by id;")
    export_html(str(outfile), hdrs, iter(rows), querytext="select *")
    body = outfile.read_text(encoding="utf-8")
    row_bodies = re.findall(r"<tr>(.*?)</tr>", body, re.S)
    data_rows = [r for r in row_bodies if "<td>" in r]
    return re.findall(r"<td>(.*?)</td>", data_rows[row], re.S)


def _markdown_rows(db, outfile):
    """Export to Markdown and return the table's rows, split on unescaped pipes."""
    write_query_to_markdown(f"select * from {TABLE_NAME} order by id;", db, str(outfile))
    lines = [ln for ln in outfile.read_text(encoding="utf-8").splitlines() if ln.startswith("|")]
    parsed = []
    for line in lines:
        # Split on pipes that are not backslash-escaped.
        cells = re.split(r"(?<!\\)\|", line)[1:-1]
        parsed.append([c.strip() for c in cells])
    return parsed


class TestHtmlEscaping:
    def test_markup_characters_are_escaped(self, export_db, tmp_path):
        """A value containing tags must arrive as text, not as markup."""
        cells = _html_cells(export_db, tmp_path / "out.html")
        cell = cells[HEADERS.index("t_markup")]
        assert "<script>" not in cell, "markup was emitted unescaped"
        assert cell == html_mod.escape(MARKUP)

    def test_escaped_markup_decodes_to_the_original(self, export_db, tmp_path):
        cells = _html_cells(export_db, tmp_path / "out.html")
        assert html_mod.unescape(cells[HEADERS.index("t_markup")]) == MARKUP

    def test_unicode_survives(self, export_db, tmp_path):
        cells = _html_cells(export_db, tmp_path / "out.html")
        assert html_mod.unescape(cells[HEADERS.index("t_unicode")]) == "café — naïve ± 30° ⚡"


class TestHtmlFalsyValues:
    """``if v`` was used where ``if v is not None`` was meant.

    A zero is a result. Rendering it as an empty cell loses data in a way that
    looks, in the output, exactly like a NULL.
    """

    def test_zero_is_not_blank(self, export_db, tmp_path):
        cells = _html_cells(export_db, tmp_path / "out.html")
        assert cells[HEADERS.index("n_zero")] == "0", "a zero exported as an empty cell"

    def test_zero_is_distinguishable_from_null(self, export_db, tmp_path):
        """Row 1 has 0, row 2 has NULL — they must not look the same."""
        zero = _html_cells(export_db, tmp_path / "a.html", row=0)[HEADERS.index("n_zero")]
        null = _html_cells(export_db, tmp_path / "b.html", row=1)[HEADERS.index("n_zero")]
        assert zero != null, "0 and NULL both rendered as the same empty cell"

    def test_null_is_still_empty(self, export_db, tmp_path):
        cells = _html_cells(export_db, tmp_path / "out.html", row=1)
        assert cells[HEADERS.index("n_zero")] == ""

    def test_negative_integer_survives(self, export_db, tmp_path):
        cells = _html_cells(export_db, tmp_path / "out.html")
        assert cells[HEADERS.index("n_int")] == "-42"


class TestMarkdownTableIntegrity:
    def test_pipe_in_a_value_does_not_add_a_column(self, export_db, tmp_path):
        """An unescaped pipe would split one cell into two and shift the row."""
        rows = _markdown_rows(export_db, tmp_path / "out.md")
        widths = {len(r) for r in rows}
        assert widths == {len(HEADERS)}, f"ragged table: row widths {widths}"

    def test_pipe_is_escaped_in_the_cell(self, export_db, tmp_path):
        rows = _markdown_rows(export_db, tmp_path / "out.md")
        cell = rows[2][HEADERS.index("t_markup")]  # header, separator, then data
        assert "|" in cell.replace("\\|", "|")
        assert r"\|" in cell, "the pipe was not escaped"

    def test_header_row_is_the_column_names(self, export_db, tmp_path):
        rows = _markdown_rows(export_db, tmp_path / "out.md")
        assert rows[0] == HEADERS

    def test_zero_is_not_blank(self, export_db, tmp_path):
        rows = _markdown_rows(export_db, tmp_path / "out.md")
        assert rows[2][HEADERS.index("n_zero")] == "0"

    def test_null_renders_empty(self, export_db, tmp_path):
        rows = _markdown_rows(export_db, tmp_path / "out.md")
        assert rows[3][HEADERS.index("n_zero")] == ""


class TestMarkdownNewlineDoesNotBreakTheTable:
    """A GFM table row is one line.

    A literal newline in a value ended the row mid-cell and left the remaining
    values on a stray line outside the table:

        | 1   | has "quotes", a comma, a\ttab and a
        newline | 0      |
    """

    def test_every_table_line_is_a_table_row(self, export_db, tmp_path):
        write_query_to_markdown(f"select * from {TABLE_NAME} order by id;", export_db, str(tmp_path / "out.md"))
        text = (tmp_path / "out.md").read_text(encoding="utf-8")
        table_lines = [ln for ln in text.splitlines() if ln.strip() and ("|" in ln)]
        stray = [ln for ln in table_lines if not ln.lstrip().startswith("|")]
        assert not stray, f"values escaped the table: {stray}"

    def test_the_table_has_exactly_four_lines(self, export_db, tmp_path):
        """Header, separator, and two data rows — no more."""
        rows = _markdown_rows(export_db, tmp_path / "out.md")
        assert len(rows) == 4

    def test_the_line_break_is_preserved_as_br(self, export_db, tmp_path):
        rows = _markdown_rows(export_db, tmp_path / "out.md")
        cell = rows[2][HEADERS.index("t_awkward")]
        assert "<br>" in cell, "the line break was dropped rather than encoded"
        assert cell.replace("<br>", "\n").replace("\\|", "|") == ('has "quotes", a comma, a\ttab and a\nnewline')
