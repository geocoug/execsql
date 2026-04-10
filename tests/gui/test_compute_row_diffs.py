"""
Tests for execsql.gui.base.compute_row_diffs and _values_equal.

compute_row_diffs is a pure function — it takes two tables (headers + rows)
and a list of key column names, and returns per-row diff states and per-row
sets of changed column names.  No database, GUI, or file I/O involved.
"""

from __future__ import annotations

from decimal import Decimal

from execsql.gui.base import compute_row_diffs


# ---------------------------------------------------------------------------
# Empty / missing key cases → returns None
# ---------------------------------------------------------------------------


class TestComputeRowDiffsNoKeys:
    def test_empty_keylist_returns_none(self):
        assert compute_row_diffs(["id"], [(1,)], ["id"], [(1,)], keylist=[]) is None

    def test_key_not_in_headers1_returns_none(self):
        assert compute_row_diffs(["other"], [(1,)], ["id"], [(1,)], keylist=["id"]) is None

    def test_key_not_in_headers2_returns_none(self):
        assert compute_row_diffs(["id"], [(1,)], ["other"], [(1,)], keylist=["id"]) is None


# ---------------------------------------------------------------------------
# Identical tables
# ---------------------------------------------------------------------------


class TestComputeRowDiffsIdentical:
    def test_single_row_match(self):
        r = compute_row_diffs(["id", "a"], [(1, "x")], ["id", "a"], [(1, "x")], ["id"])
        assert r is not None
        assert r.table1_row_states == ["match"]
        assert r.table2_row_states == ["match"]
        assert r.table1_changed_cols == [set()]
        assert r.table2_changed_cols == [set()]
        assert "matching" in r.summary

    def test_multiple_rows_all_match(self):
        rows = [(1, "a"), (2, "b"), (3, "c")]
        r = compute_row_diffs(["id", "v"], rows, ["id", "v"], rows, ["id"])
        assert r is not None
        assert all(s == "match" for s in r.table1_row_states)
        assert all(s == "match" for s in r.table2_row_states)
        assert "3 matching" in r.summary


# ---------------------------------------------------------------------------
# All differing
# ---------------------------------------------------------------------------


class TestComputeRowDiffsDiffering:
    def test_single_column_differs(self):
        r = compute_row_diffs(
            ["id", "a", "b"],
            [(1, "x", "same")],
            ["id", "a", "b"],
            [(1, "y", "same")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["changed"]
        assert r.table1_changed_cols == [{"a"}]
        assert r.table2_changed_cols == [{"a"}]

    def test_multiple_columns_differ(self):
        r = compute_row_diffs(
            ["id", "a", "b", "c"],
            [(1, "x", "y", "same")],
            ["id", "a", "b", "c"],
            [(1, "X", "Y", "same")],
            ["id"],
        )
        assert r is not None
        assert r.table1_changed_cols == [{"a", "b"}]

    def test_all_non_key_columns_differ(self):
        r = compute_row_diffs(
            ["id", "a", "b"],
            [(1, "x", "y")],
            ["id", "a", "b"],
            [(1, "X", "Y")],
            ["id"],
        )
        assert r is not None
        assert r.table1_changed_cols == [{"a", "b"}]
        assert "1 differing" in r.summary


# ---------------------------------------------------------------------------
# Only in one table
# ---------------------------------------------------------------------------


class TestComputeRowDiffsOnlyInOne:
    def test_only_in_table1(self):
        r = compute_row_diffs(
            ["id", "a"],
            [(1, "x"), (2, "y")],
            ["id", "a"],
            [(1, "x")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states[1] == "only_t1"
        assert r.table1_changed_cols[1] == set()
        assert "1 only in Table 1" in r.summary

    def test_only_in_table2(self):
        r = compute_row_diffs(
            ["id", "a"],
            [(1, "x")],
            ["id", "a"],
            [(1, "x"), (3, "z")],
            ["id"],
        )
        assert r is not None
        assert r.table2_row_states[1] == "only_t2"
        assert "1 only in Table 2" in r.summary


# ---------------------------------------------------------------------------
# Mixed scenario
# ---------------------------------------------------------------------------


class TestComputeRowDiffsMixed:
    def test_match_changed_and_only(self):
        r = compute_row_diffs(
            ["id", "val"],
            [(1, "a"), (2, "b"), (3, "c")],
            ["id", "val"],
            [(1, "a"), (2, "B"), (4, "d")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states[0] == "match"
        assert r.table1_row_states[1] == "changed"
        assert r.table1_changed_cols[1] == {"val"}
        assert r.table1_row_states[2] == "only_t1"
        assert r.table2_row_states[2] == "only_t2"


# ---------------------------------------------------------------------------
# Different header order — columns matched by name, not position
# ---------------------------------------------------------------------------


class TestComputeRowDiffsDifferentOrder:
    def test_columns_matched_by_name_not_position(self):
        r = compute_row_diffs(
            ["id", "a", "b"],
            [(1, "x", "y")],
            ["id", "b", "a"],
            [(1, "y", "X")],  # b matches, a differs
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["changed"]
        assert r.table1_changed_cols == [{"a"}]

    def test_swapped_columns_all_match(self):
        """Same data, different column order → should be match."""
        r = compute_row_diffs(
            ["id", "a", "b"],
            [(1, "x", "y")],
            ["id", "b", "a"],
            [(1, "y", "x")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]


# ---------------------------------------------------------------------------
# None / NULL handling — None is distinct from ""
# ---------------------------------------------------------------------------


class TestComputeRowDiffsNullValues:
    def test_none_vs_none_is_match(self):
        r = compute_row_diffs(
            ["id", "a"],
            [(1, None)],
            ["id", "a"],
            [(1, None)],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]

    def test_none_vs_value_is_changed(self):
        r = compute_row_diffs(
            ["id", "a"],
            [(1, None)],
            ["id", "a"],
            [(1, "x")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["changed"]
        assert r.table1_changed_cols == [{"a"}]

    def test_none_vs_empty_string_is_changed(self):
        """None (SQL NULL) is semantically different from empty string."""
        r = compute_row_diffs(
            ["id", "a"],
            [(1, None)],
            ["id", "a"],
            [(1, "")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["changed"]
        assert r.table1_changed_cols == [{"a"}]


# ---------------------------------------------------------------------------
# Numeric type comparisons — native equality, not string comparison
# ---------------------------------------------------------------------------


class TestComputeRowDiffsNumericTypes:
    def test_int_vs_float_equal(self):
        """int(1) == float(1.0) → match, not false diff."""
        r = compute_row_diffs(
            ["id", "val"],
            [(1, 1)],
            ["id", "val"],
            [(1, 1.0)],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]

    def test_decimal_different_scale_equal(self):
        """Decimal('10.00') == Decimal('10.0') → match."""
        r = compute_row_diffs(
            ["id", "val"],
            [(1, Decimal("10.00"))],
            ["id", "val"],
            [(1, Decimal("10.0"))],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]

    def test_decimal_vs_int_equal(self):
        """Decimal('42') == int(42) → match."""
        r = compute_row_diffs(
            ["id", "val"],
            [(1, Decimal("42"))],
            ["id", "val"],
            [(1, 42)],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]

    def test_decimal_vs_float_equal(self):
        """Decimal('3.5') == float(3.5) → match."""
        r = compute_row_diffs(
            ["id", "val"],
            [(1, Decimal("3.5"))],
            ["id", "val"],
            [(1, 3.5)],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]

    def test_actually_different_numbers_are_changed(self):
        r = compute_row_diffs(
            ["id", "val"],
            [(1, 10)],
            ["id", "val"],
            [(1, 11)],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["changed"]

    def test_bool_vs_int_equal(self):
        """Python bool is a subclass of int: True == 1."""
        r = compute_row_diffs(
            ["id", "val"],
            [(1, True)],
            ["id", "val"],
            [(1, 1)],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]


# ---------------------------------------------------------------------------
# Multi-column key
# ---------------------------------------------------------------------------


class TestComputeRowDiffsMultiColumnKey:
    def test_composite_key(self):
        r = compute_row_diffs(
            ["k1", "k2", "val"],
            [(1, "a", "x"), (1, "b", "y")],
            ["k1", "k2", "val"],
            [(1, "a", "X"), (1, "b", "y")],
            ["k1", "k2"],
        )
        assert r is not None
        assert r.table1_row_states[0] == "changed"
        assert r.table1_changed_cols[0] == {"val"}
        assert r.table1_row_states[1] == "match"


# ---------------------------------------------------------------------------
# Row order independence
# ---------------------------------------------------------------------------


class TestComputeRowDiffsRowOrder:
    def test_different_sort_order_matches(self):
        r = compute_row_diffs(
            ["id", "val"],
            [(2, "b"), (1, "a")],
            ["id", "val"],
            [(1, "a"), (2, "b")],
            ["id"],
        )
        assert r is not None
        # Row 0 in table1 is id=2, should match id=2 in table2
        assert r.table1_row_states[0] == "match"
        assert r.table1_row_states[1] == "match"

    def test_different_sort_order_detects_diff(self):
        r = compute_row_diffs(
            ["id", "val"],
            [(2, "B"), (1, "a")],
            ["id", "val"],
            [(1, "a"), (2, "b")],
            ["id"],
        )
        assert r is not None
        # id=2 differs, id=1 matches
        assert r.table1_row_states[0] == "changed"  # id=2 in table1 row 0
        assert r.table1_row_states[1] == "match"  # id=1 in table1 row 1


# ---------------------------------------------------------------------------
# Duplicate PK handling — first occurrence wins
# ---------------------------------------------------------------------------


class TestComputeRowDiffsDuplicatePK:
    def test_duplicate_pk_keeps_first(self):
        """When a table has duplicate keys, the first row is used."""
        r = compute_row_diffs(
            ["id", "val"],
            [(1, "first"), (1, "second")],
            ["id", "val"],
            [(1, "first")],
            ["id"],
        )
        assert r is not None
        # First row (id=1, "first") matches; second row (id=1, "second") is
        # not part of the PK map and gets state "".
        assert r.table1_row_states[0] == "match"
        assert r.table1_row_states[1] == ""  # not classified (duplicate)


# ---------------------------------------------------------------------------
# Summary format
# ---------------------------------------------------------------------------


class TestComputeRowDiffsSummary:
    def test_tables_are_identical(self):
        r = compute_row_diffs(["id", "a"], [(1, "x")], ["id", "a"], [(1, "x")], ["id"])
        assert r is not None
        assert r.summary == "1 matching"

    def test_empty_tables(self):
        r = compute_row_diffs(["id", "a"], [], ["id", "a"], [], ["id"])
        assert r is not None
        assert r.summary == "Tables are identical"

    def test_large_numbers_formatted(self):
        rows1 = [(i, "v") for i in range(1500)]
        r = compute_row_diffs(["id", "a"], rows1, ["id", "a"], rows1, ["id"])
        assert r is not None
        assert "1,500 matching" in r.summary


# ---------------------------------------------------------------------------
# Columns only in one table are not compared
# ---------------------------------------------------------------------------


class TestComputeRowDiffsExtraColumns:
    def test_extra_column_in_table1_ignored(self):
        r = compute_row_diffs(
            ["id", "a", "extra"],
            [(1, "x", "e1")],
            ["id", "a"],
            [(1, "x")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]
        assert r.table1_changed_cols == [set()]

    def test_extra_column_in_table2_ignored(self):
        r = compute_row_diffs(
            ["id", "a"],
            [(1, "x")],
            ["id", "a", "extra"],
            [(1, "x", "e2")],
            ["id"],
        )
        assert r is not None
        assert r.table1_row_states == ["match"]
