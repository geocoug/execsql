"""Tests for the shared plain-text table renderer in execsql.gui.base.

``format_table`` backs both the console GUI backend's ``_print_table`` and the
non-interactive HALT fallback in ``x_halt_msg``, so its output is user-visible
in unattended runs.
"""

from __future__ import annotations

from execsql.gui.base import DIFF_MARKER, format_table, row_count_text


class TestRowCountText:
    def test_plural(self):
        assert row_count_text(2) == "2 rows"

    def test_singular(self):
        assert row_count_text(1) == "1 row"

    def test_zero_is_plural(self):
        assert row_count_text(0) == "0 rows"

    def test_thousands_separator(self):
        assert row_count_text(12345) == "12,345 rows"


class TestFormatTable:
    def test_empty_headers_yield_empty_string(self):
        assert format_table([], [("a",)]) == ""

    def test_headers_only(self):
        """A zero-row rowset still renders headers and a separator."""
        out = format_table(["id", "reason"], [])
        lines = out.splitlines()
        assert len(lines) == 2
        assert "id" in lines[0] and "reason" in lines[0]
        assert set(lines[1].strip()) == {"-", " "}

    def test_columns_pad_to_widest_value(self):
        out = format_table(["id"], [("1",), ("longer",)])
        lines = out.splitlines()
        # Header, separator, and both data rows share one column width.
        assert len({len(line) for line in lines}) == 1

    def test_none_renders_as_empty(self):
        out = format_table(["a", "b"], [(None, "x")])
        assert "None" not in out
        assert "x" in out

    def test_non_string_values_are_stringified(self):
        out = format_table(["n"], [(42,)])
        assert "42" in out

    def test_no_trailing_newline(self):
        out = format_table(["a"], [("b",)])
        assert not out.endswith("\n")

    def test_diff_marker_applied_to_changed_cells(self):
        out = format_table(
            ["k", "v"],
            [("1", "old")],
            row_states=["changed"],
            changed_cols=[{"v"}],
        )
        assert f"{DIFF_MARKER}old" in out
        assert f"{DIFF_MARKER}1" not in out

    def test_diff_marker_width_included_in_column_sizing(self):
        """Marker width must not push the marked row wider than the others."""
        out = format_table(
            ["v"],
            [("aaa",), ("aaa",)],
            row_states=["changed", "unchanged"],
            changed_cols=[{"v"}, set()],
        )
        assert len({len(line) for line in out.splitlines()}) == 1

    def test_unchanged_rows_are_unmarked(self):
        out = format_table(
            ["v"],
            [("x",)],
            row_states=["unchanged"],
            changed_cols=[{"v"}],
        )
        assert DIFF_MARKER not in out
