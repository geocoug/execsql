"""
Tests for execsql.gui.base.compare_stats.

compare_stats is a pure function — it takes two tables (headers + rows)
and a list of key column names, and returns a one-line diff summary string.
No database, GUI, or file I/O involved.
"""

from __future__ import annotations


from execsql.gui.base import compare_stats


# ---------------------------------------------------------------------------
# Empty / missing key cases
# ---------------------------------------------------------------------------


class TestCompareStatsNoKeys:
    def test_empty_keylist_returns_empty_string(self):
        result = compare_stats(["id"], [(1,)], ["id"], [(1,)], keylist=[])
        assert result == ""

    def test_key_not_in_headers1_returns_empty_string(self):
        """Key column name does not appear in table-1 headers."""
        result = compare_stats(
            ["other_col"],
            [(1,)],
            ["id"],
            [(1,)],
            keylist=["id"],
        )
        assert result == ""

    def test_key_not_in_headers2_returns_empty_string(self):
        """Key column name does not appear in table-2 headers."""
        result = compare_stats(
            ["id"],
            [(1,)],
            ["other_col"],
            [(1,)],
            keylist=["id"],
        )
        assert result == ""

    def test_key_not_in_either_header_returns_empty_string(self):
        result = compare_stats(
            ["a"],
            [(1,)],
            ["b"],
            [(2,)],
            keylist=["nonexistent"],
        )
        assert result == ""


# ---------------------------------------------------------------------------
# Identical tables
# ---------------------------------------------------------------------------


class TestCompareStatsIdentical:
    def test_identical_single_row_shows_matching_count(self):
        """When all rows match, 'N matching' appears in the result."""
        result = compare_stats(
            ["id", "val"],
            [(1, "a")],
            ["id", "val"],
            [(1, "a")],
            keylist=["id"],
        )
        assert "1 matching" in result
        assert "differing" not in result

    def test_identical_multiple_rows_shows_all_matching(self):
        result = compare_stats(
            ["id", "val"],
            [(1, "a"), (2, "b"), (3, "c")],
            ["id", "val"],
            [(1, "a"), (2, "b"), (3, "c")],
            keylist=["id"],
        )
        assert "3 matching" in result
        assert "differing" not in result

    def test_identical_empty_tables_returns_tables_are_identical(self):
        """Both tables empty — no keys in common, parts list stays empty."""
        result = compare_stats(
            ["id"],
            [],
            ["id"],
            [],
            keylist=["id"],
        )
        assert result == "Tables are identical"


# ---------------------------------------------------------------------------
# Matching rows only
# ---------------------------------------------------------------------------


class TestCompareStatsMatchingOnly:
    def test_all_matching_rows_shows_matching_count(self):
        result = compare_stats(
            ["id", "name"],
            [(1, "Alice"), (2, "Bob")],
            ["id", "name"],
            [(1, "Alice"), (2, "Bob")],
            keylist=["id"],
        )
        assert "2 matching" in result
        assert "differing" not in result

    def test_matching_count_uses_comma_formatting_for_large_numbers(self):
        rows = [(i, f"val{i}") for i in range(1, 1001)]
        result = compare_stats(
            ["id", "val"],
            rows,
            ["id", "val"],
            rows,
            keylist=["id"],
        )
        assert "1,000 matching" in result


# ---------------------------------------------------------------------------
# Differing rows only
# ---------------------------------------------------------------------------


class TestCompareStatsDifferingOnly:
    def test_all_differing_rows_shows_differing_count(self):
        """Same keys in both tables but values differ."""
        result = compare_stats(
            ["id", "val"],
            [(1, "old1"), (2, "old2")],
            ["id", "val"],
            [(1, "new1"), (2, "new2")],
            keylist=["id"],
        )
        assert "2 differing" in result
        assert "matching" not in result

    def test_single_differing_row(self):
        result = compare_stats(
            ["id", "val"],
            [(10, "before")],
            ["id", "val"],
            [(10, "after")],
            keylist=["id"],
        )
        assert "1 differing" in result


# ---------------------------------------------------------------------------
# Rows only in one table
# ---------------------------------------------------------------------------


class TestCompareStatsOnlyInOne:
    def test_rows_only_in_table1_shows_only1_count(self):
        result = compare_stats(
            ["id"],
            [(1,), (2,), (3,)],
            ["id"],
            [(1,)],
            keylist=["id"],
        )
        assert "only in Table 1" in result
        assert "2" in result

    def test_rows_only_in_table2_shows_only2_count(self):
        result = compare_stats(
            ["id"],
            [(1,)],
            ["id"],
            [(1,), (2,), (3,)],
            keylist=["id"],
        )
        assert "only in Table 2" in result
        assert "2" in result

    def test_no_overlap_all_unique_to_each_table(self):
        result = compare_stats(
            ["id"],
            [(1,), (2,)],
            ["id"],
            [(3,), (4,)],
            keylist=["id"],
        )
        assert "only in Table 1" in result
        assert "only in Table 2" in result
        assert "matching" not in result
        assert "differing" not in result


# ---------------------------------------------------------------------------
# Mixed scenarios
# ---------------------------------------------------------------------------


class TestCompareStatsMixed:
    def test_mix_of_matching_differing_and_only_in_each(self):
        """
        Table1: rows 1 (matches), 2 (differs), 3 (only in T1)
        Table2: rows 1 (matches), 2 (differs), 4 (only in T2)
        """
        result = compare_stats(
            ["id", "val"],
            [(1, "same"), (2, "old"), (3, "gone")],
            ["id", "val"],
            [(1, "same"), (2, "new"), (4, "extra")],
            keylist=["id"],
        )
        assert "1 matching" in result
        assert "1 differing" in result
        assert "1 only in Table 1" in result
        assert "1 only in Table 2" in result

    def test_result_parts_joined_with_pipe_separator(self):
        result = compare_stats(
            ["id", "val"],
            [(1, "same"), (2, "old")],
            ["id", "val"],
            [(1, "same"), (2, "new")],
            keylist=["id"],
        )
        assert " | " in result

    def test_matching_and_only_in_table1(self):
        result = compare_stats(
            ["id", "val"],
            [(1, "a"), (2, "b")],
            ["id", "val"],
            [(1, "a")],
            keylist=["id"],
        )
        assert "1 matching" in result
        assert "1 only in Table 1" in result

    def test_matching_and_only_in_table2(self):
        result = compare_stats(
            ["id", "val"],
            [(1, "a")],
            ["id", "val"],
            [(1, "a"), (2, "b")],
            keylist=["id"],
        )
        assert "1 matching" in result
        assert "1 only in Table 2" in result


# ---------------------------------------------------------------------------
# NULL / None values in data
# ---------------------------------------------------------------------------


class TestCompareStatsNullValues:
    def test_none_in_non_key_column_treated_as_empty_string_for_comparison(self):
        """None values in non-key columns are stringified as '' for comparison."""
        result = compare_stats(
            ["id", "val"],
            [(1, None)],
            ["id", "val"],
            [(1, None)],
            keylist=["id"],
        )
        # Both rows have the same key and same None value — counted as matching
        assert "1 matching" in result
        assert "differing" not in result

    def test_none_vs_string_in_non_key_column_causes_diff(self):
        result = compare_stats(
            ["id", "val"],
            [(1, None)],
            ["id", "val"],
            [(1, "something")],
            keylist=["id"],
        )
        assert "differing" in result

    def test_none_in_key_column_treated_as_empty_string_key(self):
        """None in key columns is normalized to '' — two None-keyed rows match."""
        result = compare_stats(
            ["id", "val"],
            [(None, "a")],
            ["id", "val"],
            [(None, "a")],
            keylist=["id"],
        )
        # None key maps to "" — same key in both tables → 1 matching row
        assert "1 matching" in result

    def test_none_key_vs_string_key_results_in_only_in_each(self):
        result = compare_stats(
            ["id"],
            [(None,)],
            ["id"],
            [("1",)],
            keylist=["id"],
        )
        assert "only in Table 1" in result
        assert "only in Table 2" in result


# ---------------------------------------------------------------------------
# Large numbers (comma formatting)
# ---------------------------------------------------------------------------


class TestCompareStatsLargeNumbers:
    def test_large_matching_count_uses_comma_formatting(self):
        n = 2000
        rows = [(i, "v") for i in range(n)]
        result = compare_stats(
            ["id", "val"],
            rows,
            ["id", "val"],
            rows,
            keylist=["id"],
        )
        assert "2,000 matching" in result

    def test_large_only_in_table1_uses_comma_formatting(self):
        n = 1500
        t1 = [(i,) for i in range(n)]
        t2 = [(i,) for i in range(500)]
        result = compare_stats(
            ["id"],
            t1,
            ["id"],
            t2,
            keylist=["id"],
        )
        assert "1,000 only in Table 1" in result


# ---------------------------------------------------------------------------
# Multi-column keys
# ---------------------------------------------------------------------------


class TestCompareStatsMultiColumnKey:
    def test_composite_key_matching_rows(self):
        result = compare_stats(
            ["a", "b", "val"],
            [(1, 2, "x"), (1, 3, "y")],
            ["a", "b", "val"],
            [(1, 2, "x"), (1, 3, "y")],
            keylist=["a", "b"],
        )
        assert "2 matching" in result
        assert "differing" not in result

    def test_composite_key_partial_overlap(self):
        result = compare_stats(
            ["a", "b", "val"],
            [(1, 1, "x"), (1, 2, "y")],
            ["a", "b", "val"],
            [(1, 1, "x"), (2, 1, "z")],
            keylist=["a", "b"],
        )
        assert "1 matching" in result
        assert "1 only in Table 1" in result
        assert "1 only in Table 2" in result


# ---------------------------------------------------------------------------
# Row order independence
# ---------------------------------------------------------------------------


class TestCompareStatsRowOrderIndependence:
    def test_matching_rows_in_different_order_shows_all_matching(self):
        result = compare_stats(
            ["id", "val"],
            [(2, "b"), (1, "a")],
            ["id", "val"],
            [(1, "a"), (2, "b")],
            keylist=["id"],
        )
        assert "2 matching" in result
        assert "differing" not in result

    def test_differing_rows_found_regardless_of_order(self):
        result = compare_stats(
            ["id", "val"],
            [(2, "B"), (1, "a")],
            ["id", "val"],
            [(1, "a"), (2, "b")],
            keylist=["id"],
        )
        assert "1 differing" in result
        assert "1 matching" in result
