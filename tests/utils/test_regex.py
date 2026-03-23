"""Tests for regex-building utilities in execsql.utils.regex."""

from __future__ import annotations

import re

import pytest

from execsql.utils.regex import (
    ins_fn_rxs,
    ins_quoted_rx,
    ins_rxs,
    ins_schema_rxs,
    ins_table_list_rxs,
    ins_table_rxs,
)


# ---------------------------------------------------------------------------
# ins_rxs
# ---------------------------------------------------------------------------


class TestInsRxs:
    def test_basic_strings(self):
        result = ins_rxs(("a", "b"), "prefix_", "_suffix")
        assert result == ("prefix_a_suffix", "prefix_b_suffix")

    def test_fragment1_is_tuple(self):
        # String concatenation: no spaces are added between fragments.
        result = ins_rxs(("x",), ("f1a", "f1b"), "end")
        assert "f1axend" in result
        assert "f1bxend" in result

    def test_fragment2_is_none(self):
        result = ins_rxs(("a", "b"), "pre_", None)
        assert result == ("pre_a", "pre_b")

    def test_fragment2_is_tuple(self):
        result = ins_rxs(("mid",), "start_", ("_e1", "_e2"))
        assert "start_mid_e1" in result
        assert "start_mid_e2" in result

    def test_both_fragments_are_tuples(self):
        result = ins_rxs(("c",), ("A", "B"), ("X", "Y"))
        assert len(result) == 4
        assert "AcX" in result
        assert "AcY" in result
        assert "BcX" in result
        assert "BcY" in result

    def test_returns_tuple(self):
        assert isinstance(ins_rxs(("x",), "a", "b"), tuple)

    def test_empty_rx_list(self):
        result = ins_rxs((), "pre", "suf")
        assert result == ()

    def test_regex_fragments_are_valid(self):
        # Ensure the returned strings can actually be compiled as regexes.
        frags = ins_rxs((r"\w+", r"\d+"), r"^\s*", r"\s*$")
        for pat in frags:
            re.compile(pat)  # should not raise


# ---------------------------------------------------------------------------
# ins_quoted_rx
# ---------------------------------------------------------------------------


class TestInsQuotedRx:
    def test_returns_two_variants(self):
        result = ins_quoted_rx("START_", "_END", r"\w+")
        assert len(result) == 2

    def test_unquoted_variant_present(self):
        result = ins_quoted_rx("", "", r"\w+")
        assert r"\w+" in result

    def test_quoted_variant_present(self):
        result = ins_quoted_rx("", "", r"\w+")
        assert r'"\w+"' in result

    def test_fragments_applied(self):
        result = ins_quoted_rx("PRE_", "_POST", r"\d+")
        assert r"PRE_\d+_POST" in result
        assert r'PRE_"\d+"_POST' in result


# ---------------------------------------------------------------------------
# ins_schema_rxs
# ---------------------------------------------------------------------------


class TestInsSchemaRxs:
    def test_returns_three_variants(self):
        result = ins_schema_rxs("", "")
        assert len(result) == 3

    def test_all_compilable(self):
        for pat in ins_schema_rxs("^", "$"):
            re.compile(pat)

    def test_double_quoted_schema_matches(self):
        # Each pattern must be tested individually — they all use named group 'schema'
        # so they can't be combined with | into a single pattern.
        pats = ins_schema_rxs("", "")
        matched = False
        for pat in pats:
            m = re.match(pat, '"my schema"')
            if m:
                try:
                    assert m.group("schema") == "my schema"
                    matched = True
                    break
                except IndexError:
                    continue
        assert matched, "No pattern matched double-quoted schema with spaces"

    def test_unquoted_schema_matches(self):
        pats = ins_schema_rxs("", "")
        for pat in pats:
            m = re.match(pat, "myschema")
            if m:
                assert m.group("schema") == "myschema"
                break
        else:
            pytest.fail("No pattern matched unquoted schema")

    def test_bracket_schema_matches(self):
        pats = ins_schema_rxs("", "")
        for pat in pats:
            m = re.match(pat, "[my schema]")
            if m:
                assert m.group("schema") == "my schema"
                break
        else:
            pytest.fail("No pattern matched bracket schema")

    def test_suffix_renames_group(self):
        pats = ins_schema_rxs("", "", suffix="2")
        for pat in pats:
            m = re.match(pat, "myschema")
            if m:
                assert m.group("schema2") == "myschema"
                break
        else:
            pytest.fail("No suffixed pattern matched")

    def test_fragments_applied(self):
        pats = ins_schema_rxs(r"^\s*", r"\s*$")
        for pat in pats:
            assert pat.startswith(r"^\s*")
            assert pat.endswith(r"\s*$")


# ---------------------------------------------------------------------------
# ins_table_rxs
# ---------------------------------------------------------------------------


class TestInsTableRxs:
    def test_returns_eight_variants(self):
        result = ins_table_rxs("", "")
        assert len(result) == 8

    def test_all_compilable(self):
        for pat in ins_table_rxs("^", "$"):
            re.compile(pat)

    def test_simple_unquoted_table(self):
        pats = ins_table_rxs("", "")
        for pat in pats:
            m = re.match(pat, "mytable")
            if m:
                assert m.group("table") == "mytable"
                break
        else:
            pytest.fail("No pattern matched simple unquoted table")

    def test_schema_qualified_table(self):
        pats = ins_table_rxs("", "")
        for pat in pats:
            m = re.match(pat, "myschema.mytable")
            if m and m.group("table") == "mytable":
                assert m.group("schema") == "myschema"
                break
        else:
            pytest.fail("No pattern matched schema.table")

    def test_double_quoted_table(self):
        pats = ins_table_rxs("", "")
        for pat in pats:
            m = re.match(pat, '"my table"')
            if m and m.group("table") == "my table":
                break
        else:
            pytest.fail("No pattern matched double-quoted table name")

    def test_suffix_renames_groups(self):
        pats = ins_table_rxs("", "", suffix="2")
        for pat in pats:
            m = re.match(pat, "myschema.mytable")
            if m:
                try:
                    assert m.group("table2") == "mytable"
                    assert m.group("schema2") == "myschema"
                    break
                except IndexError:
                    continue
        else:
            pytest.fail("No suffixed pattern matched")


# ---------------------------------------------------------------------------
# ins_table_list_rxs
# ---------------------------------------------------------------------------


class TestInsTableListRxs:
    def test_returns_two_variants(self):
        result = ins_table_list_rxs("", "")
        assert len(result) == 2

    def test_all_compilable(self):
        for pat in ins_table_list_rxs("", ""):
            re.compile(pat)

    def test_single_table(self):
        pats = ins_table_list_rxs("", "")
        for pat in pats:
            m = re.match(pat, "mytable")
            if m:
                assert "mytable" in m.group("tables")
                break
        else:
            pytest.fail("No pattern matched single table")

    def test_comma_separated_tables(self):
        pats = ins_table_list_rxs("", "")
        for pat in pats:
            m = re.match(pat, "table1, table2")
            if m:
                tables_str = m.group("tables")
                assert "table1" in tables_str
                assert "table2" in tables_str
                break
        else:
            pytest.fail("No pattern matched comma-separated tables")


# ---------------------------------------------------------------------------
# ins_fn_rxs
# ---------------------------------------------------------------------------


class TestInsFnRxs:
    def test_returns_two_variants(self):
        result = ins_fn_rxs("", "")
        assert len(result) == 2

    def test_all_compilable(self):
        for pat in ins_fn_rxs("", ""):
            re.compile(pat)

    def test_simple_filename(self):
        pats = ins_fn_rxs("", "")
        for pat in pats:
            m = re.match(pat, "output.csv")
            if m:
                assert "output.csv" in m.group("filename")
                break
        else:
            pytest.fail("No pattern matched simple filename")

    def test_quoted_filename_with_spaces(self):
        pats = ins_fn_rxs("", "")
        for pat in pats:
            m = re.match(pat, '"my output.csv"')
            if m:
                assert "my output.csv" in m.group("filename")
                break
        else:
            pytest.fail("No pattern matched quoted filename with spaces")

    def test_custom_symbolic_name(self):
        pats = ins_fn_rxs("", "", symbolicname="infile")
        for pat in pats:
            m = re.match(pat, "data.txt")
            if m:
                assert "data.txt" in m.group("infile")
                break
        else:
            pytest.fail("No pattern matched with custom symbolic name")
