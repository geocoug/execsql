"""Tests for string manipulation utilities in execsql.utils.strings."""

from __future__ import annotations

import pytest

from execsql.utils.strings import (
    clean_word,
    clean_words,
    dedup_words,
    encodings_match,
    fold_word,
    fold_words,
    is_doublequoted,
    trim_word,
    trim_words,
    unquoted,
    unquoted2,
    wo_quotes,
)


# ---------------------------------------------------------------------------
# clean_word / clean_words
# ---------------------------------------------------------------------------


class TestCleanWord:
    @pytest.mark.parametrize(
        "inp, expected",
        [
            ("hello", "hello"),
            ("hello world", "hello_world"),
            ("my-col", "my_col"),
            ("col.name", "col_name"),
            ("  spaced  ", "spaced"),
            ("123abc", "_123abc"),
            ("0leading", "_0leading"),
            ("_under", "_under"),
        ],
    )
    def test_clean_word(self, inp, expected):
        assert clean_word(inp) == expected

    def test_clean_words_list(self):
        result = clean_words(["hello world", "my-col", "123abc"])
        assert result == ["hello_world", "my_col", "_123abc"]

    def test_clean_words_empty_list(self):
        assert clean_words([]) == []


# ---------------------------------------------------------------------------
# trim_word / trim_words
# ---------------------------------------------------------------------------


class TestTrimWord:
    @pytest.mark.parametrize(
        "inp, blr, expected",
        [
            ("_hello_", "both", "hello"),
            ("  _hello_  ", "both", "hello"),
            ("_hello_", "left", "hello_"),
            ("_hello_", "right", "_hello"),
            ("_hello_", "none", "_hello_"),
            ("hello", "both", "hello"),
        ],
    )
    def test_trim_word(self, inp, blr, expected):
        assert trim_word(inp, blr) == expected

    def test_trim_words(self):
        result = trim_words(["_a_", "_b_"], "both")
        assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# fold_word / fold_words
# ---------------------------------------------------------------------------


class TestFoldWord:
    @pytest.mark.parametrize(
        "inp, spec, expected",
        [
            ("Hello", "lower", "hello"),
            ("Hello", "upper", "HELLO"),
            ("Hello", "no", "Hello"),
        ],
    )
    def test_fold_word(self, inp, spec, expected):
        assert fold_word(inp, spec) == expected

    def test_fold_words(self):
        result = fold_words(["Hello", "World"], "lower")
        assert result == ["hello", "world"]


# ---------------------------------------------------------------------------
# dedup_words
# ---------------------------------------------------------------------------


class TestDedupWords:
    def test_no_duplicates(self):
        assert dedup_words(["a", "b", "c"]) == ["a", "b", "c"]

    def test_simple_duplicate(self):
        result = dedup_words(["col", "col"])
        assert result[0] == "col"
        assert result[1] != "col"  # suffix added to second occurrence

    def test_case_insensitive_dedup(self):
        result = dedup_words(["Name", "name"])
        assert result[0] == "Name"
        assert result[1] != "name"

    def test_three_duplicates(self):
        result = dedup_words(["x", "x", "x"])
        assert len(set(r.lower() for r in result)) == 3

    def test_empty_list(self):
        assert dedup_words([]) == []


# ---------------------------------------------------------------------------
# is_doublequoted
# ---------------------------------------------------------------------------


class TestIsDoubleQuoted:
    @pytest.mark.parametrize(
        "val, expected",
        [
            ('"hello"', True),
            ('"hi there"', True),
            ("hello", False),
            ('"', False),
            ("''", False),
            ('""', True),
        ],
    )
    def test_is_doublequoted(self, val, expected):
        assert is_doublequoted(val) == expected


# ---------------------------------------------------------------------------
# unquoted / unquoted2
# ---------------------------------------------------------------------------


class TestUnquoted:
    def test_removes_double_quotes(self):
        assert unquoted('"hello"') == "hello"

    def test_removes_nested_double_quotes(self):
        # Only outer pair removed per iteration — may need multiple passes
        # The implementation loops until no more pairs to remove
        assert unquoted('"""hello"""') == "hello"

    def test_no_op_on_unquoted_string(self):
        assert unquoted("hello") == "hello"

    def test_single_char_string_unchanged(self):
        assert unquoted('"') == '"'

    def test_unquoted2_removes_single_quotes(self):
        assert unquoted2("'hello'") == "hello"

    def test_unquoted2_removes_double_quotes(self):
        assert unquoted2('"hello"') == "hello"

    def test_unquoted_custom_chars(self):
        # quotechars are iterated individually; "[" and "]" are different chars
        # so "[hello]" is not stripped (each check requires same char at both ends)
        assert unquoted("[hello]", "[]") == "[hello]"


# ---------------------------------------------------------------------------
# wo_quotes
# ---------------------------------------------------------------------------


class TestWoQuotes:
    @pytest.mark.parametrize(
        "inp, expected",
        [
            ('"hello"', "hello"),
            ("'world'", "world"),
            ("[bracketed]", "bracketed"),
            ("plain", "plain"),
            ('"  spaced  "', "  spaced  "),
        ],
    )
    def test_wo_quotes(self, inp, expected):
        assert wo_quotes(inp) == expected


# ---------------------------------------------------------------------------
# encodings_match
# ---------------------------------------------------------------------------


class TestEncodingsMatch:
    def test_identical(self):
        assert encodings_match("utf-8", "utf-8") is True

    def test_case_insensitive(self):
        assert encodings_match("UTF-8", "utf-8") is True

    def test_normalised_alias(self):
        # Removing hyphens: "utf-8" and "utf8" should match
        assert encodings_match("utf-8", "utf8") is True

    def test_latin1_aliases(self):
        # latin1 / iso-8859-1 / cp1252 are in the same equivalence group
        assert encodings_match("latin1", "iso-8859-1") is True

    def test_different_encodings(self):
        assert encodings_match("utf-8", "latin1") is False

    def test_koi8r_aliases(self):
        assert encodings_match("koi8-r", "koi8r") is True
