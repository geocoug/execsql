"""
Pretty-print and raw export round trips, driven by a real database.

``prettyprint_rowset`` draws a fixed-width table, so its correctness condition
is alignment: every row must occupy one line and every column must line up. A
newline or a tab inside a value broke both.

``write_query_raw`` writes a column's bytes straight to a file with no framing
at all — that is its purpose — so what is checked here is that the bytes come
out unchanged.
"""

from __future__ import annotations

from execsql.exporters.pretty import prettyprint_rowset
from execsql.exporters.raw import write_query_raw

from .conftest import HEADERS, TABLE_NAME


def _pretty_lines(db, outfile, columns="*"):
    hdrs, rows = db.select_data(f"select {columns} from {TABLE_NAME} order by id;")
    prettyprint_rowset(hdrs, iter(rows), str(outfile))
    return outfile.read_text(encoding="utf-8").splitlines()


def _data_lines(lines):
    """Rows of the drawn table, excluding the header and its rule.

    The table is header, then a rule of dashes, then the data.
    """
    rule = next(i for i, ln in enumerate(lines) if set(ln.strip()) <= set("-| ") and "-" in ln)
    return [ln for ln in lines[rule + 1 :] if ln.strip()]


class TestPrettyTableAlignment:
    """A newline or tab in a value split the row and misaligned every column.

        1  | has "quotes", a comma, a	tab and a
    newline | 0
    """

    def test_every_data_row_is_one_line(self, export_db, tmp_path):
        lines = _pretty_lines(export_db, tmp_path / "out.txt")
        rows = _data_lines(lines)
        assert len(rows) == 2, f"expected two rows, got {len(rows)}: {rows}"

    def test_no_line_lacks_the_column_separator(self, export_db, tmp_path):
        """A split row leaves a fragment with no table structure at all."""
        lines = _pretty_lines(export_db, tmp_path / "out.txt")
        stray = [ln for ln in lines if ln.strip() and "|" not in ln]
        assert not stray, f"values escaped the table: {stray}"

    def test_every_row_has_the_same_width(self, export_db, tmp_path):
        """Fixed-width means fixed width."""
        rows = _data_lines(_pretty_lines(export_db, tmp_path / "out.txt"))
        assert len({len(r.rstrip()) for r in rows}) <= 2, "rows are ragged"

    def test_separators_line_up_across_rows(self, export_db, tmp_path):
        """Every column boundary in the rule must be a boundary in every row.

        Scanning rows for "|" would miscount — one of the values contains a
        literal pipe — so the boundaries come from the rule line, which holds
        no data, and are then checked against each row.
        """
        lines = _pretty_lines(export_db, tmp_path / "out.txt")
        rule = next(ln for ln in lines if set(ln.strip()) <= set("-| ") and "-" in ln)
        boundaries = [i for i, ch in enumerate(rule) if ch == "|"]
        for row in _data_lines(lines):
            misplaced = [i for i in boundaries if i < len(row) and row[i] != "|"]
            assert not misplaced, f"column boundary moved at {misplaced}: {row!r}"

    def test_the_break_is_still_visible(self, export_db, tmp_path):
        r"""The value is shown escaped rather than silently flattened."""
        text = "\n".join(_pretty_lines(export_db, tmp_path / "out.txt"))
        assert r"\n" in text


class TestPrettyValues:
    def test_unicode_survives(self, export_db, tmp_path):
        text = "\n".join(_pretty_lines(export_db, tmp_path / "out.txt"))
        assert "café — naïve ± 30° ⚡" in text

    def test_zero_is_rendered(self, export_db, tmp_path):
        """A falsy value is still a value."""
        rows = _data_lines(_pretty_lines(export_db, tmp_path / "out.txt", columns="id, n_zero"))
        assert rows[0].rstrip().endswith("0")

    def test_headers_are_the_column_names(self, export_db, tmp_path):
        lines = _pretty_lines(export_db, tmp_path / "out.txt")
        assert all(name in lines[0] for name in HEADERS)


class TestRawExport:
    """No framing, no escaping — the bytes are the point."""

    def test_text_column_is_written_verbatim(self, export_db, tmp_path):
        _, rows = export_db.select_data(f"select t_awkward from {TABLE_NAME} where id = 1;")
        out = tmp_path / "out.bin"
        write_query_raw(str(out), iter(rows), "utf-8")
        assert out.read_bytes().decode("utf-8") == rows[0][0]

    def test_unicode_is_written_in_the_requested_encoding(self, export_db, tmp_path):
        _, rows = export_db.select_data(f"select t_unicode from {TABLE_NAME} where id = 1;")
        out = tmp_path / "out.bin"
        write_query_raw(str(out), iter(rows), "utf-8")
        assert out.read_bytes() == "café — naïve ± 30° ⚡".encode()

    def test_no_separator_or_terminator_is_added(self, export_db, tmp_path):
        """Raw means raw: nothing is appended to the value."""
        _, rows = export_db.select_data(f"select t_short from {TABLE_NAME} where id = 1;")
        out = tmp_path / "out.bin"
        write_query_raw(str(out), iter(rows), "utf-8")
        assert out.read_bytes() == b"plain"
